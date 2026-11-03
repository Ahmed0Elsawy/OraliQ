import { Component, type ErrorInfo, type ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import Logo from "./Logo";

interface State { error: Error | null }

/**
 * Last line of defence: a render crash shows a calm recovery screen instead of a blank page.
 * Bilingual on its own (no context) because providers may be the thing that failed.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
    state: State = { error: null };

    static getDerivedStateFromError(error: Error): State {
        return { error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        // After a new deploy, an open tab asks for page chunks that no longer exist.
        // Reload once to pick up the new version instead of showing an error.
        const staleChunk = /dynamically imported module|Importing a module script failed|Loading chunk .* failed/i.test(error?.message || "");
        if (staleChunk) {
            try {
                if (!sessionStorage.getItem("oraliq_chunk_reload")) {
                    sessionStorage.setItem("oraliq_chunk_reload", "1");
                    window.location.reload();
                    return;
                }
            } catch { /* storage blocked — fall through to the recovery screen */ }
        }
        console.error("[OralIQ] UI crash:", error, info.componentStack);
    }

    render() {
        if (!this.state.error) return this.props.children;
        let ar = true;
        try { ar = localStorage.getItem("oraliq_lang") !== "en"; } catch { /* default Arabic */ }
        return (
            <main dir={ar ? "rtl" : "ltr"} className="flex min-h-dvh flex-col items-center justify-center bg-paper px-6 text-center text-ink">
                <Logo height={26} className="mb-10" title="OralIQ" />
                <h1 className="text-2xl font-bold">{ar ? "حصلت مشكلة في عرض الصفحة" : "Something went wrong showing this page"}</h1>
                <p className="mt-2 max-w-md text-ink-2">
                    {ar
                        ? "بياناتك مش متأثرة. حدّث الصفحة، ولو المشكلة اتكررت ارجع للصفحة الرئيسية."
                        : "Your data is safe. Reload the page; if it keeps happening, go back to the home page."}
                </p>
                <div className="mt-8 flex flex-wrap justify-center gap-2">
                    <button
                        type="button"
                        onClick={() => window.location.reload()}
                        className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-control)] bg-pen px-5 font-semibold text-pen-ink hover:bg-pen-hover"
                    >
                        <RefreshCw className="size-4" aria-hidden />{ar ? "حدّث الصفحة" : "Reload"}
                    </button>
                    <a href="/" className="inline-flex h-11 items-center rounded-[var(--radius-control)] border border-field/80 bg-sheet px-5 font-semibold hover:bg-sheet-2">
                        {ar ? "الصفحة الرئيسية" : "Home page"}
                    </a>
                </div>
            </main>
        );
    }
}
