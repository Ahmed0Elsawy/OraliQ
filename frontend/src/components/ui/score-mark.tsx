import { cn } from "../../lib/utils";
import { formatScore, gradeOf } from "../../lib/grades";

type Size = "sm" | "md" | "lg" | "xl";

const sizes: Record<Size, { box: string; num: string; pct: string; stroke: number }> = {
    sm: { box: "h-10 w-[4.5rem]", num: "text-[0.95rem]", pct: "text-[0.6rem]", stroke: 4 },
    md: { box: "h-14 w-24", num: "text-xl", pct: "text-xs", stroke: 3.6 },
    lg: { box: "h-20 w-36", num: "text-[2rem]", pct: "text-sm", stroke: 2.8 },
    xl: { box: "h-32 w-60", num: "text-[3.4rem]", pct: "text-xl", stroke: 2 },
};

interface ScoreMarkProps {
    score: number | null | undefined;
    size?: Size;
    /** Draw the circle like a pen stroke when it first appears. */
    animate?: boolean;
    /** Number only — for dense lists, where a column of red circles would shout. */
    plain?: boolean;
    className?: string;
    label?: string;
    /**
     * "mark": the grader's red pen (lecturer views, marketing).
     * "kind": the pen takes the grade's colour — what a student sees about their own work.
     */
    ink?: "mark" | "kind";
}

const kindInk = { pass: "text-pass", pen: "text-pen", warn: "text-sun", mark: "text-sun", neutral: "text-ink-3" } as const;

/**
 * The grade as a teacher marks it: the number, circled by hand in red pen.
 * The loop overshoots its start — the way a real pen circle does.
 */
export function ScoreMark({ score, size = "md", animate = false, plain = false, className, label, ink = "mark" }: ScoreMarkProps) {
    const s = sizes[size];
    const pending = score == null || Number.isNaN(score);
    const text = formatScore(score);
    const g = gradeOf(score);
    const penColor = ink === "kind" && g ? kindInk[g.tone] : "text-mark";

    return (
        <span
            role="img"
            aria-label={label ?? (pending ? "—" : `${text}%`)}
            className={cn("relative inline-flex shrink-0 items-center justify-center", s.box, className)}
        >
            {!pending && !plain && (
                <svg
                    viewBox="-6 -4 132 88"
                    preserveAspectRatio="none"
                    className={cn("absolute inset-0 h-full w-full -rotate-3 overflow-visible", penColor)}
                    aria-hidden
                >
                    <path
                        d="M92 10C113 17 121 44 102 62C82 80 33 80 14 63C-3 48 6 19 33 9C53 2 80 3 98 15"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={s.stroke}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        pathLength={100}
                        strokeDasharray={100}
                        style={
                            animate
                                ? ({ "--len": 100, animation: "oiq-draw 700ms cubic-bezier(.6,.05,.3,1) 150ms both" } as React.CSSProperties)
                                : undefined
                        }
                    />
                </svg>
            )}
            <span
                dir="ltr"
                className={cn("relative flex items-baseline font-display font-semibold leading-none", (size === "sm" || size === "md") && "tabular", pending ? "text-ink-3" : "text-ink", s.num)}
                aria-hidden
            >
                {text}
                {!pending && <span className={cn("ms-0.5 font-medium text-ink-2", s.pct)}>%</span>}
            </span>
        </span>
    );
}
