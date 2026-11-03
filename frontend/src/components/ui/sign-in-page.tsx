import { useRef, useState } from "react";
import { Eye, EyeOff, ArrowLeft, Loader2 } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api from "../../lib/api";
import { useI18n } from "../../i18n";
import { getApiErrorMessage } from "../../lib/apiErrors";
import { usePageTitle } from "../../lib/usePageTitle";
import { gsap, useGSAP, withMotion } from "../../lib/gsap";
import Logo from "../Logo";
import LanguageToggle, { ThemeToggle } from "../LanguageToggle";
import GoogleSignInButton from "../auth/GoogleSignInButton";

/**
 * Half Espresso Brown Visual Panel with Static Large Off-White ORALIQ Wordmark Logo Only.
 * Responsive: renders as a sleek top Espresso Brown stage on mobile/tablet (< lg)
 * and a full 50% split stage on desktop (lg:flex-1).
 */
export function StaticBlackLogoStage({ backLabel }: { backLabel: string }) {
    const navigate = useNavigate();

    return (
        <>
            {/* Mobile & Tablet Top Espresso Brown Banner (< lg) */}
            <div className="wb-mocha-stage relative flex lg:hidden items-center justify-center px-6 py-8 border-b border-[#FAF6F0]/15 select-none">
                <button
                    type="button"
                    onClick={() => navigate("/")}
                    aria-label={backLabel}
                    className="absolute start-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-[#FAF6F0]/12 hover:bg-[#FAF6F0]/22 border border-[#FAF6F0]/20 rounded-full flex items-center justify-center transition-colors"
                >
                    <ArrowLeft className="w-5 h-5 text-[#FAF6F0] rtl:rotate-180" />
                </button>
                <Logo height={42} className="text-[#FAF6F0]" />
            </div>

            {/* Desktop 50% Split Espresso Brown Stage (lg+) */}
            <div className="wb-mocha-stage relative hidden lg:flex lg:flex-1 items-center justify-center overflow-hidden select-none border-e border-[#FAF6F0]/15">
                {/* Back Button */}
                <div className="absolute top-7 start-7 z-20">
                    <button
                        type="button"
                        onClick={() => navigate("/")}
                        aria-label={backLabel}
                        className="w-11 h-11 bg-[#FAF6F0]/12 hover:bg-[#FAF6F0]/22 border border-[#FAF6F0]/20 rounded-full flex items-center justify-center transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-[#FAF6F0] rtl:rotate-180" />
                    </button>
                </div>

                {/* Center Static Large Off-White ORALIQ Wordmark Only */}
                <div className="flex items-center justify-center p-12">
                    <Logo height={88} className="text-[#FAF6F0] max-w-[80vw]" />
                </div>
            </div>
        </>
    );
}

export function LoginPage() {
    const navigate = useNavigate();
    const { l, lang } = useI18n();
    const [searchParams] = useSearchParams();
    const rawRedirect = searchParams.get("redirect") || "";
    const redirectTo = rawRedirect.startsWith("/") && !rawRedirect.startsWith("//") ? rawRedirect : "/dashboard";
    usePageTitle(l("تسجيل الدخول", "Sign In"));

    const root = useRef<HTMLDivElement>(null);
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    // Correct password, but the sign-up's e-mail was never confirmed.
    const [unverified, setUnverified] = useState(false);
    const [resendNote, setResendNote] = useState("");

    const [formData, setFormData] = useState({
        email: "",
        password: "",
        rememberMe: true,
    });

    useGSAP(() => {
        withMotion(() => {
            gsap.fromTo(
                "[data-auth-form-item]",
                { y: 18, opacity: 0 },
                { y: 0, opacity: 1, duration: 0.55, stagger: 0.06, ease: "power3.out" },
            );
        });
    }, { scope: root, dependencies: [lang] });

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const { name, value, type, checked } = e.target;
        setError("");
        setFormData((prev) => ({
            ...prev,
            [name]: type === "checkbox" ? checked : value,
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!formData.email.trim() || !formData.password) return;
        setLoading(true);
        setError("");
        try {
            const params = new URLSearchParams();
            params.append("username", formData.email.trim());
            params.append("password", formData.password);
            const response = await api.post("/login/access-token", params);
            localStorage.setItem("token", response.data.access_token);
            navigate(redirectTo);
        } catch (err: unknown) {
            const res = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
            const code = (res?.data?.detail as { code?: string } | undefined)?.code;
            setUnverified(res?.status === 403 && code === "EMAIL_NOT_VERIFIED");
            setResendNote("");
            setError(
                res?.status === 400 && res.data?.detail !== "Inactive user"
                    ? l("البريد الإلكتروني أو كلمة المرور غير صحيحة.", "Invalid email or password. Please try again.")
                    : getApiErrorMessage(err),
            );
        } finally {
            setLoading(false);
        }
    };

    const handleGoogleToken = (token: string) => {
        localStorage.setItem("token", token);
        navigate(redirectTo);
    };

    return (
        <div ref={root} className="min-h-dvh w-full bg-paper text-ink flex flex-col lg:flex-row overflow-x-hidden">
            {/* Half 1: Espresso Brown Stage with Static Large Off-White ORALIQ Wordmark */}
            <StaticBlackLogoStage backLabel={l("العودة للرئيسية", "Back to home")} />

            {/* Half 2: Warm Off-White Surface (flips to Rich Espresso Brown in Dark Mode) */}
            <div className="flex-1 flex flex-col justify-between bg-paper text-ink px-5 py-6 sm:px-10 sm:py-8 lg:px-14 overflow-y-auto">
                {/* Top Controls */}
                <div className="flex items-center justify-between">
                    <Link to="/" className="flex items-center gap-2 text-ink">
                        <Logo height={24} className="text-ink" />
                    </Link>
                    <div className="flex items-center gap-1.5">
                        <LanguageToggle compact className="text-ink hover:bg-sheet-2" />
                        <ThemeToggle className="text-ink hover:bg-sheet-2" />
                    </div>
                </div>

                {/* Form Box */}
                <div className="w-full max-w-md mx-auto my-auto py-6 sm:py-8">
                    <div data-auth-form-item className="mb-7 sm:mb-8">
                        <h1 className="ar-heading text-3xl sm:text-4xl font-bold text-ink mb-2">
                            {l("أهلاً بعودتك", "Welcome Back")}
                        </h1>
                        <p className="text-ink-2 font-medium">
                            {l("معندكش حساب لسه؟", "Don't have an account?")}{" "}
                            <button
                                type="button"
                                onClick={() => navigate(`/register?redirect=${encodeURIComponent(redirectTo)}`)}
                                className="text-pen hover:text-pen-hover font-bold underline underline-offset-4"
                            >
                                {l("أنشئ حساب جديد", "Sign up")}
                            </button>
                        </p>
                    </div>

                    {searchParams.get("expired") && !error && (
                        <div className="mb-6 rounded-xl border border-pen/35 bg-pen-wash px-4 py-3 text-sm font-bold text-ink">
                            {l("انتهت جلستك. سجّل دخولك تاني وهترجع للصفحة اللي كنت فيها.", "Your session ended. Sign in again to return to where you were.")}
                        </div>
                    )}

                    {error && (
                        <div className="mb-6 rounded-xl border border-mark/35 bg-mark-wash px-4 py-3 text-sm font-bold text-mark">
                            {error}
                            {unverified && (
                                <div className="mt-2 font-medium text-ink-2">
                                    <button
                                        type="button"
                                        className="font-bold text-pen underline underline-offset-4"
                                        onClick={async () => {
                                            try {
                                                await api.post("/auth/resend-verification", { email: formData.email.trim() });
                                                setResendNote(l("لو ينفع، هيوصلك رابط جديد خلال دقايق.", "If possible, a new link will arrive in a few minutes."));
                                            } catch (e) {
                                                setResendNote(getApiErrorMessage(e));
                                            }
                                        }}
                                    >
                                        {l("ابعت رابط التأكيد تاني", "Send the confirmation link again")}
                                    </button>
                                    {resendNote && <p className="mt-1 text-xs">{resendNote}</p>}
                                </div>
                            )}
                        </div>
                    )}

                    {notice && !error && (
                        <div className="mb-6 rounded-xl border border-pen/35 bg-pen-wash px-4 py-3 text-sm font-bold text-ink">
                            {notice}
                        </div>
                    )}

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
                        {/* Email */}
                        <div data-auth-form-item>
                            <label htmlFor="login-email" className="block text-sm font-bold text-ink mb-2">
                                {l("البريد الإلكتروني", "Email Address")}
                            </label>
                            <input
                                id="login-email"
                                type="email"
                                name="email"
                                dir="ltr"
                                value={formData.email}
                                onChange={handleInputChange}
                                placeholder="name@university.edu.eg"
                                className="auth-light-input w-full px-4 py-3.5 border border-rule bg-sheet text-ink placeholder:text-field rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium transition-all"
                                required
                            />
                        </div>

                        {/* Password */}
                        <div data-auth-form-item>
                            <label htmlFor="login-password" className="block text-sm font-bold text-ink mb-2">
                                {l("كلمة المرور", "Password")}
                            </label>
                            <div className="relative">
                                <input
                                    id="login-password"
                                    type={showPassword ? "text" : "password"}
                                    name="password"
                                    dir="ltr"
                                    value={formData.password}
                                    onChange={handleInputChange}
                                    placeholder="••••••••"
                                    className="auth-light-input w-full px-4 py-3.5 pr-12 border border-rule bg-sheet text-ink placeholder:text-field rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium transition-all"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    aria-label={showPassword ? l("إخفاء كلمة المرور", "Hide password") : l("إظهار كلمة المرور", "Show password")}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 hover:bg-sheet-2 rounded-full transition-colors"
                                >
                                    {showPassword ? (
                                        <EyeOff className="w-5 h-5 text-ink-3" />
                                    ) : (
                                        <Eye className="w-5 h-5 text-ink-3" />
                                    )}
                                </button>
                            </div>
                        </div>

                        {/* Remember Me + Forgot Password */}
                        <div data-auth-form-item className="flex flex-wrap items-center justify-between gap-2">
                            <label className="flex items-center gap-2 text-sm text-ink-2 font-medium cursor-pointer">
                                <input
                                    type="checkbox"
                                    name="rememberMe"
                                    checked={formData.rememberMe}
                                    onChange={handleInputChange}
                                    className="w-4 h-4 accent-[#6F4E37] border-rule rounded"
                                />
                                <span>{l("تذكرني", "Remember me")}</span>
                            </label>
                            <button
                                type="button"
                                onClick={() => setNotice(l(
                                    "لاسترجاع كلمة المرور تواصل مع إدارة المنصة. ولو بريدك على Gmail تقدر تدخل مباشرة بزر Google.",
                                    "To reset your password, contact the platform admin. If your email is a Google account, you can sign in with the Google button.",
                                ))}
                                className="text-sm text-pen hover:text-pen-hover font-bold"
                            >
                                {l("نسيت كلمة المرور؟", "Forgot password?")}
                            </button>
                        </div>

                        {/* Submit */}
                        <div data-auth-form-item>
                            <button
                                type="submit"
                                disabled={loading}
                                className="oiq-btn-mint w-full py-3.5 px-4 rounded-xl font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-60"
                            >
                                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                                <span>{loading ? l("جاري تسجيل الدخول…", "Signing in…") : l("تسجيل الدخول", "Sign In")}</span>
                            </button>
                        </div>

                    </form>

                    {/* Sign in with Google (shown only when the server has GOOGLE_CLIENT_ID) */}
                    <GoogleSignInButton
                        mode="signin"
                        onStart={() => { setError(""); setNotice(""); }}
                        onSuccess={handleGoogleToken}
                        onError={setError}
                        header={
                            <div data-auth-form-item className="relative my-6">
                                <div className="absolute inset-0 flex items-center">
                                    <div className="w-full border-t border-rule"></div>
                                </div>
                                <div className="relative flex justify-center text-sm">
                                    <span className="px-3 bg-paper text-ink-3 font-medium">
                                        {l("أو المتابعة عبر", "or")}
                                    </span>
                                </div>
                            </div>
                        }
                    />
                </div>

                {/* Footer */}
                <p className="text-center text-xs font-medium text-ink-3">
                    © 2026 OralIQ — AI Oral Examination Platform
                </p>
            </div>

        </div>
    );
}

export default LoginPage;
