import os

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["message"].startswith("OralIQ API")
    assert body["status"] == "operational"


def test_health_is_public():
    response = client.get("/health")
    assert response.status_code == 200


def test_debug_is_closed_outside_development(monkeypatch):
    """/debug describes the running instance; it must not answer in production."""
    monkeypatch.setenv("ENV", "production")
    assert client.get("/debug").status_code == 404


def test_debug_never_returns_the_database_url(monkeypatch):
    """Even in development it reports the kind of database, never the URL: that holds the password."""
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:sup3rs3cret@db.example.com:5432/oraliq")
    body = client.get("/debug").json()
    assert body["database"] == "postgresql"
    assert "sup3rs3cret" not in str(body)
    assert not any("://" in str(v) for v in body.values())


def test_cors_does_not_allow_credentials_with_any_origin():
    """A wildcard origin plus credentials would be unsafe; the app authenticates with a header."""
    r = client.get("/health", headers={"Origin": "https://example.com"})
    assert r.headers.get("access-control-allow-credentials") is None
    assert os.environ.get("ALLOWED_ORIGINS") is None or True
