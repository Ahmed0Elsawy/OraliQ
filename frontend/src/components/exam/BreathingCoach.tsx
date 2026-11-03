import { useEffect, useState } from "react";
import { Wind, X } from "lucide-react";
import { useI18n } from "../../i18n";
import { cn } from "../../lib/utils";

const ROUNDS = 3;
const IN_MS = 4000;
const OUT_MS = 6000;

type Step = { phase: "in" | "out"; round: number } | "done" | null;

/**
 * Optional 30-second breathing exercise before the exam (longer out-breath than in-breath
 * slows the heart rate). Shown only before the camera starts, so it never affects proctoring.
 */
export function BreathingCoach({ className }: { className?: string }) {
    const { l } = useI18n();
    const [step, setStep] = useState<Step>(null);

    useEffect(() => {
        if (!step || step === "done") return;
        const id = setTimeout(() => {
            if (step.phase === "in") setStep({ phase: "out", round: step.round });
            else setStep(step.round < ROUNDS ? { phase: "in", round: step.round + 1 } : "done");
        }, step.phase === "in" ? IN_MS : OUT_MS);
        return () => clearTimeout(id);
    }, [step]);

    if (!step) {
        return (
            <button
                type="button"
                onClick={() => setStep({ phase: "in", round: 1 })}
                className={cn("inline-flex items-center gap-2 rounded-full bg-teal-wash px-3.5 py-1.5 text-sm font-semibold text-teal transition-colors hover:bg-teal-wash/70", className)}
            >
                <Wind className="size-4" aria-hidden />
                {l("حاسس بتوتر؟ خد 3 أنفاس معانا", "Feeling nervous? Take 3 breaths with us")}
            </button>
        );
    }

    return (
        <div className={cn("relative rounded-2xl bg-teal-wash/60 px-4 py-5 text-center", className)} role="status" aria-live="polite">
            <button
                type="button"
                onClick={() => setStep(null)}
                className="absolute end-2 top-2 rounded-lg p-1.5 text-teal/70 transition-colors hover:bg-teal-wash hover:text-teal"
                aria-label={l("إغلاق", "Close")}
            >
                <X className="size-4" aria-hidden />
            </button>

            {step === "done" ? (
                <>
                    <p className="font-display text-lg font-semibold text-teal">{l("تمام كده، إنت جاهز.", "That's it — you're ready.")}</p>
                    <p className="mt-1 text-sm text-ink-2">{l("خد وقتك، ولما تحب ابدأ.", "Take your time and start when you like.")}</p>
                </>
            ) : (
                <>
                    <div className="relative mx-auto flex size-32 items-center justify-center">
                        <span
                            key={`${step.phase}-${step.round}`}
                            className="absolute inset-0 rounded-full bg-teal/15 ring-1 ring-teal/25"
                            style={{
                                animation: `${step.phase === "in" ? "oiq-breathe-in" : "oiq-breathe-out"} ${step.phase === "in" ? IN_MS : OUT_MS}ms ease-in-out forwards`,
                            }}
                            aria-hidden
                        />
                        <span className="relative font-display text-lg font-semibold text-teal">
                            {step.phase === "in" ? l("شهيق…", "Breathe in…") : l("زفير…", "Breathe out…")}
                        </span>
                    </div>
                    <p className="mt-2 text-sm text-ink-2">
                        {step.phase === "in"
                            ? l("خد نفس بالراحة من مناخيرك", "Slowly, through your nose")
                            : l("وطلّعه أبطأ من بُقّك", "And out, even slower, through your mouth")}
                        <span className="ms-2 text-ink-3 tabular">{step.round}/{ROUNDS}</span>
                    </p>
                </>
            )}
        </div>
    );
}
