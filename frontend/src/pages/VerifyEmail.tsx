import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { usePageTitle } from "../lib/usePageTitle";
import { getApiErrorMessage } from "../lib/apiErrors";
import { AuthShell } from "../components/AuthShell";

/** The secret travels in the URL fragment (#token=...), which browsers never send to a server. */
function takeTokenFromUrl(): string {
    const m = /(?:^|[#&])token=([A-Za-z0-9_-]+)/.exec(window.location.hash);
    if (m) {
        // Off the address bar and out of history, so it isn't shared or reopened by accident.
        window.history.replaceState(null, "", window.location.pathname);
    }
    return m ? m[1] : "";
}

/**
 * Completes an e-mail sign-up: the link proves the mailbox, the password proves it is the same
 * person who signed up. Only then does the backend hand out a session.
 */
export default function VerifyEmail() {
    const { l } = useI18n();
    const navigate = useNavigate();
    usePageTitle(l("تأكيد البريد", "Confirm e-mail"));
    const [token] = useState(takeTokenFromUrl);
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [code, setCode] = useState("");
    const [email, setEmail] = useState("");
    const [resent, setResent] = useState("");

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!token || !password) return;
        setBusy(true);
        setError("");
        try {
            const { data } = await api.post("/auth/verify-email", { token, password });
            localStorage.setItem("token", data.access_token);
            navigate("/dashboard", { replace: true });
        } catch (err) {
            const detail = (err as { response?: { data?: { detail?: { code?: string } } } })?.response?.data?.detail;
            setCode(detail?.code || "");
            setError(getApiErrorMessage(err));
        } finally {
            setBusy(false);
        }
    };

    const resend = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email.trim()) return;
        try {
            await api.post("/auth/resend-verification", { email: email.trim() });
            setResent(l("لو ينفع، هيوصلك رابط جديد خلال دقايق.", "If possible, a new link will arrive in a few minutes."));
        } catch (err) {
            setResent(getApiErrorMessage(err));
        }
    };

    const linkDead = !token || code === "LINK_EXPIRED" || code === "LINK_INVALID";

    return (
        <AuthShell>
            <h1 className="text-2xl font-bold">{l("تأكيد البريد الإلكتروني", "Confirm your e-mail")}</h1>

            {!linkDead ? (
                <form onSubmit={submit} className="mt-5 space-y-4">
                    <p className="text-sm text-ink-2 leading-relaxed">
                        {l(
                            "اكتب كلمة المرور اللي اخترتها وانت بتعمل الحساب. لو انت ماعملتش حساب على OralIQ، اقفل الصفحة دي ومتكتبش أي حاجة.",
                            "Enter the password you chose when you created the account. If you didn't sign up for OralIQ, close this page.",
                        )}
                    </p>
                    <input
                        type="password"
                        dir="ltr"
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => { setPassword(e.target.value); setError(""); }}
                        placeholder="••••••••"
                        className="auth-light-input w-full px-4 py-3 border border-rule bg-sheet text-ink rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium"
                    />
                    {error && <p className="rounded-xl border border-mark/35 bg-mark-wash px-4 py-3 text-sm font-bold text-mark">{error}</p>}
                    <button type="submit" disabled={busy || !password}
                        className="oiq-btn-mint w-full py-3.5 px-4 rounded-xl font-bold flex items-center justify-center gap-2 disabled:opacity-60">
                        {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                        {l("تأكيد ودخول", "Confirm and sign in")}
                    </button>
                </form>
            ) : (
                <form onSubmit={resend} className="mt-5 space-y-4">
                    <p className="text-sm text-ink-2 leading-relaxed">
                        {error || l("الرابط ده مش كامل أو مش صالح.", "This link is incomplete or invalid.")}{" "}
                        {l("اكتب بريدك وهنبعتلك رابط جديد.", "Enter your e-mail and we'll send a new link.")}
                    </p>
                    <input
                        type="email"
                        dir="ltr"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="name@university.edu.eg"
                        className="auth-light-input w-full px-4 py-3 border border-rule bg-sheet text-ink rounded-xl focus:ring-2 focus:ring-pen/30 focus:border-pen outline-none font-medium"
                    />
                    <button type="submit" className="oiq-btn-mint w-full py-3.5 px-4 rounded-xl font-bold">
                        {l("ابعت رابط جديد", "Send a new link")}
                    </button>
                    {resent && <p className="text-xs text-ink-2">{resent}</p>}
                </form>
            )}

            <p className="mt-6 text-center text-sm">
                <Link to="/login" className="font-bold text-pen underline underline-offset-4">{l("الرجوع لتسجيل الدخول", "Back to sign in")}</Link>
            </p>
        </AuthShell>
    );
}
