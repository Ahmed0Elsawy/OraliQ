"""
H1: identity and integrity results come only from what the server verified itself.

Face checks go through the real /face/verify endpoint with the face model replaced by a stub that
answers according to the frame's bytes; answers are graded by the real worker code with a fake AI
pipeline. Nothing real (cameras, models, networks) is used.
"""
import json
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
from app.models.face_check import FaceCheck
from app.models.grading_job import GradingJob
from app.models.question import Question
from app.models.user import User
from app.services import face_biometrics
from app.services.face_biometrics import EMBEDDING_DIM

FACEPRINT = json.dumps([0.01] * EMBEDDING_DIM)
FRAMES = {"match": b"MATCH" + b"\x00" * 600, "other": b"OTHER" + b"\x00" * 600,
          "noface": b"NOFACE" + b"\x00" * 600, "crowd": b"CROWD" + b"\x00" * 600, "broken": b"BROKEN" + b"\x00" * 600}


def fake_verify_image(stored, raw, threshold=None):
    if raw.startswith(b"NOFACE"):
        raise ValueError("no face found in the frame")
    if raw.startswith(b"BROKEN"):
        raise RuntimeError("InsightFace unavailable")
    sim = 30.0 if raw.startswith(b"OTHER") else 82.0
    return {"is_match": sim >= 55, "similarity_score": sim, "distance": 0.3, "cosine": 0.7,
            "report": "stub", "num_faces": 2 if raw.startswith(b"CROWD") else 1}


def fake_ai(audio_path, model_answer, keywords, alerts, voice_embedding):
    """Stands in for Whisper/SBERT/voice; the browser-alert text is produced as the real pipeline does."""
    from app.services.face_ai import face_analyzer
    parsed = json.loads(alerts or "{}")
    return {"transcript": "إجابة", "nlp_score": 80.0, "speech_score": 90.0, "voice_score": 90.0,
            "cheat_report": face_analyzer.describe_client_alerts(parsed) if parsed else None, "fluency_report": "ok"}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'h1.db').as_posix()}", connect_args={"check_same_thread": False})
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
    monkeypatch.setattr(face_biometrics.face_biometrics_service, "verify_image", fake_verify_image)
    client = TestClient(app, raise_server_exceptions=False)

    def user(email, role="student", face=True):
        with Session() as db:
            u = User(email=email, hashed_password="x", full_name=email, role=role, email_verified=True,
                     face_embedding=FACEPRINT if face else None, voice_embedding=json.dumps([0.1] * 256))
            db.add(u)
            db.commit()
            return u.id, {"Authorization": f"Bearer {security.create_access_token(u.id, timedelta(hours=1))}"}

    lect_id, _ = user("lect@t.com", "lecturer", face=False)

    def exam():
        with Session() as db:
            q = Question(text="سؤال", model_answer="إجابة", creator_id=lect_id, duration_minutes=5)
            db.add(q)
            db.flush()
            q.group_token = q.exam_token
            db.commit()
            return q.id, q.exam_token

    return {"client": client, "Session": Session, "user": user, "exam": exam}


def open_exam(e, headers, token):
    """access-check: starts (or resumes) the server-side sitting, as the exam page does on load.
    A refusal (e.g. attempts used up) is left to the submit call to report."""
    return e["client"].get(f"/api/v1/exams/access-check/{token}", headers=headers)


def face_check(e, headers, frame, token=None):
    if token:
        open_exam(e, headers, token)   # checks count from the sitting's start
    data = {"exam_token": token} if token else {}
    return e["client"].post("/api/v1/face/verify", headers=headers, data=data,
                            files={"image": ("f.jpg", FRAMES[frame], "image/jpeg")})


def submit(e, headers, qid, key, **form):
    with e["Session"]() as db:
        open_exam(e, headers, db.get(Question, qid).exam_token)
    data = {"question_id": str(qid), "student_name": "S", "student_number": "1", "submission_key": key}
    data.update({k: (json.dumps(v) if isinstance(v, dict) else str(v)) for k, v in form.items()})
    r = e["client"].post("/api/v1/exams/submit", headers=headers, data=data)
    assert r.status_code in (200, 202), r.text
    # The student's own reply hides grading until results are released (H6); the evidence these
    # tests check is what the server stored, as the lecturer sees it.
    with e["Session"]() as db:
        from app.schemas.exam_submission import ExamSubmissionOut
        return ExamSubmissionOut.model_validate(db.get(ExamSubmission, r.json()["id"])).model_dump()


def grade(e, submission_id):
    with e["Session"]() as db:
        job_id = db.query(GradingJob.id).filter(GradingJob.submission_id == submission_id).scalar()
    from sqlalchemy import update
    with e["Session"]() as db:   # claim this answer's job (claim_next would take the oldest one)
        db.execute(update(GradingJob).where(GradingJob.id == job_id).values(
            status="processing", locked_by="w-test", started_at=datetime.utcnow(),
            heartbeat_at=datetime.utcnow(), attempts=1))
        db.commit()
    assert worker_mod.process_job(e["Session"], job_id, "w-test", pipeline=fake_ai) == "completed"
    with e["Session"]() as db:
        s = db.get(ExamSubmission, submission_id)
        db.expunge(s)
        return s


# ── 1 + 3 + 8. Nothing the browser sends becomes a verified result ────────────

def test_1_a_client_face_score_of_100_verifies_nothing(env):
    _, h = env["user"]("s@t.com")
    qid, _ = env["exam"]()
    body = submit(env, h, qid, "k1", face_score=100, anti_cheat_alerts={})
    assert body["face_score"] is None and body["face_verification"] == "unverified"
    s = grade(env, body["id"])
    assert s.face_score is None
    assert "IDENTITY NOT VERIFIED" in s.cheat_report and "Identity verified" not in s.cheat_report


def test_3_tampering_cannot_override_the_servers_own_checks(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for _ in range(4):
        assert face_check(env, h, "other", tok).status_code == 200      # someone else in front of the camera
    body = submit(env, h, qid, "k3", face_score=100, anti_cheat_alerts={}, similarity_score=100,
                  face_verification="verified", integrity_status="server_sampled", facial_score=100)
    assert body["face_verification"] == "mismatch" and body["face_score"] == 30.0
    assert body["facial_score"] == 0.0 and body["integrity_status"] == "server_sampled"
    s = grade(env, body["id"])
    assert "IDENTITY NOT VERIFIED" in s.cheat_report and s.facial_score == 0.0


def test_8_client_alerts_are_kept_as_indicators_never_as_evidence(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for _ in range(3):
        face_check(env, h, "match", tok)
    body = submit(env, h, qid, "k8", anti_cheat_alerts={"phone_detected": 30, "gaze_left": 4, "made_up": 9, "no_face": "x"})
    assert json.loads(body["client_alerts"]) == {"gaze_left": 4.0, "phone_detected": 30.0}   # sanitised
    assert body["facial_score"] == 100.0                      # from the 3 server checks, not the alerts
    s = grade(env, body["id"])
    assert "غير متحقق منها" in s.cheat_report and s.facial_score == 100.0


# ── 2 + 9 + 11. Integrity score ───────────────────────────────────────────────

def test_2_9_no_alerts_and_no_monitoring_never_mean_a_clean_100(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    face_check(env, h, "match", tok)                             # one check: identity yes, monitoring too thin
    body = submit(env, h, qid, "k2", anti_cheat_alerts={})
    assert body["face_verification"] == "verified"
    assert body["facial_score"] is None and body["integrity_status"] == "insufficient_data"
    s = grade(env, body["id"])
    assert s.facial_score is None
    assert s.overall_score == 81.1                               # (80*.8 + 90*.1) / .9 — not +10 for "clean"
    assert "غير كافية" in s.cheat_report


def test_11_integrity_is_the_share_of_good_server_checks_only(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for frame in ("match", "match", "noface", "crowd"):
        face_check(env, h, frame, tok)
    body = submit(env, h, qid, "k11", anti_cheat_alerts={"phone_detected": 300})
    assert body["integrity_status"] == "server_sampled" and body["facial_score"] == 50.0   # 2 of 4
    assert body["face_checks"] == 4


# ── 4 + 5 + 6 + 7. Binding: this student, this exam, this sitting ────────────

def test_4_another_students_checks_do_not_count(env):
    _, a = env["user"]("a@t.com")
    _, b = env["user"]("b@t.com")
    qid, tok = env["exam"]()
    for _ in range(4):
        face_check(env, b, "match", tok)
    body = submit(env, a, qid, "k4")
    assert body["face_verification"] == "unverified" and body["face_checks"] == 0


def test_5_checks_for_another_exam_do_not_count(env):
    _, h = env["user"]("s@t.com")
    qx, tok_x = env["exam"]()
    qy, _ = env["exam"]()
    for _ in range(4):
        face_check(env, h, "match", tok_x)
    face_check(env, h, "match")                                  # no exam named: counts for none
    assert submit(env, h, qy, "k5")["face_verification"] == "unverified"
    assert submit(env, h, qx, "k5x")["face_verification"] == "verified"


def test_6_old_checks_are_not_accepted(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for _ in range(4):
        face_check(env, h, "match", tok)
    with env["Session"]() as db:
        for c in db.query(FaceCheck).all():
            c.created_at = datetime.utcnow() - timedelta(minutes=5 + 15 + 1)   # exam time + grace, passed
        db.commit()
    body = submit(env, h, qid, "k6")
    assert body["face_verification"] == "unverified" and body["integrity_status"] == "insufficient_data"


def test_7_missing_results_show_as_unknown(env):
    _, h = env["user"]("s@t.com")
    # Students can't start without a face print (H2); a lecturer previewing the exam can.
    _, nofp = env["user"]("nofp@t.com", role="lecturer", face=False)
    qid, _ = env["exam"]()
    assert submit(env, h, qid, "k7")["face_verification"] == "unverified"
    body = submit(env, nofp, qid, "k7b", face_score=99)
    assert body["face_verification"] == "not_enrolled" and body["face_score"] is None
    s = grade(env, body["id"])
    assert "IDENTITY NOT VERIFIED" in s.cheat_report


# ── 10. A failing face check never passes ─────────────────────────────────────

def test_10_a_crashed_face_check_records_nothing_and_proves_nothing(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    assert face_check(env, h, "broken", tok).status_code == 500
    with env["Session"]() as db:
        assert db.query(FaceCheck).count() == 0
    assert submit(env, h, qid, "k10", face_score=100)["face_verification"] == "unverified"


def test_10b_no_face_frames_are_recorded_as_such(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for _ in range(3):
        assert face_check(env, h, "noface", tok).json()["no_face"] is True
    body = submit(env, h, qid, "k10b")
    assert body["face_verification"] == "no_face" and body["facial_score"] == 0.0


# ── 12. No accusation from browser data ───────────────────────────────────────

def test_12_browser_alerts_alone_never_accuse(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for _ in range(3):
        face_check(env, h, "match", tok)
    body = submit(env, h, qid, "k12", anti_cheat_alerts={"phone_detected": 600, "multiple_people": 600, "book_detected": 600})
    s = grade(env, body["id"])
    assert "مشتبه في الغش" not in s.cheat_report               # the old verdict text is gone
    assert s.facial_score == 100.0 and s.overall_score == 83.0  # unaffected by what the browser claimed
    assert "Identity verified" in s.cheat_report


# ── 13 + 14 + 15. Queue, idempotency, old results ─────────────────────────────

def test_13_14_queue_and_idempotency_still_hold(env):
    _, h = env["user"]("s@t.com")
    qid, tok = env["exam"]()
    for _ in range(3):
        face_check(env, h, "match", tok)
    first = submit(env, h, qid, "same-key")
    face_check(env, h, "other", tok)                              # later evidence does not rewrite it
    again = submit(env, h, qid, "same-key", face_score=0)
    assert again["id"] == first["id"] and again["face_score"] == first["face_score"]
    with env["Session"]() as db:
        assert db.query(ExamSubmission).count() == 1 and db.query(GradingJob).count() == 1
    assert grade(env, first["id"]).grading_status == "completed"


def test_15_results_graded_before_this_change_are_left_as_they_were(env):
    sid, h = env["user"]("s@t.com")
    old_qid, _ = env["exam"]()     # an exam answered before this change (old answers count as attempts)
    qid, tok = env["exam"]()
    with env["Session"]() as db:
        old = ExamSubmission(question_id=old_qid, student_id=sid, student_name="Old", student_number="1",
                             face_score=97.0, facial_score=100.0, overall_score=91.0, nlp_score=90.0,
                             cheat_report="لم يتم رصد أي مخالفات", grading_status="completed")
        db.add(old)
        db.commit()
        old_id = old.id
    for _ in range(3):
        face_check(env, h, "other", tok)
    submit(env, h, qid, "new-one")
    with env["Session"]() as db:
        o = db.get(ExamSubmission, old_id)
        assert (o.face_score, o.facial_score, o.overall_score, o.cheat_report) == (97.0, 100.0, 91.0, "لم يتم رصد أي مخالفات")
        assert o.face_verification is None and o.integrity_status is None
