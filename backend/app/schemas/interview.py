from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class InterviewCreate(BaseModel):
    user_id: int # In real app, get from token

class InterviewDetailBase(BaseModel):
    question_id: int
    transcript: Optional[str] = None
    facial_emotion: Optional[str] = None
    facial_score: float = 0.0
    speech_wpm: float = 0.0
    speech_score: float = 0.0
    nlp_score: float = 0.0

class InterviewOut(BaseModel):
    id: int
    date: datetime
    overall_score: float
    details: List[InterviewDetailBase] = []

    class Config:
        from_attributes = True
