from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ExamAssignmentCreate(BaseModel):
    question_id: int
    student_id: int

class AssignedExamOut(BaseModel):
    id: int
    question_id: int
    assigned_at: Optional[datetime] = None
    status: str = "pending"
    # Question details embedded
    question_text: Optional[str] = None
    question_category: Optional[str] = None
    question_difficulty: Optional[str] = None
    exam_token: Optional[str] = None
    assigned_by_name: Optional[str] = None

    class Config:
        from_attributes = True
