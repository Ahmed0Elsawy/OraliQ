from sqlalchemy import Column, Index, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class ExamSubmission(Base):
    """A student's submission for a specific exam question."""
    __tablename__ = "exam_submissions"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"))
    student_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # The browser's id for one recording, sent with every attempt to submit it. Grading an answer
    # can outlast the client's timeout, so a retry of a request that actually succeeded used to
    # add a second graded row and the lecturer saw the same answer twice. The unique index makes
    # that impossible; the endpoint returns the original row instead of grading again.
    submission_key = Column(String, unique=True, index=True, nullable=True)

    # ── Server-side sitting and attempt (H2). NULL on answers from before sittings existed. ──
    exam_sitting_id = Column(Integer, ForeignKey("exam_sittings.id"), nullable=True)
    # 1st, 2nd... answer of this user to this question. Unique together with the user and the
    # question, and one answer per question per sitting: two concurrent requests can't both count.
    attempt_no = Column(Integer, nullable=True)
    __table_args__ = (
        Index("ux_exam_submissions_attempt", "student_id", "question_id", "attempt_no", unique=True),
        Index("ux_exam_submissions_sitting_question", "exam_sitting_id", "question_id", unique=True),
    )

    # Student info (filled in check-in form)
    student_name = Column(String)
    student_number = Column(String)

    # AI results (filled after processing)
    transcript = Column(Text, nullable=True)
    nlp_score = Column(Float, nullable=True)       # 0-100 answer quality
    facial_score = Column(Float, nullable=True)    # 0-100 integrity
    speech_score = Column(Float, nullable=True)    # 0-100 fluency
    voice_score = Column(Float, nullable=True)     # 0-100 voice match similarity
    face_score = Column(Float, nullable=True)      # 0-100 Face ID match similarity
    overall_score = Column(Float, nullable=True)   # 0-100 combined
    cheat_report = Column(Text, nullable=True)     # Arabic anti-cheat report
    fluency_report = Column(Text, nullable=True)   # Arabic fluency report

    # ── Where the identity / integrity results came from (H1). NULL on answers graded before these
    # existed, whose face_score and facial_score were taken from the browser.
    # face_verification: verified | uncertain | mismatch | no_face | unverified | not_enrolled —
    #   from face checks the server itself performed for this student and this exam.
    face_verification = Column(String(16), nullable=True)
    face_checks = Column(Integer, nullable=True)            # server face checks used
    # integrity_status: server_sampled (facial_score computed from those checks) |
    #   insufficient_data (too few server checks: facial_score is NULL, not counted in the grade).
    integrity_status = Column(String(24), nullable=True)
    # What the browser reported (gaze, head turns, objects...): stored for the lecturer to review,
    # never used as evidence or in the score — the student's browser can send anything.
    client_alerts = Column(Text, nullable=True)

    # Grading progress: queued | processing | completed | failed. Rows from before the grading
    # queue existed were graded inline, hence the "completed" default.
    grading_status = Column(String(16), nullable=False, default="completed", server_default="completed")

    # Visibility: lecturer can toggle whether student sees their grade
    grade_visible = Column(Integer, default=0)     # 0=hidden, 1=visible

    started_at = Column(DateTime, nullable=True)   # Time when Ready was clicked
    finished_at = Column(DateTime, nullable=True)  # Time when recording ended (precise duration)
    submitted_at = Column(DateTime, default=datetime.utcnow) # Time when DB record was saved

    # Relationships
    question = relationship("Question", back_populates="submissions")
    student = relationship("User", foreign_keys=[student_id])
