import { MotionConfig } from "motion/react";
import { useI18n } from "../i18n";
import { usePageTitle } from "../lib/usePageTitle";
import { LandingNav } from "../components/landing/LandingNav";
import { HomeHero } from "../components/home/HomeHero";
import { HomeAbout } from "../components/home/HomeAbout";
import { HomeSteps } from "../components/home/HomeSteps";
import { HomeVideo } from "../components/home/HomeVideo";
import { HomeClients } from "../components/home/HomeClients";
import { HomePlatform } from "../components/home/HomePlatform";
import { HomePricing } from "../components/home/HomePricing";
import { HomeTestimonials } from "../components/home/HomeTestimonials";
import { HomeContact } from "../components/home/HomeContact";
import { HomeFooter } from "../components/home/HomeFooter";

export default function LandingPage() {
    const { l } = useI18n();
    usePageTitle(l("أول منصة عربية تقدم الامتحانات الشفوي أونلاين", "The first Arabic platform for online oral exams"));
    let loggedIn = false;
    try { loggedIn = !!localStorage.getItem("token"); } catch { /* ignore */ }
    const startHref = loggedIn ? "/dashboard" : "/register";

    const sections = [
        { href: "#about", label: l("عن المنصة", "About Platform") },
        { href: "#how", label: l("الخطوات", "Steps") },
        { href: "#video", label: l("الفيديو التعريفي", "Intro Video") },
        { href: "#clients", label: l("عملاؤنا", "Our Clients") },
        { href: "#integrate", label: l("انضم كـ فيتشر", "Embed Feature") },
        { href: "#pricing", label: l("الباقات", "Pricing") },
        { href: "#testimonials", label: l("آراء العملاء", "Testimonials") },
        { href: "#contact", label: l("تواصل معنا", "Contact Us") },
    ];

    return (
        <MotionConfig reducedMotion="never">
            <div className="home min-h-dvh overflow-x-clip bg-paper text-ink transition-colors duration-300">
                <a
                    href="#main"
                    onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}
                    className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-[70] focus:rounded-full focus:bg-[#6F4E37] focus:px-5 focus:py-2.5 focus:font-bold focus:text-white"
                >
                    {l("تخطَّ إلى المحتوى", "Skip to content")}
                </a>

                <LandingNav sections={sections} loggedIn={loggedIn} />

                <main id="main" tabIndex={-1} className="outline-none">
                    <HomeHero startHref={startHref} />
                    <HomeAbout startHref={startHref} />
                    <HomeSteps />
                    <HomeVideo />
                    <HomeClients />
                    <HomePlatform />
                    <HomePricing startHref={startHref} />
                    <HomeTestimonials />
                    <HomeContact />
                </main>
                <HomeFooter sections={sections} />
            </div>
        </MotionConfig>
    );
}
