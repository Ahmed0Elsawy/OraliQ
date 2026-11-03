/**
 * Return from the payment page: the URL only names the payment; its status comes from the server.
 *     npm test        (= node --test "tests/*.test.ts")
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { PENDING_TEXT, paymentRefFromSearch, returnNotice } from "../src/lib/paymentReturn.ts";

const REF = "oiq_" + "a".repeat(32);

test("reads our reference from ?payment= (Kashier) and Kashier's merchantOrderId", () => {
    assert.equal(paymentRefFromSearch(`?payment=${REF}`), REF);
    assert.equal(paymentRefFromSearch(`?paymentStatus=SUCCESS&merchantOrderId=${REF}&signature=x`), REF);
});

test("ignores anything that is not one of our references", () => {
    assert.equal(paymentRefFromSearch(""), null);
    assert.equal(paymentRefFromSearch("?payment=../../admin"), null);
    assert.equal(paymentRefFromSearch("?success=true"), null);
    assert.equal(paymentRefFromSearch(`?payment=${REF}x`), null);
});

test("a success flag in the URL never makes a payment look paid", () => {
    // Only the server's status decides; with no status it is still "confirming".
    const n = returnNotice(undefined);
    assert.equal(n.tone, "info");
    assert.equal(n.poll, true);
});

test("pending explains the usual immediate activation and the 24h limit", () => {
    const n = returnNotice("pending");
    assert.deepEqual(n.body, PENDING_TEXT);
    assert.match(n.body.ar, /24/);
    assert.match(n.body.en, /24 hours/);
    assert.equal(n.poll, true);
});

test("server statuses map to final notices", () => {
    assert.equal(returnNotice("paid").tone, "success");
    assert.equal(returnNotice("failed").tone, "error");
    assert.equal(returnNotice("review").tone, "warning");
    assert.equal(returnNotice("review").poll, false);
    assert.equal(returnNotice("refunded").tone, "info");
    for (const s of ["paid", "failed", "review", "refunded", "refund_review"]) assert.equal(returnNotice(s).poll, false);
});
