from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class QuestionBase(BaseModel):
    text: str = Field(..., min_length=2, max_length=4000)
    model_answer: str = Field(..., min_length=1, max_length=8000)
    keywords: str = Field(default="", max_length=2000)
    difficulty: str = Field(default="medium", max_length=50)
    category: str = Field(default="general", max_length=120)
    duration_minutes: int = Field(default=2, ge=1, le=180)
    # Attempts per student at the exam this question belongs to (the exam's first question decides).
    max_attempts: int = Field(default=1, ge=1, le=10)
    # manual: grades hidden until the lecturer publishes; immediate: shown once graded.
    results_policy: str = Field(default="manual", pattern="^(manual|immediate)$")


class QuestionCreate(QuestionBase):
    group_token: Optional[str] = Field(default=None, max_length=128)


class QuestionOut(QuestionBase):
    """Full question schema for lecturers (includes model_answer & keywords)."""
    id: int
    exam_token: str
    group_token: Optional[str] = None
    order_index: int = 0
    creator_id: Optional[int] = None
    created_at: Optional[datetime] = None
    results_published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class QuestionPublicOut(BaseModel):
    """
    Sanitized public question schema for students in the Exam Room.
    Strictly omits `model_answer` and `keywords` to prevent answer-key leakage in DevTools.
    """
    id: int
    text: str
    difficulty: str = "medium"
    category: str = "general"
    duration_minutes: int = 2
    max_attempts: int = 1
    exam_token: str
    group_token: Optional[str] = None
    order_index: int = 0
    creator_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
