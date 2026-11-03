import os
import secrets
from pathlib import Path
from typing import List
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env / local.env without overriding explicit environment variables
_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env", override=False)
load_dotenv(_BACKEND_DIR / "local.env", override=False)

MIN_SECRET_LENGTH = 32
MIN_SECRET_DISTINCT_CHARS = 10
_PLACEHOLDER_SECRETS = ("changeme", "change-me", "change_me", "your-secret", "your_secret", "placeholder", "example")

# The run mode must be named: there is no default. "dev" and "test" are for a developer's machine and
# the test suite; anything deployed runs "production". A missing or misspelt value stops the process
# instead of quietly running with development defaults (open /docs, CORS "*", a throwaway SQLite
# database, a signing key generated on disk) on a real server.
VALID_ENVS = ("dev", "test", "production")


class ConfigError(RuntimeError):
    """The process must not start with this configuration. Messages never contain secret values."""


def current_env() -> str:
    raw = (os.environ.get("ENV") or "").strip()
    if not raw:
        raise ConfigError(
            "ENV is not set. Name the run mode explicitly: ENV=production on a server, "
            "ENV=dev on a developer machine (backend/local.env.example sets it), ENV=test for the tests."
        )
    if raw not in VALID_ENVS:
        raise ConfigError(f"ENV={raw[:32]!r} is not a known run mode. Use one of: {', '.join(VALID_ENVS)}.")
    if raw != "production" and os.environ.get("SPACE_ID"):
        # Hugging Face sets SPACE_ID on every Space: this is a deployed server whatever ENV says.
        raise ConfigError(f"ENV={raw} on a hosted Space. A deployed server must run with ENV=production.")
    return raw


def is_production() -> bool:
    return current_env() == "production"


def is_dev_env() -> bool:
    """True only on a developer machine. Debug-only surfaces (/docs, /openapi.json, /debug,
    tracebacks in 500 responses, /system/db-migrate) use this. Any doubt about the mode — unset,
    unknown, a hosted Space — counts as "not development", so those surfaces stay closed."""
    try:
        return current_env() == "dev"
    except ConfigError:
        return False


# ── SECRET_KEY ────────────────────────────────────────────────────────────────

def secret_key_problem(key: str) -> str:
    """Why this signing key is unacceptable ("" if it is fine). Never echoes the key."""
    if len(key) < MIN_SECRET_LENGTH:
        return (
            f"SECRET_KEY is only {len(key)} characters; it must be at least {MIN_SECRET_LENGTH}. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )
    if len(set(key)) < MIN_SECRET_DISTINCT_CHARS or any(p in key.lower() for p in _PLACEHOLDER_SECRETS):
        return (
            "SECRET_KEY looks like a placeholder or a repeated pattern, not a random key. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )
    return ""


def _get_or_create_secret() -> str:
    """
    Returns the key that signs every access token.

    Production: it must come from the environment and pass secret_key_problem(), or the process
    refuses to start. Nothing is ever generated or written there — a container has no persistent
    disk, so a generated key changes on every restart and logs every user out (mid-exam included).
    Development: the old convenience stays — a key generated once into backend/data/.secret_key.
    Tests: a random key held in memory only, so the test suite writes nothing into the project.
    """
    env = current_env()
    env_key = (os.environ.get("SECRET_KEY") or "").strip()

    if env == "production":
        if not env_key:
            raise ConfigError(
                "SECRET_KEY is not set. Set it in the environment before starting the server:\n"
                '  SECRET_KEY="$(python -c \'import secrets; print(secrets.token_urlsafe(64))\')"\n'
                "Keep the same value across restarts and across every instance, or all sessions "
                "will be dropped whenever the server restarts."
            )
        problem = secret_key_problem(env_key)
        if problem:
            raise ConfigError(problem)
        return env_key

    if env_key:
        if len(env_key) < MIN_SECRET_LENGTH:
            raise ConfigError(secret_key_problem(env_key))
        return env_key

    if env == "test":
        return secrets.token_urlsafe(64)

    # Development only, from here down.
    key_file = _BACKEND_DIR / "data" / ".secret_key"
    if key_file.exists():
        stored = key_file.read_text().strip()
        if len(stored) >= MIN_SECRET_LENGTH:
            return stored

    new_key = secrets.token_urlsafe(64)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(new_key)
    print(f"[Config] Development SECRET_KEY generated -> {key_file}")
    return new_key


# ── DATABASE_URL ──────────────────────────────────────────────────────────────

def database_url_problem(url: str) -> str:
    """Why DATABASE_URL is unusable in production ("" if fine). Never echoes the URL (it holds a password)."""
    if not url:
        return ("DATABASE_URL is not set. Production needs a PostgreSQL database; there is no "
                "fallback to a local SQLite file, which would lose every record on restart.")
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError
    normalized = "postgresql://" + url[len("postgres://"):] if url.startswith("postgres://") else url
    try:
        parsed = make_url(normalized)
    except (ArgumentError, ValueError):
        return "DATABASE_URL is not a valid database URL (expected postgresql://USER:PASSWORD@HOST:PORT/DBNAME)."
    if parsed.get_backend_name() != "postgresql":
        return (f"DATABASE_URL points at a {parsed.get_backend_name()!r} database. Production must use "
                "PostgreSQL; SQLite is for development and tests only.")
    if not parsed.host:
        return "DATABASE_URL has no host."
    return ""


# ── ALLOWED_ORIGINS ───────────────────────────────────────────────────────────

def parse_allowed_origins(raw: str, env: str) -> List[str]:
    """
    The browser origins allowed to call the API. CORS compares them exactly, so each one is
    normalized (lower-case scheme and host, no trailing slash) the way browsers send Origin.
    Production: required, https only, no wildcard, nothing added implicitly (no localhost).
    Development and tests: unset means "*".
    """
    raw = (raw or "").strip()
    if env != "production":
        if not raw:
            return ["*"]
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]

    if not raw:
        raise ConfigError(
            "ALLOWED_ORIGINS is not set. List the sites that may call this API, comma separated:\n"
            '  ALLOWED_ORIGINS="https://oraliq.com,https://www.oraliq.com"'
        )
    entries = [o.strip() for o in raw.split(",") if o.strip()]
    if not entries:
        raise ConfigError("ALLOWED_ORIGINS is empty. Name at least one https:// origin.")
    origins: List[str] = []
    for entry in entries:
        if "*" in entry:
            raise ConfigError(
                'ALLOWED_ORIGINS contains "*", which allows every site on the internet. '
                "Name the real origins instead."
            )
        parts = urlsplit(entry.rstrip("/"))
        if (
            parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password
            or parts.path or parts.query or parts.fragment
        ):
            raise ConfigError(
                f"ALLOWED_ORIGINS entry {entry[:100]!r} is not an origin. Each entry must be "
                "https://host or https://host:port, with no path."
            )
        origin = f"https://{parts.hostname.lower()}" + (f":{parts.port}" if parts.port else "")
        if origin not in origins:
            origins.append(origin)
    return origins


# ── Startup check ─────────────────────────────────────────────────────────────

def production_config_problems() -> List[str]:
    """Everything wrong with a production configuration, by setting name. Values are never included."""
    problems = []
    key = (os.environ.get("SECRET_KEY") or "").strip()
    if not key:
        problems.append("SECRET_KEY is not set.")
    elif secret_key_problem(key):
        problems.append(secret_key_problem(key))
    db_problem = database_url_problem((os.environ.get("DATABASE_URL") or "").strip())
    if db_problem:
        problems.append(db_problem)
    try:
        parse_allowed_origins(os.environ.get("ALLOWED_ORIGINS", ""), "production")
    except ConfigError as e:
        problems.append(str(e))
    problems.extend(billing_test_mode_problems())
    return problems


# ── Test-payment switches ─────────────────────────────────────────────────────

_FALSE_VALUES = ("", "0", "false", "no", "off")


def billing_test_mode_problems() -> List[str]:
    """
    Production must take real payments only. BILLING_SANDBOX activates plans with no payment at
    all; KASHIER_MODE=test points Kashier at its test hosts and keys, whose test-card payments
    would come back as genuine signed successes. Either one (or a KASHIER_MODE that isn't
    plainly "live") stops a production start. Values are never echoed.
    """
    problems = []
    if (os.environ.get("BILLING_SANDBOX") or "").strip().lower() not in _FALSE_VALUES:
        problems.append(
            "BILLING_SANDBOX is enabled (or not a recognised off value). In production it would "
            "activate subscriptions without any payment. Unset it or set BILLING_SANDBOX=0."
        )
    if (os.environ.get("KASHIER_MODE") or "").strip().lower() not in ("", "live"):
        problems.append(
            "KASHIER_MODE is not 'live'. Production must use Kashier's live hosts and live keys. "
            "Set KASHIER_MODE=live (or leave it unset)."
        )
    return problems


def validate_environment() -> str:
    """
    Runs when this module is imported, i.e. before the API or the grading worker build anything.
    Production refuses to start, listing every missing or invalid setting at once.
    """
    env = current_env()
    if env == "production":
        problems = production_config_problems()
        if problems:
            raise ConfigError(
                "Refusing to start in production; fix these settings:\n  - " + "\n  - ".join(problems)
            )
    return env


validate_environment()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "local.env"), extra="ignore")

    PROJECT_NAME: str = "OralIQ"
    API_V1_STR: str = "/api/v1"

    # Security — persistent key (survives restarts)
    SECRET_KEY: str = _get_or_create_secret()
    ALGORITHM: str = "HS256"

    # Token expiry — long enough for exam sessions
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Password hashing rounds (bcrypt)
    BCRYPT_ROUNDS: int = 12

    # Environment
    ENV: str = current_env()


settings = Settings()
