// Checks that the browser model (web/predict.js) reproduces the Python predictions exactly.
// Usage: node --test tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { chance } from "../web/predict.js";

const payload = JSON.parse(readFileSync(new URL("../web/model.json", import.meta.url)));
const cases = JSON.parse(readFileSync(new URL("./fixture.json", import.meta.url)));

test("JS predictions match Python on real 2025-26 situations", () => {
  assert.ok(cases.length >= 600);
  for (const { lift, situation, expected } of cases) {
    const got = chance(payload, lift, situation);
    assert.ok(Math.abs(got - expected) < 1e-9, `${lift} ${JSON.stringify(situation)}: ${got} vs ${expected}`);
  }
});
