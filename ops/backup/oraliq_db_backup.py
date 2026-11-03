#!/usr/bin/env python3
"""
OralIQ PostgreSQL backup and restore — production tool for a Linux server.

    oraliq_db_backup.py backup                      # nightly: dump, compress, verify, (encrypt), keep, prune
    oraliq_db_backup.py list                        # backups in BACKUP_DIR with date, size, status
    oraliq_db_backup.py verify  FILE                # checksum + gzip integrity + pg_restore --list
    oraliq_db_backup.py restore FILE --target-env RESTORE_DATABASE_URL
                                    [--replace-existing --confirm DBNAME] [--check-only]

Standard library only (Python 3.8+); needs the PostgreSQL client tools (pg_dump, pg_restore,
psql) of the server's major version or newer, and gpg only if encryption is turned on. It does not
import the OralIQ app, so it runs from cron/systemd on its own. See README.md next to it.

A backup counts as done only after every step passed: connection and version check, pg_dump in
custom format, gzip, a full decompress + header check, `pg_restore --list` reading the archive
back, optional encryption, SHA-256, and an atomic rename. Until then it is a .partial file that is
removed on failure. Old backups are pruned only after a new one succeeded.

Restore never targets anything by default: the target URL is read from an environment variable
you name, a database that already has tables is refused unless --replace-existing and
--confirm <its name> are both given, and the database the backups are taken from is refused
unless --i-am-restoring-production is added as well.

Passwords and connection strings never appear on command lines (a private .pgpass file is used)
or in logs (every message and every tool's stderr is redacted).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

FORMAT = "oraliq-pg-backup/1"
NAME_RE = re.compile(r"^oraliq_(?P<db>[A-Za-z0-9_-]+)_(?P<ts>\d{8}T\d{6}Z)\.dump\.gz(?P<gpg>\.gpg)?$")
CHUNK = 1024 * 1024

# Tool commands. PG_BINDIR selects a client version (e.g. /usr/lib/postgresql/16/bin); tests
# replace these with fakes.
TOOLS: Dict[str, List[str]] = {"pg_dump": ["pg_dump"], "pg_restore": ["pg_restore"], "psql": ["psql"], "gpg": ["gpg"]}

EXIT_OK, EXIT_FAILED, EXIT_OFFSITE_FAILED, EXIT_REFUSED = 0, 1, 3, 4


class BackupError(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message


# ── Logging with redaction ────────────────────────────────────────────────────

_SECRETS: List[str] = []
_URL_CRED = re.compile(r"(postgres(?:ql)?(?:\+\w+)?://)[^@\s/]+@", re.I)
_KV_PASSWORD = re.compile(r"(password\s*[=:]\s*)\S+", re.I)


def remember_secret(value: Optional[str]) -> None:
    if value and len(value) >= 4 and value not in _SECRETS:
        _SECRETS.append(value)


def redact(text: str) -> str:
    text = _URL_CRED.sub(r"\1***@", text or "")
    text = _KV_PASSWORD.sub(r"\1***", text)
    for s in sorted(_SECRETS, key=len, reverse=True):
        text = text.replace(s, "***")
    return text


def log(event: str, **fields) -> None:
    fields = {k: (redact(v) if isinstance(v, str) else v) for k, v in fields.items()}
    line = json.dumps({"ts": _utcnow().isoformat(), "event": event, **fields}, ensure_ascii=False, default=str)
    print(line, flush=True)
    log_file = os.environ.get("BACKUP_LOG_FILE", "").strip()
    if log_file:
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# ── Connection settings (never on a command line) ─────────────────────────────

class Conn:
    """A PostgreSQL connection parsed from a URL, handed to the client tools via libpq env vars
    and a private .pgpass file — never as an argument, where `ps` would show it."""

    def __init__(self, url: str):
        if not url:
            raise BackupError("config", "no database URL configured")
        parts = urlsplit(url.strip())
        scheme = parts.scheme.split("+", 1)[0].lower()
        if scheme not in ("postgres", "postgresql"):
            raise BackupError("config", "the database URL is not a PostgreSQL URL")
        self.host = parts.hostname or ""
        self.port = str(parts.port or 5432)
        self.user = unquote(parts.username or "")
        self.password = unquote(parts.password or "")
        self.dbname = unquote(parts.path.lstrip("/")) or self.user
        if not self.host or not self.dbname:
            raise BackupError("config", "the database URL has no host or database name")
        self.params = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        remember_secret(self.password)
        remember_secret(url.strip())
        self._dir: Optional[str] = None

    @property
    def identity(self) -> Tuple[str, str, str]:
        return (self.host.lower(), self.port, self.dbname)

    def env(self) -> Dict[str, str]:
        env = dict(os.environ)
        for k in ("DATABASE_URL", "DATABASE_URL_DIRECT", "BACKUP_DATABASE_URL", "RESTORE_DATABASE_URL", "PGPASSWORD"):
            env.pop(k, None)
        env.update({"PGHOST": self.host, "PGPORT": self.port, "PGDATABASE": self.dbname,
                    "PGUSER": self.user, "PGAPPNAME": "oraliq-backup", "PGCONNECT_TIMEOUT": "15"})
        mapping = {"sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT", "sslcert": "PGSSLCERT",
                   "sslkey": "PGSSLKEY", "connect_timeout": "PGCONNECT_TIMEOUT", "target_session_attrs": "PGTARGETSESSIONATTRS"}
        for k, v in self.params.items():
            if k in mapping:
                env[mapping[k]] = v
        if self.password:
            if self._dir is None:
                self._dir = tempfile.mkdtemp(prefix="oraliq-pg-")
                os.chmod(self._dir, 0o700)
                path = os.path.join(self._dir, "pgpass")
                esc = self.password.replace("\\", "\\\\").replace(":", "\\:")
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(f"*:*:*:*:{esc}\n")
            env["PGPASSFILE"] = os.path.join(self._dir, "pgpass")
        return env

    def close(self) -> None:
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None


def tool(name: str) -> List[str]:
    cmd = list(TOOLS[name])
    bindir = os.environ.get("PG_BINDIR", "").strip()
    if bindir and name != "gpg" and len(cmd) == 1:
        cmd[0] = os.path.join(bindir, cmd[0])
    return cmd


def run(name: str, args: List[str], env: Dict[str, str], stage: str, timeout: int = 600) -> str:
    try:
        p = subprocess.run(tool(name) + args, env=env, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise BackupError(stage, f"{name} is not installed (install the PostgreSQL client tools)")
    except subprocess.TimeoutExpired:
        raise BackupError(stage, f"{name} timed out after {timeout}s")
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise BackupError(stage, f"{name} exited {p.returncode}: {' | '.join(err) or 'no message'}")
    return p.stdout.decode("utf-8", "replace")


def psql(conn: Conn, sql: str, stage: str) -> str:
    return run("psql", ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], conn.env(), stage, timeout=120).strip()


def _major(version_text: str) -> int:
    m = re.search(r"(\d+)(?:\.\d+)?", version_text)
    return int(m.group(1)) if m else 0


def check_connection(conn: Conn) -> Dict[str, object]:
    """Fails with stage 'connect' when the server can't be reached or refuses the login."""
    psql(conn, "select 1", "connect")
    server_num = int(psql(conn, "show server_version_num", "connect") or 0)
    server_major = server_num // 10000
    client_major = _major(run("pg_dump", ["--version"], conn.env(), "connect", timeout=30))
    if client_major and server_major and client_major < server_major:
        raise BackupError("connect", f"pg_dump {client_major} is older than the server ({server_major}); "
                                     "install the matching client or set PG_BINDIR")
    return {"server_major": server_major, "pg_dump_major": client_major}


# ── Settings ──────────────────────────────────────────────────────────────────

def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    return max(minimum, int(raw)) if raw.isdigit() else default


def source_url() -> str:
    for k in ("BACKUP_DATABASE_URL", "DATABASE_URL_DIRECT", "DATABASE_URL"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _forbidden_roots() -> List[Path]:
    roots = [Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/tmp"), Path("/dev/shm")]
    app_dir = os.environ.get("BACKUP_APP_DIR", "").strip()
    roots.append(Path(app_dir) if app_dir else Path(__file__).resolve().parents[2])  # the OralIQ Web folder
    return roots


def backup_dir(create: bool) -> Path:
    raw = os.environ.get("BACKUP_DIR", "").strip()
    if not raw:
        raise BackupError("config", "BACKUP_DIR is not set (e.g. /var/backups/oraliq)")
    d = Path(raw).resolve()
    for root in _forbidden_roots():
        try:
            root = root.resolve()
        except OSError:
            continue
        if d == root or root in d.parents:
            raise BackupError("config", f"BACKUP_DIR must be outside the application and temporary folders ({root})")
    if create:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not d.is_dir():
        raise BackupError("config", f"BACKUP_DIR {d} does not exist")
    if os.name == "posix":
        mode = stat.S_IMODE(d.stat().st_mode)
        if mode & 0o077:
            raise BackupError("config", f"BACKUP_DIR {d} is accessible to other users (mode {oct(mode)}); run: chmod 700 {d}")
    return d


# ── Single-run lock ───────────────────────────────────────────────────────────

class Lock:
    """An OS file lock on BACKUP_DIR/.lock: released by the kernel if the process dies."""

    def __init__(self, directory: Path):
        self.path = directory / ".lock"
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            if os.name == "posix":
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.fh.close()
            raise BackupError("lock", "another backup or restore is already running on this BACKUP_DIR")
        return self

    def __exit__(self, *exc):
        try:
            if os.name != "posix":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self.fh.close()


# ── Building blocks ───────────────────────────────────────────────────────────

def _open_gzip(path: Path):
    """The compressed output stream (a seam for tests that simulate a full disk)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return gzip.GzipFile(fileobj=os.fdopen(fd, "wb"), mode="wb", compresslevel=6)


def dump_to_gzip(conn: Conn, out: Path, schemas: List[str]) -> None:
    args = ["--format=custom", "--compress=0", "--no-password", "--lock-wait-timeout=120000"]
    args += [f"--schema={s}" for s in schemas]
    err_file = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(tool("pg_dump") + args, env=conn.env(), stdout=subprocess.PIPE, stderr=err_file)
    except FileNotFoundError:
        raise BackupError("pg_dump", "pg_dump is not installed (install the PostgreSQL client tools)")
    try:
        try:
            gz = _open_gzip(out)
        except OSError as e:
            proc.kill()
            raise BackupError("compress", f"could not create the compressed file: {e.strerror or e}")
        try:
            with gz:
                while True:
                    chunk = proc.stdout.read(CHUNK)
                    if not chunk:
                        break
                    gz.write(chunk)
        except OSError as e:
            proc.kill()
            raise BackupError("compress", f"writing the compressed backup failed: {e.strerror or e}")
        code = proc.wait()
        if code != 0:
            err_file.seek(0)
            lines = err_file.read().decode("utf-8", "replace").strip().splitlines()[-5:]
            raise BackupError("pg_dump", f"pg_dump exited {code}: {' | '.join(lines) or 'no message'}")
    finally:
        if proc.poll() is None:
            proc.kill()
        if proc.stdout:
            proc.stdout.close()
        err_file.close()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def read_archive_list(gz_path: Path, env: Dict[str, str]) -> Dict[str, object]:
    """
    Decompresses the whole file (gzip CRC checks every byte), checks the custom-format header and
    has pg_restore read the archive's table of contents. Raises BackupError('verify', ...).
    """
    out_file = tempfile.TemporaryFile()
    err_file = tempfile.TemporaryFile()
    proc = None
    try:
        with gzip.open(gz_path, "rb") as src:
            head = src.read(5)
            if head != b"PGDMP":
                raise BackupError("verify", "not a pg_dump custom-format archive (bad header)")
            try:
                proc = subprocess.Popen(tool("pg_restore") + ["--list"], env=env, stdin=subprocess.PIPE,
                                        stdout=out_file, stderr=err_file)
            except FileNotFoundError:
                raise BackupError("verify", "pg_restore is not installed (install the PostgreSQL client tools)")
            try:
                proc.stdin.write(head)
                for chunk in iter(lambda: src.read(CHUNK), b""):
                    proc.stdin.write(chunk)
            except BrokenPipeError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            code = proc.wait()
    except (OSError, EOFError, zlib.error) as e:   # gzip.BadGzipFile is an OSError
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        out_file.close()
        err_file.close()
        raise BackupError("verify", f"the compressed file is damaged: {e}")
    except BackupError:
        out_file.close()
        err_file.close()
        raise
    out_file.seek(0)
    listing = out_file.read().decode("utf-8", "replace")
    err_file.seek(0)
    err = err_file.read().decode("utf-8", "replace").strip().splitlines()[-5:]
    out_file.close()
    err_file.close()
    if code != 0:
        raise BackupError("verify", f"pg_restore could not read the archive (exit {code}): {' | '.join(err)}")
    tables = []
    data_entries = 0
    for line in listing.splitlines():
        if line.startswith(";") or not line.strip():
            continue
        m = re.search(r"\bTABLE DATA (\S+) (\S+)", line)
        if m:
            data_entries += 1
            continue
        m = re.search(r"\bTABLE (\S+) (\S+)", line)
        if m:
            tables.append(f"{m.group(1)}.{m.group(2)}")
    return {"tables": sorted(set(tables)), "table_data_entries": data_entries}


def gpg_encrypt(src: Path, dst: Path, recipient: str) -> None:
    run("gpg", ["--batch", "--yes", "--no-tty", "--trust-model", "always", "--recipient", recipient,
                "--output", str(dst), "--encrypt", str(src)], dict(os.environ), "encrypt", timeout=3600)
    os.chmod(dst, 0o600)


def gpg_decrypt(src: Path, dst: Path) -> None:
    run("gpg", ["--batch", "--yes", "--no-tty", "--output", str(dst), "--decrypt", str(src)],
        dict(os.environ), "decrypt", timeout=3600)


def _fsync_dir(d: Path) -> None:
    if os.name == "posix":
        fd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_private(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_manifest(artifact: Path) -> Optional[dict]:
    side = artifact.with_name(artifact.name + ".json")
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        return data if data.get("format") == FORMAT and data.get("status") == "verified" else None
    except (OSError, ValueError):
        return None


def complete_backups(d: Path) -> List[Tuple[Path, dict]]:
    out = []
    for p in d.iterdir():
        if NAME_RE.match(p.name) and p.is_file():
            m = load_manifest(p)
            if m and (p.with_name(p.name + ".sha256")).exists():
                out.append((p, m))
    out.sort(key=lambda pm: pm[1].get("created_at", ""), reverse=True)
    return out


# ── Commands ──────────────────────────────────────────────────────────────────

def apply_retention(d: Path, now: Optional[_dt.datetime] = None) -> List[str]:
    """Deletes verified backups older than BACKUP_RETENTION_DAYS (default 30), always keeping the
    BACKUP_MIN_KEEP (default 7) newest. Only ever called after a successful backup."""
    days = _int_env("BACKUP_RETENTION_DAYS", 30, minimum=1)
    keep = _int_env("BACKUP_MIN_KEEP", 7, minimum=1)
    now = now or _utcnow()
    cutoff = now - _dt.timedelta(days=days)
    removed = []
    for i, (p, m) in enumerate(complete_backups(d)):
        if i < keep:
            continue
        try:
            created = _dt.datetime.fromisoformat(m["created_at"])
        except (KeyError, ValueError):
            continue
        if created < cutoff:
            for f in (p, p.with_name(p.name + ".sha256"), p.with_name(p.name + ".json")):
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
            removed.append(p.name)
    return removed


def _hook(env_name: str, *args: str) -> Optional[int]:
    """Runs an operator-provided command (off-site copy, alert). Arguments are appended, never a shell."""
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return None
    import shlex
    try:
        p = subprocess.run(shlex.split(raw) + list(args), capture_output=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"{env_name.lower()}_error", error=str(e))
        return 1
    if p.returncode != 0:
        log(f"{env_name.lower()}_error", exit=p.returncode,
            stderr=p.stderr.decode("utf-8", "replace").strip()[-400:])
    return p.returncode


def alert(message: str) -> None:
    _hook("BACKUP_ALERT_COMMAND", "FAILED", redact(message))


def cmd_backup() -> int:
    conn = None
    partial: List[Path] = []
    try:
        d = backup_dir(create=True)
        conn = Conn(source_url())
        schemas = [s.strip() for s in os.environ.get("BACKUP_SCHEMAS", "public").split(",") if s.strip()]
        recipient = os.environ.get("BACKUP_GPG_RECIPIENT", "").strip()
        if os.environ.get("BACKUP_REQUIRE_ENCRYPTION", "").strip() == "1" and not recipient:
            raise BackupError("config", "BACKUP_REQUIRE_ENCRYPTION=1 but BACKUP_GPG_RECIPIENT is not set")
        with Lock(d):
            started = _utcnow()
            stamp = started.strftime("%Y%m%dT%H%M%SZ")
            safe_db = re.sub(r"[^A-Za-z0-9_-]", "_", conn.dbname)[:60]
            gz_name = f"oraliq_{safe_db}_{stamp}.dump.gz"
            final = d / (gz_name + (".gpg" if recipient else ""))
            gz_partial = d / (gz_name + ".partial")
            partial.append(gz_partial)
            log("backup_started", database=conn.dbname, schemas=schemas, encrypted=bool(recipient), dir=str(d))

            versions = check_connection(conn)
            dump_to_gzip(conn, gz_partial, schemas)
            contents = read_archive_list(gz_partial, conn.env())
            min_tables = _int_env("BACKUP_MIN_TABLES", 1)
            if len(contents["tables"]) < min_tables:
                raise BackupError("verify", f"the archive lists {len(contents['tables'])} tables, expected at least {min_tables}")

            if recipient:
                enc_partial = d / (final.name + ".partial")
                partial.append(enc_partial)
                gpg_encrypt(gz_partial, enc_partial, recipient)
                gz_partial.unlink()
                ready = enc_partial
            else:
                ready = gz_partial
            digest = sha256_of(ready)
            os.replace(ready, final)
            partial.clear()
            partial.append(final)   # until its sidecars exist it is not a usable backup
            manifest = {
                "format": FORMAT, "status": "verified", "file": final.name,
                "created_at": started.isoformat(), "verified_at": _utcnow().isoformat(),
                "database": conn.dbname, "schemas": schemas, "encrypted": bool(recipient),
                "size_bytes": final.stat().st_size, "sha256": digest,
                "server_major": versions["server_major"], "pg_dump_major": versions["pg_dump_major"],
                "tables": contents["tables"], "table_data_entries": contents["table_data_entries"],
            }
            _write_private(final.with_name(final.name + ".sha256"), f"{digest}  {final.name}\n")
            _write_private(final.with_name(final.name + ".json"), json.dumps(manifest, indent=2))
            _fsync_dir(d)
            partial.clear()
            log("backup_verified", file=final.name, size_bytes=manifest["size_bytes"], sha256=digest,
                tables=len(contents["tables"]), seconds=round((_utcnow() - started).total_seconds(), 1))

            offsite = _hook("BACKUP_UPLOAD_COMMAND", str(final), str(final) + ".sha256", str(final) + ".json")
            if offsite in (None, 0):
                removed = apply_retention(d)
                if removed:
                    log("retention_pruned", removed=removed)
            else:
                log("retention_skipped", reason="off-site copy failed; keeping every local backup")
            if offsite is None:
                log("offsite_not_configured", warning="backup exists only on this server; set BACKUP_UPLOAD_COMMAND")
                if os.environ.get("BACKUP_REQUIRE_OFFSITE", "").strip() == "1":
                    alert("backup verified but BACKUP_REQUIRE_OFFSITE=1 and no off-site copy is configured")
                    return EXIT_OFFSITE_FAILED
            elif offsite != 0:
                alert(f"backup {final.name} verified locally but the off-site copy failed")
                return EXIT_OFFSITE_FAILED
            else:
                log("offsite_copied", file=final.name)
            return EXIT_OK
    except (BackupError, OSError) as e:
        if not isinstance(e, BackupError):
            e = BackupError("io", f"{type(e).__name__}: {e}")
        for p in partial:
            for f in (p, p.with_name(p.name + ".sha256"), p.with_name(p.name + ".json")):
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
        log("backup_failed", stage=e.stage, error=e.message)
        alert(f"OralIQ backup failed at {e.stage}: {e.message}")
        return EXIT_FAILED
    finally:
        if conn:
            conn.close()


def _resolve(file_arg: str) -> Path:
    p = Path(file_arg)
    if not p.is_absolute() and not p.exists():
        p = backup_dir(create=False) / file_arg
    if not p.is_file():
        raise BackupError("input", f"backup file not found: {file_arg}")
    return p


def check_backup(path: Path, workdir: Path) -> Tuple[Path, dict, dict]:
    """Checksum, then (decrypt and) full readback. Returns (plain .gz path, manifest, listing)."""
    side = path.with_name(path.name + ".sha256")
    if not side.exists():
        raise BackupError("checksum", "no .sha256 file next to the backup")
    expected = side.read_text(encoding="utf-8").split()[0].strip().lower()
    actual = sha256_of(path)
    if actual != expected:
        raise BackupError("checksum", "SHA-256 does not match: the file was changed or damaged")
    manifest = json.loads(path.with_name(path.name + ".json").read_text(encoding="utf-8")) \
        if path.with_name(path.name + ".json").exists() else {}
    plain = path
    if path.name.endswith(".gpg"):
        plain = workdir / path.name[:-4]
        gpg_decrypt(path, plain)
    listing = read_archive_list(plain, dict(os.environ))
    return plain, manifest, listing


def cmd_verify(file_arg: str) -> int:
    work = Path(tempfile.mkdtemp(prefix="oraliq-verify-"))
    try:
        path = _resolve(file_arg)
        _, manifest, listing = check_backup(path, work)
        log("verify_ok", file=path.name, created_at=manifest.get("created_at"), size_bytes=path.stat().st_size,
            tables=len(listing["tables"]))
        return EXIT_OK
    except BackupError as e:
        log("verify_failed", stage=e.stage, error=e.message)
        return EXIT_FAILED
    finally:
        shutil.rmtree(work, ignore_errors=True)


def cmd_list() -> int:
    try:
        d = backup_dir(create=False)
    except BackupError as e:
        log("list_failed", error=e.message)
        return EXIT_FAILED
    for p, m in complete_backups(d):
        print(f"{m.get('created_at', '?'):32}  {p.stat().st_size / 1048576:9.1f} MB  "
              f"{'encrypted' if m.get('encrypted') else 'plain    '}  {len(m.get('tables', []))} tables  {p.name}")
    for p in sorted(d.glob("*.partial")):
        print(f"{'(incomplete)':32}  {p.stat().st_size / 1048576:9.1f} MB  {p.name}")
    return EXIT_OK


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def cmd_restore(file_arg: str, target_env: str, replace: bool, confirm: Optional[str],
                production_ok: bool, check_only: bool) -> int:
    target = None
    work = Path(tempfile.mkdtemp(prefix="oraliq-restore-"))
    os.chmod(work, 0o700)
    try:
        path = _resolve(file_arg)
        plain, manifest, listing = check_backup(path, work)
        log("restore_backup_ok", file=path.name, created_at=manifest.get("created_at"),
            size_bytes=path.stat().st_size, tables=len(listing["tables"]))
        if check_only:
            return EXIT_OK

        target_url = os.environ.get(target_env, "").strip()
        if not target_url:
            raise BackupError("refused", f"no restore target: set the environment variable {target_env}")
        target = Conn(target_url)
        src = source_url()
        if src:
            source = Conn(src)
            if source.identity == target.identity and not (production_ok and replace and confirm == target.dbname):
                raise BackupError("refused", "the target is the database backups are taken from; restoring over it "
                                             "needs --replace-existing --confirm <dbname> --i-am-restoring-production")
        schemas = manifest.get("schemas") or ["public"]
        in_list = ",".join("'" + s.replace("'", "''") + "'" for s in schemas)
        existing = int(psql(target, f"select count(*) from information_schema.tables where table_schema in ({in_list})",
                            "connect") or 0)
        if existing and not (replace and confirm == target.dbname):
            raise BackupError("refused", f"target database {target.dbname} already has {existing} tables; nothing was "
                                         f"changed. To overwrite it, pass --replace-existing --confirm {target.dbname}")

        args = ["--no-owner", "--no-privileges", "--exit-on-error", "--single-transaction", "--no-password",
                f"--dbname={target.dbname}"]
        if existing:
            args += ["--clean", "--if-exists"]
        log("restore_started", file=path.name, target_database=target.dbname, replacing_existing=bool(existing))
        err_file = tempfile.TemporaryFile()
        try:
            proc = subprocess.Popen(tool("pg_restore") + args, env=target.env(), stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=err_file)
        except FileNotFoundError:
            raise BackupError("restore", "pg_restore is not installed")
        try:
            with gzip.open(plain, "rb") as src_f:
                for chunk in iter(lambda: src_f.read(CHUNK), b""):
                    proc.stdin.write(chunk)
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
        code = proc.wait()
        err_file.seek(0)
        err = err_file.read().decode("utf-8", "replace").strip().splitlines()[-5:]
        err_file.close()
        if code != 0:
            raise BackupError("restore", f"pg_restore exited {code} (single transaction: nothing was applied): {' | '.join(err)}")

        report = {}
        missing = []
        for qualified in listing["tables"]:
            schema, _, table = qualified.partition(".")
            try:
                report[qualified] = int(psql(target, f"select count(*) from {_qi(schema)}.{_qi(table)}", "report") or 0)
            except BackupError:
                missing.append(qualified)
        log("restore_completed", file=path.name, target_database=target.dbname, tables_restored=len(report),
            tables_missing=missing, row_counts=report)
        return EXIT_OK if not missing else EXIT_FAILED
    except BackupError as e:
        log("restore_failed" if e.stage != "refused" else "restore_refused", stage=e.stage, error=e.message)
        return EXIT_REFUSED if e.stage == "refused" else EXIT_FAILED
    finally:
        if target:
            target.close()
        shutil.rmtree(work, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    os.umask(0o077)
    ap = argparse.ArgumentParser(description="OralIQ PostgreSQL backup / restore")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup", help="take, verify and keep a backup; prune old ones")
    sub.add_parser("list", help="list backups")
    v = sub.add_parser("verify", help="check a backup file")
    v.add_argument("file")
    r = sub.add_parser("restore", help="restore a backup into a database you name")
    r.add_argument("file")
    r.add_argument("--target-env", default="RESTORE_DATABASE_URL",
                   help="name of the environment variable holding the target URL (never the URL itself)")
    r.add_argument("--replace-existing", action="store_true", help="allow overwriting a database that has tables")
    r.add_argument("--confirm", help="the target database name, typed out, required with --replace-existing")
    r.add_argument("--i-am-restoring-production", dest="production_ok", action="store_true")
    r.add_argument("--check-only", action="store_true", help="verify the backup and stop before touching any database")
    a = ap.parse_args(argv)
    if a.cmd == "backup":
        return cmd_backup()
    if a.cmd == "list":
        return cmd_list()
    if a.cmd == "verify":
        return cmd_verify(a.file)
    return cmd_restore(a.file, a.target_env, a.replace_existing, a.confirm, a.production_ok, a.check_only)


if __name__ == "__main__":
    sys.exit(main())
