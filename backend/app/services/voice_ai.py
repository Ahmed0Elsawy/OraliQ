import numpy as np
import os
import json
import traceback

class VoiceBiometricsService:
    """
    Speaker Verification & Voice Biometrics Service.
    Uses resemblyzer VoiceEncoder (deep learning) to extract 256-dimensional
    speaker embeddings. Falls back to enhanced MFCC only if resemblyzer fails.
    """
    EMBEDDING_DIM_RESEMBLYZER = 256
    EMBEDDING_DIM_MFCC = 173

    def __init__(self):
        self.encoder = None
        self.use_resemblyzer = False
        self._load_error: str | None = None
        self._load_encoder()

    def _load_encoder(self):
        try:
            from resemblyzer import VoiceEncoder
            print("[Voice AI] Loading VoiceEncoder (resemblyzer deep learning)...")
            self.encoder = VoiceEncoder()
            self.use_resemblyzer = True
            self._load_error = None
            print("[Voice AI] VoiceEncoder loaded successfully (256-dim embeddings).")
        except Exception as e:
            self._load_error = str(e)
            print(f"[Voice AI] Could not load resemblyzer VoiceEncoder: {e}.")
            print("[Voice AI] Using enhanced MFCC fallback (less accurate for speaker ID).")
            self.encoder = None
            self.use_resemblyzer = False

    def is_ready(self) -> bool:
        return self.use_resemblyzer and self.encoder is not None

    def get_status(self) -> dict:
        return {
            "engine": "resemblyzer" if self.use_resemblyzer else "mfcc_fallback",
            "ready": self.is_ready(),
            "embedding_dim": self.EMBEDDING_DIM_RESEMBLYZER if self.use_resemblyzer else self.EMBEDDING_DIM_MFCC,
            "error": self._load_error,
        }

    def _convert_to_wav(self, audio_path: str) -> str:
        """Convert audio file to WAV format using ffmpeg if needed."""
        ext = os.path.splitext(audio_path)[1].lower()
        if ext in ('.wav', '.wave'):
            return audio_path
        
        wav_path = audio_path.rsplit('.', 1)[0] + '_converted.wav'
        try:
            import subprocess
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', audio_path, '-ar', '16000', '-ac', '1', wav_path],
                capture_output=True, timeout=30
            )
            if result.returncode == 0 and os.path.exists(wav_path):
                return wav_path
        except Exception as e:
            print(f"[Voice AI] ffmpeg conversion failed: {e}")
        
        return audio_path  # Return original if conversion fails

    def extract_embedding(self, audio_path: str) -> list[float]:
        """
        Extracts a float vector embedding (fingerprint) from an audio file.
        Returns a list of floats.
        """
        # Convert non-WAV formats first
        converted_path = self._convert_to_wav(audio_path)
        cleanup_converted = converted_path != audio_path
        
        try:
            if self.encoder is not None:
                try:
                    from resemblyzer import preprocess_wav
                    wav = preprocess_wav(converted_path)
                    embed = self.encoder.embed_utterance(wav)
                    return embed.tolist()
                except Exception as e:
                    print(f"[Voice AI Error] Resemblyzer embedding failed: {e}")

            # Enhanced MFCC fallback — uses more features for better speaker discrimination
            return self._extract_mfcc_embedding(converted_path)
        finally:
            if cleanup_converted and os.path.exists(converted_path):
                try:
                    os.unlink(converted_path)
                except:
                    pass

    def _extract_mfcc_embedding(self, audio_path: str) -> list[float]:
        """
        Enhanced MFCC-based speaker embedding.
        Uses MFCC + delta + delta-delta + spectral features for better discrimination.
        """
        import librosa
        
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Remove silence to focus on speech
        intervals = librosa.effects.split(y, top_db=25)
        if len(intervals) > 0:
            y_speech = np.concatenate([y[start:end] for start, end in intervals])
        else:
            y_speech = y
        
        if len(y_speech) < sr * 0.5:  # Less than 0.5s of speech
            raise RuntimeError("Audio too short for voice verification")
        
        # 1. MFCC (40 coefficients) — captures vocal tract shape
        mfcc = librosa.feature.mfcc(y=y_speech, sr=sr, n_mfcc=40, n_fft=2048, hop_length=512)
        mfcc_mean = np.mean(mfcc, axis=1)
        mfcc_std = np.std(mfcc, axis=1)
        
        # 2. Delta MFCC — captures speech dynamics unique to speaker
        delta_mfcc = librosa.feature.delta(mfcc)
        delta_mean = np.mean(delta_mfcc, axis=1)
        
        # 3. Delta-delta MFCC — captures acceleration patterns
        delta2_mfcc = librosa.feature.delta(mfcc, order=2)
        delta2_mean = np.mean(delta2_mfcc, axis=1)
        
        # 4. Spectral features — pitch and tone characteristics
        spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y_speech, sr=sr))
        spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=y_speech, sr=sr))
        spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y_speech, sr=sr))
        spectral_contrast = np.mean(librosa.feature.spectral_contrast(y=y_speech, sr=sr), axis=1)
        
        # 5. Fundamental frequency (F0) — vocal pitch
        f0 = librosa.yin(y_speech, fmin=50, fmax=600, sr=sr)
        f0_valid = f0[f0 > 0]
        f0_mean = np.mean(f0_valid) if len(f0_valid) > 0 else 0
        f0_std = np.std(f0_valid) if len(f0_valid) > 0 else 0
        
        # 6. Zero crossing rate — speech pattern
        zcr = np.mean(librosa.feature.zero_crossing_rate(y_speech))
        
        # Combine all features into one vector (40+40+40+40+3+7+2+1 = 173 dimensions)
        embedding = np.concatenate([
            mfcc_mean,           # 40
            mfcc_std,            # 40  
            delta_mean,          # 40
            delta2_mean,         # 40
            [spectral_centroid / 8000, spectral_bandwidth / 8000, spectral_rolloff / 8000],  # 3 (normalized)
            spectral_contrast,   # 7
            [f0_mean / 600, f0_std / 200],  # 2 (normalized)
            [zcr],               # 1
        ])
        
        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding.tolist()

    def verify_voice(self, audio_path: str, stored_embedding: list[float], threshold: float = None) -> dict:
        """
        Compares an audio file against a stored embedding vector.
        Returns similarity percentage (0-100), match boolean, and report string.
        
        Security-first thresholds:
        - Resemblyzer: 0.75
        - MFCC fallback: 0.82
        """
        if threshold is None:
            threshold = 0.75 if self.use_resemblyzer else 0.82
        
        try:
            current_embedding = self.extract_embedding(audio_path)
            
            vec1 = np.array(stored_embedding, dtype=np.float32)
            vec2 = np.array(current_embedding, dtype=np.float32)
            
            # Dimension mismatch = different extraction methods, cannot compare
            if vec1.shape != vec2.shape:
                return {
                    "similarity_score": 0.0,
                    "is_match": False,
                    "report": f"Voice embedding dimension mismatch ({vec1.shape} vs {vec2.shape}). Student must re-enroll voice."
                }

            # Cosine similarity
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                similarity_val = 0.0
            else:
                similarity_val = float(np.dot(vec1, vec2) / (norm1 * norm2))

            # Bound similarity between 0 and 1
            similarity_val = max(0.0, min(1.0, similarity_val))
            score_percent = round(similarity_val * 100, 1)

            is_match = similarity_val >= threshold

            if is_match:
                report = f"Voice match confirmed ({score_percent}%)"
            elif score_percent >= 60:
                report = f"⚠️ Voice identity uncertain — manual review required ({score_percent}%)"
            else:
                report = f"⚠️ VOICE MISMATCH: Voice does not match enrolled voice ({score_percent}% < {threshold*100:.0f}%)"

            return {
                "similarity_score": score_percent,
                "is_match": is_match,
                "report": report
            }
        except Exception as e:
            # SECURITY: On error, mark as FAILED — never assume match
            print(f"[Voice AI Error] Verification error: {traceback.format_exc()}")
            return {
                "similarity_score": 0.0,
                "is_match": False,
                "report": f"Voice verification failed: {str(e)}"
            }

voice_service = VoiceBiometricsService()
