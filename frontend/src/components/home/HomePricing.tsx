import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpLeft, Check, Crown, Layers, Users, Zap } from "lucide-react";
import { useI18n } from "../../i18n";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import { Eyebrow, H2, Section } from "./ui";

/**
 * Section (#pricing): Subscription Plans
 * - Plans (mirror backend app/core/plans.py): Free 0 / Basic 199 / Professional 599 EGP per month / Enterprise per contract.
 * - Limits: exams per month, questions per exam, answer duration, distinct students per month.
 * - Matches the Warm Espresso Brown (#6F4E37 / #1E140F), Warm Off-White (#FAF6F0), and Caramel Gold (#E3A458) identity.
 */
export function HomePricing({ startHref }: { startHref: string }) {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);
    const [currency, setCurrency] = useState<"EGP" | "USD">("EGP");
    const [billingCycle, setBillingCycle] = useState<"monthly" | "term" | "yearly">("monthly");

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-price-card]",
                { y: 38, opacity: 0, scale: 0.97 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: 0.7,
                    stagger: 0.1,
                    ease: "power3.out",
                    scrollTrigger: {
                        trigger: "[data-price-grid]",
                        start: "top 82%",
                    },
                },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const plans = [
        {
            id: "free",
            badge: l("مجاناً للتجربة", "Free Trial"),
            name: l("الباقة المجانية", "Free"),
            desc: l(
                "جرّب المنصة بنفسك مع طلابك قبل ما تشترك.",
                "Try the platform with your students before subscribing.",
            ),
            priceEgp: 0,
            priceUsd: 0,
            maxExams: l("5 امتحانات (مرة واحدة)", "5 exams (one-time)"),
            maxStudents: l("50 طالب في نفس الوقت", "50 students at once"),
            maxDuration: l("دقيقتين / إجابة", "2 min / answer"),
            queueTier: l("طابور معالجة عادي", "Standard AI Queue"),
            featured: false,
            dark: false,
            features: [
                l("5 امتحانات تجريبية (حتى 3 أسئلة للامتحان)", "5 trial exams (up to 3 questions each)"),
                l("50 طالب يمتحنوا في نفس الوقت", "50 students taking an exam at once"),
                l("تصحيح تلقائي بالمعنى + تفريغ صوتي عربي وإنجليزي", "Semantic AI grading + Arabic & English speech-to-text"),
                l("مراقبة حيوية بـ 478 نقطة للوجه والعين والصوت", "478-point face, eye-gaze & voiceprint anti-cheat"),
            ],
        },
        {
            id: "pro",
            badge: l("للمدرسين", "For Teachers"),
            name: l("الباقة الأساسية", "Basic"),
            desc: l(
                "للمدرس اللي بيعمل كويز شفوي أسبوعي لطلابه — 150 طالب في نفس الوقت.",
                "For teachers running weekly oral quizzes — 150 students at once.",
            ),
            priceEgp: 199,
            priceUsd: 4,
            maxExams: l("15 امتحان / شهرياً", "15 exams / month"),
            maxStudents: l("150 طالب في نفس الوقت", "150 students at once"),
            maxDuration: l("5 دقائق / إجابة", "5 min / answer"),
            queueTier: l("أولوية معالجة سريعة", "Fast Priority AI Queue"),
            featured: false,
            dark: false,
            features: [
                l("15 امتحان شهرياً (حتى 5 أسئلة للامتحان)", "15 exams/month (up to 5 questions each)"),
                l("150 طالب يمتحنوا في نفس الوقت (عدد الطلاب الكلي مفتوح)", "150 students at once (unlimited total students)"),
                l("أولوية سريعة في طابور التصحيح", "Fast priority in the AI grading queue"),
                l("+10 امتحانات إضافية بـ 79 ج.م (ما بتنتهيش)", "+10 extra exams for 79 EGP (never expire)"),
            ],
        },
        {
            id: "campus",
            badge: l("الأكثر طلباً للدكاترة والسناتر", "Most Popular"),
            name: l("الباقة الاحترافية", "Professional"),
            desc: l(
                "للدكاترة والسناتر وأصحاب الأعداد الكبيرة — 500 طالب في نفس الوقت و3 مساعدين.",
                "For lecturers & centers with large cohorts — 500 students at once and 3 assistants.",
            ),
            priceEgp: 599,
            priceUsd: 12,
            maxExams: l("30 امتحان / شهرياً", "30 exams / month"),
            maxStudents: l("500 طالب في نفس الوقت", "500 students at once"),
            maxDuration: l("10 دقائق / إجابة", "10 min / answer"),
            queueTier: l("أولوية قصوى (VIP)", "VIP AI Queue"),
            featured: true,
            dark: true,
            features: [
                l("30 امتحان شهرياً (حتى 15 سؤال للامتحان)", "30 exams/month (up to 15 questions each)"),
                l("500 طالب يمتحنوا في نفس الوقت (عدد الطلاب الكلي مفتوح)", "500 students at once (unlimited total students)"),
                l("3 حسابات مساعدين (معيدين / مدرسين في السنتر)", "3 assistant accounts (TAs / center teachers)"),
                l("أولوية قصوى وقت الذروة + تحليلات متقدمة", "VIP peak-time priority + advanced analytics"),
            ],
        },
        {
            id: "enterprise",
            badge: l("مدارس وجامعات", "Schools & Universities"),
            name: l("باقة المؤسسات", "Enterprise"),
            desc: l(
                "للمدارس والجامعات والمعاهد — سعر بالطالب وحدود حسب حجم مؤسستك.",
                "For schools, universities and institutes — priced per student, sized to you.",
            ),
            priceEgp: -1,
            priceUsd: -1,
            maxExams: l("حسب الاتفاق", "Custom"),
            maxStudents: l("أكتر من 500 طالب", "500+ students"),
            maxDuration: l("15 دقيقة / إجابة", "15 min / answer"),
            queueTier: l("معالجة فورية", "Instant AI"),
            featured: false,
            dark: false,
            features: [
                l("30 ج.م للطالب في الترم (حد أدنى 150 طالب)", "30 EGP per student per term (min. 150 students)"),
                l("حتى 20 سؤال للامتحان ومدرسين غير محدود", "Up to 20 questions per exam, unlimited teachers"),
                l("لوحة تحكم للمؤسسة وتقارير شاملة", "Institution dashboard & reports"),
                l("فاتورة رسمية + إمكانية الربط عبر API / LTI", "Official invoicing + optional API / LTI integration"),
            ],
        },
    ];

    // Term = 4 months for the price of 3; Year = 12 months for the price of 10.
    const cycleMultiplier = { monthly: 1, term: 3, yearly: 10 } as const;
    const cycleLabel = {
        monthly: l("شهرياً", "month"),
        term: l("الترم (4 شهور)", "term (4 months)"),
        yearly: l("سنوياً", "year"),
    } as const;

    const formatPrice = (egp: number, usd: number) => {
        if (egp < 0) return l("تواصل معنا", "Contact us");
        if (egp === 0) return l("مجاناً", "Free");
        const factor = cycleMultiplier[billingCycle];
        if (currency === "EGP") {
            const val = egp * factor;
            return `${val.toLocaleString(lang === "ar" ? "ar-EG" : "en-US")} ${l("ج.م", "EGP")}`;
        }
        return `$${usd * factor}`;
    };

    return (
        <Section id="pricing" tone="a" className="py-16 sm:py-24 lg:py-32">
            <div ref={root} className="mx-auto max-w-[92rem] px-4 sm:px-8 lg:px-12">
                {/* Header & Controls */}
                <div className="flex flex-col items-center text-center">
                    <Eyebrow>{l("خطط الاشتراك والأسعار", "Subscription Plans")}</Eyebrow>
                    <h2 className={`${H2} mt-2 max-w-3xl text-ink`}>
                        {l(
                            "باقة على قد احتياجك — من مدرس لحد جامعة.",
                            "A plan that fits you — from a single teacher to a whole university.",
                        )}
                    </h2>
                    <p className="mt-4 max-w-2xl text-base sm:text-lg font-medium text-ink-2 leading-relaxed">
                        {l(
                            "اختار الباقة حسب عدد طلابك وامتحاناتك في الشهر. الامتحان الواحد ممكن يكون فيه أكتر من سؤال، ونفس الامتحان يتبعت لكل مجموعاتك ويتحسب مرة واحدة.",
                            "Pick a plan by how many students and exams you have per month. One exam can hold several questions, and the same exam can be sent to all your groups while counting once.",
                        )}
                    </p>

                    {/* Currency & Cycle Switchers */}
                    <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
                        <div className="inline-flex items-center rounded-full border border-rule bg-sheet p-1 shadow-xs">
                            {([
                                { id: "monthly", label: l("شهري", "Monthly"), tag: null },
                                { id: "term", label: l("ترم (4 شهور)", "Term (4 mo)"), tag: l("شهر مجاناً", "1 mo free") },
                                { id: "yearly", label: l("سنوي", "Yearly"), tag: l("شهرين مجاناً", "2 mo free") },
                            ] as const).map((c) => (
                                <button
                                    key={c.id}
                                    type="button"
                                    onClick={() => setBillingCycle(c.id)}
                                    className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-2 text-xs sm:text-sm font-bold transition-all ${
                                        billingCycle === c.id
                                            ? "bg-[#6F4E37] text-[#FAF6F0] shadow-xs"
                                            : "text-ink-2 hover:text-ink"
                                    }`}
                                >
                                    <span>{c.label}</span>
                                    {c.tag && (
                                        <span className="rounded-full bg-[#E3A458] px-2 py-0.5 text-[10px] font-extrabold text-[#18110D]">
                                            {c.tag}
                                        </span>
                                    )}
                                </button>
                            ))}
                        </div>

                        <div className="inline-flex items-center rounded-full border border-rule bg-sheet p-1 shadow-xs">
                            <button
                                type="button"
                                onClick={() => setCurrency("EGP")}
                                className={`wb-num rounded-full px-3.5 py-2 text-xs font-extrabold transition-all ${
                                    currency === "EGP" ? "bg-ink text-paper" : "text-ink-2 hover:text-ink"
                                }`}
                            >
                                EGP (ج.م)
                            </button>
                            <button
                                type="button"
                                onClick={() => setCurrency("USD")}
                                className={`wb-num rounded-full px-3.5 py-2 text-xs font-extrabold transition-all ${
                                    currency === "USD" ? "bg-ink text-paper" : "text-ink-2 hover:text-ink"
                                }`}
                            >
                                USD ($)
                            </button>
                        </div>
                    </div>
                </div>

                {/* 4 Pricing Cards Grid */}
                <div
                    data-price-grid
                    className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4"
                >
                    {plans.map((p) => (
                        <article
                            key={p.id}
                            data-price-card
                            className={`relative flex flex-col justify-between rounded-[26px] p-6 sm:p-7 transition-transform duration-300 hover:-translate-y-1 ${
                                p.dark
                                    ? "wb-mocha-stage border-2 border-[#E3A458]/60 text-[#FAF6F0] shadow-[0_28px_70px_-20px_rgba(30,20,15,0.65)]"
                                    : "border border-rule bg-sheet text-ink shadow-card"
                            }`}
                        >
                            <div>
                                {/* Top Badge & Title */}
                                <div className="flex items-center justify-between gap-2">
                                    <span
                                        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
                                            p.dark
                                                ? "bg-[#E3A458] text-[#18110D]"
                                                : "border border-rule bg-sheet-2 text-pen"
                                        }`}
                                    >
                                        {p.featured && <Crown className="size-3.5" aria-hidden />}
                                        {p.badge}
                                    </span>
                                    <span className={`wb-num text-xs font-extrabold uppercase tracking-wider ${p.dark ? "text-[#FAF6F0]/60" : "text-ink-3"}`}>
                                        {p.id}
                                    </span>
                                </div>

                                <h3 className="ar-heading mt-4 font-display text-2xl font-bold">
                                    {p.name}
                                </h3>
                                <p className={`ar-body mt-2 text-sm leading-relaxed ${p.dark ? "text-[#FAF6F0]/80" : "text-ink-2"}`}>
                                    {p.desc}
                                </p>

                                {/* Price Display */}
                                <div className="mt-5 flex items-baseline gap-1.5 border-b border-current/12 pb-5">
                                    <span className="wb-num text-3xl sm:text-4xl font-extrabold tracking-tight">
                                        {formatPrice(p.priceEgp, p.priceUsd)}
                                    </span>
                                    {p.priceEgp > 0 && (
                                        <span className={`text-xs font-bold ${p.dark ? "text-[#FAF6F0]/70" : "text-ink-3"}`}>
                                            / {cycleLabel[billingCycle]}
                                        </span>
                                    )}
                                </div>

                                {/* Key Capacity Limits Pills (Exams + Unlimited Students + AI Queue) */}
                                <div className="mt-5 grid grid-cols-2 gap-2.5">
                                    <div className={`rounded-2xl p-3 ${p.dark ? "bg-black/25 border border-white/10" : "bg-sheet-2 border border-rule"}`}>
                                        <div className="flex items-center gap-1.5 text-[11px] font-bold opacity-75">
                                            <Layers className="size-3.5 text-[#E3A458]" aria-hidden />
                                            <span>{l("عدد الامتحانات", "Exams Quota")}</span>
                                        </div>
                                        <p className="mt-1 text-sm font-extrabold">{p.maxExams}</p>
                                    </div>
                                    <div className={`rounded-2xl p-3 ${p.dark ? "bg-black/25 border border-white/10" : "bg-sheet-2 border border-rule"}`}>
                                        <div className="flex items-center gap-1.5 text-[11px] font-bold opacity-75">
                                            <Users className="size-3.5 text-[#E3A458]" aria-hidden />
                                            <span>{l("عدد الطلاب", "Students")}</span>
                                        </div>
                                        <p className="mt-1 text-xs sm:text-sm font-extrabold">{p.maxStudents}</p>
                                    </div>
                                </div>

                                <div className={`mt-2.5 flex items-center justify-between rounded-2xl px-3.5 py-2.5 text-xs font-bold ${
                                    p.dark ? "bg-[#E3A458]/15 text-[#E3A458] border border-[#E3A458]/30" : "bg-sheet-2 text-pen border border-rule"
                                }`}>
                                    <span className="inline-flex items-center gap-1.5">
                                        <Zap className="size-3.5 shrink-0" aria-hidden />
                                        {p.queueTier}
                                    </span>
                                    <span className="wb-num opacity-80">{p.maxDuration}</span>
                                </div>

                                {/* Features List */}
                                <ul className="mt-5 space-y-2.5">
                                    {p.features.map((f) => (
                                        <li key={f} className="flex items-start gap-2.5 text-xs sm:text-sm font-medium leading-relaxed">
                                            <span className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full ${
                                                p.dark ? "bg-[#E3A458] text-[#18110D]" : "bg-[#6F4E37]/15 text-[#6F4E37]"
                                            }`}>
                                                <Check className="size-3 stroke-[2.6]" aria-hidden />
                                            </span>
                                            <span className={p.dark ? "text-[#FAF6F0]/90" : "text-ink-2"}>{f}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>

                            {/* CTA Button */}
                            <div className="mt-7 pt-2">
                                <Link
                                    to={p.priceEgp < 0 ? "#contact" : startHref}
                                    className={`inline-flex h-12 w-full items-center justify-between rounded-full ps-5 pe-2 text-sm font-bold transition-all ${
                                        p.dark
                                            ? "bg-[#FAF6F0] text-[#18110D] hover:bg-[#E3A458]"
                                            : "oiq-btn-mint text-[#FAF6F0]"
                                    }`}
                                >
                                    <span>
                                        {p.priceEgp === 0
                                            ? l("ابدأ الباقة المجانية الآن", "Start Free Now")
                                            : p.priceEgp < 0
                                                ? l("تواصل معنا", "Contact sales")
                                                : l("اشترك الآن في الباقة", "Choose this plan")}
                                    </span>
                                    <span className={`flex size-8 items-center justify-center rounded-full ${
                                        p.dark ? "bg-[#18110D]/10 text-[#18110D]" : "bg-white/15 text-white"
                                    }`}>
                                        <ArrowUpLeft className="size-4 ltr:rotate-90" aria-hidden />
                                    </span>
                                </Link>
                            </div>
                        </article>
                    ))}
                </div>
            </div>
        </Section>
    );
}
