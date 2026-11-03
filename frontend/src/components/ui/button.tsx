import * as React from "react";
import { Link, type LinkProps } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "danger-ghost";
export type ButtonSize = "sm" | "md" | "lg" | "icon" | "icon-sm";

const variants: Record<ButtonVariant, string> = {
    primary:
        "border border-pen bg-pen text-pen-ink shadow-[0_10px_24px_-8px_rgba(111,78,55,0.42)] hover:bg-pen-hover hover:border-pen-hover hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98]",
    secondary:
        "border border-rule-strong bg-sheet text-ink shadow-card hover:border-ink-3 hover:bg-sheet-2 active:scale-[0.98]",
    ghost:
        "border border-transparent text-ink hover:border-rule hover:bg-sheet-2",
    danger:
        "border border-mark bg-mark text-white shadow-sm hover:opacity-92",
    "danger-ghost":
        "border border-mark/30 bg-mark-wash text-mark hover:border-mark",
};

const sizes: Record<ButtonSize, string> = {
    sm: "h-10 px-4 text-sm gap-2",
    md: "h-11 px-5 text-base gap-2",
    lg: "h-12 px-7 text-base gap-2.5",
    icon: "h-11 w-11",
    "icon-sm": "h-10 w-10",
};

export function buttonClasses(variant: ButtonVariant = "primary", size: ButtonSize = "md", className?: string) {
    return cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-[var(--radius-control)] font-bold",
        "transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
        "disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className,
    );
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant = "primary", size = "md", loading = false, disabled, children, type = "button", ...props }, ref) => (
        <button
            ref={ref}
            type={type}
            disabled={disabled || loading}
            aria-busy={loading || undefined}
            className={buttonClasses(variant, size, className)}
            {...props}
        >
            {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
            {children}
        </button>
    ),
);
Button.displayName = "Button";

export function ButtonLink({ variant = "primary", size = "md", className, ...props }: LinkProps & { variant?: ButtonVariant; size?: ButtonSize }) {
    return <Link className={buttonClasses(variant, size, className)} {...props} />;
}
