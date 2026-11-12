import assert from "node:assert/strict";
import { STATE_LAWS } from "./stateLaws.ts";

// every state law names its official source and is written in both languages
for (const [st, law] of Object.entries(STATE_LAWS)) {
  assert.match(st, /^[A-Z]{2}$/);
  assert.match(law.source, /^https:\/\//, st);
  for (const pair of [law.title, law.body, law.fine]) {
    assert.ok(pair[0].length > 10 && pair[1].length > 10, st);
    assert.notEqual(pair[0], pair[1], st);
  }
}
assert.ok(Object.keys(STATE_LAWS).length >= 13);
console.log("state law tests passed");
