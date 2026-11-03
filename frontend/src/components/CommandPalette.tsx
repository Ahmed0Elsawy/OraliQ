import * as React from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { cn } from "../lib/utils";
import { useI18n } from "../i18n";

export interface Command {
    id: string;
    label: string;
    hint?: string;
    group: string;
    icon: React.ComponentType<{ className?: string }>;
    /** Route to open, or an action to run. */
    to?: string;
    run?: () => void;
    keywords?: string;
}

/** Arabic-insensitive matching: ignore hamza/ta-marbuta/alef-maqsura differences. */
function norm(s: string) {
    return s.toLowerCase().replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");
}

/**
 * Ctrl+K / ⌘K: jump to any page or run an action without hunting through the menu.
 * Native <dialog> for focus trapping; arrow keys + Enter to choose.
 */
export function CommandPalette({ commands, open, onOpenChange }: { commands: Command[]; open: boolean; onOpenChange: (v: boolean) => void }) {
    const { l } = useI18n();
    const navigate = useNavigate();
    const ref = React.useRef<HTMLDialogElement>(null);
    const [query, setQuery] = React.useState("");
    const [active, setActive] = React.useState(0);

    // Global shortcut
    React.useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                onOpenChange(!open);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, onOpenChange]);

    React.useEffect(() => {
        const dlg = ref.current;
        if (!dlg) return;
        if (open && !dlg.open) { dlg.showModal(); setQuery(""); setActive(0); }
        if (!open && dlg.open) dlg.close();
    }, [open]);

    const q = norm(query.trim());
    const results = q ? commands.filter((c) => norm(`${c.label} ${c.hint ?? ""} ${c.keywords ?? ""}`).includes(q)) : commands;
    const groups = [...new Set(results.map((c) => c.group))];

    const choose = (c: Command) => {
        onOpenChange(false);
        if (c.to) navigate(c.to);
        c.run?.();
    };

    const onKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, results.length - 1)); }
        if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
        if (e.key === "Enter" && results[active]) { e.preventDefault(); choose(results[active]); }
    };

    return (
        <dialog
            ref={ref}
            aria-label={l("بحث سريع", "Quick search")}
            onCancel={(e) => { e.preventDefault(); onOpenChange(false); }}
            onClick={(e) => { if (e.target === ref.current) onOpenChange(false); }}
            // Blurred backdrop behind a modal over the page. avoid-ai-design-ignore: K3
            className="mx-auto mt-[12vh] w-[calc(100%-2rem)] max-w-xl rounded-[20px] border border-rule bg-sheet p-0 text-ink shadow-pop backdrop:bg-overlay backdrop:backdrop-blur-[2px] open:animate-[oiq-pop-in_160ms_ease-out]"
        >
            {open && (
                <div onKeyDown={onKeyDown}>
                    <div className="flex items-center gap-3 border-b border-rule px-4">
                        <Search className="size-5 shrink-0 text-ink-3" aria-hidden />
                        <input
                            autoFocus
                            value={query}
                            onChange={(e) => { setQuery(e.target.value); setActive(0); }}
                            placeholder={l("روح لصفحة أو اعمل حاجة…", "Go to a page or run an action…")}
                            aria-label={l("بحث", "Search")}
                            aria-controls="cmd-list"
                            aria-activedescendant={results[active] ? `cmd-${results[active].id}` : undefined}
                            className="h-14 flex-1 bg-transparent text-[1.0625rem] outline-none placeholder:text-ink-3"
                        />
                        <kbd className="rounded-md border border-rule bg-sheet-2 px-1.5 py-0.5 text-xs text-ink-3">Esc</kbd>
                    </div>
                    <ul id="cmd-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
                        {results.length === 0 && <li className="px-3 py-8 text-center text-ink-2">{l("مفيش نتيجة.", "No results.")}</li>}
                        {groups.map((g) => (
                            <li key={g} role="presentation">
                                <p className="px-3 pb-1 pt-3 text-xs font-medium text-ink-3">{g}</p>
                                <ul role="presentation">
                                    {results.filter((c) => c.group === g).map((c) => {
                                        const idx = results.indexOf(c);
                                        const Icon = c.icon;
                                        return (
                                            <li
                                                key={c.id}
                                                id={`cmd-${c.id}`}
                                                role="option"
                                                aria-selected={idx === active}
                                                onMouseEnter={() => setActive(idx)}
                                                onClick={() => choose(c)}
                                                className={cn(
                                                    "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5",
                                                    idx === active ? "bg-pen-wash text-pen" : "text-ink",
                                                )}
                                            >
                                                <Icon className="size-[18px] shrink-0" />
                                                <span className="flex-1 font-medium">{c.label}</span>
                                                {c.hint && <span className="text-sm text-ink-3">{c.hint}</span>}
                                                {idx === active && <CornerDownLeft className="size-4 opacity-60" aria-hidden />}
                                            </li>
                                        );
                                    })}
                                </ul>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </dialog>
    );
}
