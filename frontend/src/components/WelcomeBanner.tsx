import * as React from "react";
import { motion } from "motion/react";
import { cn } from "../lib/utils";

/** Buttons styled for the banner's warm espresso surface. */
export const onDark = {
    primary:
        "border border-[#E3A458]/45 bg-[#6F4E37] text-[#FAF6F0] font-bold shadow-[0_12px_28px_-8px_rgba(56,41,31,0.65)] hover:bg-[#5A3E2B] hover:border-[#E3A458]/70",
    secondary:
        "border border-[#FAF6F0]/25 bg-[#FAF6F0]/10 text-[#FAF6F0] font-bold hover:border-[#FAF6F0]/45 hover:bg-[#FAF6F0]/15",
};

export type BannerMood = "calm" | "attention" | "done";

const glows: Record<BannerMood, [string, string]> = {
    calm: ["rgba(227, 164, 88, 0.22)", "rgba(111, 78, 55, 0.34)"],
    attention: ["rgba(241, 180, 90, 0.28)", "rgba(111, 78, 55, 0.28)"],
    done: ["rgba(71, 201, 139, 0.22)", "rgba(111, 78, 55, 0.28)"],
};

const softGlows: Record<BannerMood, [string, string]> = {
    calm: ["rgba(111, 78, 55, 0.14)", "rgba(227, 164, 88, 0.10)"],
    attention: ["rgba(241, 180, 90, 0.16)", "rgba(111, 78, 55, 0.10)"],
    done: ["rgba(35, 107, 72, 0.14)", "rgba(111, 78, 55, 0.10)"],
};

interface WelcomeBannerProps {
    title: React.ReactNode;
    description?: React.ReactNode;
    actions?: React.ReactNode;
    aside?: React.ReactNode;
    mood?: BannerMood;
    variant?: "navy" | "bright";
    className?: string;
}

export function WelcomeBanner({ title, description, actions, aside, mood = "calm", variant = "navy", className }: WelcomeBannerProps) {
    const bright = variant === "bright";
    const [a, b] = (bright ? softGlows : glows)[mood];
    return (
        <motion.section
            initial={{ opacity: 0, y: 18, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            data-mood={mood}
            className={cn(
                "relative isolate mb-8 overflow-hidden rounded-[24px] px-5 py-7 sm:px-10 sm:py-10",
                bright
                    ? "border border-rule bg-sheet text-ink shadow-card"
                    : "oiq-noise border border-[#FAF6F0]/14 bg-[#1F1510] text-[#FAF6F0] shadow-float",
                className,
            )}
        >
            <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
                <div
                    className="absolute -inset-[60%] transition-[background] duration-1000 motion-safe:animate-[oiq-glow-spin_40s_linear_infinite]"
                    style={{ background: `radial-gradient(32% 38% at 70% 30%, ${a}, transparent 70%), radial-gradient(30% 35% at 30% 70%, ${b}, transparent 70%)` }}
                />
            </div>

            <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div className="max-w-2xl min-w-0">
                    <h1 className={cn("ar-heading break-words text-2xl font-bold leading-tight sm:text-4xl", bright ? "text-ink" : "text-[#FAF6F0]")}>{title}</h1>
                    {description && <p className={cn("ar-body mt-2.5 text-sm font-medium leading-relaxed sm:mt-3 sm:text-lg", bright ? "text-ink-2" : "text-[#FAF6F0]/80")}>{description}</p>}
                    {actions && <div className="mt-5 flex flex-wrap gap-3 sm:mt-6">{actions}</div>}
                </div>
                {aside && (
                    <motion.div
                        initial={{ opacity: 0, x: -24 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.25 }}
                        className="relative shrink-0"
                    >
                        {aside}
                    </motion.div>
                )}
            </div>
        </motion.section>
    );
}
