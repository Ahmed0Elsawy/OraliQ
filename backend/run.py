"""Local dev launcher — loads local.env into os.environ, then starts uvicorn.

The OralIQ backend reads DATABASE_URL from os.environ (set by HF Spaces in prod).
Locally we load it from local.env via this launcher.

We use local.env (not .env) so pydantic-settings in app/core/config.py doesn't
try to validate DATABASE_URL/GEMINI_API_KEY as model fields.

This file is NOT part of the original OralIQ repo — it's local tooling only.
"""
import sys

# Ensure UTF-8 output on Windows (the OralIQ backend prints emojis/Arabic in logs)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv("local.env")

import os
# This launcher is the developer's machine by definition (auto-reload on). The app itself has no
# default run mode, so say so here; an ENV set in the shell or in local.env still wins.
os.environ.setdefault("ENV", "dev")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
