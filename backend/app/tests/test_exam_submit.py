"""
Submitting an answer: the duplicate-grade hole, and the queue that keeps grading off the request.

Submit only stores the answer and its grading job; nothing here loads Whisper. The worker side is
covered in test_grading_queue.py.
"""
import pytest
from fastapi.testclient import TestClient

from app import worker
from app.models.exam_submission import ExamSubmission
from app.models.grading_job import GradingJob
from app.models.question import Question


def _verified_student(db, email: str, name: str):
    """A student whose e-mail is verified and face/voice enrolled (tested elsewhere)."""
    from app.core import security
    from app.models.user import User
    from app.tests.exam_helpers import ENROLLED
    u = User(email=email, hashed_password=security.get_password_hash("password123"), full_name=name,
             role="student", email_verified=True, **ENROLLED)
    db.add(u)
    db.commit()
    return u


@pytest.fixture(scope="module")
def student_token(client: TestClient, db) -> str:
    _verified_student(db, "submit-student@example.com", "Submit Student")
    r = client.post("/api/v1/login/access-token", data={
        "username": "submit-student@example.com",
        "password": "password123",
    })
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _exam(client, db, token, max_attempts=1) -> Question:
    """A fresh one-question exam, opened by the student (access-check starts the sitting, H2)."""
    from app.tests.exam_helpers import access_check, new_exam
    q = new_exam(db, text="اشرح قانون نيوتن الأول", model_answer="الجسم يحفظ حالته", keywords="نيوتن",
                 max_attempts=max_attempts)
    access_check(client, {"Authorization": f"Bearer {token}"}, q.exam_token)
    return q


@pytest.fixture()
def question(client, db, student_token) -> Question:
    return _exam(client, db, student_token)


def _submit(client, token, question_id, key=None, name="Submit Student"):
    data = {
        "question_id": str(question_id),
        "student_name": name,
        "student_number": "2026-001",
        "anti_cheat_alerts": "{}",
    }
    if key:
        data["submission_key"] = key
    return client.post(
        "/api/v1/exams/submit",
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )


def test_a_submission_is_stored_with_its_key(client, student_token, question):
    r = _submit(client, student_token, question.id, key="key-first-answer")
    assert r.status_code == 202, r.text
    assert r.json()["id"]
    assert r.json()["grading_status"] == "queued"


def test_resending_the_same_key_returns_the_first_grade(client, student_token, question, db):
    """
    The bug this closes: grading can outlast the client's timeout, so a student whose request
    appeared to fail used to submit again and the lecturer ended up with two grades for one answer.
    """
    first = _submit(client, student_token, question.id, key="key-retried-answer")
    assert first.status_code == 202, first.text

    again = _submit(client, student_token, question.id, key="key-retried-answer")
    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]

    rows = db.query(ExamSubmission).filter(
        ExamSubmission.submission_key == "key-retried-answer"
    ).count()
    assert rows == 1
    jobs = db.query(GradingJob).filter(GradingJob.submission_id == first.json()["id"]).count()
    assert jobs == 1


def test_different_keys_are_different_answers_only_within_the_attempt_limit(client, student_token, db):
    """A new key is a new answer — counted against the exam's attempts (H2), never swallowed by dedup."""
    q = _exam(client, db, student_token, max_attempts=2)
    a = _submit(client, student_token, q.id, key="key-attempt-a")
    assert a.status_code == 202, a.text
    from app.tests.exam_helpers import access_check
    access_check(client, {"Authorization": f"Bearer {student_token}"}, q.exam_token)   # 2nd sitting
    b = _submit(client, student_token, q.id, key="key-attempt-b")
    assert b.status_code == 202, b.text
    assert a.json()["id"] != b.json()["id"]
    c = client.get(f"/api/v1/exams/access-check/{q.exam_token}", headers={"Authorization": f"Bearer {student_token}"})
    assert c.status_code == 409 and c.json()["detail"]["code"] == "ATTEMPTS_EXHAUSTED"


def test_a_submission_without_a_key_is_still_accepted(client, student_token, question, db):
    """Older clients predate the key; they must keep working, without dedup protection."""
    r = _submit(client, student_token, question.id)
    assert r.status_code == 202, r.text

    row = db.query(ExamSubmission).filter(ExamSubmission.id == r.json()["id"]).one()
    assert row.submission_key is None


def test_several_keyless_submissions_do_not_collide(client, student_token, db):
    """A unique index over NULLs would reject the second one; NULLs must stay exempt."""
    first = _submit(client, student_token, _exam(client, db, student_token).id)
    second = _submit(client, student_token, _exam(client, db, student_token).id)
    assert first.status_code == 202 and second.status_code == 202, second.text
    assert first.json()["id"] != second.json()["id"]


def test_another_students_key_does_not_return_their_submission(client, student_token, question, db):
    """A submission_key is not a capability: presenting someone else's must not leak their grade."""
    _verified_student(db, "submit-other@example.com", "Other")
    other = client.post("/api/v1/login/access-token", data={
        "username": "submit-other@example.com", "password": "password123",
    }).json()["access_token"]
    assert _submit(client, student_token, question.id, key="key-owned-by-first").status_code == 202
    from app.tests.exam_helpers import access_check
    access_check(client, {"Authorization": f"Bearer {other}"}, question.exam_token)
    r = _submit(client, other, question.id, key="key-owned-by-first")
    assert r.status_code == 409


def test_a_missing_question_is_rejected(client, student_token):
    assert _submit(client, student_token, 999_999, key="key-no-question").status_code == 404


def test_submitting_requires_a_signed_in_user(client, db):
    question = Question(text="سؤال", model_answer="إجابة")
    db.add(question)
    db.commit()
    r = client.post("/api/v1/exams/submit", data={
        "question_id": str(question.id),
        "student_name": "Nobody",
        "student_number": "0",
    })
    assert r.status_code in (401, 403)


# ── Grading concurrency ───────────────────────────────────────────────────────

def test_submit_does_not_grade_inside_the_request():
    """
    Grading used to run inside this request: a class finishing together queued past the browser's
    timeout. The endpoint now only stores the answer and its job; the worker grades it.
    """
    import inspect
    from app.api.endpoints import exams
    source = inspect.getsource(exams.submit_exam) + inspect.getsource(exams._accept_submission)
    assert "run_ai_pipeline" not in source
    assert "gq.enqueue" in source


def test_the_number_of_grading_slots_is_bounded(monkeypatch):
    """Each job wants a few cores and about 2GB, so a whole class at once would exhaust memory."""
    monkeypatch.delenv("GRADING_WORKER_CONCURRENCY", raising=False)
    monkeypatch.setenv("MAX_CONCURRENT_GRADING", "3")
    assert worker.worker_concurrency() == 3

    monkeypatch.delenv("MAX_CONCURRENT_GRADING")
    monkeypatch.setattr(worker.os, "cpu_count", lambda: 16)
    assert worker.worker_concurrency() == 4

    monkeypatch.setattr(worker.os, "cpu_count", lambda: 2)
    assert worker.worker_concurrency() == 1

    monkeypatch.setenv("GRADING_WORKER_CONCURRENCY", "2")
    assert worker.worker_concurrency() == 2


def test_grading_slots_ignore_a_nonsense_value(monkeypatch):
    monkeypatch.delenv("GRADING_WORKER_CONCURRENCY", raising=False)
    monkeypatch.setenv("MAX_CONCURRENT_GRADING", "none")
    monkeypatch.setattr(worker.os, "cpu_count", lambda: 8)
    assert worker.worker_concurrency() == 2


def test_whisper_threads_divide_the_machine_between_jobs(monkeypatch):
    """Left unset, every job claims every core and parallel jobs fight each other."""
    from app.services import speech_ai

    monkeypatch.setenv("MAX_CONCURRENT_GRADING", "2")
    monkeypatch.delenv("WHISPER_CPU_THREADS", raising=False)
    monkeypatch.setattr(speech_ai.os, "cpu_count", lambda: 8)
    assert speech_ai._cpu_threads() == 4

    monkeypatch.setenv("WHISPER_CPU_THREADS", "6")
    assert speech_ai._cpu_threads() == 6


def test_the_models_load_once_under_concurrency():
    """Two worker threads reaching an unloaded model used to load a copy each: 2GB wasted."""
    import threading
    from app.services.speech_ai import speech_analyzer
    from app.services.nlp_ai import nlp_analyzer

    for service in (speech_analyzer, nlp_analyzer):
        assert isinstance(service._lock, type(threading.Lock()))
