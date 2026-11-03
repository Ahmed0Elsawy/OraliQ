import { BookOpen, CheckCircle2, Clock, Eye, Gauge, Mic, MessageSquareQuote, RotateCw, ScanFace, ShieldAlert, ShieldCheck, Smartphone, UserX, Users } from "lucide-react";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import { ScoreMark } from "./ui/score-mark";
import { Badge } from "./ui/badge";
import { gradeOf, studentGradeOf, formatScore, type Tone } from "../lib/grades";
import { formatDate, formatDuration, parseServerDate } from "../lib/format";
import type { Submission } from "../lib/types";

/** Thresholds mirror backend/app/api/endpoints/exams.py and face.py */
const FACE = { verified: 55, mismatch: 45 };
const VOICE = { verified: 75, mismatch: 60 };

type CheckState = "verified" | "uncertain" | "mismatch" | "missing";

function checkState(score: number | null, t: { verified: number; mismatch: number }): CheckState {
    if (score == null) return "missing";
    if (score >= t.verified) return "verified";
    if (score < t.mismatch) return "mismatch";
    return "uncertain";
}

const checkTone: Record<CheckState, Tone> = { verified: "pass", uncertain: "warn", mismatch: "mark", missing: "neutral" };

/** Soft coloured surfaces (work in light + dark themes). */
const SURFACE = {
    sky: "border-sky-500/30 bg-sky-500/[0.08]",
    violet: "border-violet-500/30 bg-violet-500/[0.08]",
    green: "border-emerald-500/30 bg-emerald-500/[0.09]",
    amber: "border-amber-500/40 bg-amber-500/[0.10]",
    orange: "border-orange-500/40 bg-orange-500/[0.10]",
    red: "border-rose-500/40 bg-rose-500/[0.10]",
    gray: "border-rule bg-sheet-2",
} as const;
const ICON_INK = {
    sky: "text-sky-600 dark:text-sky-400",
    violet: "text-violet-600 dark:text-violet-400",
    green: "text-emerald-600 dark:text-emerald-400",
    amber: "text-amber-600 dark:text-amber-400",
    orange: "text-orange-600 dark:text-orange-400",
    red: "text-rose-600 dark:text-rose-400",
    gray: "text-ink-3",
} as const;
type Hue = keyof typeof SURFACE;

/**
 * Backend reports are Arabic plain text: blocks joined by " | ", lines with "  • " bullets,
 * plus emoji/English identity lines we render separately as structured checks.
 */
function parseReport(text: string | null): { heading: string[]; bullets: string[] } {
    const heading: string[] = [];
    const bullets: string[] = [];
    (text || "")
        .split("\n")
        // " | " joins report blocks at top level, but inside a bullet it separates two facts on one line
        .flatMap((line) => (line.trim().startsWith("•") ? [line.replace(/\s\|\s/g, "، ")] : line.split(/\s\|\s/)))
        .map((s) => s.trim())
        .filter(Boolean)
        .filter((s) => !/identity/i.test(s))
        .forEach((line) => {
            if (line.startsWith("•")) bullets.push(line.replace(/^•\s*/, ""));
            // Strips the server's status emoji from report lines before display. avoid-ai-design-ignore: I2
            else if (!/:$/.test(line)) heading.push(line.replace(/^(?:✅|⚠️|🚨|\s)+/u, ""));
        });
    return { heading, bullets };
}

/** Classify a proctoring line (Arabic or English) into an icon + severity colour. */
function classifyAlert(text: string): { icon: typeof Eye; hue: Hue } {
    const t = text.toLowerCase();
    if (/موبايل|هاتف|تليفون|phone/.test(t)) return { icon: Smartphone, hue: "red" };
    if (/كتاب|ورق|book/.test(t)) return { icon: BookOpen, hue: "red" };
    if (/أكثر من شخص|شخص آخر|أشخاص|multiple|people/.test(t)) return { icon: Users, hue: "red" };
    if (/لا يوجد وجه|اختفى|غياب الوجه|no face|مش ظاهر/.test(t)) return { icon: UserX, hue: "orange" };
    if (/لف|رأس|الراس|الرأس|head/.test(t)) return { icon: RotateCw, hue: "orange" };
    if (/نظر|النظر|عين|gaze|look/.test(t)) return { icon: Eye, hue: "amber" };
    return { icon: ShieldAlert, hue: "amber" };
}

function Section({ title, icon: Icon, hue = "gray", children, className }: {
    title: React.ReactNode; icon?: typeof Eye; hue?: Hue; children: React.ReactNode; className?: string;
}) {
    return (
        <section className={cn("pt-5", className)}>
            <h3 className="mb-3 flex items-center gap-2 text-[0.9375rem] font-bold text-ink">
                {Icon && (
                    <span className={cn("flex size-7 items-center justify-center rounded-lg border", SURFACE[hue])}>
                        <Icon className={cn("size-4", ICON_INK[hue])} aria-hidden />
                    </span>
                )}
                {title}
            </h3>
            {children}
        </section>
    );
}

function Breakdown({ s }: { s: Submission }) {
    const { l } = useI18n();
    const rows = [
        { label: l("المحتوى", "Content"), hint: l("مقارنة بالإجابة النموذجية", "Against the model answer"), weight: 80, value: s.nlp_score, bar: "bg-sky-500" },
        { label: l("الطلاقة", "Fluency"), hint: l("التردد والتوقف والسرعة", "Hesitation, pauses, pace"), weight: 10, value: s.speech_score, bar: "bg-violet-500" },
        {
            label: l("النزاهة", "Integrity"),
            // Only server face checks count; the browser's own alerts never score.
            hint: s.integrity_status === "insufficient_data"
                ? l("غير محسوبة: فحوص الوجه على السيرفر مش كفاية — راجع يدوياً", "Not counted: too few server face checks — review manually")
                : s.integrity_status === "server_sampled"
                    ? l("فحوص الوجه على السيرفر", "Server face checks")
                    : l("المراقبة بالكاميرا", "Camera proctoring"),
            weight: 10, value: s.facial_score, bar: "bg-emerald-500",
        },
    ];
    return (
        <dl className="grid gap-3 sm:grid-cols-3">
            {rows.map((r) => {
                const low = r.value != null && r.value < 50;
                return (
                    <div key={r.weight + r.label} className={cn("rounded-xl border p-3.5", low ? SURFACE.red : SURFACE.gray)}>
                        <dt className="flex items-baseline justify-between gap-2">
                            <span className="font-bold text-ink">{r.label}</span>
                            <span className="text-[0.6875rem] text-ink-3">{l(`${r.weight}% من الدرجة`, `${r.weight}% of grade`)}</span>
                        </dt>
                        <dd className="mt-1 font-display text-2xl font-bold tabular ltr text-ink">
                            {formatScore(r.value)}{r.value != null && <span className="text-sm text-ink-3">%</span>}
                        </dd>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-rule" aria-hidden>
                            <div
                                className={cn("h-full rounded-full", low ? "bg-rose-500" : r.bar)}
                                style={{ width: `${Math.max(0, Math.min(100, r.value ?? 0))}%` }}
                            />
                        </div>
                        <p className="mt-1.5 text-xs text-ink-3">{r.hint}</p>
                    </div>
                );
            })}
        </dl>
    );
}

export function AnswerSheet({ s, viewer }: { s: Submission; viewer: "lecturer" | "student" }) {
    const { l, lang } = useI18n();
    const g = viewer === "student" ? studentGradeOf(s.overall_score) : gradeOf(s.overall_score);
    const fluency = parseReport(s.fluency_report);
    const integrity = parseReport(s.cheat_report);
    const start = parseServerDate(s.started_at);
    const end = parseServerDate(s.finished_at || s.submitted_at);
    const duration = start && end && end > start ? formatDuration((end.getTime() - start.getTime()) / 1000) : null;

    const face = checkState(s.face_score, FACE);
    const voice = checkState(s.voice_score, VOICE);
    const checkLabel = (st: CheckState) => ({
        verified: l("مطابق", "Match"),
        uncertain: l("غير مؤكد", "Uncertain"),
        mismatch: l("غير مطابق", "No match"),
        missing: l("لا توجد قراءة", "No reading"),
    })[st];
    const checkHue: Record<CheckState, Hue> = { verified: "green", uncertain: "amber", mismatch: "red", missing: "gray" };

    const integrityScore = s.facial_score;
    const integrityHue: Hue = integrity.bullets.length === 0
        ? "green"
        : integrityScore != null && integrityScore < 60 ? "red" : "amber";

    return (
        <article className="space-y-2">
            {/* Head: question + the mark */}
            <header className="flex flex-col-reverse gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                    <p className="text-sm text-ink-3">{s.question_category || l("السؤال", "Question")}</p>
                    <h2 className="mt-1 text-xl font-semibold leading-snug">{s.question_text || l("سؤال محذوف", "Deleted question")}</h2>
                    <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
                        <span>{formatDate(s.submitted_at, lang, true)}</span>
                        {duration && <span className="inline-flex items-center gap-1"><Clock className="size-3.5" aria-hidden />{l(`مدة الإجابة ${duration}`, `Answered in ${duration}`)}</span>}
                    </p>
                </div>
                <div className="flex shrink-0 flex-col items-center gap-1">
                    <ScoreMark score={s.overall_score} size="xl" animate ink={viewer === "student" ? "kind" : "mark"} />
                    {g ? <Badge tone={g.tone}>{l(g.ar, g.en)}</Badge> : <Badge>{l("قيد التصحيح", "Being graded")}</Badge>}
                </div>
            </header>

            {/* Student answer — the most important part for the lecturer */}
            <Section title={l("إجابة الطالب كما سُمعت", "The answer as heard")} icon={MessageSquareQuote} hue="sky">
                {s.transcript ? (
                    <blockquote className={cn("rounded-xl border px-4 py-3.5 text-[1.0625rem] leading-loose text-ink", SURFACE.sky)} dir="auto">
                        {s.transcript}
                    </blockquote>
                ) : (
                    <p className={cn("rounded-xl border px-4 py-3 text-ink-2", SURFACE.gray)}>{l("لم يُلتقط كلام في التسجيل.", "No speech was picked up in the recording.")}</p>
                )}
            </Section>

            {/* Proctoring — highlighted for the lecturer */}
            {viewer === "lecturer" && (
                <Section title={l("المراقبة أثناء الإجابة", "Proctoring")} icon={integrity.bullets.length ? ShieldAlert : ShieldCheck} hue={integrityHue}>
                    <div className={cn("rounded-xl border p-3.5", SURFACE[integrityHue])}>
                        {integrity.heading.length === 0 && integrity.bullets.length === 0 ? (
                            <p className="flex items-center gap-2 font-semibold text-ink">
                                <CheckCircle2 className={cn("size-5", ICON_INK.green)} aria-hidden />
                                {l("لم يُرصد أي سلوك غير عادي.", "Nothing unusual was detected.")}
                            </p>
                        ) : (
                            <>
                                {integrity.heading.map((h) => <p key={h} className="font-bold text-ink">{h}</p>)}
                                {integrity.bullets.length > 0 && (
                                    <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                                        {integrity.bullets.map((b) => {
                                            const { icon: Icon, hue } = classifyAlert(b);
                                            return (
                                                <li key={b} className={cn("flex items-start gap-2.5 rounded-lg border bg-sheet/80 px-3 py-2.5 text-sm font-semibold text-ink", SURFACE[hue])}>
                                                    <Icon className={cn("mt-0.5 size-4 shrink-0", ICON_INK[hue])} aria-hidden />
                                                    <span>{b}</span>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                )}
                            </>
                        )}
                    </div>
                    <p className="mt-2 text-xs text-ink-3">
                        {l("النظر بعيداً لوحده مش دليل غش — هو مؤشر للمراجعة بس.", "Looking away alone isn't proof of cheating — it's a cue to review.")}
                    </p>
                </Section>
            )}

            {viewer === "lecturer" && (
                <Section title={l("التحقق من الهوية", "Identity checks")} icon={ScanFace} hue={face === "mismatch" || voice === "mismatch" ? "red" : face === "verified" && voice === "verified" ? "green" : "amber"}>
                    <ul className="grid gap-2 sm:grid-cols-2">
                        {[
                            { icon: ScanFace, name: l("بصمة الوجه", "Face"), st: face, score: s.face_score, need: FACE.verified },
                            { icon: Mic, name: l("بصمة الصوت", "Voice"), st: voice, score: s.voice_score, need: VOICE.verified },
                        ].map(({ icon: Icon, name, st, score, need }) => (
                            <li key={name} className={cn("flex items-center gap-3 rounded-xl border px-3.5 py-3", SURFACE[checkHue[st]])}>
                                <Icon className={cn("size-5", ICON_INK[checkHue[st]])} aria-hidden />
                                <div className="flex-1">
                                    <p className="font-bold text-ink">{name}</p>
                                    <p className="text-xs text-ink-3">{l(`مطابق من ${need}%`, `Match from ${need}%`)}</p>
                                </div>
                                {score != null && <span className="font-display font-bold tabular ltr text-ink">{formatScore(score)}%</span>}
                                <Badge tone={checkTone[st]}>{checkLabel(st)}</Badge>
                            </li>
                        ))}
                    </ul>
                    {(face === "uncertain" || voice === "uncertain") && (
                        <p className="mt-2 text-sm text-ink-2">
                            {l("القراءة في المنطقة الرمادية. راجع التسجيل أو اطلب من الطالب إعادة الامتحان قبل نشر الدرجة.",
                                "The reading is borderline. Check the recording or ask the student to retake before publishing.")}
                        </p>
                    )}
                </Section>
            )}

            {s.overall_score != null && (
                <Section title={l("تفاصيل الدرجة", "How the grade was made")} icon={Gauge} hue="violet">
                    <Breakdown s={s} />
                    {s.nlp_score != null && s.nlp_score < 50 && (
                        <p className={cn("mt-3 rounded-lg border px-3 py-2 text-sm text-ink", SURFACE.red)}>
                            {l("المحتوى أقل من 50%، فالدرجة النهائية لا تتعدى 49.9% مهما كانت باقي العناصر.",
                                "Content is under 50%, so the final grade is capped at 49.9% regardless of the rest.")}
                        </p>
                    )}
                </Section>
            )}

            {(fluency.heading.length > 0 || fluency.bullets.length > 0) && (
                <Section title={l("الطلاقة", "Fluency")} icon={Mic} hue="violet">
                    <div className={cn("rounded-xl border p-3.5", SURFACE.violet)}>
                        {fluency.heading.map((h) => <p key={h} className="font-semibold text-ink">{h}</p>)}
                        {fluency.bullets.length > 0 && (
                            <ul className="mt-2 list-disc space-y-1 ps-5 text-ink-2 marker:text-violet-500">
                                {fluency.bullets.map((b) => <li key={b}>{b}</li>)}
                            </ul>
                        )}
                    </div>
                </Section>
            )}
        </article>
    );
}
