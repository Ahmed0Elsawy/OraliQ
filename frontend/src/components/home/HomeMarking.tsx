import { useRef, useState } from "react";
import { CheckCircle2, Eye, Mic, Sparkles } from "lucide-react";
import { useI18n } from "../../i18n";
import { cn } from "../../lib/utils";
import { Eyebrow, H2, Section } from "./ui";

function ResultsShot({ l, theme }: { l: (ar: string, en: string) => string; theme: "light" | "dark" }) {
    const base = theme === "light" ? "/screens/results" : "/screens/results-dark";
    return (
        <picture>
            <source media="(max-width: 639px)" srcSet={`${base}-drawer.webp`} width={894} height={1200} />
            <img
                src={`${base}-1280.webp`}
                srcSet={`${base}-720.webp 720w, ${base}-1280.webp 1280w, ${base}.webp 1920w`}
                sizes="(min-width: 1024px) 42vw, 100vw"
                width={1280}
                height={800}
                loading="lazy"
                decoding="async"
                alt={l(
                    "صفحة نتائج المحاضر: درجة الطالب وتفاصيلها في المحتوى والطلاقة والنزاهة، ونص إجابته",
                    "The lecturer's results page: the student's grade, its breakdown into content, fluency and integrity, and the answer's transcript",
                )}
                className="block h-auto w-full"
            />
        </picture>
    );
}

/**
 * 3. How a grade is made: the real weights (80 content, 10 fluency, 10 integrity) as bold interactive
 * tabs beside the lecturer's results screen.
 */
export function HomeMarking() {
    const { l } = useI18n();
    const [active, setActive] = useState(0);
    const tabs = useRef<(HTMLButtonElement | null)[]>([]);
    const weights = [
        {
            pct: 80,
            icon: Sparkles,
            title: l("المحتوى والفهم العلمي", "Semantic Content"),
            body: l(
                "بنحوّل كلام الطالب لنص ونقارنه بإجابتك النموذجية بالمعنى مش بالحفظ الحرفي. الطالب اللي فاهم وقال الفكرة بأسلوبه بياخد درجته كاملة، واللي محتواه أقل من 50% لا يجتاز السؤال مهما كانت طلاقته.",
                "We transcribe the spoken answer and compare it with your model answer by meaning, not verbatim wording. A student who understood and explained it in their own words gets full credit; under 50% content cannot pass regardless of fluency.",
            ),
        },
        {
            pct: 10,
            icon: Mic,
            title: l("الطلاقة والأداء الصوتي", "Vocal Fluency"),
            body: l(
                "يقيس سرعة الكلام والوقفات الطويلة وكلمات التردد زي «يعني» و«آه». ليها وزن مساعد (10%) عشان تقيّم ثقة الطالب في العرض الشفوي، وعمرها ما تضيّع إجابة علمية صحيحة.",
                "Measures speaking pace, hesitations, and filler words. It carries a supportive 10% weight to assess oral delivery confidence and never penalizes a scientifically accurate answer.",
            ),
        },
        {
            pct: 10,
            icon: Eye,
            title: l("النزاهة ومتابعة الكاميرا", "Exam Integrity"),
            body: l(
                "الكاميرا بتتابع 478 نقطة على الوجه وحركة العين، وبتلاحظ لو الطالب التفت بعيد عن الشاشة كتير أو ظهر قدامه موبايل أو كتاب، وبتسجل للمحاضر تقرير نزاهة واضح يراجعه.",
                "The camera tracks 478 facial landmarks and eye gaze, flagging repeated looks away from the screen or unauthorized objects like a phone or book for the lecturer to review.",
            ),
        },
    ];
    const w = weights[active];

    const onKey = (e: React.KeyboardEvent, i: number) => {
        const rtl = document.documentElement.dir === "rtl";
        const forward = e.key === "ArrowDown" || e.key === (rtl ? "ArrowLeft" : "ArrowRight");
        const back = e.key === "ArrowUp" || e.key === (rtl ? "ArrowRight" : "ArrowLeft");
        if (!forward && !back) return;
        e.preventDefault();
        const next = (i + (forward ? 1 : -1) + weights.length) % weights.length;
        setActive(next);
        tabs.current[next]?.focus();
    };

    return (
        <Section id="marking" tone="a">
            <div className="mx-auto max-w-[92rem] px-6 py-24 sm:px-10 lg:px-16 lg:py-32">
                <Eyebrow>{l("طريقة التصحيح", "How grading works")}</Eyebrow>
                <h2 className={cn(H2, "mt-4 max-w-3xl")}>
                    {l("درجة عادلة لكل طالب، بنفس المقياس كل مرة.", "A Fair Grade for Every Student, on the Same Scale Every Time.")}
                </h2>
                <p className="mt-5 max-w-2xl text-lg font-semibold leading-[1.85] text-home-muted sm:text-xl">
                    {l(
                        "أول طالب وآخر طالب في الدفعة بيتصححوا بنفس الدقة والعدالة، من غير إرهاق آخر اليوم.",
                        "The first student and the last are evaluated with the exact same precision, free from end-of-day grading fatigue.",
                    )}
                </p>

                <div className="mt-14 grid gap-10 lg:grid-cols-[15rem_minmax(0,1.35fr)_minmax(0,1fr)] lg:items-center">
                    {/* Interactive Weight Tabs */}
                    <div role="tablist" aria-label={l("أوزان الدرجة", "Grade weights")} className="flex gap-3 overflow-x-auto lg:flex-col">
                        {weights.map((t, i) => {
                            const selected = i === active;
                            return (
                                <button
                                    key={t.title}
                                    ref={(el) => {
                                        tabs.current[i] = el;
                                    }}
                                    type="button"
                                    role="tab"
                                    id={`mark-tab-${i}`}
                                    aria-selected={selected}
                                    aria-controls="mark-panel"
                                    tabIndex={selected ? 0 : -1}
                                    onClick={() => setActive(i)}
                                    onKeyDown={(e) => onKey(e, i)}
                                    className={cn(
                                        "flex min-h-14 shrink-0 items-center justify-between gap-4 rounded-2xl border px-5 py-3.5 text-start font-bold transition-all",
                                        selected
                                            ? "border-home-ink bg-home-ink text-home-bg shadow-md"
                                            : "border-home-line bg-home-card/60 text-home-ink hover:bg-home-card",
                                    )}
                                >
                                    <span className="flex items-center gap-2.5 text-base">
                                        <t.icon className="size-4 shrink-0" aria-hidden />
                                        <span>{t.title}</span>
                                    </span>
                                    <span className="ltr rounded-lg bg-current/15 px-2.5 py-0.5 text-sm font-black tabular">
                                        {t.pct}%
                                    </span>
                                </button>
                            );
                        })}
                    </div>

                    {/* Lecturer Results Screen */}
                    <figure className="overflow-hidden rounded-3xl border-2 border-home-line bg-home-card shadow-xl">
                        <div className="home-light-only">
                            <ResultsShot l={l} theme="light" />
                        </div>
                        <div className="home-dark-only">
                            <ResultsShot l={l} theme="dark" />
                        </div>
                    </figure>

                    {/* Active Criterion Details */}
                    <div
                        role="tabpanel"
                        id="mark-panel"
                        aria-labelledby={`mark-tab-${active}`}
                        className="rounded-3xl border border-home-line bg-home-card p-7 shadow-sm sm:p-8"
                    >
                        <div className="flex items-baseline justify-between">
                            <p className="font-display text-[clamp(3.25rem,5.5vw,4.5rem)] font-black leading-none text-home-ink">
                                <span className="ltr tabular">{w.pct}</span>
                                <span className="text-[0.5em] text-home-muted">%</span>
                            </p>
                            <span className="rounded-full border border-home-line px-3 py-1 text-xs font-extrabold uppercase tracking-wider text-home-muted">
                                {l("وزن المعيار", "Weight")}
                            </span>
                        </div>

                        <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-home-line">
                            <div
                                className="h-full rounded-full bg-home-ink transition-all duration-500"
                                style={{ width: `${w.pct}%` }}
                            />
                        </div>

                        <h3 className="mt-6 font-display text-2xl font-extrabold text-home-ink">{w.title}</h3>
                        <p className="mt-3 text-base font-medium leading-[1.85] text-home-muted">{w.body}</p>

                        <div className="mt-7 rounded-2xl border border-home-line bg-home-bg/60 p-4 text-sm font-semibold leading-relaxed text-home-ink">
                            <p className="flex items-center gap-2 font-extrabold">
                                <CheckCircle2 className="size-4 shrink-0" aria-hidden />
                                <span>{l("شرط التحقق المزدوج من الهوية:", "Dual Biometric Identity Rule:")}</span>
                            </p>
                            <p className="mt-1.5 text-home-muted">
                                {l(
                                    "تطابق الوجه 55% على الأقل وتطابق الصوت 75% على الأقل معاً. وفي حال عدم تطابق أحدهما، تصل الإجابة للمحاضر بتنبيه واضح ليتخذ القرار.",
                                    "Face match ≥ 55% and voiceprint match ≥ 75% simultaneously. If either falls short, the submission is flagged for lecturer review.",
                                )}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </Section>
    );
}
