import { useEffect } from "react";

/** Points the canonical URL and og:url at the current page (built from the configured site URL). */
function syncCanonical() {
    const link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    if (!link) return;
    let base: string;
    try { base = new URL(link.href).origin; } catch { return; }
    const href = `${base}${window.location.pathname === "/" ? "/" : window.location.pathname.replace(/\/+$/, "")}`;
    link.href = href;
    document.querySelector<HTMLMetaElement>('meta[property="og:url"]')?.setAttribute("content", href);
}

/** Sets the browser tab title as "<page> — OralIQ" while the page is mounted. */
export function usePageTitle(title: string | null | undefined) {
    useEffect(() => {
        syncCanonical();
        if (!title) return;
        const prev = document.title;
        document.title = `${title} — OralIQ`;
        return () => { document.title = prev; };
    }, [title]);
}
