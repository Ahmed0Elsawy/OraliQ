/**
 * What the dashboard shows when the lecturer comes back from the payment page.
 *
 * Kashier's redirect (its merchantRedirect carries ?payment=<ref>; Kashier may add
 * merchantOrderId) only tells us WHICH payment to look up — never
 * whether it succeeded. Any "paymentStatus=SUCCESS" / "success=true" or signature in the URL is
 * ignored: the status always comes from GET /billing/payments/<ref>, which the server only marks
 * paid after the gateway's signed webhook or its own server-to-server check with the gateway.
 *
 * Kept free of imports (no React, no axios) so it runs under `node --test` as-is.
 */

const REFERENCE = /^oiq_[0-9a-f]{32}$/;

/** Our payment reference from the return URL, or null. Nothing else in the URL is read. */
export function paymentRefFromSearch(search: string): string | null {
    const params = new URLSearchParams(search);
    for (const key of ["payment", "merchantOrderId", "merchant_order_id"]) {
        const value = (params.get(key) || "").trim();
        if (REFERENCE.test(value)) return value;
    }
    return null;
}

export type ReturnTone = "success" | "info" | "warning" | "error";

export interface ReturnNotice {
    tone: ReturnTone;
    title: { ar: string; en: string };
    body: { ar: string; en: string };
    /** Still waiting for the gateway: worth asking the server again shortly. */
    poll: boolean;
}

export const PENDING_TEXT = {
    ar: "التفعيل عادةً بيكون فوري، لكن التأكد من الدفع ممكن ياخد لحد 24 ساعة. هنفعّل اشتراكك أول ما الدفع يتأكد.",
    en: "Activation is usually immediate, but confirming the payment can take up to 24 hours. Your subscription is activated as soon as it is confirmed.",
};

/** The message for a payment status reported by the server. Unknown statuses count as pending. */
export function returnNotice(status: string | null | undefined): ReturnNotice {
    switch (status) {
        case "paid":
            return {
                tone: "success",
                title: { ar: "تم تأكيد الدفع", en: "Payment confirmed" },
                body: { ar: "اشتراكك اتفعّل.", en: "Your subscription is active." },
                poll: false,
            };
        case "failed":
            return {
                tone: "error",
                title: { ar: "الدفع ما تمّش", en: "Payment not completed" },
                body: { ar: "ماتخصمش منك اشتراك. تقدر تحاول تاني من صفحة الباقات.", en: "No subscription was charged. You can try again from the plans page." },
                poll: false,
            };
        case "review":
            return {
                tone: "warning",
                title: { ar: "الدفع تحت المراجعة", en: "Payment under review" },
                body: {
                    ar: "لسه ماوصلناش تأكيد من بوابة الدفع، فالعملية بتتراجع يدويًا. لو اتخصم منك مبلغ، تواصل مع الدعم.",
                    en: "We haven't received the gateway's confirmation yet, so this payment is being reviewed by hand. If you were charged, contact support.",
                },
                poll: false,
            };
        case "refunded":
        case "refund_review":
            return {
                tone: "info",
                title: { ar: "تم تسجيل استرداد", en: "Refund recorded" },
                body: { ar: "العملية دي عليها استرداد. للتفاصيل تواصل مع الدعم.", en: "This payment has a refund on it. Contact support for details." },
                poll: false,
            };
        default:
            return {
                tone: "info",
                title: { ar: "بنتأكد من الدفع", en: "Confirming your payment" },
                body: PENDING_TEXT,
                poll: true,
            };
    }
}
