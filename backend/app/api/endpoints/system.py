"""System maintenance endpoints (migrations, schema checks)."""
import os
from fastapi import APIRouter, HTTPException
from app.core.config import is_dev_env
from app.core.database import ensure_migrations, _column_exists, engine

router = APIRouter()


@router.get("/db-migrate")
def run_db_migrate() -> dict:
    """
    Apply pending DB schema patches (idempotent).
    Restricted outside dev once initial migrations are applied.
    """
    if not is_dev_env():
        raise HTTPException(status_code=403, detail="Forbidden in production")

    result = ensure_migrations()
    return {
        **result,
        "columns": {
            "face_embedding": _column_exists("users", "face_embedding"),
            "face_locked": _column_exists("users", "face_locked"),
            "face_score": _column_exists("exam_submissions", "face_score"),
        },
        "dialect": engine.dialect.name,
    }
