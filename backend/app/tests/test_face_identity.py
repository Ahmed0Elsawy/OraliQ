import numpy as np

from app.services.face_biometrics import face_biometrics_service


def _vector_with_cosine(cosine: float) -> tuple[list[float], list[float]]:
    enrolled = np.zeros(512, dtype=np.float32)
    current = np.zeros(512, dtype=np.float32)
    enrolled[0] = 1.0
    current[0] = cosine
    current[1] = np.sqrt(1.0 - cosine**2)
    return enrolled.tolist(), current.tolist()


def test_face_49_percent_is_not_verified():
    enrolled, current = _vector_with_cosine(0.498)
    result = face_biometrics_service.verify_face(enrolled, current)

    assert result["is_match"] is False
    assert result["similarity_score"] == 49.8
    assert "uncertain" in result["report"].lower()


def test_strong_face_match_is_verified():
    enrolled, current = _vector_with_cosine(0.8)
    result = face_biometrics_service.verify_face(enrolled, current)

    assert result["is_match"] is True
