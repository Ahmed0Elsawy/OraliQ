"""
Backup / restore tool tests. PostgreSQL is not installed or contacted: pg_dump, pg_restore, psql
and gpg are replaced by fake_pg.py, run as real child processes through the same code paths.

    python -m pytest ops/backup/tests -q
"""
import datetime as dt
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oraliq_db_backup as tool  # noqa: E402

FAKE = str(Path(__file__).with_name("fake_pg.py"))
PASSWORD = "S3cr3t-pg-pass-7f2a91"
SOURCE_URL = f"postgresql://oraliq:{PASSWORD}@db.internal.example:5432/oraliq?sslmode=require"
TARGET_PASSWORD = "R3st0re-pass-c4d1e9"
TARGET_URL = f"postgresql://restorer:{TARGET_PASSWORD}@db-test.internal.example:5432/oraliq_restore_test"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    bdir = tmp_path / "backups"
    for name in ("pg_dump", "pg_restore", "psql", "gpg"):
        monkeypatch.setitem(tool.TOOLS, name, [sys.executable, FAKE, name])
    # tmp_path lives in the temp folder, which the real check forbids; keep only the app-folder rule here
    # (test_backup_dir_must_be_outside_app_and_temp checks the real rule).
    monkeypatch.setattr(tool, "_forbidden_roots", lambda: [Path(__file__).resolve().parents[3]])
    for k in list(os.environ):
        if k.startswith(("BACKUP_", "FAKE_", "RESTORE_")) or k in ("DATABASE_URL", "DATABASE_URL_DIRECT", "PG_BINDIR"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BACKUP_DIR", str(bdir))
    monkeypatch.setenv("BACKUP_DATABASE_URL", SOURCE_URL)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("FAKE_STATE", str(tmp_path / "restored.json"))
    monkeypatch.setenv("BACKUP_LOG_FILE", str(tmp_path / "backup.log"))
    tool._SECRETS.clear()
    return {"dir": bdir, "tmp": tmp_path}


def calls(e):
    p = e["tmp"] / "calls.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def backups(e):
    return sorted(p.name for p in e["dir"].iterdir() if tool.NAME_RE.match(p.name)) if e["dir"].exists() else []


def alert_hook(monkeypatch, e):
    out = e["tmp"] / "alerts.txt"
    script = e["tmp"] / "alert.py"
    script.write_text("import sys\nopen(sys.argv[1], 'a', encoding='utf-8').write(' '.join(sys.argv[2:]) + '\\n')\n")
    monkeypatch.setenv("BACKUP_ALERT_COMMAND", f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}" "{out.as_posix()}"')
    return out


# ── 1. A good backup ──────────────────────────────────────────────────────────

def test_1_successful_backup_is_compressed_checksummed_verified(env):
    assert tool.main(["backup"]) == 0
    names = backups(env)
    assert len(names) == 1 and names[0].endswith(".dump.gz")
    f = env["dir"] / names[0]
    m = json.loads(f.with_name(f.name + ".json").read_text())
    assert m["status"] == "verified" and m["database"] == "oraliq"
    assert m["tables"] == ["public.exam_submissions", "public.questions", "public.users"]
    assert m["sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert f.with_name(f.name + ".sha256").read_text().split()[0] == m["sha256"]
    assert gzip.decompress(f.read_bytes()).startswith(b"PGDMP")
    assert f.stat().st_size < 200_000                       # compressed
    assert not list(env["dir"].glob("*.partial"))
    dump_call = [c for c in calls(env) if c["tool"] == "pg_dump" and "--version" not in c["args"]][0]
    assert "--format=custom" in dump_call["args"] and "--schema=public" in dump_call["args"]
    assert tool.main(["verify", names[0]]) == 0
    if os.name == "posix":
        assert oct(f.stat().st_mode & 0o777) == "0o600"


def test_1b_credentials_go_through_a_private_pgpass_never_arguments(env):
    assert tool.main(["backup"]) == 0
    for c in calls(env):
        assert PASSWORD not in json.dumps(c["args"]) and "postgresql://" not in json.dumps(c["args"])
        assert c["env_has_pgpassword"] is False
    used = {c["pgpassfile"] for c in calls(env) if c["pgpassfile"]}
    assert used and not any(Path(p).exists() for p in used)      # removed after the run


# ── 2. Connection failure ─────────────────────────────────────────────────────

def test_2_connection_failure_is_reported_and_alerted(env, monkeypatch, capsys):
    alerts = alert_hook(monkeypatch, env)
    monkeypatch.setenv("FAKE_CONNECT_FAIL", "1")
    assert tool.main(["backup"]) == 1
    out = capsys.readouterr().out
    assert '"stage": "connect"' in out and "password authentication failed" in out
    assert backups(env) == [] and not list(env["dir"].glob("*.partial"))
    assert "FAILED" in alerts.read_text() and "connect" in alerts.read_text()


def test_2b_a_client_older_than_the_server_is_refused(env, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_SERVER_NUM", "170002")
    assert tool.main(["backup"]) == 1
    assert "older than the server" in capsys.readouterr().out


# ── 3. pg_dump failure ────────────────────────────────────────────────────────

def test_3_pg_dump_failure_leaves_nothing_behind(env, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_PG_DUMP_FAIL", "1")
    assert tool.main(["backup"]) == 1
    out = capsys.readouterr().out
    assert '"stage": "pg_dump"' in out and "permission denied" in out
    assert backups(env) == [] and not list(env["dir"].glob("*.partial"))


# ── 4. Compression failure ────────────────────────────────────────────────────

def test_4_compression_failure_is_caught(env, monkeypatch, capsys):
    class FullDisk:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def write(self, _): raise OSError(28, "No space left on device")

    monkeypatch.setattr(tool, "_open_gzip", lambda path: FullDisk())
    assert tool.main(["backup"]) == 1
    out = capsys.readouterr().out
    assert '"stage": "compress"' in out and "No space left" in out
    assert backups(env) == []


# ── 5. Wrong checksum ─────────────────────────────────────────────────────────

def test_5_checksum_mismatch_is_detected_and_blocks_restore(env, monkeypatch, capsys):
    assert tool.main(["backup"]) == 0
    f = env["dir"] / backups(env)[0]
    data = bytearray(f.read_bytes())
    data[100] ^= 0xFF
    f.write_bytes(bytes(data))
    assert tool.main(["verify", f.name]) == 1
    assert '"stage": "checksum"' in capsys.readouterr().out
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    assert tool.main(["restore", f.name]) == 1
    assert not [c for c in calls(env) if c.get("restore")]          # target never touched


# ── 6. Damaged file ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("damage", ["truncated", "not_an_archive", "not_gzip"])
def test_6_a_damaged_backup_is_refused_even_with_a_matching_checksum(env, monkeypatch, capsys, damage):
    assert tool.main(["backup"]) == 0
    f = env["dir"] / backups(env)[0]
    raw = f.read_bytes()
    bad = {"truncated": raw[: len(raw) // 2],
           "not_an_archive": gzip.compress(b"this is not a pg_dump archive"),
           "not_gzip": b"plain bytes, never compressed"}[damage]
    f.write_bytes(bad)
    f.with_name(f.name + ".sha256").write_text(f"{hashlib.sha256(bad).hexdigest()}  {f.name}\n")
    assert tool.main(["verify", f.name]) == 1
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    assert tool.main(["restore", f.name]) == 1
    out = capsys.readouterr().out
    assert '"stage": "verify"' in out
    assert not [c for c in calls(env) if c.get("restore")]


# ── 7. Restore safety ─────────────────────────────────────────────────────────

def test_7_restore_into_an_empty_test_database(env, monkeypatch, capsys):
    assert tool.main(["backup"]) == 0
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    assert tool.main(["restore", backups(env)[0]]) == 0
    restore_call = [c for c in calls(env) if c.get("restore")][0]
    assert "--single-transaction" in restore_call["args"] and "--clean" not in restore_call["args"]
    assert "--dbname=oraliq_restore_test" in restore_call["args"]
    out = capsys.readouterr().out
    assert '"tables_restored": 3' in out and '"public.users": 5' in out


def test_7b_an_existing_database_is_not_overwritten_without_explicit_confirmation(env, monkeypatch, capsys):
    assert tool.main(["backup"]) == 0
    name = backups(env)[0]
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    monkeypatch.setenv("FAKE_TARGET_TABLE_COUNT", "12")
    assert tool.main(["restore", name]) == 4
    assert tool.main(["restore", name, "--replace-existing"]) == 4
    assert tool.main(["restore", name, "--replace-existing", "--confirm", "oraliq"]) == 4    # wrong name
    assert not [c for c in calls(env) if c.get("restore")]
    assert "already has 12 tables" in capsys.readouterr().out
    assert tool.main(["restore", name, "--replace-existing", "--confirm", "oraliq_restore_test"]) == 0
    assert "--clean" in [c for c in calls(env) if c.get("restore")][0]["args"]


def test_7c_the_source_database_is_refused_as_a_target(env, monkeypatch, capsys):
    assert tool.main(["backup"]) == 0
    name = backups(env)[0]
    monkeypatch.setenv("RESTORE_DATABASE_URL", SOURCE_URL)
    monkeypatch.setenv("FAKE_TARGET_TABLE_COUNT", "12")
    assert tool.main(["restore", name, "--replace-existing", "--confirm", "oraliq"]) == 4
    assert "taken from" in capsys.readouterr().out
    assert not [c for c in calls(env) if c.get("restore")]


def test_7d_no_target_named_means_nothing_happens(env, capsys):
    assert tool.main(["backup"]) == 0
    assert tool.main(["restore", backups(env)[0]]) == 4
    assert "no restore target" in capsys.readouterr().out


def test_7e_check_only_never_connects(env, monkeypatch):
    assert tool.main(["backup"]) == 0
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    before = len(calls(env))
    assert tool.main(["restore", backups(env)[0], "--check-only"]) == 0
    assert all(c["tool"] == "pg_restore" and "--list" in c["args"] for c in calls(env)[before:])


def test_7f_a_failed_restore_and_missing_tables_are_reported(env, monkeypatch):
    assert tool.main(["backup"]) == 0
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    monkeypatch.setenv("FAKE_RESTORE_FAIL", "1")
    assert tool.main(["restore", backups(env)[0]]) == 1
    monkeypatch.delenv("FAKE_RESTORE_FAIL")
    monkeypatch.setenv("FAKE_RESTORE_DROP", "public.questions")
    assert tool.main(["restore", backups(env)[0]]) == 1      # report shows a table that did not arrive


# ── 8 + 9. Retention ──────────────────────────────────────────────────────────

def make_old_backup(d: Path, days_ago: int, now: dt.datetime):
    created = now - dt.timedelta(days=days_ago)
    name = f"oraliq_oraliq_{created.strftime('%Y%m%dT%H%M%SZ')}.dump.gz"
    p = d / name
    p.write_bytes(b"x")
    digest = hashlib.sha256(b"x").hexdigest()
    (d / (name + ".sha256")).write_text(f"{digest}  {name}\n")
    (d / (name + ".json")).write_text(json.dumps({"format": tool.FORMAT, "status": "verified",
                                                   "created_at": created.isoformat(), "sha256": digest}))
    return name


def test_8_retention_keeps_30_days_and_a_minimum_count(env, monkeypatch):
    d = env["dir"]
    d.mkdir(mode=0o700)
    now = tool._utcnow()
    ages = [1, 5, 10, 29, 31, 35, 40, 60]
    names = {a: make_old_backup(d, a, now) for a in ages}
    (d / "notes.txt").write_text("not ours")
    (d / "oraliq_oraliq_20200101T000000Z.dump.gz.partial").write_text("incomplete")
    monkeypatch.setenv("BACKUP_MIN_KEEP", "3")
    removed = tool.apply_retention(d, now)
    assert sorted(removed) == sorted(names[a] for a in (31, 35, 40, 60))
    left = backups(env)
    assert all(names[a] in left for a in (1, 5, 10, 29))
    assert (d / "notes.txt").exists() and (d / "oraliq_oraliq_20200101T000000Z.dump.gz.partial").exists()
    assert not (d / (names[60] + ".json")).exists()

    # The minimum count wins over age: with only old backups, the newest few stay.
    for a in (1, 5, 10, 29):
        for suffix in ("", ".sha256", ".json"):
            (d / (names[a] + suffix)).unlink()
    for a in (100, 200, 300, 400):
        make_old_backup(d, a, now)
    tool.apply_retention(d, now)
    assert len(backups(env)) == 3


def test_8b_retention_days_are_configurable(env, monkeypatch):
    d = env["dir"]
    d.mkdir(mode=0o700)
    now = tool._utcnow()
    for a in (1, 3, 8, 9, 10):
        make_old_backup(d, a, now)
    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "7")
    monkeypatch.setenv("BACKUP_MIN_KEEP", "1")
    assert len(tool.apply_retention(d, now)) == 3


def test_9_a_failed_backup_never_prunes_old_ones(env, monkeypatch):
    d = env["dir"]
    d.mkdir(mode=0o700)
    now = tool._utcnow()
    old = [make_old_backup(d, a, now) for a in (40, 50, 60, 70, 80, 90, 100, 110)]
    monkeypatch.setenv("BACKUP_MIN_KEEP", "1")
    for fail_var in ("FAKE_CONNECT_FAIL", "FAKE_PG_DUMP_FAIL"):
        monkeypatch.setenv(fail_var, "1")
        assert tool.main(["backup"]) == 1
        monkeypatch.delenv(fail_var)
    assert sorted(backups(env)) == sorted(old)
    # ...and a successful one does prune them (all are older than 30 days; the new one is kept)
    assert tool.main(["backup"]) == 0
    assert len(backups(env)) == 1


# ── 10. Secrets stay out of logs ──────────────────────────────────────────────

def test_10_no_password_or_connection_string_in_any_output(env, monkeypatch, capsys):
    alerts = alert_hook(monkeypatch, env)
    for var in ("FAKE_CONNECT_FAIL", "FAKE_PG_DUMP_FAIL"):
        monkeypatch.setenv(var, "1")
        tool.main(["backup"])
        monkeypatch.delenv(var)
    tool.main(["backup"])
    monkeypatch.setenv("RESTORE_DATABASE_URL", TARGET_URL)
    monkeypatch.setenv("FAKE_TARGET_TABLE_COUNT", "2")
    tool.main(["restore", backups(env)[0]])
    seen = capsys.readouterr()
    everything = seen.out + seen.err + (env["tmp"] / "backup.log").read_text(encoding="utf-8") + alerts.read_text(encoding="utf-8")
    for secret in (PASSWORD, TARGET_PASSWORD, SOURCE_URL, TARGET_URL):
        assert secret not in everything
    assert "***" in everything                                 # the tools' messages were redacted, not dropped


# ── Concurrency, location, encryption, off-site ───────────────────────────────

def test_only_one_backup_runs_at_a_time(env, capsys):
    env["dir"].mkdir(mode=0o700)
    with tool.Lock(env["dir"]):
        assert tool.main(["backup"]) == 1
    assert '"stage": "lock"' in capsys.readouterr().out
    assert tool.main(["backup"]) == 0


def test_backup_dir_must_be_outside_app_and_temp(env, monkeypatch, capsys):
    monkeypatch.undo()  # restore the real _forbidden_roots
    monkeypatch.setitem(tool.TOOLS, "psql", [sys.executable, FAKE, "psql"])
    monkeypatch.setenv("BACKUP_DATABASE_URL", SOURCE_URL)
    monkeypatch.setenv("BACKUP_DIR", str(env["tmp"] / "inside-temp"))
    assert tool.main(["backup"]) == 1
    app_dir = Path(tool.__file__).resolve().parents[2] / "backups-here"
    monkeypatch.setenv("BACKUP_DIR", str(app_dir))
    assert tool.main(["backup"]) == 1
    monkeypatch.delenv("BACKUP_DIR")
    assert tool.main(["backup"]) == 1
    out = capsys.readouterr().out
    assert out.count("outside the application and temporary folders") == 2 and "BACKUP_DIR is not set" in out
    assert not app_dir.exists()


def test_encrypted_backup_keeps_no_plaintext_copy(env, monkeypatch):
    monkeypatch.setenv("BACKUP_GPG_RECIPIENT", "backups@oraliq.example")
    assert tool.main(["backup"]) == 0
    names = backups(env)
    assert len(names) == 1 and names[0].endswith(".dump.gz.gpg")
    f = env["dir"] / names[0]
    assert f.read_bytes().startswith(b"GPGFAKE")
    assert not list(env["dir"].glob("*.dump.gz")) and not list(env["dir"].glob("*.partial"))
    assert json.loads(f.with_name(f.name + ".json").read_text())["encrypted"] is True
    assert tool.main(["verify", names[0]]) == 0


def test_encryption_can_be_made_mandatory(env, monkeypatch):
    monkeypatch.setenv("BACKUP_REQUIRE_ENCRYPTION", "1")
    assert tool.main(["backup"]) == 1
    assert backups(env) == []


def test_offsite_copy_success_failure_and_requirement(env, monkeypatch):
    remote = env["tmp"] / "remote"
    remote.mkdir()
    copier = env["tmp"] / "copy.py"
    copier.write_text("import shutil, sys\nfor p in sys.argv[2:]: shutil.copy(p, sys.argv[1])\n")
    monkeypatch.setenv("BACKUP_UPLOAD_COMMAND", f'"{Path(sys.executable).as_posix()}" "{copier.as_posix()}" "{remote.as_posix()}"')
    assert tool.main(["backup"]) == 0
    assert len(list(remote.iterdir())) == 3

    monkeypatch.setenv("BACKUP_UPLOAD_COMMAND", f'"{Path(sys.executable).as_posix()}" -c "import sys; sys.exit(5)"')
    assert tool.main(["backup"]) == 3                          # verified locally, flagged as not off-site

    monkeypatch.delenv("BACKUP_UPLOAD_COMMAND")
    monkeypatch.setenv("BACKUP_REQUIRE_OFFSITE", "1")
    assert tool.main(["backup"]) == 3


def test_an_empty_archive_is_not_accepted(env, monkeypatch, capsys):
    monkeypatch.setenv("FAKE_PG_DUMP_TABLES", "")
    assert tool.main(["backup"]) == 1
    assert "expected at least 1" in capsys.readouterr().out
    assert backups(env) == []


def test_list_shows_date_size_and_status(env, capsys):
    assert tool.main(["backup"]) == 0
    capsys.readouterr()
    assert tool.main(["list"]) == 0
    out = capsys.readouterr().out
    assert backups(env)[0] in out and "3 tables" in out and "MB" in out
