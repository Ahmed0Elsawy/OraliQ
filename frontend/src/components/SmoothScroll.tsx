import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import type Lenis from "lenis";

let lenis: Lenis | null = null;
let refresh: (() => void) | null = null;

/** Scroll to an element or position through Lenis when it is running (falls back to native). */
export function scrollToTarget(target: string | number | HTMLElement, offset = -88) {
    if (lenis) lenis.scrollTo(target, { offset });
    else if (typeof target === "number") window.scrollTo({ top: target });
    else (typeof target === "string" ? document.querySelector(target) : target)?.scrollIntoView();
}

/**
 * Site-wide smooth scrolling (Lenis), driven by GSAP's ticker so ScrollTrigger
 * animations and the scroll position never drift apart.
 * Both libraries load after the first paint, so they never delay the page itself.
 * Lenis turns smoothing off by itself when the visitor prefers reduced motion,
 * and it never hijacks scrolling inside dialogs, drawers or marked panels.
 */
export function SmoothScroll() {
    const { pathname } = useLocation();

    useEffect(() => {
        let cancelled = false;
        let stop = () => {};
        Promise.all([import("lenis"), import("../lib/gsap")]).then(([{ default: LenisCtor }, { gsap, ScrollTrigger }]) => {
            if (cancelled) return;
            lenis = new LenisCtor({
                anchors: { offset: -88 },
                prevent: (node) => !!node.closest?.("dialog, [data-lenis-prevent]"),
            });
            lenis.on("scroll", ScrollTrigger.update);
            const tick = (time: number) => lenis?.raf(time * 1000);
            gsap.ticker.add(tick);
            gsap.ticker.lagSmoothing(0);
            refresh = () => ScrollTrigger.refresh();
            stop = () => { gsap.ticker.remove(tick); lenis?.destroy(); lenis = null; refresh = null; };
        });
        return () => { cancelled = true; stop(); };
    }, []);

    // A new page starts at the top, and scroll-driven animations re-measure it
    useEffect(() => {
        lenis?.scrollTo(0, { immediate: true });
        const id = requestAnimationFrame(() => refresh?.());
        return () => cancelAnimationFrame(id);
    }, [pathname]);

    return null;
}
