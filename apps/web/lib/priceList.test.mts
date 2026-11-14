import assert from "node:assert/strict";
import { addDecimals, itemHref, listHref, parseItem, placeTotal } from "./priceList.ts";

assert.deepEqual(parseItem("svc:vaginal-birth"), { kind: "service", slug: "vaginal-birth" });
assert.deepEqual(parseItem("MS-DRG:807"), { kind: "code", system: "MS-DRG", code: "807" });
assert.equal(parseItem("bad"), null);
assert.equal(addDecimals(["6983", "1200.50", "0.125"]), "8183.625");
assert.equal(addDecimals(["10", "abc"]), null);
assert.equal(addDecimals(["0.1", "0.2"]), "0.3");
assert.deepEqual(placeTotal([{ key: "a", low: "100", high: "150" }, { key: "b", low: "20", high: null }]), { low: "120", high: "170" });
assert.equal(placeTotal([{ key: "a", low: "100", high: null }, { key: "b", low: null, high: null }]), null);
const rest = new URLSearchParams("zip=89123&q=birth&r=10");
assert.equal(itemHref("CPT:01967", rest), "/search?zip=89123&r=10&code_system=CPT&code=01967");
assert.equal(listHref(["MS-DRG:807", "CPT:01967"], rest), "/price-list?zip=89123&q=birth&r=10&i=MS-DRG%3A807&i=CPT%3A01967");
console.log("price list tests passed");
