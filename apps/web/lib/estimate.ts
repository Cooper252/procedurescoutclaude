// "What will I pay?" (Cooper, 2026-11-11): a rough out-of-pocket estimate from
// the visitor's own plan details and a plan's negotiated rate. Done in whole
// cents with BigInt, never floating point. Kept only in this browser tab.

export type PlanDetails = {
  deductibleLeft: string; // dollars still to pay before the plan shares costs
  coinsurance: string; // percent the visitor pays after the deductible (e.g. "20")
  oopLeft: string; // dollars left before the out-of-pocket maximum ("" = unknown)
  copay: string; // flat copay for this kind of visit ("" = none / not a copay visit)
};

export const EMPTY_PLAN: PlanDetails = { deductibleLeft: "", coinsurance: "", oopLeft: "", copay: "" };

const DOLLARS = /^\d{1,7}(\.\d{1,4})?$/;

/** Dollars (as typed or as published) to whole cents, rounding half up. */
export function toCents(value: string): bigint | null {
  const v = value.replace(/[$,\s]/g, "");
  if (!DOLLARS.test(v)) return null;
  const [whole = "0", frac = ""] = v.split(".");
  const four = BigInt(whole) * 10000n + BigInt((frac + "0000").slice(0, 4));
  return (four + 50n) / 100n;
}

export function centsToDollars(c: bigint): string {
  const sign = c < 0n ? "-" : "";
  const a = c < 0n ? -c : c;
  const cents = (a % 100n).toString().padStart(2, "0");
  return `${sign}$${(a / 100n).toLocaleString("en-US")}.${cents}`;
}

export type Estimate = { cents: bigint; how: "copay" | "deductible" | "coinsurance" | "oop_cap" };

/** What the visitor would roughly pay for an in-network rate. Returns null
 *  when the details are incomplete or not numbers (nothing is guessed). */
export function estimate(rate: string, plan: PlanDetails): Estimate | null {
  const price = toCents(rate);
  if (price === null) return null;
  const cap = plan.oopLeft.trim() ? toCents(plan.oopLeft) : null;
  if (plan.oopLeft.trim() && cap === null) return null;
  const capped = (c: bigint, how: Estimate["how"]): Estimate =>
    cap !== null && c > cap ? { cents: cap, how: "oop_cap" } : { cents: c, how };
  if (plan.copay.trim()) {
    const copay = toCents(plan.copay);
    if (copay === null) return null;
    return capped(copay < price ? copay : price, "copay");
  }
  const ded = toCents(plan.deductibleLeft || "0");
  const pct = /^\d{1,3}$/.test(plan.coinsurance.trim() || "0") ? BigInt(plan.coinsurance.trim() || "0") : null;
  if (ded === null || pct === null || pct > 100n) return null;
  if (price <= ded) return capped(price, "deductible");
  const after = price - ded;
  const share = (after * pct + 50n) / 100n;
  return capped(ded + share, ded > 0n ? "deductible" : "coinsurance");
}
