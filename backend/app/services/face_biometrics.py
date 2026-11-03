"""
Face ID via InsightFace ArcFace (self-hosted ONNX — no API tokens).

Uses buffalo_sc on CPU for HF Spaces RAM limits.
Embeddings are 512-dim; cosine similarity for matching.
"""
from __future__ import annotations

import os
import threading
import traceback
from typing import Optional

import cv2
import numpy as np

# ArcFace buffalo_* embedding size
EMBEDDING_DIM = 512
# Security-first ArcFace threshold. Scores below 0.55 are not accepted as the
# enrolled identity; 0.45–0.55 is an explicit uncertain/manual-review band.
MATCH_THRESHOLD = 0.55
EXAM_THRESHOLD = 0.55


class FaceBiometricsService:
    def __init__(self):
        self._app = None
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None
        self.engine = "insightface"

    def _root(self) -> str:
        return os.environ.get("INSIGHTFACE_HOME", "/tmp/insightface")

    def _ensure_app(self):
        if self._app is not None:
            return
        with self._lock:
            if self._app is not None:
                return
            try:
                from insightface.app import FaceAnalysis

                root = self._root()
                os.makedirs(root, exist_ok=True)
                # buffalo_sc = small/CPU-friendly; still far more accurate than face-api.js
                model_name = os.environ.get("INSIGHTFACE_MODEL", "buffalo_sc")
                app = FaceAnalysis(
                    name=model_name,
                    root=root,
                    providers=["CPUExecutionProvider"],
                )
                app.prepare(ctx_id=-1, det_size=(320, 320))
                self._app = app
                self._load_error = None
                print(f"[Face ID] InsightFace ready ({model_name}, dim={EMBEDDING_DIM})")
            except Exception as e:
                self._load_error = str(e)
                print(f"[Face ID] InsightFace load failed: {traceback.format_exc()}")
                raise RuntimeError(f"InsightFace unavailable: {e}") from e

    def is_ready(self) -> bool:
        try:
            self._ensure_app()
            return self._app is not None
        except Exception:
            return False

    def get_status(self) -> dict:
        return {
            "engine": self.engine,
            "ready": self._app is not None and self._load_error is None,
            "embedding_dim": EMBEDDING_DIM,
            "error": self._load_error,
            "model": os.environ.get("INSIGHTFACE_MODEL", "buffalo_sc"),
        }

    def _decode_bgr(self, image_bytes: bytes) -> np.ndarray:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("تعذّر قراءة صورة الوجه")
        return img

    def extract_embedding(self, image_bytes: bytes) -> dict:
        """
        Detect largest face and return L2-normalized 512-d embedding.
        """
        self._ensure_app()
        img = self._decode_bgr(image_bytes)
        faces = self._app.get(img)
        if not faces:
            raise ValueError("لم يتم العثور على وجه في الصورة — انظر للكاميرا بوضوح")

        # Largest face by bbox area
        face = max(faces, key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])))
        emb = np.array(face.embedding, dtype=np.float32).flatten()
        if emb.shape[0] != EMBEDDING_DIM:
            raise RuntimeError(f"Unexpected embedding dim {emb.shape[0]} (expected {EMBEDDING_DIM})")

        norm = float(np.linalg.norm(emb))
        if norm > 1e-6:
            emb = emb / norm

        pose = getattr(face, "pose", None)
        pose_list = [float(x) for x in pose] if pose is not None else None

        return {
            "embedding": emb.tolist(),
            "det_score": float(getattr(face, "det_score", 0.0)),
            "bbox": [float(x) for x in face.bbox],
            "pose": pose_list,  # pitch, yaw, roll if available
            "num_faces": len(faces),
        }

    def average_embeddings(self, embeddings: list[list[float]]) -> list[float]:
        if not embeddings:
            raise ValueError("No embeddings to average")
        mat = np.array(embeddings, dtype=np.float32)
        avg = mat.mean(axis=0)
        n = float(np.linalg.norm(avg))
        if n > 1e-6:
            avg = avg / n
        return avg.tolist()

    def verify_face(
        self,
        stored_embedding: list[float],
        current_embedding: list[float],
        threshold: float = None,
    ) -> dict:
        if threshold is None:
            threshold = EXAM_THRESHOLD

        vec1 = np.array(stored_embedding, dtype=np.float32).flatten()
        vec2 = np.array(current_embedding, dtype=np.float32).flatten()

        if vec1.shape != vec2.shape or vec1.shape[0] != EMBEDDING_DIM:
            return {
                "similarity_score": 0.0,
                "distance": 999.0,
                "is_match": False,
                "report": (
                    f"Face embedding outdated ({vec1.shape[0]}-d). "
                    "أعد تسجيل Face ID (InsightFace 512-d)."
                ),
            }

        n1 = float(np.linalg.norm(vec1))
        n2 = float(np.linalg.norm(vec2))
        if n1 < 1e-6 or n2 < 1e-6:
            sim = 0.0
        else:
            sim = float(np.dot(vec1, vec2) / (n1 * n2))

        sim = max(-1.0, min(1.0, sim))
        # Map cosine [-1,1] → display mostly [0,100] for same-person range
        score = max(0.0, min(100.0, (sim + 1.0) * 50.0))  # conservative display
        # Better display for ArcFace: cosine 0..1 typical for same identity after ReLU-ish
        score = max(0.0, min(100.0, sim * 100.0))

        is_match = sim >= threshold
        distance = float(1.0 - sim)

        if is_match:
            report = f"Face ID match confirmed ({score:.1f}%)"
        elif sim >= 0.45:
            report = f"⚠️ Face identity uncertain — manual review required ({score:.1f}%)"
        else:
            report = f"⚠️ FACE MISMATCH: Face does not match enrolled Face ID ({score:.1f}%)"

        return {
            "similarity_score": round(score, 1),
            "distance": round(distance, 4),
            "cosine": round(sim, 4),
            "is_match": is_match,
            "report": report,
        }

    def verify_image(
        self,
        stored_embedding: list[float],
        image_bytes: bytes,
        threshold: float = None,
    ) -> dict:
        extracted = self.extract_embedding(image_bytes)
        result = self.verify_face(stored_embedding, extracted["embedding"], threshold=threshold)
        result["num_faces"] = extracted["num_faces"]
        result["det_score"] = extracted["det_score"]
        result["pose"] = extracted.get("pose")
        return result


face_biometrics_service = FaceBiometricsService()
