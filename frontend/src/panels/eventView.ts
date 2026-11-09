// Event list helpers. The resident filter is a fixed field mapping, never text matching, and
// summaries only restate payload fields: the viewer never explains why something happened.
import type { Filters } from "../replay/store.ts";
import type { ReplayBundle, WorldEvent } from "../replay/types.ts";
import { RESIDENT_REF_FIELDS } from "../replay/types.ts";

type Payload = Record<string, unknown>;
const payloadOf = (e: WorldEvent): Payload => e.payload as unknown as Payload;

/** actor_id, target_id, or a payload field defined as a resident reference. */
export function eventInvolvesResident(event: WorldEvent, residentId: string): boolean {
  if (event.actor_id === residentId || event.target_id === residentId) return true;
  const p = payloadOf(event);
  return RESIDENT_REF_FIELDS.some((field) => p[field] === residentId);
}

export function isFailureEvent(event: WorldEvent): boolean {
  return event.type === "action_failed" || event.type === "action_interrupted";
}

/** Authoritative failure code or interruption reason, as recorded. */
export function failureCode(event: WorldEvent): string | null {
  const p = payloadOf(event);
  if (event.type === "action_failed") return String(p["failure_code"]);
  if (event.type === "action_interrupted") return String(p["reason"]);
  return null;
}

export function filterEvents(bundle: ReplayBundle, filters: Filters): WorldEvent[] {
  return bundle.events.filter(
    (e) =>
      (filters.residentId === null || eventInvolvesResident(e, filters.residentId)) &&
      (!filters.failuresOnly || isFailureEvent(e)),
  );
}

const coord = (c: unknown): string => {
  const { x, y } = c as { x: number; y: number };
  return `(${x},${y})`;
};

/** Short summary built from payload fields only. */
export function summarize(event: WorldEvent): string {
  const p = payloadOf(event);
  switch (event.type) {
    case "world_initialized":
      return "world initialized";
    case "config_changed":
      return `${p["parameter"]}: ${p["old_value"]} -> ${p["new_value"]}`;
    case "action_started":
      return `${p["action_type"]} started, duration ${p["duration_ticks"] ?? "open"}`;
    case "action_progressed":
      return `${p["action_type"]} elapsed ${p["elapsed_ticks"]}, remaining ${p["remaining_ticks"] ?? "open"}`;
    case "resident_moved":
      return `${coord(p["from"])} -> ${coord(p["to"])}`;
    case "action_succeeded":
      return `${p["action_type"]} ${p["result_code"]}`;
    case "action_failed":
      return `${p["action_type"]} failed: ${p["failure_code"]}`;
    case "action_interrupted":
      return `${p["action_type"]} interrupted: ${p["reason"]}`;
    case "fruit_gathered":
      return `${p["tree_id"]} stock ${p["stock_before"]} -> ${p["stock_after"]}`;
    case "fruit_consumed":
      return `satiety ${p["satiety_before"]} -> ${p["satiety_after"]}`;
    case "water_drank":
      return `${p["source"]}: hydration ${p["hydration_before"]} -> ${p["hydration_after"]}`;
    case "canteen_filled":
      return `${p["canteen_id"]} servings ${p["servings_before"]} -> ${p["servings_after"]}`;
    case "stamina_action_cost_applied":
      return `${p["reason"]}: -${p["amount"]} stamina`;
    case "fruit_regrew":
      return `${p["tree_id"]} stock ${p["stock_before"]} -> ${p["stock_after"]}`;
    case "condition_updated":
      return `${p["resident_id"]} satiety ${p["satiety_before"]}->${p["satiety_after"]}, hydration ${p["hydration_before"]}->${p["hydration_after"]}, stamina ${p["stamina_before"]}->${p["stamina_after"]}, health ${p["health_before"]}->${p["health_after"]}`;
    case "utterance_spoken":
      return `${p["speech_act"]} to ${p["addressee_id"]}: ${JSON.stringify(p["text"])}`;
    case "utterance_heard":
      return `${p["listener_id"]} heard ${p["utterance_id"]}`;
    case "item_given":
      return `${p["item_type"]} x${p["quantity"]}: ${p["from_id"]} -> ${p["to_id"]}`;
    case "item_picked_up":
      return `${p["resident_id"]} picked up ${p["item_type"]} x${p["quantity"]} at ${coord(p["position"])}`;
    case "resident_died":
      return `${p["resident_id"]} died at ${coord(p["position"])} (${p["cause"]})`;
    case "corpse_created":
      return `${p["corpse_id"]} at ${coord(p["position"])}`;
    case "item_dropped":
      return `${p["resident_id"]} dropped ${p["item_type"]} x${p["quantity"]} at ${coord(p["position"])}`;
    case "exploration_updated":
      return `${p["resident_id"]} saw ${(p["newly_seen_tile_indices"] as unknown[]).length} new tiles`;
    case "agent_fallback_used":
      return `${p["resident_id"]} fallback ${p["fallback_policy_id"]} (${p["reason"]})`;
    case "god_intervention_recorded":
      return `${p["kind"]} for ${p["recipient_id"]}`;
  }
}
