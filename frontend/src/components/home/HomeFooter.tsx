import { Link } from "react-router-dom";
import { useI18n } from "../../i18n";
import Logo from "../Logo";
import { COMPANY, telHref } from "../../content/company";

/**
 * The footer: Deep Warm Espresso (#18110D) with giant architectural wordmark across the bottom.
 */
export function HomeFooter({ sections }: { sections: { href: string; label: string }[] }) {
    const { l } = useI18n();
    const head = "mb-4 font-display text-base font-bold text-[#E3A458]";

    return (
        <footer className="wb-dark-stage mx-2 sm:mx-4 mb-3 overflow-hidden rounded-b-[24px] sm:rounded-b-[32px] border-t border-[#FAF6F0]/12 text-[#FAF6F0]/85">
            <div className="mx-auto grid max-w-[92rem] grid-cols-1 gap-8 px-5 pt-12 pb-8 sm:grid-cols-2 sm:gap-10 sm:px-10 sm:pt-16 sm:pb-10 md:grid-cols-[1.45fr_1fr_1fr_1fr] lg:px-14">
                <div className="sm:col-span-2 md:col-span-1">
                    <Logo height={26} className="text-[#FAF6F0]" title="OralIQ" />
                    <p className="ar-body mt-4 sm:mt-5 max-w-xs text-sm font-medium leading-[1.8] text-[#FAF6F0]/75">
                        {l(
                            "أول منصة عربية تقدم الامتحانات الشفوي أونلاين بدون تدخل الدكتور عبر 3 موديلات ذكية، مع منع الغش ببصمة الوجه والعين والصوت.",
                            "The first Arabic platform for online oral exams with zero lecturer intervention via 3 AI models and 478-point biometric anti-cheating.",
                        )}
                    </p>
                </div>

                <div>
                    <p className={head}>{l("تواصل معنا", "Contact")}</p>
                    <ul className="space-y-2.5 text-sm font-medium">
                        <li>
                            <a href={`mailto:${COMPANY.email}`} className="ltr inline-block hover:text-[#E3A458]">
                                {COMPANY.email}
                            </a>
                        </li>
                        {COMPANY.phone && (
                            <li>
                                <a href={telHref(COMPANY.phone)} className="ltr inline-block tabular hover:text-[#E3A458]">
                                    {COMPANY.phone}
                                </a>
                            </li>
                        )}
                        {COMPANY.location.ar && <li>{l(COMPANY.location.ar, COMPANY.location.en)}</li>}
                    </ul>
                </div>

                <nav aria-label={l("أقسام الصفحة", "Page sections")}>
                    <p className={head}>{l("أقسام الموقع", "Sections")}</p>
                    <ul className="space-y-2.5 text-sm font-medium">
                        {sections.map((s) => (
                            <li key={s.href}>
                                <a href={s.href} className="hover:text-[#E3A458]">
                                    {s.label}
                                </a>
                            </li>
                        ))}
                    </ul>
                </nav>

                <nav aria-label={l("الحساب", "Account")}>
                    <p className={head}>{l("ابدأ الآن", "Get Started")}</p>
                    <ul className="space-y-2.5 text-sm font-medium">
                        <li>
                            <Link to="/register" className="hover:text-[#E3A458]">
                                {l("إنشاء حساب جديد", "Create Account")}
                            </Link>
                        </li>
                        <li>
                            <Link to="/login" className="hover:text-[#E3A458]">
                                {l("تسجيل الدخول", "Sign In")}
                            </Link>
                        </li>
                    </ul>
                </nav>
            </div>

            {/* Giant Architectural Wordmark */}
            <div className="mx-auto max-w-[92rem] px-5 pt-2 pb-4 sm:px-10 lg:px-14">
                <div
                    aria-hidden
                    className="wb-num select-none text-center font-extrabold leading-[0.82] tracking-tighter text-[#FAF6F0]/[0.06] text-[clamp(3.75rem,17vw,15.5rem)]"
                >
                    ORALIQ
                </div>
            </div>

            <div className="border-t border-[#FAF6F0]/10 bg-[#140E0A]">
                <div className="mx-auto flex max-w-[92rem] flex-wrap items-center justify-between gap-2 px-5 py-5 text-xs font-bold text-[#FAF6F0]/65 sm:px-10 lg:px-14">
                    <p>© 2026 {COMPANY.name} — All Rights Reserved.</p>
                    <p>
                        {l("تطوير وتصميم", "Crafted by")}{" "}
                        <span className="text-[#E3A458]">{COMPANY.maker}</span>
                    </p>
                </div>
            </div>
        </footer>
    );
}
