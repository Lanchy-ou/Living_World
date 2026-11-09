// Types come straight from the generated replay types; nothing is redefined by hand.
import type {
  DisplayFrame,
  ReplayBundle,
  ResidentFrame,
  WorldEvent,
} from "../api/generated/replay.ts";

export type { DisplayFrame, ReplayBundle, ResidentFrame, WorldEvent };

/** Why a file was refused. The viewer never repairs data. */
export interface ReplayError {
  kind: "broken_json" | "unknown_version" | "schema" | "event_payload" | "cross_field";
  /** Rule slug for cross-field errors (same slugs as backend `contract/replay.py`). */
  rule?: string;
  message: string;
  details: string[];
}

export type LoadResult = { ok: true; bundle: ReplayBundle } | { ok: false; error: ReplayError };

/** Payload fields that reference a resident (replay-frontend §4.4; `recipient_id` per OQ-009). */
export const RESIDENT_REF_FIELDS = [
  "resident_id",
  "from_id",
  "to_id",
  "listener_id",
  "addressee_id",
  "recipient_id",
] as const;
