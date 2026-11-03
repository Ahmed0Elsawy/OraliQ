import * as React from "react";
import { AlertCircle, CheckCircle2, Info, RefreshCw, TriangleAlert, WifiOff } from "lucide-react";
import { motion } from "motion/react";
import { cn } from "../../lib/utils";
import { useI18n } from "../../i18n";
import { Button } from "./button";

export function Skeleton({ className }: { className?: string }) {
    return <div className={cn("oiq-skeleton rounded-md", className)} aria-hidden />;
}

/** Ruled-row placeholders while a list loads. */
export function ListSkeleton({ rows = 4 }: { rows?: number }) {
    return (
        <div className="divide-y divide-rule" aria-busy aria-live="polite">
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-6 py-4">
                    <Skeleton className="size-10 rounded-full" />
                    <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-2/5" />
                        <Skeleton className="h-3.5 w-1/4" />
                    </div>
                    <Skeleton className="h-8 w-16" />
                </div>
            ))}
        </div>
    );
}

interface EmptyStateProps {
    icon?: React.ReactNode;
    title: React.ReactNode;
    body?: React.ReactNode;
    action?: React.ReactNode;
    className?: string;
}

export function EmptyState({ icon, title, body, action, className }: EmptyStateProps) {
    return (
        <div className={cn("flex flex-col items-center px-6 py-14 text-center", className)}>
            {icon && (
                <div className="mb-4 flex size-14 items-center justify-center rounded-2xl border border-rule-strong bg-pen-wash text-ink [&>svg]:size-6">
                    {icon}
                </div>
            )}
            <h3 className="text-lg font-extrabold text-ink sm:text-xl">{title}</h3>
            {body && <p className="mt-1.5 max-w-md text-sm font-semibold text-ink-2 sm:text-base">{body}</p>}
            {action && <div className="mt-5">{action}</div>}
        </div>
    );
}

export function LoadFailed({ onRetry, detail, className }: { onRetry: () => void; detail?: React.ReactNode; className?: string }) {
    const { l } = useI18n();
    return (
        <EmptyState
            className={className}
            icon={<WifiOff />}
            title={l("مقدرناش نجيب البيانات", "We couldn't load this")}
            body={detail || l("غالباً مشكلة في الاتصال أو السيرفر بيجهز. بياناتك محفوظة، جرّب تاني.", "Probably a connection issue or the server is starting. Your data is safe; try again.")}
            action={<Button onClick={onRetry}><RefreshCw className="size-4" aria-hidden />{l("حاول تاني", "Try again")}</Button>}
        />
    );
}

const alertTones = {
    info: { cls: "bg-pen-wash text-ink border-rule-strong", icon: Info, iconCls: "text-pen" },
    success: { cls: "bg-pass-wash text-ink border-pass/35", icon: CheckCircle2, iconCls: "text-pass" },
    warning: { cls: "bg-warn-wash text-ink border-warn/35", icon: TriangleAlert, iconCls: "text-warn" },
    warn: { cls: "bg-warn-wash text-ink border-warn/35", icon: TriangleAlert, iconCls: "text-warn" },
    error: { cls: "bg-mark-wash text-ink border-mark/35", icon: AlertCircle, iconCls: "text-mark" },
};

interface AlertProps {
    tone?: keyof typeof alertTones;
    title?: React.ReactNode;
    children?: React.ReactNode;
    action?: React.ReactNode;
    className?: string;
}

export function Alert({ tone = "info", title, children, action, className }: AlertProps) {
    const t = alertTones[tone];
    const Icon = t.icon;
    return (
        <div
            role={tone === "error" ? "alert" : "status"}
            className={cn("flex items-start gap-3 rounded-[var(--radius-control)] border-2 px-4 py-3.5 text-sm font-semibold", t.cls, className)}
        >
            <Icon className={cn("mt-0.5 size-5 shrink-0", t.iconCls)} aria-hidden />
            <div className="min-w-0 flex-1">
                {title && <p className="text-base font-extrabold">{title}</p>}
                {children && <div className={cn("font-semibold text-ink-2", title && "mt-0.5")}>{children}</div>}
            </div>
            {action && <div className="shrink-0">{action}</div>}
        </div>
    );
}

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: React.ReactNode;
    description?: React.ReactNode;
    children?: React.ReactNode;
    footer?: React.ReactNode;
    size?: "sm" | "md" | "lg";
}

/** Native <dialog>: focus trap, Esc to close and top-layer stacking come for free. */
export function Modal({ open, onClose, title, description, children, footer, size = "md" }: ModalProps) {
    const ref = React.useRef<HTMLDialogElement>(null);
    const titleId = React.useId();

    React.useEffect(() => {
        const dlg = ref.current;
        if (!dlg) return;
        if (open && !dlg.open) {
            dlg.showModal();
            dlg.querySelector<HTMLElement>("[data-autofocus]")?.focus();
        }
        if (!open && dlg.open) dlg.close();
    }, [open]);

    return (
        <dialog
            ref={ref}
            aria-labelledby={titleId}
            onCancel={(e) => { e.preventDefault(); onClose(); }}
            onClick={(e) => { if (e.target === ref.current) onClose(); }}
            className={cn(
                "m-auto w-[calc(100%-2rem)] rounded-[var(--radius-panel)] border-2 border-rule-strong bg-sheet p-0 text-ink shadow-pop",
                "backdrop:bg-overlay backdrop:backdrop-blur-[2px] open:animate-[oiq-pop-in_180ms_ease-out]",
                size === "sm" ? "max-w-md" : size === "lg" ? "max-w-3xl" : "max-w-xl",
            )}
        >
            {open && (
                <div className="flex max-h-[min(85vh,760px)] flex-col">
                    <header className={cn("px-6 py-4", (children || footer) && "border-b border-rule")}>
                        <h2 id={titleId} className="text-xl font-extrabold">{title}</h2>
                        {description && <p className="mt-0.5 text-sm font-semibold text-ink-2">{description}</p>}
                    </header>
                    {children && <div className="overflow-y-auto px-6 py-5">{children}</div>}
                    {footer && <footer className="flex flex-wrap justify-end gap-2.5 border-t border-rule px-6 py-4">{footer}</footer>}
                </div>
            )}
        </dialog>
    );
}

interface DrawerProps {
    open: boolean;
    onClose: () => void;
    label: string;
    header?: React.ReactNode;
    children?: React.ReactNode;
    footer?: React.ReactNode;
}

/** Side sheet on the end side of the page — for reviewing one record without losing the list. */
export function Drawer({ open, onClose, label, header, children, footer }: DrawerProps) {
    const ref = React.useRef<HTMLDialogElement>(null);

    React.useEffect(() => {
        const dlg = ref.current;
        if (!dlg) return;
        if (open && !dlg.open) {
            dlg.showModal();
            dlg.querySelector<HTMLElement>("[data-autofocus]")?.focus();
        }
        if (!open && dlg.open) dlg.close();
    }, [open]);

    return (
        <dialog
            ref={ref}
            aria-label={label}
            onCancel={(e) => { e.preventDefault(); onClose(); }}
            onClick={(e) => { if (e.target === ref.current) onClose(); }}
            className={cn(
                "fixed inset-y-0 m-0 ms-auto h-dvh max-h-dvh w-full max-w-2xl border-s-2 border-rule-strong bg-sheet p-0 text-ink shadow-pop",
                "backdrop:bg-overlay open:animate-[oiq-fade-in_160ms_ease-out]",
            )}
        >
            {open && (
                <div className="print-expand flex h-full flex-col">
                    {header && <div className="shrink-0 border-b border-rule px-5 py-3.5 sm:px-7">{header}</div>}
                    <div className="print-expand flex-1 overflow-y-auto px-5 py-6 sm:px-7">{children}</div>
                    {footer && <div className="flex shrink-0 flex-wrap items-center justify-between gap-2.5 border-t border-rule px-5 py-3.5 sm:px-7 print:hidden">{footer}</div>}
                </div>
            )}
        </dialog>
    );
}

interface SegmentedProps<T extends string> {
    value: T;
    onChange: (v: T) => void;
    options: { value: T; label: React.ReactNode }[];
    label: string;
    className?: string;
}

export function Segmented<T extends string>({ value, onChange, options, label, className }: SegmentedProps<T>) {
    const pillId = React.useId();
    const group = React.useRef<HTMLDivElement>(null);
    const onKeyDown = (e: React.KeyboardEvent) => {
        const rtl = getComputedStyle(e.currentTarget).direction === "rtl";
        const step = { ArrowRight: rtl ? -1 : 1, ArrowLeft: rtl ? 1 : -1, ArrowDown: 1, ArrowUp: -1 }[e.key];
        const at = options.findIndex((o) => o.value === value);
        const next = e.key === "Home" ? 0 : e.key === "End" ? options.length - 1 : step != null ? (at + step + options.length) % options.length : -1;
        if (next < 0) return;
        e.preventDefault();
        onChange(options[next].value);
        const btn = group.current?.querySelectorAll<HTMLButtonElement>("[role=radio]")[next];
        btn?.focus();
        btn?.scrollIntoView({ block: "nearest", inline: "nearest" });
    };
    return (
        <div
            ref={group}
            role="radiogroup"
            aria-label={label}
            onKeyDown={onKeyDown}
            className={cn("inline-flex max-w-full overflow-x-auto rounded-[var(--radius-control)] border-2 border-rule-strong bg-sheet-2 p-1 [scrollbar-width:none]", className)}
        >
            {options.map((o, i) => {
                const active = o.value === value;
                return (
                    <button
                        key={o.value}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        tabIndex={active || (i === 0 && !options.some((x) => x.value === value)) ? 0 : -1}
                        onClick={() => onChange(o.value)}
                        className={cn(
                            "relative shrink-0 whitespace-nowrap rounded-[8px] px-3.5 py-2 text-sm font-extrabold transition-colors",
                            active ? "text-ink" : "text-ink-2 hover:text-ink",
                        )}
                    >
                        {active && (
                            <motion.span
                                layoutId={`seg-${pillId}`}
                                transition={{ type: "spring", stiffness: 420, damping: 34 }}
                                className="absolute inset-0 rounded-[8px] bg-sheet shadow-[0_1px_3px_rgba(0,0,0,0.14)] ring-1 ring-rule-strong"
                                aria-hidden
                            />
                        )}
                        <span className="relative">{o.label}</span>
                    </button>
                );
            })}
        </div>
    );
}
