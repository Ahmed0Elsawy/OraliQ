"""
The grading itself: Whisper transcript + fluency, SBERT content score, voice match, anti-cheat
aggregation, and the weighting that turns them into one grade.

Moved here unchanged from the submit endpoint, which used to run it inside the HTTP request. It is
now called by the grading worker (app/worker.py). One deliberate difference: a crash inside Whisper
or SBERT used to be swallowed and saved as an ungraded answer; it now raises GradingError, so the
job is retried and, when retries run out, marked "failed" for a lecturer to re-run instead of
silently storing an empty grade. A voice-match or anti-cheat error stays non-fatal, as before.
"""
import json
import traceback
from typing import Any, Dict, Optional


class GradingError(Exception):
    """Whisper or SBERT failed; the attempt should be retried."""


def run_ai_pipeline(
    audio_path: Optional[str],
    model_answer: str,
    keywords: str,
    anti_cheat_alerts: str,
    voice_embedding: Optional[str],
) -> Dict[str, Any]:
    # No facial_score here: integrity comes from the server's own face checks (exam_evidence),
    # stored on the submission at submit time. The browser's alerts only become report text.
    out: Dict[str, Any] = {
        "transcript": None,
        "nlp_score": None,
        "speech_score": None,
        "voice_score": None,
        "cheat_report": None,
        "fluency_report": None,
    }

    if audio_path:
        from app.services.speech_ai import speech_analyzer
        from app.services.voice_ai import voice_service

        try:
            fluency = speech_analyzer.analyze_fluency(audio_path, hint=model_answer or "")
        except Exception as e:
            print(f"[AI Pipeline] Whisper failed: {traceback.format_exc()}")
            raise GradingError(f"speech-to-text failed: {e}") from e
        out["transcript"] = fluency["transcript"]
        out["speech_score"] = fluency["speech_score"]
        out["fluency_report"] = fluency["fluency_report"]

        if voice_embedding:
            try:
                stored_emb = json.loads(voice_embedding)
                voice_res = voice_service.verify_voice(audio_path, stored_emb, threshold=0.75)
                out["voice_score"] = voice_res["similarity_score"]
            except Exception as ve:
                print(f"[Voice Verify Error] {ve}")

    if out["transcript"] and model_answer:
        from app.services.nlp_ai import nlp_analyzer
        try:
            result = nlp_analyzer.evaluate_answer(out["transcript"], model_answer, keywords or "")
        except Exception as e:
            print(f"[AI Pipeline] SBERT failed: {traceback.format_exc()}")
            raise GradingError(f"answer scoring failed: {e}") from e
        out["nlp_score"] = result["score"]

    try:
        alerts = json.loads(anti_cheat_alerts or "{}")
        if alerts and isinstance(alerts, dict):
            from app.services.face_ai import face_analyzer
            out["cheat_report"] = face_analyzer.describe_client_alerts(alerts)
    except (json.JSONDecodeError, Exception) as cheat_err:
        print(f"[Anti-cheat Error] {cheat_err}")

    return out


def _identity_line(face_verification: Optional[str], face_id_score: Optional[float], voice_score: Optional[float]) -> str:
    voice_ok = voice_score is not None and voice_score >= 75
    voice_txt = f"Voice {voice_score:.1f}%" if voice_score is not None else "Voice not checked"
    if face_verification == "verified" and voice_ok:
        return f"✅ Identity verified: Face {face_id_score:.1f}% (server checks) + {voice_txt}"
    reason = {
        "verified": f"Face {face_id_score:.1f}% (server checks) but {voice_txt} (required 75%)" if face_id_score is not None else "",
        "uncertain": f"Face {face_id_score or 0:.1f}% (required 55%, server checks) + {voice_txt}",
        "mismatch": f"Face {face_id_score or 0:.1f}% (required 55%, server checks) + {voice_txt}",
        "no_face": "no face was found in the server's face checks",
        "unverified": "no server-side face check was recorded for this exam",
        "not_enrolled": "the student has no enrolled face print",
    }.get(face_verification or "", "unknown")
    return f"🚨 IDENTITY NOT VERIFIED: {reason}"


def _monitoring_line(integrity_status: Optional[str], facial_score: Optional[float], face_checks: Optional[int]) -> str:
    if integrity_status == "server_sampled" and facial_score is not None:
        return (f"المراقبة (فحوص وجه على السيرفر): الوجه المسجّل كان ظاهر ولوحده في {facial_score:.0f}% "
                f"من {face_checks} فحص")
    return (f"⚠️ المراقبة: بيانات متحقق منها غير كافية ({face_checks or 0} فحص وجه على السيرفر) — "
            "النزاهة غير محسوبة في الدرجة وتحتاج مراجعة")


def compute_grade(
    ai: Dict[str, Any],
    face_id_score: Optional[float],
    has_faceprint: bool,
    integrity_score: Optional[float] = None,
    face_verification: Optional[str] = None,
    integrity_status: Optional[str] = None,
    face_checks: Optional[int] = None,
) -> Dict[str, Any]:
    """
    The submission fields that come out of grading.

    Weights as before — content 80%, fluency 10%, integrity 10% — but integrity is the server's own
    evidence (`integrity_score`, from exam_evidence) and nothing else. When there is none, the
    integrity part is left out and the other two are scaled to the full mark ((0.8·content +
    0.1·fluency) / 0.9) instead of assuming a clean 100, and the report says integrity is unknown.
    The severe-integrity penalty applies only to server-measured integrity.
    """
    transcript = ai["transcript"]
    nlp_score = ai["nlp_score"]
    speech_score = ai["speech_score"]
    voice_score = ai["voice_score"]
    facial_score = integrity_score
    fluency_report = ai["fluency_report"]

    parts = []
    if face_verification is not None:
        parts.append(_monitoring_line(integrity_status, facial_score, face_checks))
    if ai.get("cheat_report"):
        parts.append(ai["cheat_report"])
    cheat_report = "\n".join(parts) or None
    if face_verification is not None:
        identity_msg = _identity_line(face_verification, face_id_score, voice_score)
        cheat_report = (cheat_report + " | " + identity_msg) if cheat_report else identity_msg

    if nlp_score is not None:
        fluency_val = speech_score if speech_score is not None else 50.0
        if facial_score is None:
            raw_overall = (nlp_score * 0.8 + fluency_val * 0.1) / 0.9
        else:
            raw_overall = (nlp_score * 0.8) + (fluency_val * 0.1) + (facial_score * 0.1)
            if facial_score < 60:
                penalty = (60 - facial_score) * 0.75
                raw_overall -= penalty

        if nlp_score < 50 or raw_overall < 50:
            overall = min(max(raw_overall, 0), 49.9)
        else:
            overall = min(round(raw_overall, 1), 100.0)
    else:
        overall = None

    return {
        "transcript": transcript,
        "nlp_score": nlp_score,
        "speech_score": speech_score,
        "voice_score": voice_score,
        "facial_score": facial_score,
        "overall_score": overall,
        "cheat_report": cheat_report,
        "fluency_report": fluency_report,
    }
