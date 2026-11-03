"""
A lecturer reaches only the students who took one of their exams — enforced by the API itself,
so requests sent straight to it get the same refusals as the web and mobile apps.

Isolated app + temporary SQLite; all data is made up.
"""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.api import deps
from app.api.api_router import api_router
from app.core import security
from app.core.database import Base
from app.models.exam_assignment import ExamAssignment
from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User

STUDENT_KEYS = {"id", "full_name", "email", "has_voiceprint", "has_faceprint", "voice_locked", "face_locked",
                "voice_reenroll_allowed"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'access.db').as_posix()}", connect_args={"check_same_thread": False})
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
    monkeypatch.setenv("BILLING_SANDBOX", "1")
    client = TestClient(app)

    def user(email, role, **fields):
        with Session() as db:
            u = User(email=email, hashed_password="x", full_name=email.split("@")[0], role=role,
                     email_verified=True, **fields)
            db.add(u)
            db.commit()
            return u.id, {"Authorization": f"Bearer {security.create_access_token(u.id, timedelta(hours=1))}"}

    def question(owner_id):
        with Session() as db:
            q = Question(text="سؤال", model_answer="إجابة", creator_id=owner_id)
            db.add(q)
            db.commit()
            return q.id

    def took_exam(student_id, question_id):
        with Session() as db:
            db.add(ExamSubmission(question_id=question_id, student_id=student_id, student_name="s",
                                  student_number="1", grading_status="completed"))
            db.commit()

    def legacy_assignment(student_id, question_id, by):
        with Session() as db:
            db.add(ExamAssignment(question_id=question_id, student_id=student_id, assigned_by=by))
            db.commit()

    # Lecturer A has a student who took A's exam; lecturer B has another. "outsider" took nobody's
    # exam; "probed" was assigned to A by id under the old rules but never took an exam.
    a_id, a = user("lect-a@t.com", "lecturer")
    b_id, b = user("lect-b@t.com", "lecturer")
    qa, qb = question(a_id), question(b_id)
    s1, s1h = user("student1@t.com", "student")
    s2, _ = user("student2@t.com", "student")
    outsider, _ = user("outsider@t.com", "student")
    probed, _ = user("probed@t.com", "student")
    took_exam(s1, qa)
    took_exam(s2, qb)
    legacy_assignment(probed, qa, a_id)
    return {
        "client": client, "Session": Session, "user": user, "question": question, "took_exam": took_exam,
        "a": a, "a_id": a_id, "b": b, "qa": qa, "qb": qb, "s1": s1, "s1h": s1h, "s2": s2,
        "outsider": outsider, "probed": probed,
    }


def students(e, headers, **params):
    r = e["client"].get("/api/v1/exams/students", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def assign(e, headers, student_id, question_id=None):
    return e["client"].post("/api/v1/exams/assign", headers=headers,
                            json={"question_id": question_id or e["qa"], "student_id": student_id})


def assignment_count(e):
    with e["Session"]() as db:
        return db.query(ExamAssignment).count()


# ── 1 + 2. Each lecturer sees their own students only ─────────────────────────

def test_1_a_lecturer_sees_exactly_the_students_who_took_their_exams(env):
    listed = students(env, env["a"])
    assert [s["id"] for s in listed] == [env["s1"]]
    assert env["probed"] not in [s["id"] for s in listed]   # an old by-id assignment no longer links


def test_2_a_lecturer_never_sees_another_lecturers_students(env):
    assert env["s2"] not in [s["id"] for s in students(env, env["a"])]
    assert [s["id"] for s in students(env, env["b"])] == [env["s2"]]


# ── 3 + 4 + 5. Assigning and acting on arbitrary ids ──────────────────────────

def test_3_assigning_an_arbitrary_student_id_is_refused(env):
    before = assignment_count(env)
    for sid in (env["outsider"], env["s2"], env["probed"], 999_999):
        r = assign(env, env["a"], sid)
        assert r.status_code == 404, sid
    assert assignment_count(env) == before


def test_4_probing_ids_reveals_nothing(env):
    """A missing id, a lecturer's id, another lecturer's student and an unrelated student all look alike."""
    probes = [999_999, env["a_id"], env["s2"], env["outsider"]]
    for path in ("/api/v1/exams/assign", "/api/v1/voice/allow-reenroll/{sid}", "/api/v1/voice/revoke-reenroll/{sid}"):
        answers = set()
        for sid in probes:
            if path.endswith("assign"):
                r = assign(env, env["a"], sid)
            else:
                r = env["client"].post(path.format(sid=sid), headers=env["a"])
            answers.add((r.status_code, r.text))
        assert len(answers) == 1, (path, answers)
        assert answers.pop()[0] == 404


def test_5_reenroll_permissions_of_an_unrelated_student_cannot_be_changed(env):
    with env["Session"]() as db:
        db.get(User, env["outsider"]).voice_embedding = "[" + "0.1," * 30 + "0.1]"
        db.commit()
    assert env["client"].post(f"/api/v1/voice/allow-reenroll/{env['outsider']}", headers=env["a"]).status_code == 404
    with env["Session"]() as db:
        assert db.get(User, env["outsider"]).voice_reenroll_allowed is False


# ── 6 + 7. What the lists contain ─────────────────────────────────────────────

def test_6_emails_appear_only_for_the_lecturers_own_students(env):
    listed = students(env, env["a"])
    assert listed[0]["email"] == "student1@t.com"
    att = env["client"].get("/api/v1/exams/attendance", headers=env["a"]).json()
    emails = {row["email"] for row in att}
    assert "student1@t.com" in emails
    assert "probed@t.com" not in emails                     # legacy by-id assignment: no e-mail
    assert all("student2" not in row["email"] and "outsider" not in row["email"] for row in att)


def test_7_no_parameter_widens_the_list(env):
    base = students(env, env["a"])
    for params in ({"limit": 100000}, {"skip": 0, "role": "all"}, {"student_id": env["outsider"]},
                   {"search": "@"}, {"lecturer_id": env["qb"]}, {"all": "true", "page": 2}):
        assert students(env, env["a"], **params) == base


# ── 8 + 9. Who can sign up as what ────────────────────────────────────────────

def test_8_self_serve_lecturer_sign_up_gets_no_session_and_no_students(env):
    """Policy (owner's decision): lecturers may sign up themselves. They still prove their e-mail
    before any session, and a new lecturer reaches no student at all."""
    c = env["client"]
    r = c.post("/api/v1/register", json={"email": "new-lect@t.com", "password": "pass-1234", "role": "lecturer"})
    assert r.status_code == 202 and "access_token" not in r.text
    assert c.post("/api/v1/login/access-token",
                  data={"username": "new-lect@t.com", "password": "pass-1234"}).status_code == 403
    _, fresh = env["user"]("fresh-lect@t.com", "lecturer")
    assert students(env, fresh) == []
    for sid in (env["s1"], env["s2"], env["outsider"]):
        assert assign(env, fresh, sid, env["question"](None)).status_code in (403, 404)


@pytest.mark.parametrize("role", ["admin", "hr", "Admin", " hr "])
def test_9_admin_and_hr_cannot_be_chosen_at_sign_up(env, role):
    c = env["client"]
    assert c.post("/api/v1/register", json={"email": "x@t.com", "password": "pass-1234", "role": role}).status_code == 422
    with env["Session"]() as db:
        assert db.query(User).filter(User.email == "x@t.com").count() == 0


# ── 10 + 11. Existing admin / HR rights unchanged ─────────────────────────────

def test_10_admins_keep_platform_wide_access(env):
    admin_id, admin = env["user"]("root@t.com", "admin")
    ids = {s["id"] for s in students(env, admin)}
    assert {env["s1"], env["s2"], env["outsider"], env["probed"]} <= ids
    assert assign(env, admin, env["outsider"]).status_code == 200      # any question, any student
    with env["Session"]() as db:
        assert db.get(User, admin_id).role == "admin"


def test_11_hr_accounts_follow_the_lecturer_rule(env):
    hr_id, hr = env["user"]("hr@t.com", "hr")
    q = env["question"](hr_id)
    assert students(env, hr) == []
    assert assign(env, hr, env["s1"], q).status_code == 404
    env["took_exam"](env["s1"], q)
    assert [s["id"] for s in students(env, hr)] == [env["s1"]]
    assert assign(env, hr, env["s1"], q).status_code == 200


# ── 12 + 13. Students and direct calls ────────────────────────────────────────

def test_12_students_cannot_see_other_students(env):
    c, h = env["client"], env["s1h"]
    assert c.get("/api/v1/exams/students", headers=h).status_code == 403
    assert c.get("/api/v1/exams/attendance", headers=h).status_code == 403
    assert assign(env, h, env["s2"]).status_code == 403
    assert c.post(f"/api/v1/voice/allow-reenroll/{env['s2']}", headers=h).status_code == 403
    assert c.get("/api/v1/exams/all-results", headers=h).status_code == 403


def test_13_direct_calls_get_the_same_refusals(env):
    c = env["client"]
    assert c.get("/api/v1/exams/students").status_code in (401, 403)                 # no token
    assert c.get("/api/v1/exams/students", headers={"Authorization": "Bearer forged"}).status_code in (401, 403)
    # Another lecturer's exam can't be sent, even to one's own student.
    assert assign(env, env["a"], env["s1"], env["qb"]).status_code == 403


def test_team_form_does_not_reveal_what_an_address_is(env):
    env["client"].post("/api/v1/billing/checkout", json={"plan_id": "campus"}, headers=env["a"])
    answers = {
        (r.status_code, r.text)
        for r in (env["client"].post("/api/v1/billing/team", json={"email": e}, headers=env["a"])
                  for e in ("nobody@t.com", "student1@t.com", "outsider@t.com"))
    }
    assert len(answers) == 1 and answers.pop()[0] == 404


# ── 14 + 15. Legitimate use and API shape ─────────────────────────────────────

def test_14_assigning_ones_own_student_still_works(env):
    r = assign(env, env["a"], env["s1"])
    assert r.status_code == 200 and set(r.json()) == {"ok", "assignment_id"}
    again = assign(env, env["a"], env["s1"])
    assert again.json()["message"] == "Already assigned"
    mine = env["client"].get("/api/v1/exams/my-assignments", headers=env["s1h"]).json()
    assert [m["question_id"] for m in mine] == [env["qa"]]
    assert env["client"].post(f"/api/v1/voice/revoke-reenroll/{env['s1']}", headers=env["a"]).status_code == 200


def test_15_response_shapes_are_unchanged_for_web_and_mobile(env):
    listed = students(env, env["a"])
    assert set(listed[0]) == STUDENT_KEYS
    r = assign(env, env["a"], env["outsider"])
    assert r.json() == {"detail": "Student not found"}          # what both apps already handle
    att = env["client"].get("/api/v1/exams/attendance", headers=env["a"]).json()
    assert all({"id", "student_name", "email", "status", "score", "question_title"} <= set(row) for row in att)
