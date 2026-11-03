"""
Proving that whoever uses an e-mail address owns it.

A password sign-up gets an e-mailed link: 32 random bytes, of which only the SHA-256 is stored,
valid EMAIL_VERIFICATION_TTL_HOURS (default 24), usable once. Completing it also requires the
password chosen at that sign-up, which is applied to the account only then. That closes the
pre-registration hijack: someone who signs up with another person's address never receives the
link, and the address's owner, if they click a link they didn't ask for, can't finish it without
the stranger's password. When the owner finishes their own sign-up, their password replaces
anything set before and every earlier session is voided (token_version).

Sending is rate limited per account (EMAIL_VERIFICATION_RESEND_SECONDS between sends, default 60;
EMAIL_VERIFICATION_MAX_PER_HOUR, default 5). The callers return the same answer whether or not an
account exists, so none of this reveals who is registered.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core import security
from app.models.email_verification import EmailVerificationToken
from app.models.user import User
from app.services import mailer

MAX_FAILED_PASSWORD_ATTEMPTS = 5
SELF_SERVICE_ROLES = ("student", "lecturer")


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


def ttl() -> timedelta:
    return timedelta(hours=_int_env("EMAIL_VERIFICATION_TTL_HOURS", 24))


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


def may_send(db: Session, user: User) -> bool:
    """Per-account throttle on verification e-mails."""
    now = _now()
    last = (
        db.query(EmailVerificationToken.created_at)
        .filter(EmailVerificationToken.user_id == user.id)
        .order_by(EmailVerificationToken.created_at.desc())
        .first()
    )
    if last and (now - last[0]).total_seconds() < _int_env("EMAIL_VERIFICATION_RESEND_SECONDS", 60):
        return False
    recent = (
        db.query(EmailVerificationToken.id)
        .filter(EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.created_at >= now - timedelta(hours=1))
        .count()
    )
    return recent < _int_env("EMAIL_VERIFICATION_MAX_PER_HOUR", 5)


def issue_and_send(
    db: Session, user: User, pending_password_hash: str,
    pending_full_name: Optional[str] = None, pending_role: Optional[str] = None,
) -> bool:
    """Creates a link and e-mails it. Returns False when throttled or the mail could not be sent."""
    if not may_send(db, user):
        return False
    raw = secrets.token_urlsafe(32)
    row = EmailVerificationToken(
        user_id=user.id, token_hash=hash_token(raw), sent_to=user.email,
        created_at=_now(), expires_at=_now() + ttl(),
        pending_password_hash=pending_password_hash,
        pending_full_name=pending_full_name, pending_role=pending_role,
    )
    db.add(row)
    db.commit()
    link = f"{mailer.frontend_base()}/verify-email#token={raw}"
    hours = int(ttl().total_seconds() // 3600)
    try:
        mailer.send(
            user.email,
            "OralIQ — أكّد بريدك الإلكتروني / Confirm your e-mail",
            "اضغط على الرابط ده عشان تأكّد إن البريد ده بتاعك، وهتحتاج كلمة المرور اللي اخترتها وانت بتسجّل:\n"
            f"{link}\n\nالرابط صالح {hours} ساعة ولمرة واحدة. لو انت ماعملتش حساب على OralIQ، تجاهل الرسالة دي.\n\n"
            "Open this link to confirm this e-mail address is yours. You will need the password you chose "
            f"when signing up:\n{link}\n\nThe link works once and expires in {hours} hours. "
            "If you did not sign up for OralIQ, ignore this message.\n",
        )
    except mailer.MailError as e:
        print(f"[EmailVerification] could not send to user #{user.id}: {e}", flush=True)
        return False
    return True


def send_account_exists_notice(db: Session, user: User) -> None:
    """Someone tried to sign up with an address that already has a verified account: tell its owner
    (throttled like links), and answer the sign-up exactly as for a new address."""
    now = _now()
    if not may_send(db, user):
        return
    # Record the send in the same throttle, with a link nobody can use (random hash, already used).
    db.add(EmailVerificationToken(
        user_id=user.id, token_hash=hash_token(secrets.token_urlsafe(32)), sent_to=user.email,
        created_at=now, expires_at=now, used_at=now, pending_password_hash="!",
    ))
    db.commit()
    try:
        mailer.send(
            user.email,
            "OralIQ — عندك حساب بالفعل / You already have an account",
            "حد حاول يعمل حساب جديد على OralIQ بالبريد ده، وانت عندك حساب بيه بالفعل. سجّل دخولك عادي؛ "
            "لو ماكنتش انت، مفيش حاجة اتغيرت في حسابك.\n\n"
            "Someone tried to create an OralIQ account with this e-mail, which already has one. Just sign "
            "in; if it wasn't you, nothing about your account changed.\n",
        )
    except mailer.MailError as e:
        print(f"[EmailVerification] notice to user #{user.id} not sent: {e}", flush=True)


def latest_pending_password_hash(db: Session, user: User) -> str:
    """The password a resend should carry: the newest outstanding sign-up's, else the account's own."""
    row = (
        db.query(EmailVerificationToken.pending_password_hash)
        .filter(EmailVerificationToken.user_id == user.id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > _now())
        .order_by(EmailVerificationToken.created_at.desc())
        .first()
    )
    return row[0] if row else user.hashed_password


def cancel_outstanding(db: Session, user_id: int) -> None:
    db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.user_id == user_id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=_now())
    )


class VerificationFailed(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code   # LINK_INVALID | LINK_EXPIRED | PASSWORD_MISMATCH


def complete(db: Session, raw_token: str, password: str) -> User:
    """Checks link + password, then hands the account to whoever proved both. Single use."""
    row = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == hash_token(raw_token))
        .first()
    )
    if row is None or row.used_at is not None or row.pending_password_hash == "!":
        raise VerificationFailed("LINK_INVALID")
    if row.expires_at <= _now():
        raise VerificationFailed("LINK_EXPIRED")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or (user.email or "").lower() != (row.sent_to or "").lower():
        raise VerificationFailed("LINK_INVALID")
    if not security.verify_password(password or "", row.pending_password_hash):
        row.failed_attempts = (row.failed_attempts or 0) + 1
        if row.failed_attempts >= MAX_FAILED_PASSWORD_ATTEMPTS:
            row.used_at = _now()   # too many guesses: this link is spent
        db.commit()
        raise VerificationFailed("PASSWORD_MISMATCH")

    # Single use even under concurrent requests: only one UPDATE can flip used_at.
    claimed = db.execute(
        update(EmailVerificationToken)
        .where(EmailVerificationToken.id == row.id, EmailVerificationToken.used_at.is_(None))
        .values(used_at=_now())
    ).rowcount
    if claimed != 1:
        db.rollback()
        raise VerificationFailed("LINK_INVALID")

    never_verified_signup = bool(user.requires_email_verification) and not user.email_verified
    user.hashed_password = row.pending_password_hash
    user.email_verified = True
    user.email_verified_at = _now()
    user.token_version = int(user.token_version or 0) + 1   # anyone signed in before loses access
    if never_verified_signup:
        # A sign-up that never got in: take the name and role of the sign-up that was proven.
        if row.pending_full_name:
            user.full_name = row.pending_full_name
        if row.pending_role in SELF_SERVICE_ROLES and user.role in SELF_SERVICE_ROLES:
            user.role = row.pending_role
    cancel_outstanding(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def is_verified_or_legacy_allowed(user: User) -> Tuple[bool, str]:
    """May this account sign in with a password? (ok, reason-code)."""
    if user.email_verified:
        return True, ""
    if user.requires_email_verification:
        return False, "EMAIL_NOT_VERIFIED"
    policy = (os.environ.get("LEGACY_UNVERIFIED_PASSWORD_LOGIN") or "allow").strip().lower()
    return (policy != "block"), "EMAIL_NOT_VERIFIED"
