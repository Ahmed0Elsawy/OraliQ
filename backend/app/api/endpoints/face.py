from typing import Any, List, Optional
import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
import json

from app.api import deps
from app.core.uploads import MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, read_upload_capped
from app.models.user import User
from app.services import exam_evidence, service_pause
from app.services.face_biometrics import face_biometrics_service, EMBEDDING_DIM
from app.services.gaze_ai import gaze_ai_service
from app.api.endpoints.voice import _can_enroll_face

router = APIRouter()


def _has_faceprint(user: User) -> bool:
    if not user.face_embedding or len(user.face_embedding) < 10:
        return False
    try:
        emb = json.loads(user.face_embedding)
        return isinstance(emb, list) and len(emb) == EMBEDDING_DIM
    except Exception:
        return False


@router.get("/status")
def get_face_status(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    has_face = _has_faceprint(current_user)
    stale = False
    if current_user.face_embedding and len(current_user.face_embedding) > 10 and not has_face:
        stale = True
    return {
        "has_faceprint": has_face,
        "face_locked": bool(current_user.face_locked) if has_face else False,
        "can_reenroll": _can_enroll_face(current_user) or stale,
        "embedding_dim": EMBEDDING_DIM,
        "engine": "insightface",
        "needs_reenroll": stale,
        "face_ready": face_biometrics_service.get_status(),
        "gaze_ready": gaze_ai_service.get_status(),
    }


@router.post("/enroll")
async def enroll_face_print(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    images: List[UploadFile] = File(...),
) -> Any:
    stale = bool(current_user.face_embedding) and not _has_faceprint(current_user)
    if not _can_enroll_face(current_user) and not stale:
        raise HTTPException(
            status_code=403,
            detail="Face ID مقفول — اطلب من المحاضر السماح بإعادة التسجيل",
        )

    if len(images) < 3:
        raise HTTPException(status_code=422, detail="أرسل 3 صور على الأقل لمسح Face ID")
    if len(images) > 10:
        raise HTTPException(status_code=422, detail="حد أقصى 10 صور")

    embeddings: list[list[float]] = []
    errors: list[str] = []
    for i, up in enumerate(images):
        try:
            raw = await read_upload_capped(up, MAX_IMAGE_BYTES)
            if len(raw) < 500:
                errors.append(f"image[{i}]: too small")
                continue
            extracted = await anyio.to_thread.run_sync(face_biometrics_service.extract_embedding, raw)
            embeddings.append(extracted["embedding"])
        except HTTPException:
            raise
        except Exception as e:
            print(f"[Face Enroll] image[{i}] rejected: {e}")
            errors.append(f"image[{i}]: no clear face")

    if len(embeddings) < 3:
        raise HTTPException(
            status_code=400,
            detail="Face not clear enough ({}/3). Improve lighting and try again. {}".format(
                len(embeddings), errors[:2]
            ),
        )

    avg = face_biometrics_service.average_embeddings(embeddings)
    current_user.face_embedding = json.dumps(avg)
    current_user.face_locked = True
    db.commit()
    db.refresh(current_user)

    return {
        "ok": True,
        "message": "تم تسجيل Face ID بنجاح (InsightFace)!",
        "has_faceprint": True,
        "face_locked": True,
        "embedding_dim": EMBEDDING_DIM,
        "samples_used": len(embeddings),
        "engine": "insightface",
    }


@router.post("/verify")
async def verify_face_print(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    image: UploadFile = File(...),
    exam_token: Optional[str] = Form(None),
) -> Any:
    """
    Compares one camera frame with the signed-in user's face print, here on the server, and
    RECORDS the result (FaceCheck) under that user and — when exam_token is given — that exam.
    Submissions take their face score from these records, never from a number the browser sends.
    A check without exam_token is answered as before but counts for no exam.
    """
    if not _has_faceprint(current_user):
        raise HTTPException(
            status_code=400,
            detail="لا يوجد Face ID مسجّل (أو قديم) — أعد تسجيل Face ID من الإعدادات",
        )

    # A face check for a paused lecturer's exam is refused (no evidence recorded for it).
    await anyio.to_thread.run_sync(lambda: service_pause.ensure_exam_token_available(db, exam_token))
    raw = await read_upload_capped(image, MAX_IMAGE_BYTES)
    stored = json.loads(current_user.face_embedding)
    exam_key = await anyio.to_thread.run_sync(lambda: exam_evidence.exam_key_from_token(db, exam_token))
    try:
        result = await anyio.to_thread.run_sync(
            lambda: face_biometrics_service.verify_image(stored, raw, threshold=0.55)
        )
    except ValueError as e:
        await anyio.to_thread.run_sync(
            lambda: exam_evidence.record_face_check(db, current_user, exam_key, None, no_face=True))
        return {
            "ok": True,
            "is_match": False,
            "similarity_score": 0.0,
            "no_face": True,
            "report": str(e),
            "recorded_for_exam": exam_key is not None,
        }
    # Any other failure (model unavailable, ...) raises: nothing is recorded, nothing passes.
    await anyio.to_thread.run_sync(
        lambda: exam_evidence.record_face_check(db, current_user, exam_key, result))

    return {
        "recorded_for_exam": exam_key is not None,
        "ok": True,
        "is_match": bool(result["is_match"]),
        "status": (
            "verified"
            if result["similarity_score"] >= 55
            else "uncertain"
            if result["similarity_score"] >= 45
            else "mismatch"
        ),
        "similarity_score": result["similarity_score"],
        "distance": result.get("distance"),
        "cosine": result.get("cosine"),
        "report": result["report"],
        "num_faces": result.get("num_faces"),
        "engine": "insightface",
    }


@router.post("/gaze")
async def analyze_gaze(
    *,
    current_user: User = Depends(deps.get_current_user),
    image: UploadFile = File(...),
    bbox: Optional[str] = Form(None),
) -> Any:
    """MobileGaze ONNX — pitch/yaw + direction for proctoring (offloaded to worker thread)."""
    raw = await read_upload_capped(image, MAX_IMAGE_BYTES)
    try:
        normalized_box = None
        if bbox:
            parsed = json.loads(bbox)
            if isinstance(parsed, list) and len(parsed) == 4:
                normalized_box = [float(v) for v in parsed]
        result = await anyio.to_thread.run_sync(
            lambda: gaze_ai_service.analyze_image_bytes(
                raw,
                normalized_face_bbox=normalized_box,
            )
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Gaze analysis failed")
    return {"ok": True, **result, "engine": "mobilegaze"}


# GET /descriptor removed: it handed the stored biometric template back to the browser,
# and nothing in the frontend used it. Verification happens server-side (/face/verify).


@router.delete("/enroll")
def delete_face_print(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if _has_faceprint(current_user) and current_user.face_locked and not current_user.voice_reenroll_allowed:
        raise HTTPException(
            status_code=403,
            detail="لا يمكن حذف Face ID — اطلب من المحاضر السماح بإعادة التسجيل",
        )
    current_user.face_embedding = None
    current_user.face_locked = False
    db.commit()
    return {"ok": True, "message": "Face ID deleted"}
