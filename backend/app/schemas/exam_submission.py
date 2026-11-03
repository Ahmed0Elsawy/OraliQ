from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

class ExamSubmissionCreate(BaseModel):
    question_id: int
    student_name: str
    student_number: str
    started_at: Optional[datetime] = None

class ExamSubmissionOut(BaseModel):
    id: int
    question_id: int
    student_name: str
    student_number: str
    transcript: Optional[str] = None
    # Scores are clamped 0–100 server-side; negative values are rejected.
    nlp_score: Optional[float] = Field(default=None, ge=0, le=100)
    facial_score: Optional[float] = Field(default=None, ge=0, le=100)
    speech_score: Optional[float] = Field(default=None, ge=0, le=100)
    voice_score: Optional[float] = Field(default=None, ge=0, le=100)
    face_score: Optional[float] = Field(default=None, ge=0, le=100)
    overall_score: Optional[float] = Field(default=None, ge=0, le=100)
    cheat_report: Optional[str] = None
    fluency_report: Optional[str] = None
    grade_visible: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    question_text: Optional[str] = None
    question_category: Optional[str] = None
    lecturer_name: Optional[str] = None
    # queued | processing | completed | failed — scores stay empty until "completed".
    grading_status: str = "completed"
    # Provenance of face_score / facial_score (None on answers graded before it was recorded).
    face_verification: Optional[str] = None
    face_checks: Optional[int] = None
    integrity_status: Optional[str] = None
    client_alerts: Optional[str] = None
    # Server-side sitting and attempt number (H2); None on answers from before sittings existed.
    exam_sitting_id: Optional[int] = None
    attempt_no: Optional[int] = None
    # Whether the grade above may be shown to the student (H6). For a student whose grade isn't
    # published yet every grading output in this object is null, whatever the endpoint.
    result_visible: Optional[bool] = None

    class Config:
        from_attributes = True


class GradingStatusOut(ExamSubmissionOut):
    """A submission plus where its grading job stands (what the exam room polls)."""
    submission_key: Optional[str] = None
    queue_ahead: Optional[int] = None      # queued answers that will be graded before this one
    attempts: int = 0
    max_attempts: int = 0
    retry_at: Optional[datetime] = None    # next attempt after a failed one
    enqueued_at: Optional[datetime] = None
    grading_started_at: Optional[datetime] = None
    grading_finished_at: Optional[datetime] = None
