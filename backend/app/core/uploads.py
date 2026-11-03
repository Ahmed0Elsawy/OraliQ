"""Bounded reads for uploaded files.

`await upload.read()` pulls the whole body into memory no matter how big it is, and the
Content-Length check in main.py is skipped by chunked requests. Read in chunks and stop as
soon as the cap is passed instead.
"""
from fastapi import HTTPException, UploadFile

MAX_AUDIO_BYTES = 40 * 1024 * 1024   # exam answers / enrollment clips
MAX_IMAGE_BYTES = 8 * 1024 * 1024    # face frames
_CHUNK = 1024 * 1024


async def read_upload_capped(upload: UploadFile, max_bytes: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = await upload.read(_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum is {max_bytes // (1024 * 1024)}MB.",
            )
    return bytes(buf)
