import { useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpLeft } from "lucide-react";
import { useI18n } from "../../i18n";
import { cn } from "../../lib/utils";
import Logo from "../Logo";
import LanguageToggle, { ThemeToggle } from "../LanguageToggle";
import { LandingMenu } from "./LandingMenu";

type Section = { href: string; label: string };

const linkClass =
    "inline-flex h-9 2xl:h-10 items-center whitespace-nowrap rounded-full px-2 2xl:px-3.5 text-[0.82rem] 2xl:text-[0.92rem] font-bold text-ink-2 transition-colors hover:bg-sheet-2 hover:text-ink";

/**
 * Floating editorial notch navbar for the landing page.
 *
 * Compact spacing below 2xl lets all 8 section links + toggles + Sign In + Create Account
 * fit comfortably at 100% zoom on standard 1280px–1366px laptops (both RTL Arabic and LTR English).
 * A ResizeObserver dynamically measures available space so whenever the viewport, zoom level,
 * or font metrics don't leave enough room, the section links collapse cleanly into LandingMenu
 * without ever clipping "أنشئ حساب" or wrapping "تسجيل الدخول".
 */
export function LandingNav({ sections, loggedIn }: { sections: Section[]; loggedIn: boolean }) {
    const { l, lang } = useI18n();
    const ghost = "text-ink hover:bg-sheet-2 hover:text-ink";

    const navRef = useRef<HTMLElement>(null);
    const logoRef = useRef<HTMLAnchorElement>(null);
    const actionsRef = useRef<HTMLDivElement>(null);
    const measureRef = useRef<HTMLUListElement>(null);
    // Start collapsed so first paint can never overflow on narrow screens.
    const [showLinks, setShowLinks] = useState(false);

    useLayoutEffect(() => {
        const nav = navRef.current;
        const logo = logoRef.current;
        const actions = actionsRef.current;
        const measure = measureRef.current;
        if (!nav || !logo || !actions || !measure) return;

        const check = () => {
            const cs = getComputedStyle(nav);
            const pad = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
            const gap = parseFloat(cs.columnGap) || 0;
            const available = nav.clientWidth - pad - logo.offsetWidth - actions.offsetWidth - gap * 2 - 8;
            setShowLinks(measure.offsetWidth <= available);
        };

        check();
        const ro = new ResizeObserver(check);
        [nav, logo, actions, measure].forEach((el) => ro.observe(el));
        document.fonts?.ready.then(check).catch(() => {});
        return () => ro.disconnect();
    }, [lang, loggedIn]);

    return (
        <header className="fixed inset-x-0 top-2.5 sm:top-3.5 z-50 px-2.5 sm:px-4 xl:px-6 pointer-events-none">
            <nav
                ref={navRef}
                aria-label={l("الرئيسية", "Main")}
                className="relative pointer-events-auto mx-auto flex h-14 sm:h-16 max-w-[86rem] items-center gap-1.5 sm:gap-2.5 2xl:gap-5 overflow-hidden rounded-full border border-rule bg-sheet/92 px-3 sm:px-5 2xl:px-7 text-ink shadow-float backdrop-blur-xl transition-colors duration-300"
            >
                <Link ref={logoRef} to="/" aria-label="OralIQ" className="flex h-10 shrink-0 items-center text-ink">
                    <Logo height={20} className="sm:h-[22px] w-auto" />
                </Link>

                {/* Invisible copy used only to measure exact required width of inline section links */}
                <ul
                    ref={measureRef}
                    aria-hidden
                    className="pointer-events-none invisible absolute top-0 start-0 flex w-max items-center gap-0.5 2xl:gap-1"
                >
                    {sections.map((s) => (
                        <li key={s.href} className="shrink-0">
                            <span className={linkClass}>{s.label}</span>
                        </li>
                    ))}
                </ul>

                {showLinks && (
                    <ul className="flex min-w-0 items-center gap-0.5 2xl:gap-1 mx-auto">
                        {sections.map((s) => (
                            <li key={s.href} className="shrink-0">
                                <a href={s.href} className={linkClass}>
                                    {s.label}
                                </a>
                            </li>
                        ))}
                    </ul>
                )}

                <div className={cn("flex shrink-0 items-center gap-1 sm:gap-1.5", showLinks ? "ms-0" : "ms-auto")}>
                    <div ref={actionsRef} className="flex shrink-0 items-center gap-1 sm:gap-1.5">
                        <LanguageToggle
                            compact
                            className={cn(ghost, "max-[380px]:hidden")}
                            labelClassName="hidden md:inline"
                        />
                        <ThemeToggle className={cn(ghost, "max-[380px]:hidden")} />
                        {loggedIn ? (
                            <Link
                                to="/dashboard"
                                className="oiq-btn-mint ms-0.5 inline-flex h-9 sm:h-10 2xl:h-11 shrink-0 items-center gap-1.5 sm:gap-2 whitespace-nowrap rounded-full ps-3.5 pe-1.5 sm:ps-4 sm:pe-1.5 2xl:ps-5 2xl:pe-2 text-xs sm:text-[0.84rem] 2xl:text-sm font-bold text-[#FAF6F0]"
                            >
                                <span>{l("لوحة التحكم", "Dashboard")}</span>
                                <span className="flex size-6 sm:size-7 shrink-0 items-center justify-center rounded-full bg-white/15 text-white">
                                    <ArrowUpLeft className="size-3.5 sm:size-4 ltr:rotate-90" aria-hidden />
                                </span>
                            </Link>
                        ) : (
                            <>
                                <Link
                                    to="/login"
                                    viewTransition
                                    className="hidden h-9 sm:h-10 shrink-0 items-center whitespace-nowrap rounded-full px-3 2xl:px-4 text-[0.84rem] 2xl:text-sm font-bold text-ink hover:bg-sheet-2 sm:inline-flex"
                                >
                                    {l("تسجيل الدخول", "Sign in")}
                                </Link>
                                <Link
                                    to="/register"
                                    viewTransition
                                    className="oiq-btn-mint ms-0.5 inline-flex h-9 sm:h-10 2xl:h-11 shrink-0 items-center gap-1.5 sm:gap-2 whitespace-nowrap rounded-full ps-3.5 pe-1.5 sm:ps-4 sm:pe-1.5 2xl:ps-5 2xl:pe-2 text-xs sm:text-[0.84rem] 2xl:text-sm font-bold text-[#FAF6F0]"
                                >
                                    <span>{l("أنشئ حساب", "Create account")}</span>
                                    <span className="flex size-6 sm:size-7 shrink-0 items-center justify-center rounded-full bg-white/15 text-white">
                                        <ArrowUpLeft className="size-3.5 sm:size-4 ltr:rotate-90" aria-hidden />
                                    </span>
                                </Link>
                            </>
                        )}
                    </div>
                    {!showLinks && <LandingMenu sections={sections} loggedIn={loggedIn} className={ghost} />}
                </div>
            </nav>
        </header>
    );
}
