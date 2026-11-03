from sqlalchemy import Column, Integer, ForeignKey, DateTime, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class ExamAssignment(Base):
    """Lecturer assigns a specific question to a specific student."""
    __tablename__ = "exam_assignments"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    student_id = Column(Integer, ForeignKey("users.id"))
    assigned_by = Column(Integer, ForeignKey("users.id"))  # lecturer id
    assigned_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="pending")  # pending | completed

    # Relationships
    question = relationship("Question", foreign_keys=[question_id])
    student = relationship("User", foreign_keys=[student_id])
    lecturer = relationship("User", foreign_keys=[assigned_by])
