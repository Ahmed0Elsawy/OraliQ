import re
import threading
import time
import traceback


class NLPAnalyzer:
    """SBERT-based semantic similarity grading (fully lazy-loaded with retry)."""

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    # Whisper often confuses these Arabic letters in oral answers
    _PHONETIC = str.maketrans({
        "ذ": "ز", "ظ": "ض", "ث": "ت", "ص": "س",
        "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي",
        "إ": "ا", "أ": "ا", "آ": "ا",
    })

    _STOPS = {
        "الذي", "التي", "على", "كان", "في", "من", "هو", "هي", "عن", "مع",
        "او", "قد", "ان", "ما", "لا", "ان", "إن", "أن", "this", "that", "the",
    }

    def __init__(self):
        self._model = None
        self._load_failed = False
        self._lock = threading.Lock()

    @property
    def model(self):
        # Answers are graded in parallel worker threads; without the lock two of them could each
        # load their own copy of SBERT on the first request after startup.
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._load_model()
        return self._model

    def _load_model(self):
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                print(f"[NLP-AI] Loading SBERT model (attempt {attempt}/{self.MAX_RETRIES})...")
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
                self._load_failed = False
                print("[NLP-AI] SBERT loaded successfully.")
                break
            except Exception as e:
                print(f"[NLP-AI] Load failed (attempt {attempt}): {e}")
                traceback.print_exc()
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                else:
                    self._load_failed = True
                    raise RuntimeError(f"Failed to load SBERT after {self.MAX_RETRIES} attempts") from e

    def is_ready(self) -> bool:
        return self._model is not None

    def _normalize_word(self, word: str) -> str:
        word = word.translate(self._PHONETIC)
        for _ in range(2):
            if word.startswith("ال") and len(word) > 4:
                word = word[2:]
            elif word.startswith("لل") and len(word) > 4:
                word = word[2:]
            elif word and word[0] in "بفكولو" and len(word) > 3:
                word = word[1:]
        return word

    def _normalize_text(self, text: str) -> str:
        words = re.findall(r"[\u0621-\u064AA-Za-z]+", text or "")
        cleaned = []
        for w in words:
            nw = self._normalize_word(w.lower() if w.isascii() else w)
            if len(nw) > 2 and nw not in self._STOPS:
                cleaned.append(nw)
        return " ".join(cleaned)

    def _levenshtein(self, a: str, b: str) -> int:
        if len(a) < len(b):
            return self._levenshtein(b, a)
        if not b:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            curr = [i]
            for j, cb in enumerate(b, 1):
                curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = curr
        return prev[-1]

    def _keyword_matches(self, student_word: str, target: str) -> bool:
        if not student_word or not target:
            return False
        if student_word == target:
            return True
        if target in student_word or student_word in target:
            return True
        max_edits = 2 if len(target) >= 5 else 1
        if len(target) >= 3 and self._levenshtein(student_word, target) <= max_edits:
            return True
        return False

    def _keyword_score(self, student_answer: str, model_answer: str, extra_keywords: str = "") -> float:
        target_keywords = set(self._normalize_text(model_answer).split())
        if extra_keywords:
            for kw in re.split(r"[,،;]+", extra_keywords):
                for part in kw.strip().split():
                    nw = self._normalize_word(part)
                    if len(nw) > 2:
                        target_keywords.add(nw)

        if not target_keywords:
            return 100.0

        student_words = self._normalize_text(student_answer).split()
        if not student_words:
            return 0.0

        matched = sum(
            1 for kw in target_keywords
            if any(self._keyword_matches(sw, kw) for sw in student_words)
        )
        return (matched / len(target_keywords)) * 100

    def _semantic_score(self, student_answer: str, model_answer: str) -> float:
        from sentence_transformers import util

        pairs = [
            (student_answer, model_answer),
            (self._normalize_text(student_answer), self._normalize_text(model_answer)),
        ]
        # Deduplicate identical normalized pairs
        seen = set()
        unique_pairs = []
        for a, b in pairs:
            key = (a, b)
            if key not in seen and a and b:
                seen.add(key)
                unique_pairs.append(key)

        if not unique_pairs:
            return 0.0

        texts = [t for pair in unique_pairs for t in pair]
        embeddings = self.model.encode(texts, convert_to_tensor=True)
        best = 0.0
        idx = 0
        for a, b in unique_pairs:
            sim = util.cos_sim(embeddings[idx], embeddings[idx + 1]).item()
            best = max(best, sim)
            idx += 2
        return max(0.0, best) * 100

    def evaluate_answer(
        self,
        student_answer: str,
        model_answer: str,
        extra_keywords: str = "",
    ) -> dict:
        """
        Grade oral answers with tolerance for Whisper transcription noise.
        Meaning matters more than exact spelling — common Arabic STT errors are normalized.
        """
        if not student_answer or not student_answer.strip():
            return {"score": 0.0, "grade": "weak", "label": "لم يتم الكشف عن كلام"}

        if not model_answer or not model_answer.strip():
            return {"score": 75.0, "grade": "good", "label": "تم تسجيل الإجابة"}

        semantic_score = self._semantic_score(student_answer, model_answer)
        keyword_score = self._keyword_score(student_answer, model_answer, extra_keywords)

        # Oral-friendly weighting: meaning + key concepts
        score = (semantic_score * 0.70) + (keyword_score * 0.30)

        # Strong keyword match → don't punish Whisper typos (e.g. بزكاء vs ذكاء)
        # Requires BOTH decent meaning AND keywords — never inflate a wrong answer.
        if keyword_score >= 100 and semantic_score >= 55:
            score = max(score, 85.0 if semantic_score >= 70 else 78.0)
        elif keyword_score >= 66 and semantic_score >= 55:
            score = max(score, 75.0 if semantic_score >= 65 else 62.0)
        elif keyword_score >= 50 and semantic_score >= 60:
            score = max(score, 65.0)

        # High semantic similarity → boost only when keywords aren't a miss
        if semantic_score >= 85 and keyword_score >= 40:
            score = max(score, 88.0)
        elif semantic_score >= 78 and keyword_score >= 35:
            score = max(score, 78.0)
        elif semantic_score >= 70 and keyword_score >= 50:
            score = max(score, 70.0)

        # Hard caps: shared filler ("هو دكتور…") must NOT score like a correct answer
        if keyword_score < 20 and semantic_score < 55:
            score = min(score, 28.0)
        elif keyword_score < 35 and semantic_score < 60:
            score = min(score, 42.0)
        elif keyword_score < 45 and semantic_score < 65:
            score = min(score, 55.0)
        elif semantic_score < 50:
            score = min(score, 48.0)

        score = round(min(100.0, max(0.0, score)), 1)

        if score >= 85:
            grade, label = "excellent", "ممتاز — إجابة نموذجية دقيقة"
        elif score >= 65:
            grade, label = "good", "جيد — يغطي المعنى العام والنقاط المطلوبة"
        elif score >= 45:
            grade, label = "partial", "جزئي — بعض المحتوى صحيح ولكن ينقصه دقة"
        else:
            grade, label = "weak", "ضعيفة — الإجابة بعيدة عن المطلوب أو تفتقد الكلمات الأساسية"

        return {
            "score": score,
            "grade": grade,
            "label": label,
            "semantic_score": round(semantic_score, 1),
            "keyword_score": round(keyword_score, 1),
        }


nlp_analyzer = NLPAnalyzer()

