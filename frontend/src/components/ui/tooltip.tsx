import * as React from "react";
import { cn } from "../../lib/utils";

/**
 * Small label for icon-only buttons. Shows on hover and on keyboard focus.
 * Purely visual — the button itself must carry the same text as aria-label.
 */
export function Tooltip({ label, children, side = "bottom", className }: { label: string; children: React.ReactNode; side?: "top" | "bottom"; className?: string }) {
    return (
        <span className={cn("group/tip relative inline-flex", className)}>
            {children}
            <span
                aria-hidden
                className={cn(
                    "pointer-events-none absolute start-1/2 z-50 whitespace-nowrap rounded-lg bg-ink px-2.5 py-1 text-xs font-medium text-paper opacity-0 shadow-pop transition-[opacity,transform] duration-150 rtl:translate-x-1/2 ltr:-translate-x-1/2",
                    // Touch screens have no hover and no Esc key; the button keeps its accessible name
                    "pointer-coarse:hidden",
                    side === "bottom" ? "top-full mt-2 -translate-y-1" : "bottom-full mb-2 translate-y-1",
                    "group-hover/tip:translate-y-0 group-hover/tip:opacity-100 group-has-[:focus-visible]/tip:translate-y-0 group-has-[:focus-visible]/tip:opacity-100",
                )}
            >
                {label}
            </span>
        </span>
    );
}
