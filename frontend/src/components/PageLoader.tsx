import { cn } from "../lib/utils";
import { LogoMark } from "./Logo";

/** Quiet loading state: the logo's circle being drawn. No fake progress. */
export function PageLoader({ fullscreen = false }: { fullscreen?: boolean }) {
    return (
        <div
            role="status"
            aria-label="Loading"
            className={cn("flex items-center justify-center", fullscreen ? "min-h-dvh bg-paper" : "min-h-[50vh]")}
        >
            <LogoMark size={44} className="animate-pulse" />
        </div>
    );
}
