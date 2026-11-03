import { useCallback, useState } from "react";
import { useI18n } from "../i18n";

type Control = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

/**
 * Form checks with messages in the page's language, shown under each field (Field `error`).
 * The rules stay in the markup (required, type="email", minLength, min/max); the browser's own
 * bubble is replaced because it speaks the browser's language, not the site's, and vanishes.
 * Works on a <form> or any container (dialogs and steps that have no form element).
 */
export function useFieldErrors() {
    const { l } = useI18n();
    const [errors, setErrors] = useState<Record<string, string>>({});

    const messageFor = useCallback((el: Control): string | null => {
        const v = el.validity;
        // Spaces alone are not an answer
        if (el.required && !el.value.trim()) return l("الخانة دي مطلوبة.", "This field is required.");
        if (v.valid) return null;
        if (v.typeMismatch && el.type === "email") return l("اكتب بريد إلكتروني صحيح، زي name@uni.edu.eg", "Enter a valid email, like name@uni.edu.eg");
        if (v.tooShort) {
            const n = (el as HTMLInputElement).minLength;
            return l(`لازم ${n} حروف أو أرقام على الأقل.`, `Use at least ${n} characters.`);
        }
        if (v.rangeUnderflow) return l(`أقل رقم مسموح ${(el as HTMLInputElement).min}.`, `The lowest allowed is ${(el as HTMLInputElement).min}.`);
        if (v.rangeOverflow) return l(`أكبر رقم مسموح ${(el as HTMLInputElement).max}.`, `The highest allowed is ${(el as HTMLInputElement).max}.`);
        return l("القيمة دي مش مظبوطة، راجعها.", "This doesn't look right; check it.");
    }, [l]);

    /** Checks every named control inside `root`; shows the messages and focuses the first problem. */
    const validate = useCallback((root: HTMLElement | null) => {
        if (!root) return true;
        const next: Record<string, string> = {};
        let first: Control | null = null;
        for (const el of root.querySelectorAll<Control>("input[id], textarea[id], select[id]")) {
            if (el.disabled || el.type === "hidden") continue;
            const msg = messageFor(el);
            if (msg) { next[el.id] = msg; first ??= el; }
        }
        setErrors(next);
        if (first) {
            // Centre it rather than letting focus park it under a sticky header
            first.focus({ preventScroll: true });
            first.scrollIntoView({ block: "center" });
        }
        return !first;
    }, [messageFor]);

    /** Call from a field's onChange so its message goes away as soon as it is being fixed. */
    const clear = useCallback((id: string) => setErrors((e) => {
        if (!(id in e)) return e;
        const rest = { ...e };
        delete rest[id];
        return rest;
    }), []);

    /** Forget all messages, e.g. when a form opens again. */
    const reset = useCallback(() => setErrors({}), []);

    return { errors, validate, clear, reset };
}
