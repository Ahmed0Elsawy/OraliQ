"""
Payment gateway adapters for OralIQ.

  * Kashier (EGP) — hosted Payment Session (POST /v3/payment/sessions) → the lecturer pays on
    Kashier's page (card / wallet). The session's `order` is our Payment.reference, which comes back
    as merchantOrderId in the webhook. Webhooks are verified with x-kashier-signature (mandatory):
    HMAC-SHA256, keyed with the Payment API Key, over the signatureKeys of `data`.
    Reconciliation uses GET /v3/payment/sessions/{id}/payment (server-to-server, secret key).
    Docs: https://developers.kashier.io/docs/accept-payments/payment-sessions , /docs/webhooks
  Kashier is the only gateway (EGP and USD). Paymob and Stripe were removed; their earlier
  records stay in the database.

Environment variables:
  KASHIER_MERCHANT_ID   — MID (merchantId)
  KASHIER_API_KEY       — Payment API Key: `api-key` header and the webhook signature key
  KASHIER_SECRET_KEY    — Secret Key: `Authorization` header (raw, not Bearer)
  KASHIER_MODE          — "test" (test-*.kashier.io hosts, test keys) or "live". Required outside
                          production; production always uses live hosts and refuses to start with
                          KASHIER_MODE=test (app.core.config). Test and live keys are not interchangeable.
  KASHIER_WEBHOOK_URL   — optional: this server's public /api/v1/billing/webhook/kashier URL, sent
                          as the session's serverWebhook (else the dashboard-configured webhook is used)
  FRONTEND_URL     — where the user returns after checkout
  BILLING_SANDBOX  — "1" to activate plans instantly without a gateway; dev/test only, off unless
                     set, refused at startup and ignored with ENV=production
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional
from urllib.parse import quote, urlparse

import httpx

from app.models.payment import Payment
from app.models.user import User


class GatewayError(Exception):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _truthy(name: str) -> bool:
    return _env(name).lower() in ("1", "true", "yes", "on")


def test_payments_forbidden() -> bool:
    """
    The single check every test-payment path goes through: True on a production server, and also
    when the run mode can't be read (unset/unknown ENV) — doubt counts as production. Startup
    already refuses production with BILLING_SANDBOX / KASHIER_MODE=test (app.core.config); this
    keeps them inert even if one is switched on after the process started.
    """
    from app.core.config import ConfigError, current_env
    try:
        return current_env() == "production"
    except ConfigError:
        return True


def sandbox_enabled() -> bool:
    """
    Simulated payments: checkout activates the plan with no gateway and no money. Development and
    tests only, and only when asked for explicitly with BILLING_SANDBOX=1 — an unset value no
    longer turns it on. Always False in production.
    """
    if test_payments_forbidden():
        return False
    return _truthy("BILLING_SANDBOX")


def sandbox_mode() -> bool:
    """
    Whether payments on this server are test payments, which is what lets the checkout UI show
    test cards, test wallet numbers and "no real money is charged". True when plans are activated
    without a gateway (sandbox_enabled) or when Kashier is explicitly on its test hosts
    (KASHIER_MODE=test). Never true in production (or with an unknown run mode).
    """
    if test_payments_forbidden():
        return False
    return sandbox_enabled() or kashier_mode() == "test"


def frontend_url() -> str:
    return _env("FRONTEND_URL", "http://localhost:5173").rstrip("/")


# ── Kashier ───────────────────────────────────────────────────────────────────

KASHIER_HOSTS = {
    "test": "https://test-api.kashier.io",
    "live": "https://api.kashier.io",
}
# Session lifetime (expireAt). A repeated click reuses the page this long (billing_service).
KASHIER_SESSION_SECONDS = 3600
# Fields this server reads from a webhook: each must be covered by the signature.
KASHIER_SIGNED_FIELDS = ("amount", "currency", "merchantOrderId", "status", "transactionId")
# Final session states (GET /v3/payment/sessions/{id}/payment) meaning nothing was paid on it.
KASHIER_UNPAID_FINAL = ("FAILED", "EXPIRED", "ABANDONED", "REJECTED", "VOIDED", "REVERSED", "REFUNDED")


def kashier_mode() -> Optional[str]:
    """live in production (test is refused at startup); elsewhere only an explicit test / live."""
    if test_payments_forbidden():
        return "live"
    mode = _env("KASHIER_MODE").lower()
    return mode if mode in KASHIER_HOSTS else None


def kashier_configured() -> bool:
    return bool(kashier_mode() and _env("KASHIER_MERCHANT_ID") and _env("KASHIER_API_KEY")
                and _env("KASHIER_SECRET_KEY"))


def _kashier_headers() -> Dict[str, str]:
    return {"Authorization": _env("KASHIER_SECRET_KEY"), "api-key": _env("KASHIER_API_KEY"),
            "Content-Type": "application/json"}


def kashier_session_marker(session_id: Any) -> str:
    return f"kashier_session:{session_id}"


def kashier_order_ref(kashier_order_id: Any) -> Optional[str]:
    return f"kashier_order:{kashier_order_id}" if kashier_order_id else None


def kashier_amount_minor(amount: Any) -> Optional[int]:
    """
    A Kashier amount as minor units (piasters / cents). Sessions are created in major units
    ("199.00", as in Kashier's examples); the docs don't state the webhook's unit, so a webhook
    amount is read the same way — one in minor units would simply not match and go to review.
    """
    if amount is None or isinstance(amount, bool) or str(amount).strip() == "":
        return None
    try:
        value = Decimal(str(amount).strip()) * 100
    except (InvalidOperation, ValueError):
        return None
    return int(value) if value == value.to_integral_value() else None


def kashier_create_checkout(payment: Payment, user: User, description: str, **_: Any) -> str:
    """Create a hosted payment session; returns Kashier's sessionUrl. The caller commits."""
    expire_at = (datetime.now(timezone.utc) + timedelta(seconds=KASHIER_SESSION_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    body: Dict[str, Any] = {
        "expireAt": expire_at,
        "maxFailureAttempts": 3,
        "paymentType": "credit",
        "amount": f"{int(payment.amount)}.00",
        "currency": payment.currency,
        "order": payment.reference,
        "merchantRedirect": f"{frontend_url()}/dashboard?payment={payment.reference}",
        "display": "ar",
        "type": "one-time",
        "allowedMethods": "card,wallet",
        "merchantId": _env("KASHIER_MERCHANT_ID"),
        "failureRedirect": False,
        "description": description[:120],
        "manualCapture": False,
        "customer": {"email": user.email, "reference": str(user.id)},
        "interactionSource": "ECOMMERCE",
        "enable3DS": True,
    }
    if _env("KASHIER_WEBHOOK_URL"):
        body["serverWebhook"] = _env("KASHIER_WEBHOOK_URL")
    host = KASHIER_HOSTS[kashier_mode() or "test"]
    try:
        resp = httpx.post(f"{host}/v3/payment/sessions", json=body, headers=_kashier_headers(), timeout=20)
    except httpx.HTTPError as e:
        raise GatewayError(f"Kashier unreachable: {type(e).__name__}") from e
    if resp.status_code >= 300:
        raise GatewayError(f"Kashier session failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json() if resp.content else {}
    session_id, url = data.get("_id"), data.get("sessionUrl")
    if not session_id or not url:
        raise GatewayError("Kashier response missing _id / sessionUrl")
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith("kashier.io"):
        raise GatewayError("Kashier sessionUrl is not a kashier.io https URL")
    # The session id lets the server ask Kashier for this payment's state (reconciliation).
    payment.provider_txn_id = kashier_session_marker(session_id)
    return str(url)


def kashier_session_payment(session_id: str) -> Dict[str, Any]:
    """GET /v3/payment/sessions/{id}/payment — the session's payment state, straight from Kashier."""
    host = KASHIER_HOSTS[kashier_mode() or "test"]
    try:
        resp = httpx.get(f"{host}/v3/payment/sessions/{quote(str(session_id), safe='')}/payment",
                         headers=_kashier_headers(), timeout=15)
    except httpx.HTTPError as e:
        raise GatewayError(f"Kashier unreachable: {type(e).__name__}") from e
    if resp.status_code >= 300:
        raise GatewayError(f"Kashier session lookup failed ({resp.status_code})")
    body = resp.json() if resp.content else {}
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise GatewayError("Kashier session lookup: no data")
    return data


def _kashier_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))          # JSON 100.0 is written 100 by Kashier's (JS) signer
    return str(value)


def kashier_signature_string(data: Dict[str, Any]) -> Optional[str]:
    """signatureKeys sorted, key=URL-encoded(value) joined with & (Kashier webhook docs)."""
    keys = data.get("signatureKeys")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        return None
    return "&".join(f"{k}={quote(_kashier_value(data.get(k)), safe='')}" for k in sorted(keys))


def kashier_verify_signature(data: Any, received: Optional[str]) -> bool:
    secret = _env("KASHIER_API_KEY")
    if not secret or not received or not isinstance(data, dict):
        return False  # never trust unsigned callbacks
    keys = data.get("signatureKeys")
    if not isinstance(keys, list) or not set(KASHIER_SIGNED_FIELDS) <= set(keys):
        return False  # a field this server acts on would not be covered by the signature
    payload = kashier_signature_string(data)
    if payload is None:
        return False
    computed = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received.strip().lower())
