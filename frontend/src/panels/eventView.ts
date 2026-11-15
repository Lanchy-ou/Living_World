// Event list helpers. The resident filter is a fixed field mapping, never text matching, and
// summaries only restate payload fields: the viewer never explains why something happened.
import type { Filters } from "../replay/store.ts";
import type { ReplayBundle, WorldEvent } from "../replay/types.ts";
import { RESIDENT_REF_FIELDS } from "../replay/types.ts";

type ResidentReferenceFields = Partial<Record<(typeof RESIDENT_REF_FIELDS)[number], string>>;

/** actor_id, target_id, or a payload field defined as a resident reference. */
export function eventInvolvesResident(event: WorldEvent, residentId: string): boolean {
  if (event.actor_id === residentId || event.target_id === residentId) return true;
  const payload: WorldEvent["payload"] & ResidentReferenceFields = event.payload;
  return RESIDENT_REF_FIELDS.some((field) => payload[field] === residentId);
}

export function isFailureEvent(event: WorldEvent): boolean {
  return event.type === "action_failed" || event.type === "action_interrupted";
}

/** Authoritative failure code or interruption reason, as recorded. */
export function failureCode(event: WorldEvent): string | null {
  const { type, payload } = event;
  if (type === "action_failed") return payload.failure_code;
  if (type === "action_interrupted") return payload.reason;
  return null;
}

export function filterEvents(bundle: ReplayBundle, filters: Filters): WorldEvent[] {
  return bundle.events.filter(
    (e) =>
      (filters.residentId === null || eventInvolvesResident(e, filters.residentId)) &&
      (!filters.failuresOnly || isFailureEvent(e)),
  );
}

const coord = ({ x, y }: { x: number; y: number }): string => `(${x},${y})`;

/** Short summary built from payload fields only. */
export function summarize(event: WorldEvent): string {
  const { type, payload } = event;
  switch (type) {
    case "world_initialized":
      return "world initialized";
    case "config_changed":
      return `${payload.parameter}: ${payload.old_value} -> ${payload.new_value}`;
    case "action_started":
      return `${payload.action_type} started, duration ${payload.duration_ticks ?? "open"}`;
    case "action_progressed":
      return `${payload.action_type} elapsed ${payload.elapsed_ticks}, remaining ${payload.remaining_ticks ?? "open"}`;
    case "resident_moved":
      return `${coord(payload.from)} -> ${coord(payload.to)}`;
    case "action_succeeded":
      return `${payload.action_type} ${payload.result_code}`;
    case "action_failed":
      return `${payload.action_type} failed: ${payload.failure_code}`;
    case "action_interrupted":
      return `${payload.action_type} interrupted: ${payload.reason}`;
    case "fruit_gathered":
      return `${payload.tree_id} stock ${payload.stock_before} -> ${payload.stock_after}`;
    case "fruit_consumed":
      return `satiety ${payload.satiety_before} -> ${payload.satiety_after}`;
    case "water_drank":
      return `${payload.source}: hydration ${payload.hydration_before} -> ${payload.hydration_after}`;
    case "canteen_filled":
      return `${payload.canteen_id} servings ${payload.servings_before} -> ${payload.servings_after}`;
    case "stamina_action_cost_applied":
      return `${payload.reason}: -${payload.amount} stamina`;
    case "fruit_regrew":
      return `${payload.tree_id} stock ${payload.stock_before} -> ${payload.stock_after}`;
    case "condition_updated":
      return `${payload.resident_id} satiety ${payload.satiety_before}->${payload.satiety_after}, hydration ${payload.hydration_before}->${payload.hydration_after}, stamina ${payload.stamina_before}->${payload.stamina_after}, health ${payload.health_before}->${payload.health_after}`;
    case "utterance_spoken":
      return `${payload.speech_act} to ${payload.addressee_id}: ${JSON.stringify(payload.text)}`;
    case "utterance_heard":
      return `${payload.listener_id} heard ${payload.utterance_id}`;
    case "item_given":
      return `${payload.item_type} x${payload.quantity}: ${payload.from_id} -> ${payload.to_id}`;
    case "item_picked_up":
      return `${payload.resident_id} picked up ${payload.item_type} x${payload.quantity} at ${coord(payload.position)}`;
    case "resident_died":
      return `${payload.resident_id} died at ${coord(payload.position)} (${payload.cause})`;
    case "corpse_created":
      return `${payload.corpse_id} at ${coord(payload.position)}`;
    case "item_dropped":
      return `${payload.resident_id} dropped ${payload.item_type} x${payload.quantity} at ${coord(payload.position)}`;
    case "exploration_updated":
      return `${payload.resident_id} saw ${payload.newly_seen_tile_indices.length} new tiles`;
    case "agent_fallback_used":
      return `${payload.resident_id} fallback ${payload.fallback_policy_id} (${payload.reason})`;
    case "god_intervention_recorded":
      return `${payload.kind} for ${payload.recipient_id}`;
  }
}
