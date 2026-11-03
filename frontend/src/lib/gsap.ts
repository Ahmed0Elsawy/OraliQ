import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, useGSAP);

if (typeof window !== "undefined") {
    ScrollTrigger.config({
        ignoreMobileResize: true,
        autoRefreshEvents: "visibilitychange,DOMContentLoaded,load,resize",
    });
}

/** One easing for scroll-driven scenes, matching motion's EASE (quick out, soft landing). */
export const GSAP_EASE = "power3.out";

/**
 * Runs GSAP animations across both Desktop and Mobile viewports.
 * Always executes `scenes()` so mobile devices (even with battery-saver / reduced-motion flags)
 * display all entrance and scroll-triggered animations reliably.
 */
export function withMotion(scenes: () => void, _still?: () => void) {
    scenes();
}

export { gsap, ScrollTrigger, useGSAP };
