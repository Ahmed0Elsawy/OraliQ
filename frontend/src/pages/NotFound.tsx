import { ButtonLink } from "../components/ui/button";
import Logo from "../components/Logo";
import { useI18n } from "../i18n";
import { usePageTitle } from "../lib/usePageTitle";

export default function NotFound() {
    const { l } = useI18n();
    usePageTitle(l("الصفحة مش موجودة", "Page not found"));
    const loggedIn = (() => { try { return !!localStorage.getItem("token"); } catch { return false; } })();
    return (
        <main className="flex min-h-dvh flex-col items-center justify-center bg-paper px-6 text-center">
            <Logo height={26} className="mb-10" title="OralIQ" />
            <p className="relative flex h-28 w-52 items-center justify-center">
                <svg viewBox="-6 -4 132 88" preserveAspectRatio="none" className="absolute inset-0 h-full w-full -rotate-3 overflow-visible text-pen" aria-hidden>
                    <path d="M92 10C113 17 121 44 102 62C82 80 33 80 14 63C-3 48 6 19 33 9C53 2 80 3 98 15" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" />
                </svg>
                <span className="relative font-display text-6xl font-bold text-ink tabular">404</span>
            </p>
            <h1 className="mt-4 text-2xl font-bold">{l("الصفحة دي مش موجودة", "This page doesn't exist")}</h1>
            <p className="mt-2 max-w-sm text-ink-2">
                {l("ممكن يكون الرابط اتكتب غلط أو اتشال. لو ده رابط امتحان، اطلب من المحاضر يبعته تاني.",
                    "The link may be mistyped or removed. If it's an exam link, ask your lecturer to send it again.")}
            </p>
            <ButtonLink to={loggedIn ? "/dashboard" : "/"} className="mt-8">
                {loggedIn ? l("الرجوع للوحة التحكم", "Back to dashboard") : l("الصفحة الرئيسية", "Home page")}
            </ButtonLink>
        </main>
    );
}
