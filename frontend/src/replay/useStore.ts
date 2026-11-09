import { useSyncExternalStore } from "react";
import type { ReplayState, ReplayStore } from "./store.ts";

export function useReplayState(store: ReplayStore): ReplayState {
  return useSyncExternalStore(store.subscribe, store.getState);
}
