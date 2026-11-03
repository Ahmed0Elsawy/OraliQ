/**
 * Test-checkout tooling must follow the backend's /billing/payment-mode and nothing else.
 *
 * Runs with Node's own test runner, no build step and no extra packages:
 *     npm test        (= node --test "tests/*.test.ts")
 * (Node 22.6+ strips the TypeScript types itself.) The backend side of the flag is covered in
 * backend/app/tests/test_payment_mode.py.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
    PAYMENT_MODE_PATH,
    loadSandboxMode,
    parseSandboxMode,
    sandboxHelp,
    walletPlaceholder,
} from "../src/lib/paymentMode.ts";

const TEST_DATA = ["01010101010", "01001001001", "5123450000000008", "4012000033330026", "06/25", "لن يتم خصم", "No real money"];
const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const allText = (h: ReturnType<typeof sandboxHelp>) => JSON.stringify(h ?? "");

/** A mocked api.get: answers only the payment-mode path. */
const backend = (response: unknown) => async (path: string) => {
    assert.equal(path, PAYMENT_MODE_PATH);
    return { data: response };
};
const unreachable = async () => { throw new Error("Network Error"); };

// ── 1 + 2. Sandbox confirmed by the backend ──────────────────────────────────

test("1. sandbox_mode=true shows the test instructions", async () => {
    const mode = await loadSandboxMode(backend({ sandbox_mode: true }));
    assert.equal(mode, true);
    const card = sandboxHelp(mode, "card");
    assert.ok(card);
    assert.match(card.heading.en, /No real money/);
    assert.ok(card.cardLines.some((l) => l.includes("5123450000000008")));
    const wallet = sandboxHelp(mode, "wallet");
    assert.ok(wallet?.walletNote?.ar.includes("01010101010"));
});

test("2. sandbox_mode=true offers the fill-test-number button (wallet only)", () => {
    assert.equal(sandboxHelp(true, "wallet")?.fillWalletNumber, "01010101010");
    assert.equal(sandboxHelp(true, "card")?.fillWalletNumber, null);
    assert.equal(walletPlaceholder(true), "01010101010");
});

// ── 3 + 5. Live / production ──────────────────────────────────────────────────

test("3. sandbox_mode=false shows no test data or instructions at all", async () => {
    const mode = await loadSandboxMode(backend({ sandbox_mode: false }));
    assert.equal(mode, false);
    for (const method of ["card", "wallet"] as const) {
        assert.equal(sandboxHelp(mode, method), null);
    }
    assert.equal(walletPlaceholder(mode), "01xxxxxxxxx");
    for (const s of TEST_DATA) assert.ok(!walletPlaceholder(mode).includes(s));
});

test("5. the checkout component itself contains no test data; it all sits behind the backend check", () => {
    const modal = read("../src/components/SubscriptionModal.tsx");
    for (const s of TEST_DATA) {
        assert.ok(!modal.includes(s), `SubscriptionModal.tsx still contains test data: ${s}`);
    }
    // The help panel and the fill button render only from sandboxHelp(...), which is null unless
    // the backend said sandbox_mode: true.
    assert.match(modal, /const help = sandboxHelp\(sandboxMode, paymentMethod\)/);
    assert.match(modal, /\{help && \(/);
});

// ── 4. Unknown / failed ───────────────────────────────────────────────────────

test("4. a failed or odd payment-mode response hides everything", async () => {
    assert.equal(await loadSandboxMode(unreachable), false);
    for (const odd of [undefined, null, {}, { sandbox_mode: "true" }, { sandbox_mode: 1 }, { sandboxMode: true }, "sandbox", [true]]) {
        assert.equal(parseSandboxMode(odd), false, JSON.stringify(odd));
        assert.equal(await loadSandboxMode(backend(odd)), false, JSON.stringify(odd));
    }
    assert.equal(sandboxHelp(false, "card"), null);
});

// ── 6. Nothing secret ─────────────────────────────────────────────────────────

test("6. the frontend asks for, and keeps, only the sandbox flag", async () => {
    // Even if a misconfigured server sent more, only the boolean is used.
    const mode = await loadSandboxMode(backend({ sandbox_mode: true, api_key: "sk_live_x", hmac: "y" }));
    assert.equal(typeof mode, "boolean");
    assert.ok(!allText(sandboxHelp(mode, "card")).includes("sk_live_x"));
});

// ── 7. Real payment flow untouched ────────────────────────────────────────────

test("7. the real checkout request and payment methods are unchanged", () => {
    const modal = read("../src/components/SubscriptionModal.tsx");
    assert.match(modal, /"\/billing\/checkout"/);
    assert.match(modal, /currency, payment_method: paymentMethod, \.\.\.body/);
    assert.match(modal, /window\.location\.href = res\.data\.checkout_url/);
    assert.match(modal, /setPaymentMethod\("card"\)/);
    assert.match(modal, /setPaymentMethod\("wallet"\)/);
    // Kashier's own page asks for the wallet number: the modal no longer collects one.
    assert.ok(!modal.includes("wallet_phone"));
    // The flag has no say in what is sent to the gateway.
    const checkout = modal.slice(modal.indexOf("const startCheckout"), modal.indexOf("const handleAddon"));
    assert.ok(!checkout.includes("sandbox"), "checkout logic must not depend on the sandbox flag");
});

// ── 8. Sandbox -> live ────────────────────────────────────────────────────────

test("8. when the backend switches to live, the next check hides the tooling", async () => {
    let serverSandbox = true;
    const get = async () => ({ data: { sandbox_mode: serverSandbox } });
    assert.ok(sandboxHelp(await loadSandboxMode(get), "card"));
    serverSandbox = false;
    assert.equal(sandboxHelp(await loadSandboxMode(get), "card"), null);

    // The modal asks again on every opening and starts hidden while it waits.
    const modal = read("../src/components/SubscriptionModal.tsx");
    assert.match(modal, /useState\(false\);\s*\n\s*\n?\s*useEffect\(\(\) => \{\s*\n\s*if \(!modalOpen\) return;/);
    assert.match(modal, /setSandboxMode\(false\);\s*\n\s*loadSandboxMode\(/);
    assert.match(modal, /\}, \[modalOpen\]\);/);
});

// ── 9. Client-side state can't turn it on ─────────────────────────────────────

test("9. only the backend answer can turn sandbox tooling on", () => {
    const modal = read("../src/components/SubscriptionModal.tsx");
    const setters = [...modal.matchAll(/setSandboxMode\(([^)]*)\)/g)].map((m) => m[1].trim());
    assert.deepEqual(setters.sort(), ["false", "mode"]);   // reset, or the backend's answer
    const lib = read("../src/lib/paymentMode.ts");
    assert.ok(!/\b(localStorage|sessionStorage|location|document|window|import\.meta)\s*[.[]/.test(lib),
        "paymentMode.ts must not read the URL, storage or build settings");
    // A truthy-but-not-true value never counts.
    assert.equal(sandboxHelp("true" as unknown as boolean, "card"), null);
    assert.equal(sandboxHelp(1 as unknown as boolean, "wallet"), null);
});
