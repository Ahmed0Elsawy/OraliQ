"""
Gaze estimation via MobileGaze ONNX (self-hosted — no API tokens).

Downloads yakhyo/MobileGaze weights once, runs with onnxruntime on CPU.
Returns pitch/yaw degrees and a discrete direction for oral-exam proctoring.
"""
from __future__ import annotations

import os
import threading
import traceback
import urllib.request
from typing import Optional

import cv2
import numpy as np

MODEL_URL = os.environ.get(
    "GAZE_MODEL_URL",
    "https://github.com/yakhyo/gaze-estimation/releases/download/weights/mobileone_s0_gaze.onnx",
)
MODEL_NAME = "mobileone_s0_gaze.onnx"


class GazeAIService:
    def __init__(self):
        self._session = None
        self._input_name = None
        self._input_size = 448
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None

    def _model_dir(self) -> str:
        return os.environ.get("GAZE_MODEL_DIR", "/tmp/gaze_models")

    def _model_path(self) -> str:
        return os.path.join(self._model_dir(), MODEL_NAME)

    def _ensure_model_file(self) -> str:
        path = self._model_path()
        if os.path.isfile(path) and os.path.getsize(path) > 100_000:
            return path
        os.makedirs(self._model_dir(), exist_ok=True)
        tmp = path + ".download"
        print(f"[Gaze] Downloading MobileGaze → {path}")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        os.replace(tmp, path)
        return path

    def _ensure_session(self):
        if self._session is not None:
            return
        with self._lock:
            if self._session is not None:
                return
            try:
                import onnxruntime as ort

                path = self._ensure_model_file()
                sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
                inp = sess.get_inputs()[0]
                self._input_name = inp.name
                # NCHW → take H
                shape = inp.shape
                if len(shape) == 4 and isinstance(shape[2], int):
                    self._input_size = int(shape[2])
                self._session = sess
                self._load_error = None
                print(f"[Gaze] MobileGaze ready (input={self._input_size})")
            except Exception as e:
                self._load_error = str(e)
                print(f"[Gaze] load failed: {traceback.format_exc()}")
                raise RuntimeError(f"Gaze model unavailable: {e}") from e

    def is_ready(self) -> bool:
        try:
            self._ensure_session()
            return self._session is not None
        except Exception:
            return False

    def get_status(self) -> dict:
        return {
            "engine": "mobilegaze_onnx",
            "ready": self._session is not None and self._load_error is None,
            "error": self._load_error,
            "model": MODEL_NAME,
        }

    def _preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        size = self._input_size
        resized = cv2.resize(face_bgr, (size, size))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        # ImageNet-ish normalize used by many gaze nets
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        rgb = (rgb - mean) / std
        chw = np.transpose(rgb, (2, 0, 1))[None, ...]
        return chw

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        x = x - np.max(x, axis=-1, keepdims=True)
        e = np.exp(x)
        return e / np.sum(e, axis=-1, keepdims=True)

    def _decode_angles(self, outputs: list) -> tuple[float, float]:
        """
        Decode exactly like yakhyo/gaze-estimation:
        output[0] = yaw logits, output[1] = pitch logits,
        90 bins × 4 degrees − 180 degrees.
        Returns (pitch_degrees, yaw_degrees).
        """
        if len(outputs) != 2:
            raise RuntimeError(f"Expected 2 gaze outputs, got {len(outputs)}")

        yaw_logits = np.asarray(outputs[0], dtype=np.float32).reshape(1, -1)
        pitch_logits = np.asarray(outputs[1], dtype=np.float32).reshape(1, -1)
        if yaw_logits.shape[1] != 90 or pitch_logits.shape[1] != 90:
            raise RuntimeError(
                f"Expected 90 gaze bins, got yaw={yaw_logits.shape}, pitch={pitch_logits.shape}"
            )

        bins = np.arange(90, dtype=np.float32)
        yaw_probs = self._softmax(yaw_logits)
        pitch_probs = self._softmax(pitch_logits)
        yaw_deg = float(np.sum(yaw_probs[0] * bins) * 4.0 - 180.0)
        pitch_deg = float(np.sum(pitch_probs[0] * bins) * 4.0 - 180.0)
        return pitch_deg, yaw_deg

    def analyze_face_crop(self, face_bgr: np.ndarray) -> dict:
        self._ensure_session()
        inp = self._preprocess(face_bgr)
        raw = self._session.run(None, {self._input_name: inp})
        pitch, yaw = self._decode_angles(raw)

        # Raw classification is useful for diagnostics. The browser calibrates these
        # angles against each student's neutral pose before raising alerts.
        direction = "center"
        abs_p, abs_y = abs(pitch), abs(yaw)
        if abs_p >= abs_y and abs_p > 12:
            # Official draw function uses dy=-sin(pitch): positive points upward.
            direction = "up" if pitch > 0 else "down"
        elif abs_y > 14:
            # Official draw function uses dx=-sin(yaw): positive points left.
            direction = "left" if yaw > 0 else "right"

        return {
            "pitch": round(float(pitch), 2),
            "yaw": round(float(yaw), 2),
            "direction": direction,
            "looking_away": direction != "center",
        }

    def analyze_image_bytes(
        self,
        image_bytes: bytes,
        face_bbox: list[float] | None = None,
        normalized_face_bbox: list[float] | None = None,
    ) -> dict:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("تعذّر قراءة الصورة للـ gaze")

        h, w = img.shape[:2]
        if normalized_face_bbox and len(normalized_face_bbox) >= 4:
            nx1, ny1, nx2, ny2 = normalized_face_bbox[:4]
            x1, y1, x2, y2 = (
                int(nx1 * w),
                int(ny1 * h),
                int(nx2 * w),
                int(ny2 * h),
            )
        elif face_bbox and len(face_bbox) >= 4:
            x1, y1, x2, y2 = [int(v) for v in face_bbox[:4]]
        else:
            # Try InsightFace detector for a tight face crop
            try:
                from app.services.face_biometrics import face_biometrics_service

                face_biometrics_service._ensure_app()
                faces = face_biometrics_service._app.get(img)
                if not faces:
                    return {
                        "pitch": 0.0,
                        "yaw": 0.0,
                        "direction": "no_face",
                        "looking_away": True,
                        "no_face": True,
                    }
                face = max(faces, key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])))
                x1, y1, x2, y2 = [int(v) for v in face.bbox]
            except Exception:
                # Center crop fallback
                side = min(h, w)
                x1 = (w - side) // 2
                y1 = (h - side) // 2
                x2 = x1 + side
                y2 = y1 + side

        # Expand box slightly
        bw, bh = x2 - x1, y2 - y1
        x1 = max(0, int(x1 - 0.1 * bw))
        y1 = max(0, int(y1 - 0.1 * bh))
        x2 = min(w, int(x2 + 0.1 * bw))
        y2 = min(h, int(y2 + 0.1 * bh))
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            raise ValueError("Face crop empty")

        result = self.analyze_face_crop(crop)
        result["bbox"] = [x1, y1, x2, y2]
        result["no_face"] = False
        return result


gaze_ai_service = GazeAIService()
