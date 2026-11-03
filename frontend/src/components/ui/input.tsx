import * as React from "react";
import { cn } from "../../lib/utils";
import { useI18n } from "../../i18n";

const controlBase = cn(
    "w-full rounded-[var(--radius-control)] border-2 border-rule-strong bg-sheet text-ink text-base font-semibold",
    "placeholder:text-ink-3/75 placeholder:font-medium transition-[border-color,box-shadow] duration-150",
    "hover:border-ink-2 focus:border-pen focus:outline-none focus:ring-3 focus:ring-pen/15",
    "disabled:opacity-60 disabled:cursor-not-allowed",
    "aria-[invalid=true]:border-mark aria-[invalid=true]:focus:ring-mark/15",
);

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
    icon?: React.ReactNode;
    /** Reserve room on the end side for an inline button (e.g. show password). */
    trailing?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, icon, trailing = false, ...props }, ref) => {
    // Padding is physical and follows the *page* direction, so an LTR field (email)
    // inside an Arabic form keeps its icon and text from overlapping.
    const { dir } = useI18n();
    const rtl = dir === "rtl";
    const startPad = icon ? (rtl ? "pr-11" : "pl-11") : (rtl ? "pr-4" : "pl-4");
    const endPad = trailing ? (rtl ? "pl-11" : "pr-11") : (rtl ? "pl-4" : "pr-4");
    const field = <input ref={ref} className={cn(controlBase, "h-12", startPad, endPad, className)} {...props} />;
    if (!icon) return field;
    return (
        <div className="relative">
            <span className={cn("pointer-events-none absolute inset-y-0 flex items-center text-ink-2 [&>svg]:size-[19px]", rtl ? "right-3.5" : "left-3.5")}>
                {icon}
            </span>
            {field}
        </div>
    );
});
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
    ({ className, ...props }, ref) => (
        <textarea ref={ref} className={cn(controlBase, "min-h-28 px-4 py-3 leading-relaxed resize-y", className)} {...props} />
    ),
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
    ({ className, children, ...props }, ref) => (
        <select ref={ref} className={cn(controlBase, "h-12 px-4", className)} {...props}>
            {children}
        </select>
    ),
);
Select.displayName = "Select";

interface FieldProps {
    label: React.ReactNode;
    htmlFor: string;
    hint?: React.ReactNode;
    error?: React.ReactNode;
    action?: React.ReactNode;
    trailing?: React.ReactNode;
    className?: string;
    children: React.ReactNode;
}

export function Field({ label, htmlFor, hint, error, action, trailing, className, children }: FieldProps) {
    const noteId = error ? `${htmlFor}-error` : hint ? `${htmlFor}-hint` : null;
    let control = children;
    if (React.isValidElement<{ "aria-describedby"?: string; "aria-invalid"?: boolean }>(children)) {
        const own = (children.props["aria-describedby"] || "").split(" ").filter((id) => id && id !== `${htmlFor}-hint` && id !== `${htmlFor}-error`);
        const describedBy = [...own, noteId].filter(Boolean).join(" ") || undefined;
        control = React.cloneElement(children, { "aria-describedby": describedBy, "aria-invalid": error ? true : children.props["aria-invalid"] });
    }
    return (
        <div className={cn("flex flex-col gap-2", className)}>
            <div className="flex items-center justify-between gap-3">
                <label htmlFor={htmlFor} className="text-[0.95rem] font-extrabold text-ink">{label}</label>
                {action || trailing}
            </div>
            {control}
            {error ? (
                <p id={`${htmlFor}-error`} className="text-sm font-bold text-mark">{error}</p>
            ) : hint ? (
                <p id={`${htmlFor}-hint`} className="text-sm font-semibold text-ink-2">{hint}</p>
            ) : null}
        </div>
    );
}
