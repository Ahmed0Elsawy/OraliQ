import { useRef } from "react";
import { FileText, Mic, Send, Sparkles } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { Eyebrow, H2, Section } from "./ui";

/**
 * Section 2 (#how): Steps — Sticky Stacking Method Cards on Desktop, Clean Vertical Stack on Mobile/Tablet
 * Surfaces: Warm Off-White (#FAF6F0), Warm Cream (#EFE7DE), Soft Sand (#E6DDD0), and Mocha Espresso (.wb-mocha-stage)
 */
export function HomeSteps() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-steps-line]",
                { scaleY: 0, transformOrigin: "top center" },
                {
                    scaleY: 1,
                    ease: "none",
                    scrollTrigger: {
                        trigger: "[data-steps-track]",
                        start: "top 72%",
                        end: "bottom 68%",
                        scrub: 0.4,
                    },
                },
            );

            const cards = gsap.utils.toArray<HTMLElement>("[data-step-card]");
            cards.forEach((card, i) => {
                gsap.fromTo(
                    card,
                    { y: 40, opacity: 0 },
                    {
                        y: 0,
                        opacity: 1,
                        duration: 0.7,
                        ease: "power3.out",
                        scrollTrigger: { trigger: card, start: "top 86%" },
                    },
                );

                if (i < cards.length - 1) {
                    gsap.to(card, {
                        scale: 0.965,
                        ease: "none",
                        scrollTrigger: {
                            trigger: cards[i + 1],
                            start: "top 75%",
                            end: "top 28%",
                            scrub: true,
                        },
                    });
                }
            });
        });
    }, { scope: root, dependencies: [lang] });

    const steps = [
        {
            num: "01",
            icon: FileText,
            surface: "bg-[#FAF6F0] text-[#1C1410] border border-white/20",
            iconTone: "bg-[#6F4E37] text-[#FAF6F0]",
            numColor: "text-[#6F4E37]/25",
            tag: l("خطوة الدكتور • دقيقة واحدة", "Lecturer Step • 1 Minute"),
            title: l("ضيف الأسئلة والإجابة النموذجية", "Add Questions & Model Answers"),
            body: l(
                "اكتب أسئلة الكويز الشفوي وحدد الإجابة النموذجية والنقاط الأساسية ووقت كل سؤال ودرجته، أو ارفع بنك الأسئلة جاهز.",
                "Write your oral quiz questions, specify the model answer, key rubric points, and time limit per question.",
            ),
        },
        {
            num: "02",
            icon: Send,
            surface: "bg-[#EFE7DE] text-[#1C1410] border border-white/25",
            iconTone: "bg-[#38291F] text-[#FAF6F0]",
            numColor: "text-[#38291F]/25",
            tag: l("مشاركة فورية • كويز أونلاين", "Instant Share • Online Quiz"),
            title: l("ابعت لينك الكويز للدفعة زي أي كويز عادي", "Share the Quiz Link With Your Cohort"),
            body: l(
                "انسخ لينك الكويز وابعته للطلاب على جروب الدفعة أو المنصة التعليمية؛ الطلاب كلها تقدر تدخل تمتحن في نفس الوقت من غير طوابير.",
                "Copy the quiz link and share it with your class; hundreds of students can sit the oral exam simultaneously with zero queues.",
            ),
        },
        {
            num: "03",
            icon: Mic,
            surface: "bg-[#E5DACB] text-[#1C1410] border border-white/30",
            iconTone: "bg-[#6F4E37] text-[#FAF6F0]",
            numColor: "text-[#6F4E37]/25",
            tag: l("خطوة الطالب • رقابة حيوية بـ 478 نقطة", "Student Step • 478-Point Live Proctoring"),
            title: l("الطالب يفتح الكاميرا ويجاوب بصوته بدون غش", "Students Open Camera & Answer Aloud With Zero Cheating"),
            body: l(
                "الطالب يسجل بصمة الوجه والصوت في ثواني، ولما السؤال يظهر يجاوب بصوته والموديلات الثلاثة بتتابع حركة عينه وتفرّغ كلامه لحظياً.",
                "Students verify their face and voiceprint in seconds, then answer aloud on camera while the 3 AI models track eye gaze and transcribe speech live.",
            ),
        },
        {
            num: "04",
            icon: Sparkles,
            surface: "wb-mocha-stage text-[#FAF6F0] border border-[#FAF6F0]/20",
            iconTone: "bg-[#E3A458] text-[#18110D]",
            numColor: "text-[#E3A458]/35",
            tag: l("النتيجة الفورية • بدون تدخل الدكتور", "Instant Result • Zero Manual Grading"),
            title: l("استلم الدرجات متصححة بالمعنى ومعاها التبرير", "Receive Graded Scores & Detailed AI Explanations"),
            body: l(
                "توصلك لوحة نتائج كاملة فيها درجة كل طالب (80% معنى + 10% طلاقة + 10% نزاهة)، النص المكتوب لإجابته، وسبب كل درجة جاهز للاعتماد أو التصدير.",
                "Get a complete results sheet with every student's score (80% meaning + 10% fluency + 10% integrity), transcript, and AI reasoning ready to publish or export.",
            ),
        },
    ];

    return (
        <Section
            id="how"
            tone="b"
            className="wb-dark-stage rounded-[24px] sm:rounded-[30px] mx-2 sm:mx-4 py-16 sm:py-24 lg:py-32"
        >
            <div ref={root} className="mx-auto grid max-w-[92rem] grid-cols-1 gap-10 px-5 sm:px-10 lg:grid-cols-12 lg:gap-16 lg:px-14">
                {/* Sticky Header Column on Desktop */}
                <div className="lg:col-span-5 lg:sticky lg:top-28 lg:self-start">
                    <Eyebrow className="text-[#E3A458]">{l("خطوات العمل", "How It Works")}</Eyebrow>
                    <h2 className={`${H2} mt-3 text-[#FAF6F0]`}>
                        {l("أربع خطوات بسيطة،", "Four Simple Steps,")}
                        <span className="mt-1.5 block text-[#E3A458]">
                            {l("والكويز الشفوي يشتغل لوحده.", "And Your Oral Quiz Runs Automatically.")}
                        </span>
                    </h2>
                    <p className="ar-body mt-5 sm:mt-6 text-base sm:text-lg font-medium leading-[1.85] text-[#FAF6F0]/80">
                        {l(
                            "من غير لجان ولا طوابير ولا تصحيح يدوي بالساعات. الطالب بيفتح اللينك من موبايله أو اللابتوب مباشرة بدون تحميل أي برنامج.",
                            "No panels, no waiting lines, and no hours of manual grading. Students open the link directly on their phone or laptop browser with zero installs.",
                        )}
                    </p>

                    {/* Scrubbed Progress Spine Indicator */}
                    <div className="mt-6 lg:mt-10 flex items-center gap-4">
                        <div className="h-16 lg:h-28 w-1.5 overflow-hidden rounded-full bg-white/15">
                            <div
                                data-steps-line
                                className="h-full w-full rounded-full bg-gradient-to-b from-[#E3A458] to-[#FAF6F0]"
                            />
                        </div>
                        <div className="text-xs font-bold text-[#FAF6F0]/75">
                            <span className="wb-num block text-base text-[#E3A458]">01 → 04</span>
                            <span>{l("اسكرول لاستعراض مراحل الكويز الشفوي", "Scroll through the 4 automated stages")}</span>
                        </div>
                    </div>
                </div>

                {/* Method Cards Column — Sticky Stacking on Mobile, Tablet & Desktop */}
                <div data-steps-track className="relative lg:col-span-7">
                    <ol className="relative space-y-5 sm:space-y-7">
                        {steps.map((s, idx) => (
                            <li
                                key={s.num}
                                style={{ top: `${78 + idx * 14}px` }}
                                className="sticky"
                            >
                                <div
                                    data-step-card
                                    className={`relative overflow-hidden rounded-[22px] sm:rounded-[24px] p-6 sm:p-9 shadow-[0_26px_60px_-18px_rgba(0,0,0,0.45)] ${s.surface}`}
                                >
                                    <div className="relative z-10 grid items-center gap-4 sm:gap-6 sm:grid-cols-[1fr_auto]">
                                        <div>
                                            <div className="flex items-center justify-between sm:justify-start gap-3">
                                                <div className="flex items-center gap-3">
                                                    <span className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${s.iconTone}`}>
                                                        <s.icon className="size-5" aria-hidden />
                                                    </span>
                                                    <span className="text-xs font-bold opacity-85">
                                                        {s.tag}
                                                    </span>
                                                </div>
                                                <span className={`wb-num text-2xl font-extrabold sm:hidden ${s.numColor}`}>
                                                    {s.num}
                                                </span>
                                            </div>
                                            <h3 className="ar-heading mt-4 font-display text-xl font-bold sm:text-3xl">
                                                {s.title}
                                            </h3>
                                            <p className="ar-body mt-2.5 sm:mt-3 text-sm sm:text-lg font-medium leading-[1.82] opacity-85">
                                                {s.body}
                                            </p>
                                        </div>

                                        {/* Step Number on Tablet/Desktop Side */}
                                        <div
                                            aria-hidden
                                            className={`wb-num hidden sm:block text-[4.5rem] lg:text-[6.5rem] font-extrabold leading-none sm:ps-4 ${s.numColor}`}
                                        >
                                            {s.num}
                                        </div>
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ol>
                </div>
            </div>
        </Section>
    );
}
