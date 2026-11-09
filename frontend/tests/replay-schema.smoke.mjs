// Ajv2020 smoke test for the generated ReplayBundle JSON Schema (P1-01b).
// Run: pnpm --dir frontend run test:schema
// Cross-field rules (replay-frontend §2.3) are NOT expressible in JSON Schema; the browser
// validator (P1-08) checks them against the same shared fixtures. This test only proves
// the schema half: a raw valid bundle passes, wrapper-shaped and schema-invalid input fails.
import Ajv2020 from "ajv/dist/2020.js";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = (rel) => fileURLToPath(new URL(rel, import.meta.url));
const readJson = (path) => JSON.parse(readFileSync(path, "utf-8"));

const schema = readJson(here("../src/api/generated/replay.schema.json"));
assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema");
assert.equal(schema.title, "ReplayBundle");

const ajv = new Ajv2020({ strict: true, allErrors: true });
const validate = ajv.compile(schema);

const fixtures = here("../../backend/tests/fixtures/replay/");
const valid = readJson(`${fixtures}valid.json`);
const invalid = Object.fromEntries(
  readdirSync(`${fixtures}invalid`)
    .filter((f) => f.endsWith(".json"))
    .map((f) => [f.slice(0, -5), readJson(`${fixtures}invalid/${f}`)]),
);

let checks = 0;
function accepts(name, doc) {
  assert.ok(validate(doc), `${name}: expected acceptance, got ${ajv.errorsText(validate.errors)}`);
  checks++;
}
function refuses(name, doc) {
  assert.ok(!validate(doc), `${name}: expected refusal`);
  checks++;
}

accepts("valid.json", valid);
accepts("mechanics.replay.json", readJson(fixtures + "mechanics.replay.json"));

refuses("contract wrapper around a valid bundle", { ReplayBundle: valid });
refuses("legacy Contract wrapper", { SnapshotMeta: { schema_version: "0.1", tick: 0 } });
refuses("empty object", {});

// Every schema__* fixture must be refused by the schema alone.
const schemaOnly = Object.keys(invalid).filter((n) => n.startsWith("schema__"));
assert.ok(schemaOnly.length >= 5, "expected the schema__ fixtures");
for (const name of schemaOnly) refuses(name, invalid[name]);

// A few structural fixtures that the grammar itself also catches.
for (const name of [
  "map__unknown_symbol",
  "map__nonpositive_dimension",
  "legend__multichar_symbol",
  "condition_bounds__min_not_zero",
  "condition_bounds__min_value_false",
  "condition_bounds__max_not_above_min",
]) {
  refuses(name, invalid[name]);
}

console.log(`replay schema smoke test: ${checks} checks passed`);
