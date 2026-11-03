"""
When a student may see the grade of their answer (H6) — decided here, for every endpoint.

Each exam (question group) has a results_policy:
  * immediate — an answer's grade becomes visible to its student the moment grading completes;
  * manual    — grades stay hidden until the exam's lecturer (or an admin) publishes the results.

Per answer, ExamSubmission.grade_visible remains the switch the student-facing endpoints obey
(it is what "My grades" always filtered on, and what the lecturer's per-answer publish sets):
the worker sets it when grading completes if the exam is immediate or already published, and
publishing an exam sets it on every graded answer of that exam. A student sees a grade only when
grade_visible is set AND grading has completed. Until then every grading output — scores,
transcript, reports, identity/integrity details — is blanked in whatever the endpoint returns;
the student still learns that the answer was received and whether grading is finished.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Type

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User
from app.schemas.exam_submission import ExamSubmissionOut

POLICIES = ("manual", "immediate")
GRADING_OUTPUTS = (
    "transcript", "nlp_score", "facial_score", "speech_score", "voice_score", "face_score",
    "overall_score", "cheat_report", "fluency_report", "face_verification", "face_checks",
    "integrity_status", "client_alerts",
)


def exam_key(question: Question) -> str:
    return question.group_token or question.exam_token


def results_released(question: Optional[Question]) -> bool:
    """True when a newly graded answer of this exam may be shown straight away."""
    if question is None:
        return False
    return question.results_policy == "immediate" or question.results_published_at is not None


def is_exam_staff(user: User, question: Optional[Question]) -> bool:
    """The exam's own lecturer, or an admin (the same rule as every other result view)."""
    return user.role == "admin" or (question is not None and question.creator_id == user.id)


def student_may_see(submission: ExamSubmission) -> bool:
    return bool(submission.grade_visible) and submission.grading_status == "completed"


def present(submission: ExamSubmission, viewer: User, schema: Type[ExamSubmissionOut] = ExamSubmissionOut,
            question: Optional[Question] = None, **extra: Any):
    """The submission as `viewer` may see it: complete for exam staff, grading blanked for a student
    until the result is released."""
    out = schema.model_validate(submission)
    for k, v in extra.items():
        setattr(out, k, v)
    question = question if question is not None else submission.question
    if is_exam_staff(viewer, question):
        out.result_visible = student_may_see(submission)
        return out
    visible = student_may_see(submission)
    out.result_visible = visible
    if not visible:
        for field in GRADING_OUTPUTS:
            setattr(out, field, None)
    return out


def visible_on_completion(db: Session, submission_id: int) -> int:
    """grade_visible to store when the worker finishes grading this submission."""
    q = (
        db.query(Question)
        .join(ExamSubmission, ExamSubmission.question_id == Question.id)
        .filter(ExamSubmission.id == submission_id)
        .first()
    )
    return 1 if results_released(q) else 0


def publish(db: Session, user: User, token: str) -> Dict[str, Any]:
    """
    Publishes an exam's results. Only its lecturer or an admin; idempotent and race-safe: the
    first call stamps the exam (one conditional UPDATE), later or concurrent calls change nothing.
    Every graded answer of the exam becomes visible to its own student; answers still being
    graded become visible when they finish (the exam is published by then).
    """
    q = db.query(Question).filter((Question.group_token == token) | (Question.exam_token == token)).first()
    if q is None or not is_exam_staff(user, q):
        # Same answer for "no such exam" and "not yours".
        raise HTTPException(status_code=404, detail="Exam not found")
    key = exam_key(q)
    if q.results_policy == "immediate":
        raise HTTPException(status_code=409, detail={
            "code": "RESULTS_ARE_IMMEDIATE",
            "message": "نتائج الامتحان ده بتظهر للطلاب تلقائياً بعد التصحيح.",
            "message_en": "This exam shows each grade automatically once it is graded.",
        })
    now = datetime.utcnow()
    in_exam = (Question.group_token == key) | (Question.exam_token == key)
    stamped = db.execute(
        update(Question).where(in_exam, Question.results_published_at.is_(None))
        .values(results_published_at=now, results_published_by=user.id)
    ).rowcount
    question_ids = db.query(Question.id).filter(in_exam)
    released = db.execute(
        update(ExamSubmission)
        .where(ExamSubmission.question_id.in_(question_ids), ExamSubmission.grading_status == "completed")
        .values(grade_visible=1)
    ).rowcount if stamped else 0
    db.commit()
    q = db.query(Question).filter(in_exam).first()
    return {
        "ok": True,
        "already_published": not stamped,
        "published_at": q.results_published_at.isoformat() + "Z" if q.results_published_at else None,
        "published_by": q.results_published_by,
        "answers_released": released,
    }
