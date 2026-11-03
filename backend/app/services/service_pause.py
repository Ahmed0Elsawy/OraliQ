"""
A lecturer's service is paused while their cancellation request is open or approved (H8,
services/cancellations.py). While paused:

  * the lecturer (and the assistants on their team) can't use the exam services of the account:
    questions, assigning, students, results, attendance, publishing, re-grading, re-enrolment;
  * students can't open, start or resume that lecturer's exams, send answers or face checks for
    them, or read their results / grading status.

Nothing is deleted or changed: the exams, answers, grades and sittings stay as they are, and
everything is reachable again once the request is resolved (the lecturer stays). Billing pages and
the user's own profile stay reachable. Enforced here, on the server, for every endpoint that
touches those exams — the frontend only shows the refusal.
"""
from typing import Optional, Set

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing_cancellation import BillingCancellationRequest
from app.models.question import Question
from app.models.user import User

PAUSED_STATUSES = ("open", "approved")
_LECTURER_ROLES = ("lecturer", "hr", "admin")


def paused_account_ids(db: Session) -> Set[int]:
    """Billing owners whose service is paused right now."""
    return {uid for (uid,) in db.query(BillingCancellationRequest.user_id)
            .filter(BillingCancellationRequest.status.in_(PAUSED_STATUSES)).distinct().all()}


def paused_creator_ids(db: Session) -> Set[int]:
    """Every account whose exams are paused: the paused owners and the assistants on their team."""
    owners = paused_account_ids(db)
    if not owners:
        return set()
    team = {uid for (uid,) in db.query(User.id).filter(User.owner_id.in_(owners)).all()}
    return owners | team


def creator_paused(db: Session, creator_id: Optional[int]) -> bool:
    if not creator_id:
        return False
    owners = paused_account_ids(db)
    if not owners:
        return False
    if creator_id in owners:
        return True
    owner_id = db.query(User.owner_id).filter(User.id == creator_id).scalar()
    return bool(owner_id and owner_id in owners)


def ensure_lecturer_active(db: Session, user: User) -> None:
    """403 for a lecturer (or team assistant) whose account is paused."""
    if user.role in _LECTURER_ROLES and creator_paused(db, user.id):
        raise HTTPException(status_code=403, detail={
            "code": "SERVICE_PAUSED",
            "message": "خدمات حسابك موقوفة مؤقتًا لحد ما طلب الإلغاء يتراجع — الدعم هيتواصل معاك. بياناتك وامتحاناتك محفوظة.",
            "message_en": "Your account's services are paused while your cancellation request is reviewed — support will contact you. Your data and exams are kept.",
        })


def ensure_exam_available(db: Session, question: Optional[Question]) -> None:
    """403 when the exam belongs to a paused lecturer (for students and anyone else)."""
    if question is not None and creator_paused(db, question.creator_id):
        raise HTTPException(status_code=403, detail={
            "code": "EXAM_UNAVAILABLE",
            "message": "الامتحان ده مش متاح حاليًا. تواصل مع المحاضر بتاعك.",
            "message_en": "This exam isn't available right now. Please contact your lecturer.",
        })


def ensure_exam_token_available(db: Session, token: Optional[str]) -> None:
    token = (token or "").strip()[:128]
    if token:
        q = db.query(Question).filter((Question.group_token == token) | (Question.exam_token == token)).first()
        ensure_exam_available(db, q)
