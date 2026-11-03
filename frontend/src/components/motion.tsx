import * as React from "react";
import {
    animate, motion, useInView, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform,
} from "motion/react";
import { cn } from "../lib/utils";

/** One easing for the whole site: quick out, soft landing. */
export const EASE = [0.22, 1, 0.36, 1] as const;

// Used only for live dashboard figures. avoid-ai-design-ignore-file: M5
/** Counts from 0 to `to` the first time it is seen. */
export function CountUp({ to, decimals = 0, duration = 1.4, suffix = "", className }: { to: number; decimals?: number; duration?: number; suffix?: string; className?: string }) {
    const ref = React.useRef<HTMLSpanElement>(null);
    const inView = useInView(ref, { once: true, amount: 0.6 });
    const reduce = useReducedMotion();
    const value = useMotionValue(0);
    const [text, setText] = React.useState((0).toFixed(decimals));

    React.useEffect(() => value.on("change", (v) => setText(v.toFixed(decimals))), [value, decimals]);
    React.useEffect(() => {
        if (!inView) return;
        if (reduce) { value.set(to); return; }
        const controls = animate(value, to, { duration, ease: EASE });
        return () => controls.stop();
    }, [inView, reduce, to, duration, value]);

    return <span ref={ref} className={className}>{text}{suffix}</span>;
}

/** Thin reading-progress bar pinned to the top of the page. */
export function ScrollProgress({ className }: { className?: string }) {
    const { scrollYProgress } = useScroll();
    const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 30, mass: 0.3 });
    return (
        <motion.div
            aria-hidden
            style={{ scaleX }}
            className={cn("fixed inset-x-0 top-0 z-50 h-[3px] origin-[0%] bg-pen rtl:origin-[100%]", className)}
        />
    );
}

/**
 * Scroll-linked value for an element: 0 when it enters the bottom of the screen,
 * 1 when its centre reaches the centre. Handy for tilt/scale reveals.
 */
export function useEnterProgress<T extends HTMLElement>() {
    const ref = React.useRef<T>(null);
    const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "center center"] });
    return { ref, progress: scrollYProgress };
}

/** True on devices with a real mouse (not touch) and no reduced-motion preference. */
function canHover() {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(hover: hover) and (pointer: fine)").matches
        && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Pulls its child a few pixels toward the pointer — used once, on the main CTA. */
export function Magnetic({ children, strength = 10, className }: { children: React.ReactNode; strength?: number; className?: string }) {
    const x = useSpring(0, { stiffness: 220, damping: 16 });
    const y = useSpring(0, { stiffness: 220, damping: 16 });
    const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
        if (!canHover()) return;
        const r = e.currentTarget.getBoundingClientRect();
        x.set(((e.clientX - r.left) / r.width - 0.5) * strength * 2);
        y.set(((e.clientY - r.top) / r.height - 0.5) * strength * 2);
    };
    return (
        <motion.div style={{ x, y }} onPointerMove={onMove} onPointerLeave={() => { x.set(0); y.set(0); }} className={cn("inline-flex", className)}>
            {children}
        </motion.div>
    );
}

/** Hand-drawn tick that draws itself — the "done" moment after submitting. */
export function DrawnCheck({ className, delay = 0.1 }: { className?: string; delay?: number }) {
    return (
        <svg viewBox="0 0 64 64" className={className} aria-hidden fill="none">
            <motion.circle
                cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity={0.25}
                initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, ease: EASE, delay }}
            />
            <motion.path
                d="M20 33.5 28.5 42 45 24" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round"
                initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.45, ease: EASE, delay: delay + 0.45 }}
            />
        </svg>
    );
}

export { motion, useScroll, useTransform, useSpring, useReducedMotion };
