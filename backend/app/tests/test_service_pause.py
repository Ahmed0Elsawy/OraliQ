"""
H8 final patch: recording a lecturer's cancellation request pauses the lecturer's services and
their students' access to that lecturer's exams, on the server, for every endpoint — and the
lecturer staying (request resolved) gives everything back. Nothing is deleted or changed.

Isolated app + temporary SQLite. No AI model runs: nothing here reaches grading or face matching.
"""
from datetime import datetime, timedelta, timezone

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
from app.models.exam_sitting import ExamSitting
from app.models.exam_submission import ExamSubmission
from app.models.question import Question
from app.models.user import User
from app.services import exam_sessions
from app.tests.exam_helpers import ENROLLED

API = "/api/v1"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'pause.db').as_posix()}", connect_args={"check_same_thread": False})
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
    monkeypatch.setenv("BILLING_SANDBOX", "0")
    client = TestClient(app)

    def user(email, role="student", **fields):
        with Session() as db:
            extra = dict(ENROLLED) if role == "student" else {}
            extra.update(fields)
            u = User(email=email, hashed_password="x", full_name=email, role=role, email_verified=True, **extra)
            db.add(u)
            db.commit()
            return u.id, {"Authorization": f"Bearer {security.create_access_token(u.id, timedelta(hours=1))}"}

    def exam(creator_id, n=2):
        with Session() as db:
            qs = []
            for i in range(n):
                q = Question(text=f"س{i}", model_answer="إجابة", creator_id=creator_id, duration_minutes=5,
                             order_index=i, max_attempts=2, results_policy="immediate")
                db.add(q)
                db.flush()
                qs.append(q)
            for q in qs:
                q.group_token = qs[0].exam_token
            db.commit()
            return qs[0].exam_token, [q.id for q in qs]

    lect_id, lect = user("lect@t.com", "lecturer")
    other_id, other = user("other@t.com", "lecturer")
    admin_id, admin = user("admin@t.com", "admin")
    stu_id, stu = user("stu@t.com")
    token, qids = exam(lect_id)
    other_token, other_qids = exam(other_id)

    # History from before the pause: an assignment, a sitting and a graded, released answer.
    with Session() as db:
        db.add(ExamAssignment(question_id=qids[1], student_id=stu_id, assigned_by=lect_id, assigned_at=datetime.utcnow()))
        db.add(ExamAssignment(question_id=other_qids[0], student_id=stu_id, assigned_by=other_id, assigned_at=datetime.utcnow()))
        s = db.get(User, stu_id)
        sitting = exam_sessions.start_or_resume(db, s, exam_sessions.exam_key_of(db.get(Question, qids[0])))
        now = datetime.now(timezone.utc)
        sub = ExamSubmission(question_id=qids[0], student_id=stu_id, student_name="S", student_number="1",
                             submission_key="k-before", overall_score=80.0, grade_visible=1, grading_status="completed",
                             started_at=now, finished_at=now, submitted_at=now, exam_sitting_id=sitting.id, attempt_no=1)
        db.add(sub)
        other_sub = ExamSubmission(question_id=other_qids[0], student_id=stu_id, student_name="S", student_number="1",
                                   submission_key="k-other", overall_score=70.0, grade_visible=1, grading_status="completed",
                                   started_at=now, finished_at=now, submitted_at=now, attempt_no=1)
        db.add(other_sub)
        db.commit()
        sub_id, other_sub_id = sub.id, other_sub.id

    return {"client": client, "Session": Session, "user": user, "lect_id": lect_id, "lect": lect, "other": other,
            "admin": admin, "stu_id": stu_id, "stu": stu, "token": token, "qids": qids,
            "other_token": other_token, "other_qids": other_qids, "sub_id": sub_id, "other_sub_id": other_sub_id}


def pause(e, uid=None):
    r = e["client"].post(f"{API}/billing/admin/cancellation-requests", headers=e["admin"], json={
        "user_id": uid or e["lect_id"], "received_at": datetime.utcnow().isoformat() + "Z"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def resume(e, request_id):
    r = e["client"].post(f"{API}/billing/admin/cancellation-requests/{request_id}/decision", headers=e["admin"],
                         json={"decision": "resolved", "note": "lecturer stays"})
    assert r.status_code == 200, r.text


def lecturer_calls(e, h, qid, token, sub_id, stu_id):
    c = e["client"]
    return {
        "questions": c.get(f"{API}/questions/", headers=h),
        "create": c.post(f"{API}/questions/", headers=h, json={"text": "سؤال جديد", "model_answer": "إجابة", "duration_minutes": 2}),
        "results": c.get(f"{API}/exams/results/{qid}", headers=h),
        "all-results": c.get(f"{API}/exams/all-results", headers=h),
        "attendance": c.get(f"{API}/exams/attendance", headers=h),
        "students": c.get(f"{API}/exams/students", headers=h),
        "assign": c.post(f"{API}/exams/assign", headers=h, json={"question_id": qid, "student_id": stu_id}),
        "visibility": c.patch(f"{API}/exams/submissions/{sub_id}/visibility?visible=true", headers=h),
        "publish": c.post(f"{API}/exams/publish-results/{token}", headers=h),
        "regrade": c.post(f"{API}/exams/submissions/{sub_id}/regrade", headers=h),
        "grading": c.get(f"{API}/exams/submissions/{sub_id}/grading", headers=h),
        "reenroll": c.post(f"{API}/voice/allow-reenroll/{stu_id}", headers=h),
        "delete": c.delete(f"{API}/questions/{qid}", headers=h),
    }


def student_calls(e, token, qid, sub_id):
    c, h = e["client"], e["stu"]
    return {
        "by-token": c.get(f"{API}/questions/by-token/{token}"),
        "by-group": c.get(f"{API}/questions/by-group/{token}"),
        "access-check": c.get(f"{API}/exams/access-check/{token}", headers=h),
        "submit": c.post(f"{API}/exams/submit", headers=h, data={
            "question_id": str(qid), "student_name": "S", "student_number": "1", "submission_key": "k-during"}),
        "grading": c.get(f"{API}/exams/submissions/{sub_id}/grading", headers=h),
        "grading-by-key": c.get(f"{API}/exams/submissions/by-key/k-before/grading", headers=h),
        "face-check": c.post(f"{API}/face/verify", headers=h, files={"image": ("f.jpg", b"\xff\xd8x", "image/jpeg")},
                             data={"exam_token": token}),
    }


def snapshot(e):
    with e["Session"]() as db:
        subs = [(s.id, s.overall_score, s.grade_visible, s.grading_status) for s in db.query(ExamSubmission).order_by(ExamSubmission.id)]
        sittings = [(s.id, s.status, s.deadline_at) for s in db.query(ExamSitting).order_by(ExamSitting.id)]
        questions = [(q.id, q.text, q.results_policy) for q in db.query(Question).order_by(Question.id)]
        assignments = [(a.id, a.status) for a in db.query(ExamAssignment).order_by(ExamAssignment.id)]
        return subs, sittings, questions, assignments


def test_paused_lecturer_loses_every_exam_service_but_keeps_billing_and_profile(env):
    e = env
    rid = pause(e)
    calls = lecturer_calls(e, e["lect"], e["qids"][0], e["token"], e["sub_id"], e["stu_id"])
    for name, r in calls.items():
        assert r.status_code == 403, (name, r.status_code, r.text)
        assert r.json()["detail"]["code"] == "SERVICE_PAUSED", name
    assert e["client"].get(f"{API}/billing/status", headers=e["lect"]).status_code == 200
    assert e["client"].get(f"{API}/users/me", headers=e["lect"]).status_code == 200
    assert e["client"].get(f"{API}/billing/payments", headers=e["lect"]).status_code == 200
    resume(e, rid)


def test_students_lose_access_to_the_paused_lecturers_exams_via_the_api(env):
    e = env
    before = snapshot(e)
    pause(e)
    for name, r in student_calls(e, e["token"], e["qids"][1], e["sub_id"]).items():
        assert r.status_code == 403, (name, r.status_code, r.text)
        assert r.json()["detail"]["code"] == "EXAM_UNAVAILABLE", name
    # Lists the apps show no longer include the paused lecturer's exams or results.
    grades = e["client"].get(f"{API}/exams/my-grades", headers=e["stu"]).json()
    assert [g["id"] for g in grades] == [e["other_sub_id"]]
    assigned = e["client"].get(f"{API}/exams/my-assignments", headers=e["stu"]).json()
    assert [a["question_id"] for a in assigned] == [e["other_qids"][0]]
    # Nothing was added, deleted or changed.
    assert snapshot(e) == before


def test_no_answer_or_grading_request_is_accepted_during_the_pause(env):
    e = env
    pause(e)
    with e["Session"]() as db:
        before = db.query(ExamSubmission).count()
    r = e["client"].post(f"{API}/exams/submit", headers=e["stu"], data={
        "question_id": str(e["qids"][1]), "student_name": "S", "student_number": "1", "submission_key": "k-x"})
    assert r.status_code == 403
    assert e["client"].post(f"{API}/exams/submissions/{e['sub_id']}/regrade", headers=e["lect"]).status_code == 403
    with e["Session"]() as db:
        assert db.query(ExamSubmission).count() == before
        from app.models.grading_job import GradingJob
        assert db.query(GradingJob).count() == 0


def test_everything_comes_back_when_the_lecturer_stays(env):
    e = env
    before = snapshot(e)
    rid = pause(e)
    resume(e, rid)
    c = e["client"]
    assert c.get(f"{API}/questions/", headers=e["lect"]).status_code == 200
    assert c.get(f"{API}/exams/all-results", headers=e["lect"]).status_code == 200
    assert c.get(f"{API}/exams/results/{e['qids'][0]}", headers=e["lect"]).status_code == 200
    assert c.get(f"{API}/questions/by-group/{e['token']}").status_code == 200
    assert c.get(f"{API}/exams/access-check/{e['token']}", headers=e["stu"]).status_code == 200   # resumes the sitting
    assert c.get(f"{API}/exams/submissions/{e['sub_id']}/grading", headers=e["stu"]).status_code == 200
    grades = {g["id"] for g in c.get(f"{API}/exams/my-grades", headers=e["stu"]).json()}
    assert grades == {e["sub_id"], e["other_sub_id"]}
    assigned = {a["question_id"] for a in c.get(f"{API}/exams/my-assignments", headers=e["stu"]).json()}
    assert e["qids"][1] in assigned
    subs, sittings, questions, assignments = snapshot(e)
    assert (subs, questions, assignments) == (before[0], before[2], before[3])
    assert [s[0] for s in sittings] == [s[0] for s in before[1]]   # same sitting, resumed


def test_other_lecturers_and_their_exams_are_not_affected(env):
    e = env
    pause(e)
    c = e["client"]
    assert c.get(f"{API}/questions/", headers=e["other"]).status_code == 200
    assert c.get(f"{API}/exams/all-results", headers=e["other"]).status_code == 200
    assert c.get(f"{API}/questions/by-group/{e['other_token']}").status_code == 200
    assert c.get(f"{API}/exams/access-check/{e['other_token']}", headers=e["stu"]).status_code == 200
    assert c.get(f"{API}/exams/submissions/{e['other_sub_id']}/grading", headers=e["stu"]).status_code == 200


def test_team_assistants_of_a_paused_owner_are_paused_too(env):
    e = env
    aid, ah = e["user"]("assist@t.com", "lecturer", owner_id=e["lect_id"])
    with e["Session"]() as db:
        q = Question(text="سؤال المساعد", model_answer="إجابة", creator_id=aid, duration_minutes=5, max_attempts=1)
        db.add(q)
        db.flush()
        q.group_token = q.exam_token
        db.commit()
        atoken = q.exam_token
    rid = pause(e)
    assert e["client"].get(f"{API}/questions/", headers=ah).status_code == 403
    assert e["client"].get(f"{API}/questions/by-group/{atoken}").status_code == 403
    resume(e, rid)
    assert e["client"].get(f"{API}/questions/", headers=ah).status_code == 200
    assert e["client"].get(f"{API}/questions/by-group/{atoken}").status_code == 200


def test_admin_keeps_oversight_of_a_paused_lecturers_answers(env):
    e = env
    pause(e)
    assert e["client"].get(f"{API}/exams/submissions/{e['sub_id']}/grading", headers=e["admin"]).status_code == 200
