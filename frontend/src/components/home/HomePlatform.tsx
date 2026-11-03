import { useRef } from "react";
import { ArrowUpLeft, Building, Code2, GraduationCap, Laptop, School, Sparkles } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { BTN, Eyebrow, H2, Section } from "./ui";

/**
 * Section 5 (#integrate): Join as a Feature inside a School, University, or EdTech Platform
 * Theme-aware (flips between Warm Off-White and Rich Espresso Brown) & responsive across Mobile, Tablet, and Desktop.
 */
export function HomePlatform() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-plat-head]",
                { y: 32, opacity: 0 },
                {
                    y: 0,
                    opacity: 1,
                    duration: 0.7,
                    stagger: 0.1,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-plat-info]", start: "top 82%" },
                },
            );
            gsap.fromTo(
                "[data-plat-card]",
                { y: 40, opacity: 0, scale: 0.95 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.75,
                    stagger: 0.12,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-plat-grid]", start: "top 82%" },
                },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const places = [
        {
            icon: GraduationCap,
            surface: "wb-mocha-stage text-[#FAF6F0] border border-[#FAF6F0]/15",
            iconTone: "bg-[#E3A458] text-[#18110D]",
            tag: l("تكامل جامعي", "University LMS"),
            title: l("فيتشـر جوّه بوابة الجامعة أو الكلية", "Feature Inside University & Faculty Portals"),
            body: l(
                "بنربط نظام الكويز الشفوي مباشرة ببوابة الجامعة (Moodle أو Blackboard أو النظام الخاص بالجامعة) عشان الطالب يمتحن شفوي في مكانه والدرجة تنزل في رصيده تلقائياً.",
                "We connect the oral quiz engine directly to your university portal (Moodle, Blackboard, or custom SIS) so students sit oral exams in-place and grades sync automatically.",
            ),
        },
        {
            icon: School,
            surface: "bg-sheet text-ink border border-rule",
            iconTone: "bg-pen-wash text-pen border border-rule",
            tag: l("تكامل مدرسي", "School Systems"),
            title: l("فيتشـر جوّه تطبيق أو موقع المدرسة", "Feature Inside School Apps & Portals"),
            body: l(
                "بنضيف الكويزات الشفوية وتسميع اللغات والقراءة كميزة أساسية داخل منصة المدرسة باسمها وشعارها، مع تقارير فورية للمدرس وولي الأمر.",
                "We embed oral quizzes, language speaking, and reading checks inside your school's platform under its own logo, with instant teacher and parent reports.",
            ),
        },
        {
            icon: Laptop,
            surface: "bg-sheet-2 text-ink border border-rule",
            iconTone: "bg-[#6F4E37] text-[#FAF6F0]",
            tag: l("منصات الكورسات", "EdTech & LMS"),
            title: l("فيتشـر جوّه منصتك التعليمية (LMS)", "White-Label Feature Inside Your EdTech Platform"),
            body: l(
                "لو عندك منصة كورسات أو تعليم أونلاين، تقدر تضيف (امتحان شفوي بالذكاء الاصطناعي) جنب كويز الاختيارات العادي بنفس ألوان منصتك وبدون ما الطالب يخرج لموقع خارجي.",
                "If you run an online course platform, add an 'AI Oral Quiz' right alongside standard MCQ quizzes in your own brand colors without sending students to an external site.",
            ),
        },
        {
            icon: Building,
            surface: "bg-sheet text-ink border border-rule",
            iconTone: "bg-[#38291F] text-[#FAF6F0]",
            tag: l("مراكز التدريب", "Training Academies"),
            title: l("فيتشـر لمراكز التدريب واللغات والتوظيف", "Feature for Training Centers & Assessments"),
            body: l(
                "اختبر آلاف المتدربين والمتقدمين شفوياً بالذكاء الاصطناعي مع التحقق من الهوية بالوجه والصوت، واستلم تقارير تفصيلية جاهزة للاعتماد.",
                "Assess thousands of trainees and applicants orally with AI biometric verification and receive detailed competency reports automatically.",
            ),
        },
    ];

    return (
        <Section id="integrate" tone="a" className="py-16 sm:py-24 lg:py-32">
            <div ref={root} className="mx-auto grid max-w-[92rem] grid-cols-1 gap-10 px-5 sm:px-10 lg:grid-cols-12 lg:gap-16 lg:px-16">
                {/* Left/Start Info Column */}
                <div data-plat-info className="lg:col-span-5 lg:self-center">
                    <div data-plat-head>
                        <Eyebrow className="text-pen">
                            {l("انضم كـ فيتشر جوه منصتك", "Embed as a Feature in Your Platform")}
                        </Eyebrow>
                    </div>
                    <h2 data-plat-head className={`${H2} mt-3 text-ink`}>
                        {l(
                            "نقدر ننضم كـ فيتشر جاهزة جوه مدرستك، جامعتك، أو منصتك التعليمية.",
                            "We Can Join as a Ready-Made Feature Inside Your School, University, or EdTech Platform.",
                        )}
                    </h2>
                    <p data-plat-head className="ar-body mt-5 sm:mt-6 text-base sm:text-lg font-medium leading-[1.85] text-ink-2">
                        {l(
                            "مش لازم طلابك يفتحوا موقع جديد أو يعملوا حساب تاني! بنركّب محرك OralIQ بـ الـ 3 موديلات بتوعه كـ (Feature) جوّه السيستم أو المنصة بتاعتك، بنفس ألوانك وتحت اسمك وشعارك.",
                            "Your students don't need to visit a new website or create another account! We embed OralIQ and its 3 AI models as a native feature inside your existing platform, in your colors and under your brand.",
                        )}
                    </p>

                    {/* Integration Specs Box */}
                    <div
                        data-plat-head
                        className="mt-6 sm:mt-7 rounded-[22px] border border-rule bg-sheet p-5 sm:p-6 text-ink shadow-card"
                    >
                        <div className="flex items-center gap-2.5 text-sm font-bold text-pen">
                            <Code2 className="size-5 shrink-0" aria-hidden />
                            <span>{l("ربط سريع عبر API / LTI / White-Label SDK", "Fast Integration via API / LTI / White-Label SDK")}</span>
                        </div>
                        <p className="ar-body mt-2 text-sm font-medium text-ink-2">
                            {l(
                                "الدرجات وتقارير النزاهة بتسمّع تلقائياً في لوحة تحكم المدرسة أو الجامعة أو المنصة التعليمية بتاعتك في نفس اللحظة.",
                                "Scores and biometric integrity reports sync automatically into your school, university, or LMS gradebook in real time.",
                            )}
                        </p>
                    </div>

                    <div data-plat-head className="mt-7 sm:mt-8 flex flex-wrap items-center gap-3">
                        <a href="#contact" className={`${BTN} w-full sm:w-auto justify-center ps-7 pe-3`}>
                            <Sparkles className="size-4 text-[#E3A458]" aria-hidden />
                            <span>{l("تواصل معنا لدمجها في منصتك", "Contact us to integrate into your platform")}</span>
                            <span className="flex size-8 items-center justify-center rounded-full bg-white/15 text-white">
                                <ArrowUpLeft className="size-4 ltr:rotate-90" aria-hidden />
                            </span>
                        </a>
                    </div>
                </div>

                {/* Right/End 4 Feature Cards Grid */}
                <ul data-plat-grid className="grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:col-span-7">
                    {places.map((p) => (
                        <li
                            key={p.title}
                            data-plat-card
                            className={`relative flex flex-col justify-between overflow-hidden rounded-[22px] sm:rounded-[24px] p-6 sm:p-8 shadow-card ${p.surface}`}
                        >
                            <div className="relative z-10">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-xs font-bold opacity-80">
                                        {p.tag}
                                    </span>
                                    <span className={`flex size-11 sm:size-12 items-center justify-center rounded-2xl ${p.iconTone}`}>
                                        <p.icon className="size-5 sm:size-6" aria-hidden />
                                    </span>
                                </div>
                                <h3 className="ar-heading mt-5 font-display text-xl font-bold sm:text-2xl">
                                    {p.title}
                                </h3>
                                <p className="ar-body mt-3 text-sm sm:text-base font-medium leading-[1.8] opacity-85">
                                    {p.body}
                                </p>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>
        </Section>
    );
}
