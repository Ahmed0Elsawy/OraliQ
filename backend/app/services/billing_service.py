"""
Billing logic for OralIQ subscriptions.

Responsibilities:
  * Resolve the billing account (assistants bill to their owner when the owner's plan has seats).
  * Maintain the 30-day quota cycle and expire plans (with a short grace period).
  * Enforce limits: exams per cycle (+ non-expiring bonus packs), questions per exam,
    answer duration, distinct students per cycle.
  * Activate plans / add-on packs after a verified payment.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException
from sqlalchemy import String, case, cast, func, literal, update
from sqlalchemy.orm import Session

from app.core.plans import (
    ADDON_EXAMS_PER_PACK,
    BILLING_PERIODS,
    CYCLE_DAYS,
    GRACE_DAYS,
    UNLIMITED,
    get_plan,
    public_plans,
)
from app.models.exam_session import ExamSession
from app.models.exam_submission import ExamSubmission
from app.models.payment import GATEWAY_PROVIDERS, OPEN_STATUSES, Payment
from app.models.question import Question
from app.models.user import User

LECTURER_ROLES = ("lecturer", "hr", "admin")


def utcnow() -> datetime:
    """Naive UTC timestamp (matches the rest of the DB, which stores naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class QuotaExceeded(HTTPException):
    """402 Payment Required with a machine-readable code for the frontend upgrade prompt."""

    def __init__(self, code: str, message_ar: str, message_en: str, **extra: Any):
        super().__init__(
            status_code=402,
            detail={"code": code, "message": message_ar, "message_en": message_en, "upgrade_required": True, **extra},
        )


# ── Account resolution ────────────────────────────────────────────────────────

def get_billing_account(db: Session, user: User) -> User:
    """Assistants consume their owner's quota while the owner's plan includes assistant seats."""
    if user.owner_id:
        owner = db.query(User).filter(User.id == user.owner_id).first()
        if owner:
            refresh_account_state(db, owner)
            if get_plan(owner.plan_tier).get("assistant_seats") != 0:
                return owner
    return user


def team_member_ids(db: Session, account: User) -> List[int]:
    ids = [account.id]
    ids += [uid for (uid,) in db.query(User.id).filter(User.owner_id == account.id).all()]
    return ids


# ── Cycle & expiry maintenance ────────────────────────────────────────────────

def refresh_account_state(db: Session, account: User) -> User:
    """Expire finished plans and roll the monthly quota cycle forward. Idempotent."""
    now = utcnow()
    changed = False
    tier = (account.plan_tier or "free").lower()

    if tier != "free" and account.plan_expires_at and now > account.plan_expires_at + timedelta(days=GRACE_DAYS):
        account.plan_tier = "free"
        account.plan_period = None
        account.cycle_started_at = None
        account.cycle_exams_used = 0
        tier = "free"
        changed = True

    if tier != "free":
        if account.cycle_started_at is None:
            account.cycle_started_at = account.plan_started_at or now
            account.cycle_exams_used = 0
            changed = True
        elapsed = now - account.cycle_started_at
        if elapsed >= timedelta(days=CYCLE_DAYS):
            cycles = elapsed.days // CYCLE_DAYS
            account.cycle_started_at = account.cycle_started_at + timedelta(days=CYCLE_DAYS * cycles)
            account.cycle_exams_used = 0
            changed = True

    if changed:
        db.commit()
        db.refresh(account)
    return account


# ── Limits ────────────────────────────────────────────────────────────────────

def effective_limits(account: User) -> Dict[str, Any]:
    plan = get_plan(account.plan_tier)
    max_exams = plan["max_exams"]
    max_students = plan["max_students"]
    if plan["id"] == "enterprise":
        if account.custom_max_exams is not None:
            max_exams = account.custom_max_exams
        if account.custom_max_students is not None:
            max_students = account.custom_max_students
    return {
        "plan": plan,
        "max_exams": max_exams,
        "max_students": max_students,
        "max_questions_per_exam": plan["max_questions_per_exam"],
        "max_duration_minutes": plan["max_duration_minutes"],
        "assistant_seats": plan["assistant_seats"],
        "lifetime_quota": plan["exams_reset"] == "lifetime",
    }


def exams_used(account: User) -> int:
    if get_plan(account.plan_tier)["exams_reset"] == "lifetime":
        return int(account.exams_created_count or 0)
    return int(account.cycle_exams_used or 0)


def _student_window_start(account: User) -> Optional[datetime]:
    """Free plan counts students over its lifetime; paid plans per cycle."""
    if get_plan(account.plan_tier)["exams_reset"] == "lifetime":
        return None
    return account.cycle_started_at


def _student_identity(student_id: Optional[int], student_number: Optional[str]) -> str:
    return f"u:{student_id}" if student_id else f"n:{(student_number or '').strip()}"


def _student_identity_sql():
    """SQL expression matching _student_identity() on both PostgreSQL and SQLite."""
    return case(
        (
            ExamSubmission.student_id.isnot(None),
            literal("u:") + cast(ExamSubmission.student_id, String),
        ),
        else_=literal("n:") + func.coalesce(func.trim(ExamSubmission.student_number), literal("")),
    )


def distinct_students(db: Session, account: User) -> Set[str]:
    member_ids = team_member_ids(db, account)
    q = (
        db.query(ExamSubmission.student_id, ExamSubmission.student_number)
        .join(Question, Question.id == ExamSubmission.question_id)
        .filter(Question.creator_id.in_(member_ids))
    )
    start = _student_window_start(account)
    if start is not None:
        q = q.filter(ExamSubmission.submitted_at >= start)
    return {_student_identity(sid, num) for sid, num in q.distinct().all()}


def distinct_students_count(db: Session, account: User, member_ids: Optional[List[int]] = None) -> int:
    """O(1)-memory SQL COUNT(DISTINCT ...) for high-scale student quota checks."""
    mids = member_ids if member_ids is not None else team_member_ids(db, account)
    id_expr = _student_identity_sql()
    q = (
        db.query(func.count(func.distinct(id_expr)))
        .select_from(ExamSubmission)
        .join(Question, Question.id == ExamSubmission.question_id)
        .filter(Question.creator_id.in_(mids))
    )
    start = _student_window_start(account)
    if start is not None:
        q = q.filter(ExamSubmission.submitted_at >= start)
    return int(q.scalar() or 0)


def consume_exam_slot(db: Session, account: User) -> str:
    """
    Atomically reserve one exam from the account quota.
    Order: monthly/lifetime quota first, then non-expiring bonus packs.
    Returns "plan" or "bonus". Raises QuotaExceeded when nothing is left.
    Caller is responsible for committing.
    """
    if subscription_paused(db, account):
        raise QuotaExceeded(
            "SUBSCRIPTION_PAUSED",
            "اشتراكك موقوف مؤقتًا لحد ما طلب الإلغاء يتراجع — الدعم هيتواصل معاك.",
            "Your subscription is paused while your cancellation request is reviewed — support will contact you.",
        )
    limits = effective_limits(account)
    max_exams = limits["max_exams"]
    counter = User.exams_created_count if limits["lifetime_quota"] else User.cycle_exams_used

    if max_exams == UNLIMITED:
        db.execute(update(User).where(User.id == account.id).values({counter: func.coalesce(counter, 0) + 1}))
        _bump_lifetime(db, account, limits)
        return "plan"

    res = db.execute(
        update(User)
        .where(User.id == account.id, func.coalesce(counter, 0) < max_exams)
        .values({counter: func.coalesce(counter, 0) + 1})
    )
    if res.rowcount:
        _bump_lifetime(db, account, limits)
        return "plan"

    res = db.execute(
        update(User)
        .where(User.id == account.id, func.coalesce(User.bonus_exams, 0) > 0)
        .values(bonus_exams=User.bonus_exams - 1)
    )
    if res.rowcount:
        _bump_lifetime(db, account, limits)
        return "bonus"

    if limits["lifetime_quota"]:
        raise QuotaExceeded(
            "EXAM_QUOTA_EXCEEDED",
            f"خلصت الامتحانات المجانية ({max_exams} امتحانات). اشترك في باقة عشان تكمل.",
            f"Free trial exams used up ({max_exams}). Subscribe to continue.",
            limit=max_exams,
        )
    raise QuotaExceeded(
        "EXAM_QUOTA_EXCEEDED",
        f"خلصت امتحانات الشهر ({max_exams} امتحان). اشتري باقة امتحانات إضافية أو رقّي باقتك.",
        f"Monthly exam quota reached ({max_exams}). Buy an add-on pack or upgrade.",
        limit=max_exams,
    )


def subscription_paused(db: Session, account: User) -> bool:
    """An open or approved cancellation request pauses the lecturer's service (services/cancellations)."""
    from app.models.billing_cancellation import BillingCancellationRequest
    return db.query(BillingCancellationRequest.id).filter(
        BillingCancellationRequest.user_id == account.id,
        BillingCancellationRequest.status.in_(("open", "approved")),
    ).first() is not None


def _bump_lifetime(db: Session, account: User, limits: Dict[str, Any]) -> None:
    """Paid plans still track lifetime usage (useful for analytics & downgrade to free)."""
    if not limits["lifetime_quota"]:
        db.execute(
            update(User)
            .where(User.id == account.id)
            .values(exams_created_count=func.coalesce(User.exams_created_count, 0) + 1)
        )


def check_question_limits(db: Session, account: User, group_size_before: int, duration_minutes: int) -> None:
    limits = effective_limits(account)
    max_q = limits["max_questions_per_exam"]
    if max_q != UNLIMITED and group_size_before >= max_q:
        raise QuotaExceeded(
            "QUESTIONS_PER_EXAM_EXCEEDED",
            f"باقتك بتسمح بـ {max_q} أسئلة بحد أقصى في الامتحان الواحد.",
            f"Your plan allows up to {max_q} questions per exam.",
            limit=max_q,
        )
    max_d = limits["max_duration_minutes"]
    if max_d != UNLIMITED and duration_minutes > max_d:
        raise QuotaExceeded(
            "DURATION_EXCEEDED",
            f"أقصى مدة للإجابة في باقتك {max_d} دقيقة.",
            f"Your plan allows answers up to {max_d} minutes.",
            limit=max_d,
        )


# ── Concurrent exam seats ─────────────────────────────────────────────────────
# The plan's student number = how many students may be IN an exam at the same time.
# A seat is held from "start" until the last answer is submitted (or the exam window ends),
# then it's free again. Finishing an exam never consumes anything.

SEAT_GRACE_MINUTES = 10


def _active_sessions_q(db: Session, account_id: int, now: datetime):
    return db.query(ExamSession).filter(
        ExamSession.account_id == account_id,
        ExamSession.finished.is_(False),
        ExamSession.expires_at > now,
    )


def active_seats(db: Session, account: User) -> int:
    return _active_sessions_q(db, account.id, utcnow()).count()


def _exam_minutes(db: Session, group_token: Optional[str]) -> int:
    if not group_token:
        return 15
    total = (
        db.query(func.coalesce(func.sum(Question.duration_minutes), 0))
        .filter((Question.group_token == group_token) | (Question.exam_token == group_token))
        .scalar()
    )
    return max(1, int(total or 0))


def acquire_exam_seat(
    db: Session, account: User, student_id: Optional[int], student_number: Optional[str],
    group_token: Optional[str],
) -> ExamSession:
    """Hold (or refresh) a seat for this student. Raises 402 when the room is full right now."""
    now = utcnow()
    key = _student_identity(student_id, student_number)[:160]
    window = timedelta(minutes=_exam_minutes(db, group_token) + SEAT_GRACE_MINUTES)

    mine = (
        _active_sessions_q(db, account.id, now)
        .filter(ExamSession.student_key == key)
        .order_by(ExamSession.id.desc())
        .first()
    )
    if mine:
        if group_token and mine.group_token != group_token:
            mine.group_token = group_token
        mine.expires_at = max(mine.expires_at, now + window)
        db.commit()
        return mine

    max_seats = effective_limits(account)["max_students"]
    if max_seats != UNLIMITED and _active_sessions_q(db, account.id, now).count() >= max_seats:
        raise QuotaExceeded(
            "CONCURRENT_LIMIT_REACHED",
            f"الامتحان مليان دلوقتي ({max_seats} طالب بيمتحنوا في نفس الوقت). استنى دقايق وجرّب تاني.",
            f"The exam room is full right now ({max_seats} students at the same time). Wait a few minutes and try again.",
            limit=max_seats,
        )
    seat = ExamSession(account_id=account.id, student_key=key, group_token=group_token,
                       started_at=now, expires_at=now + window, finished=False)
    db.add(seat)
    db.commit()
    return seat


def release_exam_seat(db: Session, account: User, student_id: Optional[int], student_number: Optional[str]) -> None:
    key = _student_identity(student_id, student_number)[:160]
    (
        db.query(ExamSession)
        .filter(ExamSession.account_id == account.id, ExamSession.student_key == key, ExamSession.finished.is_(False))
        .update({ExamSession.finished: True}, synchronize_session=False)
    )
    db.commit()


def check_student_allowed(
    db: Session, account: User, student_id: Optional[int], student_number: Optional[str]
) -> None:
    """Reject NEW students once the account reached its distinct-student limit for the cycle."""
    max_students = effective_limits(account)["max_students"]
    if max_students == UNLIMITED:
        return

    member_ids = team_member_ids(db, account)
    start = _student_window_start(account)

    # Fast indexed point check: if this student already submitted in the current window, allow immediately
    existing_q = (
        db.query(ExamSubmission.id)
        .join(Question, Question.id == ExamSubmission.question_id)
        .filter(Question.creator_id.in_(member_ids))
    )
    if start is not None:
        existing_q = existing_q.filter(ExamSubmission.submitted_at >= start)
    if student_id:
        already = existing_q.filter(ExamSubmission.student_id == student_id).first() is not None
    else:
        norm_num = (student_number or "").strip()
        already = (
            existing_q.filter(
                ExamSubmission.student_id.is_(None),
                func.coalesce(func.trim(ExamSubmission.student_number), "") == norm_num,
            ).first()
            is not None
        )
    if already:
        return

    used_students = distinct_students_count(db, account, member_ids=member_ids)
    if used_students >= max_students:
        raise QuotaExceeded(
            "STUDENT_LIMIT_REACHED",
            f"المدرس وصل للحد الأقصى من الطلاب في باقته ({max_students} طالب). بلّغ المدرس.",
            f"The lecturer's plan reached its student limit ({max_students}). Please contact your lecturer.",
            limit=max_students,
        )


# ── Activation after verified payment ─────────────────────────────────────────

# Statuses a payment never leaves through a callback: a repeated (or late) success never applies it
# again, so it can never extend or create a subscription twice.
FINAL_STATUSES = ("paid", "refunded", "refund_review")


def apply_paid_payment(db: Session, payment: Payment, provider_txn_id: Optional[str] = None) -> bool:
    """
    Mark payment paid and grant the plan / add-on. Idempotent. Returns True if newly applied.

    The one place a payment turns into a subscription, so it is also the last line of defence:
    only a payment confirmed by a gateway (Kashier, after its signed callback) may be
    applied, unless simulated payments are explicitly on in dev/test (never in production).
    """
    if payment.status in FINAL_STATUSES:
        return False
    from app.services import payment_gateways as gw
    if payment.provider not in GATEWAY_PROVIDERS and not gw.sandbox_enabled():
        payment.status = "failed"
        payment.note = "refused: activation without a gateway-confirmed payment is not allowed here"
        db.commit()
        print(f"[Billing] refused to activate payment #{payment.id} (provider={payment.provider!r}) "
              "without a gateway-confirmed payment", flush=True)
        return False
    user = db.query(User).filter(User.id == payment.user_id).first()
    if not user:
        payment.status = "failed"
        payment.note = "user not found"
        db.commit()
        return False
    if user.role not in LECTURER_ROLES:
        # Only lecturer accounts pay (students are free). Money may have been taken, so this is
        # left for an admin to reconcile rather than marked failed — and nothing is activated.
        flag_for_review(db, payment, f"not applied: account role {user.role!r} cannot hold a subscription")
        return False

    now = utcnow()
    refresh_account_state(db, user)

    if payment.kind == "addon":
        user.bonus_exams = int(user.bonus_exams or 0) + int(payment.addon_exams or ADDON_EXAMS_PER_PACK)
    else:
        grant_plan(user, payment.plan_id, payment.period or "monthly", now)

    payment.status = "paid"
    payment.paid_at = now
    if provider_txn_id:
        payment.provider_txn_id = str(provider_txn_id)[:128]
    db.commit()
    db.refresh(user)
    return True


def grant_plan(user: User, plan_id: str, period: str, now: Optional[datetime] = None, months: Optional[int] = None) -> None:
    """Start or extend a plan. Renewing the same active plan extends the expiry date."""
    now = now or utcnow()
    days = (months * 30) if months else BILLING_PERIODS.get(period, BILLING_PERIODS["monthly"])["days"]
    current = (user.plan_tier or "free").lower()
    active = current != "free" and user.plan_expires_at and user.plan_expires_at > now

    if active and current == plan_id:
        user.plan_expires_at = user.plan_expires_at + timedelta(days=days)
    else:
        # New plan or upgrade/downgrade: starts now with a fresh cycle.
        user.plan_tier = plan_id
        user.plan_started_at = now
        user.plan_expires_at = now + timedelta(days=days)
        user.cycle_started_at = now
        user.cycle_exams_used = 0
    user.plan_period = period
    user.plan_updated_at = now.replace(tzinfo=timezone.utc).isoformat()


# ── Pending, reconciliation and refunds ───────────────────────────────────────

# A gateway payment still unconfirmed after this long goes to "review" (reconciliation by an
# admin) — never to "failed": the money may have been taken and only the callback is late.
PENDING_REVIEW_HOURS = 24
# A repeated checkout click returns the payment page already created, while it is this fresh.
# Kept at the Kashier session lifetime (payment_gateways.KASHIER_SESSION_SECONDS).
CHECKOUT_REUSE_SECONDS = 3600


def log_billing(message: str) -> None:
    print(f"[Billing] {message}", flush=True)


def _append_note(payment: Payment, text: str) -> None:
    payment.note = (f"{payment.note} | {text}" if payment.note else text)[:2000]


def move_stale_to_review(db: Session, user_id: Optional[int] = None) -> int:
    """Pending gateway payments older than PENDING_REVIEW_HOURS -> review. Idempotent."""
    cutoff = utcnow() - timedelta(hours=PENDING_REVIEW_HOURS)
    q = db.query(Payment).filter(
        Payment.status == "pending",
        Payment.provider.in_(GATEWAY_PROVIDERS),
        Payment.created_at < cutoff,
    )
    if user_id is not None:
        q = q.filter(Payment.user_id == user_id)
    rows = q.all()
    now = utcnow()
    for p in rows:
        p.status = "review"
        p.review_at = now
        log_billing(f"payment {p.reference} unconfirmed for over {PENDING_REVIEW_HOURS}h -> review (reconcile with the gateway)")
    if rows:
        db.commit()
    return len(rows)


def flag_for_review(db: Session, payment: Payment, detail: str) -> None:
    """
    Something about this payment needs a person (money may have been taken but it can't be
    applied as is). An unresolved payment moves to review; a closed one keeps its status (so it
    can't take a second open slot) and only gets the note. Always logged.
    """
    if payment.status in OPEN_STATUSES:
        payment.status = "review"
        payment.review_at = payment.review_at or utcnow()
    _append_note(payment, f"NEEDS REVIEW: {detail}")
    db.commit()
    log_billing(f"payment {payment.reference}: {detail} -> needs admin review")


def open_payment(db: Session, account_id: int) -> Optional[Payment]:
    """The account's unresolved gateway payment (pending / review), if any."""
    return (
        db.query(Payment)
        .filter(
            Payment.user_id == account_id,
            Payment.status.in_(OPEN_STATUSES),
            Payment.provider.in_(GATEWAY_PROVIDERS),
        )
        .order_by(Payment.id.desc())
        .first()
    )


def end_subscription(user: User, now: Optional[datetime] = None) -> None:
    """Back to the free plan now (no grace period): used when the subscription is refunded."""
    now = now or utcnow()
    user.plan_tier = "free"
    user.plan_period = None
    user.plan_expires_at = now
    user.cycle_started_at = None
    user.cycle_exams_used = 0
    user.plan_updated_at = now.replace(tzinfo=timezone.utc).isoformat()


def reverse_payment(db: Session, payment: Payment, refunded_minor: Optional[int], source: str,
                    when: Optional[datetime] = None) -> str:
    """
    A FULL refund / void of this payment is confirmed: take back what it granted (the days of
    its plan period, or its add-on exams) and mark it refunded. Idempotent. Never moves money.
    """
    if payment.status == "refunded":
        return "already_refunded"
    if payment.status not in ("paid", "refund_review"):
        # Nothing was granted. A reversal confirmed by the gateway also settles an unresolved
        # payment: it is not paid, so the lecturer may check out again.
        _append_note(payment, f"refund/void reported by {source} while {payment.status}")
        if payment.status in OPEN_STATUSES:
            payment.status = "failed"
        db.commit()
        log_billing(f"payment {payment.reference}: refund/void reported by {source} on an unpaid payment — nothing to take back")
        return "not_paid"
    user = db.query(User).filter(User.id == payment.user_id).first()
    if user:
        refresh_account_state(db, user)
        if payment.kind == "addon":
            remove = int(payment.addon_exams or ADDON_EXAMS_PER_PACK)
            have = int(user.bonus_exams or 0)
            user.bonus_exams = max(0, have - remove)
            if have < remove:
                log_billing(f"payment {payment.reference}: {remove - have} refunded add-on exams were already used")
        elif (user.plan_tier or "free").lower() == payment.plan_id and user.plan_expires_at:
            days = BILLING_PERIODS.get(payment.period or "monthly", BILLING_PERIODS["monthly"])["days"]
            new_expiry = user.plan_expires_at - timedelta(days=days)
            if new_expiry <= utcnow():
                end_subscription(user)
            else:
                user.plan_expires_at = new_expiry
        else:
            log_billing(f"payment {payment.reference}: refunded plan {payment.plan_id!r} is no longer the "
                        "account's plan — nothing left to take back")
    payment.status = "refunded"
    payment.refunded_at = when or utcnow()
    payment.refunded_amount_minor = refunded_minor
    _append_note(payment, f"refunded ({source})")
    db.commit()
    log_billing(f"payment {payment.reference}: full refund confirmed by {source} — entitlement removed")
    return "refunded"


def mark_refund_review(db: Session, payment: Payment, detail: str) -> str:
    """A partial or unclear refund: keep the subscription, flag it for an admin, log it."""
    if payment.status == "paid":
        payment.status = "refund_review"
        _append_note(payment, detail)
        db.commit()
    log_billing(f"payment {payment.reference}: {detail} -> needs admin review")
    return payment.status


# ── Status payload ────────────────────────────────────────────────────────────

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def billing_status(db: Session, user: User) -> Dict[str, Any]:
    account = get_billing_account(db, user)
    refresh_account_state(db, account)
    limits = effective_limits(account)
    plan = limits["plan"]
    used = exams_used(account)
    member_ids = team_member_ids(db, account)
    students_count = distinct_students_count(db, account, member_ids=member_ids)

    # Single SQL GROUP BY aggregation for per-exam student counts & total submissions (O(1) Python RAM)
    group_expr = func.coalesce(Question.group_token, Question.exam_token)
    id_expr = _student_identity_sql()
    agg_rows = (
        db.query(
            group_expr.label("grp"),
            func.count(ExamSubmission.id).label("sub_count"),
            func.count(func.distinct(id_expr)).label("stu_count"),
        )
        .select_from(ExamSubmission)
        .join(Question, Question.id == ExamSubmission.question_id)
        .filter(Question.creator_id.in_(member_ids))
        .group_by(group_expr)
        .all()
    )
    exam_student_counts: Dict[str, int] = {str(grp): int(stu_cnt) for grp, _, stu_cnt in agg_rows if grp}
    total_submissions = sum(int(sub_cnt) for _, sub_cnt, _ in agg_rows)

    max_exams = limits["max_exams"]
    cycle_resets_at = (
        account.cycle_started_at + timedelta(days=CYCLE_DAYS)
        if account.cycle_started_at and not limits["lifetime_quota"] else None
    )
    team = [
        {"id": m.id, "email": m.email, "full_name": m.full_name}
        for m in db.query(User).filter(User.owner_id == account.id).all()
    ]

    return {
        "plan": plan,
        "plan_tier": plan["id"],
        "plan_period": account.plan_period,
        "plan_updated_at": account.plan_updated_at or _iso(account.plan_started_at),
        "plan_started_at": _iso(account.plan_started_at),
        "plan_expires_at": _iso(account.plan_expires_at),
        "is_team_member": account.id != user.id,
        "billing_owner": {"id": account.id, "email": account.email} if account.id != user.id else None,
        "usage": {
            "exams_used": used,
            "exams_limit": max_exams if max_exams != UNLIMITED else 9999,
            "exams_remaining": (max(0, max_exams - used) if max_exams != UNLIMITED else 9999),
            "exams_quota_type": plan["exams_reset"],
            "bonus_exams": int(account.bonus_exams or 0),
            "cycle_started_at": _iso(account.cycle_started_at),
            "cycle_resets_at": _iso(cycle_resets_at),
            "students_used": active_seats(db, account),
            "students_limit_type": "concurrent",
            "distinct_students": students_count,
            "students_limit": limits["max_students"],
            "max_students_per_exam": plan["max_students_per_exam"],
            "max_questions_per_exam": limits["max_questions_per_exam"],
            "max_duration_minutes": limits["max_duration_minutes"],
            "assistant_seats": limits["assistant_seats"],
            "peak_students_in_single_exam": max(exam_student_counts.values(), default=0),
            "total_submissions": total_submissions,
            "exam_student_counts": exam_student_counts,
        },
        "team": team,
        "all_plans": public_plans(),
    }
