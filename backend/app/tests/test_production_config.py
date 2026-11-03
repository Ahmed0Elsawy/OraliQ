"""The settings a production deployment must not be allowed to get wrong silently."""
import pytest
from starlette.requests import Request

from app.core.config import _get_or_create_secret
from app.main import _allowed_origins, _rate_limit_key


def _request(headers: dict, client_host: str = "203.0.113.9") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/exams/submit",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 51234),
    })


# ── SECRET_KEY ────────────────────────────────────────────────────────────────

def test_secret_key_is_required_in_production(monkeypatch):
    """A container has no persistent disk: generating a key would log everyone out on restart."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY is not set"):
        _get_or_create_secret()


def test_secret_key_rejects_a_short_value(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="at least"):
        _get_or_create_secret()


def test_secret_key_from_the_environment_is_used_as_is(monkeypatch):
    import secrets
    key = secrets.token_urlsafe(48)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", key)
    assert _get_or_create_secret() == key


def test_development_still_falls_back_to_a_generated_key(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config._BACKEND_DIR", tmp_path)  # never write into the project
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert len(_get_or_create_secret()) >= 32


# ── ALLOWED_ORIGINS ───────────────────────────────────────────────────────────

def test_allowed_origins_is_required_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS is not set"):
        _allowed_origins()


def test_allowed_origins_refuses_a_wildcard_in_production(monkeypatch):
    """Any page on the internet could otherwise drive the API with a token it got hold of."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://oraliq.com,*")
    with pytest.raises(RuntimeError, match="allows every site"):
        _allowed_origins()


def test_allowed_origins_parses_a_real_list(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://oraliq.com/ , https://www.oraliq.com ")
    assert _allowed_origins() == ["https://oraliq.com", "https://www.oraliq.com"]


def test_development_defaults_to_any_origin(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert _allowed_origins() == ["*"]


# ── Rate limit bucketing ──────────────────────────────────────────────────────

def test_two_students_on_one_school_ip_get_separate_buckets():
    """The case that matters: a class behind one NAT must not share one allowance."""
    from app.core import security
    a = _rate_limit_key(_request({"authorization": f"Bearer {security.create_access_token(101)}"}))
    b = _rate_limit_key(_request({"authorization": f"Bearer {security.create_access_token(102)}"}))
    assert a != b
    assert a.startswith("u:")


def test_forged_tokens_do_not_get_their_own_bucket():
    """Random bearer strings must not mint unlimited fresh buckets (and evict real users')."""
    a = _rate_limit_key(_request({"authorization": "Bearer token-of-student-a"}, client_host="198.51.100.7"))
    b = _rate_limit_key(_request({"authorization": "Bearer token-of-student-b"}, client_host="198.51.100.7"))
    assert a == b == "ip:198.51.100.7"


def test_the_bucket_name_never_contains_the_token():
    token = "a-real-looking-access-token"
    assert token not in _rate_limit_key(_request({"authorization": f"Bearer {token}"}))


def test_anonymous_callers_fall_back_to_their_ip():
    assert _rate_limit_key(_request({}, client_host="198.51.100.4")) == "ip:198.51.100.4"


def test_a_forwarded_header_is_ignored_unless_a_proxy_is_trusted(monkeypatch):
    """Honoured blindly, any caller could claim a fresh IP per request and never be limited."""
    monkeypatch.setattr("app.main.TRUST_PROXY", False)
    key = _rate_limit_key(_request({"x-forwarded-for": "1.2.3.4"}, client_host="127.0.0.1"))
    assert key == "ip:127.0.0.1"


def test_a_trusted_proxy_reveals_the_real_client(monkeypatch):
    """Behind nginx every request arrives from 127.0.0.1, which would be one global bucket."""
    monkeypatch.setattr("app.main.TRUST_PROXY", True)
    monkeypatch.setattr("app.main.TRUSTED_PROXY_HOPS", 1)
    key = _rate_limit_key(_request({"x-forwarded-for": "1.2.3.4"}, client_host="127.0.0.1"))
    assert key == "ip:1.2.3.4"
    # two proxies we control: the client is the second entry from the right
    monkeypatch.setattr("app.main.TRUSTED_PROXY_HOPS", 2)
    key = _rate_limit_key(_request({"x-forwarded-for": "1.2.3.4, 10.0.0.1"}, client_host="127.0.0.1"))
    assert key == "ip:1.2.3.4"


def test_a_spoofed_forwarded_entry_is_not_believed(monkeypatch):
    """The client controls everything left of what our proxy appended."""
    monkeypatch.setattr("app.main.TRUST_PROXY", True)
    monkeypatch.setattr("app.main.TRUSTED_PROXY_HOPS", 1)
    key = _rate_limit_key(_request({"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, client_host="127.0.0.1"))
    assert key == "ip:1.2.3.4"


def test_the_limiter_forgets_idle_callers():
    """Without pruning the limiter keeps one bucket per key forever: an unbounded leak."""
    import time
    from app.main import RateLimiter

    limiter = RateLimiter(limit=5, window=60)
    stale = time.time() - 3600
    for i in range(50):
        limiter._hits[f"ip:10.0.0.{i}"] = [stale]

    limiter.is_allowed("ip:10.0.1.1")
    assert list(limiter._hits) == ["ip:10.0.1.1"]


def test_the_limiter_still_blocks_a_flood():
    from app.main import RateLimiter
    limiter = RateLimiter(limit=3, window=60)
    assert [limiter.is_allowed("s:one") for _ in range(4)] == [True, True, True, False]
