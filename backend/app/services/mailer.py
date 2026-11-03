"""
Outgoing e-mail for account verification. Standard library only (smtplib), no provider SDK: any
SMTP account works (a transactional e-mail service, Google Workspace, the host's relay).

EMAIL_BACKEND
  smtp     SMTP_HOST, SMTP_PORT (587), SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM,
           SMTP_SECURITY = starttls (default) | ssl | none
  console  prints the message (development only; refused in production, it would log links)
  memory   keeps messages in `outbox` (tests)
Default: smtp when SMTP_HOST is set, console in dev, memory in test, nothing in production.

Production also needs FRONTEND_URL on https, since that is where the links point. Without a
working configuration, password sign-up answers "unavailable" and Google sign-in is unaffected.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Optional

outbox: List[EmailMessage] = []


class MailError(Exception):
    pass


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _run_mode() -> str:
    from app.core.config import ConfigError, current_env
    try:
        return current_env()
    except ConfigError:
        return "production"


def backend() -> Optional[str]:
    chosen = _env("EMAIL_BACKEND").lower()
    mode = _run_mode()
    if not chosen:
        chosen = "smtp" if _env("SMTP_HOST") else {"dev": "console", "test": "memory"}.get(mode, "")
    if chosen not in ("smtp", "console", "memory"):
        return None
    if mode == "production" and chosen != "smtp":
        return None
    return chosen


def frontend_base() -> Optional[str]:
    url = _env("FRONTEND_URL").rstrip("/")
    if _run_mode() == "production":
        return url if url.startswith("https://") else None
    return url or "http://localhost:5173"


def configured() -> bool:
    b = backend()
    if b is None or frontend_base() is None:
        return False
    if b == "smtp":
        return bool(_env("SMTP_HOST") and _env("SMTP_FROM"))
    return True


def send(to: str, subject: str, text: str) -> None:
    b = backend()
    if not configured():
        raise MailError("e-mail is not configured")
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = _env("SMTP_FROM", "OralIQ <no-reply@localhost>")
    msg["Subject"] = subject
    msg.set_content(text)
    if b == "memory":
        outbox.append(msg)
        return
    if b == "console":
        print(f"[Mailer:console] To: {to}\nSubject: {subject}\n\n{text}\n", flush=True)
        return
    host, port = _env("SMTP_HOST"), int(_env("SMTP_PORT", "587") or 587)
    security = _env("SMTP_SECURITY", "starttls").lower()
    user, password = _env("SMTP_USERNAME"), os.environ.get("SMTP_PASSWORD", "")
    try:
        context = ssl.create_default_context()
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
        with server:
            if security == "starttls":
                server.starttls(context=context)
            if user:
                server.login(user, password)
            server.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        # Never echo the server's reply verbatim: some include the login name.
        raise MailError(f"SMTP delivery failed ({type(e).__name__})") from None
