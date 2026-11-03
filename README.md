# OralIQ

An Arabic-first platform for **oral exams online**. A lecturer writes a question and a model
answer; students answer out loud from a phone or laptop; the grade comes back with a transcript,
a fluency reading and an integrity report. Built by [GharTech](mailto:ghartech1@gmail.com).

The product is Arabic-first and fully bilingual (Arabic / English, RTL and LTR).

## How a submission is scored

One answer produces one grade, weighted:

| Weight | What it measures | How |
|-------:|------------------|-----|
| **80%** | Content — does the answer say the right thing | Sentence-BERT similarity against the model answer, plus keyword cover |
| **10%** | Delivery — fluency, pace, filler words | Derived from the Whisper transcript and its word timings |
| **10%** | Integrity — was the student alone and present | Alerts raised in the browser from the webcam, aggregated server-side into one score |

Two rules sit on top of the weighting: an answer that fails on content cannot pass overall, and a
severe integrity event applies a penalty rather than merely being noted. Identity is never
confirmed from a single weak biometric — a face match and a voice match must agree.

## Stack

**Frontend** — React 19, Vite 7, TypeScript, Tailwind v4. The marketing page is pre-rendered at
build time; the app is a SPA. Fonts are Alexandria (display) and IBM Plex Sans Arabic.

**Backend** — FastAPI on Python 3.10, SQLAlchemy, PostgreSQL in production and SQLite for local
development.

**Models.** Everything on the server runs on CPU, and nothing is sent to a third-party AI API.
Watching the student happens in their own browser, so video never leaves the device — only the
audio and a summary of the alerts are uploaded.

| Job | Model | Runs |
|-----|-------|------|
| Speech to text | faster-whisper `medium`, int8 | Server |
| Answer grading | `paraphrase-multilingual-MiniLM-L12-v2` | Server |
| Voice identity | Resemblyzer `VoiceEncoder`, 256-dim | Server |
| Face identity | InsightFace `buffalo_sc` | Server |
| Gaze | MobileGaze (ONNX Runtime) | Server |
| Face mesh and landmarks | MediaPipe FaceMesh | Browser |
| Objects in frame | MediaPipe `ObjectDetector` | Browser |

## Layout

```
backend/
  app/
    api/endpoints/   exams, auth, questions, face, voice, speech, users
    services/        one module per model
    models/          SQLAlchemy tables
    core/            config, database, security
    tests/
frontend/
  src/
    pages/           app screens, incl. ExamRoom
    components/      UI kit, home page sections, charts
    content/         company details and client list
  DESIGN.md          the design system — read before changing any UI
scripts/
```

## Running it locally

**Prerequisites:** Python 3.10, Node 20+, and `ffmpeg` on PATH (faster-whisper decodes audio
with it).

```bash
# Backend — first run downloads about 1.3GB of model weights
cd backend
python -m venv venv
venv/Scripts/activate        # Windows; use source venv/bin/activate elsewhere
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
# Frontend
cd frontend
npm install
npm run dev
```

The run mode has no default: copy `backend/local.env.example` to `backend/local.env` (it sets
`ENV=dev`) or start with `python run.py`, which sets it for you. In development with no
`DATABASE_URL` the backend creates a local SQLite file, so nothing else is needed to get started.

## Configuration

Every setting is documented in [`backend/local.env.example`](backend/local.env.example). Copy it
to `backend/local.env` and fill in what you need.

`ENV` must be one of `dev`, `test`, `production`; unset or anything else, the API and the grading
worker refuse to start (and `dev`/`test` are refused on a Hugging Face Space). With
`ENV=production` **the server refuses to start**, listing every problem at once, unless:

- `SECRET_KEY` — signs access tokens; at least 32 random characters. Generate it once and keep the
  same value for the life of the deployment: change it and every signed-in user is logged out,
  mid-exam included. Production never generates or stores one.
- `DATABASE_URL` — PostgreSQL, reachable at startup. There is no SQLite fallback.
- `ALLOWED_ORIGINS` — the `https://` origins allowed to call the API, comma separated, matched
  exactly. `*` is rejected.

In production `/docs`, `/redoc`, `/openapi.json` and `/debug` are switched off.

### How an answer gets graded

Submitting stores the recording and a grading job in the database in one transaction and returns
at once (`202`). A separate worker process (`python -m app.worker`) claims jobs, runs Whisper,
SBERT and the voice check, and saves the grade; the exam room polls
`/exams/submissions/{id}/grading` and shows *waiting → grading → graded* (or *failed*, which a
lecturer can re-run with `/exams/submissions/{id}/regrade`). Jobs survive restarts: a job whose
worker stops heart-beating goes back to the queue. By default the API starts the worker itself
(`GRADING_WORKER_MODE=embedded`); see `backend/local.env.example` for running it separately.
Queue depth and timings: `GET /api/v1/exams/grading/metrics` (admin). Load test:
`backend/scripts/load_test_submit.py`.

The settings that decide throughput:

- `MAX_CONCURRENT_GRADING` — how many answers one worker grades at once. Each job wants a
  few cores and roughly 2GB, so this is what caps grading throughput per instance. Answers past
  it wait in the queue. Defaults to cores / 4.
- `WHISPER_CPU_THREADS` — cores per transcription. Defaults to cores / `MAX_CONCURRENT_GRADING`.
- `TRUST_PROXY` — set this **only** when a reverse proxy you control sets `X-Forwarded-For`.
  Without a proxy in front, any caller could claim any IP.

## Tests

```bash
cd backend && pytest app/tests -q
```

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```

The backend tests run against an in-memory database and never touch a real one.

## Deployment

The backend is a container; `backend/Dockerfile` builds it with the CPU-only torch wheel and keeps
model weights under `/models`, which is meant to be a mounted volume — without one, every restart
re-downloads the weights while the first students wait. It runs a single API worker on purpose: the
rate limiter counts per process. Grading runs in its own process (started by the API by default).

Sizing is governed by transcription, not by how many accounts exist: students record in the
browser and the server only works at the moment of submit. Measure `MAX_CONCURRENT_GRADING`
against a real recording on the target machine before promising a class size.
