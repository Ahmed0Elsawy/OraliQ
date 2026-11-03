"""
Grading worker: a separate process that takes answers off the database queue and grades them.

    python -m app.worker

Runs GRADING_WORKER_CONCURRENCY threads (default: MAX_CONCURRENT_GRADING, else cores / 4), all
sharing one copy of each model, loaded once when the process starts. The API never runs Whisper
or SBERT for a submission any more; it only stores the answer and its job.

By default the API starts this process itself (GRADING_WORKER_MODE=embedded) so a single-container
deployment keeps working unchanged. Set GRADING_WORKER_MODE=external to run it on its own — in
another container or on another machine pointed at the same DATABASE_URL — and as many copies as
the hardware allows: the queue's row-level claims keep them from grading the same answer twice.
"""
import json
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from app.services import grading_queue as gq
from app.services.grading_pipeline import compute_grade, run_ai_pipeline

POLL_SECONDS = float(os.environ.get("GRADING_POLL_SECONDS", "1.0") or 1.0)
MAINTENANCE_SECONDS = 30


def worker_concurrency() -> int:
    explicit = os.environ.get("GRADING_WORKER_CONCURRENCY", "").strip()
    if explicit.isdigit() and int(explicit) > 0:
        return int(explicit)
    slots = os.environ.get("MAX_CONCURRENT_GRADING", "").strip()
    if slots.isdigit() and int(slots) > 0:
        return int(slots)
    return max(1, (os.cpu_count() or 2) // 4)


def _log(event: str, **fields) -> None:
    """One JSON line per event, so logs can be grepped or shipped as they are."""
    fields.update({"event": event, "ts": round(time.time(), 3)})
    print("[GradingWorker] " + json.dumps(fields, ensure_ascii=False, default=str), flush=True)


def _rss_mb() -> Optional[float]:
    """Resident memory of this process (Linux); None where /proc is not available."""
    try:
        with open("/proc/self/statm") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 1)
    except Exception:
        return None


class _Heartbeat:
    """Keeps the lease on a job alive while the (slow) grading runs."""

    def __init__(self, session_factory: Callable[[], Session], job_id: int, worker_id: str):
        self._factory = session_factory
        self._job_id = job_id
        self._worker_id = worker_id
        self._stop = threading.Event()
        self.lost = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self):
        interval = gq.heartbeat_seconds()
        while not self._stop.wait(interval):
            db = self._factory()
            try:
                if not gq.heartbeat(db, self._job_id, self._worker_id):
                    self.lost = True
                    return
            except Exception as e:
                print(f"[GradingWorker] heartbeat error on job {self._job_id}: {e}", flush=True)
            finally:
                db.close()


def process_job(
    session_factory: Callable[[], Session],
    job_id: int,
    worker_id: str,
    pipeline: Callable = run_ai_pipeline,
) -> str:
    """
    Grades one claimed job. Returns "completed", "queued" (will retry), "failed", or "lost" (the
    lease moved to another worker; nothing was saved). The recording stays in the database until
    the grade is committed.
    """
    from app.models.grading_job import GradingJob
    from app.models.question import Question
    from sqlalchemy.orm import undefer

    db = session_factory()
    tmp_path = None
    try:
        job = (
            db.query(GradingJob)
            .options(undefer(GradingJob.audio))
            .filter(GradingJob.id == job_id)
            .first()
        )
        if job is None:
            return "lost"
        submission = job.submission
        submission_id = submission.id
        question = db.query(Question).filter(Question.id == submission.question_id).first()
        model_answer = (question.model_answer if question else "") or ""
        keywords = (question.keywords if question else "") or ""
        # Server-side evidence recorded at submit time (exam_evidence); NULL provenance = an answer
        # queued before it existed, graded the old way.
        face_id_score = submission.face_score
        evidence = {
            "integrity_score": submission.facial_score,
            "face_verification": submission.face_verification,
            "integrity_status": submission.integrity_status,
            "face_checks": submission.face_checks,
        }
        if job.audio:
            with tempfile.NamedTemporaryFile(delete=False, suffix=job.audio_suffix or ".webm") as tmp:
                tmp.write(job.audio)
                tmp_path = tmp.name
        attempt = job.attempts
        alerts, voice_emb, has_face = job.anti_cheat_alerts or "{}", job.voice_embedding, bool(job.has_faceprint)
        db.rollback()  # don't hold a transaction open for the minutes grading may take

        cpu0, wall0 = time.process_time(), time.perf_counter()
        with _Heartbeat(session_factory, job_id, worker_id) as hb:
            try:
                ai = pipeline(tmp_path, model_answer, keywords, alerts, voice_emb)
                fields = compute_grade(ai, face_id_score, has_face, **evidence)
            except Exception as e:
                status = gq.fail_attempt(db, job_id, worker_id, f"{type(e).__name__}: {e}")
                _log("attempt_failed", job=job_id, attempt=attempt, new_status=status,
                     error=str(e)[:300], process_ms=int((time.perf_counter() - wall0) * 1000))
                return status or "lost"
        if hb.lost:
            _log("lease_lost", job=job_id, attempt=attempt)
            return "lost"

        if not gq.complete(db, job_id, worker_id, fields):
            _log("lease_lost", job=job_id, attempt=attempt)
            return "lost"
        _log(
            "completed", job=job_id, submission=submission_id, attempt=attempt,
            process_ms=int((time.perf_counter() - wall0) * 1000),
            cpu_seconds=round(time.process_time() - cpu0, 2),  # whole process: shared with parallel jobs
            rss_mb=_rss_mb(),
        )
        return "completed"
    except Exception as e:
        # Bookkeeping failed (database unreachable, ...). Leave the job alone: if it is still ours,
        # the lease expires and another pass picks it up again with the recording intact.
        print(f"[GradingWorker] job {job_id} error: {traceback.format_exc()}", flush=True)
        try:
            db.rollback()
        except Exception:
            pass
        return "error"
    finally:
        db.close()
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class Worker:
    def __init__(self, session_factory: Callable[[], Session], concurrency: int, pipeline: Callable = run_ai_pipeline):
        self.session_factory = session_factory
        self.concurrency = max(1, concurrency)
        self.pipeline = pipeline
        self.stop = threading.Event()
        self.base_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

    def run_one(self, slot: int) -> Optional[str]:
        """Claim and grade a single job. Returns its outcome, or None if the queue was empty."""
        worker_id = f"{self.base_id}#{slot}"
        db = self.session_factory()
        try:
            job_id = gq.claim_next(db, worker_id)
        finally:
            db.close()
        if job_id is None:
            return None
        return process_job(self.session_factory, job_id, worker_id, self.pipeline)

    def maintenance(self) -> None:
        db = self.session_factory()
        try:
            recovered = gq.recover_stale(db)
            purged = gq.purge_expired_audio(db)
            if recovered or purged:
                _log("maintenance", recovered_stale=recovered, purged_audio=purged)
        finally:
            db.close()

    def _slot_loop(self, slot: int) -> None:
        while not self.stop.is_set():
            try:
                outcome = self.run_one(slot)
            except Exception:
                print(f"[GradingWorker] slot {slot}: {traceback.format_exc()}", flush=True)
                outcome = None
                self.stop.wait(5)
            if outcome is None:
                self.stop.wait(POLL_SECONDS)

    def _maintenance_loop(self) -> None:
        last_stats = 0.0
        while not self.stop.is_set():
            try:
                self.maintenance()
                if time.time() - last_stats >= 60:
                    last_stats = time.time()
                    db = self.session_factory()
                    try:
                        m = gq.metrics(db, window_minutes=15)
                    finally:
                        db.close()
                    _log("stats", queued=m["queued"], processing=m["processing"], failed=m["failed"],
                         oldest_queued_seconds=m["oldest_queued_seconds"],
                         wait_ms=m["queue_wait_ms"], process_ms=m["process_ms"], rss_mb=_rss_mb())
            except Exception:
                print(f"[GradingWorker] maintenance: {traceback.format_exc()}", flush=True)
            self.stop.wait(MAINTENANCE_SECONDS)

    def serve(self) -> None:
        threads = [threading.Thread(target=self._maintenance_loop, daemon=True, name="grading-maint")]
        threads += [
            threading.Thread(target=self._slot_loop, args=(i,), daemon=True, name=f"grading-{i}")
            for i in range(self.concurrency)
        ]
        for t in threads:
            t.start()
        _log("started", worker=self.base_id, concurrency=self.concurrency)
        try:
            while not self.stop.is_set():
                self.stop.wait(1)
        finally:
            # Jobs still running when we exit are not lost: their heartbeat stops, and the next
            # worker puts them back in the queue after GRADING_STALE_SECONDS.
            _log("stopping", worker=self.base_id)


def _preload_models() -> None:
    for name, load in (
        ("whisper", lambda: __import__("app.services.speech_ai", fromlist=["x"]).speech_analyzer.model),
        ("sbert", lambda: __import__("app.services.nlp_ai", fromlist=["x"]).nlp_analyzer.model),
        ("voice", lambda: __import__("app.services.voice_ai", fromlist=["x"]).voice_service.encoder),
    ):
        try:
            t0 = time.perf_counter()
            load()
            _log("model_loaded", model=name, seconds=round(time.perf_counter() - t0, 1), rss_mb=_rss_mb())
        except Exception as e:
            _log("model_load_failed", model=name, error=str(e)[:300])


def _wait_for_schema(engine) -> None:
    """The queue table and the grading_status column must exist before the first claim."""
    from app.core.database import Base, _column_exists, ensure_migrations
    import app.models  # noqa: F401 — register every table

    while True:
        try:
            Base.metadata.create_all(bind=engine)
            ensure_migrations()
            if _column_exists("exam_submissions", "grading_status"):
                return
        except Exception as e:
            print(f"[GradingWorker] waiting for database schema: {e}", flush=True)
        time.sleep(5)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # Importing the database module runs the same fail-closed configuration checks as the API.
    from app.core.config import is_production
    from app.core.database import engine, verify_database_connection

    if is_production():
        verify_database_connection()
    _wait_for_schema(engine)
    worker = Worker(sessionmaker(autocommit=False, autoflush=False, bind=engine), worker_concurrency())
    signal.signal(signal.SIGTERM, lambda *_: worker.stop.set())
    signal.signal(signal.SIGINT, lambda *_: worker.stop.set())
    if os.environ.get("GRADING_PRELOAD_MODELS", "1").strip().lower() not in ("0", "false", "no"):
        _preload_models()
    worker.serve()


if __name__ == "__main__":
    main()
