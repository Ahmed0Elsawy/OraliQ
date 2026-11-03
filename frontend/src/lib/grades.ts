/** Grade bands — match the backend NLP grader (nlp_ai.py): 85 / 65 / 45. */
export type GradeKey = "excellent" | "good" | "partial" | "weak";
export type Tone = "neutral" | "pen" | "pass" | "warn" | "mark";

export interface GradeInfo {
    key: GradeKey;
    ar: string;
    en: string;
    tone: Tone;
}

export function gradeOf(score: number | null | undefined): GradeInfo | null {
    if (score == null || Number.isNaN(score)) return null;
    if (score >= 85) return { key: "excellent", ar: "ممتاز", en: "Excellent", tone: "pass" };
    if (score >= 65) return { key: "good", ar: "جيد", en: "Good", tone: "pen" };
    if (score >= 45) return { key: "partial", ar: "مقبول", en: "Fair", tone: "warn" };
    return { key: "weak", ar: "ضعيف", en: "Weak", tone: "mark" };
}

/**
 * The same bands, worded for the student who earned them: encouraging, never alarming.
 * Lecturers keep the plain labels; a student sees where to go next.
 */
export function studentGradeOf(score: number | null | undefined): GradeInfo | null {
    const g = gradeOf(score);
    if (!g || g.key !== "weak") return g;
    return { ...g, ar: "يحتاج تقوية", en: "Needs practice", tone: "warn" };
}

/** A short, kind line for the student after an answer is graded. */
export function encouragementOf(score: number | null | undefined): { ar: string; en: string } | null {
    const g = gradeOf(score);
    if (!g) return null;
    switch (g.key) {
        case "excellent": return { ar: "شغل عالي! واضح إنك فاهم الموضوع كويس.", en: "Great work — you clearly know this well." };
        case "good": return { ar: "إجابة كويسة. شوية تفاصيل كمان وتبقى ممتازة.", en: "A good answer. A few more details and it's excellent." };
        case "partial": return { ar: "بداية كويسة. راجع النقط الأساسية وهتفرق معاك جداً.", en: "A good start. Reviewing the key points will make a big difference." };
        default: return { ar: "ولا يهمك، كل امتحان بيعلّمك حاجة. راجع الموضوع وهتعدّيها المرة الجاية.", en: "No worries — every exam teaches you something. Review the topic and you'll get it next time." };
    }
}

/** 91.5 → "91.5", 76 → "76" */
export function formatScore(score: number | null | undefined): string {
    if (score == null || Number.isNaN(score)) return "—";
    const rounded = Math.round(score * 10) / 10;
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}
