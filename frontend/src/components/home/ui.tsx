import { cn } from "../../lib/utils";

/** Section titles: portfolio2027-ten.vercel.app scale (ThmanyahSans-Bold + BricolageGrotesque). */
export const H2 = "ar-heading font-display text-[clamp(2.25rem,4.6vw,4.15rem)] font-bold leading-[1.15]";

/** Primary Mocha Espresso Pill CTA button. */
export const BTN = "oiq-btn-mint inline-flex h-13 items-center justify-center gap-3 rounded-full px-7 text-base font-bold";

/** Secondary Warm Alabaster Pill CTA button. */
export const BTN_GHOST = "oiq-btn-white inline-flex h-13 items-center justify-center gap-2.5 rounded-full px-7 text-base font-bold";

/**
 * One band of the page. Alternates `tone="a"` (#FAF9F6 warm alabaster paper) and
 * `tone="b"` (#050608 deep espresso obsidian).
 */
export function Section({ tone, id, className, style, children }: { tone: "a" | "b"; id?: string; className?: string; style?: React.CSSProperties; children: React.ReactNode }) {
    return (
        <section id={id} style={style} className={cn(tone === "a" ? "home-a" : "home-b", id && "scroll-mt-24", className)}>
            {children}
        </section>
    );
}

/** Clean script eyebrow kicker over a section title (no rectangle/pill box around it, matching ahmedali.online/ar). */
export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
    return (
        <p className={cn("ar-script text-lg md:text-2xl font-medium", className)}>
            {children}
        </p>
    );
}
