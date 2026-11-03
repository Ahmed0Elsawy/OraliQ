from typing import Any, List, Optional
import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import tempfile, os, json, traceback
import numpy as np

from app.api import deps
from app.core.uploads import MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, read_upload_capped
from app.models.user import User
from app.services import service_pause
from app.services.voice_ai import voice_service
from app.services.face_biometrics import EMBEDDING_DIM as FACE_DIM

router = APIRouter()

ALLOWED_AUDIO_EXTS = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".mp4"}


def _safe_audio_suffix(filename: Optional[str]) -> str:
    if not filename:
        return ".webm"
    raw_ext = os.path.splitext(os.path.basename(filename))[1].lower()
    return raw_ext if raw_ext in ALLOWED_AUDIO_EXTS else ".webm"


def _has_voiceprint(user: User) -> bool:
    return bool(user.voice_embedding and len(user.voice_embedding) > 10)


def _has_faceprint(user: User) -> bool:
    if not user.face_embedding or len(user.face_embedding) < 10:
        return False
    try:
        emb = json.loads(user.face_embedding)
        return isinstance(emb, list) and len(emb) == FACE_DIM
    except Exception:
        return False


def _can_enroll(user: User) -> bool:
    """First enrollment always allowed; re-enroll only if lecturer permitted."""
    if not _has_voiceprint(user):
        return True
    if not user.voice_locked:
        return True
    return bool(user.voice_reenroll_allowed)


def _can_enroll_face(user: User) -> bool:
    """Same rule for the face print, judged on the face print itself (not the voice one)."""
    if not _has_faceprint(user):
        return True
    if not user.face_locked:
        return True
    return bool(user.voice_reenroll_allowed)


def _lecturer_linked_to_student(db: Session, lecturer: User, student_id: int) -> bool:
    """A lecturer may only manage students who took one of their own exams (an assignment alone
    doesn't count: see app/services/student_access.py). Admins: any student."""
    from app.services import student_access
    return student_access.can_access_student(db, lecturer, student_id)


@router.get("/status")
def get_voice_status(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Returns whether the current logged-in user has enrolled a voice print."""
    has_voice = _has_voiceprint(current_user)
    has_face = _has_faceprint(current_user)
    status = voice_service.get_status()
    return {
        "has_voiceprint": has_voice,
        "has_faceprint": has_face,
        "biometrics_complete": has_voice and has_face,
        "user_id": current_user.id,
        "full_name": current_user.full_name,
        "engine": status["engine"],
        "engine_ready": status["ready"],
        "embedding_dim": status["embedding_dim"],
        "face_embedding_dim": FACE_DIM,
        "voice_locked": bool(current_user.voice_locked) if has_voice else False,
        "face_locked": bool(current_user.face_locked) if has_face else False,
        "voice_reenroll_allowed": bool(current_user.voice_reenroll_allowed),
        "can_reenroll": _can_enroll(current_user),
    }


@router.post("/enroll")
async def enroll_voice_print(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    audio: UploadFile = File(...),
) -> Any:
    """Enrolls a user's voice print from a single audio file (offloaded to worker thread)."""
    if not _can_enroll(current_user):
        raise HTTPException(
            status_code=403,
            detail="بصمة الصوت مقفولة — اطلب من المحاضر السماح بإعادة التسجيل",
        )

    if not audio or not audio.filename:
        raise HTTPException(status_code=400, detail="Audio file is required")

    suffix = _safe_audio_suffix(audio.filename)
    content = await read_upload_capped(audio, MAX_AUDIO_BYTES)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        embedding = await anyio.to_thread.run_sync(voice_service.extract_embedding, tmp_path)
        if not embedding or len(embedding) == 0:
            raise HTTPException(status_code=422, detail="Could not extract voice features from audio")

        current_user.voice_embedding = json.dumps(embedding)
        current_user.voice_locked = True
        current_user.voice_reenroll_allowed = False
        db.commit()
        db.refresh(current_user)

        return {
            "ok": True,
            "message": "تم تسجيل بصمة الصوت بنجاح!",
            "has_voiceprint": True,
            "voice_locked": True,
        }
    except HTTPException:
        raise
    except Exception:
        print(f"[Voice Enroll Error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to record voice print")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/enroll-multi")
async def enroll_voice_print_multi(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    audio_files: List[UploadFile] = File(...),
) -> Any:
    if not _can_enroll(current_user):
        raise HTTPException(
            status_code=403,
            detail="بصمة الصوت مقفولة — اطلب من المحاضر السماح بإعادة التسجيل",
        )

    if not audio_files or len(audio_files) == 0:
        raise HTTPException(status_code=400, detail="At least one audio file is required")
    if len(audio_files) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 audio files allowed")

    embeddings: list[list[float]] = []
    tmp_paths: list[str] = []

    try:
        for i, audio in enumerate(audio_files):
            if not audio or not audio.filename:
                continue

            suffix = _safe_audio_suffix(audio.filename)
            content = await read_upload_capped(audio, MAX_AUDIO_BYTES)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                tmp_paths.append(tmp.name)

            try:
                emb = await anyio.to_thread.run_sync(voice_service.extract_embedding, tmp_paths[-1])
                if emb and len(emb) > 0:
                    embeddings.append(emb)
            except Exception as e:
                print(f"[Voice Enroll] Sample {i+1} extraction error: {e}")

        if len(embeddings) == 0:
            raise HTTPException(status_code=422, detail="Could not extract voice features from any audio file")

        emb_array = np.array(embeddings, dtype=np.float32)
        avg_embedding = np.mean(emb_array, axis=0)
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm

        final_embedding = avg_embedding.tolist()

        current_user.voice_embedding = json.dumps(final_embedding)
        current_user.voice_locked = True
        current_user.voice_reenroll_allowed = False
        db.commit()
        db.refresh(current_user)

        return {
            "ok": True,
            "message": f"تم تسجيل بصمة الصوت بنجاح من {len(embeddings)} عينات!",
            "has_voiceprint": True,
            "samples_used": len(embeddings),
            "engine": voice_service.get_status()["engine"],
            "embedding_dim": len(final_embedding),
            "voice_locked": True,
        }

    except HTTPException:
        raise
    except Exception:
        print(f"[Voice Enroll Multi Error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to process voice samples")
    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


@router.delete("/enroll")
def delete_voice_print(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if not _can_enroll(current_user) or not _can_enroll_face(current_user):
        raise HTTPException(
            status_code=403,
            detail="لا يمكن حذف البصمة — اطلب من المحاضر السماح بإعادة التسجيل",
        )
    current_user.voice_embedding = None
    current_user.voice_locked = False
    current_user.face_embedding = None
    current_user.face_locked = False
    current_user.voice_reenroll_allowed = False
    db.commit()
    return {"ok": True, "message": "Biometrics deleted (voice + face)"}


@router.post("/verify")
async def verify_voice_print(
    *,
    current_user: User = Depends(deps.get_current_user),
    audio: UploadFile = File(...),
) -> Any:
    if not _has_voiceprint(current_user):
        raise HTTPException(status_code=400, detail="لا توجد بصمة صوت مسجّلة لهذا الحساب")

    if not audio or not audio.filename:
        raise HTTPException(status_code=400, detail="ملف الصوت مطلوب")

    suffix = _safe_audio_suffix(audio.filename)
    content = await read_upload_capped(audio, MAX_AUDIO_BYTES)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        stored_emb = json.loads(current_user.voice_embedding)
        result = await anyio.to_thread.run_sync(voice_service.verify_voice, tmp_path, stored_emb)
        return {
            "ok": True,
            "is_match": bool(result.get("is_match")),
            "similarity_score": result.get("similarity_score"),
            "report": result.get("report") or (
                "تم التحقق من الهوية الصوتية" if result.get("is_match")
                else "الصوت لا يطابق بصمتك المسجّلة"
            ),
            "engine": result.get("engine") or voice_service.get_status().get("engine"),
        }
    except HTTPException:
        raise
    except Exception:
        print(f"[Voice Verify Error] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="فشل التحقق من بصمة الصوت")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/allow-reenroll/{student_id}")
def allow_voice_reenroll(
    student_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ("lecturer", "hr", "admin"):
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)

    student = db.query(User).filter(User.id == student_id, User.role == "student").first()
    if not student or not _lecturer_linked_to_student(db, current_user, student_id):
        raise HTTPException(status_code=404, detail="Student not found")
    if not _has_voiceprint(student) and not _has_faceprint(student):
        raise HTTPException(status_code=400, detail="Student has no biometrics enrolled yet")

    student.voice_reenroll_allowed = True
    db.commit()
    return {
        "ok": True,
        "message": f"تم السماح لـ {student.full_name} بإعادة تسجيل بصمة الصوت",
        "student_id": student.id,
        "voice_reenroll_allowed": True,
    }


@router.post("/revoke-reenroll/{student_id}")
def revoke_voice_reenroll(
    student_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    if current_user.role not in ("lecturer", "hr", "admin"):
        raise HTTPException(status_code=403, detail="Lecturers only")
    service_pause.ensure_lecturer_active(db, current_user)

    student = db.query(User).filter(User.id == student_id, User.role == "student").first()
    if not student or not _lecturer_linked_to_student(db, current_user, student_id):
        raise HTTPException(status_code=404, detail="Student not found")

    student.voice_reenroll_allowed = False
    db.commit()
    return {"ok": True, "message": "تم إلغاء السماح بإعادة التسجيل", "student_id": student.id}
