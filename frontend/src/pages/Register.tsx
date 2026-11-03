import { useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, GraduationCap, Loader2, Presentation } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { cn } from "../lib/utils";
import { usePageTitle } from "../lib/usePageTitle";
import { getApiErrorMessage } from "../lib/apiErrors";
import { gsap, useGSAP, withMotion } from "../lib/gsap";
import Logo from "../components/Logo";
import LanguageToggle, { ThemeToggle } from "../components/LanguageToggle";
import { StaticBlackLogoStage } from "../components/ui/sign-in-page";
import GoogleSignInButton from "../components/auth/GoogleSignInButton";

export default function RegisterPage() {
    const { l, lang } = useI18n();
    const root = useRef<HTMLDivElement>(null);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [fullName, setFullName] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    // After sign-up: the address the confirmation link went to (no session until it is used).
    const [sentTo, setSentTo] = useState("");
    const [resendNote, setResendNote] = useState("");
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const rawRedirect = searchParams.get("redirect") || "";
    const redirectTo = rawRedirect.startsWith("/") && !rawRedirect.startsWith("//") ? rawRedirect : "/dashboard";
    const forcedRole = searchParams.get("role");
    const [role, setRole] = useState(forcedRole || "student");
    usePageTitle(l("إنشاء حساب", "Create account"));

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-reg-item]",
                { y: 18, opacity: 0 },
                { y: 0, opacity: 1, duration: 0.55, stagger: 0.05, ease: "power3.out" },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const handleRegister = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!fullName.trim() || !email.trim() || password.length < 8) return;
        setLoading(true);
        setError("");
        try {
            // The account stays unverified until the e-mailed link is opened with this password;
            // the answer is the same whether or not the address was already registered.
            await api.post("/register", { email: email.trim(), password, full_name: fullName.trim(), role });
            setSentTo(email.trim());
            setResendNote("");
        } catch (err: unknown) {
            const e2 = err as { response?: { status?: number; data?: { detail?: unknown } } };
            if (e2?.response?.status === 422) {
                setError(l("راجع البريد الإلكتروني، شكله مش مكتوب صح.", "Check the email address — it doesn't look right."));
            } else {
                setError(getApiErrorMessage(err, l("تعذّر إنشاء الحساب. جرّب تاني بعد لحظات.", "Couldn't create the account. Try again shortly.")));
            }
        } finally {
            setLoading(false);
        }
    };

    const resend = async () => {
        setResendNote("");
        try {
            await api.post("/auth/resend-verification", { email: sentTo });
            setResendNote(l("لو ينفع، هيوصلك رابط جديد خلال دقايق. افحص الـ Spam كمان.", "If possible, a new link will arrive in a few minutes. Check spam too."));
        } catch (err) {
            setResendNote(getApiErrorMessage(err));
        }
    };

    const roles = [
        { value: "student", icon: GraduationCap, label: l("طالب", "Student"), sub: l("أدخل الامتحانات وأشوف درجاتي", "Take exams and see my grades") },
        { value: "lecturer", icon: Presentation, label: l("دكتور / محاضر / مدرس", "Doctor / Lecturer / Teacher"), sub: l("أكتب الأسئلة وأراجع إجابات الطلاب", "Write questions and review student answers") },
    ];

    return (
        <div ref={root} className="min-h-dvh w-full bg-paper text-ink flex flex-col lg:flex-row overflow-x-hidden">
            {/* Half 1: Espresso Brown Stage with Static Large Off-White ORALIQ Wordmark */}
            <StaticBlackLogoStage backLabel={l("العودة للرئيسية", "Back to home")} />

            {/* Half 2: Warm Off-White Surface (flips to Rich Espresso Brown in Dark Mode) */}
            <div className="flex-1 flex flex-col justify-between bg-paper text-ink px-5 py-6 sm:px-10 sm:py-8 lg:px-14 overflow-y-auto">
                <div className="flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-2 text-ink">
                        <Logo height={24} className="text-ink" />
                    </Link>
                    <div className="flex items-center gap-1.5">
                        <LanguageToggle compact className="text-ink hover:bg-sheet-2" />
                        <ThemeToggle className="text-ink hover:bg-sheet-2" />
                    </div>
                </div>

                <div className="w-full max-w-md mx-auto my-auto py-6">
                    <div data-reg-item className="mb-6">
                        <h1 className="ar-heading text-3xl sm:text-4xl font-bold text-ink mb-2">
                            {l("إنشاء حساب جديد", "Create Account")}
                        </h1>
                        <p className="text-ink-2 font-medium">
                            {l("عندك حساب بالفعل؟", "Already have an account?")}{" "}
                            <button
                                type="button"
                                onClick={() => navigate(`/login?redirect=${encodeURIComponent(redirectTo)}`)}
                                className="text-pen hover:text-pen-hover font-bold underline underline-offset-4"
                            >
                                {l("سجّل دخولك", "Sign in")}
                            </button>
                        </p>
                    </div>

                    {error && (
                        <div className="mb-5 rounded-xl border border-mark/35 bg-mark-wash px-4 py-3 text-sm font-bold text-mark">
                            {error}
                        </div>
                    )}

                    {sentTo ? (
                        <div data-reg-item className="rounded-xl border border-rule bg-sheet px-5 py-5 text-ink" role="status">
                            <p className="text-lg font-bold">{l("افتح بريدك عشان تكمّل", "Check your e-mail to finish")}</p>
                            <p className="mt-2 text-sm text-ink-2 leading-relaxed">
                                {l(
                                    "لو البريد ده ينفع يتسجّل بيه، بعتنا عليه رابط تأكيد. افتح الرابط واكتب نفس كلمة المرور اللي لسه اخترتها، وبعدها هتدخل على حسابك.",
                                    "If this address can be used, we sent it a confirmation link. Open it and enter the password you just chose; then you're in.",
                                )}
                            </p>
                            <p className="mt-2 text-sm font-bold text-ink [overflow-wrap:anywhere]" dir="ltr">{sentTo}</p>
                            <div className="mt-4 flex flex-wrap gap-3 text-sm">
                                <button type="button" onClick={resend} className="font-bold text-pen underline underline-offset-4">
                                    {l("ابعت الرابط تاني", "Send the link again")}
                                </button>
                                <button type="button" onClick={() => setSentTo("")} className="font-bold text-ink-2 underline underline-offset-4">
                                    {l("غيّر البريد", "Use a different e-mail")}
                                </button>
                            </div>
                            {resendNote && <p className="mt-3 text-xs text-ink-2">{resendNote}</p>}
                        </div>
                    ) : (
                    <form onSubmit={handleRegister} className="space-y-4" noValidate>
                        {!forcedRole && (
                            <div data-reg-item className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup">
                                {roles.map(({ value, icon: Icon, label, sub }) => {
                                    const active = role === value;
                                    return (
                                        <label
                                            key={value}
                                            className={cn(
                                                "relative flex cursor-pointer flex-col gap-1 rounded-xl border p-3.5 transition-all",
                                                active
                                                    ? "border-pen bg-sheet shadow-card ring-1 ring-pen"
                                                    : "border-rule bg-sheet/65 hover:border-ink-3",
                                            )}
                                        >
                                            <input
                                                type="radio"
                                                name="role"
                                                value={value}
                                                checked={active}
                                                onChange={() => setRole(value)}
                                                className="sr-only"
                                            />
                                            <div className="flex items-center justify-between">
                                                <Icon className={cn("size-5", active ? "text-pen" : "text-ink-3")} aria-hidden />
                                                <span className={cn("size-3.5 rounded-full border", active ? "border-pen bg-pen" : "border-rule-strong/40")} />
                                            </div>
                                            <span className="mt-1 text-sm font-bold text-ink">{label}</span>
                                            <span className="text-xs text-ink-2 leading-snug">{sub}</span>
                                        </label>
                                    );
                                })}
                            </div>
                        )}

                        <div data-reg-item>
                            <label htmlFor="reg-name" className="block text-sm font-bold text-ink mb-1.5">
                                {l("الاسم بالكامل", "Full Name")}
                            </label>
                            <input
                                id="reg-name"
                                type="text"
                                required
                                value={fullName}
                                onChange={(e) => setFullName(e.target.value)}
                                placeholder={l("اسمك الثلاثي", "Your full name")}
                                className="auth-light-input w-full px-4 py-3 border border-rule bg-sheet text-ink placeholder:text-field rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium"
                            />
                        </div>

                        <div data-reg-item>
                            <label htmlFor="reg-email" className="block text-sm font-bold text-ink mb-1.5">
                                {l("البريد الإلكتروني", "Email Address")}
                            </label>
                            <input
                                id="reg-email"
                                type="email"
                                required
                                dir="ltr"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="name@university.edu.eg"
                                className="auth-light-input w-full px-4 py-3 border border-rule bg-sheet text-ink placeholder:text-field rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium"
                            />
                        </div>

                        <div data-reg-item>
                            <label htmlFor="reg-pass" className="block text-sm font-bold text-ink mb-1.5">
                                {l("كلمة المرور (8 حروف على الأقل)", "Password (min 8 characters)")}
                            </label>
                            <div className="relative">
                                <input
                                    id="reg-pass"
                                    type={showPassword ? "text" : "password"}
                                    required
                                    minLength={8}
                                    dir="ltr"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="••••••••"
                                    className="auth-light-input w-full px-4 py-3 pr-12 border border-rule bg-sheet text-ink placeholder:text-field rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 hover:bg-sheet-2 rounded-full"
                                >
                                    {showPassword ? <EyeOff className="w-5 h-5 text-ink-3" /> : <Eye className="w-5 h-5 text-ink-3" />}
                                </button>
                            </div>
                        </div>

                        <div data-reg-item className="pt-1">
                            <button
                                type="submit"
                                disabled={loading}
                                className="oiq-btn-mint w-full py-3.5 px-4 rounded-xl font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-60"
                            >
                                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                                <span>{loading ? l("جاري إنشاء الحساب…", "Creating account…") : l("إنشاء الحساب", "Sign Up")}</span>
                            </button>
                        </div>

                    </form>
                    )}

                    {/* Sign up with Google */}
                    <GoogleSignInButton
                        mode="signup"
                        defaultRole={role === "student" || role === "lecturer" ? role : undefined}
                        initialName={fullName}
                        onStart={() => setError("")}
                        onSuccess={(token) => {
                            localStorage.setItem("token", token);
                            const dest = (role === "lecturer" || role === "hr" || role === "admin") ? "/dashboard" : redirectTo;
                            navigate(dest);
                        }}
                        onError={setError}
                        header={
                            <div data-reg-item className="relative my-5">
                                <div className="absolute inset-0 flex items-center">
                                    <div className="w-full border-t border-rule"></div>
                                </div>
                                <div className="relative flex justify-center text-sm">
                                    <span className="px-3 bg-paper text-ink-3 font-medium">
                                        {l("أو التسجيل عبر", "or")}
                                    </span>
                                </div>
                            </div>
                        }
                    />
                </div>

                <p className="text-center text-xs font-medium text-ink-3">
                    © 2026 OralIQ — AI Oral Examination Platform
                </p>
            </div>
        </div>
    );
}
