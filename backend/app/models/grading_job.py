from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import deferred, relationship
from app.core.database import Base


class GradingJob(Base):
    """
    One answer waiting to be graded, kept in the database so a restart never loses it.

    The API writes the row (with the recording) in the same transaction as the submission and
    answers at once; a separate worker process claims rows, runs Whisper + SBERT + voice check,
    and writes the grade. Status moves queued -> processing -> completed, or back to queued for a
    retry, or failed once max_attempts is spent. A claim is a lease: the worker refreshes
    heartbeat_at while it works, and a row whose heartbeat went quiet (worker crashed or was
    restarted) is put back in the queue by the next worker that looks.
    """
    __tablename__ = "grading_jobs"

    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("exam_submissions.id"), nullable=False, unique=True)

    status = Column(String(16), nullable=False, default="queued")  # queued | processing | completed | failed
    priority = Column(Integer, nullable=False, default=3)           # plan queue_priority: lower runs first
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow)  # not before (retry backoff)

    locked_by = Column(String(128), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)

    enqueued_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)    # start of the latest attempt
    finished_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    # The recording itself. Deferred so status polls never pull megabytes out of the database;
    # cleared once the grade is saved, or after the retention window when grading failed.
    audio = deferred(Column(LargeBinary, nullable=True))
    audio_suffix = Column(String(8), nullable=True)
    audio_bytes = Column(Integer, nullable=True)
    audio_purged_at = Column(DateTime, nullable=True)

    # What grading needs, captured when the answer arrived.
    anti_cheat_alerts = Column(Text, nullable=True)
    voice_embedding = Column(Text, nullable=True)
    has_faceprint = Column(Boolean, nullable=False, default=False)

    # Timings for monitoring (milliseconds).
    api_receive_ms = Column(Integer, nullable=True)
    queue_wait_ms = Column(Integer, nullable=True)
    process_ms = Column(Integer, nullable=True)

    submission = relationship("ExamSubmission")

    __table_args__ = (
        Index("ix_grading_jobs_claim", "status", "priority", "available_at", "id"),
        Index("ix_grading_jobs_heartbeat", "status", "heartbeat_at"),
    )
