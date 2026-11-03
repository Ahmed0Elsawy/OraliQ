import { useEffect, useRef } from "react";
import { useI18n } from "../../i18n";

/**
 * Three Huge Infinite Marquee Rows with a Tilted Sand-Coloured Band in Between:
 * - Rows move in alternating directions and loop seamlessly (duplicated content wrapped at 50% width).
 * - Scrolling speeds them up based on scroll velocity, and scrolling up reverses their direction.
 * - Powered by requestAnimationFrame for 60fps physics.
 */
export function HomeMarquee() {
    const { lang } = useI18n();
    const row1Ref = useRef<HTMLDivElement>(null);
    const row2Ref = useRef<HTMLDivElement>(null);
    const row3Ref = useRef<HTMLDivElement>(null);

    const row1Items = lang === "ar"
        ? ["امتحانات شفوية بالذكاء الاصطناعي", "تتبع الوجه 478 نقطة", "تصحيح فوري بالمعنى", "بصمة صوتية حيوية", "رصد حركة العين والالتفات", "تقارير تفصيلية للمحاضر", "بدون لجان أو طوابير"]
        : ["AI ORAL EXAMINATIONS", "478-POINT FACE MESH", "SEMANTIC ANSWER GRADING", "VOICEPRINT BIOMETRICS", "LIVE EYE GAZE TRACKING", "DETAILED LECTURER REPORTS", "ZERO QUEUES OR PANELS"];

    const row2Items = lang === "ar"
        ? ["ORALIQ AI — أول منصة عربية للامتحانات الشفوية أونلاين", "امتحن دفعتك كلها في نفس الوقت", "درجة عادلة ومفصلة لكل طالب", "متاح للجامعات والمدارس والمنصات التعليمية"]
        : ["ORALIQ AI — FIRST ARABIC ONLINE ORAL EXAM PLATFORM", "EXAMINE YOUR WHOLE COHORT AT ONCE", "FAIR EXPLAINED GRADES FOR EVERY STUDENT", "BUILT FOR UNIVERSITIES, SCHOOLS & LMS PLATFORMS"];

    const row3Items = lang === "ar"
        ? ["كليات الطب والصيدلة", "كليات الهندسة والحاسبات", "كليات اللغات والترجمة", "كليات التجارة وإدارة الأعمال", "المعاهد والمراكز التدريبية", "المدارس الدولية واللغات", "المنصات التعليمية الرقمية"]
        : ["MEDICAL & HEALTH FACULTIES", "ENGINEERING & COMPUTER SCIENCE", "LANGUAGES & TRANSLATION", "BUSINESS & ECONOMICS", "TRAINING INSTITUTES", "INTERNATIONAL SCHOOLS", "DIGITAL LEARNING PLATFORMS"];

    useEffect(() => {
        let rafId = 0;
        let lastScrollY = window.scrollY;
        let velocity = 0;
        let dir = 1; // +1 when scrolling down, -1 when scrolling up

        // Normalized progress [0..1) for each row (wraps at 0.5 of duplicated track)
        let pos1 = 0;
        let pos2 = 0;
        let pos3 = 0;

        const onScroll = () => {
            const y = window.scrollY;
            const delta = y - lastScrollY;
            lastScrollY = y;
            if (Math.abs(delta) > 0.5) {
                dir = delta > 0 ? 1 : -1;
                velocity = Math.min(28, Math.abs(delta) * 0.45);
            }
        };

        const tick = () => {
            // Smoothly decay scroll velocity boost
            velocity *= 0.92;
            const baseSpeed = 0.00045;
            const boost = velocity * 0.00018;
            const step = (baseSpeed + boost) * dir;

            // Row 1 & Row 3 move in `dir`, Row 2 moves in `-dir` (alternating directions)
            pos1 = (pos1 + step) % 0.5;
            if (pos1 < 0) pos1 += 0.5;

            pos2 = (pos2 - step * 1.15) % 0.5;
            if (pos2 < 0) pos2 += 0.5;

            pos3 = (pos3 + step * 0.9) % 0.5;
            if (pos3 < 0) pos3 += 0.5;

            if (row1Ref.current) {
                row1Ref.current.style.transform = `translate3d(${(-pos1 * 100).toFixed(3)}%, 0, 0)`;
            }
            if (row2Ref.current) {
                row2Ref.current.style.transform = `translate3d(${(-pos2 * 100).toFixed(3)}%, 0, 0)`;
            }
            if (row3Ref.current) {
                row3Ref.current.style.transform = `translate3d(${(-pos3 * 100).toFixed(3)}%, 0, 0)`;
            }

            rafId = requestAnimationFrame(tick);
        };

        window.addEventListener("scroll", onScroll, { passive: true });
        rafId = requestAnimationFrame(tick);
        return () => {
            cancelAnimationFrame(rafId);
            window.removeEventListener("scroll", onScroll);
        };
    }, []);

    const renderGroup = (items: string[], dotClass: string) => (
        <div className="flex shrink-0 items-center gap-8 pe-8">
            {items.map((item, idx) => (
                <span key={idx} className="inline-flex items-center gap-8 whitespace-nowrap">
                    <span>{item}</span>
                    <span className={dotClass} aria-hidden>✦</span>
                </span>
            ))}
        </div>
    );

    return (
        <section
            dir="ltr"
            aria-hidden
            className="relative overflow-hidden bg-[#0D0D0D] py-16 text-white select-none sm:py-24 border-y border-white/10"
        >
            {/* Row 1: Huge Display Row */}
            <div className=" flex overflow-hidden py-2">
                <div
                    ref={row1Ref}
                    className="flex w-max will-change-transform font-display text-[clamp(2.25rem,5vw,4.5rem)] font-black uppercase tracking-tight text-white/90"
                >
                    {renderGroup(row1Items, "text-[#E5C178] text-2xl sm:text-4xl")}
                    {renderGroup(row1Items, "text-[#E5C178] text-2xl sm:text-4xl")}
                </div>
            </div>

            {/* Row 2: Tilted Sand-Gold Announcement Band in Between */}
            <div className="relative z-10 my-5 -mx-6 -rotate-[2.2deg] bg-[#D8B36A] py-4 text-[#0D0D0D] shadow-[0_14px_40px_rgba(0,0,0,0.55)] sm:py-5">
                <div className="flex overflow-hidden">
                    <div
                        ref={row2Ref}
                        className="flex w-max will-change-transform font-display text-[clamp(1.35rem,2.6vw,2.15rem)] font-black uppercase tracking-wide text-[#0D0D0D]"
                    >
                        {renderGroup(row2Items, "text-[#0D0D0D]/60 text-xl")}
                        {renderGroup(row2Items, "text-[#0D0D0D]/60 text-xl")}
                    </div>
                </div>
            </div>

            {/* Row 3: Huge Outlined/Secondary Row */}
            <div className="flex overflow-hidden py-2">
                <div
                    ref={row3Ref}
                    className="flex w-max will-change-transform font-display text-[clamp(2.1rem,4.6vw,4.1rem)] font-extrabold uppercase tracking-tight text-white/40"
                >
                    {renderGroup(row3Items, "text-[#D8B36A]/70 text-2xl sm:text-3xl")}
                    {renderGroup(row3Items, "text-[#D8B36A]/70 text-2xl sm:text-3xl")}
                </div>
            </div>
        </section>
    );
}
