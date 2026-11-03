"""
E-mail ownership: verified sign-up, no session before verification, no account enumeration, and
Google sign-in that can't be used to keep — or steal — someone else's account.

Isolated app + temporary SQLite; e-mail goes to the in-memory outbox and Google's tokeninfo is
mocked. Nothing real is contacted.
"""
import hashlib
import re
import time
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.api import deps
from app.api.api_router import api_router
from app.api.endpoints import auth as auth_ep
from app.core import security
from app.core.database import Base
from app.models.email_verification import EmailVerificationToken
from app.models.question import Question
from app.models.user import User
from app.services import mailer

CLIENT_ID = "test-client.apps.googleusercontent.com"
VICTIM = "victim@example.com"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'auth.db').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[deps.get_db] = _get_db
    for k in ("EMAIL_BACKEND", "SMTP_HOST", "LEGACY_UNVERIFIED_PASSWORD_LOGIN", "EMAIL_VERIFICATION_RESEND_SECONDS",
              "EMAIL_VERIFICATION_MAX_PER_HOUR", "EMAIL_VERIFICATION_TTL_HOURS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FRONTEND_URL", "https://app.oraliq.example")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    google = {"claims": None}
    monkeypatch.setattr(auth_ep, "_fetch_google_tokeninfo", lambda credential: google["claims"])
    mailer.outbox.clear()
    return TestClient(app), Session, google


def claims(email=VICTIM, sub="google-sub-victim", **over):
    c = {"aud": CLIENT_ID, "iss": "https://accounts.google.com", "sub": sub, "exp": str(int(time.time()) + 600),
         "email": email, "email_verified": "true", "name": "Real Owner"}
    c.update(over)
    return c


def register(client, email=VICTIM, password="attacker-pass-1", role="lecturer", name="Someone"):
    return client.post("/api/v1/register", json={"email": email, "password": password, "full_name": name, "role": role})


def login(client, email, password):
    return client.post("/api/v1/login/access-token", data={"username": email, "password": password})


def mails_to(email):
    return [m for m in mailer.outbox if m["To"] == email]


def link_token(email):
    return re.search(r"#token=([A-Za-z0-9_\-]+)", mails_to(email)[-1].get_content()).group(1)


def verify(client, token, password):
    return client.post("/api/v1/auth/verify-email", json={"token": token, "password": password})


def google_login(client, google, role=None, **c):
    google["claims"] = claims(**c)
    body = {"credential": "x" * 30}
    if role:
        body["role"] = role
    return client.post("/api/v1/login/google", json=body)


def me(client, token):
    return client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})


def user_by_email(Session, email):
    with Session() as db:
        u = db.query(User).filter(User.email == email).one()
        db.expunge(u)
        return u


def age_links(Session, seconds):
    with Session() as db:
        for t in db.query(EmailVerificationToken).all():
            t.created_at -= timedelta(seconds=seconds)
        db.commit()


def legacy_user(Session, email, password="legacy-pass-1", role="lecturer", verified=False):
    """An account created before verification existed (the migration marks it this way)."""
    with Session() as db:
        u = User(email=email, hashed_password=security.get_password_hash(password), full_name="Legacy",
                 role=role, email_verified=verified, requires_email_verification=False)
        db.add(u)
        db.commit()
        return u.id


# ── 1 + 3. Sign-up and the e-mail it sends ────────────────────────────────────

def test_1_sign_up_creates_an_unverified_account_and_sends_one_link(env):
    client, Session, _ = env
    r = register(client, "new@example.com", "my-pass-123", role="student")
    assert r.status_code == 202 and r.json()["verification_required"] is True
    assert "access_token" not in r.json()
    u = user_by_email(Session, "new@example.com")
    assert u.email_verified is False and u.requires_email_verification is True and u.role == "student"
    assert len(mails_to("new@example.com")) == 1


def test_3_the_link_is_random_hashed_at_rest_and_expires(env):
    client, Session, _ = env
    register(client, "new@example.com", "my-pass-123")
    body = mails_to("new@example.com")[0].get_content()
    assert "https://app.oraliq.example/verify-email#token=" in body
    raw = link_token("new@example.com")
    assert len(raw) >= 40
    with Session() as db:
        row = db.query(EmailVerificationToken).one()
        assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in (row.token_hash, row.pending_password_hash)
        assert timedelta(hours=23) < row.expires_at - datetime.utcnow() <= timedelta(hours=24)
        assert security.verify_password("my-pass-123", row.pending_password_hash)


# ── 2. No session before verification ─────────────────────────────────────────

def test_2_password_login_is_refused_until_the_email_is_verified(env):
    client, _, _ = env
    register(client, "new@example.com", "my-pass-123")
    r = login(client, "new@example.com", "my-pass-123")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"
    assert "access_token" not in r.text
    assert login(client, "new@example.com", "wrong-pass").status_code == 400   # wrong password says nothing more


# ── 4–7. Completing the link ──────────────────────────────────────────────────

def test_4_a_correct_link_and_password_verify_and_sign_in(env):
    client, Session, _ = env
    register(client, "new@example.com", "my-pass-123", role="lecturer", name="Dr. New")
    r = verify(client, link_token("new@example.com"), "my-pass-123")
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert me(client, r.json()["access_token"]).json()["email_verified"] is True
    u = user_by_email(Session, "new@example.com")
    assert u.email_verified and u.role == "lecturer" and u.full_name == "Dr. New"
    assert login(client, "new@example.com", "my-pass-123").status_code == 200


def test_5_an_expired_link_is_refused_and_a_new_one_can_be_requested(env, monkeypatch):
    client, Session, _ = env
    register(client, "new@example.com", "my-pass-123")
    old = link_token("new@example.com")
    with Session() as db:
        db.query(EmailVerificationToken).update({EmailVerificationToken.expires_at: datetime.utcnow() - timedelta(minutes=1)})
        db.commit()
    r = verify(client, old, "my-pass-123")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "LINK_EXPIRED"
    age_links(Session, 120)
    assert client.post("/api/v1/auth/resend-verification", json={"email": "new@example.com"}).status_code == 202
    fresh = link_token("new@example.com")
    assert fresh != old
    assert verify(client, fresh, "my-pass-123").status_code == 200


def test_6_a_link_works_only_once(env):
    client, _, _ = env
    register(client, "new@example.com", "my-pass-123")
    tok = link_token("new@example.com")
    assert verify(client, tok, "my-pass-123").status_code == 200
    r = verify(client, tok, "my-pass-123")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "LINK_INVALID"


def test_7_wrong_tokens_and_wrong_passwords_are_refused(env):
    client, Session, _ = env
    register(client, "new@example.com", "my-pass-123")
    assert verify(client, "A" * 43, "my-pass-123").json()["detail"]["code"] == "LINK_INVALID"
    tok = link_token("new@example.com")
    for _ in range(4):
        assert verify(client, tok, "guess-pass").json()["detail"]["code"] == "PASSWORD_MISMATCH"
    assert verify(client, tok, "guess-pass").json()["detail"]["code"] == "PASSWORD_MISMATCH"   # 5th: link spent
    assert verify(client, tok, "my-pass-123").json()["detail"]["code"] == "LINK_INVALID"
    assert user_by_email(Session, "new@example.com").email_verified is False


# ── 8. Nothing reveals whether an address is registered ──────────────────────

def test_8_answers_are_identical_for_new_pending_and_taken_addresses(env):
    client, Session, _ = env
    legacy_user(Session, "taken@example.com", verified=True)
    register(client, "pending@example.com", "p-pass-123")
    answers = [register(client, e, "any-pass-123") for e in ("fresh@example.com", "pending@example.com", "taken@example.com")]
    assert len({(a.status_code, a.text) for a in answers}) == 1
    resends = [client.post("/api/v1/auth/resend-verification", json={"email": e})
               for e in ("nobody@example.com", "pending@example.com", "taken@example.com")]
    assert len({(a.status_code, a.text) for a in resends}) == 1
    assert login(client, "nobody@example.com", "x-pass-123").json() == login(client, "taken@example.com", "x-pass-123").json()
    # The real owner of a taken address hears about the attempt; the password is never mailed anywhere.
    assert "already has one" in mails_to("taken@example.com")[-1].get_content()
    assert all("any-pass-123" not in m.get_content() for m in mailer.outbox)


# ── 9 + 10. Google token checks ───────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"email_verified": "false"}, {"aud": "another-app.apps.googleusercontent.com"},
    {"iss": "https://evil.example"}, {"exp": str(int(time.time()) - 1)}, {"sub": ""},
])
def test_9_10_google_tokens_must_be_verified_for_this_app(env, bad):
    client, Session, google = env
    register(client)
    r = google_login(client, google, role="student", **bad)
    assert r.status_code == 401
    u = user_by_email(Session, VICTIM)
    assert u.google_sub is None and u.email_verified is False


def test_10b_google_rejecting_the_token_signs_nobody_in(env):
    client, _, google = env
    google["claims"] = None   # tokeninfo refused it (bad signature, malformed, revoked)
    assert client.post("/api/v1/login/google", json={"credential": "x" * 30, "role": "student"}).status_code == 401


# ── 11. Pre-registration hijack ───────────────────────────────────────────────

def test_11_a_pre_registered_address_goes_to_its_google_owner_and_the_squatter_is_out(env):
    client, Session, google = env
    register(client, VICTIM, "attacker-pass-1", role="lecturer", name="Attacker")
    assert login(client, VICTIM, "attacker-pass-1").status_code == 403     # can't get in unverified

    r = google_login(client, google, role="student")
    assert r.status_code == 200 and r.json()["password_login_disabled"] is True
    u = user_by_email(Session, VICTIM)
    assert u.google_sub == "google-sub-victim" and u.email_verified and u.role == "student" and u.full_name == "Real Owner"
    assert login(client, VICTIM, "attacker-pass-1").status_code == 400     # attacker's password is gone
    attacker_link = link_token(VICTIM)
    assert verify(client, attacker_link, "attacker-pass-1").status_code == 400   # and so is their pending link


def test_11b_the_owner_signing_up_with_a_password_takes_the_address_back(env):
    client, Session, _ = env
    register(client, VICTIM, "attacker-pass-1", role="lecturer")
    attacker_link = link_token(VICTIM)
    age_links(Session, 120)
    register(client, VICTIM, "owner-pass-123", role="student", name="Owner")
    owner_link = link_token(VICTIM)
    # The owner, clicking the stranger's (unsolicited) link, can't finish it without the stranger's password.
    assert verify(client, attacker_link, "owner-pass-123").json()["detail"]["code"] == "PASSWORD_MISMATCH"
    assert verify(client, owner_link, "owner-pass-123").status_code == 200
    u = user_by_email(Session, VICTIM)
    assert u.role == "student" and u.full_name == "Owner"
    assert login(client, VICTIM, "owner-pass-123").status_code == 200
    assert login(client, VICTIM, "attacker-pass-1").status_code == 400
    assert verify(client, attacker_link, "attacker-pass-1").status_code == 400   # cancelled


# ── 12. Linking Google to an existing password account ───────────────────────

def test_12_google_links_to_a_verified_account_and_keeps_the_owners_password(env):
    client, Session, google = env
    register(client, VICTIM, "owner-pass-123", role="lecturer")
    verify(client, link_token(VICTIM), "owner-pass-123")
    uid = user_by_email(Session, VICTIM).id
    r = google_login(client, google)
    assert r.status_code == 200 and "password_login_disabled" not in r.json()
    assert me(client, r.json()["access_token"]).json()["id"] == uid
    assert login(client, VICTIM, "owner-pass-123").status_code == 200     # same person proved both
    # A different Google account with the same address can't take it.
    r = google_login(client, google, sub="another-google-account")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "GOOGLE_ACCOUNT_MISMATCH"


def test_12b_google_on_an_unverified_legacy_account_keeps_its_data_and_revokes_old_access(env):
    client, Session, google = env
    uid = legacy_user(Session, VICTIM, "maybe-squatter-pass", role="lecturer")
    with Session() as db:
        db.add(Question(text="سؤال قديم", model_answer="إجابة", creator_id=uid))
        db.commit()
    old_session = login(client, VICTIM, "maybe-squatter-pass").json()["access_token"]
    assert me(client, old_session).status_code == 200

    r = google_login(client, google, role="student")
    assert r.status_code == 200 and r.json()["password_login_disabled"] is True
    new_session = r.json()["access_token"]
    assert me(client, new_session).json()["id"] == uid                     # same account, not a new one
    u = user_by_email(Session, VICTIM)
    assert u.role == "lecturer"                                            # existing role never changed
    with Session() as db:
        assert db.query(Question).filter(Question.creator_id == uid).count() == 1   # data kept
    assert me(client, old_session).status_code == 401                      # earlier sessions void
    assert login(client, VICTIM, "maybe-squatter-pass").status_code == 400


def test_12c_a_linked_google_account_signs_in_even_after_its_email_changes(env):
    client, Session, google = env
    google_login(client, google, role="lecturer")
    uid = user_by_email(Session, VICTIM).id
    r = google_login(client, google, email="renamed@example.com")
    assert r.status_code == 200 and me(client, r.json()["access_token"]).json()["id"] == uid


# ── 13. Resend throttling ─────────────────────────────────────────────────────

def test_13_resending_is_rate_limited_per_account(env, monkeypatch):
    client, Session, _ = env
    monkeypatch.setenv("EMAIL_VERIFICATION_MAX_PER_HOUR", "3")
    register(client, "new@example.com", "my-pass-123")
    resend = lambda: client.post("/api/v1/auth/resend-verification", json={"email": "new@example.com"})
    assert resend().status_code == 202
    assert len(mails_to("new@example.com")) == 1                          # too soon: nothing sent
    for expected in (2, 3):
        age_links(Session, 61)
        resend()
        assert len(mails_to("new@example.com")) == expected
    age_links(Session, 61)
    resend()
    assert len(mails_to("new@example.com")) == 3                          # hourly cap reached


# ── 14. Existing accounts keep working ────────────────────────────────────────

def test_14_accounts_from_before_verification_keep_signing_in(env, monkeypatch):
    client, Session, _ = env
    legacy_user(Session, "old@example.com", "old-pass-123")
    r = login(client, "old@example.com", "old-pass-123")
    assert r.status_code == 200 and r.json()["email_verified"] is False   # can be nudged to verify
    pre_upgrade_token = security.create_access_token(user_by_email(Session, "old@example.com").id)
    assert me(client, pre_upgrade_token).status_code == 200               # tokens issued before still valid
    # They can verify from inside the app...
    assert client.post("/api/v1/auth/email-verification/request",
                       headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 202
    assert verify(client, link_token("old@example.com"), "old-pass-123").status_code == 200
    assert user_by_email(Session, "old@example.com").email_verified is True
    # ...and the operator can later require it.
    legacy_user(Session, "old2@example.com", "old-pass-123")
    monkeypatch.setenv("LEGACY_UNVERIFIED_PASSWORD_LOGIN", "block")
    assert login(client, "old2@example.com", "old-pass-123").status_code == 403


# ── 15. Roles never change through these flows ────────────────────────────────

@pytest.mark.parametrize("role", ["admin", "lecturer", "hr"])
def test_15_verification_and_google_never_change_an_existing_role(env, role):
    client, Session, google = env
    legacy_user(Session, VICTIM, "own-pass-123", role=role)
    register(client, VICTIM, "own-pass-123", role="student")             # someone asks for "student"
    assert verify(client, link_token(VICTIM), "own-pass-123").status_code == 200
    assert user_by_email(Session, VICTIM).role == role
    google_login(client, google, role="student")
    assert user_by_email(Session, VICTIM).role == role


def test_15b_admin_can_never_be_requested(env):
    client, Session, google = env
    assert register(client, "x@example.com", "x-pass-123", role="admin").status_code == 422
    assert google_login(client, google, role="admin").status_code == 400


# ── 16. Verified accounts: nothing changes ────────────────────────────────────

def test_16_verified_accounts_sign_in_as_before(env):
    client, Session, _ = env
    legacy_user(Session, "ok@example.com", "ok-pass-123", verified=True)
    r = login(client, "ok@example.com", "ok-pass-123")
    assert r.status_code == 200 and r.json()["email_verified"] is True
    assert me(client, r.json()["access_token"]).status_code == 200
    assert login(client, "ok@example.com", "bad-pass-123").status_code == 400


# ── Configuration ─────────────────────────────────────────────────────────────

def test_without_email_delivery_password_sign_up_is_unavailable_but_google_works(env, monkeypatch):
    client, Session, google = env
    monkeypatch.setenv("ENV", "production")          # production never uses console/memory delivery
    for e in ("fresh@example.com", VICTIM):
        r = register(client, e, "a-pass-1234")
        assert r.status_code == 503 and r.json()["detail"]["code"] == "EMAIL_SIGNUP_UNAVAILABLE"
    monkeypatch.setenv("EMAIL_BACKEND", "console")
    assert mailer.configured() is False
    monkeypatch.setenv("ENV", "test")
    assert google_login(client, google, role="student").status_code == 200


def test_a_failed_delivery_still_answers_the_same_and_can_be_retried(env, monkeypatch):
    client, Session, _ = env

    def broken(*a, **k):
        raise mailer.MailError("SMTP delivery failed (ConnectionRefusedError)")
    with monkeypatch.context() as m:
        m.setattr(mailer, "send", broken)
        r = register(client, "new@example.com", "my-pass-123")
    assert r.status_code == 202
    age_links(Session, 120)
    client.post("/api/v1/auth/resend-verification", json={"email": "new@example.com"})
    assert verify(client, link_token("new@example.com"), "my-pass-123").status_code == 200
