"""
H8 — Kashier payments, pending / review, duplicates, refunds / voids, and cancellation requests.

The lecturer is the customer (pays, renews, cancels, gets refunds); students are free and can't
reach any financial action. No real gateway is called: Kashier's session creation and session
lookup are replaced by fakes, and webhooks are signed locally with a test Payment API Key, the
way Kashier documents it (HMAC-SHA256 over the sorted, URL-encoded signatureKeys of `data`).
"""
import hashlib
import hmac
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.payment import Payment
from app.services import billing_service as bs
from app.services import cancellations
from app.services import payment_gateways as gw
from app.services.billing_service import utcnow
from app.tests.test_billing import (  # noqa: F401
    KASHIER_TEST_KEY, _kashier_data, _kashier_send, _kashier_sign, env, get_user, make_user, update_user,
)

API = "/api/v1/billing"
DAY = 86400


@pytest.fixture()
def km(env, monkeypatch):
    """Kashier 'configured' with fake session creation / lookup (no network). Sandbox off."""
    client, Session = env
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    calls, sessions = [], {}

    def fake_checkout(payment, user, description, **_):
        sid = f"s-{len(calls) + 1}"
        calls.append(payment.reference)
        payment.provider_txn_id = gw.kashier_session_marker(sid)
        return f"https://payments.kashier.io/session/{sid}"

    def fake_lookup(session_id):
        if session_id not in sessions:
            raise gw.GatewayError("Kashier unreachable: ConnectError")
        return sessions[session_id]

    monkeypatch.setattr(gw, "kashier_configured", lambda: True)
    monkeypatch.setattr(gw, "kashier_create_checkout", fake_checkout)
    monkeypatch.setattr(gw, "kashier_session_payment", fake_lookup)
    return client, Session, calls, sessions


def _payment(Session, ref):
    db = Session()
    p = db.query(Payment).filter(Payment.reference == ref).first()
    db.expunge(p)
    db.close()
    return p


def _set_payment(Session, ref, **fields):
    db = Session()
    p = db.query(Payment).filter(Payment.reference == ref).first()
    for k, v in fields.items():
        setattr(p, k, v)
    db.commit()
    db.close()


def _checkout(client, h, **body):
    return client.post(f"{API}/checkout", json={"plan_id": "pro", "period": "monthly", **body}, headers=h)


def _pay(client, h, amount="199.00", **body):
    """Checkout + Kashier's signed SUCCESS pay webhook. Returns the reference."""
    r = _checkout(client, h, **body)
    assert r.status_code == 200, r.text
    ref = r.json()["reference"]
    data = _kashier_data(ref, amount=amount, kashierOrderId=f"ko-{ref[-6:]}", transactionId=f"TX-{ref[-6:]}")
    assert _kashier_send(client, data).json()["status"] == "paid"
    return ref


def _admin(Session):
    return make_user(Session, "admin@t.com", role="admin")[1]


def _iso(dt):
    return dt.isoformat() + "Z"


# ── Kashier integration as documented ─────────────────────────────────────────

def test_signature_string_follows_kashier_docs():
    data = {"signatureKeys": ["status", "amount", "channel"], "status": "SUCCESS", "amount": 11334,
            "channel": "online | e-commerce", "notSigned": "x"}
    # Sorted keys, values URL-encoded (the docs' own example: "online | e-commerce").
    assert gw.kashier_signature_string(data) == "amount=11334&channel=online%20%7C%20e-commerce&status=SUCCESS"


def test_signature_must_cover_every_field_the_server_reads(env):
    client, Session = env
    uid, _ = make_user(Session, "cover@t.com")
    data = _kashier_data("oiq_" + "0" * 32)
    for field in gw.KASHIER_SIGNED_FIELDS:
        loose = {**data, "signatureKeys": [k for k in data["signatureKeys"] if k != field]}
        assert _kashier_send(client, loose).status_code == 401, field


def test_create_session_request_matches_kashier_docs(env, monkeypatch):
    _, Session = env
    monkeypatch.setenv("ENV", "dev")
    for k, v in {"KASHIER_MODE": "test", "KASHIER_MERCHANT_ID": "MID-1-2", "KASHIER_API_KEY": "api-k",
                 "KASHIER_SECRET_KEY": "sec-k", "KASHIER_WEBHOOK_URL": "https://api.example/wh"}.items():
        monkeypatch.setenv(k, v)
    sent = {}

    class Resp:
        status_code, content, text = 200, b"x", ""

        @staticmethod
        def json():
            return {"_id": "sess-9", "sessionUrl": "https://payments.kashier.io/session/sess-9", "status": "CREATED"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return Resp()
    monkeypatch.setattr(httpx, "post", fake_post)
    uid, _ = make_user(Session, "body@t.com")
    p = Payment(user_id=uid, kind="plan", plan_id="pro", period="monthly", amount=199, currency="EGP", provider="kashier")
    from app.models.user import User
    url = gw.kashier_create_checkout(p, User(id=uid, email="body@t.com"), "OralIQ Pro (Monthly)")
    assert sent["url"] == "https://test-api.kashier.io/v3/payment/sessions"
    assert sent["headers"]["Authorization"] == "sec-k" and sent["headers"]["api-key"] == "api-k"
    b = sent["body"]
    assert b["amount"] == "199.00" and b["currency"] == "EGP" and b["order"] == p.reference
    assert b["merchantId"] == "MID-1-2" and b["serverWebhook"] == "https://api.example/wh"
    assert b["merchantRedirect"].endswith(f"/dashboard?payment={p.reference}") and b["manualCapture"] is False
    assert url.startswith("https://payments.kashier.io/") and p.provider_txn_id == "kashier_session:sess-9"
    # A sessionUrl that isn't Kashier's is refused (never redirect the lecturer elsewhere).
    Resp.json = staticmethod(lambda: {"_id": "x", "sessionUrl": "https://evil.example/pay"})
    with pytest.raises(gw.GatewayError):
        gw.kashier_create_checkout(p, User(id=uid, email="body@t.com"), "x")
    # Production always uses the live host.
    monkeypatch.setenv("ENV", "production")
    Resp.json = staticmethod(lambda: {"_id": "s", "sessionUrl": "https://payments.kashier.io/s"})
    gw.kashier_create_checkout(p, User(id=uid, email="body@t.com"), "x")
    assert sent["url"] == "https://api.kashier.io/v3/payment/sessions"


# ── Successful / failed / pending payments ────────────────────────────────────

def test_successful_payment_activates_once_for_the_paying_lecturer(km):
    client, Session, calls, _ = km
    uid, h = make_user(Session, "payer@t.com")
    r = _checkout(client, h)
    assert r.status_code == 200 and r.json()["gateway"] == "kashier"
    ref = r.json()["reference"]
    p = _payment(Session, ref)
    assert p.user_id == uid and p.status == "pending"
    assert get_user(Session, uid).plan_tier == "free"           # nothing before Kashier confirms
    data = _kashier_data(ref, kashierOrderId="ko-77")
    assert _kashier_send(client, data).json()["status"] == "paid"
    assert get_user(Session, uid).plan_tier == "pro"
    assert _payment(Session, ref).provider_order_ref == "kashier_order:ko-77"   # kept for refunds


def test_pending_status_stays_pending_with_24h_message(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "slow@t.com")
    r = _checkout(client, h)
    assert "24" in r.json()["pending_message"] and "24" in r.json()["pending_message_en"]
    ref = r.json()["reference"]
    assert _kashier_send(client, _kashier_data(ref, status="PENDING")).json()["pending"] is True
    assert client.get(f"{API}/payments/{ref}", headers=h).json()["status"] == "pending"
    assert get_user(Session, uid).plan_tier == "free"


def test_failed_attempt_keeps_the_session_open_and_kashier_confirms_the_end(km):
    client, Session, calls, sessions = km
    uid, h = make_user(Session, "fail@t.com")
    ref = _checkout(client, h).json()["reference"]
    # A declined card: Kashier's page allows more attempts, so the payment stays unresolved.
    assert _kashier_send(client, _kashier_data(ref, status="FAILURE")).json()["status"] == "attempt_failed"
    assert _payment(Session, ref).status == "pending"
    # The lecturer comes back for another plan: the server asks Kashier first.
    sessions["s-1"] = {"status": "FAILED", "merchantOrderId": ref}
    r = _checkout(client, h, plan_id="campus")
    assert r.status_code == 200 and r.json()["reference"] != ref
    assert _payment(Session, ref).status == "failed"
    assert get_user(Session, uid).plan_tier == "free"


def test_late_webhook_after_24h_review_still_applies(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "late@t.com")
    ref = _checkout(client, h).json()["reference"]
    _set_payment(Session, ref, created_at=utcnow() - timedelta(hours=25))
    got = client.get(f"{API}/payments/{ref}", headers=h).json()
    assert got["status"] == "review" and got["review_at"]          # review, never "failed"
    assert _kashier_send(client, _kashier_data(ref)).json()["status"] == "paid"
    assert get_user(Session, uid).plan_tier == "pro"


def test_duplicate_and_replayed_webhooks_never_extend_twice(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "dup@t.com")
    ref = _checkout(client, h).json()["reference"]
    data = _kashier_data(ref)
    _kashier_send(client, data)
    expiry = get_user(Session, uid).plan_expires_at
    for event in ("pay", "idempotency", "pay"):
        assert _kashier_send(client, data, event=event).json()["already_applied"] is True
    assert get_user(Session, uid).plan_expires_at == expiry


def test_no_activation_before_payment_is_confirmed(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "redirect@t.com")
    ref = _checkout(client, h).json()["reference"]
    # The browser coming back with paymentStatus=SUCCESS can only read the payment.
    assert client.get(f"{API}/payments/{ref}?paymentStatus=SUCCESS", headers=h).json()["status"] == "pending"
    assert client.get(f"{API}/status", headers=h).json()["plan_tier"] == "free"
    assert client.post(f"{API}/webhook/kashier", json={"event": "pay", "data": _kashier_data(ref)}).status_code == 401
    assert _kashier_send(client, _kashier_data(ref), signature="00" * 32).status_code == 401
    assert get_user(Session, uid).plan_tier == "free"


def test_amount_or_currency_mismatch_is_never_applied(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "amt@t.com")
    ref = _checkout(client, h).json()["reference"]
    assert _kashier_send(client, _kashier_data(ref, amount="1.99")).json()["status"] == "amount_mismatch"
    assert _payment(Session, ref).status == "review"
    uid2, h2 = make_user(Session, "cur@t.com")
    ref2 = _checkout(client, h2).json()["reference"]
    assert _kashier_send(client, _kashier_data(ref2, currency="USD")).json()["status"] == "currency_mismatch"
    assert get_user(Session, uid).plan_tier == "free" and get_user(Session, uid2).plan_tier == "free"


def test_a_kashier_webhook_cannot_pay_a_stripe_or_sandbox_payment(km):
    client, Session, _, _ = km
    uid, _ = make_user(Session, "cross@t.com")
    db = Session()
    p = Payment(user_id=uid, kind="plan", plan_id="pro", period="monthly", amount=199, currency="EGP", provider="stripe")
    db.add(p)
    db.commit()
    ref = p.reference
    db.close()
    assert _kashier_send(client, _kashier_data(ref)).json()["matched"] is False
    assert get_user(Session, uid).plan_tier == "free"


# ── One pending payment, repeated clicks, concurrency, reconciliation ─────────

def test_repeated_click_returns_the_existing_payment(km):
    client, Session, calls, _ = km
    _, h = make_user(Session, "click@t.com")
    first = _checkout(client, h).json()
    second = _checkout(client, h).json()
    assert second["reused"] is True and second["reference"] == first["reference"]
    assert second["checkout_url"] == first["checkout_url"] and len(calls) == 1


def test_concurrent_checkouts_open_only_one_payment(km, monkeypatch):
    client, Session, calls, _ = km
    uid, h = make_user(Session, "race@t.com")
    first = _checkout(client, h).json()
    real = bs.open_payment
    seen = {"n": 0}

    def blind_twice(db, account_id):      # the racing request doesn't see the first one
        seen["n"] += 1
        return None if seen["n"] <= 2 else real(db, account_id)
    monkeypatch.setattr(bs, "open_payment", blind_twice)
    second = _checkout(client, h)
    assert second.status_code == 200 and second.json()["reference"] == first["reference"]
    db = Session()
    assert db.query(Payment).filter(Payment.user_id == uid, Payment.status == "pending").count() == 1
    db.add(Payment(user_id=uid, kind="plan", plan_id="pro", period="monthly", amount=199, currency="EGP", provider="kashier"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.close()


def test_a_second_payment_waits_until_kashier_confirms_the_first(km):
    client, Session, calls, sessions = km
    _, h = make_user(Session, "block@t.com")
    ref = _checkout(client, h).json()["reference"]
    # Kashier can't be reached: blocked (never "assume it failed").
    r = _checkout(client, h, plan_id="campus")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PAYMENT_PENDING" and "24" in r.json()["detail"]["message"]
    # Kashier says the session is still open: still blocked.
    sessions["s-1"] = {"status": "PENDING", "merchantOrderId": ref}
    assert _checkout(client, h, plan_id="campus").status_code == 409
    # In review after 24h: blocked with the review message until Kashier / an admin settles it.
    _set_payment(Session, ref, created_at=utcnow() - timedelta(hours=25))
    r = _checkout(client, h, plan_id="campus")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PAYMENT_IN_REVIEW"
    # The session expired unpaid: closed, and the new checkout goes ahead.
    sessions["s-1"] = {"status": "EXPIRED", "merchantOrderId": ref}
    assert _checkout(client, h, plan_id="campus").status_code == 200
    assert _payment(Session, ref).status == "failed" and len(calls) == 2


def test_reconciliation_applies_a_paid_session_with_the_usual_checks(km):
    client, Session, calls, sessions = km
    uid, h = make_user(Session, "recon@t.com")
    ref = _checkout(client, h).json()["reference"]
    _set_payment(Session, ref, checkout_expires_at=utcnow() - timedelta(minutes=1))   # page expired
    sessions["s-1"] = {"status": "PAID", "merchantOrderId": ref, "amount": "1.00", "currency": "EGP"}
    assert _checkout(client, h).status_code == 409                  # wrong amount: not applied
    assert _payment(Session, ref).status == "review"
    sessions["s-1"]["amount"] = "199.00"
    ah = _admin(Session)
    out = client.post(f"{API}/admin/payments/{ref}/verify", headers=ah).json()
    assert out["status"] == "paid" and get_user(Session, uid).plan_tier == "pro"


def test_retry_allowed_after_checkout_error(km, monkeypatch):
    client, Session, _, _ = km
    _, h = make_user(Session, "boom@t.com")

    def broken(*a, **k):
        raise ValueError("unexpected gateway response")
    monkeypatch.setattr(gw, "kashier_create_checkout", broken)
    assert _checkout(client, h).status_code == 502
    monkeypatch.setattr(gw, "kashier_create_checkout", lambda p, *a, **k: "https://payments.kashier.io/x")
    assert _checkout(client, h).status_code == 200


# ── Refund / void as Kashier sends them ───────────────────────────────────────

def test_kashier_void_and_full_refund_reverse_partial_is_flagged(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "void@t.com")
    ref = _pay(client, h)
    order = f"ko-{ref[-6:]}"
    # Failed / pending refund operations change nothing.
    for status in ("FAILURE", "PENDING"):
        r = _kashier_send(client, _kashier_data(ref, status=status, kashierOrderId=order), event="refund")
        assert "ignored" in r.json()
    # A partial refund keeps the plan and is flagged for an admin.
    r = _kashier_send(client, _kashier_data(ref, amount="50.00", kashierOrderId=order), event="partial_refund")
    assert r.json()["refund"] == "refund_review" and get_user(Session, uid).plan_tier == "pro"
    # The full refund (matched by the Kashier order even without our reference) takes it back.
    data = _kashier_data(None, kashierOrderId=order, transactionId="TX-R1")
    r = _kashier_send(client, data, event="refund")
    assert r.json()["refund"] == "refunded" and get_user(Session, uid).plan_tier == "free"
    # A late "pay" replay never brings it back.
    assert _kashier_send(client, _kashier_data(ref)).json()["already_applied"] is True
    assert get_user(Session, uid).plan_tier == "free"

    uid2, h2 = make_user(Session, "void2@t.com")
    ref2 = _pay(client, h2)
    assert _kashier_send(client, _kashier_data(ref2), event="void").json()["refund"] == "refunded"
    assert get_user(Session, uid2).plan_tier == "free"
    assert _kashier_send(client, _kashier_data("oiq_" + "f" * 32, kashierOrderId="none"), event="void").json()["matched"] is False


def test_refunding_one_renewal_keeps_the_other_month(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "renewref@t.com")
    _pay(client, h)
    ref2 = _pay(client, h)
    before = get_user(Session, uid).plan_expires_at
    _kashier_send(client, _kashier_data(ref2), event="reversal")
    u = get_user(Session, uid)
    assert u.plan_tier == "pro" and (before - u.plan_expires_at).days == 30


def test_renewals_and_plan_changes_still_work(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "renew@t.com")
    _pay(client, h)
    first = get_user(Session, uid).plan_expires_at
    _pay(client, h)
    assert (get_user(Session, uid).plan_expires_at - first).days == 30
    _pay(client, h, amount="599.00", plan_id="campus")
    assert get_user(Session, uid).plan_tier == "campus"


# ── Cancellation: pause, remaining time, reactivation, prorated refund ────────

def _subscribed(client, Session, email, days_used=10):
    """A lecturer who paid 199 EGP for 30 days and has used `days_used` of them."""
    uid, h = make_user(Session, email)
    ref = _pay(client, h)
    u = get_user(Session, uid)
    shift = timedelta(days=days_used)
    update_user(Session, uid, plan_started_at=u.plan_started_at - shift, plan_expires_at=u.plan_expires_at - shift,
                cycle_started_at=u.cycle_started_at - shift, cycle_exams_used=3)
    _set_payment(Session, ref, paid_at=u.plan_started_at - shift)
    return uid, h, ref


def _record(client, ah, uid, received_at):
    r = client.post(f"{API}/admin/cancellation-requests", headers=ah, json={"user_id": uid, "received_at": _iso(received_at)})
    assert r.status_code == 200, r.text
    return r.json()


def test_recording_the_request_pauses_the_subscription_and_keeps_the_remaining_time(km):
    client, Session, _, _ = km
    uid, h, _ = _subscribed(client, Session, "pause@t.com", days_used=10)
    ah = _admin(Session)
    received = utcnow().replace(microsecond=0)
    c = _record(client, ah, uid, received)
    assert c["status"] == "open" and c["plan_tier_at_request"] == "pro"
    assert abs(c["remaining_seconds"] - 20 * DAY) <= 5                 # 30-day plan, 10 days used
    assert get_user(Session, uid).plan_tier == "free"                  # stopped right away
    assert client.get(f"{API}/status", headers=h).json()["plan_tier"] == "free"
    # No new payment while the request is open.
    r = _checkout(client, h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CANCELLATION_OPEN"


def test_staying_restores_the_full_remaining_time_and_review_time_is_not_taken(km):
    client, Session, _, _ = km
    uid, _, _ = _subscribed(client, Session, "stay@t.com", days_used=10)
    ah = _admin(Session)
    received = utcnow() - timedelta(days=4)            # e-mail arrived 4 days ago, logged today
    c = _record(client, ah, uid, received)
    assert abs(c["remaining_seconds"] - 24 * DAY) <= 5  # 30 - (10 - 4) days left when it ARRIVED
    r = client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                    json={"decision": "resolved", "note": "problem fixed, lecturer stays"}).json()
    assert r["status"] == "resolved" and r["refund_amount_minor"] is None
    u = get_user(Session, uid)
    assert u.plan_tier == "pro"
    left = (u.plan_expires_at - utcnow()).total_seconds()
    assert abs(left - 24 * DAY) <= 5                    # the 4 days of review are not deducted
    assert u.cycle_exams_used == 3                      # quota usage restored, not reset


def test_policy_example_30_days_cancel_after_10_continue_gets_20(km):
    client, Session, _, _ = km
    uid, _, _ = _subscribed(client, Session, "example@t.com", days_used=10)
    ah = _admin(Session)
    c = _record(client, ah, uid, utcnow())
    client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                json={"decision": "resolved", "note": "continues"})
    left_days = (get_user(Session, uid).plan_expires_at - utcnow()).total_seconds() / DAY
    assert 19.99 <= left_days <= 20.0


def test_refund_is_prorated_from_the_request_time_without_fees(km, monkeypatch):
    client, Session, _, _ = km
    uid, _, ref = _subscribed(client, Session, "refund@t.com", days_used=10)
    ah = _admin(Session)

    def no_network(*a, **k):
        raise AssertionError("approving a refund must not call any gateway")
    monkeypatch.setattr(httpx, "post", no_network)
    monkeypatch.setattr(httpx, "put", no_network)
    received = utcnow() - timedelta(days=6)            # arrived 6 days ago: 4 days used then, 26 left
    c = _record(client, ah, uid, received)
    expected = 19900 * c["remaining_seconds"] // (30 * DAY)
    assert c["term_paid_minor"] == 19900 and c["term_seconds"] == 30 * DAY
    assert c["computed_refund_minor"] == expected
    assert abs(expected - 19900 * 26 // 30) <= 1        # 26 of 30 days at arrival — not 20 (today)
    # An amount other than the computed one is refused; the computed one is approved.
    bad = client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                      json={"decision": "approve_refund", "note": "cancel for good", "refund_amount_minor": expected - 500})
    assert bad.status_code == 400
    d = client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                    json={"decision": "approve_refund", "note": "cancel for good"}).json()
    assert d["status"] == "approved" and d["refund_amount_minor"] == expected and d["refund_currency"] == "EGP"
    assert d["refund_executed_at"] is None and _payment(Session, ref).status == "paid"
    assert get_user(Session, uid).plan_tier == "free"   # stays stopped


def test_request_decision_and_execution_times_stay_separate(km):
    client, Session, _, _ = km
    uid, _, ref = _subscribed(client, Session, "times@t.com", days_used=5)
    ah = _admin(Session)
    received = (utcnow() - timedelta(days=3)).replace(microsecond=0)
    executed = (utcnow() - timedelta(hours=1)).replace(microsecond=0)
    c = _record(client, ah, uid, received)
    assert c["request_received_at"] == received.isoformat() and c["recorded_at"] != c["request_received_at"]
    assert client.post(f"{API}/admin/cancellation-requests/{c['id']}/refund-executed", headers=ah,
                       json={}).status_code == 409                 # not approved yet
    client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                json={"decision": "approve_refund", "note": "approved after call"})
    assert client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                       json={"decision": "resolved", "note": "again"}).status_code == 409
    assert client.post(f"{API}/admin/cancellation-requests/{c['id']}/refund-executed", headers=ah,
                       json={"executed_at": _iso(received - timedelta(days=1))}).status_code == 400
    done = client.post(f"{API}/admin/cancellation-requests/{c['id']}/refund-executed", headers=ah,
                       json={"executed_at": _iso(executed), "refund_reference": "kashier-refund-1"}).json()
    assert done["status"] == "refunded"
    assert done["request_received_at"] == received.isoformat()          # unchanged by the admin's work
    assert done["refund_executed_at"] == executed.isoformat()
    assert done["decided_at"] not in (done["request_received_at"], done["refund_executed_at"])
    p = _payment(Session, ref)
    assert p.status == "refunded" and p.refunded_amount_minor == done["refund_amount_minor"]
    # Kashier's own refund webhook arriving afterwards changes nothing more.
    _kashier_send(client, _kashier_data(ref, amount="50.00", kashierOrderId=f"ko-{ref[-6:]}"), event="partial_refund")
    assert _payment(Session, ref).status == "refunded"
    assert get_user(Session, uid).plan_tier == "free"


def test_received_time_is_required_and_not_in_the_future(km):
    client, Session, _, _ = km
    uid, _, _ = _subscribed(client, Session, "future@t.com")
    ah = _admin(Session)
    assert client.post(f"{API}/admin/cancellation-requests", headers=ah, json={"user_id": uid}).status_code == 422
    bad = client.post(f"{API}/admin/cancellation-requests", headers=ah,
                      json={"user_id": uid, "received_at": _iso(utcnow() + timedelta(days=1))})
    assert bad.status_code == 400
    assert get_user(Session, uid).plan_tier == "pro"     # nothing paused by a refused request
    _record(client, ah, uid, utcnow())
    assert client.post(f"{API}/admin/cancellation-requests", headers=ah,
                       json={"user_id": uid, "received_at": _iso(utcnow())}).status_code == 409   # one at a time


def test_renewed_term_is_prorated_over_both_payments(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "two@t.com")
    _pay(client, h)
    _pay(client, h)                                      # 60 days paid, 398 EGP
    ah = _admin(Session)
    c = _record(client, ah, uid, utcnow())
    assert c["term_paid_minor"] == 39800 and c["term_seconds"] == 60 * DAY
    assert abs(c["computed_refund_minor"] - 39800) <= 2  # nothing used yet


def test_prorated_formula():
    assert cancellations.prorated_refund_minor(19900, 20 * DAY, 30 * DAY) == 13266
    assert cancellations.prorated_refund_minor(19900, 0, 30 * DAY) == 0
    assert cancellations.prorated_refund_minor(19900, 40 * DAY, 30 * DAY) == 19900   # never above what was paid


# ── Lecturer is the customer; students are free ─────────────────────────────

def test_student_cannot_reach_any_financial_action(km):
    client, Session, calls, _ = km
    sid, sh = make_user(Session, "student@t.com", role="student")
    for path, body in (("/checkout", {"plan_id": "pro"}), ("/upgrade", {"plan_id": "pro"}), ("/checkout", {"kind": "addon"})):
        assert client.post(f"{API}{path}", json=body, headers=sh).status_code == 403
    assert client.get(f"{API}/payments", headers=sh).status_code == 403
    assert client.get(f"{API}/payments/oiq_x", headers=sh).status_code == 403
    assert client.get(f"{API}/team", headers=sh).status_code == 403
    assert client.post(f"{API}/team", json={"email": "x@t.com"}, headers=sh).status_code == 403
    assert client.delete(f"{API}/team/{sid}", headers=sh).status_code == 403
    for path in ("/admin/payments", "/admin/cancellation-requests"):
        assert client.get(f"{API}{path}", headers=sh).status_code == 403
    assert client.post(f"{API}/admin/payments/oiq_x/verify", headers=sh).status_code == 403
    assert client.post(f"{API}/admin/grant", json={"user_id": sid, "plan_id": "pro"}, headers=sh).status_code == 403
    assert calls == []
    ah = _admin(Session)
    assert client.post(f"{API}/admin/grant", json={"user_id": sid, "plan_id": "pro"}, headers=ah).status_code == 400
    assert client.post(f"{API}/admin/cancellation-requests", headers=ah,
                       json={"user_id": sid, "received_at": _iso(utcnow())}).status_code == 400
    assert get_user(Session, sid).plan_tier == "free"


def test_payment_for_an_account_that_is_no_longer_a_lecturer_is_not_applied(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "became@t.com")
    ref = _checkout(client, h).json()["reference"]
    update_user(Session, uid, role="student")
    _kashier_send(client, _kashier_data(ref))
    assert get_user(Session, uid).plan_tier == "free" and _payment(Session, ref).status == "review"


def test_admin_endpoints_need_admin_and_assistants_do_not_pay(km):
    client, Session, _, _ = km
    owner, oh = make_user(Session, "owner@t.com")
    aid, lh = make_user(Session, "assist@t.com")
    assert client.get(f"{API}/admin/payments", headers=oh).status_code == 403
    assert client.post(f"{API}/admin/cancellation-requests", headers=oh,
                       json={"user_id": owner, "received_at": _iso(utcnow())}).status_code == 403
    update_user(Session, owner, plan_tier="campus", plan_expires_at=utcnow() + timedelta(days=20))
    update_user(Session, aid, owner_id=owner)
    assert _checkout(client, lh).status_code == 400                  # the team owner pays
    ah = _admin(Session)
    assert client.post(f"{API}/admin/cancellation-requests", headers=ah,
                       json={"user_id": aid, "received_at": _iso(utcnow())}).status_code == 400


def test_simulated_payments_still_refused_outside_sandbox(km, monkeypatch):
    _, Session, _, _ = km
    uid, _ = make_user(Session, "c3@t.com")
    db = Session()
    p = Payment(user_id=uid, kind="plan", plan_id="pro", period="monthly", amount=199, currency="EGP", provider="sandbox")
    db.add(p)
    db.commit()
    assert bs.apply_paid_payment(db, p) is False and p.status == "failed"
    db.close()
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    monkeypatch.setenv("KASHIER_MODE", "test")
    assert gw.sandbox_enabled() is False and gw.sandbox_mode() is False and gw.kashier_mode() == "live"


def test_signature_helper_matches_an_independent_hmac():
    data = _kashier_data("oiq_" + "1" * 32)
    keys = sorted(data["signatureKeys"])
    from urllib.parse import quote
    payload = "&".join(f"{k}={quote(str(data[k]), safe='')}" for k in keys)
    assert _kashier_sign(data) == hmac.new(KASHIER_TEST_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


# ── Final H8 adjustments: Kashier for EGP and USD only; add-on exams frozen while paused ──

def test_kashier_session_in_usd(env, monkeypatch):
    _, Session = env
    monkeypatch.setenv("ENV", "dev")
    for k, v in {"KASHIER_MODE": "test", "KASHIER_MERCHANT_ID": "MID-1", "KASHIER_API_KEY": "a", "KASHIER_SECRET_KEY": "s"}.items():
        monkeypatch.setenv(k, v)
    sent = {}

    class Resp:
        status_code, content, text = 200, b"x", ""

        @staticmethod
        def json():
            return {"_id": "s-usd", "sessionUrl": "https://payments.kashier.io/session/s-usd"}

    monkeypatch.setattr(httpx, "post", lambda url, json=None, headers=None, timeout=None: sent.update(body=json) or Resp())
    uid, _ = make_user(Session, "usd-body@t.com")
    from app.models.user import User
    p = Payment(user_id=uid, kind="plan", plan_id="pro", period="monthly", amount=12, currency="USD", provider="kashier")
    gw.kashier_create_checkout(p, User(id=uid, email="usd-body@t.com"), "OralIQ Pro")
    assert sent["body"]["currency"] == "USD" and sent["body"]["amount"] == "12.00"


def test_egp_and_usd_checkouts_both_go_through_kashier(km, monkeypatch):
    client, Session, calls, _ = km
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")           # an old key left behind changes nothing
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    for currency in ("EGP", "USD"):
        uid, h = make_user(Session, f"{currency.lower()}@t.com")
        r = _checkout(client, h, currency=currency)
        assert r.status_code == 200 and r.json()["gateway"] == "kashier" and r.json()["currency"] == currency
        ref, amount = r.json()["reference"], r.json()["amount"]
        assert _payment(Session, ref).provider == "kashier"
        data = _kashier_data(ref, amount=f"{amount}.00", currency=currency)
        assert _kashier_send(client, data).json()["status"] == "paid"
        assert _kashier_send(client, data).json()["already_applied"] is True      # once only
        assert get_user(Session, uid).plan_tier == "pro"
    assert len(calls) == 2
    db = Session()
    assert db.query(Payment).filter(Payment.provider.in_(("stripe", "paymob"))).count() == 0
    db.close()


def test_without_kashier_no_other_gateway_starts_a_payment(env, monkeypatch):
    client, Session = env
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("PAYMOB_API_KEY", "pm")
    _, h = make_user(Session, "nogw@t.com")
    for currency in ("EGP", "USD"):
        assert _checkout(client, h, currency=currency).status_code == 503
    assert not hasattr(gw, "stripe_create_checkout") and not hasattr(gw, "paymob_create_checkout")


def test_pause_freezes_add_on_exams_and_blocks_new_exams(km):
    from app.tests.test_billing import new_exam
    client, Session, _, _ = km
    uid, h, _ = _subscribed(client, Session, "bonus@t.com", days_used=10)
    update_user(Session, uid, bonus_exams=7)
    ah = _admin(Session)
    c = _record(client, ah, uid, utcnow())
    u = get_user(Session, uid)
    assert u.bonus_exams == 0 and u.plan_tier == "free"                  # frozen, not usable
    r = new_exam(client, h)
    # Stopped by the service pause (403) before the quota check (402 SUBSCRIPTION_PAUSED) is reached.
    assert r.status_code == 403 and r.json()["detail"]["code"] == "SERVICE_PAUSED"
    assert get_user(Session, uid).bonus_exams == 0
    # The lecturer stays: plan time and the whole add-on balance come back.
    client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                json={"decision": "resolved", "note": "lecturer stays"})
    u = get_user(Session, uid)
    assert u.bonus_exams == 7 and u.plan_tier == "pro"
    assert new_exam(client, h).status_code == 200


def test_final_cancellation_keeps_add_on_balance_frozen_and_out_of_the_refund(km):
    client, Session, _, _ = km
    uid, h = make_user(Session, "addonfinal@t.com")
    _pay(client, h)
    r = client.post(f"{API}/checkout", json={"kind": "addon"}, headers=h)
    ref = r.json()["reference"]
    _kashier_send(client, _kashier_data(ref, amount=f"{r.json()['amount']}.00"))
    assert get_user(Session, uid).bonus_exams == 10
    ah = _admin(Session)
    c = _record(client, ah, uid, utcnow())
    assert c["term_paid_minor"] == 19900                                 # the add-on pack isn't in it
    d = client.post(f"{API}/admin/cancellation-requests/{c['id']}/decision", headers=ah,
                    json={"decision": "approve_refund", "note": "cancel for good"}).json()
    assert d["refund_amount_minor"] == c["computed_refund_minor"]
    assert get_user(Session, uid).bonus_exams == 0                       # still frozen (not decided)
    db = Session()
    from app.models.billing_cancellation import BillingCancellationRequest
    assert db.get(BillingCancellationRequest, c["id"]).bonus_exams_frozen == 10
    db.close()
