import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { useI18n } from "../../i18n";
import { cn } from "../../lib/utils";
import Logo from "../Logo";
import LanguageToggle, { ThemeToggle } from "../LanguageToggle";

/**
 * When the header's section links don't fit (LandingNav measures this), this button opens them in a side sheet,
 * with the account links, language and theme. A native dialog: focus, Escape and the backdrop
 * behave as expected, and Lenis leaves it alone.
 */
export function LandingMenu({ sections, loggedIn, className }: { sections: { href: string; label: string }[]; loggedIn: boolean; className?: string }) {
    const { l } = useI18n();
    const ref = useRef<HTMLDialogElement>(null);
    const [open, setOpen] = useState(false);

    useEffect(() => {
        const d = ref.current;
        if (!d) return;
        if (open && !d.open) d.showModal();
        if (!open && d.open) d.close();
    }, [open]);

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                aria-label={l("القائمة", "Menu")}
                aria-expanded={open}
                className={cn("flex size-10 items-center justify-center shrink-0 rounded-full", className ?? "text-ink hover:bg-sheet")}
            >
                <Menu className="size-5" aria-hidden />
            </button>
            <dialog
                ref={ref}
                onCancel={(e) => { e.preventDefault(); setOpen(false); }}
                onClick={(e) => { if (e.target === ref.current) setOpen(false); }}
                aria-label={l("القائمة", "Menu")}
                className="m-0 ms-auto h-dvh max-h-dvh w-[min(22rem,100%)] bg-sheet p-0 text-ink backdrop:bg-overlay open:animate-[oiq-fade-in_160ms_ease-out]"
            >
                {open && (
                    <div className="flex h-full flex-col gap-6 p-5">
                        <div className="flex items-center justify-between">
                            <Logo height={20} />
                            <button type="button" onClick={() => setOpen(false)} aria-label={l("إغلاق القائمة", "Close menu")} className="flex size-10 items-center justify-center rounded-full hover:bg-sheet-2">
                                <X className="size-5" aria-hidden />
                            </button>
                        </div>
                        <nav aria-label={l("أقسام الصفحة", "Page sections")}>
                            <ul className="divide-y divide-rule border-y border-rule">
                                {sections.map((s) => (
                                    <li key={s.href}><a href={s.href} onClick={() => setOpen(false)} className="block py-3.5 font-display text-lg font-semibold hover:text-pen">{s.label}</a></li>
                                ))}
                            </ul>
                        </nav>
                        <div className="mt-auto grid gap-2">
                            {loggedIn ? (
                                <Link to="/dashboard" className="flex h-12 items-center justify-center rounded-full bg-pen font-semibold text-pen-ink hover:bg-pen-hover">{l("لوحة التحكم", "Dashboard")}</Link>
                            ) : (
                                <>
                                    <Link to="/register" className="flex h-12 items-center justify-center rounded-full bg-pen font-semibold text-pen-ink hover:bg-pen-hover">{l("أنشئ حساب", "Create account")}</Link>
                                    <Link to="/login" className="flex h-12 items-center justify-center rounded-full border border-rule font-semibold hover:border-ink-3">{l("تسجيل الدخول", "Sign in")}</Link>
                                </>
                            )}
                            <div className="flex items-center justify-center gap-1 pt-2"><LanguageToggle compact /><ThemeToggle /></div>
                        </div>
                    </div>
                )}
            </dialog>
        </>
    );
}
