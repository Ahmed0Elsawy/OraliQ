"""
H6: when a student may see their grade is decided by the backend for every endpoint, per exam:
'immediate' (shown once graded) or 'manual' (hidden until the exam's lecturer publishes).

Isolated app + temporary SQLite; grading runs through the real worker code with a fake pipeline.
"""
import threading
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
from app.core import security
from app.core.database import Base
from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User
from app.services import results_visibility
from app.tests.exam_helpers import ENROLLED

GRADE_FIELDS = ("overall_score", "nlp_score", "speech_score", "facial_score", "voice_score", "face_score",
                "transcript", "cheat_report", "fluency_report", "face_verification", "integrity_status")


def fake_ai(*args):
    return {"transcript": "إجابة الطالب", "nlp_score": 80.0, "speech_score": 90.0, "voice_score": 90.0,
            "cheat_report": None, "fluency_report": "ok"}


@pytest.fixture()
def env(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'h6.db').as_posix()}",
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

    def user(email, role="student"):
        with Session() as db:
            u = User(email=email, hashed_password="x", full_name=email, role=role, email_verified=True,
                     **(ENROLLED if role == "student" else {}))
            db.add(u)
            db.commit()
            return u.id, {"Authorization": f"Bearer {security.create_access_token(u.id, timedelta(hours=1))}"}

    lect_id, lect = user("lect@t.com", "lecturer")
    _, other_lect = user("other@t.com", "lecturer")
    _, s1 = user("s1@t.com")
    _, s2 = user("s2@t.com")

    def exam(policy="manual", n=1):
        with Session() as db:
            qs = []
            for i in range(n):
                q = Question(text=f"س{i}", model_answer="إجابة نموذجية سرية", creator_id=lect_id,
                             duration_minutes=2, order_index=i, results_policy=policy)
                db.add(q)
                db.flush()
                qs.append(q)
            for q in qs:
                q.group_token = qs[0].exam_token
            db.commit()
            return qs[0].exam_token, [q.id for q in qs]

    def answer(h, token, qid, key):
        assert client.get(f"/api/v1/exams/access-check/{token}", headers=h).status_code == 200
        r = client.post("/api/v1/exams/submit", headers=h, data={
            "question_id": str(qid), "student_name": "S", "student_number": "1", "submission_key": key})
        assert r.status_code in (200, 202), r.text
        return r.json()

    def grade_all():
        w = worker_mod.Worker(Session, 1, pipeline=fake_ai)
        while w.run_one(0) is not None:
            pass

    return {"client": client, "Session": Session, "lect": lect, "other": other_lect, "s1": s1, "s2": s2,
            "exam": exam, "answer": answer, "grade_all": grade_all}


def status(e, h, sub_id):
    r = e["client"].get(f"/api/v1/exams/submissions/{sub_id}/grading", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def blank(body):
    return all(body.get(f) is None for f in GRADE_FIELDS)


def my_grades(e, h):
    return e["client"].get("/api/v1/exams/my-grades", headers=h).json()


def publish(e, h, token):
    return e["client"].post(f"/api/v1/exams/publish-results/{token}", headers=h)


# ── 1 + 2. Choosing the policy when creating an exam ──────────────────────────

def test_1_2_the_lecturer_chooses_the_policy_per_exam(env):
    c, lect = env["client"], env["lect"]
    imm = c.post("/api/v1/questions/", headers=lect, json={"text": "سؤال", "model_answer": "ج", "results_policy": "immediate"}).json()
    man = c.post("/api/v1/questions/", headers=lect, json={"text": "سؤال", "model_answer": "ج", "results_policy": "manual"}).json()
    default = c.post("/api/v1/questions/", headers=lect, json={"text": "سؤال", "model_answer": "ج"}).json()
    assert (imm["results_policy"], man["results_policy"], default["results_policy"]) == ("immediate", "manual", "manual")
    second = c.post("/api/v1/questions/", headers=lect, json={"text": "س2", "model_answer": "ج", "results_policy": "manual",
                                                               "group_token": imm["group_token"]}).json()
    assert second["results_policy"] == "immediate"                  # the exam's policy, inherited
    assert c.post("/api/v1/questions/", headers=lect,
                  json={"text": "سؤال", "model_answer": "ج", "results_policy": "public"}).status_code == 422


# ── 3. Immediate ──────────────────────────────────────────────────────────────

def test_3_immediate_shows_the_grade_once_graded(env):
    tok, qids = env["exam"]("immediate")
    sub = env["answer"](env["s1"], tok, qids[0], "k1")
    assert blank(sub) and sub["result_visible"] is False             # not graded yet
    env["grade_all"]()
    st = status(env, env["s1"], sub["id"])
    assert st["result_visible"] is True and st["overall_score"] is not None and st["transcript"]
    assert [g["id"] for g in my_grades(env, env["s1"])] == [sub["id"]]


# ── 4 + 9 + 10 + 11 + 12. Manual: nothing leaks before publishing ──────────────

def test_4_12_manual_keeps_every_grading_output_from_the_student(env):
    tok, qids = env["exam"]("manual")
    sub = env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    st = status(env, env["s1"], sub["id"])
    assert st["grading_status"] == "completed"                       # they may know it's graded...
    assert st["result_visible"] is False and blank(st)               # ...not how it went
    by_key = env["client"].get("/api/v1/exams/submissions/by-key/k1/grading", headers=env["s1"]).json()
    assert by_key["grading_status"] == "completed" and blank(by_key)
    assert my_grades(env, env["s1"]) == []


def test_9_re_sending_the_key_does_not_reveal_the_grade(env):
    tok, qids = env["exam"]("manual")
    env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    r = env["client"].post("/api/v1/exams/submit", headers=env["s1"], data={
        "question_id": str(qids[0]), "student_name": "S", "student_number": "1", "submission_key": "k1"})
    assert r.status_code == 200 and blank(r.json()) and r.json()["grading_status"] == "completed"


def test_10_11_lecturer_only_lists_stay_closed_to_students(env):
    tok, qids = env["exam"]("manual")
    env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    c, s1 = env["client"], env["s1"]
    for path in ("/api/v1/exams/all-results", f"/api/v1/exams/results/{qids[0]}", "/api/v1/exams/attendance"):
        assert c.get(path, headers=s1).status_code == 403, path
    assert "model_answer" not in str(c.get(f"/api/v1/questions/by-group/{tok}").json())
    assert "إجابة نموذجية سرية" not in c.get(f"/api/v1/questions/by-group/{tok}").text


# ── 5. The lecturer reviews before publishing ─────────────────────────────────

def test_5_the_lecturer_sees_everything_before_publishing(env):
    tok, qids = env["exam"]("manual")
    sub = env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    rows = env["client"].get("/api/v1/exams/all-results", headers=env["lect"]).json()
    assert rows[0]["overall_score"] is not None and rows[0]["transcript"]
    st = status(env, env["lect"], sub["id"])
    assert st["overall_score"] is not None and st["result_visible"] is False   # graded, not yet released


# ── 6 + 7 + 8 + 13 + 17. Publishing ──────────────────────────────────────────

def test_6_13_publishing_releases_each_students_own_grades(env):
    tok, qids = env["exam"]("manual")
    a = env["answer"](env["s1"], tok, qids[0], "k1")
    b = env["answer"](env["s2"], tok, qids[0], "k2")
    env["grade_all"]()
    r = publish(env, env["lect"], tok)
    assert r.status_code == 200 and r.json()["answers_released"] == 2 and r.json()["already_published"] is False
    assert r.json()["published_at"].endswith("Z")
    assert [g["id"] for g in my_grades(env, env["s1"])] == [a["id"]]          # own grades only
    assert status(env, env["s2"], b["id"])["overall_score"] is not None
    assert env["client"].get(f"/api/v1/exams/submissions/{b['id']}/grading", headers=env["s1"]).status_code == 404


def test_7_a_student_cannot_publish(env):
    tok, _ = env["exam"]("manual")
    assert publish(env, env["s1"], tok).status_code == 403
    with env["Session"]() as db:
        assert db.query(Question).one().results_published_at is None


def test_8_another_lecturer_cannot_publish(env):
    tok, _ = env["exam"]("manual")
    assert publish(env, env["other"], tok).status_code == 404
    assert publish(env, env["other"], "no-such-exam").status_code == 404     # same answer
    with env["Session"]() as db:
        assert db.query(Question).one().results_published_at is None


def test_17_publishing_twice_or_concurrently_changes_nothing_more(env):
    tok, qids = env["exam"]("manual")
    env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    first = publish(env, env["lect"], tok).json()
    again = publish(env, env["lect"], tok).json()
    assert again["already_published"] is True and again["published_at"] == first["published_at"]
    assert again["answers_released"] == 0

    tok2, _ = env["exam"]("manual")
    results = []
    with env["Session"]() as db:
        lect = db.query(User).filter(User.email == "lect@t.com").one()
        lect_id = lect.id

    def one():
        db = env["Session"]()
        try:
            results.append(results_visibility.publish(db, db.get(User, lect_id), tok2)["already_published"])
        finally:
            db.close()

    threads = [threading.Thread(target=one) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, True, True, True]
    imm, _ = env["exam"]("immediate")
    r = publish(env, env["lect"], imm)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "RESULTS_ARE_IMMEDIATE"


# ── 14 + 15 + 16. Independence, old exams, answers still in grading ───────────

def test_14_publishing_one_exam_leaves_the_others_hidden(env):
    tok_a, qa = env["exam"]("manual")
    tok_b, qb = env["exam"]("manual")
    env["answer"](env["s1"], tok_a, qa[0], "ka")
    sb = env["answer"](env["s1"], tok_b, qb[0], "kb")
    env["grade_all"]()
    publish(env, env["lect"], tok_a)
    assert [g["question_id"] for g in my_grades(env, env["s1"])] == [qa[0]]
    assert blank(status(env, env["s1"], sb["id"]))


def test_15_old_exams_keep_publishing_answer_by_answer(env):
    tok, qids = env["exam"]("manual")
    sub = env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    # The lecturer's existing per-answer publish still works and is still obeyed.
    r = env["client"].patch(f"/api/v1/exams/submissions/{sub['id']}/visibility?visible=true", headers=env["lect"])
    assert r.status_code == 200
    assert [g["id"] for g in my_grades(env, env["s1"])] == [sub["id"]]
    env["client"].patch(f"/api/v1/exams/submissions/{sub['id']}/visibility?visible=false", headers=env["lect"])
    assert my_grades(env, env["s1"]) == [] and blank(status(env, env["s1"], sub["id"]))


def test_16_answers_graded_after_publishing_are_released_when_they_finish(env):
    tok, qids = env["exam"]("manual", n=2)
    sub = env["answer"](env["s1"], tok, qids[0], "k1")
    publish(env, env["lect"], tok)                                    # published while still queued
    st = status(env, env["s1"], sub["id"])
    assert st["grading_status"] == "queued" and blank(st)
    env["grade_all"]()
    st = status(env, env["s1"], sub["id"])
    assert st["result_visible"] is True and st["overall_score"] is not None


# ── 18 + 19. Queue untouched, history untouched ───────────────────────────────

def test_18_hidden_grades_are_still_graded_and_stored(env):
    tok, qids = env["exam"]("manual")
    sub = env["answer"](env["s1"], tok, qids[0], "k1")
    env["grade_all"]()
    with env["Session"]() as db:
        row = db.get(ExamSubmission, sub["id"])
        assert row.grading_status == "completed" and row.overall_score is not None and row.grade_visible == 0


def test_19_historical_results_are_not_changed(env):
    tok, qids = env["exam"]("manual")
    tok_other, _ = env["exam"]("manual")
    with env["Session"]() as db:
        sid = db.query(User).filter(User.email == "s1@t.com").one().id
        old_pub = ExamSubmission(question_id=qids[0], student_id=sid, student_name="S", student_number="1",
                                 overall_score=88.0, grade_visible=1, grading_status="completed",
                                 submitted_at=datetime(2026, 9, 1))
        db.add(old_pub)
        db.commit()
        old_id = old_pub.id
    assert [g["overall_score"] for g in my_grades(env, env["s1"])] == [88.0]    # published before: still visible
    publish(env, env["lect"], tok_other)
    with env["Session"]() as db:
        row = db.get(ExamSubmission, old_id)
        assert (row.overall_score, row.grade_visible) == (88.0, 1)
