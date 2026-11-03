"""
Speech analysis powered by faster-whisper.

Why faster-whisper instead of openai-whisper?
  - Same models, but the CTranslate2 engine is 4-8x faster on CPU.
  - Uses int8 quantization, so the "medium" model only needs ~1.5GB RAM
    instead of ~3GB for openai-whisper.
  - Supports word-level timestamps natively.
  - Result: we can run "medium" (much better Arabic accuracy than "small")
    without blowing past the 5-minute submit timeout.
"""

import os
import re
import threading
import time
import traceback
import warnings
warnings.filterwarnings("ignore")


def _cpu_threads() -> int:
    """
    Cores per transcription. Several answers are graded at once, so each job gets a share of the
    machine rather than all of it: left unset, CTranslate2 takes every core for every job and
    parallel jobs end up fighting each other. Read together with MAX_CONCURRENT_GRADING, which
    decides how many jobs there are.
    """
    explicit = os.environ.get("WHISPER_CPU_THREADS", "").strip()
    if explicit.isdigit() and int(explicit) > 0:
        return int(explicit)
    cores = os.cpu_count() or 2
    slots = os.environ.get("MAX_CONCURRENT_GRADING", "").strip()
    jobs = int(slots) if slots.isdigit() and int(slots) > 0 else max(1, cores // 4)
    return max(1, cores // jobs)

# Make ffmpeg available (needed by faster-whisper to decode audio)
try:
    if os.name == "nt":  # Windows only
        import imageio_ffmpeg
        import shutil
        ffmpeg_src = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dst = os.path.join(os.path.dirname(ffmpeg_src), "ffmpeg.exe")
        if not os.path.exists(ffmpeg_dst):
            shutil.copy2(ffmpeg_src, ffmpeg_dst)
        os.environ["PATH"] = os.path.dirname(ffmpeg_dst) + os.pathsep + os.environ["PATH"]
except Exception:
    pass

# Arabic filler / hesitation markers
ARABIC_FILLERS = [
    "اه", "آه", "إه", "اهه", "امم", "ام", "يعني", "مم", "ممم",
    "هم", "هممم", "طبع", "طبعا", "خلاص", "عارف",
    "كده", "كدا", "اللي هو", "بمعنى", "بالظبط", "بالضبط", "وكده", "وكدا",
    "بقا", "بقى", "تمام", "يا سيدي", "يا ستي",
]


class SpeechAnalyzer:
    """faster-whisper STT + fluency analysis. Lazy-loaded with retry."""

    MAX_RETRIES = 3
    RETRY_DELAY = 2
    # "medium" gives much better Arabic/English oral-answer accuracy.
    # Override with WHISPER_MODEL=small if HF CPU-basic runs out of memory.
    requested_model = os.environ.get("WHISPER_MODEL", "medium").strip() or "medium"
    if os.environ.get("SPACE_ID") and requested_model == "small":
        requested_model = "medium"
    MODEL_SIZE = requested_model

    CPU_THREADS = _cpu_threads()

    # CTranslate2 runs one transcription at a time per worker: with the default of 1, grading
    # threads that call transcribe() together simply wait for each other. More workers give real
    # parallelism at the cost of memory per worker — measure before raising it.
    _num_workers_env = os.environ.get("WHISPER_NUM_WORKERS", "").strip()
    NUM_WORKERS = int(_num_workers_env) if _num_workers_env.isdigit() else 1

    def __init__(self):
        self._model = None
        self._load_failed = False
        self._lock = threading.Lock()
        self.filler_prompt = "اه يعني اممم طيب بصراحة خلاص كدة تمام ممم إه"

    @property
    def model(self):
        # Submissions are graded in parallel worker threads, so two of them can reach an unloaded
        # model at the same moment. Without the lock both would load their own copy of Whisper —
        # two gigabytes each — and the second would quietly replace the first.
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._load_model()
        return self._model

    def _load_model(self):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                print(f"[SpeechAI] Loading faster-whisper '{self.MODEL_SIZE}' (int8, attempt {attempt}/{self.MAX_RETRIES})...")
                from faster_whisper import WhisperModel
                # int8 = smaller memory + faster CPU inference, same accuracy as fp16.
                # cpu_threads is capped so parallel jobs share the cores instead of each
                # claiming all of them and thrashing: left at 0, every job takes every core.
                self._model = WhisperModel(
                    self.MODEL_SIZE,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.CPU_THREADS,
                    num_workers=max(1, self.NUM_WORKERS),
                )
                self._load_failed = False
                print(f"[SpeechAI] faster-whisper '{self.MODEL_SIZE}' loaded ({self.CPU_THREADS} threads, {max(1, self.NUM_WORKERS)} workers).")
                break
            except Exception as e:
                print(f"[SpeechAI] Load failed (attempt {attempt}): {e}")
                traceback.print_exc()
                if attempt < self.MAX_RETRIES:
                    print(f"[SpeechAI] Retrying in {self.RETRY_DELAY}s...")
                    time.sleep(self.RETRY_DELAY)
                else:
                    self._load_failed = True
                    raise RuntimeError(
                        f"Failed to load faster-whisper after {self.MAX_RETRIES} attempts"
                    ) from e

    def is_ready(self) -> bool:
        return self._model is not None

    MAX_AI_AUDIO_SECONDS = 600  # Resource & compute spend limit: max 10 minutes per answer

    def _transcribe(self, audio_path: str, hint: str = "", word_timestamps: bool = False):
        """Run a transcription, return (full_text, segments_list, info)."""
        prompt = (hint + " " + self.filler_prompt).strip()
        language_hint = os.environ.get("WHISPER_LANGUAGE", "").strip() or None
        segments_iter, info = self.model.transcribe(
            audio_path,
            language=language_hint,  # None lets Whisper detect Arabic/English automatically.
            initial_prompt=prompt,
            word_timestamps=word_timestamps,
            vad_filter=True,            # skip pure-silence regions
            vad_parameters={"min_silence_duration_ms": 500},
            beam_size=5,
            condition_on_previous_text=False,  # avoid hallucinations from short clips
        )
        segments = []
        for s in segments_iter:
            segments.append(s)
            if s.end >= self.MAX_AI_AUDIO_SECONDS:
                break
        text = " ".join(s.text.strip() for s in segments if s.text).strip()
        return text, segments, info

    def transcribe_audio(self, audio_path: str, hint: str = "") -> str:
        text, _segments, _info = self._transcribe(audio_path, hint, word_timestamps=False)
        return text

    def analyze_fluency(self, audio_path: str, hint: str = "") -> dict:
        transcript, segments, _info = self._transcribe(audio_path, hint, word_timestamps=True)

        if not transcript or not segments:
            return {
                "transcript": transcript or "",
                "speech_score": 0.0,
                "fluency_report": "لم يتم الكشف عن كلام",
                "details": {
                    "wpm": 0, "filler_count": 0, "fillers_found": [],
                    "pause_count": 0, "repeat_count": 0, "total_duration": 0,
                },
            }

        # Flatten word-level info from all segments
        words_all = []
        for seg in segments:
            for w in (seg.words or []):
                words_all.append({"word": w.word, "start": w.start, "end": w.end})

        total_duration = (segments[-1].end - segments[0].start) if segments else 0
        actual_words = [w for w in transcript.split() if w.strip()]
        word_count = len(actual_words)
        wpm = (word_count / total_duration * 60) if total_duration > 0 else 0

        # ── Filler detection ─────────────────────────────────────────────────
        def normalize_arabic(text: str) -> str:
            text = re.sub(r"[ً-ْ]", "", text)        # remove harakat
            text = re.sub(r"(ا){2,}", "ا", text)          # collapse repeated Alef
            return text

        filler_count = 0
        fillers_found: list[str] = []
        words_text = [w["word"].strip() for w in words_all]
        for word in words_text:
            clean = normalize_arabic(word)
            if clean in ARABIC_FILLERS:
                filler_count += 1
                if clean not in fillers_found:
                    fillers_found.append(clean)

        # ── Long pauses (>1.5s gap between words) ────────────────────────────
        pause_count = 0
        for i in range(1, len(words_all)):
            gap = words_all[i]["start"] - words_all[i - 1]["end"]
            if gap > 1.5:
                pause_count += 1

        # ── Repetition detection ─────────────────────────────────────────────
        repeat_count = 0
        for i in range(1, len(words_text)):
            if normalize_arabic(words_text[i - 1]) and \
               normalize_arabic(words_text[i - 1]) == normalize_arabic(words_text[i]):
                repeat_count += 1

        # ── Score ────────────────────────────────────────────────────────────
        penalty = 0
        penalty += filler_count * 5
        penalty += pause_count * 8
        penalty += repeat_count * 6
        if wpm < 60:
            penalty += 10
        elif wpm < 80:
            penalty += 5
        elif wpm > 200:
            penalty += 5
        speech_score = max(0.0, min(100.0, 100.0 - penalty))

        # ── Arabic report ────────────────────────────────────────────────────
        report_lines: list[str] = []
        if speech_score >= 85:
            report_lines.append("تحدث بطلاقة وثقة")
        elif speech_score >= 70:
            report_lines.append("تحدث بشكل مقبول مع بعض التردد")
        elif speech_score >= 50:
            report_lines.append("تردد ملحوظ أثناء الإجابة")
        else:
            report_lines.append("تلعثم واضح — لم يكن واثقاً من إجابته")

        details_lines: list[str] = []
        if filler_count > 0:
            details_lines.append(f"كلمات تردد ({filler_count}): {', '.join(fillers_found)}")
        if pause_count > 0:
            details_lines.append(f"توقفات طويلة: {pause_count} مرة")
        if repeat_count > 0:
            details_lines.append(f"تكرار كلمات: {repeat_count} مرة")
        speed_label = (
            "بطيء جداً" if wpm < 60 else
            "بطيء" if wpm < 80 else
            "طبيعي" if wpm <= 160 else
            "سريع"
        )
        details_lines.append(f"عدد الكلمات: {word_count} كلمة | سرعة الكلام: {wpm:.0f} كلمة/دقيقة ({speed_label})")
        if details_lines:
            report_lines.append("الملاحظات:")
            report_lines.extend(f"  • {d}" for d in details_lines)
        fluency_report = "\n".join(report_lines)

        return {
            "transcript": transcript,
            "speech_score": round(speech_score, 1),
            "fluency_report": fluency_report,
            "details": {
                "wpm": round(wpm, 1),
                "filler_count": filler_count,
                "fillers_found": fillers_found,
                "pause_count": pause_count,
                "repeat_count": repeat_count,
                "total_duration": round(total_duration, 1),
            },
        }


# Singleton (lazy — model loads on first use)
speech_analyzer = SpeechAnalyzer()
