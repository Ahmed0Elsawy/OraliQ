"""
Identity and integrity evidence for one answer, built ONLY from what the server itself observed.

Sources and how much they are trusted:
  * Server-verified — face checks this server ran (POST /face/verify → FaceCheck rows) for this
    signed-in student and this exam, within this exam's time window. They give the face score
    and the integrity score (share of checks where the enrolled face was present and alone).
  * Client-reported — the browser's proctoring alerts (gaze, head turns, phone/book...). The
    student's own device produces them and can send anything, including nothing, so they are
    stored for a lecturer to look at and never feed a score or an accusation.
  * Unknown — no or too few server checks. The result says so ("unverified" /
    "insufficient_data"); it is never turned into a pass or into 100.

What a face check does NOT prove: the frame comes from the student's camera through the
browser, so a photo, a replayed video or a virtual camera can pass it (there is no liveness
check), and the checks are only as frequent as the browser sends them. It is evidence for a
lecturer, not proof of presence.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.face_check import FaceCheck
from app.models.question import Question
from app.models.user import User

FACE_VERIFIED, FACE_UNCERTAIN = 55.0, 45.0     # same thresholds as /face/verify and the reports
KNOWN_CLIENT_ALERTS = (
    "gaze_left", "gaze_right", "gaze_down", "gaze_up", "head_turn_left", "head_turn_right",
    "no_face", "multiple_people", "phone_detected", "book_detected", "face_mismatch",
)


def _int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.isdigit() else default


def exam_key_for(question: Question) -> str:
    return question.group_token or question.exam_token


def exam_key_from_token(db: Session, token: Optional[str]) -> Optional[str]:
    """The exam (group token) a face check is taken for, from the token the exam room knows."""
    token = (token or "").strip()[:128]
    if not token:
        return None
    q = db.query(Question).filter((Question.group_token == token) | (Question.exam_token == token)).first()
    return exam_key_for(q) if q else None


def has_faceprint(user: User) -> bool:
    try:
        emb = json.loads(user.face_embedding or "")
        return isinstance(emb, list) and len(emb) > 10
    except ValueError:
        return False


def _exam_window(db: Session, key: str) -> timedelta:
    """How far back a face check still belongs to this sitting of the exam."""
    from app.services.billing_service import _exam_minutes
    grace = _int_env("FACE_CHECK_GRACE_MINUTES", 15)
    return timedelta(minutes=min(_exam_minutes(db, key) + grace, 240))


def _trimmed_mean(values):
    """Same aggregation the exam room used: drop the lowest quarter (a blink, a bad frame)."""
    if len(values) <= 1:
        return values[0] if values else None
    ordered = sorted(values)
    kept = ordered[max(1, len(ordered) // 4):]
    return sum(kept) / len(kept)


def face_evidence(db: Session, user: User, question: Question, now: Optional[datetime] = None,
                  since: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Face score + integrity evidence for `user` answering `question`, from server face checks only.
    `since` is the server-recorded start of the exam sitting (H2): only checks taken during this
    sitting count. Without it (no sitting), the exam's duration back from now is used.
    Keys: face_verification, face_score, face_checks, facial_score, integrity_status, has_faceprint.
    """
    now = now or datetime.utcnow()
    key = exam_key_for(question)
    enrolled = has_faceprint(user)
    start = since if since is not None else now - _exam_window(db, key)
    checks = []
    if enrolled:
        checks = (
            db.query(FaceCheck)
            .filter(FaceCheck.user_id == user.id, FaceCheck.exam_key == key,
                    FaceCheck.created_at >= start, FaceCheck.created_at <= now)
            .all()
        )
    n = len(checks)
    out: Dict[str, Any] = {"face_checks": n, "has_faceprint": enrolled, "face_score": None, "facial_score": None}

    if not enrolled:
        out["face_verification"] = "not_enrolled"
    elif n == 0:
        out["face_verification"] = "unverified"
    else:
        sims = [c.similarity for c in checks if not c.no_face and c.similarity is not None]
        if not sims:
            out["face_verification"] = "no_face"
        else:
            score = round(_trimmed_mean(sims), 1)
            out["face_score"] = score
            out["face_verification"] = (
                "verified" if score >= FACE_VERIFIED else "uncertain" if score >= FACE_UNCERTAIN else "mismatch"
            )

    # Integrity: the share of server checks in which the enrolled face was there, matching, alone.
    if n >= max(1, _int_env("INTEGRITY_MIN_SERVER_CHECKS", 3)):
        good = sum(1 for c in checks if not c.no_face and c.is_match and (c.num_faces in (None, 1)))
        out["facial_score"] = round(100.0 * good / n, 1)
        out["integrity_status"] = "server_sampled"
    else:
        out["integrity_status"] = "insufficient_data"
    return out


def sanitize_client_alerts(raw: Optional[str]) -> str:
    """Known alert names with their reported seconds (clamped), as JSON. Anything else is dropped."""
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return "{}"
    if not isinstance(data, dict):
        return "{}"
    clean = {}
    for k in KNOWN_CLIENT_ALERTS:
        v = data.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            clean[k] = round(min(float(v), 3600.0), 1)
    return json.dumps(clean, sort_keys=True)


def record_face_check(db: Session, user: User, exam_key: Optional[str], result: Optional[Dict[str, Any]],
                      no_face: bool = False) -> FaceCheck:
    row = FaceCheck(
        user_id=user.id, exam_key=exam_key, no_face=no_face,
        similarity=None if no_face or not result else float(result.get("similarity_score") or 0.0),
        is_match=bool(result and result.get("is_match")) and not no_face,
        num_faces=(result or {}).get("num_faces"),
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return row
