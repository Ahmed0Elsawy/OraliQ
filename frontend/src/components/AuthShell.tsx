import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import Logo, { LogoMark } from "./Logo";
import LanguageToggle, { ThemeToggle } from "./LanguageToggle";
import { useI18n } from "../i18n";
import { COMPANY } from "../content/company";

/**
 * Clean, Photo-Free AuthShell (Inspired by ahmedali.online/ar):
 * - Zero stock photos!
 * - Prominent OralIQ Logo Mark + Wordmark + Tactile Registration / Login Box.
 */
export function AuthShell({ children }: { children: React.ReactNode; scene?: "signin" | "signup" }) {
    const { l } = useI18n();

    return (
        <div
            style={{
                background: "radial-gradient(ellipse at 50% 20%, rgba(207,247,238,0.12) 0%, transparent 65%)",
            }}
            className="flex min-h-dvh flex-col justify-between bg-paper px-4 py-6 text-ink sm:px-8"
        >
            {/* Top Navigation Bar */}
            <header className="mx-auto flex w-full max-w-[76rem] items-center justify-between rounded-full border-2 border-rule-strong bg-sheet px-5 py-2.5 shadow-card">
                <Link
                    to="/"
                    aria-label="OralIQ"
                    className="inline-flex items-center gap-2.5 text-sm font-bold text-ink transition-opacity hover:opacity-80"
                >
                    <ArrowRight className="size-4 ltr:rotate-180" aria-hidden />
                    <span>{l("العودة للرئيسية", "Back to Home")}</span>
                </Link>
                <div className="flex items-center gap-1.5">
                    <LanguageToggle compact />
                    <ThemeToggle />
                </div>
            </header>

            {/* Centered Logo + Tactile Auth Box */}
            <main className="mx-auto my-8 flex w-full max-w-[31rem] flex-col items-center justify-center">
                {/* Prominent Logo Header in place of old photos */}
                <Link
                    to="/"
                    aria-label="OralIQ"
                    className="mb-6 flex flex-col items-center gap-3 text-center group"
                >
                    <span className="flex size-16 items-center justify-center rounded-2xl border-2 border-[#004D5A] bg-[#CFF7EE] text-[#04323A] shadow-[4px_4px_0px_0px_#004D5A] transition-transform group-hover:-translate-y-0.5">
                        <LogoMark size={34} />
                    </span>
                    <Logo height={28} className="text-ink" />
                </Link>

                {/* Tactile Login / Registration Box */}
                <div className="w-full rounded-3xl border-2 border-rule-strong bg-sheet p-6 shadow-[6px_6px_0px_0px_#004D5A] sm:p-9">
                    {children}
                </div>
            </main>

            {/* Minimal Footer */}
            <footer className="text-center text-xs font-bold text-ink-2">
                © 2026 {COMPANY.name} — {l("منتج من", "A product by")} {COMPANY.maker}
            </footer>
        </div>
    );
}
