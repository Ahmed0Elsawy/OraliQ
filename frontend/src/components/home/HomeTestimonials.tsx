import { useRef } from "react";
import { Star, Quote, CheckCircle2 } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card, CardContent } from "@/components/ui/card";
import { Marquee } from "@/components/ui/3d-testimonails";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { Eyebrow, H2, Section } from "./ui";

interface ReviewItem {
    name: string;
    role: string;
    institution: string;
    initials: string;
    body: string;
    tone: "light" | "mocha" | "cream";
}

function TestimonialCard({ name, role, institution, initials, body, tone }: ReviewItem) {
    const isMocha = tone === "mocha";
    const isCream = tone === "cream";

    return (
        <Card
            className={
                isMocha
                    ? "w-[13.25rem] sm:w-64 lg:w-72 wb-mocha-stage border-[#FAF6F0]/20 text-[#FAF6F0] shadow-float"
                    : isCream
                        ? "w-[13.25rem] sm:w-64 lg:w-72 bg-[#EFE7DE] border-[#6F4E37]/20 text-[#1C1410] shadow-card"
                        : "w-[13.25rem] sm:w-64 lg:w-72 bg-[#FAF6F0] border-[#6F4E37]/15 text-[#1C1410] shadow-card"
            }
        >
            <CardContent className="p-4 sm:p-5">
                <div className="flex items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-0.5 text-[#E3A458]" aria-hidden>
                        <Star className="size-3.5 fill-current" />
                        <Star className="size-3.5 fill-current" />
                        <Star className="size-3.5 fill-current" />
                        <Star className="size-3.5 fill-current" />
                        <Star className="size-3.5 fill-current" />
                    </div>
                    <Quote className={isMocha ? "size-4 text-[#E3A458]/60" : "size-4 text-[#6F4E37]/40"} aria-hidden />
                </div>

                <blockquote
                    className={`ar-body text-xs sm:text-sm font-medium leading-[1.75] ${
                        isMocha ? "text-[#FAF6F0]/90" : "text-[#1C1410]/85"
                    }`}
                >
                    «{body}»
                </blockquote>

                <div className={`mt-4 flex items-center gap-3 border-t pt-3.5 ${isMocha ? "border-[#FAF6F0]/15" : "border-[#1C1410]/10"}`}>
                    <Avatar className="size-9">
                        <AvatarFallback
                            className={
                                isMocha
                                    ? "bg-[#E3A458] text-[#18110D] font-extrabold text-xs"
                                    : "bg-[#6F4E37] text-[#FAF6F0] font-extrabold text-xs"
                            }
                        >
                            {initials}
                        </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                        <figcaption
                            className={`ar-heading truncate text-xs sm:text-sm font-bold flex items-center gap-1.5 ${
                                isMocha ? "text-[#FAF6F0]" : "text-[#1C1410]"
                            }`}
                        >
                            <span className="truncate">{name}</span>
                            <CheckCircle2 className="size-3.5 shrink-0 text-[#E3A458]" aria-hidden />
                        </figcaption>
                        <p className={`truncate text-[11px] font-bold ${isMocha ? "text-[#E3A458]" : "text-[#6F4E37]"}`}>
                            {role} • {institution}
                        </p>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

/**
 * 3D Testimonials Section (Placed right before Contact section)
 * Integrates the 3D Vertical Marquee component styled with our Warm Espresso Brown & Off-White design system.
 */
export function HomeTestimonials() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-testi-head]",
                { y: 28, opacity: 0 },
                {
                    y: 0,
                    opacity: 1,
                    duration: 0.7,
                    stagger: 0.1,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-testi-wrap]", start: "top 82%" },
                },
            );
            gsap.fromTo(
                "[data-testi-stage]",
                { y: 36, opacity: 0, scale: 0.96 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.85,
                    ease: "power3.out",
                    scrollTrigger: { trigger: "[data-testi-stage]", start: "top 84%" },
                },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const testimonials: ReviewItem[] = [
        {
            name: l("أ.د. طارق المنشاوي", "Prof. Tarek El-Menshawy"),
            role: l("أستاذ هندسة الحاسبات", "Professor of Computer Engineering"),
            institution: l("جامعة القاهرة", "Cairo University"),
            initials: l("طم", "TM"),
            body: l(
                "امتحنّا 650 طالب شفوي في ساعتين بدل أسبوعين لجان! التصحيح بالمعنى دقيق جداً وبيفهم الطالب اللي فاهم حتى لو شرح بأسلوبه.",
                "We assessed 650 students orally in 2 hours instead of 2 weeks of panels! The semantic grading understands students even in their own words.",
            ),
            tone: "mocha",
        },
        {
            name: l("د. سلمى عبد الرحمن", "Dr. Salma Abdelrahman"),
            role: l("مدرس الذكاء الاصطناعي", "AI Lecturer"),
            institution: l("جامعة عين شمس", "Ain Shams University"),
            initials: l("سع", "SA"),
            body: l(
                "تتبع حركة العين بـ 478 نقطة مع بصمة الصوت قضى تماماً على أي محاولة غش أو قراءة من شاشة تانية أثناء الكويز الشفوي.",
                "478-point eye-gaze tracking with voiceprint matching completely eliminated cheating or reading from secondary screens.",
            ),
            tone: "light",
        },
        {
            name: l("د. كريم الشافعي", "Dr. Karim El-Shafei"),
            role: l("منسق المقررات العملية", "Practical Courses Coordinator"),
            institution: l("جامعة الإسكندرية", "Alexandria University"),
            initials: l("كش", "KS"),
            body: l(
                "الكويز الشفوي بقى أونلاين بجد زي أي كويز عادي؛ ببعت اللينك على جروب الدفعة والدرجات بتوصلني متصححة ومعاها سبب كل درجة.",
                "Oral quizzes are now genuinely online like any regular quiz; I share the link and receive graded scores with detailed AI reasoning.",
            ),
            tone: "cream",
        },
        {
            name: l("أ. نادية الكيلاني", "Ms. Nadia El-Kilany"),
            role: l("مديرة قسم اللغات", "Head of Languages"),
            institution: l("مدارس STEM الدولية", "STEM International Schools"),
            initials: l("نك", "NK"),
            body: l(
                "دمجنا OralIQ كـ فيتشر جوه منصة المدرسة، وبقينا نقيس طلاقة التحدث والنطق للطلاب كل أسبوع من غير أي عبء إضافي على المدرسين.",
                "We embedded OralIQ inside our school portal and now evaluate speaking fluency weekly with zero extra workload on teachers.",
            ),
            tone: "light",
        },
        {
            name: l("م. زياد نصار", "Eng. Ziad Nassar"),
            role: l("مؤسس منصة تعليمية", "EdTech Founder"),
            institution: l("أكاديمية مسار", "Masar Academy"),
            initials: l("زن", "ZN"),
            body: l(
                "إضافة الامتحان الشفوي بالذكاء الاصطناعي قبل إصدار الشهادة رفعت مصداقية شهاداتنا عند الشركات بنسبة 100%.",
                "Adding AI oral exams before certificate issuance boosted our credential credibility with employers by 100%.",
            ),
            tone: "mocha",
        },
        {
            name: l("أ.د. هاني الجندي", "Prof. Hany El-Gendy"),
            role: l("وكيل كلية الطب للتعليم", "Vice Dean for Education"),
            institution: l("جامعة المنصورة", "Mansoura University"),
            initials: l("هج", "HG"),
            body: l(
                "في امتحانات الـ Oral Clinical، النظام وفر علينا مئات الساعات وبيطلع تقرير تفصيلي لكل طالب بالنقاط اللي ذكرها واللي نسيها.",
                "In clinical oral exams, the platform saved hundreds of hours and outputs a detailed rubric report of covered and missed points.",
            ),
            tone: "cream",
        },
        {
            name: l("د. مريم فؤاد", "Dr. Mariam Fouad"),
            role: l("أستاذ مساعد البرمجيات", "Associate Professor of SE"),
            institution: l("الجامعة الألمانية GUC", "GUC Cairo"),
            initials: l("مف", "MF"),
            body: l(
                "مناقشات مشاريع التخرج والكويزات الأسبوعية بقت أسهل بكتير؛ الطالب بيجاوب بصوته براحته والتفريغ الصوتي بيلقط العربي والمصطلحات الإنجليزي بدقة.",
                "Project defenses and weekly quizzes are effortless; students speak naturally and the transcription captures Arabic & English terms accurately.",
            ),
            tone: "light",
        },
        {
            name: l("د. رانيا حجازي", "Dr. Rania Hegazy"),
            role: l("مدير التعليم الإلكتروني", "E-Learning Director"),
            institution: l("الجامعة المصرية اليابانية", "E-JUST"),
            initials: l("رح", "RH"),
            body: l(
                "الربط مع نظام Moodle تم في أقل من يوم واحد، والطلاب بيمتحنوا شفوي من المتصفح مباشرة بدون تحميل أي تطبيق.",
                "Integrating with Moodle took less than a day, and students take oral exams right in their browser with zero app installs.",
            ),
            tone: "mocha",
        },
        {
            name: l("د. وائل علام", "Dr. Wael Allam"),
            role: l("رئيس قسم نظم المعلومات", "Head of Information Systems"),
            institution: l("مدينة زويل للعلوم", "Zewail City"),
            initials: l("وع", "WA"),
            body: l(
                "تقسيم الدرجة (80% فهم المعنى + 10% طلاقة + 10% نزاهة حيوية) عادل جداً ومخلّي كل طالب ياخد حقه بالمللي.",
                "The 80% meaning + 10% fluency + 10% biometric integrity rubric is remarkably fair and gives every student their exact due.",
            ),
            tone: "cream",
        },
    ];

    const col1 = testimonials.slice(0, 5);
    const col2 = testimonials.slice(2, 7);
    const col3 = testimonials.slice(4, 9);
    const col4 = [...testimonials.slice(6, 9), ...testimonials.slice(0, 2)];

    return (
        <Section id="testimonials" tone="a" className="py-16 sm:py-24 lg:py-28">
            <div ref={root} className="mx-auto max-w-[92rem] px-4 sm:px-10 lg:px-16">
                {/* Section Header */}
                <div data-testi-wrap className="mx-auto max-w-3xl text-center mb-10 sm:mb-14">
                    <div data-testi-head>
                        <Eyebrow className="text-pen">
                            {l("آراء عملائنا وتجارب الأساتذة", "Client Reviews & Faculty Testimonials")}
                        </Eyebrow>
                    </div>
                    <h2 data-testi-head className={`${H2} mt-3 text-ink`}>
                        {l("ماذا يقول أساتذة الجامعات والمنصات التعليمية", "What University Professors & EdTech Leaders")}
                        <span className="mt-1.5 block text-pen">
                            {l("عن تجربتهم مع OralIQ؟", "Say About OralIQ.")}
                        </span>
                    </h2>
                    <p data-testi-head className="ar-body mt-4 text-base sm:text-lg font-medium leading-[1.85] text-ink-2">
                        {l(
                            "تجارب حقيقية من مدرسين، رؤساء أقسام، ومؤسسي منصات تعليمية حوّلوا الامتحانات الشفوية لكويزات ذكية أونلاين بدون تدخل يدوي.",
                            "Real feedback from professors, department heads, and EdTech founders who automated their oral exams with zero manual grading.",
                        )}
                    </p>
                </div>

                {/* 3D Vertical Marquee Stage (Styled in Warm Espresso & Off-White, Responsive on Mobile & Desktop) */}
                <div
                    data-testi-stage
                    dir="ltr"
                    style={{
                        background:
                            "radial-gradient(ellipse at 50% 45%, rgba(111, 78, 55, 0.34) 0%, transparent 68%), linear-gradient(180deg, #1E140F 0%, #140E0A 100%)",
                    }}
                    className="relative mx-auto flex h-[28rem] sm:h-[34rem] w-full max-w-[84rem] flex-row items-center justify-center overflow-hidden rounded-[22px] sm:rounded-[30px] border border-[#FAF6F0]/15 shadow-float gap-2 [perspective:420px]"
                >
                    <div
                        className="flex h-[36rem] sm:h-[42rem] flex-row items-center justify-center gap-2.5 sm:gap-5 [transform:translateX(0px)_translateY(0px)_translateZ(-45px)_rotateX(14deg)_rotateY(-7deg)_rotateZ(9deg)] sm:[transform:translateX(-40px)_translateY(0px)_translateZ(-80px)_rotateX(18deg)_rotateY(-10deg)_rotateZ(16deg)]"
                    >
                        {/* Vertical Marquee 1 (downwards) */}
                        <Marquee vertical pauseOnHover repeat={3} className="[--duration:38s] [--gap:1.1rem]">
                            {col1.map((review) => (
                                <TestimonialCard key={`c1-${review.name}`} {...review} />
                            ))}
                        </Marquee>

                        {/* Vertical Marquee 2 (upwards) */}
                        <Marquee vertical pauseOnHover reverse repeat={3} className="[--duration:42s] [--gap:1.1rem]">
                            {col2.map((review) => (
                                <TestimonialCard key={`c2-${review.name}`} {...review} />
                            ))}
                        </Marquee>

                        {/* Vertical Marquee 3 (downwards) */}
                        <Marquee vertical pauseOnHover repeat={3} className="hidden sm:flex [--duration:36s] [--gap:1.1rem]">
                            {col3.map((review) => (
                                <TestimonialCard key={`c3-${review.name}`} {...review} />
                            ))}
                        </Marquee>

                        {/* Vertical Marquee 4 (upwards) */}
                        <Marquee vertical pauseOnHover reverse repeat={3} className="hidden lg:flex [--duration:44s] [--gap:1.1rem]">
                            {col4.map((review) => (
                                <TestimonialCard key={`c4-${review.name}`} {...review} />
                            ))}
                        </Marquee>
                    </div>

                    {/* Smooth Warm Espresso Gradient Overlays for 3D Vertical Marquee */}
                    <div
                        className="pointer-events-none absolute inset-x-0 top-0 h-1/4"
                        style={{ background: "linear-gradient(to bottom, #1D130E, transparent)" }}
                        aria-hidden
                    />
                    <div
                        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/4"
                        style={{ background: "linear-gradient(to top, #140E0A, transparent)" }}
                        aria-hidden
                    />
                    <div
                        className="pointer-events-none absolute inset-y-0 left-0 w-1/5"
                        style={{ background: "linear-gradient(to right, #16100C, transparent)" }}
                        aria-hidden
                    />
                    <div
                        className="pointer-events-none absolute inset-y-0 right-0 w-1/5"
                        style={{ background: "linear-gradient(to left, #16100C, transparent)" }}
                        aria-hidden
                    />
                </div>
            </div>
        </Section>
    );
}
