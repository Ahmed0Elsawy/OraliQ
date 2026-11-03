from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime, default=datetime.utcnow)
    overall_score = Column(Float, default=0.0)
    
    # Relationships
    user = relationship("User", back_populates="interviews")
    details = relationship("InterviewDetail", back_populates="interview")

class InterviewDetail(Base):
    __tablename__ = "interview_details"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"))
    question_id = Column(Integer, ForeignKey("questions.id"))
    
    # Paths to recorded media
    audio_path = Column(String)
    video_path = Column(String)
    
    # AI Analysis Results
    transcript = Column(String) # Speech to Text
    facial_emotion = Column(String) # e.g., "nervous", "confident"
    facial_score = Column(Float) # 0-100
    speech_wpm = Column(Float) # Words Per Minute
    speech_score = Column(Float) # 0-100
    nlp_score = Column(Float) # 0-100 (Answer quality)
    
    # Relationships
    interview = relationship("Interview", back_populates="details")
    question = relationship("Question")

# Update User model to include relationship
from app.models.user import User
User.interviews = relationship("Interview", back_populates="user")
