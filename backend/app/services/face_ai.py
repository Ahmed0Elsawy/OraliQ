from typing import Dict, List


class FaceAnalyzer:
    """
    Processes anti-cheat alert summaries collected by the frontend.
    The browser-side JS tracks gaze/head/object alerts in real-time,
    then sends the counts here for scoring.
    """

    ALERT_WEIGHTS = {
        # Gaze is supporting evidence, not proof of cheating.
        "gaze_left": 1.0,
        "gaze_right": 1.0,
        "gaze_down": 1.0,
        "gaze_up": 1.0,
        "head_turn_left": 6.0,
        "head_turn_right": 6.0,
        "no_face": 2.0,
        "multiple_people": 25.0,
        "phone_detected": 30.0,
        "book_detected": 25.0,
        "face_mismatch": 10.0,
    }

    # Total weighted penalty above this → "cheating suspected"
    CHEAT_THRESHOLD = 25

    def describe_client_alerts(self, alerts: Dict[str, float]) -> str:
        """
        The browser's alerts as report text for a lecturer, explicitly marked as unverified
        indicators. No score, no verdict: the student's own browser produced them (and can send
        anything, or nothing), and gaze or a missing face for a moment are not proof of cheating.
        """
        details = [self._format_alert(k, float(v)) for k, v in (alerts or {}).items()
                   if k in self.ALERT_WEIGHTS and isinstance(v, (int, float)) and float(v) >= 0.5]
        if not details:
            return "مؤشرات من متصفح الطالب (غير متحقق منها): لم يُبلَّغ عن شيء — وده مش دليل على عدم وجود مخالفات"
        return "مؤشرات من متصفح الطالب (غير متحقق منها، للمراجعة فقط):\n" + "\n".join(f"  • {d}" for d in details)

    def calculate_cheat_score(self, alerts: Dict[str, float]) -> dict:
        """
        Deprecated: scored browser-reported alerts, which the student controls. No longer used for
        grading (see services/exam_evidence.py). No alerts means "no data", not a clean 100.
        """
        if not alerts:
            return {
                "facial_score": None,
                "is_suspicious": False,
                "report": "لا توجد بيانات مراقبة",
            }
        
        # Calculate weighted penalty
        total_penalty = 0
        details = []

        for alert_type, duration in alerts.items():
            if duration >= 0.5 and alert_type in self.ALERT_WEIGHTS: # ignore accidental glitches < 0.5s
                weight = self.ALERT_WEIGHTS[alert_type]
                penalty = duration * weight
                total_penalty += penalty
                details.append(self._format_alert(alert_type, duration))

        # Convert penalty to 0-100 score (100 = clean)
        facial_score = max(0.0, 100.0 - total_penalty)
        is_suspicious = total_penalty >= self.CHEAT_THRESHOLD

        # Build report
        if is_suspicious:
            report = f"مشتبه في الغش (درجة النزاهة: {facial_score:.1f}%)\n"
            report += "المخالفات المرصودة:\n"
            report += "\n".join(f"  • {d}" for d in details)
        elif details:
            report = f"سلوك مقبول (درجة النزاهة: {facial_score:.1f}%)\n"
            report += "ملاحظات بسيطة:\n"
            report += "\n".join(f"  • {d}" for d in details)
        else:
            report = "لم يتم رصد أي مخالفات جسيمة"

        return {
            "facial_score": round(facial_score, 1),
            "is_suspicious": is_suspicious,
            "report": report,
        }

    def _format_alert(self, alert_type: str, duration: float) -> str:
        d_str = f"{duration:.1f} ثانية"
        labels = {
            "gaze_left": f"نظر لليسار لمدة {d_str}",
            "gaze_right": f"نظر لليمين لمدة {d_str}",
            "gaze_down": f"نظر للأسفل لمدة {d_str}",
            "gaze_up": f"نظر للأعلى لمدة {d_str}",
            "head_turn_left": f"لفّ الرأس لليسار لمدة {d_str}",
            "head_turn_right": f"لفّ الرأس لليمين لمدة {d_str}",
            "no_face": f"اختفى الوجه من الكاميرا {d_str}",
            "multiple_people": f"تم رصد أشخاص آخرين لـ {d_str}",
            "phone_detected": f"تم رصد هاتف لـ {d_str}",
            "book_detected": f"تم رصد كتاب/ورقة لـ {d_str}",
            "face_mismatch": f"⚠️ Face ID لا يطابق — شخص مختلف لـ {d_str}",
        }
        return labels.get(alert_type, f"{alert_type}: {d_str}")


# Singleton
face_analyzer = FaceAnalyzer()
