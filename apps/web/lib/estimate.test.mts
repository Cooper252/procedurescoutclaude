import { estimate, toCents, centsToDollars, EMPTY_PLAN } from "./estimate.ts";
import assert from "node:assert/strict";
assert.equal(toCents("100.1"), 10010n);
assert.equal(toCents("$1,234.565"), 123457n);
assert.equal(toCents("abc"), null);
// all deductible
assert.deepEqual(estimate("250", { ...EMPTY_PLAN, deductibleLeft: "1000", coinsurance: "20" }), { cents: 25000n, how: "deductible" });
// part deductible + 20%
assert.deepEqual(estimate("1500", { ...EMPTY_PLAN, deductibleLeft: "1000", coinsurance: "20" }), { cents: 110000n, how: "deductible" });
// deductible met
assert.deepEqual(estimate("1500", { ...EMPTY_PLAN, deductibleLeft: "0", coinsurance: "20" }), { cents: 30000n, how: "coinsurance" });
// cap
assert.deepEqual(estimate("20000", { ...EMPTY_PLAN, deductibleLeft: "500", coinsurance: "30", oopLeft: "2000" }), { cents: 200000n, how: "oop_cap" });
// copay, and copay above the rate
assert.deepEqual(estimate("180", { ...EMPTY_PLAN, copay: "40" }), { cents: 4000n, how: "copay" });
assert.deepEqual(estimate("25", { ...EMPTY_PLAN, copay: "40" }), { cents: 2500n, how: "copay" });
assert.equal(estimate("100", { ...EMPTY_PLAN, coinsurance: "120" }), null);
assert.equal(centsToDollars(123456n), "$1,234.56");
console.log("estimate tests passed");
