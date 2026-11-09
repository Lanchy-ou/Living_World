// Shared test setup: the generated schema, a validator and fixture readers.
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createReplayValidator } from "../../src/replay/validate.ts";

const here = (rel) => fileURLToPath(new URL(rel, import.meta.url));

export const SCHEMA_PATH = here("../../src/api/generated/replay.schema.json");
export const HANDMADE_DIR = here("../fixtures/handmade/");
export const SHARED_DIR = here("../../../backend/tests/fixtures/replay/");

export const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf-8"));
export const validator = createReplayValidator(schema);

export const readText = (path) => readFileSync(path, "utf-8");

export function loadHandmade(name) {
  const result = validator.validateText(readText(`${HANDMADE_DIR}${name}`));
  if (!result.ok) throw new Error(`${name}: ${result.error.message}`);
  return result.bundle;
}

export function sharedInvalidNames() {
  return readdirSync(`${SHARED_DIR}invalid`)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.slice(0, -5))
    .sort();
}
