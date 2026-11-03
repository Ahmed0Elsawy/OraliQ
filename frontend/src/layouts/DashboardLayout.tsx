import { useState, useEffect, useRef } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
    Award, BarChart3, CalendarCheck, ClipboardList, EyeOff, Inbox, Languages, LayoutDashboard, LogOut, Menu, Moon, Plus, Search, Settings, ShieldAlert, TrendingUp, Users, X,
} from "lucide-react";
import { cn } from "../lib/utils";
import api from "../lib/api";
import Logo from "../components/Logo";
import LanguageToggle, { ThemeToggle } from "../components/LanguageToggle";
import { Avatar } from "../components/ui/avatar";
import { buttonClasses } from "../components/ui/button";
import { useI18n } from "../i18n";
import { MotionConfig, motion } from "motion/react";
import { usePageTitle } from "../lib/usePageTitle";
import { useTheme } from "../lib/theme";
import { CommandPalette, type Command } from "../components/CommandPalette";
import PaymentReturnNotice from "../components/PaymentReturnNotice";

type Me = { full_name: string; email: string; role: string };

export function DashboardLayout() {
    const { t, l, toggleLang, lang } = useI18n();
    const { toggle: toggleTheme } = useTheme();
    const [paletteOpen, setPaletteOpen] = useState(false);
    const [isOpen, setIsOpen] = useState(false);
    const [user, setUser] = useState<Me | null>(null);
    const [profilePic, setProfilePic] = useState<string | null>(null);
    const location = useLocation();
    const navigate = useNavigate();

    useEffect(() => {
        api.get("/users/me")
            .then((res) => {
                setUser(res.data);
                try {
                    const saved = localStorage.getItem(`profilePic_${res.data.email}`);
                    if (saved) setProfilePic(saved);
                } catch { /* no saved picture */ }
            })
            .catch((err) => {
                const status = err?.response?.status;
                if (status === 401 || status === 403) {
                    localStorage.removeItem("token");
                    navigate("/login", { replace: true });
                }
            });
    }, [navigate]);

    // Close the mobile drawer on Esc (links close it on click)
    useEffect(() => {
        if (!isOpen) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setIsOpen(false); };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [isOpen]);

    const menuButton = useRef<HTMLButtonElement>(null);
    const closeButton = useRef<HTMLButtonElement>(null);
    const wasOpen = useRef(false);
    useEffect(() => {
        if (isOpen) closeButton.current?.focus();
        else if (wasOpen.current && window.matchMedia("(max-width: 767.98px)").matches) menuButton.current?.focus();
        wasOpen.current = isOpen;
    }, [isOpen]);
    useEffect(() => {
        const desktop = window.matchMedia("(min-width: 768px)");
        const onChange = () => { if (desktop.matches) setIsOpen(false); };
        desktop.addEventListener("change", onChange);
        return () => desktop.removeEventListener("change", onChange);
    }, []);

    const handleLogout = () => { localStorage.removeItem("token"); navigate("/login"); };

    const isLecturer = user ? ["lecturer", "hr", "admin"].includes(user.role) : false;

    const navItems = isLecturer
        ? [
            { icon: LayoutDashboard, label: t("nav.overview"), href: "/dashboard" },
            { icon: ClipboardList, label: t("nav.questions"), href: "/dashboard/questions" },
            { icon: BarChart3, label: t("nav.results"), href: "/dashboard/results" },
            { icon: TrendingUp, label: t("nav.analytics"), href: "/dashboard/analytics" },
            { icon: CalendarCheck, label: t("nav.attendance"), href: "/dashboard/attendance" },
            { icon: Users, label: t("nav.students"), href: "/dashboard/students" },
        ]
        : [
            { icon: LayoutDashboard, label: t("nav.overview"), href: "/dashboard" },
            { icon: Inbox, label: l("دعوات الامتحانات", "Exam invites"), href: "/dashboard/messages" },
            { icon: Award, label: t("nav.grades"), href: "/dashboard/grades" },
        ];

    const currentTitle =
        location.pathname === "/dashboard/settings"
            ? t("nav.settings")
            : navItems.find((n) => n.href === location.pathname)?.label;
    usePageTitle(user ? currentTitle : null);

    const pagesGroup = l("الصفحات", "Pages");
    const actionsGroup = l("أوامر", "Actions");
    const commands: Command[] = [
        ...navItems.map((n) => ({ id: n.href, label: n.label, group: pagesGroup, icon: n.icon, to: n.href })),
        { id: "settings", label: t("nav.settings"), group: pagesGroup, icon: Settings, to: "/dashboard/settings" },
        ...(isLecturer ? [
            { id: "new-q", label: l("سؤال جديد", "New question"), group: actionsGroup, icon: Plus, to: "/dashboard/questions?new=1", keywords: "add create اضافة" },
            { id: "review", label: l("الإجابات اللي محتاجة مراجعة", "Answers needing review"), group: actionsGroup, icon: ShieldAlert, to: "/dashboard/results?filter=review" },
            { id: "unpublished", label: l("الدرجات اللي لسه ماتنشرتش", "Unpublished grades"), group: actionsGroup, icon: EyeOff, to: "/dashboard/results?filter=unpublished" },
        ] : []),
        { id: "theme", label: l("تبديل الوضع الليلي/النهاري", "Toggle dark/light mode"), group: actionsGroup, icon: Moon, run: toggleTheme, keywords: "dark light theme" },
        { id: "lang", label: lang === "ar" ? "Switch to English" : "التبديل للعربية", group: actionsGroup, icon: Languages, run: toggleLang, keywords: "language لغة" },
        { id: "logout", label: t("nav.signOut"), group: actionsGroup, icon: LogOut, run: handleLogout },
    ];

    return (
        <div className="min-h-dvh bg-paper text-ink md:flex transition-colors duration-300">
            <a
                href="#main"
                className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-pen focus:px-4 focus:py-2 focus:font-bold focus:text-pen-ink"
            >
                {l("تخطَّ إلى المحتوى", "Skip to content")}
            </a>

            {/* Mobile overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 z-40 bg-overlay animate-[oiq-fade-in_150ms_ease-out] md:hidden"
                    onClick={() => setIsOpen(false)}
                    aria-hidden
                />
            )}

            {/* ── Sidebar ── */}
            <aside
                id="sidebar"
                className={cn(
                    "fixed inset-y-0 start-0 z-50 flex w-[17.5rem] lg:w-[18.25rem] shrink-0 flex-col border-e-2 border-rail-line bg-rail text-rail-ink",
                    "duration-200 ease-out md:sticky md:top-0 md:h-dvh",
                    isOpen ? "transition-transform" : "transition-[transform,visibility] max-md:invisible max-md:ltr:-translate-x-full max-md:rtl:translate-x-full",
                )}
                aria-label={l("القائمة الرئيسية", "Main menu")}
            >
                <div className="flex h-[4.5rem] shrink-0 items-center justify-between border-b border-rail-line px-5">
                    <Link to="/dashboard" aria-label="OralIQ" className="flex h-11 items-center text-rail-ink">
                        <Logo height={25} />
                    </Link>
                    <button
                        ref={closeButton}
                        type="button"
                        className={cn(buttonClasses("ghost", "icon-sm", "text-rail-muted hover:bg-rail-hover hover:text-rail-ink"), "md:hidden")}
                        onClick={() => setIsOpen(false)}
                        aria-label={l("إغلاق القائمة", "Close menu")}
                    >
                        <X className="size-5" aria-hidden />
                    </button>
                </div>

                <div className="px-3.5 pt-3.5 pb-2">
                    <button
                        type="button"
                        onClick={() => setPaletteOpen(true)}
                        className="flex w-full items-center gap-2.5 rounded-[var(--radius-control)] border-2 border-rail-line bg-rail-hover/65 px-3.5 py-2.5 text-sm font-bold text-rail-muted transition-colors hover:border-rule-strong hover:bg-rail-hover hover:text-rail-ink"
                    >
                        <Search className="size-4 text-rail-ink" aria-hidden />
                        <span className="flex-1 text-start">{l("بحث سريع", "Quick search")}</span>
                        <kbd className="rounded-md border border-rail-line bg-rail px-2 py-0.5 text-xs font-extrabold text-rail-ink ltr pointer-coarse:hidden" dir="ltr">Ctrl K</kbd>
                    </button>
                </div>

                <nav className="flex-1 overflow-y-auto px-3.5 py-3">
                    <ul role="list" className="space-y-1">
                        {(user ? navItems : []).map((item) => (
                            <li key={item.href}>
                                <NavItem {...item} active={location.pathname === item.href} onNavigate={() => setIsOpen(false)} />
                            </li>
                        ))}
                    </ul>
                </nav>

                <div className="shrink-0 space-y-1.5 border-t border-rail-line px-3.5 py-3">
                    <NavItem icon={Settings} label={t("nav.settings")} href="/dashboard/settings" active={location.pathname === "/dashboard/settings"} onNavigate={() => setIsOpen(false)} />
                    <div className="flex items-center gap-1.5 px-1 pt-1">
                        <LanguageToggle compact className="font-bold text-rail-ink hover:bg-rail-hover" />
                        <ThemeToggle className="text-rail-ink hover:bg-rail-hover" />
                    </div>
                </div>

                {user && (
                    <div className="m-3.5 mt-0 flex shrink-0 items-center gap-3 rounded-2xl border border-rail-line bg-rail-hover px-3.5 py-3">
                        <Avatar name={user.full_name} src={profilePic} />
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-extrabold text-rail-ink">{user.full_name}</p>
                            <p className="truncate text-xs font-bold text-rail-muted">
                                {isLecturer ? t("auth.role.lecturer") : t("auth.role.student")}
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={handleLogout}
                            className={buttonClasses("ghost", "icon-sm", "text-rail-muted hover:bg-mark-wash hover:text-mark")}
                            aria-label={t("nav.signOut")}
                            title={t("nav.signOut")}
                        >
                            <LogOut className="size-5 rtl:-scale-x-100" aria-hidden />
                        </button>
                    </div>
                )}
            </aside>

            {user && <CommandPalette commands={commands} open={paletteOpen} onOpenChange={setPaletteOpen} />}

            {/* ── Main ── */}
            <div className="flex min-w-0 flex-1 flex-col" inert={isOpen}>
                {/* Mobile top bar */}
                <header className="sticky top-0 z-30 flex h-15 items-center justify-between border-b-2 border-rule bg-paper/95 px-4 backdrop-blur md:hidden">
                    <button
                        ref={menuButton}
                        type="button"
                        className={buttonClasses("secondary", "icon-sm")}
                        onClick={() => setIsOpen(true)}
                        aria-label={l("فتح القائمة", "Open menu")}
                        aria-expanded={isOpen}
                        aria-controls="sidebar"
                    >
                        <Menu className="size-5" aria-hidden />
                    </button>
                    <Link to="/dashboard" className="text-ink">
                        <Logo height={20} title="OralIQ" />
                    </Link>
                    <div className="flex items-center gap-1">
                        <ThemeToggle className="text-ink hover:bg-sheet-2" />
                        <Avatar name={user?.full_name} src={profilePic} size="sm" />
                    </div>
                </header>

                <main id="main" className="mx-auto w-full max-w-[90rem] flex-1 px-4 py-6 sm:px-8 sm:py-9 lg:px-12">
                    <MotionConfig reducedMotion="user">
                        <motion.div
                            key={location.pathname}
                            initial={{ opacity: 0, y: 14 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                        >
                            <PaymentReturnNotice enabled={isLecturer} />
                            <Outlet />
                        </motion.div>
                    </MotionConfig>
                </main>
            </div>
        </div>
    );
}

export default DashboardLayout;

interface NavItemProps {
    icon: typeof Users;
    label: string;
    href: string;
    active: boolean;
    onNavigate: () => void;
}

function NavItem({ icon: Icon, label, href, active, onNavigate }: NavItemProps) {
    return (
        <Link
            to={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
                "relative flex items-center gap-3.5 rounded-[var(--radius-control)] px-3.5 py-3 text-base transition-colors",
                active ? "font-extrabold text-rail-active-ink" : "font-bold text-rail-muted hover:bg-rail-hover hover:text-rail-ink",
            )}
        >
            {active && (
                <motion.span
                    layoutId="nav-active"
                    transition={{ type: "spring", stiffness: 380, damping: 32 }}
                    className="absolute inset-0 rounded-[var(--radius-control)] bg-rail-active shadow-[inset_0_0_0_1.5px_var(--rule-strong)] before:absolute before:inset-y-2 before:start-0 before:w-1.5 before:rounded-full before:bg-rail-indicator"
                    aria-hidden
                />
            )}
            <Icon className="relative size-5 shrink-0" aria-hidden />
            <span className="relative truncate">{label}</span>
        </Link>
    );
}
