import { useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowUpLeft, Play, ScanFace, ShieldCheck } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { FaceScan } from "./FaceScan";
import { BTN, BTN_GHOST } from "./ui";

/**
 * 0. Hero Section:
 * - Stage background is calibrated to exact solid #0E0804 (matching the background-removed
 *   /media/hero-face-mesh.mp4 pixel-for-pixel) so the character looks like an integral part
 *   of the Hero box itself with zero background rectangle or shadow.
 * - Uses a SINGLE <FaceScan /> video element across Mobile, Tablet, and Desktop so mobile
 *   browsers never abort duplicate video streams and always play the animation smoothly.
 */
export function HomeHero({ startHref }: { startHref: string }) {
    const { l, lang } = useI18n();
    const root = useRef<HTMLElement>(null);
    const stageRef = useRef<HTMLDivElement>(null);

    useGSAP(() => {
        withMotion(() => {
            const tl = gsap.timeline({ defaults: { ease: "power3.out" } });
            tl.fromTo("[data-hero-line]", { y: 36, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8, stagger: 0.1 })
                .fromTo("[data-hero-fade]", { y: 20, opacity: 0 }, { y: 0, opacity: 1, duration: 0.65, stagger: 0.08 }, "-=0.45")
                .fromTo("[data-hero-video]", { scale: 0.94, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.8, ease: "power2.out" }, "-=0.55")
                .fromTo("[data-hero-card]", { y: 26, opacity: 0, scale: 0.96 }, { y: 0, opacity: 1, scale: 1, duration: 0.7, ease: "back.out(1.2)" }, "-=0.5")
                .fromTo("[data-hero-bento]", { y: 22, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, stagger: 0.08 }, "-=0.4");

            gsap.to("[data-hero-title-wrap]", {
                yPercent: -5,
                ease: "none",
                scrollTrigger: {
                    trigger: stageRef.current,
                    start: "top top",
                    end: "bottom top",
                    scrub: true,
                },
            });
        });
    }, { scope: root, dependencies: [lang] });

    const lowerPanels = [
        {
            index: "01",
            metric: "80%",
            tone: "bg-sheet border-rule text-ink",
            badge: l("التصحيح بالمعنى", "Semantic Grading"),
            title: l("يفهم شرح الطالب بأسلوبه بدون حفظ حرفي", "Grades Student Meaning Without Rote Memorization"),
        },
        {
            index: "02",
            metric: "478",
            tone: "wb-mocha-stage border-[#FAF6F0]/15 text-[#FAF6F0]",
            badge: l("منع الغش بالكاميرا والصوت", "Vision & Voice Anti-Cheat"),
            title: l("نقطة تتبُّع للوجه وحركة العين وبصمة الصوت لحظياً", "Live Facial, Eye-Gaze & Voiceprint Landmarks"),
            dark: true,
        },
        {
            index: "03",
            metric: "100%",
            tone: "bg-sheet-2 border-rule text-ink",
            badge: l("أوتوماتيك بالكامل", "Fully Automated"),
            title: l("الدفعة كلها بتمتحن شفوي أونلاين في نفس الوقت", "Entire Cohort Takes the Online Oral Quiz Together"),
        },
    ];

    return (
        <section
            ref={root}
            className="home-a relative px-2.5 pt-21 pb-6 sm:px-5 sm:pt-24 sm:pb-8 lg:px-7"
        >
            {/* Rounded Hero Stage — Unified #0E0804 Base Matching the Processed Video Background 1:1 */}
            <div
                ref={stageRef}
                style={{
                    backgroundColor: "#0E0804",
                }}
                className="relative isolate mx-auto flex min-h-[calc(100dvh-7.5rem)] max-w-[94rem] flex-col justify-between overflow-hidden rounded-[24px] sm:rounded-[28px] border border-[#FAF6F0]/12 text-[#FAF6F0] shadow-[0_30px_80px_-24px_rgba(20,14,10,0.5)]"
            >
                {/* FOREGROUND CONTENT: 3-Column Layout (Headline on Right | Open 5-Col Center for Character | 478 Card on Left) */}
                <div className="relative z-10 mx-auto grid w-full max-w-[90rem] flex-1 grid-cols-1 items-center gap-5 px-4 pt-6 pb-5 sm:px-8 sm:pt-8 sm:pb-8 lg:grid-cols-12 lg:gap-6 lg:px-12 lg:py-12">
                    {/* 1. Start Column (Right in RTL): Headline & Actions (4 cols) */}
                    <div data-hero-title-wrap className="order-1 lg:order-none lg:col-span-4 relative z-10">
                        <h1 className="ar-heading font-display text-[clamp(1.95rem,3.8vw,3.95rem)] font-bold leading-[1.16] text-[#FAF6F0]">
                            <span data-hero-line className="block">
                                {l("أول منصة عربية", "The First Arabic Platform")}
                            </span>
                            <span data-hero-line className="mt-1.5 block text-[#E3A458]">
                                {l("تقدم الامتحانات الشفوي", "For Online Oral")}
                            </span>
                            <span data-hero-line className="mt-1.5 block text-[#EFE7DE]">
                                {l("أونلاين.", "Examinations.")}
                            </span>
                        </h1>

                        <p data-hero-fade className="ar-body mt-3.5 sm:mt-5 max-w-[26rem] text-[0.95rem] font-medium leading-[1.82] text-[#FAF6F0]/82 sm:text-[1.05rem]">
                            {l(
                                "حولنا الامتحان الشفوي لكويز أونلاين ذكي زي أي كويز إلكتروني: الطالب بيجاوب بصوته، و3 موديلات ذكاء اصطناعي بتصحح الإجابة بالمعنى وبتراقب حركة العين وبصمة الوجه والصوت عشان مستحيل يغش.",
                                "Turn oral exams into an effortless online quiz: students answer by voice while 3 AI models grade meaning and track eye gaze, face mesh, and voiceprint so cheating is impossible.",
                            )}
                        </p>

                        <div data-hero-fade className="mt-5 sm:mt-8 flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2.5 sm:gap-3">
                            <Link to={startHref} viewTransition className={`${BTN} w-full sm:w-auto justify-center ps-6 pe-2.5`}>
                                <span>{l("ابدأ الآن مجاناً", "Start now for free")}</span>
                                <span className="flex size-8 items-center justify-center rounded-full bg-white/15 text-white">
                                    <ArrowUpLeft className="size-4 ltr:rotate-90" aria-hidden />
                                </span>
                            </Link>
                            <a href="#video" className={`${BTN_GHOST} w-full sm:w-auto justify-center`}>
                                <Play className="size-4 fill-current text-[#6F4E37]" aria-hidden />
                                {l("شاهد الفيديو التعريفي", "Watch intro video")}
                            </a>
                        </div>
                    </div>

                    {/* 2. Center Column (5 cols in Grid Flow so 478 Card stays on Left!): Contains the SINGLE FaceScan Video */}
                    <div className="order-2 lg:order-none lg:col-span-5 flex items-end justify-center">
                        <div
                            data-hero-video
                            className="flex w-full items-end justify-center -my-2 sm:my-0 lg:pointer-events-none lg:absolute lg:inset-y-0 lg:left-[46.5%] lg:-translate-x-1/2 lg:z-0 lg:w-[39rem] xl:w-[44rem] lg:pt-2"
                        >
                            <FaceScan
                                priority
                                className="h-[20.5rem] w-full max-w-[22rem] sm:h-[27rem] sm:max-w-[30rem] lg:h-full lg:max-w-none"
                            />
                        </div>
                    </div>

                    {/* 3. End Column (Left in RTL): Warm Off-White 478 Points Biometric Anti-Cheating Card (3 cols) */}
                    <div className="order-3 lg:order-none lg:col-span-3 relative z-10">
                        <div
                            data-hero-card
                            className="rounded-[22px] sm:rounded-[23px] border border-[#FAF6F0]/20 bg-[#FAF6F0] p-4.5 sm:p-6 text-[#1C1410] shadow-[0_24px_60px_-15px_rgba(0,0,0,0.55)]"
                        >
                            <div className="flex items-center gap-3 border-b border-[#1C1410]/12 pb-3.5 sm:pb-4">
                                <span className="flex size-11 sm:size-12 shrink-0 items-center justify-center rounded-2xl bg-[#6F4E37] text-[#FAF6F0] shadow-md">
                                    <ScanFace className="size-5 sm:size-6" aria-hidden />
                                </span>
                                <div>
                                    <span className="wb-num block text-2xl sm:text-3xl font-extrabold leading-none text-[#1C1410]">
                                        478
                                    </span>
                                    <span className="mt-1 block text-xs font-bold text-[#6F4E37]">
                                        {l("نقطة تتبُّع حيوي على الوجه والعين", "Live face & eye-gaze landmarks")}
                                    </span>
                                </div>
                            </div>

                            <p className="ar-body mt-3.5 sm:mt-4 text-xs sm:text-sm font-medium leading-[1.78] text-[#1C1410]/85">
                                {l(
                                    "الطالب مش هيعرف يغش: الكاميرا بترسم 478 نقطة على الوجه وبتتابع حركة العين لحظة بلحظة، مع مطابقة بصمة الصوت وتصحيح الإجابة بالمعنى تلقائياً.",
                                    "Cheating is impossible: the camera maps 478 facial landmarks and tracks eye movement in real time, matching voiceprints and grading answers semantically.",
                                )}
                            </p>

                            <div className="mt-3.5 sm:mt-4 flex items-center gap-2 border-t border-[#1C1410]/10 pt-3 text-xs font-bold text-[#6F4E37]">
                                <ShieldCheck className="size-4 shrink-0" aria-hidden />
                                <span>{l("مراقبة حيوية لحظية بدون تدخل بشري", "Real-time autonomous proctoring")}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Lower Hero Bento Panels — Responsive on Mobile, Tablet & Desktop */}
            <div className="mx-auto mt-3.5 sm:mt-4 grid max-w-[94rem] grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {lowerPanels.map((p, idx) => (
                    <div
                        key={p.index}
                        data-hero-bento
                        className={`flex items-center justify-between gap-4 rounded-[20px] sm:rounded-[22px] border p-4.5 sm:p-6 shadow-card ${p.tone} ${idx === 2 ? "sm:col-span-2 lg:col-span-1" : ""}`}
                    >
                        <div className="min-w-0">
                            <span className={`inline-block text-xs font-bold ${p.dark ? "text-[#E3A458]" : "text-pen"}`}>
                                {p.badge}
                            </span>
                            <p className={`ar-heading mt-1 text-[0.95rem] sm:text-lg font-bold leading-snug ${p.dark ? "text-[#FAF6F0]" : "text-ink"}`}>
                                {p.title}
                            </p>
                        </div>
                        <span className={`wb-num shrink-0 text-2xl sm:text-4xl font-extrabold ${p.dark ? "text-[#E3A458]" : "text-ink"}`}>
                            {p.metric}
                        </span>
                    </div>
                ))}
            </div>
        </section>
    );
}
