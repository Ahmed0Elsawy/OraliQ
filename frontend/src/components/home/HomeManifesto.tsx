import { useEffect, useRef } from "react";
import { Sparkles } from "lucide-react";
import { useI18n } from "../../i18n";

type WordToken = { text: string; gold?: boolean };

const AR_WORDS: WordToken[] = [
    { text: "الامتحان" },
    { text: "الشفوي" },
    { text: "مش" },
    { text: "لازم" },
    { text: "يكون" },
    { text: "طابور" },
    { text: "طويل" },
    { text: "وتوتر" },
    { text: "وساعات" },
    { text: "مهدرة." },
    { text: "مع" },
    { text: "OralIQ،", gold: true },
    { text: "كل" },
    { text: "طالب" },
    { text: "بيجاوب" },
    { text: "بصوته", gold: true },
    { text: "قدام" },
    { text: "شاشه" },
    { text: "موبايله" },
    { text: "أو" },
    { text: "اللابتوب،" },
    { text: "والذكاء" },
    { text: "الاصطناعي" },
    { text: "بيرصد" },
    { text: "478", gold: true },
    { text: "نقطة", gold: true },
    { text: "على" },
    { text: "الوجه" },
    { text: "وحركة" },
    { text: "العين" },
    { text: "لحظياً،" },
    { text: "ويفهم" },
    { text: "الإجابة" },
    { text: "بالمعنى", gold: true },
    { text: "مش", gold: true },
    { text: "بالحفظ،", gold: true },
    { text: "عشان" },
    { text: "تستلم" },
    { text: "درجة", gold: true },
    { text: "عادلة", gold: true },
    { text: "ومفصلة" },
    { text: "لدفعتك" },
    { text: "كلها" },
    { text: "في", gold: true },
    { text: "نفس", gold: true },
    { text: "الوقت.", gold: true },
];

const EN_WORDS: WordToken[] = [
    { text: "An" },
    { text: "oral" },
    { text: "exam" },
    { text: "should" },
    { text: "never" },
    { text: "mean" },
    { text: "endless" },
    { text: "queues," },
    { text: "anxiety," },
    { text: "and" },
    { text: "wasted" },
    { text: "hours." },
    { text: "With" },
    { text: "OralIQ,", gold: true },
    { text: "every" },
    { text: "student" },
    { text: "answers" },
    { text: "out", gold: true },
    { text: "loud", gold: true },
    { text: "in" },
    { text: "front" },
    { text: "of" },
    { text: "their" },
    { text: "screen" },
    { text: "while" },
    { text: "AI" },
    { text: "tracks" },
    { text: "478", gold: true },
    { text: "face", gold: true },
    { text: "landmarks", gold: true },
    { text: "and" },
    { text: "eye" },
    { text: "gaze" },
    { text: "live," },
    { text: "grading" },
    { text: "by", gold: true },
    { text: "meaning", gold: true },
    { text: "not" },
    { text: "memorization—delivering" },
    { text: "a" },
    { text: "fair,", gold: true },
    { text: "explained", gold: true },
    { text: "grade", gold: true },
    { text: "for" },
    { text: "your" },
    { text: "entire" },
    { text: "class" },
    { text: "at", gold: true },
    { text: "once.", gold: true },
];

/**
 * Sticky 300vh Word-by-Word Scroll Reveal Section:
 * Pinned in the middle of the screen inside a 300vh track. As the user scrolls through the track,
 * words transition from 14% opacity to full white one by one in reading order, while key words
 * illuminate in a warm sand-gold accent (#E5C178).
 */
export function HomeManifesto() {
    const { lang, l } = useI18n();
    const trackRef = useRef<HTMLDivElement>(null);
    const wordsRef = useRef<(HTMLSpanElement | null)[]>([]);
    const barRef = useRef<HTMLDivElement>(null);
    const words = lang === "ar" ? AR_WORDS : EN_WORDS;

    useEffect(() => {
        const track = trackRef.current;
        if (!track) return;

        let rafId = 0;
        const update = () => {
            const rect = track.getBoundingClientRect();
            const vh = window.innerHeight || 1;
            const scrollable = Math.max(1, rect.height - vh);
            const rawProgress = -rect.top / scrollable;
            const progress = Math.max(0, Math.min(1, rawProgress));

            const total = words.length;
            for (let i = 0; i < total; i++) {
                const el = wordsRef.current[i];
                if (!el) continue;
                const start = i / total;
                const end = (i + 1) / total;
                const wordProgress = Math.max(0, Math.min(1, (progress - start) / (end - start)));
                const opacity = 0.14 + wordProgress * 0.86;
                el.style.opacity = opacity.toFixed(3);
            }

            if (barRef.current) {
                barRef.current.style.transform = `scaleX(${progress.toFixed(4)})`;
            }
        };

        const onScroll = () => {
            cancelAnimationFrame(rafId);
            rafId = requestAnimationFrame(update);
        };

        update();
        window.addEventListener("scroll", onScroll, { passive: true });
        window.addEventListener("resize", onScroll, { passive: true });
        return () => {
            cancelAnimationFrame(rafId);
            window.removeEventListener("scroll", onScroll);
            window.removeEventListener("resize", onScroll);
        };
    }, [words]);

    return (
        <section
            ref={trackRef}
            aria-label={l("رؤية المنصة", "Platform Manifesto")}
            className="relative h-[280vh] bg-[#0B0B0C] text-white"
        >
            <div className="sticky top-0 flex h-dvh flex-col justify-between overflow-hidden px-4 py-20 sm:px-8">
                {/* Subtle ambient sand-gold glow in the center */}
                <div
                    className="pointer-events-none absolute left-1/2 top-1/2 -z-10 size-[34rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#D8B36A]/[0.07] blur-[120px]"
                    aria-hidden
                />

                {/* Top label */}
                <div className="mx-auto flex w-full max-w-7xl items-center justify-between text-xs font-bold uppercase tracking-widest text-white/60">
                    <span className="inline-flex items-center gap-2 text-[#E5C178]">
                        <Sparkles className="size-4" aria-hidden />
                        {l("لماذا OralIQ؟", "WHY ORALIQ?")}
                    </span>
                    <span>{l("مرّر للقراءة", "SCROLL TO READ")}</span>
                </div>

                {/* Centered Pinned Paragraph */}
                <div className="mx-auto my-auto max-w-7xl">
                    <p className="font-display text-[clamp(1.75rem,3.7vw,3.35rem)] font-extrabold leading-[1.48] tracking-tight">
                        {words.map((w, i) => (
                            <span
                                key={`${i}-${w.text}`}
                                ref={(el) => {
                                    wordsRef.current[i] = el;
                                }}
                                style={{ opacity: 0.14 }}
                                className={
                                    w.gold
                                        ? "inline-block pe-[0.28em] text-[#E5C178] transition-colors duration-150"
                                        : "inline-block pe-[0.28em] text-white transition-colors duration-150"
                                }
                            >
                                {w.text}
                            </span>
                        ))}
                    </p>
                </div>

                {/* Reading Progress Track at bottom */}
                <div className="mx-auto flex w-full max-w-7xl items-center gap-4">
                    <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/10">
                        <div
                            ref={barRef}
                            className="h-full w-full origin-start rounded-full bg-gradient-to-r from-[#D8B36A] to-[#F3D999]"
                            style={{ transform: "scaleX(0)" }}
                        />
                    </div>
                    <span className="font-mono text-xs font-bold text-[#E5C178]">ORALIQ AI</span>
                </div>
            </div>
        </section>
    );
}
