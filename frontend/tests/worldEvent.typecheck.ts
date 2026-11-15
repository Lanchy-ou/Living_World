import type { ReplayBundle, WorldEvent } from "../src/api/generated/replay.ts";

export function movementDestination(
  event: ReplayBundle["events"][number],
): number | undefined {
  if (event.type === "resident_moved") {
    // @ts-expect-error A move does not have an action failure code.
    void event.payload.failure_code;
    return event.payload.to.x;
  }

  // @ts-expect-error Other events do not have a movement destination.
  return event.payload.to.x;
}

export function invalidPairing(event: Extract<WorldEvent, { type: "resident_moved" }>): WorldEvent {
  // @ts-expect-error A movement payload cannot be used for a failed action.
  return { ...event, type: "action_failed" };
}
