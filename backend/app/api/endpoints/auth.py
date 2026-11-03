import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import email_verification as ev
from app.services import mailer

router = APIRouter()

_DUMMY_HASH = security.get_password_hash("oraliq-timing-equaliser")
# Block public hardcoded passwords used by the retired fake social login modal so any legacy
# account created through it cannot be taken over via password login (must use verified Google Sign-In).
_RETIRED_FAKE_OAUTH_PASSWORDS = {
    "oauth_google_oraliq_2026!",
    "oauth_github_oraliq_2026!",
}


@router.post("/login/access-token")
def login_access_token(
    db: Session = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Any:
    email_norm = (form_data.username or "").strip().lower()
    raw_password = form_data.password or ""
    if len(email_norm) > 254 or len(raw_password) > 128:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if raw_password.strip().lower() in _RETIRED_FAKE_OAUTH_PASSWORDS:
        security.verify_password(raw_password, _DUMMY_HASH)
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        # Fallback case-insensitive match for legacy records
        user = db.query(User).filter(User.email == form_data.username).first()

    if not user:
        security.verify_password(form_data.password, _DUMMY_HASH)  # same timing as a real miss
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    # Only after the password matched (so this reveals nothing to someone guessing addresses):
    # a password sign-up must have proved its e-mail before it gets a session.
    allowed, reason = ev.is_verified_or_legacy_allowed(user)
    if not allowed:
        raise HTTPException(status_code=403, detail={
            "code": reason,
            "message": "أكّد بريدك الإلكتروني الأول من الرابط اللي اتبعتلك، أو اطلب رابط جديد.",
            "message_en": "Confirm your e-mail first using the link we sent you, or ask for a new one.",
        })

    return _session(user)


def _session(user: User, **extra: Any) -> dict:
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires, token_version=user.token_version or 0,
        ),
        "token_type": "bearer",
        "email_verified": bool(user.email_verified),
        **extra,
    }


# Every sign-up / resend answers with exactly this, whether or not the address has an account, so
# the endpoints can't be used to find out who is registered.
_CHECK_YOUR_EMAIL = {
    "ok": True,
    "verification_required": True,
    "message": "لو البريد ده ينفع يتسجّل بيه، بعتنا عليه رابط تأكيد. افتح الرابط واكتب كلمة المرور اللي اخترتها.",
    "message_en": "If this address can be used, we sent it a confirmation link. Open it and enter the password you chose.",
}


def _email_signup_available() -> None:
    if not mailer.configured():
        raise HTTPException(status_code=503, detail={
            "code": "EMAIL_SIGNUP_UNAVAILABLE",
            "message": "التسجيل بالبريد مش متاح دلوقتي. سجّل بحساب Google.",
            "message_en": "E-mail sign-up is not available right now. Please continue with Google.",
        })


@router.post("/register", status_code=202)
def register_user(
    *,
    db: Session = Depends(deps.get_db),
    user_in: UserCreate,
) -> Any:
    """
    Creates the account, unverified, and e-mails a confirmation link; no session until it is used.
    The reply is the same for a new address, a pending one and a taken one.
    """
    _email_signup_available()
    email_norm = user_in.email.strip().lower()
    full_name = (user_in.full_name or "").strip()[:120] or None
    password_hash = security.get_password_hash(user_in.password)   # hashed on every path: same timing
    try:
        user = db.query(User).filter(User.email == email_norm).first()
        if user is None:
            user = User(
                email=email_norm, hashed_password=password_hash, full_name=full_name, role=user_in.role,
                email_verified=False, requires_email_verification=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            ev.issue_and_send(db, user, password_hash, full_name, user_in.role)
        elif not user.email_verified and not user.google_sub:
            # An address nobody has proven yet (a pending sign-up, or an account from before
            # verification existed). Whoever completes the link — which needs this new password —
            # gets the account; until then nothing about it changes.
            ev.issue_and_send(db, user, password_hash, full_name, user_in.role)
        else:
            ev.send_account_exists_notice(db, user)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Registration failed due to an internal error")
    return _CHECK_YOUR_EMAIL


class ResendIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


@router.post("/auth/resend-verification", status_code=202)
def resend_verification(payload: ResendIn, db: Session = Depends(deps.get_db)) -> Any:
    """A fresh link for an unverified account (throttled). Same answer for every address."""
    _email_signup_available()
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if user is not None and user.is_active and not user.email_verified and not user.google_sub:
        ev.issue_and_send(db, user, ev.latest_pending_password_hash(db, user))
    return _CHECK_YOUR_EMAIL


@router.post("/auth/email-verification/request", status_code=202)
def request_my_verification(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """A signed-in account from before verification existed asks to verify its address."""
    _email_signup_available()
    if current_user.email_verified:
        return {"ok": True, "email_verified": True}
    sent = ev.issue_and_send(db, current_user, current_user.hashed_password)
    return {"ok": True, "sent": sent}


class VerifyIn(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/auth/verify-email")
def verify_email(payload: VerifyIn, db: Session = Depends(deps.get_db)) -> Any:
    """Completes a sign-up: the link's secret plus the password chosen with it. Signs the user in."""
    try:
        user = ev.complete(db, payload.token, payload.password)
    except ev.VerificationFailed as e:
        messages = {
            "LINK_EXPIRED": ("الرابط ده انتهت صلاحيته. اطلب رابط جديد.", "This link has expired. Ask for a new one."),
            "PASSWORD_MISMATCH": ("كلمة المرور مش هي اللي اخترتها وانت بتسجّل.", "That is not the password chosen at sign-up."),
        }
        ar, en = messages.get(e.code, ("الرابط ده مش صالح أو اتستخدم قبل كده.", "This link is invalid or was already used."))
        raise HTTPException(status_code=400, detail={"code": e.code, "message": ar, "message_en": en})
    return _session(user)



# ── Sign in with Google ───────────────────────────────────────────────────────
# The browser gets an ID token from Google Identity Services and posts it here.
# We verify it with Google's tokeninfo endpoint (no extra dependency) and check
# audience / issuer / expiry / verified e-mail ourselves before trusting it.
# Enabled simply by setting GOOGLE_CLIENT_ID (comma-separated for several clients).

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_SIGNUP_ROLES = {"student", "lecturer"}


def _google_client_ids() -> List[str]:
    raw = os.environ.get("GOOGLE_CLIENT_ID") or ""
    return [c.strip() for c in raw.split(",") if c.strip()]


def _fetch_google_tokeninfo(credential: str) -> Optional[dict]:
    """Network call to Google. Returns the decoded claims, or None if Google rejects the token."""
    try:
        resp = httpx.get(GOOGLE_TOKENINFO_URL, params={"id_token": credential}, timeout=10.0)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach Google to verify the sign-in. Try again.")
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def verify_google_id_token(credential: str, client_ids: List[str]) -> dict:
    claims = _fetch_google_tokeninfo(credential)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid Google credential")
    if claims.get("aud") not in client_ids:
        raise HTTPException(status_code=401, detail="Google credential was issued for a different app")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise HTTPException(status_code=401, detail="Invalid Google credential issuer")
    try:
        exp = int(claims.get("exp", 0))
    except (TypeError, ValueError):
        exp = 0
    if exp <= int(time.time()):
        raise HTTPException(status_code=401, detail="Google credential has expired")
    if str(claims.get("email_verified", "")).lower() != "true":
        raise HTTPException(status_code=401, detail="Google account e-mail is not verified")
    if not claims.get("email"):
        raise HTTPException(status_code=401, detail="Google credential has no e-mail")
    if not str(claims.get("sub") or "").strip():
        raise HTTPException(status_code=401, detail="Google credential has no account id")
    return claims


class GoogleLoginIn(BaseModel):
    credential: str = Field(..., min_length=10, max_length=8192)
    role: Optional[str] = Field(default=None, max_length=32)
    full_name: Optional[str] = Field(default=None, max_length=120)


@router.get("/auth/google/config")
def google_auth_config() -> Any:
    ids = _google_client_ids()
    return {"enabled": bool(ids), "client_id": ids[0] if ids else None}


@router.post("/login/google")
def login_google(
    payload: GoogleLoginIn,
    db: Session = Depends(deps.get_db),
) -> Any:
    client_ids = _google_client_ids()
    if not client_ids:
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured on this server (GOOGLE_CLIENT_ID is not set).",
        )

    role = (payload.role or "").strip().lower() or None
    if role is not None and role not in GOOGLE_SIGNUP_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role. Allowed roles: student, lecturer")

    claims = verify_google_id_token(payload.credential, client_ids)
    email_norm = str(claims["email"]).strip().lower()
    if len(email_norm) > 254:
        raise HTTPException(status_code=400, detail="E-mail address is too long")

    google_name = str(claims.get("name") or "").strip()[:120]
    custom_name = (payload.full_name or "").strip()[:120]
    google_sub = str(claims["sub"]).strip()[:255]

    # 1. This Google account was linked before: it signs in to that account, whatever its e-mail is now.
    linked = db.query(User).filter(User.google_sub == google_sub).first()
    if linked is not None:
        if not linked.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return _session(linked)

    user = db.query(User).filter(User.email == email_norm).first()
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        if user.google_sub and user.google_sub != google_sub:
            # 2. The address belongs to an account tied to a different Google account.
            raise HTTPException(status_code=409, detail={
                "code": "GOOGLE_ACCOUNT_MISMATCH",
                "message": "الحساب ده مربوط بحساب Google تاني.",
                "message_en": "This OralIQ account is linked to a different Google account.",
            })
        if user.email_verified:
            # 3. Both sides proved the same mailbox (the link earlier, Google now): link and sign in.
            user.google_sub = google_sub
            db.commit()
            return _session(user)
        # 4. Nobody had proven this address yet — a pending sign-up, or an account from before
        #    verification existed — and Google just proved who owns it. The owner gets the account
        #    with all its data; any password set by someone else stops working and every earlier
        #    session is voided. Nothing is deleted or merged.
        never_verified_signup = bool(user.requires_email_verification)
        user.google_sub = google_sub
        user.email_verified = True
        user.email_verified_at = datetime.utcnow()
        user.hashed_password = security.get_password_hash(secrets.token_urlsafe(48))
        user.token_version = int(user.token_version or 0) + 1
        if never_verified_signup:
            # It never got a session, so nothing was created in it: let the owner set it up.
            if role in GOOGLE_SIGNUP_ROLES and user.role in GOOGLE_SIGNUP_ROLES:
                user.role = role
            if custom_name or google_name:
                user.full_name = custom_name or google_name
        ev.cancel_outstanding(db, user.id)
        db.commit()
        db.refresh(user)
        print(f"[Auth] e-mail ownership of user #{user.id} proven with Google; password sign-in "
              "reset and earlier sessions revoked", flush=True)
        return _session(user, password_login_disabled=True)

    if user is None:
        if role is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ROLE_REQUIRED",
                    "message": "No account exists for this Google e-mail yet. Choose student or lecturer to create one.",
                    "email": email_norm,
                    "suggested_name": google_name,
                },
            )
        try:
            user = User(
                email=email_norm,
                # Random secret nobody knows: password login stays impossible until a reset.
                hashed_password=security.get_password_hash(secrets.token_urlsafe(48)),
                full_name=(custom_name or google_name or None),
                role=role,
                google_sub=google_sub,
                email_verified=True,                    # Google verified it (email_verified=true)
                email_verified_at=datetime.utcnow(),
                requires_email_verification=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="Could not create the account. Try again.")

    return _session(user)
