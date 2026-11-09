// Browser validation: schema + every cross-field rule, same verdicts as the backend.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";
import { sha256Hex } from "../src/replay/canon.ts";
import { buildAll } from "./fixtures/handmade/build.mjs";
import { generateLongBundle } from "./lib/builder.mjs";
import {
  HANDMADE_DIR,
  SHARED_DIR,
  readText,
  schema,
  sharedInvalidNames,
  validator,
} from "./lib/env.mjs";

test("sha256Hex matches node:crypto, including multi-block and non-ASCII input", () => {
  for (const text of ["", "abc", "a".repeat(55), "a".repeat(56), "a".repeat(64), "map\n".repeat(200), "艾拉米娅\n"]) {
    assert.equal(sha256Hex(text), createHash("sha256").update(text, "utf8").digest("hex"), text.slice(0, 8));
  }
});

test("FE-T09: the committed schema is the generated JSON Schema 2020-12 rooted at ReplayBundle", () => {
  assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema");
  assert.equal(schema.title, "ReplayBundle");
});

test("FE-T01: every valid hand-made fixture passes validation", () => {
  for (const [name, { expect }] of buildAll()) {
    if (expect !== "valid") continue;
    const result = validator.validateText(readText(`${HANDMADE_DIR}${name}`));
    assert.ok(result.ok, `${name}: ${result.ok ? "" : result.error.message}`);
  }
});

test("hand-made fixtures on disk equal the builder output (no drift)", () => {
  for (const [name, { text }] of buildAll()) {
    assert.equal(readText(`${HANDMADE_DIR}${name}`), text, `${name} drifted: run build.mjs`);
  }
});

test("FE-T08: broken, unknown-version, gapped and out-of-order files are refused with a clear error", () => {
  for (const [name, { expect }] of buildAll()) {
    if (expect === "valid") continue;
    const result = validator.validateText(readText(`${HANDMADE_DIR}${name}`));
    assert.ok(!result.ok, `${name} must be refused`);
    assert.equal(result.error.kind, expect.kind, `${name}: ${result.error.message}`);
    if (expect.rule) assert.equal(result.error.rule, expect.rule, name);
    assert.ok(result.error.message.length > 0);
  }
});

test("FE-T08: validation never repairs or modifies the parsed file", () => {
  const value = JSON.parse(readText(`${HANDMADE_DIR}edge-missing-frame.json`));
  const copy = structuredClone(value);
  assert.ok(!validator.validateValue(value).ok);
  assert.deepEqual(value, copy);
});

test("FE-T06: a generated 1,009-frame bundle validates", () => {
  const bundle = generateLongBundle(1008);
  assert.equal(bundle.frames.length, 1009);
  const result = validator.validateValue(bundle);
  assert.ok(result.ok, result.ok ? "" : result.error.message);
});

test("a Contract-wrapper-shaped input is refused by the schema", () => {
  const valid = JSON.parse(readText(`${SHARED_DIR}valid.json`));
  for (const wrapped of [{ ReplayBundle: valid }, { SnapshotMeta: { schema_version: "0.1", tick: 0 } }]) {
    const result = validator.validateValue(wrapped);
    assert.ok(!result.ok);
    assert.equal(result.error.kind, "schema");
  }
});

test("a payload that does not match its event type is refused", () => {
  const valid = JSON.parse(readText(`${SHARED_DIR}valid.json`));
  const failed = valid.events.find((e) => e.type === "action_succeeded");
  failed.type = "action_started"; // payload shape belongs to action_succeeded
  const result = validator.validateValue(valid);
  assert.ok(!result.ok);
  assert.equal(result.error.kind, "event_payload");
});

test("FE-T12: the shared valid fixture is accepted", () => {
  const result = validator.validateText(readText(`${SHARED_DIR}valid.json`));
  assert.ok(result.ok, result.ok ? "" : result.error.message);
});

// Groups whose backend rule slug differs from the fixture group name.
const RULE_BY_GROUP = { ground_fruit: "frame_sort" };
// OQ-013 / OQ-024 (owner-accepted): integral decimals such as 0.0 cannot be told from integers
// after JSON.parse. This is the one explicit exemption list for FE-T12 parity.
const INTEGRAL_DECIMAL_EXEMPT = new Set(["condition_bounds__min_value_float"]);
const SCHEMA_ONLY_OK = new Set(["schema", "map", "legend", "condition_bounds"]);

for (const name of sharedInvalidNames().filter((n) => !INTEGRAL_DECIMAL_EXEMPT.has(n))) {
  test(`FE-T12: shared invalid fixture ${name} is refused`, () => {
    const result = validator.validateText(readText(`${SHARED_DIR}invalid/${name}.json`));
    assert.ok(!result.ok, `${name} must be refused by the browser validator`);
    const group = name.split("__")[0];
    if (result.error.kind === "cross_field") {
      const expected = RULE_BY_GROUP[group] ?? group;
      if (group === "map") assert.ok(["map", "map_hash"].includes(result.error.rule), name);
      else if (!SCHEMA_ONLY_OK.has(group) || group === "legend")
        assert.equal(result.error.rule, expected, `${name}: ${result.error.message}`);
    } else {
      assert.ok(
        ["schema", "event_payload", "unknown_version"].includes(result.error.kind),
        `${name}: unexpected kind ${result.error.kind}`,
      );
    }
  });
}

test("FE-T12: every shared invalid fixture outside the exemption list is refused", () => {
  const refused = sharedInvalidNames()
    .filter((n) => !INTEGRAL_DECIMAL_EXEMPT.has(n))
    .filter((n) => !validator.validateText(readText(`${SHARED_DIR}invalid/${n}.json`)).ok);
  assert.equal(refused.length, sharedInvalidNames().length - INTEGRAL_DECIMAL_EXEMPT.size);
});

test("OQ-013/OQ-024: the exemption list holds integral-decimal fixtures only, and they are accepted (documented limitation)", () => {
  for (const name of INTEGRAL_DECIMAL_EXEMPT) {
    const text = readText(`${SHARED_DIR}invalid/${name}.json`);
    assert.match(text, /[0-9]\.0[,}\]]/, `${name} must contain an integral decimal literal`);
    const result = validator.validateText(text);
    assert.ok(result.ok, `${name}: the browser accepts it by documented limitation`);
  }
});

test("FE-T12: every shared cross-field rule group is refused as cross_field by the browser", () => {
  const crossGroups = new Set([
    "frame_ticks",
    "event_range",
    "event_order",
    "event_seq",
    "run_id",
    "event_id",
    "causal_refs",
    "utterance_refs",
    "entity_refs",
    "namespaces",
    "init_event",
    "frame_residents",
    "frame_sort",
    "trees",
    "coords",
    "conditions",
    "clock",
    "residents",
  ]);
  const seen = new Set();
  for (const name of sharedInvalidNames()) {
    const group = name.split("__")[0];
    if (!crossGroups.has(group)) continue;
    const result = validator.validateText(readText(`${SHARED_DIR}invalid/${name}.json`));
    assert.equal(result.error.kind, "cross_field", name);
    seen.add(group);
  }
  assert.deepEqual([...seen].sort(), [...crossGroups].sort());
});

test("OQ-013: an integral decimal such as 1.0 is not claimed to be detected", () => {
  // JSON.parse cannot tell 1.0 from 1, so the viewer accepts it; the backend refuses it.
  const text = readText(`${SHARED_DIR}valid.json`).replace('"tick":1,', '"tick":1.0,');
  assert.equal(JSON.parse(text).frames[1].tick, 1);
});

test("G2-02: exploration_updated indices must be strictly ascending and duplicate-free", () => {
  const make = (indices) => {
    const valid = JSON.parse(readText(`${SHARED_DIR}valid.json`));
    const last = valid.events[valid.events.length - 1];
    last.type = "exploration_updated";
    last.actor_id = "mia";
    last.caused_by_event_ids = [];
    last.payload = { resident_id: "mia", newly_seen_tile_indices: indices };
    return valid;
  };
  assert.ok(validator.validateValue(make([3, 4])).ok);
  assert.ok(validator.validateValue(make([])).ok);
  for (const bad of [[4, 3], [3, 3]]) {
    const result = validator.validateValue(make(bad));
    assert.ok(!result.ok, JSON.stringify(bad));
    assert.equal(result.error.rule, "event_payload");
    assert.match(result.error.message, /ascending and duplicate-free/);
  }
});
