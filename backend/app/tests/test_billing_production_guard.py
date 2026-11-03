"""
No subscription without real money in production.

Covers every path that can activate a plan: startup with test-payment switches on, the
checkout's simulated-payment branch, the shared activation function, and Kashier callbacks
(refunds, voids, foreign keys, missing amount). No gateway is contacted; callbacks are
built and signed locally with a test secret.
"""
import hashlib
import hmac
import json
import time
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.api import deps
from app.api.api_router import api_router
from app.core import config, security
from app.core.database import Base
from app.models.payment import Payment
from app.models.user import User
from app.services import billing_service as bs
from app.services import payment_gateways as gw
from app.tests.test_billing import _kashier_data, _kashier_sign
from app.tests.test_fail_closed_config import GOOD_PRODUCTION, assert_refused, start

HMAC_SECRET = "kapi-" + "9f3c1d7e5a2b4c6d8e0f1a3b5c7d9e1f"     # Kashier Payment API Key (signs webhooks)
STRIPE_SECRET = "whsec_" + "a1b2c3d4e5f60718293a4b5c6d7e8f90"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'guard.db').as_posix()}", connect_args={"check_same_thread": False})
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
    for var in ("KASHIER_MERCHANT_ID", "KASHIER_SECRET_KEY", "KASHIER_MODE", "STRIPE_SECRET_KEY", "BILLING_SANDBOX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KASHIER_API_KEY", HMAC_SECRET)
    yield TestClient(app), Session


def lecturer(Session, email="lect@guard.test"):
    db = Session()
    u = User(email=email, hashed_password="x", full_name="L", role="lecturer")
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid, {"Authorization": f"Bearer {security.create_access_token(uid, expires_delta=timedelta(hours=1))}"}


def user(Session, uid):
    db = Session()
    u = db.get(User, uid)
    db.expunge(u)
    db.close()
    return u


def pending(Session, uid, provider="kashier", amount=199, currency="EGP", order=111):
    db = Session()
    p = Payment(user_id=uid, kind="plan", plan_id="pro", period="monthly", amount=amount, currency=currency,
                provider=provider, provider_txn_id=f"kashier_session:{order}")
    db.add(p)
    db.commit()
    ref, pid = p.reference, p.id
    db.close()
    return ref, pid


def payment(Session, pid):
    db = Session()
    p = db.get(Payment, pid)
    db.expunge(p)
    db.close()
    return p


def kashier_callback(client, data, event="pay", secret=HMAC_SECRET):
    return client.post("/api/v1/billing/webhook/kashier", json={"event": event, "data": data},
                       headers={"x-kashier-signature": _kashier_sign(data, key=secret)})


# ── 1 + 2 + 6. Startup ────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["1", "true", "YES", "on", "maybe"])
def test_1_production_with_billing_sandbox_on_refuses_to_start(tmp_path, value):
    assert_refused(start(tmp_path, {**GOOD_PRODUCTION, "BILLING_SANDBOX": value}), "BILLING_SANDBOX")


@pytest.mark.parametrize("value", ["0", "false", "off", ""])
def test_2_production_with_billing_sandbox_off_starts(tmp_path, value):
    r = start(tmp_path, {**GOOD_PRODUCTION, "BILLING_SANDBOX": value})
    assert r.returncode == 0 and "STARTED" in r.stdout, (r.stdout + r.stderr)[-1500:]


@pytest.mark.parametrize("value", ["test", "TEST", "sandbox", "1"])
def test_6_production_with_kashier_test_mode_refuses_to_start(tmp_path, value):
    assert_refused(start(tmp_path, {**GOOD_PRODUCTION, "KASHIER_MODE": value}), "KASHIER_MODE")


def test_6a_production_with_kashier_live_starts(tmp_path):
    r = start(tmp_path, {**GOOD_PRODUCTION, "KASHIER_MODE": "live"})
    assert r.returncode == 0 and "STARTED" in r.stdout, (r.stdout + r.stderr)[-1500:]


# ── 3. Unset means off ────────────────────────────────────────────────────────

@pytest.mark.parametrize("run_mode", ["dev", "test", "production"])
def test_3_unset_billing_sandbox_never_enables_simulated_payments(monkeypatch, run_mode):
    monkeypatch.setenv("ENV", run_mode)
    monkeypatch.delenv("BILLING_SANDBOX", raising=False)
    assert gw.sandbox_enabled() is False


def test_3b_unknown_run_mode_counts_as_production(monkeypatch):
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    for bad in ("staging", ""):
        monkeypatch.setenv("ENV", bad)
        assert gw.test_payments_forbidden() is True
        assert gw.sandbox_enabled() is False


# ── 4. Simulated activation refused in production ─────────────────────────────

def test_4_checkout_cannot_simulate_a_payment_in_production(env, monkeypatch):
    client, Session = env
    uid, h = lecturer(Session)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("BILLING_SANDBOX", "1")          # switched on after startup, by mistake
    monkeypatch.setenv("KASHIER_MODE", "test")
    r = client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=h)
    assert r.status_code == 503
    assert user(Session, uid).plan_tier == "free"
    db = Session()
    assert db.query(Payment).filter(Payment.status == "paid").count() == 0
    db.close()


def test_4b_activation_function_refuses_a_non_gateway_payment_in_production(env, monkeypatch):
    """Defence in depth: even if a caller (or a future bug) reaches apply_paid_payment."""
    _, Session = env
    uid, _ = lecturer(Session)
    _, pid = pending(Session, uid, provider="sandbox")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    db = Session()
    assert bs.apply_paid_payment(db, db.get(Payment, pid), provider_txn_id="sandbox-x") is False
    db.close()
    assert user(Session, uid).plan_tier == "free"
    assert payment(Session, pid).status == "failed"


@pytest.mark.parametrize("provider", ["sandbox", "manual", None, "kashier-test"])
def test_4c_only_gateway_providers_activate_outside_sandbox(env, monkeypatch, provider):
    _, Session = env
    uid, _ = lecturer(Session, f"p-{provider}@guard.test")
    _, pid = pending(Session, uid, provider=provider)
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.delenv("BILLING_SANDBOX", raising=False)
    db = Session()
    assert bs.apply_paid_payment(db, db.get(Payment, pid)) is False
    db.close()
    assert user(Session, uid).plan_tier == "free"


# ── 5. No plan without a confirmed payment ────────────────────────────────────

def test_5_client_supplied_fields_cannot_activate_anything(env, monkeypatch):
    client, Session = env
    uid, h = lecturer(Session)
    monkeypatch.setenv("ENV", "production")
    body = {"plan_id": "pro", "sandbox": True, "provider": "sandbox", "status": "paid", "BILLING_SANDBOX": "1"}
    r = client.post("/api/v1/billing/upgrade", json=body, headers=h)
    assert r.status_code == 503
    assert user(Session, uid).plan_tier == "free"


@pytest.mark.parametrize("event,over,label", [
    ("pay", {"status": "FAILURE"}, "declined"),
    ("pay", {"status": "PENDING"}, "pending"),
    ("authorize", {}, "authorize only"),
    ("reject", {}, "rejected"),
    ("refund", {}, "refund"),
    ("partial_refund", {"amount": "50.00"}, "partial refund"),
    ("void", {}, "void"),
    ("pay", {"amount": ""}, "no amount"),
    ("pay", {"currency": ""}, "no currency"),
    ("pay", {"currency": "USD"}, "wrong currency"),
    ("pay", {"amount": "1.00"}, "partial amount"),
    ("pay", {"amount": 19900}, "amount in another unit"),
])
def test_5b_signed_callbacks_that_are_not_a_full_purchase_do_not_activate(env, monkeypatch, event, over, label):
    client, Session = env
    monkeypatch.setenv("ENV", "production")
    uid, _ = lecturer(Session, f"cb-{abs(hash(label))}@guard.test")
    ref, pid = pending(Session, uid)
    r = kashier_callback(client, _kashier_data(ref, **over), event=event)
    assert r.status_code == 200, label
    assert user(Session, uid).plan_tier == "free", label
    assert payment(Session, pid).status != "paid", label


def test_5c_callbacks_signed_with_another_key_are_refused(env, monkeypatch):
    """E.g. a test-mode delivery (signed with the test key) reaching the live server."""
    client, Session = env
    monkeypatch.setenv("ENV", "production")
    uid, _ = lecturer(Session)
    ref, pid = pending(Session, uid)
    assert kashier_callback(client, _kashier_data(ref), secret="kashier-test-mode-key").status_code == 401
    assert user(Session, uid).plan_tier == "free"
    assert kashier_callback(client, _kashier_data(ref)).json()["status"] == "paid"
    assert user(Session, uid).plan_tier == "pro"


def test_5d_a_refund_callback_never_pays_a_pending_payment(env):
    client, Session = env
    uid, _ = lecturer(Session)
    ref, pid = pending(Session, uid)
    kashier_callback(client, _kashier_data(ref, transactionId="TX-988"), event="refund")
    assert payment(Session, pid).status != "paid"
    assert user(Session, uid).plan_tier == "free"


def test_5e_stripe_keys_can_no_longer_start_or_confirm_a_payment(env, monkeypatch):
    client, Session = env
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", STRIPE_SECRET)
    uid, h = lecturer(Session)
    r = client.post("/api/v1/billing/checkout", json={"plan_id": "pro", "currency": "USD"}, headers=h)
    assert r.status_code == 503                         # Kashier not configured: no other gateway
    ref, pid = pending(Session, uid, provider="stripe", amount=4, currency="USD")
    raw = json.dumps({"type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": ref, "payment_status": "paid", "amount_total": 400, "currency": "usd"}}}).encode()
    ts = int(time.time())
    sig = hmac.new(STRIPE_SECRET.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    r = client.post("/api/v1/billing/webhook/stripe", content=raw, headers={"Stripe-Signature": f"t={ts},v1={sig}"})
    assert r.status_code in (404, 405)
    assert user(Session, uid).plan_tier == "free"


# ── 6. KASHIER_MODE=test is inert in production ───────────────────────────────

def test_6b_kashier_test_mode_cannot_make_anything_free_in_production(env, monkeypatch):
    client, Session = env
    uid, h = lecturer(Session)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("KASHIER_MODE", "test")
    assert gw.sandbox_enabled() is False and gw.sandbox_mode() is False
    assert gw.kashier_mode() == "live"                  # production never talks to the test hosts
    assert client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=h).status_code == 503
    assert user(Session, uid).plan_tier == "free"


# ── 7 + 8. Development and tests keep their sandbox ───────────────────────────

@pytest.mark.parametrize("run_mode", ["dev", "test"])
def test_7_8_sandbox_works_where_it_is_allowed(env, monkeypatch, run_mode):
    client, Session = env
    monkeypatch.setenv("ENV", run_mode)
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    uid, h = lecturer(Session, f"{run_mode}@guard.test")
    r = client.post("/api/v1/billing/checkout", json={"plan_id": "pro"}, headers=h)
    assert r.status_code == 200 and r.json()["gateway"] == "sandbox", r.text
    assert user(Session, uid).plan_tier == "pro"


# ── 9. Signature and idempotency unchanged ────────────────────────────────────

def test_9_signature_is_still_mandatory_and_a_replay_applies_once(env, monkeypatch):
    client, Session = env
    monkeypatch.setenv("ENV", "production")
    uid, _ = lecturer(Session)
    ref, pid = pending(Session, uid)
    data = _kashier_data(ref)
    assert client.post("/api/v1/billing/webhook/kashier", json={"event": "pay", "data": data}).status_code == 401
    assert kashier_callback(client, data, secret="not-the-secret").status_code == 401
    assert user(Session, uid).plan_tier == "free"
    assert kashier_callback(client, data).json()["status"] == "paid"
    first_expiry = user(Session, uid).plan_expires_at
    assert kashier_callback(client, data).json().get("already_applied") is True
    assert user(Session, uid).plan_expires_at == first_expiry          # not extended twice


# ── 10. No secrets in errors or logs ──────────────────────────────────────────

def test_10_refusals_never_print_secret_values(tmp_path, env, monkeypatch, capsys):
    secret_env = {**GOOD_PRODUCTION, "BILLING_SANDBOX": "1", "KASHIER_MODE": "test",
                  "KASHIER_SECRET_KEY": "kashier-secret-SHOULD-NOT-APPEAR", "KASHIER_API_KEY": HMAC_SECRET}
    r = start(tmp_path, secret_env)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    for v in ("kashier-secret-SHOULD-NOT-APPEAR", HMAC_SECRET, GOOD_PRODUCTION["SECRET_KEY"]):
        assert v not in out

    # In-process refusal path and callback failures: nothing secret logged or stored.
    client, Session = env
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    uid, _ = lecturer(Session)
    _, pid = pending(Session, uid, provider="sandbox")
    db = Session()
    bs.apply_paid_payment(db, db.get(Payment, pid))
    db.close()
    ref, pid2 = pending(Session, uid, order=112)
    kashier_callback(client, _kashier_data(ref, amount="0.01"))
    logged = capsys.readouterr()
    notes = (payment(Session, pid).note or "") + (payment(Session, pid2).note or "")
    for v in (HMAC_SECRET, STRIPE_SECRET):
        assert v not in logged.out + logged.err + notes


def test_billing_switch_problems_are_named_without_values(monkeypatch):
    monkeypatch.setenv("BILLING_SANDBOX", "on-please-123")
    monkeypatch.setenv("KASHIER_MODE", "yes-xyz")
    msgs = " ".join(config.billing_test_mode_problems())
    assert "BILLING_SANDBOX" in msgs and "KASHIER_MODE" in msgs
    assert "on-please-123" not in msgs and "yes-xyz" not in msgs
