"""
Sign in with Google — isolated app + temporary SQLite DB, no network.
Google's tokeninfo call is mocked; the audience/issuer/expiry/e-mail checks run for real.
Run:  pytest app/tests/test_google_login.py -q --noconftest
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.api.endpoints import auth as auth_ep
from app.core import security
from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401  (register all models)
from app.models.user import User

CLIENT_ID = "test-client.apps.googleusercontent.com"


def _claims(**over):
    c = {
        "aud": CLIENT_ID,
        "iss": "https://accounts.google.com",
        "sub": "109876543210987654321",
        "exp": str(int(time.time()) + 600),
        "email": "New.User@Gmail.com",
        "email_verified": "true",
        "name": "New User",
    }
    c.update(over)
    return c


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'google.db').as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_ep.router, prefix="/api/v1")
    app.dependency_overrides[deps.get_db] = _get_db

    monkeypatch.setenv("GOOGLE_CLIENT_ID", f"other-client.apps.googleusercontent.com, {CLIENT_ID}")
    state = {"claims": _claims()}
    monkeypatch.setattr(auth_ep, "_fetch_google_tokeninfo", lambda credential: state["claims"])

    yield TestClient(app), Session, state


def _uid(token: str) -> int:
    return int(jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])["sub"])


def test_config_endpoint(env, monkeypatch):
    client, _, _ = env
    r = client.get("/api/v1/auth/google/config")
    assert r.status_code == 200
    assert r.json() == {"enabled": True, "client_id": "other-client.apps.googleusercontent.com"}
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    assert client.get("/api/v1/auth/google/config").json() == {"enabled": False, "client_id": None}


def test_unset_client_id_returns_503(env, monkeypatch):
    client, _, _ = env
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20})
    assert r.status_code == 503
    assert "GOOGLE_CLIENT_ID" in r.json()["detail"]


def test_wrong_audience_returns_401(env):
    client, _, state = env
    state["claims"] = _claims(aud="someone-elses-app")
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20, "role": "student"})
    assert r.status_code == 401


@pytest.mark.parametrize("over", [
    {"iss": "evil.example.com"},
    {"exp": str(int(time.time()) - 5)},
    {"email_verified": "false"},
])
def test_bad_claims_return_401(env, over):
    client, _, state = env
    state["claims"] = _claims(**over)
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20, "role": "student"})
    assert r.status_code == 401


def test_google_rejects_token_returns_401(env):
    client, _, state = env
    state["claims"] = None
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20, "role": "student"})
    assert r.status_code == 401


def test_new_user_without_role_returns_409(env):
    client, Session, _ = env
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "ROLE_REQUIRED"
    assert detail["email"] == "new.user@gmail.com"
    assert detail["suggested_name"] == "New User"
    with Session() as db:
        assert db.query(User).count() == 0


def test_new_user_with_custom_full_name_and_role(env):
    client, Session, _ = env
    r = client.post(
        "/api/v1/login/google",
        json={"credential": "x" * 20, "role": "lecturer", "full_name": "  د. أحمد الصاوي  "},
    )
    assert r.status_code == 200, r.text
    with Session() as db:
        user = db.query(User).filter(User.email == "new.user@gmail.com").one()
        assert user.role == "lecturer"
        assert user.full_name == "د. أحمد الصاوي"


def test_new_user_with_role_is_created(env):
    client, Session, _ = env
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20, "role": "lecturer"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    with Session() as db:
        user = db.query(User).filter(User.email == "new.user@gmail.com").one()
        assert user.role == "lecturer"
        assert user.full_name == "New User"
        assert _uid(body["access_token"]) == user.id
        # Random password: nobody can log in with a password for this account.
        assert not security.verify_password("", user.hashed_password)


def test_existing_user_gets_token(env):
    client, Session, _ = env
    with Session() as db:
        u = User(email="new.user@gmail.com", hashed_password=security.get_password_hash("Secret123!"),
                 full_name="Existing", role="student")
        db.add(u)
        db.commit()
        uid = u.id
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20})
    assert r.status_code == 200, r.text
    assert _uid(r.json()["access_token"]) == uid
    with Session() as db:
        assert db.query(User).count() == 1
        assert db.get(User, uid).role == "student"  # role untouched


def test_inactive_user_rejected(env):
    client, Session, _ = env
    with Session() as db:
        db.add(User(email="new.user@gmail.com", hashed_password="x", role="student", is_active=False))
        db.commit()
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20})
    assert r.status_code == 400
    assert r.json()["detail"] == "Inactive user"


def test_admin_role_rejected(env):
    client, Session, _ = env
    r = client.post("/api/v1/login/google", json={"credential": "x" * 20, "role": "admin"})
    assert r.status_code == 400
    with Session() as db:
        assert db.query(User).count() == 0


def test_retired_fake_oauth_passwords_blocked(env):
    """Legacy accounts created with the old hardcoded fake OAuth string cannot be hijacked via password login."""
    client, Session, _ = env
    for bad_pw in ("OAuth_google_OralIQ_2026!", "OAuth_github_OralIQ_2026!"):
        reg = client.post("/api/v1/register", json={"email": "victim@t.com", "password": bad_pw, "role": "student"})
        assert reg.status_code == 422

    with Session() as db:
        db.add(User(
            email="legacy@gmail.com",
            hashed_password=security.get_password_hash("OAuth_google_OralIQ_2026!"),
            full_name="Legacy Victim",
            role="lecturer",
        ))
        db.commit()

    hijack = client.post(
        "/api/v1/login/access-token",
        data={"username": "legacy@gmail.com", "password": "OAuth_google_OralIQ_2026!"},
    )
    assert hijack.status_code == 400
