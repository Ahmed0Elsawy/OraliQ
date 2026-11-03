import * as React from "react";
import { cn } from "../../lib/utils";

export type BadgeTone = "neutral" | "pen" | "pass" | "warn" | "mark" | "violet" | "teal";

const tones: Record<BadgeTone, string> = {
    neutral: "border border-rule-strong/70 bg-pen-wash text-ink",
    pen: "border border-rule-strong bg-pen-wash text-ink",
    pass: "border border-pass/30 bg-pass-wash text-pass",
    warn: "border border-warn/30 bg-warn-wash text-warn",
    mark: "border border-mark/30 bg-mark-wash text-mark",
    violet: "border border-rule-strong/70 bg-violet-wash text-violet",
    teal: "border border-rule-strong/70 bg-teal-wash text-teal",
};

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
    tone?: BadgeTone;
    icon?: React.ReactNode;
}

export function Badge({ tone = "neutral", icon, className, children, ...props }: BadgeProps) {
    return (
        <span
            className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-extrabold leading-tight [&>svg]:size-3.5",
                tones[tone],
                className,
            )}
            {...props}
        >
            {icon}
            {children}
        </span>
    );
}
