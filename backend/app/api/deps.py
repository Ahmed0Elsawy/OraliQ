from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.core import security
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

def get_db() -> Generator:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = payload.get("sub")
        token_version = payload.get("tv", 0)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    try:
        user_id = int(token_data)
    except (TypeError, ValueError):
        raise HTTPException(status_code=403, detail="Could not validate credentials")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=401,
            detail="الجلسة منتهية أو الحساب غير موجود — سجّل الدخول مرة أخرى",
        )
    if not user.is_active:
        # A disabled account must lose access now, not when its 7-day token expires.
        raise HTTPException(status_code=401, detail="Inactive user")
    try:
        token_version = int(token_version or 0)
    except (TypeError, ValueError):
        token_version = -1
    if token_version != int(user.token_version or 0):
        # Issued before the account changed hands (e.g. its real owner proved the e-mail): void.
        raise HTTPException(status_code=401, detail="الجلسة منتهية أو الحساب غير موجود — سجّل الدخول مرة أخرى")
    return user

def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
