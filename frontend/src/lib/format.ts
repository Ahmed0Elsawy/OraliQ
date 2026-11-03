import type { Language } from "../i18n";
import type { Tone } from "./grades";

/** Latin digits in both languages so scores, IDs and dates read the same everywhere. */
const locale = (lang: Language) => (lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB");

/** The API returns naive UTC timestamps (no "Z"); treat them as UTC. */
export function parseServerDate(value?: string | null): Date | null {
    if (!value) return null;
    const hasZone = /[zZ]|[+-]\d\d:?\d\d$/.test(value);
    const d = new Date(hasZone ? value : `${value}Z`);
    return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDate(value: string | null | undefined, lang: Language, withTime = false): string {
    const d = parseServerDate(value);
    if (!d) return "—";
    return new Intl.DateTimeFormat(locale(lang), {
        day: "numeric", month: "short", year: "numeric",
        ...(withTime ? { hour: "numeric", minute: "2-digit" } : {}),
    }).format(d);
}

export function timeAgo(value: string | null | undefined, lang: Language): string {
    const d = parseServerDate(value);
    if (!d) return "—";
    const sec = Math.round((d.getTime() - Date.now()) / 1000);
    const rtf = new Intl.RelativeTimeFormat(locale(lang), { numeric: "auto" });
    const abs = Math.abs(sec);
    if (abs < 60) return rtf.format(sec, "second");
    if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
    if (abs < 86400 * 7) return rtf.format(Math.round(sec / 86400), "day");
    return formatDate(value, lang);
}

/** "1:05" from seconds */
export function formatDuration(totalSec: number): string {
    const s = Math.max(0, Math.round(totalSec));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Counted noun with correct grammar.
 * Arabic: 1 → "سؤال واحد", 2 → "سؤالين", 3–10 → "3 أسئلة", 11+ → "11 سؤال".
 * English: "1 question" / "2 questions".
 */
export function countOf(
    lang: Language,
    n: number,
    noun: { ar: { one: string; two: string; few: string; many: string }; en: { one: string; other: string } },
): string {
    if (lang === "en") return `${n} ${n === 1 ? noun.en.one : noun.en.other}`;
    if (n === 1) return noun.ar.one;
    if (n === 2) return noun.ar.two;
    if (n >= 3 && n <= 10) return `${n} ${noun.ar.few}`;
    return `${n} ${noun.ar.many}`;
}

export const NOUNS = {
    question: { ar: { one: "سؤال واحد", two: "سؤالين", few: "أسئلة", many: "سؤال" }, en: { one: "question", other: "questions" } },
    exam: { ar: { one: "امتحان واحد", two: "امتحانين", few: "امتحانات", many: "امتحان" }, en: { one: "exam", other: "exams" } },
    answer: { ar: { one: "إجابة واحدة", two: "إجابتين", few: "إجابات", many: "إجابة" }, en: { one: "answer", other: "answers" } },
    grade: { ar: { one: "درجة واحدة", two: "درجتين", few: "درجات", many: "درجة" }, en: { one: "grade", other: "grades" } },
    minute: { ar: { one: "دقيقة واحدة", two: "دقيقتين", few: "دقائق", many: "دقيقة" }, en: { one: "min", other: "min" } },
};

export function difficultyInfo(value: string | null | undefined, lang: Language): { label: string; tone: Tone } {
    const map: Record<string, { ar: string; en: string; tone: Tone }> = {
        easy: { ar: "سهل", en: "Easy", tone: "pass" },
        medium: { ar: "متوسط", en: "Medium", tone: "warn" },
        hard: { ar: "صعب", en: "Hard", tone: "mark" },
    };
    const m = map[(value || "").toLowerCase()];
    if (!m) return { label: value || "—", tone: "neutral" };
    return { label: lang === "ar" ? m.ar : m.en, tone: m.tone };
}
