"""
Lecturer cancellation requests (received by e-mail at OralIQ support, recorded by an admin).

Policy:
  * Only the lecturer who pays (the billing owner) has a subscription to cancel; students are free.
  * The e-mail's arrival time is entered by the admin from the e-mail and never changes. Nothing
    here reads a mailbox: there is no e-mail integration.
  * Recording the request pauses the lecturer's service immediately: the subscription stops, the
    add-on exam balance is frozen (nothing can be consumed) and no new exam can be created. The
    time left when the e-mail arrived is kept, so the admin's review time is never taken.
  * Resolved (the lecturer stays): the subscription comes back with that full remaining time and
    the add-on balance comes back in full.
  * Approved (cancel for good): refund = paid amount of the term × remaining / term length, from
    the arrival time — no fees, taxes or deductions, and no deduction for the review time. The
    refund is never sent automatically: it is carried out by a person and then recorded.
  * Add-on exam packs are not time-based: they are left out of the refund, and on a final
    cancellation their balance stays frozen — what happens to it is not decided yet.

All times are naive UTC.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.plans import BILLING_PERIODS
from app.models.billing_cancellation import BillingCancellationRequest
from app.models.payment import Payment
from app.models.user import User
from app.services import billing_service as bs

ACTIVE_STATUSES = ("open", "approved")


def active_request(db: Session, user_id: int) -> Optional[BillingCancellationRequest]:
    """An open (paused) or approved request: no new checkout while one exists."""
    return (
        db.query(BillingCancellationRequest)
        .filter(BillingCancellationRequest.user_id == user_id,
                BillingCancellationRequest.status.in_(ACTIVE_STATUSES))
        .first()
    )


def payment_days(p: Payment) -> Optional[int]:
    """Days a plan payment bought: a billing period, or "<n>m" from an admin grant (n × 30)."""
    if p.period in BILLING_PERIODS:
        return int(BILLING_PERIODS[p.period]["days"])
    m = re.fullmatch(r"(\d+)m", p.period or "")
    return int(m.group(1)) * 30 if m else None


def term_payments(db: Session, user: User) -> List[Payment]:
    """The plan payments behind the current subscription: same plan, paid since it started
    (a renewal of the same plan extends the term; a plan change starts a new one)."""
    if not user.plan_started_at:
        return []
    return (
        db.query(Payment)
        .filter(Payment.user_id == user.id, Payment.kind == "plan",
                Payment.plan_id == (user.plan_tier or "").lower(),
                Payment.status.in_(("paid", "refund_review")),
                Payment.paid_at >= user.plan_started_at)
        .order_by(Payment.id.asc())
        .all()
    )


def prorated_refund_minor(paid_minor: int, remaining_seconds: int, term_seconds: int) -> int:
    """paid × remaining / term, rounded down to the minor unit. Nothing else is added or taken."""
    if not term_seconds or term_seconds <= 0 or paid_minor <= 0 or remaining_seconds <= 0:
        return 0
    return paid_minor * min(remaining_seconds, term_seconds) // term_seconds


def record_request(db: Session, target: User, received_at: datetime, admin_id: int,
                   note: Optional[str]) -> BillingCancellationRequest:
    """Record the e-mail, snapshot the subscription at its arrival, and pause it now."""
    if target.role not in bs.LECTURER_ROLES:
        raise HTTPException(status_code=400, detail="Only lecturer accounts pay — students have no subscription to cancel.")
    if target.owner_id:
        raise HTTPException(status_code=400, detail="This account is a team assistant — the team owner holds the subscription.")
    if active_request(db, target.id):
        raise HTTPException(status_code=409, detail="This lecturer already has an open cancellation request.")
    bs.refresh_account_state(db, target)
    now = bs.utcnow()
    tier = (target.plan_tier or "free").lower()
    c = BillingCancellationRequest(
        user_id=target.id, channel="email", request_received_at=received_at,
        recorded_at=now, recorded_by=admin_id, note=note, status="open",
        plan_tier_at_request=tier, plan_period_at_request=target.plan_period,
        plan_started_at_at_request=target.plan_started_at,
        plan_expires_at_at_request=target.plan_expires_at,
        cycle_started_at_at_request=target.cycle_started_at,
        cycle_exams_used_at_request=int(target.cycle_exams_used or 0),
        bonus_exams_frozen=int(target.bonus_exams or 0),
        remaining_seconds=0,
    )
    if tier != "free" and target.plan_expires_at:
        if target.plan_started_at and received_at < target.plan_started_at:
            raise HTTPException(status_code=409, detail="The plan changed after this e-mail arrived — handle this request by hand.")
        c.remaining_seconds = max(0, int((target.plan_expires_at - received_at).total_seconds()))
        payments = term_payments(db, target)
        days = [payment_days(p) for p in payments]
        currencies = {(p.currency or "").upper() for p in payments}
        c.term_payment_ids = ",".join(str(p.id) for p in payments) or None
        c.term_paid_minor = sum(int(p.amount or 0) * 100 for p in payments)
        c.term_currency = currencies.pop() if len(currencies) == 1 else None
        if payments and None not in days and c.term_currency:
            c.term_seconds = sum(days) * 86400
            c.computed_refund_minor = prorated_refund_minor(c.term_paid_minor, c.remaining_seconds, c.term_seconds)
        else:
            # No payment record, mixed currencies or an unknown period: the amount needs a person.
            bs.log_billing(f"cancellation for user #{target.id}: refund can't be computed from the payments on record")
        bs.end_subscription(target, now)          # paused from the moment it is recorded
    target.bonus_exams = 0                        # frozen; kept in c.bonus_exams_frozen
    db.add(c)
    db.commit()
    db.refresh(c)
    bs.log_billing(f"cancellation request #{c.id} recorded for user #{target.id} (received "
                   f"{received_at.isoformat()}, {c.remaining_seconds}s left) — subscription paused")
    return c


def resolve_and_reactivate(db: Session, c: BillingCancellationRequest, admin_id: int, note: str) -> None:
    """The lecturer stays: the subscription returns with the full time left at the e-mail's arrival."""
    now = bs.utcnow()
    user = db.query(User).filter(User.id == c.user_id).with_for_update().first()
    if user and c.plan_tier_at_request and c.plan_tier_at_request != "free" and c.remaining_seconds > 0:
        shift = now - c.request_received_at       # the paused time is added back, not consumed
        user.plan_tier = c.plan_tier_at_request
        user.plan_period = c.plan_period_at_request
        user.plan_started_at = c.plan_started_at_at_request
        user.plan_expires_at = now + timedelta(seconds=c.remaining_seconds)
        user.cycle_started_at = (c.cycle_started_at_at_request + shift) if c.cycle_started_at_at_request else now
        user.cycle_exams_used = int(c.cycle_exams_used_at_request or 0)
        user.plan_updated_at = now.replace(tzinfo=timezone.utc).isoformat()
        c.reactivated_at = now
        c.reactivated_until = user.plan_expires_at
    if user and c.bonus_exams_frozen:
        # The frozen add-on balance comes back in full (on top of anything granted meanwhile).
        user.bonus_exams = int(user.bonus_exams or 0) + int(c.bonus_exams_frozen)
        c.reactivated_at = c.reactivated_at or now
    c.status = "resolved"
    c.decided_at = now
    c.decided_by = admin_id
    c.decision_note = note
    db.commit()
    bs.log_billing(f"cancellation request #{c.id}: resolved, subscription reactivated until {c.reactivated_until}")


def approve_refund(db: Session, c: BillingCancellationRequest, admin_id: int, note: str,
                   manual_amount_minor: Optional[int], manual_currency: Optional[str]) -> None:
    """Cancel for good and approve the prorated refund. Moves no money; the plan stays paused."""
    if c.computed_refund_minor is not None:
        if manual_amount_minor is not None and manual_amount_minor != c.computed_refund_minor:
            raise HTTPException(status_code=400, detail=(
                f"The refund is computed from the remaining time ({c.computed_refund_minor} minor units); "
                "a different amount can't be approved here."))
        c.refund_amount_minor = c.computed_refund_minor
        c.refund_currency = c.term_currency
    else:
        if manual_amount_minor is None or not manual_currency:
            raise HTTPException(status_code=400, detail=(
                "The refund couldn't be computed from the payments on record — enter "
                "refund_amount_minor and refund_currency."))
        c.refund_amount_minor = manual_amount_minor
        c.refund_currency = manual_currency.upper()
    c.status = "approved"
    c.decided_at = bs.utcnow()
    c.decided_by = admin_id
    c.decision_note = note
    db.commit()
    bs.log_billing(f"cancellation request #{c.id}: refund of {c.refund_amount_minor} {c.refund_currency} "
                   f"approved by admin #{admin_id} (not sent — to be carried out by hand)")


def record_refund_executed(db: Session, c: BillingCancellationRequest, executed_at: datetime, admin_id: int,
                           reference: Optional[str], note: Optional[str]) -> None:
    """The approved refund was carried out (e.g. in Kashier's dashboard). Records when."""
    c.status = "refunded"
    c.refund_executed_at = executed_at
    c.refund_recorded_by = admin_id
    c.refund_reference = reference
    if note:
        c.note = f"{c.note} | {note}" if c.note else note
    ids = [int(i) for i in (c.term_payment_ids or "").split(",") if i.strip().isdigit()]
    for p in db.query(Payment).filter(Payment.id.in_(ids)).with_for_update().all() if ids else []:
        if p.status in ("paid", "refund_review"):
            p.status = "refunded"
            p.refunded_at = executed_at
            # This payment's share of the refund, by its part of the amount paid for the term.
            p.refunded_amount_minor = (
                int(c.refund_amount_minor or 0) * int(p.amount or 0) * 100 // int(c.term_paid_minor)
                if c.term_paid_minor else None
            )
            bs._append_note(p, f"refund via cancellation request #{c.id}")
    db.commit()
    bs.log_billing(f"cancellation request #{c.id}: refund executed at {executed_at.isoformat()} by admin #{admin_id}")
