// Derive the viewer's read-only types from the generated replay contract.
import type {
  DisplayFrame as WireDisplayFrame,
  ReplayBundle as WireReplayBundle,
  ResidentFrame as WireResidentFrame,
  WorldEvent as WireWorldEvent,
} from "../api/generated/replay.ts";

export type DeepReadonly<T> = T extends object
  ? { readonly [Key in keyof T]: DeepReadonly<T[Key]> }
  : T;

export type DisplayFrame = DeepReadonly<WireDisplayFrame>;
export type ReplayBundle = DeepReadonly<WireReplayBundle>;
export type ResidentFrame = DeepReadonly<WireResidentFrame>;
export type WorldEvent = DeepReadonly<WireWorldEvent>;

/** Why a file was refused. The viewer never repairs data. */
export interface ReplayError {
  kind: "file_read" | "broken_json" | "unknown_version" | "schema" | "event_payload" | "cross_field";
  /** Rule slug for cross-field errors (same slugs as backend `contract/replay.py`). */
  rule?: string;
  message: string;
  details: string[];
}

export type LoadResult = { ok: true; bundle: WireReplayBundle } | { ok: false; error: ReplayError };

/** Payload fields that reference a resident (replay-frontend §4.4; `recipient_id` per OQ-009). */
export const RESIDENT_REF_FIELDS = [
  "resident_id",
  "from_id",
  "to_id",
  "listener_id",
  "addressee_id",
  "recipient_id",
] as const;
