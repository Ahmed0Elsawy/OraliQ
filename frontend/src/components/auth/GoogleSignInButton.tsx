import { useCallback, useEffect, useRef, useState } from "react";
import { GraduationCap, Loader2, Presentation, X } from "lucide-react";
import api from "../../lib/api";
import { useI18n } from "../../i18n";
import { useTheme } from "../../lib/theme";
import { cn } from "../../lib/utils";
import { getApiErrorMessage } from "../../lib/apiErrors";

/**
 * Official "Sign in with Google" button (Google Identity Services).
 *
 * - Existing accounts sign right in with one click.
 * - First-time Google accounts (whether started from Login or Register) open a clean modal
 *   allowing the user to enter/edit their real full name (pre-filled from the form or Google)
 *   and pick whether they are a Student ("طالب") or Doctor/Teacher ("دكتور / أستاذ").
 */

type Role = "student" | "lecturer";

type GoogleCredentialResponse = { credential?: string };
type GoogleId = {
    initialize: (opts: {
        client_id: string;
        callback: (resp: GoogleCredentialResponse) => void;
        ux_mode?: "popup" | "redirect";
        auto_select?: boolean;
        cancel_on_tap_outside?: boolean;
        context?: "signin" | "signup" | "use";
    }) => void;
    renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
    cancel: () => void;
};
declare global {
    interface Window {
        google?: { accounts?: { id?: GoogleId } };
    }
}

const GSI_SRC = "https://accounts.google.com/gsi/client";
let gsiPromise: Promise<GoogleId> | null = null;

function loadGsi(): Promise<GoogleId> {
    if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
    if (gsiPromise) return gsiPromise;
    gsiPromise = new Promise<GoogleId>((resolve, reject) => {
        const done = () => {
            const id = window.google?.accounts?.id;
            if (id) resolve(id);
            else reject(new Error("Google Identity Services unavailable"));
        };
        const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
        const script = existing ?? document.createElement("script");
        script.addEventListener("load", done, { once: true });
        script.addEventListener("error", () => reject(new Error("Failed to load Google script")), { once: true });
        if (!existing) {
            script.src = GSI_SRC;
            script.async = true;
            script.defer = true;
            document.head.appendChild(script);
        }
    }).catch((err) => {
        gsiPromise = null;
        throw err;
    });
    return gsiPromise;
}

let configPromise: Promise<string | null> | null = null;

function getClientId(): Promise<string | null> {
    if (configPromise) return configPromise;
    const fallback = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined)?.trim() || null;
    // Client ID is public: use the build-time value right away instead of waiting for a
    // (possibly cold-starting) backend, so the Google button is clickable immediately.
    if (fallback) {
        configPromise = Promise.resolve(fallback);
        return configPromise;
    }
    configPromise = api
        .get<{ enabled: boolean; client_id: string | null }>("/auth/google/config")
        .then((res) => (res.data?.enabled && res.data.client_id ? res.data.client_id : fallback))
        .catch(() => {
            configPromise = null;
            return fallback;
        });
    return configPromise;
}

function GoogleMark() {
    return (
        <svg className="size-5 shrink-0" viewBox="0 0 24 24" aria-hidden>
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
        </svg>
    );
}

type Props = {
    /** Pre-selected role for the first-time Google signup modal (e.g. from Register page). */
    defaultRole?: Role;
    /** Pre-filled full name if the user already started typing on Register page. */
    initialName?: string;
    mode?: "signin" | "signup";
    onSuccess: (token: string) => void;
    onError: (message: string) => void;
    /** Called before every attempt so the page can clear old errors. */
    onStart?: () => void;
    /** Rendered above the button (e.g. an "or" divider). */
    header?: React.ReactNode;
    className?: string;
};

export default function GoogleSignInButton({
    defaultRole,
    initialName,
    mode = "signin",
    onSuccess,
    onError,
    onStart,
    header,
    className,
}: Props) {
    const { l, lang } = useI18n();
    const { resolved } = useTheme();
    const btnRef = useRef<HTMLDivElement>(null);
    const [clientId, setClientId] = useState<string | null>(null);
    const [configChecked, setConfigChecked] = useState(false);
    const [gsiReady, setGsiReady] = useState(false);
    const [busy, setBusy] = useState(false);

    // First-time signup completion modal state
    const [pendingCredential, setPendingCredential] = useState<string | null>(null);
    const [pendingEmail, setPendingEmail] = useState<string>("");
    const [customName, setCustomName] = useState<string>("");
    const [chosenRole, setChosenRole] = useState<Role>(defaultRole ?? "student");
    const [modalError, setModalError] = useState<string>("");

    const latest = useRef({ defaultRole, initialName, onSuccess, onError, onStart, l });
    latest.current = { defaultRole, initialName, onSuccess, onError, onStart, l };

    const submit = useCallback(async (credential: string, roleToCreate?: Role, fullNameToCreate?: string) => {
        const { defaultRole: defRole, initialName: initName, onSuccess: ok, onError: fail, onStart: start, l: t } = latest.current;
        start?.();
        setModalError("");
        setBusy(true);
        try {
            const res = await api.post("/login/google", {
                credential,
                role: roleToCreate ?? null,
                full_name: fullNameToCreate?.trim() || null,
            });
            setPendingCredential(null);
            ok(res.data.access_token);
        } catch (err: unknown) {
            const r = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
            const detail = r?.data?.detail as
                | { code?: string; email?: string; suggested_name?: string }
                | string
                | undefined;
            if (r?.status === 409 && typeof detail === "object" && detail?.code === "ROLE_REQUIRED") {
                setPendingCredential(credential);
                setPendingEmail(detail.email || "");
                setCustomName((initName || "").trim() || (detail.suggested_name || "").trim());
                setChosenRole(defRole ?? "student");
                setModalError("");
            } else if (r?.status === 401) {
                const msg = t("تعذّر التحقق من حساب Google. جرّب تاني.", "Couldn't verify your Google account. Please try again.");
                setPendingCredential(null);
                fail(msg);
            } else if (r?.status === 503) {
                const msg = t("الدخول بحساب Google غير مفعّل بعد على السيرفر (أضف GOOGLE_CLIENT_ID).", "Google sign-in isn't configured on the server yet (set GOOGLE_CLIENT_ID).");
                setPendingCredential(null);
                fail(msg);
            } else {
                const msg = getApiErrorMessage(err, t("تعذّر تسجيل الدخول بحساب Google.", "Could not sign in with Google."));
                if (roleToCreate) setModalError(msg);
                else fail(msg);
            }
        } finally {
            setBusy(false);
        }
    }, []);

    useEffect(() => {
        let alive = true;
        void getClientId().then((id) => {
            if (!alive) return;
            setClientId(id);
            setConfigChecked(true);
        });
        return () => { alive = false; };
    }, []);

    useEffect(() => {
        if (!clientId) {
            setGsiReady(false);
            return;
        }
        let alive = true;
        loadGsi()
            .then((gid) => {
                if (!alive || !btnRef.current) return;
                gid.initialize({
                    client_id: clientId,
                    callback: (resp) => {
                        // Always check account existence first; new users get the Name + Role dialog.
                        if (resp.credential) void submit(resp.credential);
                    },
                    ux_mode: "popup",
                    cancel_on_tap_outside: true,
                    context: mode === "signup" ? "signup" : "signin",
                });
                btnRef.current.innerHTML = "";
                const width = Math.min(400, Math.max(220, Math.round(btnRef.current.getBoundingClientRect().width || 340)));
                gid.renderButton(btnRef.current, {
                    type: "standard",
                    theme: resolved === "dark" ? "filled_black" : "outline",
                    size: "large",
                    shape: "pill",
                    text: mode === "signup" ? "signup_with" : "continue_with",
                    logo_alignment: "center",
                    width,
                    locale: lang,
                });
                setGsiReady(true);
            })
            .catch(() => {
                if (alive) setGsiReady(false);
            });
        return () => { alive = false; };
    }, [clientId, lang, resolved, mode, submit]);

    const handleUnconfiguredClick = () => {
        onStart?.();
        if (!configChecked) return;
        if (!clientId) {
            onError(
                l(
                    "لتفعيل الدخول بحساب Google: أضف GOOGLE_CLIENT_ID في ملف إعدادات السيرفر (local.env أو .env) وأعد تشغيل الباك إند.",
                    "To enable Google Sign-In: set GOOGLE_CLIENT_ID in the backend env file and restart the server.",
                ),
            );
        } else {
            onError(
                l(
                    "تعذّر تحميل خدمة Google (تأكد من الاتصال بالإنترنت أو إيقاف مانع الإعلانات).",
                    "Could not load Google Identity Services (check your connection or ad-blocker).",
                ),
            );
        }
    };

    const handleCompleteSignup = (e: React.FormEvent) => {
        e.preventDefault();
        if (!pendingCredential) return;
        const trimmed = customName.trim();
        if (trimmed.length < 2) {
            setModalError(l("اكتب اسمك بالكامل (حرفين على الأقل).", "Please enter your full name (at least 2 characters)."));
            return;
        }
        void submit(pendingCredential, chosenRole, trimmed);
    };

    const roles: { value: Role; icon: typeof GraduationCap; label: string; sub: string }[] = [
        {
            value: "student",
            icon: GraduationCap,
            label: l("طالب", "Student"),
            sub: l("أدخل الامتحانات وأشوف درجاتي", "Take oral exams and view my grades"),
        },
        {
            value: "lecturer",
            icon: Presentation,
            label: l("دكتور / محاضر / مدرس", "Doctor / Lecturer / Teacher"),
            sub: l("أنشئ الامتحانات وأتابع الطلاب", "Create exams and review students"),
        },
    ];

    return (
        <div className={className}>
            {header}
            <div className="relative flex justify-center">
                {clientId && (
                    <div
                        ref={btnRef}
                        className={cn(
                            "w-full flex justify-center min-h-[44px]",
                            !gsiReady && "sr-only",
                            busy && "pointer-events-none opacity-50",
                        )}
                    />
                )}
                {(!clientId || !gsiReady) && (
                    <button
                        type="button"
                        disabled={!configChecked || busy}
                        onClick={handleUnconfiguredClick}
                        className="w-full py-3 px-4 rounded-full border border-rule bg-sheet hover:bg-sheet-2 text-ink font-bold text-sm transition-all flex items-center justify-center gap-3 shadow-xs disabled:opacity-60"
                    >
                        <GoogleMark />
                        <span>
                            {mode === "signup"
                                ? l("التسجيل باستخدام Google", "Sign up with Google")
                                : l("المتابعة باستخدام Google", "Continue with Google")}
                        </span>
                    </button>
                )}
                {busy && !pendingCredential && (
                    <div className="absolute inset-0 flex items-center justify-center">
                        <Loader2 className="w-5 h-5 animate-spin text-pen" />
                    </div>
                )}
            </div>

            {pendingCredential && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 backdrop-blur-xs p-4"
                    role="dialog"
                    aria-modal="true"
                    aria-label={l("إكمال بيانات الحساب", "Complete account setup")}
                >
                    <form
                        onSubmit={handleCompleteSignup}
                        className="w-full max-w-md rounded-2xl border border-rule bg-paper p-5 sm:p-6 text-ink shadow-float space-y-4 animate-[oiq-fade-in_160ms_ease-out]"
                    >
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <div className="inline-flex items-center gap-2 rounded-full border border-rule bg-sheet px-3 py-1 text-xs font-bold text-ink-2 mb-2">
                                    <GoogleMark />
                                    <span dir="ltr" className="truncate max-w-[15rem]">{pendingEmail}</span>
                                </div>
                                <h2 className="ar-heading text-xl sm:text-2xl font-bold text-ink">
                                    {l("كمّل بيانات حسابك", "Complete Your Profile")}
                                </h2>
                                <p className="text-xs sm:text-sm text-ink-2 mt-0.5">
                                    {l("اكتب اسمك اللي هيظهر في المنصة واختار نوع حسابك.", "Enter your display name and choose your account type.")}
                                </p>
                            </div>
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => setPendingCredential(null)}
                                aria-label={l("إغلاق", "Close")}
                                className="flex size-9 shrink-0 items-center justify-center rounded-full hover:bg-sheet-2 text-ink-2"
                            >
                                <X className="size-4" />
                            </button>
                        </div>

                        {modalError && (
                            <div className="rounded-xl border border-mark/35 bg-mark-wash px-3.5 py-2.5 text-xs sm:text-sm font-bold text-mark">
                                {modalError}
                            </div>
                        )}

                        <div>
                            <label htmlFor="google-full-name" className="block text-sm font-bold text-ink mb-1.5">
                                {l("الاسم بالكامل", "Full Name")}
                            </label>
                            <input
                                id="google-full-name"
                                type="text"
                                required
                                autoFocus
                                maxLength={120}
                                value={customName}
                                onChange={(e) => { setCustomName(e.target.value); setModalError(""); }}
                                placeholder={l("اكتب اسمك الثلاثي", "Enter your full name")}
                                className="auth-light-input w-full px-4 py-3 border border-rule bg-sheet text-ink placeholder:text-field rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium"
                            />
                        </div>

                        <div>
                            <span className="block text-sm font-bold text-ink mb-2">
                                {l("أنت بتسجّل كـ:", "I am signing up as:")}
                            </span>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5" role="radiogroup">
                                {roles.map(({ value, icon: Icon, label, sub }) => {
                                    const active = chosenRole === value;
                                    return (
                                        <button
                                            key={value}
                                            type="button"
                                            role="radio"
                                            aria-checked={active}
                                            disabled={busy}
                                            onClick={() => setChosenRole(value)}
                                            className={cn(
                                                "flex flex-col items-start gap-1 rounded-xl border p-3.5 text-start transition-all",
                                                active
                                                    ? "border-pen bg-sheet shadow-card ring-1 ring-pen"
                                                    : "border-rule bg-sheet/65 hover:border-ink-3",
                                            )}
                                        >
                                            <div className="flex w-full items-center justify-between">
                                                <Icon className={cn("size-5", active ? "text-pen" : "text-ink-3")} aria-hidden />
                                                <span className={cn("size-3.5 rounded-full border", active ? "border-pen bg-pen" : "border-rule-strong/40")} />
                                            </div>
                                            <span className="mt-1 text-sm font-bold text-ink">{label}</span>
                                            <span className="text-xs text-ink-2 leading-snug">{sub}</span>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        <div className="flex items-center gap-2.5 pt-1">
                            <button
                                type="submit"
                                disabled={busy}
                                className="oiq-btn-mint flex-1 py-3 px-4 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2 disabled:opacity-60"
                            >
                                {busy && <Loader2 className="size-4 animate-spin" />}
                                <span>{busy ? l("جاري إنشاء الحساب…", "Creating account…") : l("تأكيد وإنشاء الحساب", "Confirm & Create Account")}</span>
                            </button>
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => setPendingCredential(null)}
                                className="py-3 px-4 rounded-xl border border-rule bg-sheet hover:bg-sheet-2 text-xs sm:text-sm font-bold text-ink-2"
                            >
                                {l("إلغاء", "Cancel")}
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
}
