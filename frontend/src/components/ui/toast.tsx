import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, X } from "lucide-react";
import { cn } from "../../lib/utils";

type ToastTone = "success" | "error";
interface ToastItem { id: number; message: string; tone: ToastTone }

const ToastContext = createContext<((message: string, tone?: ToastTone) => void) | null>(null);

/**
 * Short confirmations after an action ("Published", "Link copied").
 * One polite live region, bottom of the screen, auto-dismiss — never blocks the page.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [items, setItems] = useState<ToastItem[]>([]);
    const nextId = useRef(1);
    const regionRef = useRef<HTMLDivElement>(null);

    // Native <dialog>s live in the browser's top layer; a z-index can't beat them.
    // The region is a manual popover, re-shown on each toast so it stacks above any open dialog.
    useEffect(() => {
        const el = regionRef.current as (HTMLDivElement & { showPopover?: () => void; hidePopover?: () => void }) | null;
        if (!el?.showPopover) return;
        try {
            if (el.matches(":popover-open")) el.hidePopover?.();
            if (items.length) el.showPopover();
        } catch { /* popover unsupported — falls back to z-index */ }
    }, [items]);

    const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((t) => t.id !== id)), []);

    const toast = useCallback((message: string, tone: ToastTone = "success") => {
        const id = nextId.current++;
        setItems((xs) => [...xs.slice(-2), { id, message, tone }]);
        setTimeout(() => dismiss(id), tone === "error" ? 6000 : 3500);
    }, [dismiss]);

    const value = useMemo(() => toast, [toast]);

    return (
        <ToastContext.Provider value={value}>
            {children}
            <div
                ref={regionRef}
                popover="manual"
                aria-live="polite"
                role="status"
                className="pointer-events-none fixed inset-x-0 top-auto bottom-4 z-[100] m-0 flex w-full flex-col items-center gap-2 overflow-visible border-0 bg-transparent px-4"
            >
                {items.map((t) => {
                    const Icon = t.tone === "success" ? CheckCircle2 : AlertCircle;
                    return (
                        <div
                            key={t.id}
                            className="pointer-events-auto flex max-w-md items-center gap-3 rounded-[var(--radius-control)] bg-ink px-4 py-3 text-sm font-medium text-paper shadow-pop animate-[oiq-pop-in_180ms_ease-out]"
                        >
                            <Icon className={cn("size-[18px] shrink-0", t.tone === "success" ? "text-pass" : "text-mark")} aria-hidden />
                            <span className="flex-1">{t.message}</span>
                            <button type="button" onClick={() => dismiss(t.id)} className="-me-1 rounded p-1 opacity-70 hover:opacity-100" aria-label="Dismiss">
                                <X className="size-4" aria-hidden />
                            </button>
                        </div>
                    );
                })}
            </div>
        </ToastContext.Provider>
    );
}

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used inside ToastProvider");
    return ctx;
}
