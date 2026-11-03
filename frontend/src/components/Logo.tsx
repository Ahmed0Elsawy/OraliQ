import { cn } from "../lib/utils";
import { MARK, WORDMARK } from "./brand";

const WORD_ID = "oraliq-wordmark";

/**
 * The wordmark, defined once per document. It appears in the header, the footer and the sidebar;
 * inlining its path each time would add ~14KB of markup per copy to the pre-rendered home page,
 * so the shape lives here and every logo points at it.
 */
export function BrandSprite() {
    return (
        <svg width={0} height={0} aria-hidden focusable="false" style={{ position: "absolute" }}>
            <symbol id={WORD_ID} viewBox={WORDMARK.viewBox}><path fill="currentColor" fillRule="evenodd" d={WORDMARK.d} /></symbol>
        </svg>
    );
}

/**
 * The Q with its infinity tail: the brand mark on its own, for square places. It draws its own
 * path rather than joining the sprite, because the pages that use it are not the pre-rendered one.
 */
export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
    return (
        <svg width={size} height={size} viewBox={MARK.viewBox} className={cn("shrink-0", className)} aria-hidden focusable="false">
            <path fill="currentColor" fillRule="evenodd" d={MARK.d} />
        </svg>
    );
}

interface LogoProps {
    /** Cap height of the wordmark in px; its width follows. */
    height?: number;
    className?: string;
    /** Give the logo an accessible name — only where it is not already inside a labelled link. */
    title?: string;
}

/**
 * The OralIQ wordmark. It inherits `currentColor`, so a parent that sets a text colour (or the
 * page's own ink) colours it: black on the light surfaces, white on the black ones.
 */
export default function Logo({ height = 22, className, title }: LogoProps) {
    return (
        <svg
            height={height}
            width={Math.round(height * WORDMARK.ratio)}
            viewBox={WORDMARK.viewBox}
            className={cn("block shrink-0", className)}
            role={title ? "img" : undefined}
            aria-label={title}
            aria-hidden={title ? undefined : true}
            focusable="false"
        >
            <use href={`#${WORD_ID}`} />
        </svg>
    );
}
