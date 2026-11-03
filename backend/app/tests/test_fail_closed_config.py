"""
Production must refuse to start when a setting it depends on is missing or unsafe, instead of
falling back to development behaviour (open docs, CORS "*", SQLite in /tmp, a generated key).

Startup is tested in a separate Python process, exactly as a server would import the app; the
process is cut off from backend/.env and local.env so a developer's own settings can't leak in.
No database is contacted and no secret value is ever printed.
"""
import hashlib
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import config
from app.core.config import ConfigError

BACKEND = Path(__file__).resolve().parents[2]
CONFIG_KEYS = ("ENV", "SECRET_KEY", "DATABASE_URL", "ALLOWED_ORIGINS", "SPACE_ID", "DATABASE_URL_DIRECT")
GOOD_KEY = secrets.token_urlsafe(48)
DB_PASSWORD = "pw-" + secrets.token_hex(8)
GOOD_PRODUCTION = {
    "ENV": "production",
    "SECRET_KEY": GOOD_KEY,
    "DATABASE_URL": f"postgresql://oraliq:{DB_PASSWORD}@db.example.invalid:5432/oraliq",
    "ALLOWED_ORIGINS": "https://oraliq.example",
}


def start(tmp_path, env: dict, module: str = "app.core.config", extra: str = "") -> subprocess.CompletedProcess:
    """Import the app the way a server process would, with exactly these settings."""
    child_env = {k: v for k, v in os.environ.items() if k not in CONFIG_KEYS}
    child_env.update(env)
    child_env["PYTHONPATH"] = str(BACKEND)
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = (
        "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"  # ignore developer .env files
        f"import importlib; m = importlib.import_module({module!r})\n"
        f"{extra}\n"
        "print('STARTED')"
    )
    return subprocess.run(
        [sys.executable, "-c", code], env=child_env, cwd=str(tmp_path),
        capture_output=True, text=True, timeout=120,
    )


def assert_refused(result, *fragments):
    out = result.stdout + result.stderr
    assert result.returncode != 0 and "STARTED" not in result.stdout, out[-2000:]
    assert "ConfigError" in out, out[-2000:]
    for f in fragments:
        assert f in out, out[-2000:]
    # Never leak a secret into the log, even when refusing.
    assert GOOD_KEY not in out and DB_PASSWORD not in out


def without(*keys):
    return {k: v for k, v in GOOD_PRODUCTION.items() if k not in keys}


# ── 1. No ENV ─────────────────────────────────────────────────────────────────

def test_1_startup_without_env_is_refused(tmp_path):
    assert_refused(start(tmp_path, without("ENV")), "ENV is not set")


def test_1b_a_server_with_no_env_does_not_become_development(monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    assert config.is_dev_env() is False
    with pytest.raises(ConfigError, match="ENV is not set"):
        config.current_env()


# ── 2. Unknown ENV ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["prod", "Production", "staging", "development", "dev "])
def test_2_unknown_env_is_refused(monkeypatch, value):
    monkeypatch.setenv("ENV", value)
    if value.strip() in config.VALID_ENVS:   # surrounding whitespace is tolerated, the word is not
        assert config.current_env() == value.strip()
        return
    with pytest.raises(ConfigError, match="not a known run mode"):
        config.current_env()


def test_2b_startup_with_an_unknown_env_is_refused(tmp_path):
    assert_refused(start(tmp_path, {**GOOD_PRODUCTION, "ENV": "prod"}), "not a known run mode")


def test_2c_development_mode_on_a_hosted_space_is_refused(tmp_path):
    assert_refused(start(tmp_path, {"ENV": "dev", "SPACE_ID": "someone/oraliq-api"}), "hosted Space")


# ── 3. No DATABASE_URL ────────────────────────────────────────────────────────

def test_3_production_without_database_url_is_refused(tmp_path):
    assert_refused(start(tmp_path, without("DATABASE_URL")), "DATABASE_URL is not set")


@pytest.mark.parametrize("url,fragment", [
    ("not a url", "not a valid database URL"),
    ("mysql://u:p@h/db", "'mysql'"),
    ("postgresql:///oraliq", "no host"),
])
def test_3b_production_rejects_an_unusable_database_url(url, fragment):
    assert fragment in config.database_url_problem(url)


def test_3c_postgres_scheme_alias_is_accepted():
    assert config.database_url_problem("postgres://u:p@db.example.invalid:5432/oraliq") == ""


# ── 4. No SECRET_KEY ──────────────────────────────────────────────────────────

def test_4_production_without_secret_key_is_refused(tmp_path):
    assert_refused(start(tmp_path, without("SECRET_KEY")), "SECRET_KEY is not set")


@pytest.mark.parametrize("weak", ["short-key", "a" * 64, "changeme-" + "0123456789abcdef" * 3])
def test_4b_production_refuses_a_weak_secret_key(tmp_path, weak):
    result = start(tmp_path, {**GOOD_PRODUCTION, "SECRET_KEY": weak})
    assert_refused(result, "SECRET_KEY")
    assert weak not in result.stdout + result.stderr


# ── 5 + 6. CORS ───────────────────────────────────────────────────────────────

def test_5_production_without_allowed_origins_is_refused(tmp_path):
    assert_refused(start(tmp_path, without("ALLOWED_ORIGINS")), "ALLOWED_ORIGINS is not set")


def test_5b_an_empty_origin_list_is_refused():
    with pytest.raises(ConfigError, match="empty"):
        config.parse_allowed_origins(" , ,", "production")


def test_6_wildcard_origin_is_refused(tmp_path):
    assert_refused(start(tmp_path, {**GOOD_PRODUCTION, "ALLOWED_ORIGINS": "*"}), "allows every site")
    with pytest.raises(ConfigError, match="allows every site"):
        config.parse_allowed_origins("https://*.oraliq.example", "production")


@pytest.mark.parametrize("bad", [
    "http://oraliq.example",            # not https
    "https://oraliq.example/app",       # a path is not an origin
    "oraliq.example",                   # no scheme
    "https://user@oraliq.example",
])
def test_6b_only_exact_https_origins_are_accepted(bad):
    with pytest.raises(ConfigError, match="not an origin"):
        config.parse_allowed_origins(bad, "production")


def test_6c_origins_are_normalized_and_nothing_is_added():
    got = config.parse_allowed_origins(
        " https://OralIQ.example/ , https://www.oraliq.example:8443,https://oraliq.example", "production"
    )
    assert got == ["https://oraliq.example", "https://www.oraliq.example:8443"]
    assert not any("localhost" in o for o in got)


# ── 7. No SQLite fallback in production ───────────────────────────────────────

def test_7_production_never_falls_back_to_sqlite(monkeypatch):
    from app.core import database
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError, match="no fallback"):
        database._resolve_database_url()
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/interview_ai.db")
    with pytest.raises(ConfigError, match="SQLite is for development"):
        database._resolve_database_url()


def test_7b_tests_get_an_in_memory_database_and_dev_may_choose_sqlite(monkeypatch, tmp_path):
    from app.core import database
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database._resolve_database_url() == "sqlite://"
    explicit = f"sqlite:///{(tmp_path / 'dev.db').as_posix()}"
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", explicit)
    assert database._resolve_database_url() == explicit


def test_7c_an_unreachable_database_stops_production_startup(monkeypatch):
    """The startup hook turns a failed connection into a clear refusal, without the driver's message."""
    from app import main
    from app.core import database

    class Unreachable:
        def connect(self):
            raise OSError(f"could not connect to db.example.invalid with password {DB_PASSWORD}")

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setattr(database, "engine", Unreachable())
    with pytest.raises(ConfigError, match="Could not connect") as e:
        main._check_database_reachable()
    assert DB_PASSWORD not in str(e.value)


# ── 8. No docs / debug in production ──────────────────────────────────────────

def test_8_docs_openapi_and_redoc_are_off_in_production(monkeypatch):
    from app import main
    monkeypatch.setenv("ENV", "production")
    settings = main._api_docs_settings()
    assert settings == {"docs_url": None, "redoc_url": None, "openapi_url": None}

    probe = FastAPI(**settings)
    probe.get("/ping")(lambda: {"ok": True})
    c = TestClient(probe)
    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert c.get(path).status_code == 404, path


def test_8b_debug_and_migration_endpoints_are_closed_in_production(monkeypatch):
    from app.main import app
    c = TestClient(app)
    monkeypatch.setenv("ENV", "production")
    assert c.get("/debug").status_code == 404
    assert c.get("/api/v1/system/db-migrate").status_code == 403
    assert "config" not in c.get("/health").json() or c.get("/health").json()["config"] == {}


def test_8c_the_running_test_app_exposes_no_schema():
    """The app object built for this suite (ENV=test) has the docs switched off as well."""
    from app.main import app
    assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None


# ── 9. Development keeps working ──────────────────────────────────────────────

def test_9_development_starts_with_its_conveniences(tmp_path):
    dev_db = f"sqlite:///{(tmp_path / 'dev.db').as_posix()}"
    result = start(
        tmp_path,
        {"ENV": "dev", "SECRET_KEY": GOOD_KEY, "DATABASE_URL": dev_db, "GRADING_WORKER_MODE": "off"},
        module="app.main",
        extra=(
            "assert m.app.docs_url == '/docs' and m.app.openapi_url == '/openapi.json'\n"
            "assert m.ALLOWED_ORIGINS == ['*']"
        ),
    )
    assert result.returncode == 0 and "STARTED" in result.stdout, (result.stdout + result.stderr)[-2000:]


def test_9b_development_may_still_generate_its_own_key_once(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    first = config._get_or_create_secret()
    assert config._get_or_create_secret() == first          # stable across restarts on that machine
    assert (tmp_path / "data" / ".secret_key").exists()


# ── 10. Tests keep working ────────────────────────────────────────────────────

def test_10_the_suite_runs_in_test_mode_without_touching_the_project(monkeypatch, tmp_path):
    assert config.current_env() == "test"
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert len(config._get_or_create_secret()) >= 32
    assert not (tmp_path / "data").exists()                 # nothing written


# ── 11. A restart never mints a new key ───────────────────────────────────────

def test_11_production_uses_the_configured_key_on_every_start(tmp_path):
    marker = BACKEND / "data" / ".secret_key"
    existed_before = marker.exists()
    digest = "import hashlib; print('KEY', hashlib.sha256(m.settings.SECRET_KEY.encode()).hexdigest())"
    runs = [start(tmp_path, GOOD_PRODUCTION, extra=digest) for _ in range(2)]
    expected = hashlib.sha256(GOOD_KEY.encode()).hexdigest()
    for r in runs:
        assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
        assert f"KEY {expected}" in r.stdout
        assert GOOD_KEY not in r.stdout + r.stderr
    assert marker.exists() == existed_before                 # nothing generated or written
    assert not any(tmp_path.rglob(".secret_key"))


def test_11b_production_secret_lookup_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_BACKEND_DIR", tmp_path)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", GOOD_KEY)
    assert config._get_or_create_secret() == GOOD_KEY
    assert config._get_or_create_secret() == GOOD_KEY
    assert not any(tmp_path.iterdir())


def test_a_good_production_config_passes_validation(tmp_path):
    result = start(tmp_path, GOOD_PRODUCTION)
    assert result.returncode == 0 and "STARTED" in result.stdout, (result.stdout + result.stderr)[-2000:]


def test_every_problem_is_reported_at_once(tmp_path):
    result = start(tmp_path, {"ENV": "production"})
    assert_refused(result, "SECRET_KEY is not set", "DATABASE_URL is not set", "ALLOWED_ORIGINS is not set")
