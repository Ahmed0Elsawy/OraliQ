from typing import Any, Optional
import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import tempfile
import os
import traceback

from app.api import deps
from app.core.uploads import MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, read_upload_capped
from app.models.user import User

router = APIRouter()

ALLOWED_AUDIO_EXTS = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".mp4"}


def _safe_audio_suffix(filename: Optional[str]) -> str:
    if not filename:
        return ".webm"
    raw_ext = os.path.splitext(os.path.basename(filename))[1].lower()
    return raw_ext if raw_ext in ALLOWED_AUDIO_EXTS else ".webm"


@router.post("/transcribe")
async def transcribe_speech(
    *,
    current_user: User = Depends(deps.get_current_user),
    audio: UploadFile = File(...),
    hint: str = Form(""),
) -> Any:
    """Convert a short voice recording to text (Whisper) in a worker thread."""
    if not audio or not audio.filename:
        raise HTTPException(status_code=400, detail="Audio file is required")

    suffix = _safe_audio_suffix(audio.filename)
    content = await read_upload_capped(audio, MAX_AUDIO_BYTES)
    if len(content) < 500:
        raise HTTPException(status_code=422, detail="Recording too short — speak longer")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from app.services.speech_ai import speech_analyzer
        safe_hint = (hint or "")[:500]
        text = await anyio.to_thread.run_sync(
            lambda: speech_analyzer.transcribe_audio(tmp_path, hint=safe_hint)
        )
        if not text or not text.strip():
            raise HTTPException(status_code=422, detail="Could not detect speech in recording")
        return {"text": text.strip()}
    except HTTPException:
        raise
    except Exception:
        print(f"[Speech Transcribe Error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Transcription failed")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
