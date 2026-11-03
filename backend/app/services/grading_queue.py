"""
Durable grading queue on the application's own database (PostgreSQL in production, SQLite locally).

Why the database and not Redis: the queue has to survive restarts, and the database is already
there, already backed by the provider, and already transactional — the submission row and its
job are written in one commit, so an answer can never exist without its job or the other way
round. The load is small (one row per answer, a few polls a second), well within what Postgres
handles without a dedicated broker.

Every state change is a compare-and-set UPDATE (`... WHERE id = :id AND status = :expected`), so
two workers can never both claim, finish or fail the same job: on PostgreSQL the second UPDATE
waits for the first's row lock and then matches nothing; on SQLite writes are serialized anyway.
Finishing a job is only accepted from the worker that still holds its lease, in the same
transaction that saves the grade.
"""
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import Session

from app.models.exam_submission import ExamSubmission
from app.models.grading_job import GradingJob

QUEUED, PROCESSING, COMPLETED, FAILED = "queued", "processing", "completed", "failed"


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if raw.isdigit():
        return max(minimum, int(raw))
    return default


def max_attempts() -> int:
    return _env_int("GRADING_MAX_ATTEMPTS", 3, minimum=1)


def heartbeat_seconds() -> int:
    return _env_int("GRADING_HEARTBEAT_SECONDS", 15, minimum=1)


def stale_after_seconds() -> int:
    """A processing job whose heartbeat is older than this is presumed orphaned."""
    return _env_int("GRADING_STALE_SECONDS", 120, minimum=5)


def failed_audio_retention_hours() -> int:
    """How long the recording of a failed job is kept so a lecturer can re-run it."""
    return _env_int("GRADING_FAILED_AUDIO_RETENTION_HOURS", 72)


def retry_delay_seconds(attempt: int) -> int:
    base = _env_int("GRADING_RETRY_BASE_SECONDS", 30)
    return min(base * (2 ** max(0, attempt - 1)), 600)


def utcnow() -> datetime:
    """Naive UTC, like every other timestamp in this database."""
    return datetime.utcnow()


def _ms(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() * 1000))


def _set_submission_status(db: Session, submission_id: int, status: str) -> None:
    db.execute(
        update(ExamSubmission)
        .where(ExamSubmission.id == submission_id)
        .values(grading_status=status)
    )


# ── Enqueue (API side) ────────────────────────────────────────────────────────

def enqueue(
    db: Session,
    submission: ExamSubmission,
    *,
    audio: Optional[bytes],
    audio_suffix: Optional[str],
    anti_cheat_alerts: str,
    voice_embedding: Optional[str],
    has_faceprint: bool,
    priority: int,
) -> GradingJob:
    """Adds the job for a submission that is being added in the same session. Caller commits."""
    now = utcnow()
    submission.grading_status = QUEUED
    job = GradingJob(
        submission=submission,
        status=QUEUED,
        priority=priority,
        attempts=0,
        max_attempts=max_attempts(),
        available_at=now,
        enqueued_at=now,
        audio=audio,
        audio_suffix=audio_suffix,
        audio_bytes=len(audio) if audio else 0,
        anti_cheat_alerts=anti_cheat_alerts,
        voice_embedding=voice_embedding,
        has_faceprint=has_faceprint,
    )
    db.add(job)
    return job


# ── Worker side ───────────────────────────────────────────────────────────────

def claim_next(db: Session, worker_id: str) -> Optional[int]:
    """Takes the next due job (highest plan priority, then oldest) and returns its id."""
    now = utcnow()
    candidates = (
        db.query(GradingJob.id)
        .filter(GradingJob.status == QUEUED, GradingJob.available_at <= now)
        .order_by(GradingJob.priority, GradingJob.available_at, GradingJob.id)
        .limit(5)
        .all()
    )
    db.rollback()  # end the read; each claim below is its own short transaction
    for (job_id,) in candidates:
        res = db.execute(
            update(GradingJob)
            .where(GradingJob.id == job_id, GradingJob.status == QUEUED)
            .values(
                status=PROCESSING,
                locked_by=worker_id,
                locked_at=now,
                heartbeat_at=now,
                started_at=now,
                attempts=GradingJob.attempts + 1,
            )
        )
        if res.rowcount == 1:
            sub_id = db.query(GradingJob.submission_id).filter(GradingJob.id == job_id).scalar()
            _set_submission_status(db, sub_id, PROCESSING)
            db.commit()
            return job_id
        db.rollback()  # another worker got it first
    return None


def heartbeat(db: Session, job_id: int, worker_id: str) -> bool:
    res = db.execute(
        update(GradingJob)
        .where(GradingJob.id == job_id, GradingJob.status == PROCESSING, GradingJob.locked_by == worker_id)
        .values(heartbeat_at=utcnow())
    )
    db.commit()
    return res.rowcount == 1


def complete(db: Session, job_id: int, worker_id: str, fields: Dict[str, Any]) -> bool:
    """
    Saves the grade and closes the job in one transaction. Returns False (and saves nothing) when
    this worker no longer holds the job — its lease expired and someone else took over.
    """
    job = db.query(GradingJob).filter(GradingJob.id == job_id).first()
    if job is None:
        db.rollback()
        return False
    now = utcnow()
    started = job.started_at or now
    res = db.execute(
        update(GradingJob)
        .where(GradingJob.id == job_id, GradingJob.status == PROCESSING, GradingJob.locked_by == worker_id)
        .values(
            status=COMPLETED,
            finished_at=now,
            heartbeat_at=now,
            last_error=None,
            audio=None,
            audio_purged_at=now,
            queue_wait_ms=_ms(started - job.enqueued_at) if job.enqueued_at else None,
            process_ms=_ms(now - started),
        )
    )
    if res.rowcount != 1:
        db.rollback()
        return False
    # Release the grade to its student now if the exam shows results immediately or has already
    # been published (H6). Evaluated inside the UPDATE itself, so an exam published while this
    # answer was being graded is seen; a grade already released by the lecturer stays released.
    from sqlalchemy import case, exists
    from app.models.question import Question
    released = exists().where(
        Question.id == ExamSubmission.question_id,
        or_(Question.results_policy == "immediate", Question.results_published_at.isnot(None)),
    )
    db.execute(
        update(ExamSubmission)
        .where(ExamSubmission.id == job.submission_id)
        .values(grading_status=COMPLETED,
                grade_visible=case((released, 1), else_=func.coalesce(ExamSubmission.grade_visible, 0)),
                **fields)
    )
    db.commit()
    return True


def fail_attempt(db: Session, job_id: int, worker_id: str, error: str) -> Optional[str]:
    """
    Records a failed attempt: back to the queue with a delay, or "failed" when attempts are spent.
    The recording is kept either way. Returns the new status, or None if the lease was lost.
    """
    job = db.query(GradingJob).filter(GradingJob.id == job_id).first()
    if job is None:
        db.rollback()
        return None
    now = utcnow()
    exhausted = (job.attempts or 0) >= (job.max_attempts or 1)
    new_status = FAILED if exhausted else QUEUED
    values: Dict[str, Any] = {
        "status": new_status,
        "locked_by": None,
        "last_error": (error or "")[:2000],
        "process_ms": _ms(now - (job.started_at or now)),
    }
    if exhausted:
        values["finished_at"] = now
    else:
        values["available_at"] = now + timedelta(seconds=retry_delay_seconds(job.attempts or 1))
    res = db.execute(
        update(GradingJob)
        .where(GradingJob.id == job_id, GradingJob.status == PROCESSING, GradingJob.locked_by == worker_id)
        .values(**values)
    )
    if res.rowcount != 1:
        db.rollback()
        return None
    _set_submission_status(db, job.submission_id, new_status)
    db.commit()
    return new_status


def recover_stale(db: Session) -> int:
    """
    Puts back jobs whose worker stopped heart-beating (crash, kill, restart). The interrupted
    attempt counts; a job that already used every attempt is marked failed instead of looping.
    """
    now = utcnow()
    cutoff = now - timedelta(seconds=stale_after_seconds())
    stale = (
        db.query(GradingJob.id, GradingJob.submission_id, GradingJob.attempts, GradingJob.max_attempts, GradingJob.locked_by)
        .filter(GradingJob.status == PROCESSING, GradingJob.heartbeat_at < cutoff)
        .all()
    )
    db.rollback()
    recovered = 0
    for job_id, sub_id, attempts, limit, holder in stale:
        exhausted = (attempts or 0) >= (limit or 1)
        new_status = FAILED if exhausted else QUEUED
        values: Dict[str, Any] = {
            "status": new_status,
            "locked_by": None,
            "last_error": f"worker {holder} stopped responding during attempt {attempts}",
        }
        if exhausted:
            values["finished_at"] = now
        else:
            values["available_at"] = now
        res = db.execute(
            update(GradingJob)
            .where(GradingJob.id == job_id, GradingJob.status == PROCESSING, GradingJob.heartbeat_at < cutoff)
            .values(**values)
        )
        if res.rowcount == 1:
            _set_submission_status(db, sub_id, new_status)
            db.commit()
            recovered += 1
        else:
            db.rollback()
    return recovered


def purge_expired_audio(db: Session) -> int:
    """Drops recordings of failed jobs once the retention window has passed."""
    now = utcnow()
    cutoff = now - timedelta(hours=failed_audio_retention_hours())
    res = db.execute(
        update(GradingJob)
        .where(
            GradingJob.status == FAILED,
            GradingJob.finished_at < cutoff,
            GradingJob.audio_purged_at.is_(None),
        )
        .values(audio=None, audio_purged_at=now)
    )
    db.commit()
    return res.rowcount or 0


def requeue_failed(db: Session, job: GradingJob) -> bool:
    """A lecturer asks for a failed answer to be graded again (needs the recording still kept)."""
    if job.audio_purged_at is not None and (job.audio_bytes or 0) > 0:
        return False
    now = utcnow()
    res = db.execute(
        update(GradingJob)
        .where(GradingJob.id == job.id, GradingJob.status == FAILED)
        .values(status=QUEUED, attempts=0, available_at=now, enqueued_at=now,
                finished_at=None, locked_by=None, last_error=None)
    )
    if res.rowcount != 1:
        db.rollback()
        return False
    _set_submission_status(db, job.submission_id, QUEUED)
    db.commit()
    return True


# ── Read side ─────────────────────────────────────────────────────────────────

def queue_ahead(db: Session, job: GradingJob) -> Optional[int]:
    if job.status != QUEUED:
        return None
    return (
        db.query(func.count(GradingJob.id))
        .filter(
            GradingJob.status == QUEUED,
            or_(
                GradingJob.priority < job.priority,
                and_(GradingJob.priority == job.priority, GradingJob.id < job.id),
            ),
        )
        .scalar()
        or 0
    )


def _percentile(values: List[int], pct: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100.0 * (len(ordered) - 1)))))
    return ordered[idx]


def metrics(db: Session, window_minutes: int = 60) -> Dict[str, Any]:
    now = utcnow()
    counts = dict(db.query(GradingJob.status, func.count(GradingJob.id)).group_by(GradingJob.status).all())
    oldest = db.query(func.min(GradingJob.enqueued_at)).filter(GradingJob.status == QUEUED).scalar()
    since = now - timedelta(minutes=window_minutes)
    done = (
        db.query(GradingJob.queue_wait_ms, GradingJob.process_ms, GradingJob.api_receive_ms)
        .filter(GradingJob.status == COMPLETED, GradingJob.finished_at >= since)
        .all()
    )
    waits = [w for w, _, _ in done if w is not None]
    procs = [p for _, p, _ in done if p is not None]
    receives = [r for _, _, r in done if r is not None]
    failed_recent = (
        db.query(func.count(GradingJob.id))
        .filter(GradingJob.status == FAILED, GradingJob.finished_at >= since)
        .scalar()
        or 0
    )
    live_cutoff = now - timedelta(seconds=stale_after_seconds())
    active_workers = [
        w for (w,) in db.query(GradingJob.locked_by)
        .filter(GradingJob.status == PROCESSING, GradingJob.heartbeat_at >= live_cutoff)
        .distinct()
        .all()
        if w
    ]
    return {
        "queued": int(counts.get(QUEUED, 0)),
        "processing": int(counts.get(PROCESSING, 0)),
        "completed": int(counts.get(COMPLETED, 0)),
        "failed": int(counts.get(FAILED, 0)),
        "oldest_queued_seconds": int((now - oldest).total_seconds()) if oldest else 0,
        "window_minutes": window_minutes,
        "completed_in_window": len(done),
        "failed_in_window": int(failed_recent),
        "queue_wait_ms": {"avg": int(sum(waits) / len(waits)) if waits else None,
                          "p95": _percentile(waits, 95), "max": max(waits) if waits else None},
        "process_ms": {"avg": int(sum(procs) / len(procs)) if procs else None,
                       "p95": _percentile(procs, 95), "max": max(procs) if procs else None},
        "api_receive_ms": {"avg": int(sum(receives) / len(receives)) if receives else None,
                           "p95": _percentile(receives, 95)},
        "workers_with_active_jobs": active_workers,
    }
