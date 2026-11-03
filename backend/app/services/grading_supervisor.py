"""
Starts the grading worker as a child process of the API when GRADING_WORKER_MODE=embedded (the
default), and restarts it if it dies. That keeps a one-container deployment (Hugging Face Space,
a single VPS) working without a second service definition, while grading still runs in its own
process: a crash or a memory spike in Whisper cannot take the API down with it.

GRADING_WORKER_MODE=external — the API starts nothing; run `python -m app.worker` yourself.
GRADING_WORKER_MODE=off      — nothing grades (tests, or an API-only replica).
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def worker_mode() -> str:
    mode = os.environ.get("GRADING_WORKER_MODE", "embedded").strip().lower()
    return mode if mode in ("embedded", "external", "off") else "embedded"


class WorkerSupervisor:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._stopping = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="grading-supervisor")
        self._thread.start()

    def _run(self) -> None:
        backoff = 5
        while not self._stopping.is_set():
            started = time.time()
            try:
                self._proc = subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=str(_BACKEND_DIR))
                print(f"[GradingSupervisor] worker started (pid {self._proc.pid})", flush=True)
                code = self._proc.wait()
            except Exception as e:
                code = f"spawn error: {e}"
            if self._stopping.is_set():
                return
            # A worker that ran for a while gets restarted quickly; one that keeps dying at start
            # (no database, broken model download) backs off up to a minute between tries.
            backoff = 5 if time.time() - started > 300 else min(backoff * 2, 60)
            print(f"[GradingSupervisor] worker exited ({code}); restarting in {backoff}s", flush=True)
            self._stopping.wait(backoff)

    def stop(self, timeout: float = 10.0) -> None:
        self._stopping.set()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()


supervisor = WorkerSupervisor()
