from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from app.core.database import Base


class ExamSitting(Base):
    """
    One attempt at an exam (a question group) by one user, timed by the server.

    Started by GET /exams/access-check (which both the web and the mobile app call before an exam);
    reopening the exam returns the same sitting with the same deadline, so a reload never resets
    the clock. Answers are accepted only inside an active sitting of their exam. Each sitting is one
    attempt: the exam's max_attempts caps how many a user gets.

    All times are naive UTC, like the rest of this database.
    """
    __tablename__ = "exam_sittings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exam_key = Column(String(128), nullable=False)             # question group token
    attempt_no = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="active")   # active | completed | expired
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deadline_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    # 1 while active, NULL afterwards: the unique index below allows only one active sitting per
    # user and exam, even when two requests try to start one at the same moment.
    active_slot = Column(Integer, nullable=True, default=1)

    __table_args__ = (
        Index("ux_exam_sittings_one_active", "user_id", "exam_key", "active_slot", unique=True),
        Index("ux_exam_sittings_attempt", "user_id", "exam_key", "attempt_no", unique=True),
    )
