from typing import Any, List, Optional
import anyio
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File, Form
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
import os, time

from app.api import deps
from app.core.uploads import MAX_AUDIO_BYTES, read_upload_capped
from app.core.plans import get_plan
from app.services import billing_service as bs
from app.services import grading_queue as gq
from app.services import student_access
from app.services import exam_evidence
from app.services import exam_sessions
from app.services import results_visibility
from app.services import service_pause
from app.models.exam_submission import ExamSubmission
from app.models.exam_assignment import ExamAssignment
from app.models.grading_job import GradingJob
from app.models.question import Question
from app.models.user import User
from app.schemas.exam_submission import ExamSubmissionCreate, ExamSubmissionOut, GradingStatusOut
from app.schemas.exam_assignment import ExamAssignmentCreate, AssignedExamOut

router = APIRouter()

ALLOWED_AUDIO_EXTS = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".mp4"}


def _safe_audio_suffix(filename: Optional[str]) -> str:
    if not filename:
        return ".webm"
    raw_ext = os.path.splitext(os.path.basename(filename))[1].lower()
    return raw_ext if raw_ext in ALLOWED_AUDIO_EXTS else ".webm"


# ── POST assign exam to student (lecturer) ────────────────────────────────────
@router.post("/assign")
def assign_exam(
    *,
    db: Session = Depends(deps.get_db),
    assignment_in: ExamAssignmentCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)

    question = db.query(Question).filter(Question.id == assignment_in.question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if question.creator_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to assign this question")

    # Only a student who already took one of this lecturer's exams (or anyone, for an admin). A
    # missing id, a non-student and an unrelated student all get the same answer, so ids can't be
    # probed; and assigning never creates the relationship by itself.
    if not student_access.can_access_student(db, current_user, assignment_in.student_id):
        raise HTTPException(status_code=404, detail="Student not found")

    existing = db.query(ExamAssignment).filter(
        ExamAssignment.question_id == assignment_in.question_id,
        ExamAssignment.student_id == assignment_in.student_id,
        ExamAssignment.status == "pending",
    ).first()
    if existing:
        return {"ok": True, "assignment_id": existing.id, "message": "Already assigned"}

    assignment = ExamAssignment(
        question_id=assignment_in.question_id,
        student_id=assignment_in.student_id,
        assigned_by=current_user.id,
        assigned_at=datetime.utcnow(),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return {"ok": True, "assignment_id": assignment.id}


# ── GET my assigned exams (student) ──────────────────────────────────────────
@router.get("/my-assignments", response_model=List[AssignedExamOut])
def get_my_assignments(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    assignments = (
        db.query(ExamAssignment)
        .options(joinedload(ExamAssignment.question), joinedload(ExamAssignment.lecturer))
        .filter(
            ExamAssignment.student_id == current_user.id,
            ExamAssignment.status == "pending",
        )
        .all()
    )

    paused = service_pause.paused_creator_ids(db)
    result = []
    for a in assignments:
        if a.question is not None and a.question.creator_id in paused:
            continue
        result.append(AssignedExamOut(
            id=a.id,
            question_id=a.question_id,
            assigned_at=a.assigned_at,
            status=a.status,
            question_text=None,
            question_category=a.question.category if a.question else None,
            question_difficulty=a.question.difficulty if a.question else None,
            exam_token=a.question.exam_token if a.question else None,
            assigned_by_name=a.lecturer.full_name if a.lecturer else "Unknown",
        ))
    return result


# ── GET all students (for lecturer to pick from) ──────────────────────────────
@router.get("/students", response_model=List[dict])
def get_students(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)
    # Only students who took one of this lecturer's exams — never the platform's student list
    # (anyone can sign up as a lecturer), and no query parameter can widen it. The e-mail stays: it
    # is how a lecturer tells their students apart and how the mobile app's "send by e-mail" finds
    # one, and it only ever covers students who chose to sit this lecturer's exam.
    students = student_access.accessible_students(db, current_user).order_by(User.id.desc()).limit(2000).all()
    return [{
        "id": s.id,
        "full_name": s.full_name,
        "email": s.email,
        "has_voiceprint": bool(s.voice_embedding and len(s.voice_embedding) > 10),
        "has_faceprint": bool(s.face_embedding and len(s.face_embedding) > 10),
        "voice_locked": bool(s.voice_locked),
        "face_locked": bool(s.face_locked),
        "voice_reenroll_allowed": bool(s.voice_reenroll_allowed),
    } for s in students]


# ── GET pre-exam access check (student) ──────────────────────────────────────
# Call before the student starts recording so a full student quota is reported up-front.
@router.get("/access-check/{group_token}")
def exam_access_check(
    group_token: str,
    student_number: Optional[str] = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    question = (
        db.query(Question)
        .filter((Question.group_token == group_token) | (Question.exam_token == group_token))
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Exam not found")
    service_pause.ensure_exam_available(db, question)
    # Starts — or, after a reload or a dropped connection, resumes — the server-timed sitting
    # (services/exam_sessions.py). Eligibility (face/voice enrolled, attempts left) is checked
    # before a seat is taken; the seat check (plan's concurrent students) still answers 402.
    key = exam_sessions.exam_key_of(question)
    sitting = exam_sessions.active_sitting(db, current_user, key)
    if sitting is None:
        exam_sessions.check_can_start(db, current_user, key)
    creator = db.query(User).filter(User.id == question.creator_id).first() if question.creator_id else None
    if creator is not None:
        account = bs.get_billing_account(db, creator)
        bs.refresh_account_state(db, account)
        bs.acquire_exam_seat(db, account, current_user.id, None, key)
    if sitting is None:
        sitting = exam_sessions.start_or_resume(db, current_user, key)
    return {"allowed": True, "session": exam_sessions.describe(db, sitting)}


# ── POST submit exam: store the answer + queue it for grading (Plan Capacity & Priority) ──
# Grading (Whisper + SBERT + voice check) no longer runs inside this request: it took up to
# minutes per answer, a class finishing together queued past the browser's timeout, and a retry
# of a slow request graded the same recording again. The answer and its grading job are now
# written in one transaction and the request returns at once (202); the worker process
# (app/worker.py) grades it and the exam room polls /submissions/{id}/grading for the result.
def _parse_client_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _existing_for_key(db: Session, key: str, user: User) -> Optional[ExamSubmission]:
    existing = db.query(ExamSubmission).filter(ExamSubmission.submission_key == key).first()
    if existing and existing.student_id != user.id:
        # A submission_key is not a capability: someone else's key must not return their grade.
        raise HTTPException(status_code=409, detail="Duplicate submission key")
    return existing


def _accept_submission(
    db: Session,
    current_user: User,
    question: Question,
    *,
    key: Optional[str],
    student_name: str,
    student_number: str,
    audio: Optional[bytes],
    audio_suffix: Optional[str],
    anti_cheat_alerts: str,
    face_score: Optional[float],
    started_at: Optional[str],
    finished_at: Optional[str],
    t0: float,
) -> tuple:
    """Synchronous part of submit (runs in a worker thread). Returns (submission, created)."""
    if key:
        existing = _existing_for_key(db, key, current_user)
        if existing:
            return existing, False   # the same recording again: not a new attempt

    # Server-side rules before anything is stored or queued: enrolled, inside an active sitting of
    # THIS question's exam (not expired), question not answered yet in it, attempts left.
    allowed = exam_sessions.check_submission(db, current_user, question)
    sitting = allowed["sitting"]

    # Lecturer's billing account: concurrent-seat limit + priority of the grading queue.
    creator = db.query(User).filter(User.id == question.creator_id).first() if question.creator_id else None
    account = bs.get_billing_account(db, creator) if creator else None
    if account is not None:
        bs.refresh_account_state(db, account)
        bs.acquire_exam_seat(db, account, current_user.id, None, question.group_token or question.exam_token)
    plan = get_plan(account.plan_tier if account is not None else "free")
    priority = int(plan.get("queue_priority", 3))

    # Identity and integrity come from face checks this server ran for this student and this exam
    # (see services/exam_evidence.py). The browser's face_score is ignored — it is still accepted so
    # older web/mobile builds keep submitting — and its proctoring alerts are kept as
    # client-reported indicators only.
    del face_score, started_at, finished_at
    # Face checks count from the server-recorded start of this sitting (not a browser time).
    evidence = exam_evidence.face_evidence(db, current_user, question, since=sitting.started_at)
    if len(anti_cheat_alerts or "") > 32768:
        anti_cheat_alerts = "{}"
    client_alerts = exam_evidence.sanitize_client_alerts(anti_cheat_alerts)
    now = datetime.now(timezone.utc)

    submission = ExamSubmission(
        question_id=question.id,
        student_id=current_user.id,
        submission_key=key,
        student_name=(student_name or "").strip()[:120],
        student_number=(student_number or "").strip()[:64],
        face_score=evidence["face_score"],
        face_verification=evidence["face_verification"],
        face_checks=evidence["face_checks"],
        facial_score=evidence["facial_score"],
        integrity_status=evidence["integrity_status"],
        client_alerts=client_alerts,
        # Server times only: the sitting's recorded start and the moment the answer arrived. The
        # browser's started_at / finished_at are ignored (still accepted for older apps).
        started_at=sitting.started_at.replace(tzinfo=timezone.utc),
        finished_at=now,
        submitted_at=now,
        exam_sitting_id=sitting.id,
        attempt_no=allowed["attempt_no"],
    )
    db.add(submission)
    job = gq.enqueue(
        db, submission,
        audio=audio,
        audio_suffix=audio_suffix,
        anti_cheat_alerts=client_alerts,
        voice_embedding=current_user.voice_embedding,
        has_faceprint=evidence["has_faceprint"],
        priority=priority,
    )
    job.api_receive_ms = int((time.perf_counter() - t0) * 1000)
    try:
        # The submission and its job are one commit: a recording is never accepted without the
        # job that will grade it, and the unique submission_key lets only one of two concurrent
        # requests for the same recording commit — the other lands in the except below.
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.query(ExamSubmission).filter(ExamSubmission.submission_key == key).first() if key else None
        if winner and winner.student_id == current_user.id:
            return winner, False
        if winner:
            raise HTTPException(status_code=409, detail="Duplicate submission key")
        # Lost a race on the attempt / one-answer-per-sitting indexes: another request with a
        # different key took this attempt a moment earlier.
        raise exam_sessions.refuse(409, "ATTEMPT_CONFLICT", "الإجابة دي اتسجلت بالفعل من طلب تاني.",
                                   "An answer for this attempt was already recorded by another request.")
    db.refresh(submission)
    exam_sessions.complete_if_done(db, sitting)

    assignment = db.query(ExamAssignment).filter(
        ExamAssignment.question_id == question.id,
        ExamAssignment.student_id == current_user.id,
        ExamAssignment.status == "pending",
    ).first()
    if assignment:
        assignment.status = "completed"
        db.commit()

    # Free the seat once the student answered the last question of the exam.
    if account is not None:
        grp = question.group_token or question.exam_token
        last_idx = (
            db.query(func.max(Question.order_index))
            .filter((Question.group_token == grp) | (Question.exam_token == grp))
            .scalar()
        )
        if last_idx is None or (question.order_index or 0) >= last_idx:
            bs.release_exam_seat(db, account, current_user.id, None)

    print(f"[Submit] submission={submission.id} queued in {job.api_receive_ms}ms "
          f"(audio {job.audio_bytes or 0} bytes, priority {priority})", flush=True)
    return submission, True


@router.post("/submit", response_model=ExamSubmissionOut)
async def submit_exam(
    *,
    response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    question_id: int = Form(...),
    student_name: str = Form(...),
    student_number: str = Form(...),
    audio: UploadFile = File(None),
    anti_cheat_alerts: str = Form("{}"),
    face_score: Optional[float] = Form(None),
    started_at: Optional[str] = Form(None),
    finished_at: Optional[str] = Form(None),
    submission_key: Optional[str] = Form(None),
) -> Any:
    """202 = answer stored and queued for grading; 200 = this submission_key was already received
    (the original submission is returned, nothing is queued again)."""
    t0 = time.perf_counter()
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    service_pause.ensure_exam_available(db, question)

    key = (submission_key or "").strip()[:128] or None
    content: Optional[bytes] = None
    suffix: Optional[str] = None
    if audio and audio.filename:
        suffix = _safe_audio_suffix(audio.filename)
        content = await read_upload_capped(audio, MAX_AUDIO_BYTES)

    # Database work (including writing a recording of up to 40MB) off the event loop.
    submission, created = await anyio.to_thread.run_sync(
        lambda: _accept_submission(
            db, current_user, question,
            key=key, student_name=student_name, student_number=student_number,
            audio=content, audio_suffix=suffix, anti_cheat_alerts=anti_cheat_alerts,
            face_score=face_score, started_at=started_at, finished_at=finished_at, t0=t0,
        )
    )
    response.status_code = 202 if created else 200
    # A grade is never in this reply unless the exam already releases it (H6) — so a re-sent key
    # can't be used to read a result the lecturer hasn't published.
    return results_visibility.present(submission, current_user, question=question)


# ── GET grading status of one submission (the student who sent it, or its lecturer) ──
def _grading_status_out(db: Session, submission: ExamSubmission, viewer: User) -> GradingStatusOut:
    if viewer.role != "admin":
        service_pause.ensure_lecturer_active(db, viewer)
        service_pause.ensure_exam_available(db, db.get(Question, submission.question_id))
    # Progress for everyone who may see the answer; the grade itself only once released (H6).
    out = results_visibility.present(submission, viewer, schema=GradingStatusOut)
    job = db.query(GradingJob).filter(GradingJob.submission_id == submission.id).first()
    if job is not None:
        out.attempts = job.attempts or 0
        out.max_attempts = job.max_attempts or 0
        out.queue_ahead = gq.queue_ahead(db, job)
        out.retry_at = job.available_at if job.status == gq.QUEUED and (job.attempts or 0) > 0 else None
        out.enqueued_at = job.enqueued_at
        out.grading_started_at = job.started_at
        out.grading_finished_at = job.finished_at
    return out


def _can_view_submission(db: Session, user: User, submission: ExamSubmission) -> bool:
    if submission.student_id == user.id or user.role == "admin":
        return True
    if user.role in ("lecturer", "hr"):
        q = db.query(Question.creator_id).filter(Question.id == submission.question_id).scalar()
        return q == user.id
    return False


@router.get("/submissions/{submission_id}/grading", response_model=GradingStatusOut)
def get_grading_status(
    submission_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    sub = db.query(ExamSubmission).filter(ExamSubmission.id == submission_id).first()
    if not sub or not _can_view_submission(db, current_user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")
    return _grading_status_out(db, sub, current_user)


@router.get("/submissions/by-key/{submission_key}/grading", response_model=GradingStatusOut)
def get_grading_status_by_key(
    submission_key: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """For a browser that lost the submit response: find the answer by the key it generated."""
    sub = db.query(ExamSubmission).filter(
        ExamSubmission.submission_key == submission_key[:128],
        ExamSubmission.student_id == current_user.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return _grading_status_out(db, sub, current_user)


# ── POST re-run grading of a failed answer (its lecturer, or an admin) ────────
@router.post("/submissions/{submission_id}/regrade", response_model=GradingStatusOut)
def regrade_submission(
    submission_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    sub = db.query(ExamSubmission).filter(ExamSubmission.id == submission_id).first()
    if not sub or not _can_view_submission(db, current_user, sub):
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role != "admin":
        service_pause.ensure_lecturer_active(db, current_user)
        service_pause.ensure_exam_available(db, db.get(Question, sub.question_id))
    job = db.query(GradingJob).filter(GradingJob.submission_id == sub.id).first()
    if job is None or job.status != gq.FAILED:
        raise HTTPException(status_code=409, detail="Only an answer whose grading failed can be re-graded")
    if not gq.requeue_failed(db, job):
        raise HTTPException(status_code=410, detail="The recording of this answer is no longer kept")
    db.refresh(sub)
    return _grading_status_out(db, sub, current_user)


# ── GET grading queue metrics (admin) ─────────────────────────────────────────
@router.get("/grading/metrics")
def grading_metrics(
    window_minutes: int = 60,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return gq.metrics(db, window_minutes=max(1, min(window_minutes, 24 * 60)))


# ── GET results for a question (lecturer only) ────────────────────────────────
@router.get("/results/{question_id}", response_model=List[ExamSubmissionOut])
def get_results(
    question_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.creator_id == current_user.id,
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question.submissions


# ── GET all results for all questions (lecturer dashboard) ────────────────────
@router.get("/all-results", response_model=List[ExamSubmissionOut])
def get_all_results(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)

    submissions = (
        db.query(ExamSubmission)
        .options(joinedload(ExamSubmission.question))
        .join(Question)
        .filter(Question.creator_id == current_user.id)
        .all()
    )

    result = []
    for s in submissions:
        item = ExamSubmissionOut.from_orm(s)
        if s.question:
            item.question_text = s.question.text
            item.question_category = s.question.category
        result.append(item)

    return result


# ── GET attendance data (lecturer) ────────────────────────────────────────────
@router.get("/attendance", response_model=List[dict])
def get_attendance(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)

    assignments = (
        db.query(ExamAssignment)
        .options(joinedload(ExamAssignment.student), joinedload(ExamAssignment.question))
        .join(Question)
        .filter(Question.creator_id == current_user.id)
        .all()
    )

    submissions = (
        db.query(ExamSubmission)
        .options(joinedload(ExamSubmission.student), joinedload(ExamSubmission.question))
        .join(Question)
        .filter(Question.creator_id == current_user.id)
        .all()
    )

    data_map = {}
    # An assignment alone doesn't open a student's e-mail (assignments used to accept any id);
    # only students who took one of this lecturer's exams show it.
    related = {sid for (sid,) in student_access.related_student_ids(db, current_user).all()}

    for a in assignments:
        key = (a.student_id, a.question_id)
        data_map[key] = {
            "id": a.id,
            "student_name": a.student.full_name if a.student else "Unknown",
            "email": a.student.email if a.student and (a.student_id in related or current_user.role == "admin") else "",
            "assigned_at": a.assigned_at,
            "started_at": None,
            "finished_at": None,
            "status": a.status,
            "score": None,
            "question_title": a.question.text[:50] if a.question and a.question.text else "Exam",
        }

    for s in submissions:
        key = (s.student_id, s.question_id)
        if key in data_map:
            data_map[key]["status"] = "completed"
            data_map[key]["score"] = s.overall_score
        else:
            data_map[key] = {
                "id": -s.id,
                "student_name": s.student_name or (s.student.full_name if s.student else "Unknown"),
                "email": s.student.email if s.student else "",
                "assigned_at": s.submitted_at,
                "started_at": s.started_at,
                "finished_at": s.submitted_at,
                "status": "completed",
                "score": s.overall_score,
                "question_title": s.question.text[:50] if s.question and s.question.text else "Exam",
            }

        if key in data_map and s.started_at:
            data_map[key]["started_at"] = s.started_at
            data_map[key]["finished_at"] = s.submitted_at

    return list(data_map.values())


# ── GET my grades (student — only visible ones) ───────────────────────────────
@router.get("/my-grades", response_model=List[ExamSubmissionOut])
def get_my_grades(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    subs = (
        db.query(ExamSubmission)
        .options(joinedload(ExamSubmission.question).joinedload(Question.creator))
        .filter(
            ExamSubmission.student_id == current_user.id,
            ExamSubmission.grade_visible == 1,
            ExamSubmission.grading_status == "completed",   # released and actually graded (H6)
        )
        .all()
    )
    paused = service_pause.paused_creator_ids(db)
    out = []
    for s in subs:
        if s.question is not None and s.question.creator_id in paused:
            continue
        item = results_visibility.present(s, current_user)
        if s.question:
            item.question_text = s.question.text
            item.question_category = s.question.category
            if s.question.creator:
                item.lecturer_name = s.question.creator.full_name
        out.append(item)
    return out


# ── PATCH toggle grade visibility (lecturer — verified ownership) ─────────────
@router.patch("/submissions/{submission_id}/visibility")
def toggle_grade_visibility(
    submission_id: int,
    visible: bool,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)
    sub = (
        db.query(ExamSubmission)
        .options(joinedload(ExamSubmission.question))
        .filter(ExamSubmission.id == submission_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if current_user.role != "admin" and (not sub.question or sub.question.creator_id != current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to modify this submission")
    sub.grade_visible = 1 if visible else 0
    db.commit()
    return {"ok": True}


# ── POST publish an exam's results (its lecturer, or an admin) — H6 ───────────
@router.post("/publish-results/{exam_token}")
def publish_results(
    exam_token: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Makes every graded answer of an exam with results_policy=manual visible to its own student.
    Idempotent: publishing again changes nothing and says so."""
    if current_user.role not in ["lecturer", "hr", "admin"]:
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)
    return results_visibility.publish(db, current_user, exam_token)
