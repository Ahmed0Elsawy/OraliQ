from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.models.exam_assignment import ExamAssignment
from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User
from app.schemas.question import QuestionCreate, QuestionOut, QuestionPublicOut
from app.services import billing_service as bs
from app.services import service_pause

router = APIRouter()


# ── GET all questions (lecturer sees only their own) ──────────────────────────
@router.get("/", response_model=List[QuestionOut])
def read_questions(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role in ["lecturer", "hr", "admin"]:
        service_pause.ensure_lecturer_active(db, current_user)
        return db.query(Question).filter(Question.creator_id == current_user.id).all()
    return []


# ── POST create question (lecturer only — enforces subscription plan quota) ───
@router.post("/", response_model=QuestionOut)
def create_question(
    *,
    db: Session = Depends(deps.get_db),
    question_in: QuestionCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    service_pause.ensure_lecturer_active(db, current_user)
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Only lecturers can create questions")

    if question_in.duration_minutes is None or question_in.duration_minutes < 1:
        raise HTTPException(status_code=400, detail="duration_minutes must be at least 1")

    # Billing account (assistants consume their owner's quota) + monthly cycle maintenance
    account = bs.get_billing_account(db, current_user)
    bs.refresh_account_state(db, account)
    team_ids = set(bs.team_member_ids(db, account))

    is_new_exam_group = True
    group_size_before = 0
    if question_in.group_token:
        group_questions = (
            db.query(Question).filter(Question.group_token == question_in.group_token).all()
        )
        if group_questions:
            # Existing exam: only the owner's team may add to it
            if any(q.creator_id not in team_ids for q in group_questions):
                raise HTTPException(status_code=403, detail="Not authorized to add to this exam group")
            is_new_exam_group = False
            group_size_before = len(group_questions)

            # Block adding/replacing questions inside an exam that already has student submissions,
            # assignments, or had questions deleted to recycle the link as a new exam.
            group_q_ids = [q.id for q in group_questions]
            max_prev_order = max(((q.order_index or 0) for q in group_questions), default=-1)
            had_deleted_questions = max_prev_order >= len(group_questions)
            has_submissions = (
                db.query(ExamSubmission.id)
                .filter(ExamSubmission.question_id.in_(group_q_ids))
                .first()
                is not None
            )
            has_assignments = (
                db.query(ExamAssignment.id)
                .filter(ExamAssignment.question_id.in_(group_q_ids))
                .first()
                is not None
            )
            if has_submissions or has_assignments or had_deleted_questions:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "لا يمكن استبدال أو إضافة أسئلة داخل امتحان تم تعديله أو مشاركته مع الطلاب "
                        "(لمنع إعادة استخدام نفس الرابط كامتحان جديد). يرجى الضغط على «امتحان جديد»."
                    ),
                )

    # Plan limits: questions per exam + answer duration (402 with upgrade code)
    bs.check_question_limits(db, account, group_size_before, question_in.duration_minutes)

    try:
        if is_new_exam_group:
            bs.consume_exam_slot(db, account)  # monthly quota first, then non-expiring add-on packs

        # The attempt limit belongs to the exam: a question added to an existing exam takes the
        # exam's value, whatever the request says.
        max_attempts = question_in.max_attempts
        results_policy = question_in.results_policy
        results_published_at = results_published_by = None
        if not is_new_exam_group:
            leader = min(group_questions, key=lambda q: (q.order_index or 0, q.id))
            max_attempts = leader.max_attempts or 1
            results_policy = leader.results_policy or "manual"   # also the exam's, not per question
            results_published_at, results_published_by = leader.results_published_at, leader.results_published_by
        question = Question(
            text=question_in.text,
            model_answer=question_in.model_answer,
            keywords=question_in.keywords,
            difficulty=question_in.difficulty,
            category=question_in.category,
            duration_minutes=question_in.duration_minutes,
            max_attempts=max_attempts,
            results_policy=results_policy,
            results_published_at=results_published_at,
            results_published_by=results_published_by,
            creator_id=current_user.id,
        )
        db.add(question)
        db.flush()

        if question_in.group_token:
            question.group_token = question_in.group_token
            count = db.query(Question).filter(Question.group_token == question_in.group_token).count()
            question.order_index = count - 1
        else:
            question.group_token = question.exam_token
            question.order_index = 0

        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(question)
    return question


# ── DELETE question (only creator — does NOT refund consumed exam quota) ──────
@router.delete("/{question_id}", status_code=204)
def delete_question(
    question_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> None:
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if question.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your question")
    service_pause.ensure_lecturer_active(db, current_user)

    # Block deleting questions from an exam that already has student submissions
    # so lecturers cannot wipe questions and reuse the same exam link for a new exam.
    grp = question.group_token or question.exam_token
    grp_questions = db.query(Question).filter(Question.group_token == grp).all()
    grp_q_ids = [q.id for q in grp_questions] or [question.id]
    has_submissions = (
        db.query(ExamSubmission.id)
        .filter(ExamSubmission.question_id.in_(grp_q_ids))
        .first()
        is not None
    )
    if has_submissions:
        raise HTTPException(
            status_code=403,
            detail="لا يمكن حذف أو تعديل أسئلة امتحان قام الطلاب بالإجابة عليه بالفعل حفاظاً على سجل الدرجات ومنع إعادة استخدام الرابط.",
        )

    # Mark remaining questions in the group so deleted slots cannot be refilled to recycle the exam link
    remaining = [q for q in grp_questions if q.id != question.id]
    if remaining:
        max_idx = max((q.order_index or 0) for q in grp_questions)
        remaining[-1].order_index = max(max_idx, len(remaining))

    # Preserve cumulative count before deleting so deleting an exam NEVER refunds quota
    existing_questions = db.query(Question).filter(Question.creator_id == current_user.id).all()
    distinct_groups = {q.group_token or q.exam_token for q in existing_questions}
    current_user.exams_created_count = max(
        getattr(current_user, "exams_created_count", 0) or 0,
        len(distinct_groups),
    )

    db.delete(question)
    db.commit()


# ── GET by exam token (PUBLIC — sanitized: omits model_answer & keywords) ───
@router.get("/by-token/{token}", response_model=QuestionPublicOut)
def get_question_by_token(
    token: str,
    db: Session = Depends(deps.get_db),
) -> Any:
    question = db.query(Question).filter(Question.exam_token == token).first()
    if not question:
        raise HTTPException(status_code=404, detail="Exam not found")
    service_pause.ensure_exam_available(db, question)
    return question


# ── GET all questions in a group (PUBLIC — sanitized: omits model_answer & keywords) ──
@router.get("/by-group/{group_token}", response_model=List[QuestionPublicOut])
def get_questions_by_group(
    group_token: str,
    db: Session = Depends(deps.get_db),
) -> Any:
    questions = (
        db.query(Question)
        .filter(Question.group_token == group_token)
        .order_by(Question.order_index)
        .all()
    )
    if not questions:
        raise HTTPException(status_code=404, detail="Exam group not found")
    service_pause.ensure_exam_available(db, questions[0])
    return questions
