// What a resident is recorded as doing at a tick, for the status chip and the map bubble.
// This only restates recorded fields (`active_action`, `alive`) and the tick's own events; it
// never infers intent, cause or success that the replay does not state.
import { eventsOfFrame, frameAt } from "../replay/store.ts";
import type { ReplayBundle, WorldEvent } from "../replay/types.ts";
import type { EmoteName } from "../render/assets/objectArt.ts";
import { failureCode } from "./eventView.ts";

type Payload = Record<string, unknown>;
const payloadOf = (e: WorldEvent): Payload => e.payload as unknown as Payload;

/** Fixed display names for recorded action types. An unknown type is shown as recorded. */
const ACTION_LABELS: Record<string, string> = {
  move_to: "Walking",
  gather: "Gathering",
  eat: "Eating",
  drink: "Drinking",
  fill_canteen: "Filling canteen",
  rest: "Resting",
  sleep: "Sleeping",
  talk: "Talking",
  give: "Giving",
  pick_up: "Picking up",
  wait: "Waiting",
};

const ACTION_EMOTES: Record<string, EmoteName> = {
  gather: "fruit",
  eat: "fruit",
  drink: "water",
  fill_canteen: "water",
  rest: "rest",
  sleep: "sleep",
  talk: "talk",
  give: "hand",
  pick_up: "hand",
};

/** Events recorded in this tick whose type shows as a bubble, by the acting resident. */
const EVENT_EMOTES: Record<string, EmoteName> = {
  water_drank: "water",
  canteen_filled: "water",
  fruit_gathered: "fruit",
  fruit_consumed: "fruit",
  utterance_spoken: "talk",
  item_given: "hand",
  item_picked_up: "hand",
};

export function actionLabel(actionType: string): string {
  return ACTION_LABELS[actionType] ?? actionType;
}

export type ActivityKind = "dead" | "active" | "finished" | "failed" | "interrupted" | "none";

export interface Activity {
  kind: ActivityKind;
  /** Short status text, e.g. "Gathering" or "Gather failed: RESOURCE_TAKEN". */
  label: string;
  /** Bubble shown above the resident on the map, or null. */
  emote: EmoteName | null;
  /** Recorded action type, when one applies. */
  actionType: string | null;
  /** Authoritative failure code or interruption reason, as recorded. */
  code: string | null;
}

function lastOf(events: WorldEvent[], pred: (e: WorldEvent) => boolean): WorldEvent | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i] as WorldEvent;
    if (pred(e)) return e;
  }
  return undefined;
}

function tickEventsBy(bundle: ReplayBundle, tick: number, residentId: string): WorldEvent[] {
  return eventsOfFrame(bundle, frameAt(bundle, tick)).filter((e) => e.actor_id === residentId);
}

/** The recorded death of a resident, if it happened at or before `tick`. */
export function deathRecord(
  bundle: ReplayBundle,
  tick: number,
  residentId: string,
): { tick: number; cause: string } | null {
  for (const e of bundle.events) {
    if (e.tick > tick) break;
    if (e.type === "resident_died" && payloadOf(e)["resident_id"] === residentId) {
      return { tick: e.tick, cause: String(payloadOf(e)["cause"]) };
    }
  }
  return null;
}

export function activityOf(bundle: ReplayBundle, tick: number, residentId: string): Activity {
  const resident = frameAt(bundle, tick).residents.find((r) => r.id === residentId);
  const none: Activity = { kind: "none", label: "No action recorded", emote: null, actionType: null, code: null };
  if (resident === undefined) return none;
  if (!resident.alive) return { kind: "dead", label: "Dead", emote: null, actionType: null, code: null };

  const events = tickEventsBy(bundle, tick, residentId);
  const failed = lastOf(events, (e) => e.type === "action_failed");
  if (failed !== undefined) {
    const type = String(payloadOf(failed)["action_type"]);
    const code = failureCode(failed);
    return { kind: "failed", label: `${actionLabel(type)} failed: ${code}`, emote: "fail", actionType: type, code };
  }

  const active = resident.active_action;
  if (active !== null) {
    return {
      kind: "active",
      label: actionLabel(active.action_type),
      emote: ACTION_EMOTES[active.action_type] ?? null,
      actionType: active.action_type,
      code: null,
    };
  }

  const interrupted = lastOf(events, (e) => e.type === "action_interrupted");
  if (interrupted !== undefined) {
    const type = String(payloadOf(interrupted)["action_type"]);
    const code = failureCode(interrupted);
    return {
      kind: "interrupted",
      label: `${actionLabel(type)} interrupted: ${code}`,
      emote: null,
      actionType: type,
      code,
    };
  }

  const succeeded = lastOf(events, (e) => e.type === "action_succeeded");
  const shown = lastOf(events, (e) => e.type in EVENT_EMOTES);
  if (succeeded !== undefined) {
    const type = String(payloadOf(succeeded)["action_type"]);
    return {
      kind: "finished",
      label: `${actionLabel(type)} (finished)`,
      emote: shown === undefined ? null : (EVENT_EMOTES[shown.type] as EmoteName),
      actionType: type,
      code: null,
    };
  }
  return none;
}
