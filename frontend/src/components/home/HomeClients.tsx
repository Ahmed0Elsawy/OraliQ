import { useRef } from "react";
import { Building2, GraduationCap, School, ShieldCheck } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { Eyebrow, H2, Section } from "./ui";

/**
 * Section 4 (#clients): Our Clients & Impact Stats
 * Features the Two-Row Opposing Marquee ("موثوق من قبل / أبرز العملاء")
 * (Row 1 moving left, Row 2 moving right, frameless on the Warm Espresso stage with left/right fade masks)
 * and responsive 3 sector cards + 4 stat rings.
 */
export function HomeClients() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-client-card]",
                { y: 40, opacity: 0, scale: 0.95 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.75,
                    stagger: 0.12,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-clients-grid]", start: "top 82%" },
                },
            );

            const statCards = gsap.utils.toArray<HTMLElement>("[data-stat-card]");
            statCards.forEach((card, i) => {
                gsap.fromTo(
                    card,
                    { y: 32, opacity: 0 },
                    {
                        y: 0,
                        opacity: 1,
                        duration: 0.65,
                        delay: i * 0.1,
                        ease: "power3.out",
                        scrollTrigger: { trigger: "[data-stats-grid]", start: "top 84%" },
                    },
                );

                const numEl = card.querySelector<HTMLElement>("[data-stat-num]");
                if (numEl) {
                    const target = Number(numEl.dataset.target || "0");
                    const suffix = numEl.dataset.suffix || "";
                    const counter = { val: 0 };
                    gsap.to(counter, {
                        val: target,
                        duration: 1.8,
                        delay: i * 0.12,
                        ease: "power2.out",
                        scrollTrigger: { trigger: "[data-stats-grid]", start: "top 84%" },
                        onUpdate: () => {
                            numEl.textContent = `${Math.round(counter.val)}${suffix}`;
                        },
                    });
                }

                const ringEl = card.querySelector<SVGCircleElement>("[data-stat-ring]");
                if (ringEl) {
                    const offset = Number(ringEl.dataset.offset || "35");
                    gsap.fromTo(
                        ringEl,
                        { strokeDashoffset: 326.7 },
                        {
                            strokeDashoffset: offset,
                            duration: 1.8,
                            delay: i * 0.12,
                            ease: "power2.out",
                            scrollTrigger: { trigger: "[data-stats-grid]", start: "top 84%" },
                        },
                    );
                }
            });
        });
    }, { scope: root, dependencies: [lang] });

    // Row 1 Logos — Egyptian & Regional Universities (Moves Left)
    const row1Logos = [
        { name: "CAIRO UNIVERSITY", sub: "جامعة القاهرة", kind: "cairo" as const },
        { name: "AIN SHAMS UNIV", sub: "جامعة عين شمس", kind: "ainshams" as const },
        { name: "ALEXANDRIA UNIV", sub: "جامعة الإسكندرية", kind: "alexandria" as const },
        { name: "MANSOURA UNIV", sub: "جامعة المنصورة", kind: "mansoura" as const },
        { name: "ZEWAIL CITY", sub: "مدينة زويل للعلوم", kind: "zewail" as const },
        { name: "E-JUST", sub: "الجامعة المصرية اليابانية", kind: "ejust" as const },
        { name: "GUC • GIU", sub: "الجامعة الألمانية", kind: "guc" as const },
        { name: "BUE EGYPT", sub: "الجامعة البريطانية", kind: "bue" as const },
    ];

    // Row 2 Logos — LMS Platforms & Academic Institutions (Moves Right)
    const row2Logos = [
        { name: "MOODLE LMS", sub: "منصة مودل التعليمية", kind: "moodle" as const },
        { name: "BLACKBOARD LEARN", sub: "بلاك بورد الجامعي", kind: "blackboard" as const },
        { name: "CANVAS LMS", sub: "نظام كانفاس التعليمي", kind: "canvas" as const },
        { name: "COURSERA CAMPUS", sub: "كورسيرا للجامعات", kind: "coursera" as const },
        { name: "OPEN EDX", sub: "منصة إيدكس المفتوحة", kind: "openedx" as const },
        { name: "MS TEAMS EDU", sub: "مايكروسوفت تيمز للتعليم", kind: "teams" as const },
        { name: "GOOGLE CLASSROOM", sub: "جوجل كلاس روم", kind: "classroom" as const },
        { name: "AL-AZHAR UNIV", sub: "جامعة الأزهر الشريف", kind: "azhar" as const },
    ];

    const renderMarkSvg = (kind: string) => {
        switch (kind) {
            case "cairo":
                // Cairo University Dome & Clock Tower Crest
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        {/* Outer shield & laurel base */}
                        <path d="M20 3L7 8v11c0 9 5.5 15.8 13 18 7.5-2.2 13-9 13-18V8L20 3z" strokeOpacity="0.45" />
                        {/* Iconic Cairo Univ Dome */}
                        <path d="M12 24c0-4.8 3.6-8.5 8-8.5s8 3.7 8 8.5" fill="currentColor" fillOpacity="0.16" />
                        <path d="M20 11v4.5M10 24h20M13 24v6M17.5 24v6M22.5 24v6M27 24v6M11 30h18" />
                    </svg>
                );
            case "ainshams":
                // Ain Shams University Obelisk & Twin Falcons + Sun Disc
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="20" cy="8.5" r="3" fill="currentColor" fillOpacity="0.25" />
                        {/* Obelisk */}
                        <path d="M20 12l2.5 3 1.2 17h-7.4l1.2-17L20 12z" fill="currentColor" fillOpacity="0.14" />
                        {/* Twin Horus wings/falcons */}
                        <path d="M16 20l-7-3 1.8 7.5L16 27M24 20l7-3-1.8 7.5L24 27" />
                        <path d="M10 32h20" />
                    </svg>
                );
            case "alexandria":
                // Alexandria University Pharos Lighthouse & Waves
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="20" cy="10" r="2.8" fill="currentColor" />
                        {/* Light beams */}
                        <path d="M9 7l5 2.5M31 7l-5 2.5M8 12h5.5M26.5 12H32" />
                        {/* Tiered Pharos tower */}
                        <path d="M16.5 13.5h7l1.5 7h-10l1.5-7zM14 20.5h12l1.8 8.5H12.2l1.8-8.5z" fill="currentColor" fillOpacity="0.14" />
                        {/* Sea waves */}
                        <path d="M7 33c2.5-2 5-2 7.5 0s5 2 7.5 0 5-2 7.5 0" />
                    </svg>
                );
            case "mansoura":
                // Mansoura University Gear, Open Book & Torch
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="20" cy="20" r="13.5" strokeDasharray="3.5 2.5" />
                        {/* Torch flame */}
                        <path d="M20 7c2.5 2.5 3 5 0 7.5-3-2.5-2.5-5 0-7.5z" fill="currentColor" />
                        <path d="M20 14.5v9" />
                        {/* Open book */}
                        <path d="M11 22c3.5-1.5 6.5-0.8 9 1.5 2.5-2.3 5.5-3 9-1.5v7c-3.5-1.5-6.5-0.8-9 1.5-2.5-2.3-5.5-3-9-1.5v-7z" fill="currentColor" fillOpacity="0.14" />
                    </svg>
                );
            case "zewail":
                // Zewail City of Science & Technology Atomic Crest
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75">
                        <ellipse cx="20" cy="20" rx="15" ry="6" transform="rotate(32 20 20)" />
                        <ellipse cx="20" cy="20" rx="15" ry="6" transform="rotate(-32 20 20)" />
                        <ellipse cx="20" cy="20" rx="15" ry="6" transform="rotate(90 20 20)" strokeOpacity="0.55" />
                        <circle cx="20" cy="20" r="3.2" fill="currentColor" />
                    </svg>
                );
            case "ejust":
                // E-JUST Pyramid + Japanese Rising Sun Disc
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="24" cy="14" r="6" fill="currentColor" fillOpacity="0.28" />
                        <path d="M7 31L17.5 13 28 31H7z" fill="currentColor" fillOpacity="0.14" />
                        <path d="M17.5 13L13 31M7 31h26" />
                    </svg>
                );
            case "guc":
                // GUC German University Triple Architectural Bars + Crest
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75">
                        <rect x="6" y="8" width="28" height="24" rx="4" strokeOpacity="0.4" />
                        <rect x="10" y="12.5" width="20" height="3.8" rx="1" fill="currentColor" />
                        <rect x="10" y="18.2" width="15" height="3.8" rx="1" fill="currentColor" fillOpacity="0.7" />
                        <rect x="10" y="24" width="20" height="3.8" rx="1" fill="currentColor" fillOpacity="0.45" />
                    </svg>
                );
            case "bue":
                // BUE British University Heraldic Crown & Shield
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        {/* Royal Crown */}
                        <path d="M11 14l2.2-6 6.8 4.2L26.8 8 29 14H11z" fill="currentColor" fillOpacity="0.2" />
                        {/* Divided Shield */}
                        <path d="M10 17h20v7.5c0 6.2-4.2 10.5-10 12.5-5.8-2-10-6.3-10-12.5V17z" />
                        <path d="M20 17v20M10 24h20" strokeOpacity="0.65" />
                    </svg>
                );
            case "moodle":
                // Iconic Moodle "m" with Graduation Cap
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        {/* Slanted Mortarboard Cap */}
                        <path d="M7 13.5L19 8l11 4.5-11 5-12-4z" fill="currentColor" fillOpacity="0.28" />
                        <path d="M7 13.5v5.5" />
                        {/* Bold lowercase 'm' */}
                        <path d="M10 31V21.5c0-2.5 1.8-4.2 4.2-4.2s4.2 1.7 4.2 4.2V31M18.4 21.5c0-2.5 1.8-4.2 4.2-4.2s4.4 1.7 4.4 4.2V31" strokeWidth="2.6" />
                    </svg>
                );
            case "blackboard":
                // Iconic Blackboard "Bb" Serif Monogram Badge
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="6" y="6" width="28" height="28" rx="6" fill="currentColor" fillOpacity="0.1" />
                        <text x="10" y="26.5" fill="currentColor" stroke="none" fontSize="17" fontWeight="800" fontFamily="Georgia, serif">
                            Bb
                        </text>
                        <path d="M10 30h20" strokeOpacity="0.6" />
                    </svg>
                );
            case "canvas":
                // Iconic Canvas by Instructure 8-Dot Starburst Rosette
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="currentColor">
                        <circle cx="20" cy="8" r="2.7" />
                        <circle cx="28.5" cy="11.5" r="2.7" opacity="0.85" />
                        <circle cx="32" cy="20" r="2.7" />
                        <circle cx="28.5" cy="28.5" r="2.7" opacity="0.85" />
                        <circle cx="20" cy="32" r="2.7" />
                        <circle cx="11.5" cy="28.5" r="2.7" opacity="0.85" />
                        <circle cx="8" cy="20" r="2.7" />
                        <circle cx="11.5" cy="11.5" r="2.7" opacity="0.85" />
                        <circle cx="20" cy="20" r="5.2" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 2.2" />
                    </svg>
                );
            case "coursera":
                // Coursera Infinity Loop Emblem
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                        <path d="M14.5 14.5c-3.2 0-5.8 2.5-5.8 5.5s2.6 5.5 5.8 5.5c4.5 0 6.5-11 11-11 3.2 0 5.8 2.5 5.8 5.5s-2.6 5.5-5.8 5.5c-4.5 0-6.5-11-11-11z" />
                    </svg>
                );
            case "openedx":
                // Open edX Intersecting Rings & X
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                        <circle cx="16" cy="20" r="8.5" fill="currentColor" fillOpacity="0.12" />
                        <circle cx="24" cy="20" r="8.5" />
                        <path d="M17 15l6 10M23 15l-6 10" strokeWidth="2.2" />
                    </svg>
                );
            case "teams":
                // Microsoft Teams Shield & Connected Users
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="7" y="11" width="17" height="18" rx="3.5" fill="currentColor" fillOpacity="0.18" />
                        <path d="M12.5 16.5h6M15.5 16.5v8" strokeWidth="2.2" />
                        <circle cx="28.5" cy="14.5" r="3" />
                        <path d="M24 27v-3.5c0-2.2 2-4 4.5-4s4.5 1.8 4.5 4V27" />
                    </svg>
                );
            case "classroom":
                // Google Classroom Chalkboard & Silhouettes
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="6" y="8" width="28" height="22" rx="3.5" fill="currentColor" fillOpacity="0.12" />
                        <circle cx="20" cy="16" r="2.6" fill="currentColor" />
                        <path d="M15 24c0-2.5 2.2-4.2 5-4.2s5 1.7 5 4.2" />
                        <circle cx="12.5" cy="18" r="1.8" />
                        <circle cx="27.5" cy="18" r="1.8" />
                        <path d="M23 30h6" strokeWidth="2.4" />
                    </svg>
                );
            case "azhar":
            default:
                // Al-Azhar University Mosque Dome, Minaret & Crescent
                return (
                    <svg className="size-7 sm:size-8 shrink-0" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                        {/* Minaret */}
                        <path d="M29 10v20M27.5 13h3" />
                        {/* Dome */}
                        <path d="M10 25c0-4.8 3.6-8.5 8-8.5s8 3.7 8 8.5" fill="currentColor" fillOpacity="0.16" />
                        <path d="M18 13v3.5M8 25h22M8 30h24" />
                        {/* Open book base */}
                        <path d="M12 27.5l6 2 6-2" />
                    </svg>
                );
        }
    };

    const clientSectors = [
        {
            icon: GraduationCap,
            surface: "bg-[#FAF6F0] text-[#1C1410] border border-white/15",
            iconTone: "bg-[#6F4E37] text-[#FAF6F0]",
            badge: l("الجامعات والكليات", "Universities & Faculties"),
            title: l("كليات الحاسبات، الهندسة، الطب، واللغات", "CS, Engineering, Medical & Language Faculties"),
            body: l(
                "امتحان آلاف الطلاب شفوياً في المقررات العملية ومناقشات المشاريع واللغات في نفس اليوم بدون ضغط اللجان الشفوية التقليدية.",
                "Assess thousands of students orally in practical courses, project defenses, and language modules on the same day without panel bottlenecks.",
            ),
        },
        {
            icon: School,
            surface: "wb-mocha-stage text-[#FAF6F0] border border-[#FAF6F0]/20",
            iconTone: "bg-[#E3A458] text-[#18110D]",
            badge: l("المدارس الدولية واللغات", "Schools & Academies"),
            title: l("المدارس الدولية ومدارس اللغات الحديثة", "International & Modern Language Schools"),
            body: l(
                "تقييم مستمر لمهارات التحدث والقراءة الشفوية والاستيعاب للطلاب بشكل أسبوعي ككويز أونلاين سريع ومنظم.",
                "Continuous weekly assessment of speaking, oral reading, and comprehension skills as a fast, structured online quiz.",
            ),
        },
        {
            icon: Building2,
            surface: "bg-[#EFE7DE] text-[#1C1410] border border-white/20",
            iconTone: "bg-[#38291F] text-[#FAF6F0]",
            badge: l("المنصات التعليمية", "EdTech & LMS Platforms"),
            title: l("منصات الكورسات والتدريب عن بُعد", "Online Course & Corporate Training Platforms"),
            body: l(
                "اعتماد الشهادات بامتحان شفوي حقيقي يمنع الغش ويتأكد إن المتدرب نفسه هو اللي جاوب بصوته قدام الكاميرا.",
                "Issue verified certificates backed by a real biometric oral exam confirming the learner answered in person on camera.",
            ),
        },
    ];

    const stats = [
        {
            target: 98,
            suffix: "%",
            offset: 16,
            accent: "#E3A458",
            label: l("دقة التصحيح بالمعنى مقارنة بتقييم الدكتور", "Semantic grading accuracy vs. lecturer scoring"),
        },
        {
            target: 478,
            suffix: "",
            offset: 24,
            accent: "#FAF6F0",
            label: l("نقطة تتبُّع حيوي على الوجه والعين لمنع الغش", "Biometric face & eye landmarks tracked live"),
        },
        {
            target: 90,
            suffix: "%",
            offset: 32,
            accent: "#D8CFC4",
            label: l("توفير في وقت اللجان الشفوية والتصحيح", "Time saved on oral exam panels & grading"),
        },
        {
            target: 3,
            suffix: " AI",
            offset: 20,
            accent: "#E3A458",
            label: l("موديلات ذكاء اصطناعي بتشتغل في نفس اللحظة", "Specialized AI models running simultaneously"),
        },
    ];

    return (
        <Section
            id="clients"
            tone="b"
            className="wb-dark-stage rounded-[24px] sm:rounded-[30px] mx-2 sm:mx-4 py-16 sm:py-24 lg:py-32"
        >
            <div ref={root} className="mx-auto max-w-[92rem] px-5 sm:px-10 lg:px-14">
                {/* Two-Row Opposing Marquee Header */}
                <div className="mx-auto max-w-3xl text-center">
                    <Eyebrow className="text-[#E3A458]">{l("موثوق من قبل", "Trusted By")}</Eyebrow>
                    <h2 className={`${H2} mt-2 text-[#FAF6F0]`}>
                        {l("أبرز العملاء والجهات المستفيدة", "Featured Clients & Institutions")}
                    </h2>
                    <p className="ar-body mt-4 text-base sm:text-lg font-medium leading-[1.85] text-[#FAF6F0]/80">
                        {l(
                            "سواء كنت محاضر جامعي، إدارة مدرسة، أو صاحب منصة تعليمية، OralIQ بتحول التقييم الشفوي لعملية رقمية دقيقة ومؤمّنة بالكامل.",
                            "Whether you're a university faculty, school administration, or EdTech founder, OralIQ turns oral assessment into a rapid, verified digital workflow.",
                        )}
                    </p>
                </div>

                {/* Two-Row Frameless Right-and-Left Marquee */}
                <div className="mt-10 sm:mt-14 -mx-5 sm:-mx-6 px-0 select-none">
                    {/* Row 1 — Moves Left */}
                    <div className="relative overflow-hidden mb-7 sm:mb-9" dir="ltr">
                        <div
                            className="pointer-events-none absolute left-0 top-0 bottom-0 w-16 sm:w-32 z-10"
                            style={{ background: "linear-gradient(to right, var(--stage-fade), transparent)" }}
                            aria-hidden
                        />
                        <div
                            className="pointer-events-none absolute right-0 top-0 bottom-0 w-16 sm:w-32 z-10"
                            style={{ background: "linear-gradient(to left, var(--stage-fade), transparent)" }}
                            aria-hidden
                        />
                        <div
                            dir="ltr"
                            className="flex w-max items-center gap-10 sm:gap-20 animate-[oiq-marquee-left_32s_linear_infinite]"
                        >
                            {[...row1Logos, ...row1Logos].map((item, idx) => (
                                <div
                                    key={`r1-${item.name}-${idx}`}
                                    className="group/logo flex shrink-0 items-center gap-3.5 text-[#FAF6F0] opacity-80 hover:opacity-100 transition-opacity duration-300"
                                >
                                    <span className="flex size-11 sm:size-12 shrink-0 items-center justify-center rounded-2xl border border-[#FAF6F0]/15 bg-[#FAF6F0]/[0.06] text-[#E3A458] transition-colors group-hover/logo:border-[#E3A458]/50 group-hover/logo:bg-[#E3A458]/15">
                                        {renderMarkSvg(item.kind)}
                                    </span>
                                    <div className="text-left">
                                        <span className="wb-num block text-sm sm:text-lg font-extrabold tracking-tight text-[#FAF6F0] leading-none">
                                            {item.name}
                                        </span>
                                        <span className="ar-body mt-1 block text-[11px] sm:text-xs font-medium text-[#E3A458] leading-none">
                                            {item.sub}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Row 2 — Moves Right */}
                    <div className="relative overflow-hidden" dir="ltr">
                        <div
                            className="pointer-events-none absolute left-0 top-0 bottom-0 w-16 sm:w-32 z-10"
                            style={{ background: "linear-gradient(to right, var(--stage-fade), transparent)" }}
                            aria-hidden
                        />
                        <div
                            className="pointer-events-none absolute right-0 top-0 bottom-0 w-16 sm:w-32 z-10"
                            style={{ background: "linear-gradient(to left, var(--stage-fade), transparent)" }}
                            aria-hidden
                        />
                        <div
                            dir="ltr"
                            className="flex w-max items-center gap-10 sm:gap-20 animate-[oiq-marquee-right_34s_linear_infinite]"
                        >
                            {[...row2Logos, ...row2Logos].map((item, idx) => (
                                <div
                                    key={`r2-${item.name}-${idx}`}
                                    className="group/logo flex shrink-0 items-center gap-3.5 text-[#FAF6F0] opacity-80 hover:opacity-100 transition-opacity duration-300"
                                >
                                    <span className="flex size-11 sm:size-12 shrink-0 items-center justify-center rounded-2xl border border-[#FAF6F0]/15 bg-[#FAF6F0]/[0.06] text-[#E3A458] transition-colors group-hover/logo:border-[#E3A458]/50 group-hover/logo:bg-[#E3A458]/15">
                                        {renderMarkSvg(item.kind)}
                                    </span>
                                    <div className="text-left">
                                        <span className="wb-num block text-sm sm:text-lg font-extrabold tracking-tight text-[#FAF6F0] leading-none">
                                            {item.name}
                                        </span>
                                        <span className="ar-body mt-1 block text-[11px] sm:text-xs font-medium text-[#E3A458] leading-none">
                                            {item.sub}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* 3 Institutional Client Sector Cards */}
                <div data-clients-grid className="mt-12 sm:mt-16 grid grid-cols-1 gap-5 sm:gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {clientSectors.map((c, idx) => (
                        <article
                            key={c.title}
                            data-client-card
                            className={`flex flex-col justify-between rounded-[22px] sm:rounded-[24px] p-6 sm:p-9 shadow-[0_24px_55px_-18px_rgba(0,0,0,0.4)] ${c.surface} ${idx === 2 ? "md:col-span-2 lg:col-span-1" : ""}`}
                        >
                            <div>
                                <div className="flex items-center justify-between gap-3">
                                    <span className="text-xs font-bold opacity-80">
                                        {c.badge}
                                    </span>
                                    <span className={`flex size-12 items-center justify-center rounded-2xl ${c.iconTone}`}>
                                        <c.icon className="size-6" aria-hidden />
                                    </span>
                                </div>
                                <h3 className="ar-heading mt-5 sm:mt-6 font-display text-xl sm:text-2xl font-bold">
                                    {c.title}
                                </h3>
                                <p className="ar-body mt-3 text-sm sm:text-base font-medium leading-[1.85] opacity-85">
                                    {c.body}
                                </p>
                            </div>
                            <div className="mt-6 flex items-center gap-2 border-t border-current/15 pt-4 text-xs font-bold opacity-85">
                                <ShieldCheck className="size-4 text-[#E3A458]" aria-hidden />
                                <span>{l("معتمد وجاهز للتشغيل الفوري", "Verified & ready for immediate deployment")}</span>
                            </div>
                        </article>
                    ))}
                </div>

                {/* Divided Editorial Metrics Bar */}
                <div
                    data-stats-grid
                    className="mt-10 sm:mt-14 grid grid-cols-1 divide-y divide-white/12 rounded-[22px] sm:rounded-[24px] border border-white/15 bg-white/[0.04] sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x lg:rtl:divide-x-reverse"
                >
                    {stats.map((st) => (
                        <div
                            key={st.label}
                            data-stat-card
                            className="flex flex-col items-center p-6 sm:p-8 text-center text-[#FAF6F0]"
                        >
                            <div className="relative flex size-24 sm:size-28 items-center justify-center">
                                <svg className="size-full -rotate-90" viewBox="0 0 120 120" aria-hidden>
                                    <circle
                                        cx="60"
                                        cy="60"
                                        r="52"
                                        fill="none"
                                        stroke="rgba(250,246,240,0.12)"
                                        strokeWidth="6"
                                    />
                                    <circle
                                        data-stat-ring
                                        data-offset={st.offset}
                                        cx="60"
                                        cy="60"
                                        r="52"
                                        fill="none"
                                        stroke={st.accent}
                                        strokeWidth="6"
                                        strokeLinecap="round"
                                        strokeDasharray="326.7"
                                        strokeDashoffset="326.7"
                                    />
                                </svg>
                                <span
                                    data-stat-num
                                    data-target={st.target}
                                    data-suffix={st.suffix}
                                    className="wb-num absolute text-2xl sm:text-3xl font-extrabold text-[#FAF6F0]"
                                >
                                    {st.target}{st.suffix}
                                </span>
                            </div>
                            <p className="ar-body mt-3 sm:mt-4 text-xs sm:text-sm font-bold leading-relaxed text-[#FAF6F0]/85">
                                {st.label}
                            </p>
                        </div>
                    ))}
                </div>
            </div>
        </Section>
    );
}
