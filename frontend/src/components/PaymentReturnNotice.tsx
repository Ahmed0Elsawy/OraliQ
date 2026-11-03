import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import api from "../lib/api";
import { useI18n } from "../i18n";
import { Alert } from "./ui/feedback";
import { paymentRefFromSearch, returnNotice, type ReturnNotice } from "../lib/paymentReturn";

const POLL_MS = 5000;
const POLL_TRIES = 12; // about a minute; after that the pending text (up to 24h) stays up

/**
 * Shown on return from the payment page (?payment=<ref> / ?merchant_order_id=<ref>). The status
 * always comes from the server — the redirect itself never activates or confirms anything.
 * Lecturers only (students never pay).
 */
export default function PaymentReturnNotice({ enabled }: { enabled: boolean }) {
    const { l } = useI18n();
    const location = useLocation();
    const navigate = useNavigate();
    const reference = paymentRefFromSearch(location.search);
    const [notice, setNotice] = useState<ReturnNotice | null>(null);

    useEffect(() => {
        if (!enabled || !reference) return;
        let cancelled = false;
        let tries = 0;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const check = () => {
            api.get<{ status: string }>(`/billing/payments/${reference}`)
                .then((res) => {
                    if (cancelled) return;
                    const next = returnNotice(res.data?.status);
                    setNotice(next);
                    if (next.poll && ++tries < POLL_TRIES) timer = setTimeout(check, POLL_MS);
                })
                .catch(() => {
                    if (!cancelled) setNotice(null);
                });
        };
        check();
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
        };
    }, [enabled, reference]);

    if (!enabled || !reference || !notice) return null;

    const dismiss = () => {
        const params = new URLSearchParams(location.search);
        params.delete("payment");
        params.delete("merchant_order_id");
        params.delete("canceled");
        const search = params.toString();
        setNotice(null);
        navigate({ pathname: location.pathname, search: search ? `?${search}` : "" }, { replace: true });
    };

    return (
        <Alert
            tone={notice.tone}
            title={l(notice.title.ar, notice.title.en)}
            className="mb-6"
            action={
                <button type="button" onClick={dismiss} aria-label={l("إغلاق", "Dismiss")} className="rounded-md p-1 text-ink-2 hover:text-ink">
                    <X className="size-4" aria-hidden />
                </button>
            }
        >
            {l(notice.body.ar, notice.body.en)}
        </Alert>
    );
}
