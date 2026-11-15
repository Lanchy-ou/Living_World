// Runtime validation of a replay file: JSON parse, Ajv2020 against the generated schema,
// payload/type agreement, then the cross-field rules. The file is never repaired or modified.
import Ajv2020 from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv/dist/2020.js";
import type { ReplayBundle } from "../api/generated/replay.ts";
import { checkCrossField } from "./crossField.ts";
import type { LoadResult, ReplayError, WorldEvent } from "./types.ts";

const MAX_DETAILS = 8;

export interface ReplayValidator {
  validateText(text: string): LoadResult;
  validateValue(value: unknown): LoadResult;
}

const fail = (error: ReplayError): LoadResult => ({ ok: false, error });

/** `world_initialized` -> `WorldInitializedPayload`, the definition name in the generated schema. */
function payloadDefinitionName(eventType: string): string {
  const pascal = eventType
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
  return `${pascal}Payload`;
}

/**
 * Builds a validator from the generated `replay.schema.json` (JSON Schema 2020-12).
 * The schema is passed in so Node tests and the Vite app can load it their own way.
 */
export function createReplayValidator(schema: object): ReplayValidator {
  const ajv = new Ajv2020({ strict: true, allErrors: false });
  ajv.addSchema(schema, "replay");
  const root = ajv.getSchema("replay") as ValidateFunction;
  const payloadValidators = new Map<string, ValidateFunction>();
  const defs = (schema as { $defs?: Record<string, unknown> }).$defs ?? {};
  for (const name of Object.keys(defs)) {
    if (name.endsWith("Payload")) {
      const v = ajv.getSchema(`replay#/$defs/${name}`);
      if (v) payloadValidators.set(name, v);
    }
  }

  function validateValue(value: unknown): LoadResult {
    const version =
      typeof value === "object" && value !== null
        ? (value as Record<string, unknown>)["replay_schema_version"]
        : undefined;
    if (version !== undefined && version !== "0.1") {
      return fail({
        kind: "unknown_version",
        message: `Unknown replay_schema_version ${JSON.stringify(version)}; only "0.1" is supported`,
        details: [],
      });
    }
    if (!root(value)) {
      const errors = root.errors ?? [];
      const details = errors
        .slice(0, MAX_DETAILS)
        .map((e) => `${e.instancePath === "" ? "(root)" : e.instancePath}: ${e.message ?? "invalid"}`);
      return fail({
        kind: "schema",
        message: `The file is not a valid ReplayBundle (${details[0] ?? "schema error"})`,
        details,
      });
    }
    const bundle = value as unknown as ReplayBundle;
    const mismatch = checkPayloadTypes(bundle.events);
    if (mismatch !== null) return fail(mismatch);
    const crossField = checkCrossField(bundle);
    if (crossField !== null) return fail(crossField);
    return { ok: true, bundle };
  }

  /** The schema allows any payload for any type; the type must name its own payload shape. */
  function checkPayloadTypes(events: WorldEvent[]): ReplayError | null {
    for (const e of events) {
      const name = payloadDefinitionName(e.type);
      const check = payloadValidators.get(name);
      if (check === undefined || !check(e.payload)) {
        const message = `event_payload: payload of ${e.event_id} does not match event type ${e.type}`;
        return { kind: "event_payload", rule: "event_payload", message, details: [message] };
      }
    }
    return null;
  }

  return {
    validateValue,
    validateText(text: string): LoadResult {
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        return fail({ kind: "broken_json", message: "The file is not valid JSON", details: [detail] });
      }
      return validateValue(parsed);
    },
  };
}
