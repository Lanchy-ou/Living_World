import type { ReplayBundle } from "../src/api/generated/replay.ts";
import { frameAt, ReplayStore } from "../src/replay/store.ts";

export function checkReplayStoreTypes(bundle: ReplayBundle) {
  const store = new ReplayStore();
  store.load(bundle);
  // The caller's wire bundle remains writable after load.
  bundle.frames[0].residents[0].position.x = 0;

  const state = store.getState();
  // @ts-expect-error The public snapshot cannot set the playback tick.
  state.currentTick = 1;
  // @ts-expect-error The camera must be changed through the store.
  state.camera.panX = 1;
  // @ts-expect-error The filters must be changed through the store.
  state.filters.failuresOnly = true;

  if (state.bundle === null) return;
  // @ts-expect-error Published frame arrays cannot be reordered.
  state.bundle.frames.reverse();
  // @ts-expect-error A frame read through a helper retains its deep read-only view.
  frameAt(state.bundle, 0).residents[0].position.x = 0;

  const event = state.bundle.events[0];
  // @ts-expect-error An event's array fields are read-only.
  event.caused_by_event_ids.length = 0;
  if ("from" in event.payload) {
    // @ts-expect-error An event payload's nested fields are read-only.
    event.payload.from.x = 0;
  }
}
