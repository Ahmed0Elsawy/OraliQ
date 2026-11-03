"""
Billing, Subscription Plans & Dual-Currency Payment Endpoints for OralIQ.

  - Kashier is the only gateway, for EGP and USD: hosted payment sessions, x-kashier-signature
    verified webhooks, reconciled with Kashier's session lookup. Paymob / Stripe records made
    earlier are kept (and an admin can still settle them), but nothing starts a payment with them.
  - Plans are activated ONLY after a verified payment (or in explicit sandbox mode / by an admin).
  - Only lecturer accounts (the billing owner) pay, renew, cancel or get refunds; students are free.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import deps
from app.core.plans import ADDON_EXAMS_PER_PACK, BILLING_PERIODS, PLANS, addon_price, get_plan, plan_price, public_plans
from app.models.billing_cancellation import BillingCancellationRequest
from app.models.payment import OPEN_STATUSES, Payment
from app.models.user import User
from app.services import billing_service as bs
from app.services import cancellations
from app.services import payment_gateways as gw

router = APIRouter()


class CheckoutRequest(BaseModel):
    kind: str = Field(default="plan", pattern="^(plan|addon)$")
    plan_id: Optional[str] = Field(default=None, max_length=32)
    period: str = Field(default="monthly", max_length=16)
    currency: str = Field(default="EGP", max_length=8)
    # Informational only: Kashier's page offers card and wallet and asks for the wallet number itself.
    payment_method: str = Field(default="card", max_length=32)
    wallet_phone: Optional[str] = Field(default=None, max_length=24)


class TeamAddRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class AdminGrantRequest(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    plan_id: Optional[str] = None
    months: int = Field(default=1, ge=1, le=36)
    custom_max_exams: Optional[int] = Field(default=None, ge=0)
    custom_max_students: Optional[int] = Field(default=None, ge=0)
    bonus_exams: int = Field(default=0, ge=0, le=10000)
    amount: int = Field(default=0, ge=0)
    currency: str = Field(default="EGP", max_length=8)
    note: Optional[str] = Field(default=None, max_length=500)


class PaymentResolveRequest(BaseModel):
    # review / pending: paid | failed (after checking the gateway dashboard)
    # refund_review:    refunded (full: take back what it granted) | keep (partial: plan stays)
    outcome: Literal["paid", "failed", "refunded", "keep"]
    note: str = Field(..., min_length=3, max_length=500)
    provider_txn_id: Optional[str] = Field(default=None, max_length=128)


class CancellationCreateRequest(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = Field(default=None, max_length=255)
    # When the lecturer's e-mail arrived at support, copied by the admin from the e-mail itself
    # (its Date / received header) — not when it is logged. There is no mailbox integration.
    received_at: datetime
    note: Optional[str] = Field(default=None, max_length=1000)


class CancellationDecisionRequest(BaseModel):
    # resolved: the lecturer stays (reactivated with the time left); approve_refund: cancel for good.
    decision: Literal["resolved", "approve_refund"]
    note: str = Field(..., min_length=3, max_length=1000)
    # Only when the refund can't be computed from the payments on record (mixed currencies, no
    # payment record): then the admin enters it. Otherwise it must equal the computed amount.
    refund_amount_minor: Optional[int] = Field(default=None, ge=0)
    refund_currency: Optional[str] = Field(default=None, max_length=8)


class RefundExecutedRequest(BaseModel):
    executed_at: Optional[datetime] = None          # when the refund was actually carried out
    refund_reference: Optional[str] = Field(default=None, max_length=128)
    note: Optional[str] = Field(default=None, max_length=1000)


PENDING_MESSAGE_AR = "التفعيل عادةً بيكون فوري، لكن التأكد من الدفع ممكن ياخد لحد 24 ساعة."
PENDING_MESSAGE_EN = "Activation is usually immediate, but confirming the payment can take up to 24 hours."
# Clock skew allowed when an admin enters a time ("received at", "executed at").
_FUTURE_TOLERANCE = timedelta(minutes=5)


def _require_lecturer(user: User) -> None:
    if user.role not in bs.LECTURER_ROLES:
        raise HTTPException(status_code=403, detail="Lecturers only")


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")


# ── Public / status ───────────────────────────────────────────────────────────

@router.get("/plans")
def list_public_plans() -> Any:
    """Public endpoint returning all subscription tiers with period prices."""
    return {
        "plans": public_plans(),
        "periods": BILLING_PERIODS,
        "addon_exams_per_pack": ADDON_EXAMS_PER_PACK,
    }


@router.get("/payment-mode")
def read_payment_mode() -> Any:
    """Public: whether checkout on this server is a test checkout. Only this one flag — never keys,
    integration ids or which gateways are configured."""
    return {"sandbox_mode": gw.sandbox_mode()}


@router.get("/status")
def read_billing_status(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Current subscription, limits, live usage and team."""
    return bs.billing_status(db, current_user)


# ── Checkout ──────────────────────────────────────────────────────────────────

def _start_checkout(db: Session, user: User, payload: CheckoutRequest) -> Any:
    _require_lecturer(user)
    account = bs.get_billing_account(db, user)
    if account.id != user.id:
        raise HTTPException(status_code=400, detail="حسابك تابع لاشتراك حساب آخر — صاحب الاشتراك هو اللي يدفع.")
    if cancellations.active_request(db, account.id):
        raise HTTPException(status_code=409, detail={
            "code": "CANCELLATION_OPEN",
            "message": "عندك طلب إلغاء اشتراك لسه بيتراجع — الدعم هيتواصل معاك. مش هينفع دفع جديد قبل ما يتقفل.",
            "message_en": "Your cancellation request is still being reviewed — support will contact you. A new payment can't start until it is closed.",
        })
    bs.refresh_account_state(db, account)

    currency = (payload.currency or "EGP").strip().upper()
    if currency not in ("EGP", "USD"):
        raise HTTPException(status_code=400, detail="Unsupported currency")

    if payload.kind == "addon":
        current_plan = get_plan(account.plan_tier)
        price = addon_price(current_plan["id"], currency)
        if price is None:
            raise HTTPException(status_code=400, detail="الامتحانات الإضافية متاحة للباقات المدفوعة (الأساسية والاحترافية) فقط.")
        payment = Payment(
            user_id=account.id, kind="addon", plan_id=current_plan["id"],
            addon_exams=ADDON_EXAMS_PER_PACK, amount=price, currency=currency,
        )
        description = f"OralIQ +{ADDON_EXAMS_PER_PACK} exams"
    else:
        plan_id = (payload.plan_id or "").strip().lower()
        period = (payload.period or "monthly").strip().lower()
        if plan_id not in PLANS:
            raise HTTPException(status_code=400, detail="Invalid subscription plan ID")
        if period not in BILLING_PERIODS:
            raise HTTPException(status_code=400, detail="Invalid billing period")
        price = plan_price(plan_id, period, currency)
        if price is None:
            if plan_id == "enterprise":
                raise HTTPException(status_code=400, detail="باقة المؤسسات بالتعاقد — تواصل معنا وهنفعّلها لك.")
            raise HTTPException(status_code=400, detail="This plan cannot be purchased")
        payment = Payment(
            user_id=account.id, kind="plan", plan_id=plan_id, period=period,
            amount=price, currency=currency,
        )
        description = f"OralIQ {PLANS[plan_id]['name_en']} ({BILLING_PERIODS[period]['name_en']})"

    if gw.kashier_configured():           # EGP and USD alike
        provider = "kashier"
        # One unresolved gateway payment per account. An unresolved one that can't simply be
        # reopened is first checked with Kashier: a session that ended unpaid is closed (the
        # lecturer may pay again), one that was paid is applied. Then the account row is locked
        # so two checkouts at once are serialised; the unique index on (user_id, open_slot)
        # backs this up.
        bs.move_stale_to_review(db, account.id)
        existing = bs.open_payment(db, account.id)
        if existing and not _reusable(existing, payment, provider):
            _reconcile_kashier(db, existing)
        db.query(User).filter(User.id == account.id).with_for_update().first()
        existing = bs.open_payment(db, account.id)
        if existing:
            return _reuse_or_block(existing, payment, provider)
        payment.provider = provider
        payment.status = "pending"
        db.add(payment)
        try:
            db.commit()
        except IntegrityError:          # a concurrent checkout opened one first
            db.rollback()
            existing = bs.open_payment(db, account.id)
            if existing:
                return _reuse_or_block(existing, payment, provider)
            raise HTTPException(status_code=409, detail="عملية دفع أخرى بتتسجل دلوقتي — حاول تاني بعد لحظات.")
        db.refresh(payment)
        try:
            url = gw.kashier_create_checkout(payment, account, description)
        except Exception as e:
            # No payment page reached the lecturer, so nothing can be paid on this one: close it
            # (a stuck "pending" would block the next checkout for a day). Any gateway id already
            # recorded is kept: if money still arrives on it, the signed callback still applies it.
            payment.status = "failed"
            payment.note = (str(e) if isinstance(e, gw.GatewayError) else f"checkout error: {type(e).__name__}")[:500]
            db.commit()
            bs.log_billing(f"payment {payment.reference}: checkout could not start ({payment.note})")
            raise HTTPException(status_code=502, detail="تعذر بدء عملية الدفع — حاول مرة أخرى.")
        payment.checkout_url = url
        payment.checkout_expires_at = bs.utcnow() + timedelta(seconds=bs.CHECKOUT_REUSE_SECONDS)
        db.commit()  # keeps the gateway order id recorded on the payment
        return {
            "ok": True,
            "gateway": payment.provider,
            "reference": payment.reference,
            "currency": currency,
            "amount": payment.amount,
            "checkout_url": url,
            "message": "جاري تحويلك لصفحة الدفع...",
            "pending_message": PENDING_MESSAGE_AR,
            "pending_message_en": PENDING_MESSAGE_EN,
        }

    if gw.sandbox_enabled() and not gw.test_payments_forbidden():
        # Development / tests only: simulate a successful payment. sandbox_enabled() is already
        # False in production; apply_paid_payment refuses a non-gateway payment there as well.
        payment.provider = "sandbox"
        db.add(payment)
        db.commit()
        db.refresh(payment)
        bs.apply_paid_payment(db, payment, provider_txn_id=f"sandbox-{payment.id}")
        return {
            "ok": True,
            "gateway": "sandbox",
            "reference": payment.reference,
            "currency": currency,
            "amount": payment.amount,
            "checkout_url": None,
            "message": f"(وضع تجريبي) تم التفعيل بنجاح ({payment.amount} {'ج.م' if currency == 'EGP' else '$'})",
            **bs.billing_status(db, user),
        }

    raise HTTPException(status_code=503, detail="بوابة الدفع غير مفعّلة حالياً — تواصل مع الدعم.")


def _reusable(existing: Payment, requested: Payment, provider: str) -> bool:
    """Same purchase, still pending, and its payment page is still valid."""
    same = (
        existing.provider == provider
        and existing.kind == requested.kind
        and existing.plan_id == requested.plan_id
        and (existing.period or None) == (requested.period or None)
        and (existing.currency or "").upper() == (requested.currency or "").upper()
    )
    fresh = existing.checkout_expires_at is not None and existing.checkout_expires_at > bs.utcnow()
    return bool(existing.status == "pending" and same and existing.checkout_url and fresh)


def _reuse_or_block(existing: Payment, requested: Payment, provider: str) -> Any:
    """
    The account already has an unresolved payment. A repeated click for the same purchase gets
    that payment's page back while it is still valid; anything else waits until it is confirmed
    (paid / failed) — a second payment could otherwise charge the lecturer twice.
    """
    if _reusable(existing, requested, provider):
        return {
            "ok": True,
            "reused": True,
            "gateway": existing.provider,
            "reference": existing.reference,
            "currency": existing.currency,
            "amount": existing.amount,
            "checkout_url": existing.checkout_url,
            "message": "عندك عملية دفع مفتوحة لنفس الطلب — هنكملها.",
            "pending_message": PENDING_MESSAGE_AR,
            "pending_message_en": PENDING_MESSAGE_EN,
        }
    if existing.status == "review":
        detail = {
            "code": "PAYMENT_IN_REVIEW",
            "message": "عملية الدفع السابقة لسه تحت المراجعة. مش هتقدر تبدأ دفع جديد قبل ما نتأكد منها — تواصل مع الدعم لو محتاج مساعدة.",
            "message_en": "Your previous payment is under review. A new payment can't start until it is confirmed — contact support if you need help.",
        }
    else:
        detail = {
            "code": "PAYMENT_PENDING",
            "message": f"عندك عملية دفع سابقة لسه بنتأكد منها. {PENDING_MESSAGE_AR} مش هتقدر تبدأ دفع جديد قبل ما نتأكد منها.",
            "message_en": f"You have a previous payment we're still confirming. {PENDING_MESSAGE_EN} A new payment can't start until it is confirmed.",
        }
    raise HTTPException(status_code=409, detail={**detail, "reference": existing.reference, "status": existing.status})


@router.post("/checkout")
def create_checkout(
    *,
    db: Session = Depends(deps.get_db),
    payload: CheckoutRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Start a checkout for a plan (monthly / term / yearly) or an add-on exam pack."""
    return _start_checkout(db, current_user, payload)


@router.post("/upgrade")
def upgrade_subscription_plan(
    *,
    db: Session = Depends(deps.get_db),
    payload: CheckoutRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Backward-compatible alias of /checkout (does NOT activate without payment)."""
    return _start_checkout(db, current_user, payload)


@router.get("/payments")
def list_my_payments(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_lecturer(current_user)     # students are free: they have no payments
    bs.move_stale_to_review(db, current_user.id)
    rows = db.query(Payment).filter(Payment.user_id == current_user.id).order_by(Payment.id.desc()).limit(50).all()
    return [_payment_out(p) for p in rows]


@router.get("/payments/{reference}")
def get_payment(
    reference: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """The lecturer's own payment — what the page shows on return from the gateway. Only the
    server's record counts; the gateway's redirect parameters are never trusted."""
    _require_lecturer(current_user)
    bs.move_stale_to_review(db, current_user.id)
    p = db.query(Payment).filter(Payment.reference == reference, Payment.user_id == current_user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _payment_out(p)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _payment_out(p: Payment) -> dict:
    return {
        "reference": p.reference, "kind": p.kind, "plan_id": p.plan_id, "period": p.period,
        "addon_exams": p.addon_exams, "amount": p.amount, "currency": p.currency,
        "provider": p.provider, "status": p.status,
        "created_at": _iso(p.created_at),
        "paid_at": _iso(p.paid_at),
        "review_at": _iso(p.review_at),
        "refunded_at": _iso(p.refunded_at),
    }


# ── Webhooks ──────────────────────────────────────────────────────────────────

def _fulfil(db: Session, reference: Optional[str], amount_minor: Optional[int], currency: Optional[str],
            success: bool, txn_id: Optional[str], provider: str, order_ref: Optional[str] = None) -> dict:
    if not reference:
        return {"received": True, "matched": False}
    payment = (
        db.query(Payment).filter(Payment.reference == str(reference)).with_for_update().first()
    )
    if not payment:
        bs.log_billing(f"signed callback for an unknown payment reference ({str(reference)[:64]})")
        return {"received": True, "matched": False}
    if payment.provider != provider:
        # Signed by one gateway for a payment made with another (or a sandbox / manual one).
        return {"received": True, "matched": False}
    if payment.status in bs.FINAL_STATUSES:
        # Duplicate / late success: applied once already (or refunded) — never extends again.
        return {"received": True, "matched": True, "already_applied": True, "status": payment.status}
    if not success:
        if payment.status in OPEN_STATUSES:
            payment.status = "failed"
        payment.provider_txn_id = str(txn_id)[:128] if txn_id else payment.provider_txn_id
        db.commit()
        return {"received": True, "matched": True, "status": "failed"}
    expected_minor = int(payment.amount) * 100
    # A success that doesn't state the amount and currency is not proof of payment: both are
    # required, not merely checked when present.
    try:
        paid_minor = int(amount_minor) if amount_minor is not None and str(amount_minor).strip() != "" else None
    except (TypeError, ValueError):
        paid_minor = None
    if paid_minor != expected_minor:
        # Money of the wrong amount: never applied, kept for an admin to reconcile.
        bs.flag_for_review(db, payment, f"amount mismatch: got {str(amount_minor)[:32]}, expected {expected_minor}")
        return {"received": True, "matched": True, "status": "amount_mismatch"}
    if not currency or str(currency).upper() != payment.currency.upper():
        bs.flag_for_review(db, payment, f"currency mismatch: got {str(currency)[:16]}")
        return {"received": True, "matched": True, "status": "currency_mismatch"}
    if not payment.provider_order_ref and order_ref:
        payment.provider_order_ref = order_ref   # refunds map back through it
    applied = bs.apply_paid_payment(db, payment, provider_txn_id=txn_id)
    return {"received": True, "matched": True, "status": "paid" if applied else payment.status}


def _reverse(db: Session, payment: Payment, full: bool, refunded_minor: Optional[int], source: str) -> dict:
    if full:
        result = bs.reverse_payment(db, payment, refunded_minor, source)
    elif payment.status in ("paid", "refund_review"):
        result = bs.mark_refund_review(db, payment, f"partial or unconfirmed refund reported by {source}")
    else:
        bs.log_billing(f"payment {payment.reference}: refund/void callback from {source} while {payment.status!r} — left as is")
        result = payment.status
    return {"received": True, "matched": True, "refund": result}


def _kashier_payment(db: Session, data: dict) -> Optional[Payment]:
    """The payment a signed Kashier transaction belongs to: our reference (merchantOrderId, signed),
    else the Kashier order recorded when it was paid (kashierOrderId)."""
    q = db.query(Payment).filter(Payment.provider == "kashier")
    reference = data.get("merchantOrderId")
    payment = q.filter(Payment.reference == str(reference)).with_for_update().first() if reference else None
    order_ref = gw.kashier_order_ref(data.get("kashierOrderId"))
    if not payment and order_ref:
        payment = q.filter(Payment.provider_order_ref == order_ref).with_for_update().first()
    return payment


def _kashier_reversal(db: Session, event: str, status: str, data: dict) -> dict:
    """
    A signed refund / partial_refund / void / reversal. Never a success: it can only take back
    what the payment granted. A void / reversal / refund of the whole amount removes the
    entitlement; a partial one (partial_refund, or a smaller amount) is flagged for an admin.
    """
    if status != "SUCCESS":
        bs.log_billing(f"Kashier {event} {status or 'without status'} for {data.get('merchantOrderId')} — nothing changed")
        return {"received": True, "ignored": f"{event}_{(status or 'unknown').lower()}"}
    payment = _kashier_payment(db, data)
    if not payment:
        bs.log_billing(f"Kashier {event} for no matching payment ({data.get('merchantOrderId')}) — unresolved, check the Kashier dashboard")
        return {"received": True, "matched": False, "ignored": event}
    expected_minor = int(payment.amount) * 100
    amount_minor = gw.kashier_amount_minor(data.get("amount"))
    if event in ("void", "reversal"):
        full = amount_minor is None or amount_minor == expected_minor
    else:
        full = event == "refund" and amount_minor == expected_minor
    return _reverse(db, payment, full, amount_minor if amount_minor is not None else (expected_minor if full else None),
                    f"kashier {event}")


def _reconcile_kashier(db: Session, payment: Payment) -> str:
    """
    Ask Kashier (GET /v3/payment/sessions/{id}/payment, server to server) what became of an
    unresolved payment. PAID is applied through the same checks as a webhook; a session that
    ended unpaid closes the payment (the lecturer may pay again); anything else — still open,
    unknown, or Kashier unreachable — leaves it as it is.
    """
    marker = payment.provider_txn_id or ""
    if payment.provider != "kashier" or payment.status not in OPEN_STATUSES or not marker.startswith("kashier_session:"):
        return payment.status
    try:
        data = gw.kashier_session_payment(marker.split(":", 1)[1])
    except gw.GatewayError as e:
        bs.log_billing(f"payment {payment.reference}: Kashier lookup failed ({e}) — left {payment.status}")
        return payment.status
    state = str(data.get("status") or "").upper()
    if data.get("merchantOrderId") not in (None, payment.reference):
        bs.flag_for_review(db, payment, "Kashier session lookup returned another merchantOrderId")
        return payment.status
    if state == "PAID":
        result = _fulfil(db, payment.reference, gw.kashier_amount_minor(data.get("amount")), data.get("currency"),
                         True, data.get("sessionId") or marker, "kashier",
                         order_ref=gw.kashier_order_ref(data.get("orderId")))
        bs.log_billing(f"payment {payment.reference}: Kashier session PAID -> {result.get('status')}")
    elif state in gw.KASHIER_UNPAID_FINAL:
        payment.status = "failed"
        bs._append_note(payment, f"Kashier session {state}")
        db.commit()
        bs.log_billing(f"payment {payment.reference}: Kashier session {state} -> failed (new checkout allowed)")
    return payment.status


@router.post("/webhook/kashier")
async def kashier_webhook(
    request: Request,
    signature: Optional[str] = Header(default=None, alias="x-kashier-signature"),
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Kashier transaction webhook. The x-kashier-signature check is mandatory (HMAC-SHA256 with the
    Payment API Key over data.signatureKeys). The outcome is data.status, never the event's
    arrival. Kashier retries until it gets 200 and may repeat a delivery: every branch is idempotent.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    data = body.get("data") if isinstance(body, dict) else None
    if not gw.kashier_verify_signature(data, signature):
        raise HTTPException(status_code=401, detail="Invalid Kashier signature")
    event = str(body.get("event") or "").strip().lower()
    status = str(data.get("status") or "").strip().upper()
    if event in ("refund", "partial_refund", "void", "reversal"):
        return _kashier_reversal(db, event, status, data)
    if event not in ("pay", "idempotency"):
        # authorize / capture (manualCapture is off) / reject / anything new: never a purchase.
        bs.log_billing(f"Kashier {event or 'unknown'} event ({status}) for {data.get('merchantOrderId')} — not a purchase, ignored")
        return {"received": True, "ignored": event or "unknown"}
    if status == "PENDING":
        return {"received": True, "pending": True}
    if status != "SUCCESS":
        # A failed attempt doesn't end the session (the page allows more attempts until it
        # expires), so the payment stays unresolved; Kashier's session state closes it.
        payment = _kashier_payment(db, data)
        if payment and payment.status in OPEN_STATUSES:
            bs._append_note(payment, f"attempt {status or 'unknown'} ({str(data.get('transactionResponseCode'))[:32]})")
            db.commit()
        return {"received": True, "matched": bool(payment), "status": "attempt_failed"}
    return _fulfil(
        db,
        reference=data.get("merchantOrderId"),
        amount_minor=gw.kashier_amount_minor(data.get("amount")),
        currency=data.get("currency"),
        success=True,
        txn_id=data.get("transactionId"),
        provider="kashier",
        order_ref=gw.kashier_order_ref(data.get("kashierOrderId")),
    )


# ── Team (assistant accounts) ─────────────────────────────────────────────────

@router.get("/team")
def list_team(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_lecturer(current_user)
    status = bs.billing_status(db, current_user)
    return {"team": status["team"], "assistant_seats": status["usage"]["assistant_seats"]}


@router.post("/team")
def add_team_member(
    *,
    db: Session = Depends(deps.get_db),
    payload: TeamAddRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Owner links an existing lecturer account as an assistant (shares the owner's quota)."""
    _require_lecturer(current_user)
    if current_user.owner_id:
        raise HTTPException(status_code=400, detail="حساب المساعد لا يمكنه إضافة مساعدين.")
    bs.refresh_account_state(db, current_user)
    seats = get_plan(current_user.plan_tier)["assistant_seats"]
    current_count = db.query(User).filter(User.owner_id == current_user.id).count()
    if get_plan(current_user.plan_tier)["id"] in ("free", "pro"):
        raise bs.QuotaExceeded(
            "ASSISTANTS_NOT_IN_PLAN",
            "حسابات المساعدين متاحة في الباقة الاحترافية والمؤسسات.",
            "Assistant accounts are available on Professional and Enterprise plans.",
        )
    if seats != 0 and current_count >= seats:
        raise bs.QuotaExceeded(
            "ASSISTANT_SEATS_FULL",
            f"وصلت للحد الأقصى من المساعدين ({seats}).",
            f"Assistant seats are full ({seats}).",
            limit=seats,
        )
    email_clean = payload.email.strip().lower()
    if email_clean == (current_user.email or "").lower():
        raise HTTPException(status_code=400, detail="لا يمكنك إضافة نفسك.")
    member = db.query(User).filter(func.lower(User.email) == email_clean).first()
    # One answer for every address that can't be added — no account, a student, someone else's
    # assistant, a team owner — so this form can't be used to find out who is registered or what
    # kind of account an address is.
    if (
        not member
        or member.role not in bs.LECTURER_ROLES
        or (member.owner_id and member.owner_id != current_user.id)
        or db.query(User).filter(User.owner_id == member.id).count()
    ):
        raise HTTPException(
            status_code=404,
            detail="مفيش حساب محاضر متاح للإضافة بالبريد ده. اطلب من المساعد يسجّل كمحاضر بنفس البريد، ومايكونش تابع لفريق تاني.",
        )
    member.owner_id = current_user.id
    db.commit()
    return {"ok": True, "member": {"id": member.id, "email": member.email, "full_name": member.full_name}}


@router.delete("/team/{member_id}")
def remove_team_member(
    member_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_lecturer(current_user)
    member = db.query(User).filter(User.id == member_id).first()
    if not member or member.owner_id != current_user.id:
        # An assistant may also leave the team themselves.
        if not (member and member.id == current_user.id and member.owner_id):
            raise HTTPException(status_code=404, detail="Team member not found")
    member.owner_id = None
    db.commit()
    return {"ok": True}


# ── Admin (manual payments, enterprise contracts, bonus exams) ────────────────

@router.post("/admin/grant")
def admin_grant(
    *,
    db: Session = Depends(deps.get_db),
    payload: AdminGrantRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Admin: activate a plan after offline payment (InstaPay/transfer) or an enterprise contract."""
    _require_admin(current_user)
    q = db.query(User)
    target = q.filter(User.id == payload.user_id).first() if payload.user_id else (
        q.filter(func.lower(User.email) == (payload.email or "").strip().lower()).first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role not in bs.LECTURER_ROLES:
        raise HTTPException(status_code=400, detail="Subscriptions belong to lecturer accounts — students are free.")

    bs.refresh_account_state(db, target)
    if payload.plan_id:
        plan_id = payload.plan_id.strip().lower()
        if plan_id not in PLANS or plan_id == "free":
            raise HTTPException(status_code=400, detail="Invalid plan")
        bs.grant_plan(target, plan_id, "monthly", months=payload.months)
    if payload.custom_max_exams is not None:
        target.custom_max_exams = payload.custom_max_exams
    if payload.custom_max_students is not None:
        target.custom_max_students = payload.custom_max_students
    if payload.bonus_exams:
        target.bonus_exams = int(target.bonus_exams or 0) + payload.bonus_exams

    db.add(Payment(
        user_id=target.id, kind="plan" if payload.plan_id else "addon",
        plan_id=(payload.plan_id or target.plan_tier), period=f"{payload.months}m",
        addon_exams=payload.bonus_exams, amount=payload.amount, currency=payload.currency.upper(),
        provider="manual", status="paid", paid_at=bs.utcnow(),
        note=f"granted by admin #{current_user.id}: {payload.note or ''}"[:500],
    ))
    db.commit()
    return {"ok": True, **bs.billing_status(db, target)}


# ── Admin: reconciliation (payments in review) ───────────────────────────────

def _admin_payment_out(db: Session, p: Payment) -> dict:
    owner = db.query(User.email).filter(User.id == p.user_id).scalar()
    return {**_payment_out(p), "user_id": p.user_id, "user_email": owner, "note": p.note,
            "provider_order_ref": p.provider_order_ref}


@router.get("/admin/payments")
def admin_list_payments(
    status: str = Query(default="review", max_length=16),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Admin: payments needing attention (review = unconfirmed for 24h+, refund_review, pending)."""
    _require_admin(current_user)
    bs.move_stale_to_review(db)
    rows = db.query(Payment).filter(Payment.status == status).order_by(Payment.id.asc()).limit(200).all()
    return [_admin_payment_out(db, p) for p in rows]


@router.post("/admin/payments/{reference}/verify")
def admin_verify_payment(
    reference: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Admin: ask Kashier what became of an unresolved payment (paid -> applied with the usual
    amount / currency checks; ended unpaid -> failed; otherwise unchanged)."""
    _require_admin(current_user)
    p = db.query(Payment).filter(Payment.reference == reference).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    _reconcile_kashier(db, p)
    db.refresh(p)
    return _admin_payment_out(db, p)


@router.post("/admin/payments/{reference}/resolve")
def admin_resolve_payment(
    reference: str,
    payload: PaymentResolveRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Admin: settle a payment by hand after checking it in the gateway's own dashboard (use
    /verify first for Kashier). review/pending -> paid | failed; refund_review -> refunded | keep.
    """
    _require_admin(current_user)
    p = db.query(Payment).filter(Payment.reference == reference).with_for_update().first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    tag = f"admin #{current_user.id}: {payload.note}"
    if p.status in OPEN_STATUSES and payload.outcome in ("paid", "failed"):
        if payload.outcome == "paid":
            bs._append_note(p, f"confirmed paid by {tag}")
            if not bs.apply_paid_payment(db, p, provider_txn_id=payload.provider_txn_id):
                raise HTTPException(status_code=409, detail=f"Payment could not be applied (status {p.status}).")
        else:
            p.status = "failed"
            bs._append_note(p, f"confirmed not paid by {tag}")
            db.commit()
    elif p.status == "refund_review" and payload.outcome in ("refunded", "keep"):
        if payload.outcome == "refunded":
            bs.reverse_payment(db, p, p.refunded_amount_minor or int(p.amount) * 100, tag)
        else:
            p.status = "paid"
            bs._append_note(p, f"partial refund, subscription kept by {tag}")
            db.commit()
    else:
        raise HTTPException(status_code=409, detail=f"Cannot mark a {p.status!r} payment as {payload.outcome!r}.")
    bs.log_billing(f"payment {p.reference} resolved by admin #{current_user.id} as {payload.outcome}")
    return _admin_payment_out(db, p)


# ── Admin: cancellation requests (received by e-mail) ─────────────────────────
# The admin types in the e-mail's arrival time (there is no mailbox integration). Recording it
# pauses the subscription; the time left at arrival is kept. Resolved -> reactivated with that
# time; approved -> prorated refund, carried out by hand and then recorded. See
# app.services.cancellations for the policy.

def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _not_future(value: datetime, field: str) -> None:
    if value > bs.utcnow() + _FUTURE_TOLERANCE:
        raise HTTPException(status_code=400, detail=f"{field} can't be in the future.")


def _cancellation_out(c: BillingCancellationRequest) -> dict:
    return {
        "id": c.id, "user_id": c.user_id, "channel": c.channel, "status": c.status,
        "request_received_at": _iso(c.request_received_at),
        "recorded_at": _iso(c.recorded_at), "recorded_by": c.recorded_by,
        "plan_tier_at_request": c.plan_tier_at_request,
        "plan_expires_at_at_request": _iso(c.plan_expires_at_at_request),
        "remaining_seconds": c.remaining_seconds,
        "remaining_days": round((c.remaining_seconds or 0) / 86400, 2),
        "term_seconds": c.term_seconds, "term_paid_minor": c.term_paid_minor, "term_currency": c.term_currency,
        "computed_refund_minor": c.computed_refund_minor,
        "decided_at": _iso(c.decided_at), "decided_by": c.decided_by, "decision_note": c.decision_note,
        "reactivated_at": _iso(c.reactivated_at), "reactivated_until": _iso(c.reactivated_until),
        "refund_amount_minor": c.refund_amount_minor, "refund_currency": c.refund_currency,
        "refund_executed_at": _iso(c.refund_executed_at), "refund_recorded_by": c.refund_recorded_by,
        "refund_reference": c.refund_reference, "note": c.note,
    }


def _get_cancellation(db: Session, request_id: int) -> BillingCancellationRequest:
    c = db.query(BillingCancellationRequest).filter(BillingCancellationRequest.id == request_id).with_for_update().first()
    if not c:
        raise HTTPException(status_code=404, detail="Cancellation request not found")
    return c


@router.post("/admin/cancellation-requests")
def admin_record_cancellation(
    payload: CancellationCreateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Admin: record a lecturer's cancellation e-mail (arrival time typed in from the e-mail).
    Pauses the subscription now and keeps the time left at the e-mail's arrival."""
    _require_admin(current_user)
    q = db.query(User)
    target = q.filter(User.id == payload.user_id).first() if payload.user_id else (
        q.filter(func.lower(User.email) == (payload.email or "").strip().lower()).first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    received_at = _naive_utc(payload.received_at)
    _not_future(received_at, "received_at")
    c = cancellations.record_request(db, target, received_at, current_user.id, payload.note)
    return _cancellation_out(c)


@router.get("/admin/cancellation-requests")
def admin_list_cancellations(
    status: Optional[str] = Query(default=None, max_length=16),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    _require_admin(current_user)
    q = db.query(BillingCancellationRequest)
    if status:
        q = q.filter(BillingCancellationRequest.status == status)
    return [_cancellation_out(c) for c in q.order_by(BillingCancellationRequest.id.asc()).limit(200).all()]


@router.post("/admin/cancellation-requests/{request_id}/decision")
def admin_decide_cancellation(
    request_id: int,
    payload: CancellationDecisionRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Admin, after contacting the lecturer: resolved (reactivated with the full time left) or
    approve_refund (cancelled for good, prorated refund approved — no money is sent here)."""
    _require_admin(current_user)
    c = _get_cancellation(db, request_id)
    if c.status != "open":
        raise HTTPException(status_code=409, detail=f"Request is already {c.status}.")
    if payload.decision == "resolved":
        cancellations.resolve_and_reactivate(db, c, current_user.id, payload.note)
    else:
        cancellations.approve_refund(db, c, current_user.id, payload.note,
                                     payload.refund_amount_minor, payload.refund_currency)
    return _cancellation_out(c)


@router.post("/admin/cancellation-requests/{request_id}/refund-executed")
def admin_record_refund_executed(
    request_id: int,
    payload: RefundExecutedRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Admin: the approved refund was carried out by hand (e.g. in Kashier's dashboard). Records
    when, and marks the term's payments refunded. The subscription is already stopped."""
    _require_admin(current_user)
    c = _get_cancellation(db, request_id)
    if c.status != "approved":
        raise HTTPException(status_code=409, detail=f"Only an approved request can be marked refunded (this one is {c.status}).")
    executed_at = _naive_utc(payload.executed_at) if payload.executed_at else bs.utcnow()
    _not_future(executed_at, "executed_at")
    if executed_at < c.request_received_at:
        raise HTTPException(status_code=400, detail="executed_at is before the request was received.")
    cancellations.record_refund_executed(db, c, executed_at, current_user.id, payload.refund_reference, payload.note)
    return _cancellation_out(c)
