/**
 * Test-checkout tooling (test cards, test wallet numbers, "no real money is charged") may only
 * appear when the backend says this server takes test payments: GET /billing/payment-mode.
 *
 * The backend is the only source: nothing here looks at the site's URL, localhost, the build mode,
 * localStorage or query parameters. Anything other than an explicit `sandbox_mode: true` from that
 * endpoint — a failed request, a missing field, "true" as a string — means live, so the tooling
 * stays hidden.
 *
 * Kept free of imports (no React, no axios) so it runs under `node --test` as-is.
 */

export const PAYMENT_MODE_PATH = "/billing/payment-mode";

type Getter = (path: string) => Promise<{ data: unknown }>;

/** Only an explicit boolean `true` counts. */
export function parseSandboxMode(data: unknown): boolean {
    return typeof data === "object" && data !== null && (data as { sandbox_mode?: unknown }).sandbox_mode === true;
}

/** Asks the backend; any failure is "live". */
export async function loadSandboxMode(get: Getter): Promise<boolean> {
    try {
        const res = await get(PAYMENT_MODE_PATH);
        return parseSandboxMode(res?.data);
    } catch {
        return false;
    }
}

export type PaymentMethod = "card" | "wallet";

export interface SandboxHelp {
    heading: { ar: string; en: string };
    /** Card method: test card lines (shown left-to-right, monospace). */
    cardLines: string[];
    /** Wallet method: what to type on the test payment page. */
    walletNote: { ar: string; en: string } | null;
    /** The number the "use test number" button fills in (wallet method only). */
    fillWalletNumber: string | null;
}

// Kashier test data (developers.kashier.io/docs/get-started/testing).
const TEST_WALLET_NUMBER = "01010101010";
const OTHER_TEST_WALLET_NUMBER = "01001001001";

/**
 * The test instructions for the chosen method, or null when they must not be shown.
 * Every piece of test data the checkout can display lives here, behind this check.
 */
export function sandboxHelp(sandboxMode: boolean, method: PaymentMethod): SandboxHelp | null {
    if (sandboxMode !== true) return null;
    return {
        heading: {
            ar: "تعليمات التيست والاختبار (لن يتم خصم أي أموال حقيقية):",
            en: "Test / Sandbox Mode (No real money charged):",
        },
        cardLines: method === "card"
            ? ["Card: 5123450000000008 (or 4012000033330026)", "Expiry: 06/25 = approved, 05/25 = declined   CVV: 100"]
            : [],
        walletNote: method === "wallet"
            ? {
                ar: `في صفحة الدفع الخاصة بـ Kashier: فودافون كاش ${TEST_WALLET_NUMBER}، وأي محفظة تانية ${OTHER_TEST_WALLET_NUMBER}`,
                en: `On Kashier's payment page: Vodafone Cash ${TEST_WALLET_NUMBER}, any other wallet ${OTHER_TEST_WALLET_NUMBER}`,
            }
            : null,
        fillWalletNumber: method === "wallet" ? TEST_WALLET_NUMBER : null,
    };
}

/** Placeholder of the wallet number field: a format hint in live mode, never a test number. */
export function walletPlaceholder(sandboxMode: boolean): string {
    return sandboxMode === true ? TEST_WALLET_NUMBER : "01xxxxxxxxx";
}
