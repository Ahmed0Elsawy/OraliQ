"""Shared test helpers for answering exams the way the apps do since H2: an enrolled student, a
fresh exam, and a server-side sitting opened (access-check) before any answer."""
import json

from app.models.question import Question
from app.services import exam_sessions

# Face and voice "enrolled" (the shapes the server checks; the values never reach a model in tests).
ENROLLED = {"voice_embedding": json.dumps([0.1] * 256), "face_embedding": json.dumps([0.01] * 512)}


def new_exam(db, creator_id=None, duration=5, max_attempts=1, **fields) -> Question:
    q = Question(text=fields.pop("text", "سؤال"), model_answer=fields.pop("model_answer", "إجابة"),
                 keywords=fields.pop("keywords", ""), creator_id=creator_id, duration_minutes=duration,
                 max_attempts=max_attempts, **fields)
    db.add(q)
    db.flush()
    q.group_token = q.exam_token
    db.commit()
    db.refresh(q)
    return q


def open_sitting(db, user, question):
    """What GET /exams/access-check does: start (or resume) the user's sitting of that exam."""
    return exam_sessions.start_or_resume(db, user, exam_sessions.exam_key_of(question))


def access_check(client, headers, exam_token):
    r = client.get(f"/api/v1/exams/access-check/{exam_token}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
