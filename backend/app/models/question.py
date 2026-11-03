import uuid
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String, index=True)
    model_answer = Column(Text)
    keywords = Column(String, default="")
    difficulty = Column(String, default="medium")   # easy, medium, hard
    category = Column(String, default="general")
    duration_minutes = Column(Integer, default=2)

    # Ownership & sharing
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    exam_token = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    group_token = Column(String, index=True, nullable=True)  # shared across questions in the same exam bundle
    order_index = Column(Integer, default=0)  # question order within the group
    # Attempts each student gets at this exam (set by the lecturer for the whole group; questions
    # added later inherit the first question's value). Enforced by the server per sitting.
    max_attempts = Column(Integer, nullable=False, default=1, server_default="1")
    # When students see their grade (whole exam; later questions inherit the first one's):
    #   manual    — hidden until the lecturer publishes the exam's results (the default, and how
    #               every existing exam already worked: grades appeared in "My grades" only once
    #               the lecturer published them);
    #   immediate — each answer's grade is shown to its student as soon as grading completes.
    results_policy = Column(String(16), nullable=False, default="manual", server_default="manual")
    results_published_at = Column(DateTime, nullable=True)
    results_published_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User", foreign_keys=[creator_id])
    submissions = relationship("ExamSubmission", back_populates="question")
