import * as React from "react";
import { cn } from "../../lib/utils";
import { CountUp } from "../motion";
import { Skeleton } from "./feedback";

/** Numbers ("71%", "6", 91.5) count up once; anything else renders as-is. */
function AnimatedValue({ value }: { value: React.ReactNode }) {
    const text = typeof value === "number" ? String(value) : typeof value === "string" ? value : null;
    const m = text?.match(/^(\d+(?:\.(\d+))?)(%?)$/);
    if (!m) return <>{value}</>;
    return <CountUp to={parseFloat(m[1])} decimals={m[2]?.length ?? 0} suffix={m[3]} duration={1.1} />;
}

/** The base surface: a card lifted off the page with a crisp border and ambient shadow. */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
    return <section className={cn("rounded-[var(--radius-panel)] border border-rule bg-sheet shadow-card", className)} {...props} />;
}

interface PanelHeaderProps {
    title: React.ReactNode;
    description?: React.ReactNode;
    actions?: React.ReactNode;
    className?: string;
}

export function PanelHeader({ title, description, actions, className }: PanelHeaderProps) {
    return (
        <header className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-rule px-6 py-4", className)}>
            <div className="min-w-0">
                <h2 className="ar-heading text-lg font-bold text-ink sm:text-xl">{title}</h2>
                {description && <p className="mt-0.5 text-sm font-medium text-ink-2 sm:text-[0.9375rem]">{description}</p>}
            </div>
            {actions && <div className="flex shrink-0 items-center gap-2.5">{actions}</div>}
        </header>
    );
}

/** Ruled rows inside a card. */
export function RuledList({ className, ...props }: React.HTMLAttributes<HTMLUListElement>) {
    return <ul role="list" className={cn("divide-y divide-rule", className)} {...props} />;
}

interface PageHeaderProps {
    title: React.ReactNode;
    description?: React.ReactNode;
    actions?: React.ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
    return (
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div className="min-w-0 max-w-3xl">
                <h1 className="ar-heading text-3xl font-bold leading-tight text-ink sm:text-4xl">{title}</h1>
                {description && <p className="mt-2 text-base font-medium text-ink-2 sm:text-lg">{description}</p>}
            </div>
            {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
        </div>
    );
}

export type StatTone = "pen" | "violet" | "teal" | "warn" | "mark" | "pass";

const toneChip: Record<StatTone, string> = {
    pen: "bg-pen-wash text-pen",
    violet: "bg-violet-wash text-violet",
    teal: "bg-teal-wash text-teal",
    warn: "bg-warn-wash text-warn",
    mark: "bg-mark-wash text-mark",
    pass: "bg-pass-wash text-pass",
};

export interface StatItem {
    label: React.ReactNode;
    value: React.ReactNode;
    hint?: React.ReactNode;
    icon?: React.ComponentType<{ className?: string }>;
    tone?: StatTone;
}

export function StatStrip({ items, loading = false, className }: { items: StatItem[]; loading?: boolean; className?: string }) {
    const cols = items.length === 3 ? "lg:grid-cols-3" : items.length === 2 ? "lg:grid-cols-2" : "lg:grid-cols-4";
    return (
        <dl className={cn("grid grid-cols-2 gap-3 sm:gap-4", cols, className)} aria-busy={loading || undefined}>
            {items.map((item, i) => {
                const Icon = item.icon;
                return (
                    <div
                        key={i}
                        className={cn(
                            "@container rounded-[var(--radius-panel)] border border-rule bg-sheet p-5 shadow-card",
                            items.length % 2 === 1 && i === items.length - 1 && "col-span-2 lg:col-span-1",
                        )}
                    >
                        <dt className="flex items-start justify-between gap-3 text-sm font-bold text-ink-2 sm:text-[0.95rem]">
                            <span>{item.label}</span>
                            {Icon && (
                                <span className={cn("flex size-10 shrink-0 items-center justify-center rounded-xl @max-[10.5rem]:hidden [&>svg]:size-5", toneChip[item.tone ?? "pen"])} aria-hidden>
                                    <Icon />
                                </span>
                            )}
                        </dt>
                        {loading ? (
                            <dd className="mt-2.5"><Skeleton className="h-9 w-20" /></dd>
                        ) : (
                            <>
                                <dd className="mt-2.5 font-display text-3xl font-extrabold leading-none text-ink sm:text-4xl"><AnimatedValue value={item.value} /></dd>
                                {item.hint && <dd className="mt-2 text-xs font-bold text-ink-2 sm:text-sm">{item.hint}</dd>}
                            </>
                        )}
                    </div>
                );
            })}
        </dl>
    );
}
