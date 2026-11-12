import assert from "node:assert/strict";
import { fitsType, matchCard } from "./cardRead.ts";

const plans = [
  { plan_id: "1", payer: "Anthem Blue Cross Blue Shield (Nevada)", plan: "HMO", product_type: "hmo", segment: "commercial", payer_id: "a" },
  { plan_id: "2", payer: "Anthem Blue Cross Blue Shield (Nevada)", plan: "PPO", product_type: "ppo", segment: "commercial", payer_id: "a" },
  { plan_id: "3", payer: "Aetna", plan: "Medicare Advantage", product_type: "unknown", segment: "medicare_advantage", payer_id: "b" },
];
// what a phone photo of a card reads like: noisy, mixed case
const anthem = matchCard("anthem.\nBlueCross BlueShield\nMember ID XYZ123456789\nPLAN: Pathway HMO\nRxBIN 020099", plans);
assert.equal(anthem.payerId, "a");
assert.equal(anthem.planType, "HMO");
assert.ok(fitsType(plans[0]!, "HMO") && !fitsType(plans[1]!, "HMO"));
const aetna = matchCard("aetna\nMedicare Advantage PPO\nMember", plans);
assert.equal(aetna.payerId, "b");
assert.equal(aetna.planType, "Medicare Advantage");
assert.equal(matchCard("random words only", plans).payerId, null);
console.log("card reading tests passed");
