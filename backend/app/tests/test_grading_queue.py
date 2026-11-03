"""
The grading queue and worker: durable jobs, single grading per recording, crash recovery.

No model is loaded here. The worker is driven with a fake pipeline; the tests that need real
concurrent database connections use a throwaway SQLite file (the shared in-memory database in
conftest is one connection, so it cannot show a race).
"""
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — register every table
from app import worker as worker_mod
from app.api.endpoints import exams
from app.core import security
from app.core.database import Base
from app.models.exam_submission import ExamSubmission
from app.models.grading_job import GradingJob
from app.models.question import Question
from app.models.user import User
from app.services import grading_pipeline
from app.services import grading_queue as gq
from app.tests.exam_helpers import ENROLLED, access_check, new_exam, open_sitting

AUDIO = b"RIFF" + b"\x00" * 4096  # stands in for a recording; never decoded


def fake_ai(score=80.0):
    def pipeline(audio_path, model_answer, keywords, alerts, voice_embedding):
        return {
            "transcript": "الجسم يحفظ حالته", "nlp_score": score, "speech_score": 90.0,
            "voice_score": None, "facial_score": 100.0, "cheat_report": None, "fluency_report": "ok",
        }
    return pipeline


# ── Fixtures: a private SQLite file per test ──────────────────────────────────

@pytest.fixture()
def Session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'queue.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture()
def seed(Session):
    db = Session()
    student = User(email="q-student@example.com", hashed_password="x", full_name="Q Student", role="student",
                   **ENROLLED)
    question = Question(text="اشرح قانون نيوتن الأول", model_answer="الجسم يحفظ حالته", keywords="نيوتن")
    db.add_all([student, question])
    db.commit()
    ids = {"student": student.id, "question": question.id}
    db.close()
    return ids


def accept(Session, seed, key=None, audio=AUDIO):
    """Runs the submit endpoint's synchronous part in its own session, like one request. Each new
    answer goes to a fresh exam inside an open sitting (one answer per question per sitting, H2);
    a key that was already used is returned before any of that is looked at."""
    db = Session()
    try:
        user = db.get(User, seed["student"])
        existing = db.query(ExamSubmission).filter(ExamSubmission.submission_key == key).first() if key else None
        if existing is not None:
            question = db.get(Question, existing.question_id)
        else:
            question = new_exam(db, text="اشرح قانون نيوتن الأول", model_answer="الجسم يحفظ حالته", keywords="نيوتن")
            open_sitting(db, user, question)
        sub, created = exams._accept_submission(
            db, user, question, key=key, student_name="Q Student", student_number="1",
            audio=audio, audio_suffix=".webm", anti_cheat_alerts="{}", face_score=None,
            started_at=None, finished_at=None, t0=time.perf_counter(),
        )
        return sub.id, created
    finally:
        db.close()


def job_of(Session, submission_id):
    db = Session()
    try:
        from sqlalchemy.orm import undefer
        job = (db.query(GradingJob).options(undefer(GradingJob.audio))
               .filter(GradingJob.submission_id == submission_id).one())
        db.expunge(job)
        return job
    finally:
        db.close()


def submission_of(Session, submission_id):
    db = Session()
    try:
        sub = db.get(ExamSubmission, submission_id)
        db.expunge(sub)
        return sub
    finally:
        db.close()


# ── 1. Submit answers at once with "queued" ───────────────────────────────────

def test_1_submit_is_queued_and_answers_without_grading(client, db, monkeypatch):
    def must_not_run(*a, **k):
        raise AssertionError("grading ran inside the request")
    monkeypatch.setattr(grading_pipeline, "run_ai_pipeline", must_not_run)

    student = User(email="fast-submit@example.com", hashed_password=security.get_password_hash("password123"),
                   full_name="Fast", role="student", **ENROLLED)
    db.add(student)
    db.commit()
    q = new_exam(db)
    token = security.create_access_token(student.id)
    access_check(client, {"Authorization": f"Bearer {token}"}, q.exam_token)

    t0 = time.perf_counter()
    r = client.post(
        "/api/v1/exams/submit",
        data={"question_id": str(q.id), "student_name": "Fast", "student_number": "7",
              "submission_key": "fast-key-1", "anti_cheat_alerts": "{}"},
        files={"audio": ("answer.webm", AUDIO, "audio/webm")},
        headers={"Authorization": f"Bearer {token}"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["grading_status"] == "queued"
    assert body["overall_score"] is None
    assert elapsed < 2.0, f"submit took {elapsed:.2f}s"

    job = db.query(GradingJob).filter(GradingJob.submission_id == body["id"]).one()
    assert job.status == "queued" and job.audio_bytes == len(AUDIO)
    assert job.api_receive_ms is not None


# ── 2. queued -> processing -> completed ──────────────────────────────────────

def test_2_job_moves_from_queued_to_processing_to_completed(Session, seed):
    sub_id, created = accept(Session, seed, key="k-lifecycle")
    assert created
    assert submission_of(Session, sub_id).grading_status == "queued"

    db = Session()
    job_id = gq.claim_next(db, "w-test")
    db.close()
    assert job_of(Session, sub_id).status == "processing"
    assert submission_of(Session, sub_id).grading_status == "processing"

    outcome = worker_mod.process_job(Session, job_id, "w-test", pipeline=fake_ai(80.0))
    assert outcome == "completed"

    job = job_of(Session, sub_id)
    sub = submission_of(Session, sub_id)
    assert job.status == "completed" and job.attempts == 1
    assert job.audio is None and job.audio_purged_at is not None   # recording dropped after the grade
    assert job.queue_wait_ms is not None and job.process_ms is not None
    assert sub.grading_status == "completed"
    assert sub.transcript == "الجسم يحفظ حالته"
    # No server face checks for this student, so integrity is unknown: it is left out and the rest
    # scaled to the full mark, (80*.8 + 90*.1) / .9 — never an assumed 100 (H1).
    assert sub.nlp_score == 80.0 and sub.overall_score == 81.1
    assert sub.integrity_status == "insufficient_data" and sub.facial_score is None


# ── 3. Same key sent again ────────────────────────────────────────────────────

def test_3_same_key_again_returns_the_original_and_queues_nothing(Session, seed):
    first, created = accept(Session, seed, key="k-repeat")
    assert created
    for _ in range(3):
        again, created_again = accept(Session, seed, key="k-repeat")
        assert again == first and not created_again
    db = Session()
    assert db.query(ExamSubmission).filter(ExamSubmission.submission_key == "k-repeat").count() == 1
    assert db.query(GradingJob).count() == 1
    db.close()


# ── 4. Two requests with the same key at the same instant ────────────────────

def test_4_two_concurrent_requests_with_one_key_create_one_job(Session, seed):
    barrier = threading.Barrier(2)
    results, errors = [], []

    def send():
        try:
            barrier.wait()
            results.append(accept(Session, seed, key="k-race"))
        except Exception as e:  # pragma: no cover — reported below
            errors.append(e)

    threads = [threading.Thread(target=send) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert len({sid for sid, _ in results}) == 1           # both see the same submission
    assert sorted(created for _, created in results) == [False, True]
    db = Session()
    assert db.query(GradingJob).count() == 1
    db.close()


def test_4b_two_workers_cannot_claim_the_same_job(Session, seed):
    accept(Session, seed, key="k-claim-race")
    barrier = threading.Barrier(4)
    claimed = []

    def claim(i):
        db = Session()
        try:
            barrier.wait()
            claimed.append(gq.claim_next(db, f"w{i}"))
        finally:
            db.close()

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([c for c in claimed if c is not None]) == 1


# ── 5 + 6. Worker dies mid-grading; a restarted worker recovers the job ──────

def _make_stale(Session, sub_id):
    db = Session()
    db.query(GradingJob).filter(GradingJob.submission_id == sub_id).update(
        {GradingJob.heartbeat_at: gq.utcnow() - timedelta(seconds=gq.stale_after_seconds() + 5)}
    )
    db.commit()
    db.close()


def test_5_a_crashed_attempt_keeps_the_recording_and_is_recovered(Session, seed):
    sub_id, _ = accept(Session, seed, key="k-crash")
    db = Session()
    gq.claim_next(db, "w-crashing")   # claimed, then the process "dies": no heartbeat, no result
    db.close()
    _make_stale(Session, sub_id)

    db = Session()
    assert gq.recover_stale(db) == 1
    db.close()
    job = job_of(Session, sub_id)
    assert job.status == "queued" and job.locked_by is None and job.attempts == 1
    assert job.audio == AUDIO
    assert submission_of(Session, sub_id).grading_status == "queued"


def test_6_restarted_worker_finishes_the_recovered_job(Session, seed):
    sub_id, _ = accept(Session, seed, key="k-restart")
    db = Session()
    gq.claim_next(db, "w-old")
    db.close()
    _make_stale(Session, sub_id)

    fresh = worker_mod.Worker(Session, concurrency=1, pipeline=fake_ai())
    fresh.maintenance()                          # what a new worker does on its first pass
    assert fresh.run_one(0) == "completed"
    job = job_of(Session, sub_id)
    assert job.status == "completed" and job.attempts == 2
    assert submission_of(Session, sub_id).grading_status == "completed"


def test_6b_a_job_that_keeps_crashing_its_worker_ends_failed_not_looping(Session, seed, monkeypatch):
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "1")
    sub_id, _ = accept(Session, seed, key="k-poison")
    db = Session()
    gq.claim_next(db, "w-old")
    db.close()
    _make_stale(Session, sub_id)
    db = Session()
    gq.recover_stale(db)
    db.close()
    assert job_of(Session, sub_id).status == "failed"
    assert job_of(Session, sub_id).audio == AUDIO   # kept for a lecturer-triggered re-grade


# ── 7. Whisper or SBERT fails ─────────────────────────────────────────────────

def test_7_whisper_failure_raises_instead_of_saving_an_empty_grade(monkeypatch):
    from app.services.speech_ai import speech_analyzer

    def boom(*a, **k):
        raise RuntimeError("ffmpeg could not decode")
    monkeypatch.setattr(speech_analyzer, "analyze_fluency", boom)
    with pytest.raises(grading_pipeline.GradingError):
        grading_pipeline.run_ai_pipeline("x.webm", "answer", "", "{}", None)


def test_7b_sbert_failure_raises(monkeypatch):
    from app.services.speech_ai import speech_analyzer
    from app.services.nlp_ai import nlp_analyzer

    monkeypatch.setattr(speech_analyzer, "analyze_fluency",
                        lambda *a, **k: {"transcript": "نص", "speech_score": 80.0, "fluency_report": ""})
    monkeypatch.setattr(nlp_analyzer, "evaluate_answer",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("model missing")))
    with pytest.raises(grading_pipeline.GradingError):
        grading_pipeline.run_ai_pipeline("x.webm", "answer", "", "{}", None)


def test_7c_a_failed_attempt_is_retried_then_marked_failed(Session, seed, monkeypatch):
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("GRADING_RETRY_BASE_SECONDS", "0")
    sub_id, _ = accept(Session, seed, key="k-fails")

    def failing(*a, **k):
        raise grading_pipeline.GradingError("speech-to-text failed")

    w = worker_mod.Worker(Session, concurrency=1, pipeline=failing)
    assert w.run_one(0) == "queued"
    job = job_of(Session, sub_id)
    assert job.status == "queued" and job.attempts == 1 and "speech-to-text" in job.last_error
    assert job.audio == AUDIO

    assert w.run_one(0) == "failed"
    job = job_of(Session, sub_id)
    assert job.status == "failed" and job.attempts == 2
    assert job.audio == AUDIO
    assert submission_of(Session, sub_id).grading_status == "failed"
    assert w.run_one(0) is None                  # a failed job is not picked up again by itself


# ── 8. Retry never creates a second answer ────────────────────────────────────

def test_8_retries_and_regrade_keep_one_submission(Session, seed, monkeypatch):
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "1")
    sub_id, _ = accept(Session, seed, key="k-regrade")

    def failing(*a, **k):
        raise grading_pipeline.GradingError("transient")

    assert worker_mod.Worker(Session, 1, pipeline=failing).run_one(0) == "failed"

    db = Session()
    job = db.query(GradingJob).filter(GradingJob.submission_id == sub_id).one()
    assert gq.requeue_failed(db, job)
    db.close()
    assert worker_mod.Worker(Session, 1, pipeline=fake_ai()).run_one(0) == "completed"

    db = Session()
    assert db.query(ExamSubmission).count() == 1
    assert db.query(GradingJob).count() == 1
    db.close()
    assert submission_of(Session, sub_id).grading_status == "completed"


def test_8b_purged_recording_cannot_be_regraded(Session, seed, monkeypatch):
    monkeypatch.setenv("GRADING_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GRADING_FAILED_AUDIO_RETENTION_HOURS", "0")
    sub_id, _ = accept(Session, seed, key="k-purged")
    worker_mod.Worker(Session, 1, pipeline=lambda *a: (_ for _ in ()).throw(RuntimeError("x"))).run_one(0)
    db = Session()
    db.query(GradingJob).update({GradingJob.finished_at: gq.utcnow() - timedelta(hours=1)})
    db.commit()
    assert gq.purge_expired_audio(db) == 1
    job = db.query(GradingJob).one()
    assert not gq.requeue_failed(db, job)
    db.close()
    assert job_of(Session, sub_id).audio is None


# ── 9. Student loses the connection after the answer was accepted ────────────

def test_9_status_can_be_found_by_key_after_a_lost_response(client, db):
    student = User(email="offline@example.com", hashed_password="x", full_name="Off", role="student", **ENROLLED)
    other = User(email="offline-other@example.com", hashed_password="x", full_name="Other", role="student", **ENROLLED)
    db.add_all([student, other])
    db.commit()
    q = new_exam(db)
    h = {"Authorization": f"Bearer {security.create_access_token(student.id)}"}
    access_check(client, h, q.exam_token)

    r = client.post("/api/v1/exams/submit", headers=h, files={"audio": ("a.webm", AUDIO, "audio/webm")},
                    data={"question_id": str(q.id), "student_name": "Off", "student_number": "1",
                          "submission_key": "offline-key"})
    assert r.status_code == 202
    sub_id = r.json()["id"]

    # The browser never saw that response; it asks by the key it generated.
    s = client.get("/api/v1/exams/submissions/by-key/offline-key/grading", headers=h)
    assert s.status_code == 200
    assert s.json()["id"] == sub_id and s.json()["grading_status"] == "queued"
    assert s.json()["queue_ahead"] is not None
    assert client.get(f"/api/v1/exams/submissions/{sub_id}/grading", headers=h).status_code == 200

    # Re-sending the whole answer is also safe: same submission, no new job.
    again = client.post("/api/v1/exams/submit", headers=h, files={"audio": ("a.webm", AUDIO, "audio/webm")},
                        data={"question_id": str(q.id), "student_name": "Off", "student_number": "1",
                              "submission_key": "offline-key"})
    assert again.status_code == 200 and again.json()["id"] == sub_id
    assert db.query(GradingJob).filter(GradingJob.submission_id == sub_id).count() == 1

    # Nobody else can read it, by key or by id.
    oh = {"Authorization": f"Bearer {security.create_access_token(other.id)}"}
    assert client.get("/api/v1/exams/submissions/by-key/offline-key/grading", headers=oh).status_code == 404
    assert client.get(f"/api/v1/exams/submissions/{sub_id}/grading", headers=oh).status_code == 404


# ── 10. Many answers at the same time ─────────────────────────────────────────

def test_10_many_answers_are_each_graded_once_within_the_concurrency_cap(Session, seed):
    n, cap = 12, 3
    for i in range(n):
        accept(Session, seed, key=f"k-many-{i}")

    lock = threading.Lock()
    running = {"now": 0, "peak": 0}
    calls = []

    def slow_ai(audio_path, *rest):
        with lock:
            running["now"] += 1
            running["peak"] = max(running["peak"], running["now"])
            calls.append(audio_path)
        time.sleep(0.05)
        with lock:
            running["now"] -= 1
        return fake_ai()(audio_path, *rest)

    w = worker_mod.Worker(Session, concurrency=cap, pipeline=slow_ai)
    t = threading.Thread(target=w.serve, daemon=True)
    t.start()
    deadline = time.time() + 30
    db = Session()
    try:
        while time.time() < deadline:
            if db.query(GradingJob).filter(GradingJob.status == "completed").count() == n:
                break
            db.rollback()
            time.sleep(0.05)
    finally:
        db.close()
        w.stop.set()
        t.join(timeout=10)

    db = Session()
    assert db.query(GradingJob).filter(GradingJob.status == "completed").count() == n
    assert db.query(ExamSubmission).filter(ExamSubmission.grading_status == "completed").count() == n
    db.close()
    assert len(calls) == n                      # no job graded twice
    assert 1 <= running["peak"] <= cap          # never more AI jobs than the cap


# ── 11. The recording survives until the grade is saved ──────────────────────

def test_11_a_worker_that_lost_its_lease_saves_nothing_and_drops_nothing(Session, seed):
    sub_id, _ = accept(Session, seed, key="k-lease")
    db = Session()
    job_id = gq.claim_next(db, "w-slow")
    db.close()

    # w-slow takes too long; its lease is reclaimed and handed to w-new.
    _make_stale(Session, sub_id)
    db = Session()
    gq.recover_stale(db)
    assert gq.claim_next(db, "w-new") == job_id
    db.close()

    # w-slow finally finishes: its result is refused, the recording is still there.
    db = Session()
    assert gq.complete(db, job_id, "w-slow", {"overall_score": 99.0}) is False
    db.close()
    job = job_of(Session, sub_id)
    assert job.status == "processing" and job.locked_by == "w-new"
    assert job.audio == AUDIO
    assert submission_of(Session, sub_id).overall_score is None

    assert worker_mod.process_job(Session, job_id, "w-new", pipeline=fake_ai()) == "completed"
    assert job_of(Session, sub_id).audio is None


def test_11b_a_failing_database_write_does_not_lose_the_recording(Session, seed, monkeypatch):
    sub_id, _ = accept(Session, seed, key="k-dbfail")
    db = Session()
    job_id = gq.claim_next(db, "w")
    db.close()

    def broken_complete(*a, **k):
        raise RuntimeError("database went away")
    monkeypatch.setattr(gq, "complete", broken_complete)
    assert worker_mod.process_job(Session, job_id, "w", pipeline=fake_ai()) == "error"
    job = job_of(Session, sub_id)
    assert job.audio == AUDIO and job.status == "processing"   # lease will expire and it will rerun


# ── 12. Grading load never blocks the API ─────────────────────────────────────

def test_12_api_answers_while_grading_is_busy(client, db, monkeypatch):
    """A slow grade runs in another process; here, the request path must not call it at all."""
    calls = []

    def slow(*a, **k):
        calls.append(1)
        time.sleep(5)
    monkeypatch.setattr(grading_pipeline, "run_ai_pipeline", slow)

    student = User(email="busy@example.com", hashed_password="x", full_name="Busy", role="student", **ENROLLED)
    db.add(student)
    db.commit()
    h = {"Authorization": f"Bearer {security.create_access_token(student.id)}"}
    exams_ = [new_exam(db) for _ in range(5)]
    for q in exams_:
        access_check(client, h, q.exam_token)

    t0 = time.perf_counter()
    for i, q in enumerate(exams_):
        r = client.post("/api/v1/exams/submit", headers=h,
                        files={"audio": ("a.webm", AUDIO, "audio/webm")},
                        data={"question_id": str(q.id), "student_name": "Busy", "student_number": "1",
                              "submission_key": f"busy-{i}"})
        assert r.status_code == 202
    assert client.get("/").status_code == 200
    assert time.perf_counter() - t0 < 5
    assert calls == []


# ── Metrics ───────────────────────────────────────────────────────────────────

def test_metrics_report_queue_depth_and_timings(Session, seed):
    for i in range(3):
        accept(Session, seed, key=f"k-metrics-{i}")
    worker_mod.Worker(Session, 1, pipeline=fake_ai()).run_one(0)
    db = Session()
    m = gq.metrics(db)
    db.close()
    assert m["queued"] == 2 and m["completed"] == 1 and m["processing"] == 0
    assert m["completed_in_window"] == 1
    assert m["process_ms"]["avg"] is not None and m["queue_wait_ms"]["avg"] is not None


def test_metrics_endpoint_is_admin_only(client, db):
    lecturer = User(email="metrics-lect@example.com", hashed_password="x", full_name="L", role="lecturer")
    admin = User(email="metrics-admin@example.com", hashed_password="x", full_name="A", role="admin")
    db.add_all([lecturer, admin])
    db.commit()
    lh = {"Authorization": f"Bearer {security.create_access_token(lecturer.id)}"}
    ah = {"Authorization": f"Bearer {security.create_access_token(admin.id)}"}
    assert client.get("/api/v1/exams/grading/metrics", headers=lh).status_code == 403
    r = client.get("/api/v1/exams/grading/metrics", headers=ah)
    assert r.status_code == 200 and "queued" in r.json()


def test_grade_weighting_is_unchanged():
    """Same formula as the inline grading it replaced when integrity is server-measured, including
    the fail cap and the penalty; integrity now only ever comes from integrity_score."""
    ai = {"transcript": "t", "nlp_score": 40.0, "speech_score": 90.0, "voice_score": None,
          "cheat_report": None, "fluency_report": None}
    # content below 50 caps the grade under a pass, whatever the other parts add
    assert grading_pipeline.compute_grade(ai, None, False, integrity_score=100.0)["overall_score"] == 49.9
    ai.update(nlp_score=90.0)
    # 72 + 9 + 4 = 85, minus (60-40)*0.75 = 15 -> 70
    assert grading_pipeline.compute_grade(ai, None, False, integrity_score=40.0)["overall_score"] == 70.0
    out = grading_pipeline.compute_grade(ai, 30.0, True, integrity_score=40.0, face_verification="mismatch",
                                         integrity_status="server_sampled", face_checks=5)
    assert "IDENTITY NOT VERIFIED" in out["cheat_report"]
    ai.update(nlp_score=None)
    assert grading_pipeline.compute_grade(ai, None, False)["overall_score"] is None
