from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional

ALLOWED_SIGNUP_ROLES = {"student", "lecturer"}


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=120)
    role: str = Field(default="student", max_length=32)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def reject_compromised_passwords(cls, v: str) -> str:
        if v.strip().lower() in {"oauth_google_oraliq_2026!", "oauth_github_oraliq_2026!"}:
            raise ValueError("Please choose a different password")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        role_clean = (v or "student").strip().lower()
        if role_clean not in ALLOWED_SIGNUP_ROLES:
            raise ValueError("Invalid role. Allowed roles: student, lecturer")
        return role_clean

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(UserBase):
    id: int
    is_active: bool
    plan_tier: Optional[str] = "free"
    email_verified: bool = False

    class Config:
        from_attributes = True
