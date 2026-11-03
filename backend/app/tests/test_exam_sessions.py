"""
H2: the server decides who may sit an exam, when the sitting started and ends, and how many
attempts there are — for direct API calls and concurrent requests too.

Isolated app + temporary SQLite (real connections, so races are real). No AI runs: grading uses a
fake pipeline through the real worker code.
"""
import threading
import time
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app import worker as worker_mod
from app.api import deps
from app.api.api_router import api_router
from app.api.endpoints import exams as exams_ep
from app.core import security
from app.core.database import Base
from app.models.exam_sitting import ExamSitting
from app.models.exam_submission import ExamSubmission
from app.models.face_check import FaceCheck
from app.models.grading_job import GradingJob
from app.models.question import Question
from app.models.user import User
from app.services import exam_sessions
from app.services import grading_queue as gq
from app.tests.exam_helpers import ENROLLED


def fake_ai(*args):
    return {"transcript": "t", "nlp_score": 80.0, "speech_score": 90.0, "voice_score": 90.0,
            "cheat_report": None, "fluency_report": "ok"}


@pytest.fixture()
def env(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'h2.db').as_posix()}",
                           connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[deps.get_db] = _get_db
    client = TestClient(app)

    def user(email, role="student", enrolled=True):
        with Session() as db:
            u = User(email=email, hashed_password="x", full_name=email, role=role, email_verified=True,
                     **(ENROLLED if enrolled else {}))
            db.add(u)
            db.commit()
            return u.id, {"Authorization": f"Bearer {security.create_access_token(u.id, timedelta(hours=1))}"}

    lect_id, lect = user("lect@t.com", "lecturer", enrolled=False)

    def exam(durations=(2, 3), max_attempts=1):
        """An exam (one group) with one question per duration; returns (token, [question ids])."""
        with Session() as db:
            qs = []
            for i, d in enumerate(durations):
                q = Question(text=f"س{i}", model_answer="إجابة", creator_id=lect_id, duration_minutes=d,
                             order_index=i, max_attempts=max_attempts)
                db.add(q)
                db.flush()
                qs.append(q)
            for q in qs:
                q.group_token = qs[0].exam_token
            db.commit()
            return qs[0].exam_token, [q.id for q in qs]

    return {"client": client, "Session": Session, "user": user, "exam": exam, "lect": lect}


def check(e, h, token):
    return e["client"].get(f"/api/v1/exams/access-check/{token}", headers=h)


def submit(e, h, qid, key, **extra):
    data = {"question_id": str(qid), "student_name": "S", "student_number": "1", "submission_key": key}
    data.update({k: str(v) for k, v in extra.items()})
    return e["client"].post("/api/v1/exams/submit", headers=h, data=data)


def code(r):
    return r.json()["detail"]["code"]


def count(e, model, **filters):
    with e["Session"]() as db:
        q = db.query(model)
        for k, v in filters.items():
            q = q.filter(getattr(model, k) == v)
        return q.count()


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", ""))


# ── 1 + 2. Starting a sitting ─────────────────────────────────────────────────

def test_1_access_check_starts_a_server_timed_sitting(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2, 3))
    before = datetime.utcnow()
    r = check(env, h, tok)
    assert r.status_code == 200, r.text
    s = r.json()["session"]
    started, deadline = parse(s["started_at"]), parse(s["deadline_at"])
    assert before - timedelta(seconds=2) <= started <= datetime.utcnow()
    assert deadline - started == timedelta(minutes=2 + 3 + 3)     # question time + 3 min grace
    assert s["deadline_at"].endswith("Z") and s["status"] == "active"
    assert s["attempt_no"] == 1 and s["max_attempts"] == 1 and s["answered_question_ids"] == []
    assert 470 <= s["remaining_seconds"] <= 480


def test_2_who_may_not_start(env):
    _, unenrolled = env["user"]("u@t.com", enrolled=False)
    tok, _ = env["exam"]()
    assert env["client"].get(f"/api/v1/exams/access-check/{tok}").status_code in (401, 403)
    r = check(env, unenrolled, tok)
    assert r.status_code == 403 and code(r) == "BIOMETRICS_REQUIRED"
    assert check(env, unenrolled, "no-such-exam").status_code == 404
    assert count(env, ExamSitting) == 0


# ── 3 + 4 + 13 + 14. Answers need this user's sitting of this exam ──────────

def test_3_14_a_question_from_another_exam_is_refused(env):
    _, h = env["user"]("s@t.com")
    tok_a, _ = env["exam"]()
    _, qids_b = env["exam"]()
    check(env, h, tok_a)
    r = submit(env, h, qids_b[0], "k1")
    assert r.status_code == 409 and code(r) == "NO_ACTIVE_SESSION"
    assert count(env, ExamSubmission) == 0


def test_4_no_sitting_no_answer_even_for_a_direct_call(env):
    _, h = env["user"]("s@t.com")
    _, qids = env["exam"]()
    r = submit(env, h, qids[0], "k1", face_score=100)
    assert r.status_code == 409 and code(r) == "NO_ACTIVE_SESSION"
    _, unenrolled = env["user"]("u@t.com", enrolled=False)
    assert code(submit(env, unenrolled, qids[0], "k2")) == "BIOMETRICS_REQUIRED"
    assert count(env, ExamSubmission) == 0 and count(env, GradingJob) == 0


def test_13_another_students_sitting_cannot_be_used(env):
    _, a = env["user"]("a@t.com")
    _, b = env["user"]("b@t.com")
    tok, qids = env["exam"]()
    check(env, b, tok)
    assert code(submit(env, a, qids[0], "k-a")) == "NO_ACTIVE_SESSION"


# ── 5 + 6. Time comes from the server ─────────────────────────────────────────

def test_5_answers_after_the_deadline_are_refused(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]()
    check(env, h, tok)
    with env["Session"]() as db:
        s = db.query(ExamSitting).one()
        s.deadline_at = datetime.utcnow() - timedelta(seconds=60)      # inside the 90 s upload grace
        db.commit()
    assert submit(env, h, qids[0], "k-late-ok").status_code == 202
    with env["Session"]() as db:
        s = db.query(ExamSitting).one()
        s.deadline_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    r = submit(env, h, qids[1], "k-too-late")
    assert r.status_code == 409 and code(r) == "SESSION_EXPIRED"
    with env["Session"]() as db:
        assert db.query(ExamSitting).one().status == "expired"


def test_6_forged_start_and_finish_times_are_ignored(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]()
    started = parse(check(env, h, tok).json()["session"]["started_at"])
    r = submit(env, h, qids[0], "k1", started_at="2020-01-01T00:00:00Z", finished_at="2099-01-01T00:00:00Z")
    assert r.status_code == 202
    with env["Session"]() as db:
        sub = db.get(ExamSubmission, r.json()["id"])
        assert sub.started_at.replace(tzinfo=None) == started
        assert abs((sub.finished_at.replace(tzinfo=None) - datetime.utcnow()).total_seconds()) < 5


# ── 7 + 8. Reload and reconnect ───────────────────────────────────────────────

def test_7_reopening_the_exam_never_restarts_the_clock(env):
    _, h = env["user"]("s@t.com")
    tok, _ = env["exam"]()
    first = check(env, h, tok).json()["session"]
    time.sleep(1.1)
    again = check(env, h, tok).json()["session"]
    assert again["id"] == first["id"] and again["deadline_at"] == first["deadline_at"]
    assert again["remaining_seconds"] < first["remaining_seconds"]
    assert count(env, ExamSitting) == 1


def test_8_a_dropped_connection_resumes_the_same_sitting(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]()
    sid = check(env, h, tok).json()["session"]["id"]
    assert submit(env, h, qids[0], "k1").status_code == 202
    resumed = check(env, h, tok).json()["session"]
    assert resumed["id"] == sid and resumed["answered_question_ids"] == [qids[0]]
    assert submit(env, h, qids[1], "k2").status_code == 202
    with env["Session"]() as db:
        assert db.query(ExamSitting).one().status == "completed"


# ── 9 + 10 + 11 + 12. Attempts ────────────────────────────────────────────────

def test_9_attempts_are_capped_per_exam(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,), max_attempts=2)
    for attempt in (1, 2):
        s = check(env, h, tok).json()["session"]
        assert s["attempt_no"] == attempt
        r = submit(env, h, qids[0], f"k{attempt}")
        assert r.status_code == 202 and r.json()["attempt_no"] == attempt
    r = check(env, h, tok)
    assert r.status_code == 409 and code(r) == "ATTEMPTS_EXHAUSTED"
    assert code(submit(env, h, qids[0], "k3")) in ("NO_ACTIVE_SESSION", "ATTEMPTS_EXHAUSTED")
    assert count(env, ExamSubmission) == 2


def test_9b_a_question_is_answered_once_per_sitting(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2, 3), max_attempts=3)
    check(env, h, tok)
    assert submit(env, h, qids[0], "k1").status_code == 202
    r = submit(env, h, qids[0], "k2")
    assert r.status_code == 409 and code(r) == "ALREADY_ANSWERED"


def test_10_concurrent_answers_cannot_exceed_the_limit(env):
    uid, _ = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,), max_attempts=1)
    with env["Session"]() as db:
        exam_sessions.start_or_resume(db, db.get(User, uid), tok)
    barrier = threading.Barrier(4)
    results = []

    def one(i):
        db = env["Session"]()
        try:
            barrier.wait()
            sub, created = exams_ep._accept_submission(
                db, db.get(User, uid), db.get(Question, qids[0]), key=f"race-{i}", student_name="S",
                student_number="1", audio=None, audio_suffix=None, anti_cheat_alerts="{}", face_score=None,
                started_at=None, finished_at=None, t0=time.perf_counter())
            results.append(("ok", created))
        except Exception as e:  # noqa: BLE001 — the refusal is the point
            results.append(("refused", getattr(e, "detail", {}).get("code") if hasattr(e, "detail") else str(e)))
        finally:
            db.close()

    threads = [threading.Thread(target=one, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r for r in results if r[0] == "ok"] == [("ok", True)], results
    assert all(r[1] in ("ATTEMPT_CONFLICT", "ALREADY_ANSWERED", "NO_ACTIVE_SESSION", "ATTEMPTS_EXHAUSTED")
               for r in results if r[0] == "refused"), results
    assert count(env, ExamSubmission) == 1


def test_10b_concurrent_starts_make_one_sitting(env):
    uid, _ = env["user"]("s@t.com")
    tok, _ = env["exam"]()
    barrier = threading.Barrier(4)
    ids = []

    def one():
        db = env["Session"]()
        try:
            barrier.wait()
            ids.append(exam_sessions.start_or_resume(db, db.get(User, uid), tok).id)
        finally:
            db.close()

    threads = [threading.Thread(target=one) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(ids)) == 1 and count(env, ExamSitting) == 1


def test_11_resending_the_same_key_is_not_a_new_attempt(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,))
    check(env, h, tok)
    first = submit(env, h, qids[0], "same")
    for _ in range(3):
        again = submit(env, h, qids[0], "same")           # even after the sitting completed
        assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert count(env, ExamSubmission) == 1 and first.json()["attempt_no"] == 1


def test_12_regrading_in_the_queue_is_not_a_new_attempt(env, monkeypatch):
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "1")
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,))
    check(env, h, tok)
    sub_id = submit(env, h, qids[0], "k1").json()["id"]
    w = worker_mod.Worker(env["Session"], 1, pipeline=lambda *a: (_ for _ in ()).throw(RuntimeError("asr down")))
    assert w.run_one(0) == "failed"
    with env["Session"]() as db:
        assert gq.requeue_failed(db, db.query(GradingJob).one())
    assert worker_mod.Worker(env["Session"], 1, pipeline=fake_ai).run_one(0) == "completed"
    with env["Session"]() as db:
        sub = db.get(ExamSubmission, sub_id)
        assert sub.attempt_no == 1 and db.query(ExamSubmission).count() == 1
    assert code(check(env, h, tok)) == "ATTEMPTS_EXHAUSTED"


# ── 15 + 16 + 17. H1, C1 and history ──────────────────────────────────────────

def test_15_face_evidence_counts_only_checks_inside_the_sitting(env):
    uid, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,))
    with env["Session"]() as db:   # checks from before the sitting started (e.g. a previous visit)
        for _ in range(4):
            db.add(FaceCheck(user_id=uid, exam_key=tok, similarity=90.0, is_match=True,
                             created_at=datetime.utcnow() - timedelta(minutes=1)))
        db.commit()
    check(env, h, tok)
    with env["Session"]() as db:
        for _ in range(3):
            db.add(FaceCheck(user_id=uid, exam_key=tok, similarity=80.0, is_match=True, created_at=datetime.utcnow()))
        db.commit()
    sub_id = submit(env, h, qids[0], "k1").json()["id"]
    with env["Session"]() as db:   # stored evidence (the student's reply hides it until released, H6)
        row = db.get(ExamSubmission, sub_id)
        assert (row.face_checks, row.face_score, row.face_verification) == (3, 80.0, "verified")


def test_16_answers_still_flow_through_the_queue(env):
    _, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,))
    check(env, h, tok)
    body = submit(env, h, qids[0], "k1").json()
    assert body["grading_status"] == "queued"
    assert worker_mod.Worker(env["Session"], 1, pipeline=fake_ai).run_one(0) == "completed"
    with env["Session"]() as db:
        assert db.get(ExamSubmission, body["id"]).grading_status == "completed"


def test_17_historical_answers_are_untouched_but_count_as_attempts(env):
    uid, h = env["user"]("s@t.com")
    tok, qids = env["exam"]((2,))
    with env["Session"]() as db:
        db.add(ExamSubmission(question_id=qids[0], student_id=uid, student_name="Old", student_number="1",
                              overall_score=77.0, started_at=datetime(2026, 9, 1), grading_status="completed"))
        db.commit()
    r = check(env, h, tok)
    assert r.status_code == 409 and code(r) == "ATTEMPTS_EXHAUSTED"
    with env["Session"]() as db:
        old = db.query(ExamSubmission).one()
        assert (old.overall_score, old.attempt_no, old.exam_sitting_id) == (77.0, None, None)
        assert old.started_at == datetime(2026, 9, 1)


def test_lecturer_sets_attempts_for_the_whole_exam(env):
    c, lect = env["client"], env["lect"]
    first = c.post("/api/v1/questions/", headers=lect,
                   json={"text": "س1", "model_answer": "ج", "duration_minutes": 2, "max_attempts": 3}).json()
    second = c.post("/api/v1/questions/", headers=lect,
                    json={"text": "س2", "model_answer": "ج", "duration_minutes": 2, "max_attempts": 9,
                          "group_token": first["group_token"]}).json()
    assert first["max_attempts"] == 3 and second["max_attempts"] == 3          # inherited, not 9
    public = c.get(f"/api/v1/questions/by-group/{first['group_token']}").json()
    assert {q["max_attempts"] for q in public} == {3}
    assert c.post("/api/v1/questions/", headers=lect,
                  json={"text": "س", "model_answer": "ج", "max_attempts": 0}).status_code == 422
