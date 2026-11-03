import { useEffect, useState } from "react";
import { AlertTriangle, CalendarClock, Check, CreditCard, Crown, Layers, PlusCircle, Sparkles, Users, Wallet, X, Zap } from "lucide-react";
import api from "../lib/api";
import { loadSandboxMode, sandboxHelp } from "../lib/paymentMode";
import { useI18n } from "../i18n";

/**
 * Lecturer subscription bar + upgrade modal.
 * All limits come from the backend (app/core/plans.py + services/billing_service.py):
 *   exams (lifetime trial on Free, monthly on paid), questions/exam, answer duration,
 *   distinct students, add-on exam packs, plan expiry and billing period.
 */

export interface PlanInfo {
    id: string;
    name_ar: string;
    name_en: string;
    price_usd: number | null;
    price_egp: number | null;
    purchasable?: boolean;
    exams_reset?: "lifetime" | "monthly";
    max_exams: number;
    max_questions_per_exam: number;
    max_students?: number;
    max_students_per_exam: number;
    max_duration_minutes: number;
    assistant_seats?: number;
    addon_price_egp?: number | null;
    addon_price_usd?: number | null;
    price_per_student_term_egp?: number;
    queue_priority: number;
    queue_label_ar: string;
    queue_label_en: string;
    period_prices?: Record<Period, { EGP: number | null; USD: number | null }> | null;
}

export interface BillingStatusResponse {
    plan: PlanInfo;
    plan_tier: string;
    plan_period?: string | null;
    plan_updated_at?: string | null;
    plan_expires_at?: string | null;
    is_team_member?: boolean;
    billing_owner?: { id: number; email: string } | null;
    usage: {
        exams_used: number;
        exams_limit: number;
        exams_remaining: number;
        exams_quota_type?: "lifetime" | "monthly";
        bonus_exams?: number;
        cycle_resets_at?: string | null;
        students_used?: number;
        students_limit?: number;
        max_students_per_exam: number;
        max_questions_per_exam: number;
        max_duration_minutes: number;
        assistant_seats?: number;
        peak_students_in_single_exam: number;
        total_submissions: number;
        exam_student_counts: Record<string, number>;
    };
    team?: { id: number; email: string; full_name?: string | null }[];
    all_plans: PlanInfo[];
}

type Period = "monthly" | "term" | "yearly";
type Currency = "EGP" | "USD";

/** Extracts a readable message from FastAPI errors (string detail or {message, message_en}). */
export function billingErrorMessage(err: unknown, lang: string, fallback: string): string {
    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
        const d = detail as { message?: string; message_en?: string };
        return (lang === "ar" ? d.message : d.message_en || d.message) || fallback;
    }
    return fallback;
}

function fmtDate(iso: string | null | undefined, lang: string): string | null {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString(lang === "ar" ? "ar-EG" : "en-US", { day: "numeric", month: "long", year: "numeric" });
}

export function SubscriptionQuotaBar({ refreshTrigger = 0 }: { refreshTrigger?: number }) {
    const { l, lang } = useI18n();
    const [data, setData] = useState<BillingStatusResponse | null>(null);
    const [modalOpen, setModalOpen] = useState(false);
    const [selectedPlan, setSelectedPlan] = useState<string>("pro");
    const [period, setPeriod] = useState<Period>("monthly");
    const [currency, setCurrency] = useState<Currency>("EGP");
    const [paymentMethod, setPaymentMethod] = useState<"card" | "wallet">("card");
    const [busy, setBusy] = useState(false);
    const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
    // Test-checkout help only when the backend says payments here are test payments. Starts hidden,
    // is hidden again while each opening re-asks (so a switch to live takes effect), and stays
    // hidden if the question fails.
    const [sandboxMode, setSandboxMode] = useState(false);

    useEffect(() => {
        if (!modalOpen) return;
        let cancelled = false;
        setSandboxMode(false);
        loadSandboxMode((path) => api.get(path)).then((mode) => {
            if (!cancelled) setSandboxMode(mode);
        });
        return () => { cancelled = true; };
    }, [modalOpen]);

    const fetchStatus = async () => {
        try {
            const res = await api.get<BillingStatusResponse>("/billing/status");
            setData(res.data);
            const tier = res.data.plan_tier;
            setSelectedPlan(tier === "free" ? "pro" : tier === "pro" ? "campus" : tier);
        } catch {
            setData(null);
        }
    };

    useEffect(() => {
        fetchStatus();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [refreshTrigger]);

    if (!data) return null;

    const { plan, usage, all_plans } = data;
    const isLifetime = (usage.exams_quota_type || plan.exams_reset) === "lifetime";
    const isUnlimitedExams = usage.exams_limit >= 9999;
    const pct = isUnlimitedExams ? 8 : Math.min(100, Math.round((usage.exams_used / Math.max(1, usage.exams_limit)) * 100));
    const bonus = usage.bonus_exams ?? 0;
    const isExhausted = !isUnlimitedExams && usage.exams_remaining === 0 && bonus === 0;
    const isNearLimit = !isUnlimitedExams && usage.exams_remaining <= 1;
    const studentsLimit = usage.students_limit ?? 0;
    const studentsUsed = usage.students_used ?? 0;
    const studentsFull = studentsLimit > 0 && studentsUsed >= studentsLimit;
    const resetsAt = fmtDate(usage.cycle_resets_at, lang);
    const expiresAt = fmtDate(data.plan_expires_at, lang);
    const canBuyAddon = !data.is_team_member && (plan.id === "pro" || plan.id === "campus");
    const addonPrice = currency === "EGP" ? plan.addon_price_egp : plan.addon_price_usd;
    // null unless the backend confirmed test payments: no test cards, numbers or "no real money" text.
    const help = sandboxHelp(sandboxMode, paymentMethod);

    const selected = all_plans.find((p) => p.id === selectedPlan) || plan;
    const selectedPrice = selected.period_prices?.[period]?.[currency] ?? null;

    const money = (v: number | null | undefined) =>
        v == null ? "—" : currency === "EGP" ? `${v.toLocaleString(lang === "ar" ? "ar-EG" : "en-US")} ${l("ج.م", "EGP")}` : `$${v}`;

    const startCheckout = async (body: Record<string, unknown>) => {
        setBusy(true);
        setToast(null);
        try {
            const res = await api.post<BillingStatusResponse & { message: string; checkout_url?: string | null }>(
                "/billing/checkout",
                { currency, payment_method: paymentMethod, ...body },
            );
            if (res.data.checkout_url) {
                window.location.href = res.data.checkout_url;
                return;
            }
            setToast({ ok: true, text: res.data.message || l("تم التفعيل بنجاح", "Activated successfully") });
            await fetchStatus();
            setTimeout(() => {
                setModalOpen(false);
                setToast(null);
            }, 1400);
        } catch (err) {
            setToast({ ok: false, text: billingErrorMessage(err, lang, l("تعذر إتمام العملية حالياً، حاول مرة أخرى", "Could not complete the request")) });
        } finally {
            setBusy(false);
        }
    };

    const handleUpgrade = () => {
        if (selected.id === "enterprise") {
            window.location.href = "/#contact";
            return;
        }
        startCheckout({ kind: "plan", plan_id: selected.id, period });
    };

    const handleAddon = () => {
        setModalOpen(true);
        setSelectedPlan(plan.id);
    };

    return (
        <>
            <div className="mb-6 rounded-[22px] border border-rule bg-sheet p-5 sm:p-6 shadow-card">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex-1">
                        <div className="flex flex-wrap items-center gap-2.5">
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#6F4E37] px-3.5 py-1 text-xs font-bold text-[#FAF6F0]">
                                <Crown className="size-3.5 text-[#E3A458]" aria-hidden />
                                {lang === "ar" ? plan.name_ar : plan.name_en}
                            </span>
                            <span className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-sheet-2 px-3 py-1 text-xs font-bold text-pen">
                                <Zap className="size-3.5 text-[#E3A458]" aria-hidden />
                                {lang === "ar" ? plan.queue_label_ar : plan.queue_label_en}
                            </span>
                            {studentsLimit > 0 && (
                                <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold ${studentsFull ? "border-bad/40 text-bad" : "border-rule bg-sheet-2 text-ink-2"}`}>
                                    <Users className="size-3.5 text-[#6F4E37]" aria-hidden />
                                    <span className="wb-num">{studentsUsed} / {studentsLimit}</span>
                                    {l("طالب بيمتحن دلوقتي", "in an exam now")}
                                </span>
                            )}
                            {expiresAt && (
                                <span className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-sheet-2 px-3 py-1 text-xs font-bold text-ink-2">
                                    <CalendarClock className="size-3.5 text-[#6F4E37]" aria-hidden />
                                    {l(`ينتهي ${expiresAt}`, `Expires ${expiresAt}`)}
                                </span>
                            )}
                            {data.is_team_member && data.billing_owner && (
                                <span className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-sheet-2 px-3 py-1 text-xs font-bold text-ink-2">
                                    {l(`ضمن فريق ${data.billing_owner.email}`, `Team of ${data.billing_owner.email}`)}
                                </span>
                            )}
                        </div>

                        <div className="mt-4 max-w-xl">
                            <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-bold">
                                <span className="text-ink-2">
                                    {isLifetime ? l("الامتحانات التجريبية:", "Trial exams:") : l("امتحانات الشهر:", "Exams this month:")}{" "}
                                    <strong className="wb-num text-ink">
                                        {isUnlimitedExams ? `${usage.exams_used} / ${l("غير محدود", "Unlimited")}` : `${usage.exams_used} / ${usage.exams_limit}`}
                                    </strong>
                                    {bonus > 0 && (
                                        <span className="ms-2 rounded-full bg-[#E3A458]/20 px-2 py-0.5 text-[11px] text-pen">
                                            {l(`+${bonus} إضافي`, `+${bonus} extra`)}
                                        </span>
                                    )}
                                </span>
                                <span className={isExhausted ? "text-bad" : isNearLimit ? "text-warn" : "text-pen"}>
                                    {isExhausted
                                        ? l("خلص رصيد الامتحانات", "Exam quota used up")
                                        : l(
                                              `متبقي ${usage.exams_remaining} · حتى ${usage.max_questions_per_exam} أسئلة · ${usage.max_duration_minutes} د/إجابة`,
                                              `${usage.exams_remaining} left · up to ${usage.max_questions_per_exam} questions · ${usage.max_duration_minutes}m/answer`,
                                          )}
                                </span>
                            </div>
                            <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full border border-rule bg-sheet-2">
                                <div
                                    className={`h-full rounded-full transition-all duration-500 ${isExhausted ? "bg-bad" : isNearLimit ? "bg-warn" : "bg-[#6F4E37]"}`}
                                    style={{ width: `${pct}%` }}
                                />
                            </div>
                            {!isLifetime && resetsAt && (
                                <p className="mt-1.5 text-[11px] font-bold text-ink-3">{l(`الرصيد بيتجدد يوم ${resetsAt}`, `Quota resets on ${resetsAt}`)}</p>
                            )}
                        </div>

                        {(isNearLimit || studentsFull) && (
                            <p className="mt-2.5 inline-flex items-center gap-1.5 text-xs font-bold text-warn">
                                <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
                                {studentsFull
                                    ? l("الامتحان مليان دلوقتي — أي طالب جديد هيستنى لحد ما حد يخلّص، أو رقّي الباقة لعدد أكبر في نفس الوقت.", "Exam room is full right now — new students wait until someone finishes, or upgrade for more at once.")
                                    : isLifetime
                                      ? l("الامتحانات التجريبية قربت تخلص — اشترك عشان تكمل.", "Trial exams almost used — subscribe to continue.")
                                      : l("امتحانات الشهر قربت تخلص — اشتري امتحانات إضافية أو رقّي باقتك.", "Monthly exams almost used — buy extra exams or upgrade.")}
                            </p>
                        )}
                    </div>

                    {!data.is_team_member && (
                        <div className="flex shrink-0 flex-wrap items-center gap-2.5">
                            {canBuyAddon && (
                                <button
                                    type="button"
                                    onClick={handleAddon}
                                    className="inline-flex h-11 items-center gap-2 whitespace-nowrap rounded-full border border-rule bg-sheet-2 px-4 text-xs sm:text-sm font-bold text-ink hover:bg-sheet"
                                >
                                    <PlusCircle className="size-4 text-[#6F4E37]" aria-hidden />
                                    {l("+10 امتحانات", "+10 exams")}
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={() => setModalOpen(true)}
                                className="oiq-btn-mint inline-flex h-11 items-center gap-2 whitespace-nowrap rounded-full px-5 text-xs sm:text-sm font-bold text-[#FAF6F0] shadow-sm transition-transform active:scale-[0.98]"
                            >
                                <Sparkles className="size-4 text-[#E3A458]" aria-hidden />
                                <span>{plan.id === "free" ? l("اشترك الآن", "Subscribe") : l("ترقية / تجديد الباقة", "Upgrade / Renew")}</span>
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {modalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-3 sm:p-6 backdrop-blur-xs" role="dialog" aria-modal="true">
                    <div className="relative max-h-[92dvh] w-full max-w-5xl overflow-y-auto rounded-[26px] border border-rule bg-paper p-5 sm:p-8 text-ink shadow-float">
                        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-rule pb-4">
                            <div>
                                <span className="inline-flex items-center gap-1.5 text-xs font-extrabold text-pen">
                                    <Crown className="size-4 text-[#E3A458]" aria-hidden />
                                    {l("إدارة الاشتراك", "Subscription")}
                                </span>
                                <h2 className="ar-heading mt-1 font-display text-xl sm:text-2xl font-bold text-ink">
                                    {l("اختار الباقة على قد طلابك وامتحاناتك", "Pick the plan that fits your students and exams")}
                                </h2>
                            </div>
                            <div className="flex flex-wrap items-center gap-2.5">
                                <div className="inline-flex items-center rounded-full border border-rule bg-sheet p-1 shadow-xs">
                                    {([
                                        ["monthly", l("شهري", "Monthly")],
                                        ["term", l("ترم", "Term")],
                                        ["yearly", l("سنوي", "Yearly")],
                                    ] as const).map(([id, label]) => (
                                        <button
                                            key={id}
                                            type="button"
                                            onClick={() => setPeriod(id)}
                                            className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-extrabold transition-all ${period === id ? "bg-[#6F4E37] text-[#FAF6F0]" : "text-ink-2 hover:text-ink"}`}
                                        >
                                            {label}
                                        </button>
                                    ))}
                                </div>
                                <div className="inline-flex items-center rounded-full border border-rule bg-sheet p-1 shadow-xs">
                                    {(["EGP", "USD"] as const).map((c) => (
                                        <button
                                            key={c}
                                            type="button"
                                            onClick={() => {
                                                setCurrency(c);
                                                setPaymentMethod("card");
                                            }}
                                            className={`wb-num rounded-full px-3 py-1.5 text-xs font-extrabold transition-all ${currency === c ? "bg-[#6F4E37] text-[#FAF6F0]" : "text-ink-2 hover:text-ink"}`}
                                        >
                                            {c === "EGP" ? "EGP (ج.م)" : "USD ($)"}
                                        </button>
                                    ))}
                                </div>
                                <button
                                    type="button"
                                    onClick={() => setModalOpen(false)}
                                    className="flex size-9 items-center justify-center rounded-full border border-rule bg-sheet text-ink-2 hover:bg-sheet-2 hover:text-ink"
                                    aria-label={l("إغلاق", "Close")}
                                >
                                    <X className="size-4" />
                                </button>
                            </div>
                        </div>

                        <div className="mt-5 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
                            {all_plans.map((p) => {
                                const isCurrent = p.id === plan.id;
                                const isSelected = p.id === selectedPlan;
                                const isEnterprise = p.id === "enterprise";
                                const isFree = p.id === "free";
                                const price = p.period_prices?.[period]?.[currency] ?? null;
                                return (
                                    <button
                                        key={p.id}
                                        type="button"
                                        disabled={isFree}
                                        onClick={() => setSelectedPlan(p.id)}
                                        className={`flex flex-col justify-between rounded-[20px] p-4 text-start transition-all disabled:cursor-default ${
                                            isSelected
                                                ? "wb-mocha-stage border-2 border-[#E3A458] text-[#FAF6F0] shadow-md"
                                                : "border border-rule bg-sheet text-ink hover:bg-sheet-2"
                                        } ${isFree ? "opacity-70" : ""}`}
                                    >
                                        <div>
                                            <div className="flex items-center justify-between gap-2">
                                                <span className="text-xs font-extrabold uppercase tracking-wider opacity-75">{p.id}</span>
                                                {isCurrent && (
                                                    <span className="rounded-full bg-[#E3A458] px-2.5 py-0.5 text-[10px] font-extrabold text-[#18110D]">
                                                        {l("باقتك الحالية", "Current")}
                                                    </span>
                                                )}
                                            </div>
                                            <h3 className="ar-heading mt-2 font-display text-base font-bold">{lang === "ar" ? p.name_ar : p.name_en}</h3>
                                            <p className="wb-num mt-2 text-2xl font-extrabold">
                                                {isFree
                                                    ? l("مجاناً", "Free")
                                                    : isEnterprise
                                                      ? l(`${p.price_per_student_term_egp ?? 30} ج.م / طالب / ترم`, `${p.price_per_student_term_egp ?? 30} EGP / student / term`)
                                                      : money(price)}
                                            </p>
                                            <div className="mt-3 space-y-1.5 border-t border-current/15 pt-3 text-xs font-bold">
                                                <div className="flex items-center gap-1.5">
                                                    <Layers className="size-3.5 text-[#E3A458]" aria-hidden />
                                                    <span>
                                                        {isEnterprise
                                                            ? l("امتحانات حسب الاتفاق", "Custom exams")
                                                            : p.exams_reset === "lifetime"
                                                              ? l(`${p.max_exams} امتحانات (مرة واحدة)`, `${p.max_exams} exams (one-time)`)
                                                              : l(`${p.max_exams} امتحان / شهر`, `${p.max_exams} exams / month`)}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <Users className="size-3.5 text-[#E3A458]" aria-hidden />
                                                    <span>
                                                        {isEnterprise
                                                            ? l("طلاب حسب الاتفاق", "Custom students")
                                                            : l(`${p.max_students} طالب في نفس الوقت`, `${p.max_students} students at once`)}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <Check className="size-3.5 text-[#E3A458]" aria-hidden />
                                                    <span>
                                                        {l(
                                                            `${p.max_questions_per_exam} أسئلة · ${p.max_duration_minutes} د/إجابة`,
                                                            `${p.max_questions_per_exam} questions · ${p.max_duration_minutes}m/answer`,
                                                        )}
                                                    </span>
                                                </div>
                                                {!!p.assistant_seats && (
                                                    <div className="flex items-center gap-1.5">
                                                        <Users className="size-3.5 text-[#E3A458]" aria-hidden />
                                                        <span>{l(`${p.assistant_seats} مساعدين`, `${p.assistant_seats} assistants`)}</span>
                                                    </div>
                                                )}
                                                <div className="flex items-center gap-1.5">
                                                    <Zap className="size-3.5 text-[#E3A458]" aria-hidden />
                                                    <span>{lang === "ar" ? p.queue_label_ar : p.queue_label_en}</span>
                                                </div>
                                            </div>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>

                        {selected.id !== "enterprise" && (
                            <div className="mt-6 rounded-[20px] border border-rule bg-sheet p-4 sm:p-5">
                                <p className="text-xs font-extrabold text-ink-2">
                                    {currency === "EGP" ? l("وسيلة الدفع (Kashier):", "Payment method (Kashier):") : l("الدفع بالدولار (Kashier):", "USD payment (Kashier):")}
                                </p>
                                <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                                    <button
                                        type="button"
                                        onClick={() => setPaymentMethod("card")}
                                        className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-xs font-bold transition-all ${paymentMethod === "card" ? "border-[#6F4E37] bg-[#6F4E37]/12 text-ink" : "border-rule bg-sheet-2 text-ink-2 hover:text-ink"}`}
                                    >
                                        <CreditCard className="size-4 shrink-0 text-[#6F4E37]" aria-hidden />
                                        {currency === "EGP" ? l("بطاقة بنكية / ميزة", "Card / Meeza") : l("بطاقة بنكية دولية", "International card")}
                                    </button>
                                    {currency === "EGP" && (
                                        <button
                                            type="button"
                                            onClick={() => setPaymentMethod("wallet")}
                                            className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-xs font-bold transition-all ${paymentMethod === "wallet" ? "border-[#6F4E37] bg-[#6F4E37]/12 text-ink" : "border-rule bg-sheet-2 text-ink-2 hover:text-ink"}`}
                                        >
                                            <Wallet className="size-4 shrink-0 text-[#6F4E37]" aria-hidden />
                                            {l("محفظة إلكترونية (فودافون كاش وغيرها)", "Mobile wallet (Vodafone Cash, etc.)")}
                                        </button>
                                    )}
                                </div>
                                {paymentMethod === "wallet" && currency === "EGP" && (
                                    <p className="mt-3 text-xs font-semibold text-ink-2">
                                        {l("رقم المحفظة هتكتبه في صفحة الدفع الآمنة الخاصة بـ Kashier.", "You'll enter your wallet number on Kashier's secure payment page.")}
                                    </p>
                                )}

                                {help && (
                                    <div className="mt-4 rounded-xl border border-rule/80 bg-sheet-2/60 p-3.5 text-xs text-ink-2">
                                        <p className="font-extrabold text-ink flex items-center gap-1.5 mb-1.5">
                                            <span className="inline-block size-2 rounded-full bg-[#E3A458]" />
                                            {l(help.heading.ar, help.heading.en)}
                                        </p>
                                        {help.cardLines.length > 0 && (
                                            <div className="space-y-1 font-mono text-[11px] text-ink leading-relaxed" dir="ltr">
                                                {help.cardLines.map((line) => <p key={line}>{line}</p>)}
                                            </div>
                                        )}
                                        {help.walletNote && (
                                            <div className="space-y-1 text-[11px] text-ink leading-relaxed">
                                                <p>{l(help.walletNote.ar, help.walletNote.en)}</p>
                                            </div>
                                        )}
                                    </div>
                                )}
                                {canBuyAddon && (
                                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
                                        <span className="text-xs font-bold text-ink-2">
                                            {l(
                                                `محتاج امتحانات أكتر الشهر ده؟ +10 امتحانات بـ ${money(addonPrice)} (ما بتنتهيش)`,
                                                `Need more exams this month? +10 exams for ${money(addonPrice)} (never expire)`,
                                            )}
                                        </span>
                                        <button
                                            type="button"
                                            disabled={busy}
                                            onClick={() => startCheckout({ kind: "addon" })}
                                            className="inline-flex h-10 items-center gap-2 whitespace-nowrap rounded-full border border-[#6F4E37] px-4 text-xs font-bold text-[#6F4E37] hover:bg-[#6F4E37]/10 disabled:opacity-50"
                                        >
                                            <PlusCircle className="size-4" aria-hidden />
                                            {l("اشتري +10 امتحانات", "Buy +10 exams")}
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}

                        {toast && (
                            <div className={`mt-4 rounded-xl border px-4 py-3 text-xs font-bold ${toast.ok ? "border-good/30 bg-good-soft text-good" : "border-bad/30 bg-bad/10 text-bad"}`}>
                                {toast.text}
                            </div>
                        )}

                        <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
                            <button
                                type="button"
                                onClick={() => setModalOpen(false)}
                                className="h-11 rounded-full border border-rule bg-sheet px-5 text-xs sm:text-sm font-bold text-ink-2 hover:bg-sheet-2 hover:text-ink"
                            >
                                {l("إلغاء", "Cancel")}
                            </button>
                            <button
                                type="button"
                                disabled={busy || selected.id === "free"}
                                onClick={handleUpgrade}
                                className="oiq-btn-mint inline-flex h-11 items-center gap-2 rounded-full px-6 text-xs sm:text-sm font-bold text-[#FAF6F0] disabled:opacity-50"
                            >
                                <Sparkles className="size-4 text-[#E3A458]" aria-hidden />
                                <span>
                                    {busy
                                        ? l("جاري التحويل للدفع...", "Redirecting to payment...")
                                        : selected.id === "enterprise"
                                          ? l("تواصل معنا", "Contact sales")
                                          : selected.id === plan.id
                                            ? l(`تجديد الباقة (${money(selectedPrice)})`, `Renew (${money(selectedPrice)})`)
                                            : l(`ادفع واشترك (${money(selectedPrice)})`, `Pay & subscribe (${money(selectedPrice)})`)}
                                </span>
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
