import { useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowUpLeft, BrainCircuit, CheckCircle2, Eye, Mic } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { BTN, BTN_GHOST, Eyebrow, H2, Section } from "./ui";

/**
 * Section 1 after Hero (#about): What is the Platform?
 * - Theme-aware (flips cleanly between Warm Off-White in Light Mode and Rich Espresso Brown in Dark Mode).
 * - Responsive across Mobile, Tablet, and Desktop.
 */
export function HomeAbout({ startHref }: { startHref: string }) {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);

    useGSAP(() => {
        withMotion(() => {
            const words = gsap.utils.toArray<HTMLElement>("[data-intro-word]");
            if (words.length > 0) {
                gsap.fromTo(
                    words,
                    { opacity: 0.18, y: 8 },
                    {
                        opacity: 1,
                        y: 0,
                        stagger: 0.06,
                        ease: "none",
                        scrollTrigger: {
                            trigger: "[data-brand-intro]",
                            start: "top 82%",
                            end: "bottom 58%",
                            scrub: 0.4,
                        },
                    },
                );
            }

            gsap.fromTo(
                "[data-pillar-pill]",
                { y: 28, opacity: 0, scale: 0.95 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.65,
                    stagger: 0.1,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-pillars-strip]", start: "top 84%" },
                },
            );

            gsap.fromTo(
                "[data-model-card]",
                { y: 48, opacity: 0, scale: 0.95 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.8,
                    stagger: 0.14,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-models-grid]", start: "top 80%" },
                },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const models = [
        {
            num: "01",
            weight: "10%",
            weightLabel: l("من الدرجة للطلاقة", "of grade for fluency"),
            icon: Mic,
            surface: "bg-sheet text-ink border border-rule shadow-card",
            iconTone: "bg-pen-wash text-pen border border-rule",
            badge: l("الموديل الأول", "Model 01"),
            title: l("موديل التفريغ الصوتي وتحليل الطلاقة", "Speech-to-Text & Vocal Fluency Model"),
            body: l(
                "بيسمع إجابة الطالب باللهجة المصرية أو العربية الفصحى أو الإنجليزية، يحوّلها لنص مكتوب فوري، ويقيس سرعة الكلام، التردد، والوقفات الطويلة عشان يقيم ثقة الطالب في إجابته.",
                "Listens to the student's spoken answer in Arabic or English, transcribes it immediately, and measures speech pace, hesitation, and pauses to evaluate vocal confidence.",
            ),
            points: [
                l("يدعم العربي والمصري والإنجليزي والمصطلحات العلمية", "Supports Arabic, Egyptian dialect, English & technical terms"),
                l("يقيس الطلاقة والوقفات بدون ظلم للطالب", "Measures fluency and pauses fairly"),
            ],
        },
        {
            num: "02",
            weight: "80%",
            weightLabel: l("من الدرجة على الفهم والمعنى", "of grade for semantic meaning"),
            icon: BrainCircuit,
            surface: "wb-mocha-stage text-[#FAF6F0] border border-[#FAF6F0]/15 shadow-[0_28px_65px_-20px_rgba(56,41,31,0.45)]",
            iconTone: "bg-white/15 text-[#FAF6F0] border border-white/20",
            badge: l("الموديل الثاني", "Model 02"),
            title: l("موديل التصحيح الذكي بالمعنى والفهم", "Semantic Meaning & Deep Grading Model"),
            body: l(
                "مش بيدور على حفظ الكلمات بالحرف؛ الموديل بيفهم معنى كلام الطالب ويقارنه بالإجابة النموذجية بتاعت الدكتور حتى لو الطالب شرح بأسلوبه، ويطلع الدرجة مع سبب واضح لكل درجة.",
                "Doesn't just match memorized words—it understands the student's meaning, compares it to the lecturer's model answer even in the student's own phrasing, and outputs a justified score.",
            ),
            points: [
                l("تصحيح فوري بالمعنى من غير ما الدكتور يتدخل", "Instant semantic grading with zero lecturer intervention"),
                l("تبرير تفصيلي للدرجة والنقاط اللي الطالب قالها أو نسيها", "Detailed rubric breakdown of covered and missed points"),
            ],
        },
        {
            num: "03",
            weight: "10%",
            weightLabel: l("من الدرجة للنزاهة والهوية", "of grade for biometric integrity"),
            icon: Eye,
            surface: "bg-sheet-2 text-ink border border-rule shadow-card",
            iconTone: "bg-sheet text-pen border border-rule",
            badge: l("الموديل الثالث", "Model 03"),
            title: l("موديل بصمة الوجه والعين والصوت لمنع الغش", "478-Point Face, Eye-Gaze & Voice Anti-Cheat"),
            body: l(
                "بيرسم 478 نقطة على وجه الطالب ويتابع حركة عينه لحظة بلحظة مع مطابقة بصمة صوته؛ لو الطالب بص في ورق أو شاشة تانية أو حد غيره اتكلم، الموديل بيكتشفه فوراً فالطالب مش هيعرف يغش.",
                "Maps 478 facial landmarks and tracks eye gaze in real time alongside voiceprint verification—if the student reads off another screen or someone else speaks, it flags it immediately.",
            ),
            points: [
                l("متابعة حركة العين والالتفات خارج الشاشة لحظياً", "Real-time eye-gaze and head-turn tracking"),
                l("مطابقة بصمة الوجه وبصمة الصوت طوال مدة الكويز", "Continuous face & voiceprint identity verification"),
            ],
        },
    ];

    const pillars = [
        {
            tone: "bg-sheet border-rule text-ink",
            badgeBg: "bg-[#6F4E37] text-[#FAF6F0]",
            title: l("من غير ما الدكتور يتدخل", "Zero Lecturer Intervention"),
            desc: l("الدفعة كلها بتمتحن في نفس الوقت، والـ 3 موديلات بتسأل وتسمع وتصحح وتطلع النتيجة النهائية جاهزة.", "The whole cohort takes the exam simultaneously while the 3 AI models ask, listen, grade, and deliver final scores."),
        },
        {
            tone: "wb-mocha-stage border-[#FAF6F0]/15 text-[#FAF6F0]",
            badgeBg: "bg-[#E3A458] text-[#18110D]",
            title: l("الطالب مش هيعرف يغش", "Students Cannot Cheat"),
            desc: l("الكاميرا والمايك شغالين بـ 478 نقطة تتبع للعين والوجه وبصمة الصوت، وأول ما السؤال يظهر العد التنازلي بيبدأ فوراً.", "Camera and mic enforce 478-point eye/face tracking and voiceprint matching with an immediate countdown."),
            dark: true,
        },
        {
            tone: "bg-sheet-2 border-rule text-ink",
            badgeBg: "bg-[#6F4E37] text-[#FAF6F0]",
            title: l("الكويز الشفوي بقى أونلاين زي أي كويز", "Oral Quiz is Now Online Like Any Quiz"),
            desc: l("زي ما بتبعت لينك كويز اختيارات (MCQ)، دلوقتي تبعت لينك كويز شفوي والطالب يدخل يجاوب بصوته في دقايق.", "Just like sharing an MCQ quiz link, you now share an oral quiz link and students answer by voice in minutes."),
        },
    ];

    const splitWords = (text: string, accentClass?: string) =>
        text.split(" ").map((w, i) => (
            <span key={`${w}-${i}`} data-intro-word className={`inline-block me-[0.26em] ${accentClass || ""}`}>
                {w}
            </span>
        ));

    return (
        <Section id="about" tone="a" className="py-16 sm:py-24 lg:py-32">
            <div ref={root} className="mx-auto max-w-[92rem] px-5 sm:px-10 lg:px-16">
                {/* Word-by-Word Scroll-Scrubbed Brand Intro Statement */}
                <div data-brand-intro className="mx-auto max-w-[74rem] text-center">
                    <Eyebrow className="text-pen">
                        {l("إيه هي منصة OralIQ؟", "What is the OralIQ Platform?")}
                    </Eyebrow>

                    <h2 className="ar-heading mt-4 font-display text-[clamp(1.75rem,3.6vw,3.75rem)] font-bold leading-[1.38] text-ink">
                        {splitWords(l("منصة امتحانات شفوية بالذكاء الاصطناعي", "An AI-powered oral examination platform"))}
                        {splitWords(l("تشتغل أوتوماتيك من غير ما الدكتور يتدخل،", "running automatically with zero lecturer intervention,"), "text-pen")}
                        {splitWords(l("عن طريق 3 موديلات ذكية بتسمع وتصحح الإجابة بالمعنى،", "via 3 AI models that listen and grade semantic meaning,"))}
                        {splitWords(l("وبتراقب حركة العين والوجه والصوت عشان الطالب مستحيل يغش", "while tracking eye gaze, face & voice so students cannot cheat"))}
                        {splitWords(l("ويبقى الكويز الشفوي أونلاين زي أي كويز عادي.", "making the oral quiz online just like any regular quiz."), "text-pen")}
                    </h2>
                </div>

                {/* 3 Key Pillars Strip */}
                <div data-pillars-strip className="mt-12 sm:mt-16 grid grid-cols-1 gap-4 sm:gap-5 md:grid-cols-3">
                    {pillars.map((p) => (
                        <div
                            key={p.title}
                            data-pillar-pill
                            className={`rounded-[23px] border p-6 sm:p-7 shadow-card ${p.tone}`}
                        >
                            <div className="flex items-center gap-3">
                                <span className={`flex size-9 shrink-0 items-center justify-center rounded-full text-xs font-extrabold ${p.badgeBg}`}>
                                    ✓
                                </span>
                                <h3 className={`ar-heading text-lg sm:text-xl font-bold ${p.dark ? "text-[#FAF6F0]" : "text-ink"}`}>{p.title}</h3>
                            </div>
                            <p className={`ar-body mt-3.5 text-sm sm:text-base font-medium leading-[1.8] ${p.dark ? "text-[#FAF6F0]/85" : "text-ink-2"}`}>
                                {p.desc}
                            </p>
                        </div>
                    ))}
                </div>

                {/* The 3 AI Models Grid */}
                <div className="mt-18 sm:mt-24">
                    <div className="flex flex-col items-start justify-between gap-4 border-b border-rule pb-6 md:flex-row md:items-end">
                        <div>
                            <Eyebrow className="text-pen">
                                {l("كيف تعمل المنصة من الداخل؟", "How does the platform work under the hood?")}
                            </Eyebrow>
                            <h3 className={`${H2} mt-2 text-ink`}>
                                {l("3 موديلات ذكاء اصطناعي بتشتغل في نفس اللحظة.", "3 Specialized AI Models Running Simultaneously.")}
                            </h3>
                        </div>
                    </div>

                    <div data-models-grid className="mt-8 sm:mt-10 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
                        {models.map((m, idx) => (
                            <article
                                key={m.num}
                                data-model-card
                                className={`relative flex flex-col justify-between overflow-hidden rounded-[24px] p-6 sm:p-8 lg:p-9 ${m.surface} ${idx === 2 ? "md:col-span-2 lg:col-span-1" : ""}`}
                            >
                                <div className="relative z-10">
                                    <div className="flex items-center justify-between gap-3">
                                        <span className="text-sm font-bold opacity-80">
                                            {m.badge}
                                        </span>
                                        <span className="wb-num text-3xl sm:text-4xl font-extrabold">
                                            {m.weight}
                                        </span>
                                    </div>

                                    <div className="mt-5 sm:mt-6 flex items-center gap-4">
                                        <span className={`flex size-12 sm:size-14 shrink-0 items-center justify-center rounded-2xl ${m.iconTone}`}>
                                            <m.icon className="size-6 sm:size-7" aria-hidden />
                                        </span>
                                        <div>
                                            <span className="block text-xs font-bold opacity-75">{m.weightLabel}</span>
                                            <h4 className="ar-heading mt-0.5 font-display text-xl sm:text-2xl font-bold">
                                                {m.title}
                                            </h4>
                                        </div>
                                    </div>

                                    <p className="ar-body mt-4 sm:mt-5 text-sm sm:text-base font-medium leading-[1.82] opacity-90">
                                        {m.body}
                                    </p>
                                </div>

                                <ul className="relative z-10 mt-6 sm:mt-7 space-y-2.5 border-t border-current/15 pt-5">
                                    {m.points.map((pt) => (
                                        <li key={pt} className="flex items-start gap-2.5 text-sm font-bold">
                                            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[#E3A458]" aria-hidden />
                                            <span>{pt}</span>
                                        </li>
                                    ))}
                                </ul>
                            </article>
                        ))}
                    </div>
                </div>

                {/* Anti-Cheating & Online Quiz Guarantee Banner */}
                <div className="wb-mocha-stage mt-12 sm:mt-14 rounded-[26px] border border-[#FAF6F0]/15 p-6 sm:p-8 text-[#FAF6F0] shadow-float lg:p-11">
                    <div className="grid items-center gap-6 sm:gap-8 lg:grid-cols-12">
                        <div className="lg:col-span-8">
                            <h3 className="ar-heading font-display text-xl font-bold text-[#FAF6F0] sm:text-3xl">
                                {l(
                                    "ليه الطالب مستحيل يغش في كويز OralIQ؟",
                                    "Why is it impossible for a student to cheat in an OralIQ quiz?",
                                )}
                            </h3>
                            <p className="ar-body mt-3 text-sm sm:text-base font-medium leading-[1.85] text-[#FAF6F0]/85">
                                {l(
                                    "السؤال مش بيظهر غير لما الكاميرا تتأكد من وجه الطالب، وأول ما السؤال يظهر الطالب بيجاوب بصوته فوراً وعينه قدام الكاميرا. مفيش وقت يدور في ورق ولا شات جي بي تي، ولو بص بعيد أو حد همس جنبه، النظام بيسجل المخالفة بالثانية في تقرير الدكتور.",
                                    "The question only appears once the camera verifies the student's face, and as soon as it appears, the student answers aloud while looking at the camera. There's no time to search notes or ChatGPT, and any gaze shift or whisper is timestamped in the lecturer's report.",
                                )}
                            </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 lg:col-span-4 lg:justify-end">
                            <Link to={startHref} viewTransition className={`${BTN} w-full sm:w-auto justify-center ps-7 pe-3`}>
                                <span>{l("جرّب إنشاء كويز شفوي", "Create an oral quiz now")}</span>
                                <span className="flex size-8 items-center justify-center rounded-full bg-white/15 text-white">
                                    <ArrowUpLeft className="size-4 ltr:rotate-90" aria-hidden />
                                </span>
                            </Link>
                            <a href="#how" className={`${BTN_GHOST} w-full sm:w-auto justify-center`}>
                                {l("شوف الخطوات", "See the steps")}
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </Section>
    );
}
