"""
Billing / subscription tests — isolated app + temporary SQLite DB (never touches the real DB,
never loads AI models). Run:  pytest app/tests/test_billing.py -q
"""
import hashlib
import hmac
import json
import os
import time
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.api.api_router import api_router
from app.api.endpoints import exams as exams_ep
from app.core import security
from app.core.database import Base
import app.models  # noqa: F401  (register all models)
from app.models.exam_submission import ExamSubmission
from app.models.payment import Payment
from app.models.question import Question
from app.models.user import User
from app.services.billing_service import utcnow
from app.services.payment_gateways import kashier_signature_string


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'billing.db').as_posix()}", connect_args={"check_same_thread": False})
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

    # No AI runs during these tests: submit only queues the answer (graded by app/worker.py).
    for var in ("KASHIER_MERCHANT_ID", "KASHIER_SECRET_KEY", "KASHIER_MODE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    monkeypatch.setenv("KASHIER_API_KEY", KASHIER_TEST_KEY)   # the webhook signature key

    yield TestClient(app), Session


def make_user(Session, email, role="lecturer", **fields):
    if role == "student":   # students sit exams only with face and voice enrolled (H2)
        from app.tests.exam_helpers import ENROLLED
        fields = {**ENROLLED, **fields}
    db = Session()
    u = User(email=email, hashed_password="x", full_name=email.split("@")[0], role=role, **fields)
    db.add(u)
    db.commit()
    db.refresh(u)
    token = security.create_access_token(u.id, expires_delta=timedelta(hours=1))
    uid = u.id
    db.close()
    return uid, {"Authorization": f"Bearer {token}"}


def new_exam(client, headers, duration=2, group=None):
    body = {"text": "What is X?", "model_answer": "A", "duration_minutes": duration}
    if group:
        body["group_token"] = group
    return client.post("/api/v1/questions/", json=body, headers=headers)


def get_user(Session, uid):
    db = Session()
    u = db.query(User).filter(User.id == uid).first()
    db.expunge(u)
    db.close()
    return u


def update_user(Session, uid, **fields):
    db = Session()
    u = db.query(User).filter(User.id == uid).first()
    for k, v in fields.items():
        setattr(u, k, v)
    db.commit()
    db.close()


# ── Free plan ─────────────────────────────────────────────────────────────────

def test_free_plan_exam_quota_is_lifetime_5(env):
    client, Session = env
    _, h = make_user(Session, "free@t.com")
    for _ in range(5):
        assert new_exam(client, h).status_code == 200
    r = new_exam(client, h)
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "EXAM_QUOTA_EXCEEDED"


def test_free_plan_question_and_duration_limits(env):
    client, Session = env
    _, h = make_user(Session, "free2@t.com")
    g = new_exam(client, h).json()["group_token"]
    assert new_exam(client, h, group=g).status_code == 200
    assert new_exam(client, h, group=g).status_code == 200
    r = new_exam(client, h, group=g)  # 4th question
    assert r.status_code == 402 and r.json()["detail"]["code"] == "QUESTIONS_PER_EXAM_EXCEEDED"
    r = new_exam(client, h, duration=3)  # free max 2 minutes
    assert r.status_code == 402 and r.json()["detail"]["code"] == "DURATION_EXCEEDED"
    # extra questions in a group do not consume exams
    assert client.get("/api/v1/billing/status", headers=h).json()["usage"]["exams_used"] == 1


def test_cannot_add_question_to_someone_elses_exam(env):
    client, Session = env
    _, h1 = make_user(Session, "a@t.com")
    _, h2 = make_user(Session, "b@t.com")
    g = new_exam(client, h1).json()["group_token"]
    assert new_exam(client, h2, group=g).status_code == 403


def test_register_cannot_self_assign_admin(env):
    client, _ = env
    r = client.post("/api/v1/register", json={"email": "evil@t.com", "password": "p", "role": "admin"})
    assert r.status_code in (400, 422)


# ── Checkout / activation ─────────────────────────────────────────────────────

def test_upgrade_without_gateway_and_sandbox_does_not_activate(env, monkeypatch):
    client, Session = env
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    uid, h = make_user(Session, "nopay@t.com")
    r = client.post("/api/v1/billing/upgrade", json={"plan_id": "campus"}, headers=h)
    assert r.status_code == 503
    assert get_user(Session, uid).plan_tier == "free"


def test_sandbox_checkout_activates_basic_plan(env):
    client, Session = env
    uid, h = make_user(Session, "basic@t.com")
    r = client.post("/api/v1/billing/checkout", json={"plan_id": "pro", "period": "monthly"}, headers=h)
    assert r.status_code == 200, r.text
    u = get_user(Session, uid)
    assert u.plan_tier == "pro"
    assert 29 <= (u.plan_expires_at - utcnow()).days <= 30
    st = client.get("/api/v1/billing/status", headers=h).json()
    assert st["usage"]["exams_limit"] == 15
    assert st["usage"]["max_questions_per_exam"] == 5
    assert st["usage"]["students_limit"] == 150


def test_term_price_and_renewal_extends_expiry(env):
    client, Session = env
    uid, h = make_user(Session, "term@t.com")
    r = client.post("/api/v1/billing/checkout", json={"plan_id": "pro", "period": "term"}, headers=h)
    assert r.json()["amount"] == 597
    first_exp = get_user(Session, uid).plan_expires_at
    client.post("/api/v1/billing/checkout", json={"plan_id": "pro", "period": "monthly"}, headers=h)
    assert (get_user(Session, uid).plan_expires_at - first_exp).days == 30


def test_enterprise_not_self_purchasable(env):
    client, Session = env
    _, h = make_user(Session, "ent@t.com")
    assert client.post("/api/v1/billing/checkout", json={"plan_id": "enterprise"}, headers=h).status_code == 400


def test_monthly_cycle_resets_and_no_rollover(env):
    client, Session = env
    uid, h = make_user(Session, "cycle@t.com")
    client.post("/api/v1/billing/checkout", json={"plan_id": "pro", "period": "yearly"}, headers=h)
    for _ in range(3):
        new_exam(client, h)
    assert client.get("/api/v1/billing/status", headers=h).json()["usage"]["exams_used"] == 3
    u = get_user(Session, uid)
    update_user(Session, uid, cycle_started_at=u.cycle_started_at - timedelta(days=31))
    usage = client.get("/api/v1/billing/status", headers=h).json()["usage"]
    assert usage["exams_used"] == 0 and usage["exams_remaining"] == 15


def test_expired_plan_falls_back_to_free_after_grace(env):
    client, Session = env
    uid, h = make_user(Session, "exp@t.com")
    client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=h)
    update_user(Session, uid, plan_expires_at=utcnow() - timedelta(days=2))
    assert client.get("/api/v1/billing/status", headers=h).json()["plan_tier"] == "pro"  # grace
    update_user(Session, uid, plan_expires_at=utcnow() - timedelta(days=4))
    assert client.get("/api/v1/billing/status", headers=h).json()["plan_tier"] == "free"


def test_addon_pack_used_after_monthly_quota(env):
    client, Session = env
    uid, h = make_user(Session, "addon@t.com")
    assert client.post("/api/v1/billing/checkout", json={"kind": "addon"}, headers=h).status_code == 400  # free
    client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=h)
    r = client.post("/api/v1/billing/checkout", json={"kind": "addon"}, headers=h)
    assert r.status_code == 200 and r.json()["amount"] == 79
    for _ in range(15):
        assert new_exam(client, h).status_code == 200
    assert new_exam(client, h).status_code == 200  # from bonus
    assert get_user(Session, uid).bonus_exams == 9


# ── Webhooks ──────────────────────────────────────────────────────────────────

KASHIER_TEST_KEY = "kashier-test-api-key"
KASHIER_SIGNATURE_KEYS = ["amount", "channel", "currency", "kashierOrderId", "merchantOrderId", "method",
                          "orderReference", "status", "transactionId", "transactionResponseCode"]


def _kashier_data(reference, amount="199.00", status="SUCCESS", **over):
    """A Kashier webhook `data` object shaped like the documented pay example."""
    data = {
        "merchantOrderId": reference, "kashierOrderId": "ko-111", "orderReference": "TEST-ORD-1",
        "transactionId": "TX-1", "status": status, "method": "card", "creationDate": "2026-11-03T10:00:00.000Z",
        "amount": amount, "currency": "EGP", "transactionResponseCode": "00", "channel": "online | e-commerce",
        "signatureKeys": list(KASHIER_SIGNATURE_KEYS),
    }
    data.update(over)
    return data


def _kashier_sign(data, key=KASHIER_TEST_KEY):
    return hmac.new(key.encode(), kashier_signature_string(data).encode(), hashlib.sha256).hexdigest()


def _kashier_send(client, data, event="pay", signature=None):
    sig = signature if signature is not None else _kashier_sign(data)
    return client.post("/api/v1/billing/webhook/kashier", json={"event": event, "data": data},
                       headers={"x-kashier-signature": sig})


def _pending_payment(Session, uid, amount=199, plan="pro"):
    db = Session()
    p = Payment(user_id=uid, kind="plan", plan_id=plan, period="monthly", amount=amount, currency="EGP", provider="kashier",
                provider_txn_id="kashier_session:s-111")  # what kashier_create_checkout records
    db.add(p)
    db.commit()
    ref = p.reference
    db.close()
    return ref


def test_kashier_webhook_requires_valid_signature(env):
    client, Session = env
    uid, _ = make_user(Session, "pm@t.com")
    ref = _pending_payment(Session, uid)
    data = _kashier_data(ref)
    assert client.post("/api/v1/billing/webhook/kashier", json={"event": "pay", "data": data}).status_code == 401
    assert _kashier_send(client, data, signature="deadbeef").status_code == 401
    assert _kashier_send(client, data, signature=_kashier_sign(data, key="another-key")).status_code == 401
    assert get_user(Session, uid).plan_tier == "free"
    r = _kashier_send(client, data)
    assert r.status_code == 200 and r.json()["status"] == "paid"
    assert get_user(Session, uid).plan_tier == "pro"
    # idempotent replay (Kashier retries and may repeat a delivery)
    assert _kashier_send(client, data).json().get("already_applied") is True
    assert _kashier_send(client, data, event="idempotency").json().get("already_applied") is True


def test_kashier_signed_callback_cannot_be_repointed(env):
    """merchantOrderId is one of the signed keys: pointing a signed callback at another payment breaks it."""
    client, Session = env
    uid, _ = make_user(Session, "pm3@t.com")
    uid2, _ = make_user(Session, "pm3b@t.com")
    ref = _pending_payment(Session, uid)
    other_ref = _pending_payment(Session, uid2)
    data = _kashier_data(ref)
    sig = _kashier_sign(data)
    assert _kashier_send(client, {**data, "merchantOrderId": other_ref}, signature=sig).status_code == 401
    # Dropping the key from signatureKeys to escape the signature is refused too.
    loose = {**data, "merchantOrderId": other_ref,
             "signatureKeys": [k for k in KASHIER_SIGNATURE_KEYS if k != "merchantOrderId"]}
    assert _kashier_send(client, loose).status_code == 401
    assert get_user(Session, uid2).plan_tier == "free"


def test_kashier_amount_mismatch_rejected(env):
    client, Session = env
    uid, _ = make_user(Session, "pm2@t.com")
    ref = _pending_payment(Session, uid, amount=599, plan="campus")
    r = _kashier_send(client, _kashier_data(ref, amount="1.00"))   # paid 1 EGP instead of 599
    assert r.json()["status"] == "amount_mismatch"
    assert get_user(Session, uid).plan_tier == "free"


def test_stripe_and_paymob_webhooks_are_gone_and_their_records_are_kept(env):
    """Kashier is the only gateway: no Stripe / Paymob callback can pay anything; old rows stay."""
    client, Session = env
    uid, _ = make_user(Session, "st@t.com")
    db = Session()
    p = Payment(user_id=uid, kind="plan", plan_id="campus", period="monthly", amount=12, currency="USD",
                provider="stripe", status="paid")
    db.add(p)
    db.commit()
    pid = p.id
    db.close()
    for path in ("/api/v1/billing/webhook/stripe", "/api/v1/billing/webhook/paymob"):
        assert client.post(path, json={"type": "checkout.session.completed"}).status_code in (404, 405)
    db = Session()
    assert db.get(Payment, pid).status == "paid"          # history untouched
    db.close()


# ── Students limit ────────────────────────────────────────────────────────────

def test_concurrent_limit_counts_students_in_exam_at_same_time(env):
    """Free plan = 50 students AT THE SAME TIME. Finished students free their seat."""
    client, Session = env
    owner_id, h = make_user(Session, "lim@t.com")
    qid = new_exam(client, h).json()["id"]
    token = client.get("/api/v1/questions/", headers=h).json()[0]["group_token"]

    # 50 students currently inside the exam
    from app.models.exam_session import ExamSession
    db = Session()
    for i in range(50):
        db.add(ExamSession(account_id=owner_id, student_key=f"n:S{i}", group_token=token,
                           started_at=utcnow(), expires_at=utcnow() + timedelta(minutes=10)))
    db.commit()
    db.close()

    sid, sh = make_user(Session, "stud51@t.com", role="student")
    r = client.get(f"/api/v1/exams/access-check/{token}", headers=sh)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "CONCURRENT_LIMIT_REACHED"

    # One student finishes -> a seat frees up -> the new student can enter
    db = Session()
    db.query(ExamSession).filter(ExamSession.student_key == "n:S0").update({ExamSession.finished: True})
    db.commit()
    db.close()
    assert client.get(f"/api/v1/exams/access-check/{token}", headers=sh).status_code == 200

    # Submitting the (only/last) question releases the seat again
    form = {"question_id": qid, "student_name": "x", "student_number": "S999"}
    assert client.post("/api/v1/exams/submit", data=form, headers=sh).status_code == 202
    db = Session()
    open_seats = db.query(ExamSession).filter(ExamSession.finished.is_(False), ExamSession.expires_at > utcnow()).count()
    db.close()
    assert open_seats == 49

    # Many students finishing over time never "uses up" the plan
    for i in range(60):
        _, hh = make_user(Session, f"later{i}@t.com", role="student")
        db = Session()
        db.query(ExamSession).filter(ExamSession.finished.is_(False)).update({ExamSession.finished: True})
        db.commit()
        db.close()
        assert client.get(f"/api/v1/exams/access-check/{token}", headers=hh).status_code == 200


# ── Team / assistants ─────────────────────────────────────────────────────────

def test_team_assistants_share_owner_quota(env):
    client, Session = env
    owner_id, oh = make_user(Session, "owner@t.com")
    asst_id, ah = make_user(Session, "asst@t.com")
    # Basic plan has no assistant seats
    client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=oh)
    assert client.post("/api/v1/billing/team", json={"email": "asst@t.com"}, headers=oh).status_code == 402
    client.post("/api/v1/billing/checkout", json={"plan_id": "campus"}, headers=oh)
    assert client.post("/api/v1/billing/team", json={"email": "asst@t.com"}, headers=oh).status_code == 200
    assert new_exam(client, ah, duration=10).status_code == 200  # campus limits apply to assistant
    assert get_user(Session, owner_id).cycle_exams_used == 1
    st = client.get("/api/v1/billing/status", headers=ah).json()
    assert st["is_team_member"] is True and st["plan_tier"] == "campus"
    # assistant can't buy
    assert client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=ah).status_code == 400


def test_admin_grant_enterprise_custom_limits(env):
    client, Session = env
    _, adm = make_user(Session, "admin@t.com", role="admin")
    uid, h = make_user(Session, "school@t.com")
    r = client.post("/api/v1/billing/admin/grant", headers=adm, json={
        "email": "school@t.com", "plan_id": "enterprise", "months": 4,
        "custom_max_students": 300, "custom_max_exams": 120, "amount": 9000,
    })
    assert r.status_code == 200, r.text
    usage = client.get("/api/v1/billing/status", headers=h).json()["usage"]
    assert usage["students_limit"] == 300 and usage["exams_limit"] == 120
    # non-admin forbidden
    assert client.post("/api/v1/billing/admin/grant", headers=h, json={"email": "school@t.com"}).status_code == 403
