from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from datetime import datetime

from app.api import deps
from app.models.interview import Interview, InterviewDetail
from app.models.user import User
from app.schemas.interview import InterviewOut, InterviewCreate

router = APIRouter()

@router.post("/start", response_model=InterviewOut)
def start_interview(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    interview = Interview(user_id=current_user.id, date=datetime.utcnow())
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview

@router.get("/my-interviews", response_model=List[InterviewOut])
def read_my_interviews(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    return current_user.interviews

# TODO: Add endpoint to submit video/audio for a specific question
# This will be the main entry point for the AI processing
