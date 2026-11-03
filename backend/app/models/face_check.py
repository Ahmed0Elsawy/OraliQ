from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String
from app.core.database import Base


class FaceCheck(Base):
    """
    One face verification the SERVER performed (POST /face/verify): the frame was compared with the
    user's enrolled face print by InsightFace here, and this is the result. A submission's face
    score and monitoring evidence are computed from these rows — never from numbers the browser
    sends. Each row is tied to the signed-in user and to the exam (group token) it was taken for.
    """
    __tablename__ = "face_checks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exam_key = Column(String(128), nullable=True)      # question group token; None = not tied to an exam
    similarity = Column(Float, nullable=True)          # 0-100, None when no face was found
    is_match = Column(Boolean, nullable=False, default=False)
    no_face = Column(Boolean, nullable=False, default=False)
    num_faces = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_face_checks_user_exam_time", "user_id", "exam_key", "created_at"),
    )
