"""
Server-side exam sittings: who may sit an exam, when it started, when it ends, and how many
attempts are left. The browser's clock and the browser's "started_at" play no part.

  * A sitting starts at GET /exams/access-check (the web and mobile apps both call it before an
    exam). Its deadline is fixed then: the exam's total question time plus
    EXAM_SESSION_GRACE_MINUTES (default 3, for reading the instructions). Opening the exam again
    returns the same sitting — a reload never restarts the clock.
  * An answer is accepted only inside the user's active sitting of that exam, up to
    EXAM_SUBMIT_GRACE_SECONDS (default 90) past the deadline for an upload already under way.
  * Each sitting is one attempt; the exam's max_attempts (set by the lecturer) caps them, and each
    question can be answered once per sitting. Answers from before sittings existed count too.
  * Students must have their face and voice enrolled (until now only the exam page checked).
"""
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.exam_sitting import ExamSitting
from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.isdigit() else default


def now() -> datetime:
    return datetime.utcnow()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def refuse(status: int, code: str, ar: str, en: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": ar, "message_en": en, **extra})


def exam_questions(db: Session, key: str) -> List[Question]:
    return (
        db.query(Question)
        .filter((Question.group_token == key) | (Question.exam_token == key))
        .order_by(Question.order_index, Question.id)
        .all()
    )


def exam_key_of(question: Question) -> str:
    return question.group_token or question.exam_token


def max_attempts_of(questions: List[Question]) -> int:
    return max(1, int(questions[0].max_attempts or 1)) if questions else 1


def require_enrollment(user: User) -> None:
    """Students sit exams only with face and voice enrolled (the identity checks need both)."""
    if user.role != "student":
        return   # lecturers previewing their own exam, as the exam page already allowed
    from app.api.endpoints.voice import _has_voiceprint
    from app.services.exam_evidence import has_faceprint
    if not (_has_voiceprint(user) and has_faceprint(user)):
        raise refuse(403, "BIOMETRICS_REQUIRED",
                     "لازم تسجّل بصمة الوجه والصوت قبل ما تبدأ الامتحان.",
                     "Register your face and voice before starting the exam.")


def answers_count(db: Session, user_id: int, question_id: int) -> int:
    return (
        db.query(func.count(ExamSubmission.id))
        .filter(ExamSubmission.student_id == user_id, ExamSubmission.question_id == question_id)
        .scalar() or 0
    )


def _expire_if_over(db: Session, sitting: ExamSitting, at: datetime) -> ExamSitting:
    grace = timedelta(seconds=_int_env("EXAM_SUBMIT_GRACE_SECONDS", 90))
    if sitting.status == "active" and at > sitting.deadline_at + grace:
        db.execute(
            update(ExamSitting).where(ExamSitting.id == sitting.id, ExamSitting.status == "active")
            .values(status="expired", active_slot=None, completed_at=sitting.deadline_at)
        )
        db.commit()
        db.refresh(sitting)
    return sitting


def active_sitting(db: Session, user: User, key: str, at: Optional[datetime] = None) -> Optional[ExamSitting]:
    at = at or now()
    s = (
        db.query(ExamSitting)
        .filter(ExamSitting.user_id == user.id, ExamSitting.exam_key == key, ExamSitting.status == "active")
        .first()
    )
    if s is None:
        return None
    s = _expire_if_over(db, s, at)
    return s if s.status == "active" else None


def answered_in(db: Session, sitting: ExamSitting) -> List[int]:
    return [qid for (qid,) in db.query(ExamSubmission.question_id)
            .filter(ExamSubmission.exam_sitting_id == sitting.id).all()]


def check_can_start(db: Session, user: User, key: str, questions: Optional[List[Question]] = None) -> int:
    """Raises unless the user may start a new sitting of this exam; returns sittings used so far."""
    questions = questions if questions is not None else exam_questions(db, key)
    require_enrollment(user)
    limit = max_attempts_of(questions)
    used = db.query(func.count(ExamSitting.id)).filter(
        ExamSitting.user_id == user.id, ExamSitting.exam_key == key).scalar() or 0
    open_questions = [q for q in questions if answers_count(db, user.id, q.id) < (q.max_attempts or 1)]
    if used >= limit or not open_questions:
        raise refuse(409, "ATTEMPTS_EXHAUSTED",
                     "استخدمت كل المحاولات المسموحة للامتحان ده.",
                     "You have used all the attempts allowed for this exam.", max_attempts=limit)
    return used


def start_or_resume(db: Session, user: User, key: str) -> ExamSitting:
    """The user's active sitting of this exam, or a new one if attempts remain."""
    questions = exam_questions(db, key)
    if not questions:
        raise HTTPException(status_code=404, detail="Exam not found")
    existing = active_sitting(db, user, key)
    if existing is not None:
        return existing

    used = check_can_start(db, user, key, questions)
    start = now()
    minutes = sum(int(q.duration_minutes or 0) for q in questions) + _int_env("EXAM_SESSION_GRACE_MINUTES", 3)
    sitting = ExamSitting(user_id=user.id, exam_key=key, attempt_no=used + 1, status="active",
                          started_at=start, deadline_at=start + timedelta(minutes=minutes), active_slot=1)
    db.add(sitting)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request started it first (one active sitting / one attempt number per user).
        db.rollback()
        winner = active_sitting(db, user, key)
        if winner is None:
            raise refuse(409, "SESSION_CONFLICT", "حاول تاني.", "Please try again.")
        return winner
    db.refresh(sitting)
    return sitting


def complete_if_done(db: Session, sitting: ExamSitting) -> None:
    """Closes the sitting once every question of the exam has an answer in it."""
    total = len(exam_questions(db, sitting.exam_key))
    if total and len(set(answered_in(db, sitting))) >= total:
        db.execute(
            update(ExamSitting).where(ExamSitting.id == sitting.id, ExamSitting.status == "active")
            .values(status="completed", active_slot=None, completed_at=now())
        )
        db.commit()


def describe(db: Session, sitting: ExamSitting, questions: Optional[List[Question]] = None) -> Dict[str, Any]:
    questions = questions if questions is not None else exam_questions(db, sitting.exam_key)
    at = now()
    return {
        "id": sitting.id,
        "status": sitting.status,
        "attempt_no": sitting.attempt_no,
        "max_attempts": max_attempts_of(questions),
        "started_at": _iso(sitting.started_at),
        "deadline_at": _iso(sitting.deadline_at),
        "server_now": _iso(at),
        "remaining_seconds": max(0, int((sitting.deadline_at - at).total_seconds())),
        "answered_question_ids": sorted(set(answered_in(db, sitting))),
    }


def check_submission(db: Session, user: User, question: Question) -> Dict[str, Any]:
    """
    Everything that must hold before an answer is stored and queued. Returns the sitting and the
    attempt number to record; raises a coded 403/409 otherwise. Called inside the submit request,
    so direct API calls get exactly the same checks as the apps.
    """
    require_enrollment(user)
    key = exam_key_of(question)
    sitting = active_sitting(db, user, key)
    if sitting is None:
        expired = db.query(ExamSitting.id).filter(
            ExamSitting.user_id == user.id, ExamSitting.exam_key == key, ExamSitting.status == "expired").first()
        if expired:
            raise refuse(409, "SESSION_EXPIRED", "وقت الامتحان خلص، والإجابة دي ماتسجلتش.",
                         "The exam time is over; this answer was not accepted.")
        raise refuse(409, "NO_ACTIVE_SESSION", "افتح الامتحان من رابطه الأول عشان تبدأ جلسة.",
                     "Open the exam from its link first to start a session.")
    if question.id in answered_in(db, sitting):
        raise refuse(409, "ALREADY_ANSWERED", "السؤال ده اتجاوب بالفعل في المحاولة دي.",
                     "This question was already answered in this attempt.")
    count = answers_count(db, user.id, question.id)
    if count >= (question.max_attempts or 1):
        raise refuse(409, "ATTEMPTS_EXHAUSTED", "استخدمت كل المحاولات المسموحة للسؤال ده.",
                     "You have used all the attempts allowed for this question.")
    return {"sitting": sitting, "attempt_no": count + 1}
