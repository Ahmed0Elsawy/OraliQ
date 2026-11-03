from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String

from app.core.database import Base


class ExamSession(Base):
    """
    One seat in a lecturer's exam room. The plan's student limit counts how many students
    are taking the lecturer's exams AT THE SAME TIME (open, unexpired sessions) — it is not
    consumed when a student finishes.
    """
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("users.id"), nullable=False)   # billing owner
    student_key = Column(String(160), nullable=False)                     # "u:<id>" or "n:<number>"
    group_token = Column(String, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    finished = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_exam_sessions_account_active", "account_id", "finished", "expires_at"),
        Index("ix_exam_sessions_student", "account_id", "student_key"),
    )
