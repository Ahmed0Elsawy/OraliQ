from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class EmailVerificationToken(Base):
    """
    One e-mailed verification link. Only the SHA-256 of the link's secret is stored, so a database
    leak doesn't hand out working links. Completing it also needs the password chosen at sign-up
    (kept here as a hash, applied to the account only on success): whoever registered and whoever
    reads the mailbox must be the same person.
    """
    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    sent_to = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)          # set when used, or when superseded/cancelled
    failed_attempts = Column(Integer, nullable=False, default=0)

    pending_password_hash = Column(Text, nullable=False)
    pending_full_name = Column(String, nullable=True)
    pending_role = Column(String(32), nullable=True)

    user = relationship("User")
