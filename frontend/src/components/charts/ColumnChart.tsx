import { useId, useState } from "react";
import { cn } from "../../lib/utils";
import { useI18n } from "../../i18n";

export interface Column {
    key: string;
    label: string;
    value: number;
    /** Extra lines for the tooltip, e.g. "avg 72%". */
    detail?: string[];
}

interface ColumnChartProps {
    data: Column[];
    /** Accessible name; also the table caption. */
    title: string;
    valueLabel: string;
    /** Show the value on these columns' caps (selective labeling). Defaults to the tallest. */
    labelKeys?: string[];
    height?: number;
    formatValue?: (v: number) => string;
}

function niceMax(v: number) {
    if (v <= 4) return 4;
    const pow = 10 ** Math.floor(Math.log10(v));
    const steps = [1, 2, 2.5, 5, 10];
    for (const s of steps) if (s * pow >= v) return s * pow;
    return 10 * pow;
}

/**
 * Single-series column chart: ≤24px columns, 4px rounded data-end, square baseline,
 * hairline grid, hover/focus tooltip, and a table view for screen readers and anyone who wants numbers.
 */
export function ColumnChart({ data, title, valueLabel, labelKeys, height = 180, formatValue = (v) => String(v) }: ColumnChartProps) {
    const { l } = useI18n();
    const [active, setActive] = useState<string | null>(null);
    const id = useId();
    const max = niceMax(Math.max(0, ...data.map((d) => d.value)));
    const ticks = [0, max / 2, max];
    const tallest = data.reduce((a, b) => (b.value > a.value ? b : a), data[0] ?? { key: "", value: 0 });
    const labeled = new Set(labelKeys ?? (tallest && tallest.value > 0 ? [tallest.key] : []));

    return (
        <figure aria-labelledby={`${id}-cap`} className="min-w-0">
            <figcaption id={`${id}-cap`} className="sr-only">{title}</figcaption>
            <div className="flex min-w-0 gap-3">
                {/* Y axis */}
                <div className="relative w-8 shrink-0 text-xs text-ink-3 tabular" style={{ height }} aria-hidden>
                    {ticks.map((t) => (
                        <span key={t} className="absolute end-0 leading-none" style={{ bottom: `${(t / max) * 100}%`, transform: "translateY(50%)" }}>
                            {formatValue(t)}
                        </span>
                    ))}
                </div>

                {/* Below ~24px a column is too small to point at, so the plot scrolls instead of
                    squeezing: 14 days on a phone would leave 19px columns. */}
                <div className="min-w-0 flex-1 overflow-x-auto pb-1">
                    <div className="relative" style={{ height, minWidth: data.length * 26 }}>
                        {/* Grid */}
                        {ticks.map((t) => (
                            <div key={t} className="absolute inset-x-0 border-t border-rule" style={{ bottom: `${(t / max) * 100}%` }} aria-hidden />
                        ))}
                        {/* Columns */}
                        <div className="absolute inset-0 flex items-end">
                            {data.map((d) => {
                                const pct = max ? (d.value / max) * 100 : 0;
                                const isActive = active === d.key;
                                return (
                                    <div
                                        key={d.key}
                                        tabIndex={0}
                                        role="img"
                                        aria-label={`${d.label}: ${formatValue(d.value)} ${valueLabel}${d.detail ? `، ${d.detail.join("، ")}` : ""}`}
                                        onMouseEnter={() => setActive(d.key)}
                                        onMouseLeave={() => setActive((a) => (a === d.key ? null : a))}
                                        onFocus={() => setActive(d.key)}
                                        onBlur={() => setActive((a) => (a === d.key ? null : a))}
                                        className="group relative flex h-full flex-1 cursor-default flex-col items-center justify-end rounded-sm outline-offset-0"
                                    >
                                        {(labeled.has(d.key) || isActive) && d.value > 0 && (
                                            <span className="mb-1 text-xs font-semibold text-ink tabular">{formatValue(d.value)}</span>
                                        )}
                                        <div
                                            className={cn("w-full max-w-6 rounded-t bg-chart transition-opacity", active && !isActive && "opacity-45")}
                                            style={{ height: d.value > 0 ? `max(${pct}%, 4px)` : 0 }}
                                        />
                                        {isActive && (
                                            <div className="pointer-events-none absolute bottom-full z-10 mb-2 min-w-36 whitespace-nowrap rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-2 text-start text-sm shadow-pop">
                                                <p className="font-semibold">{d.label}</p>
                                                <p className="text-ink-2">{formatValue(d.value)} {valueLabel}</p>
                                                {d.detail?.map((x) => <p key={x} className="text-ink-3">{x}</p>)}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                    {/* X labels */}
                    <div className="mt-2 flex text-xs text-ink-3" style={{ minWidth: data.length * 26 }} aria-hidden>
                        {data.map((d, i) => (
                            <span key={d.key} className="flex-1 truncate text-center">
                                {data.length > 8 && i % 2 === 1 ? "" : d.label}
                            </span>
                        ))}
                    </div>
                </div>
            </div>

            <details className="mt-4 text-sm">
                <summary className="cursor-pointer text-ink-2 hover:text-ink">{l("عرض البيانات كجدول", "Show as table")}</summary>
                <table className="mt-2 w-full text-start">
                    <caption className="sr-only">{title}</caption>
                    <tbody className="divide-y divide-rule">
                        {data.map((d) => (
                            <tr key={d.key}>
                                <th scope="row" className="py-1.5 text-start font-normal text-ink-2">{d.label}</th>
                                <td className="py-1.5 text-end tabular">{formatValue(d.value)}</td>
                                {data.some((x) => x.detail) && <td className="py-1.5 text-end text-ink-3">{d.detail?.join("، ")}</td>}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </details>
        </figure>
    );
}
