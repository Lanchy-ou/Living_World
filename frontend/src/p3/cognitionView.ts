import type { InspectionDecisionRef } from "./generated/index.ts";
import type { ExperienceRecord } from "./generated/sample.ts";

export function decisionAt(
  refs: readonly InspectionDecisionRef[], tick: number,
): InspectionDecisionRef | undefined {
  let start = 0;
  let end = refs.length;
  while (start < end) {
    const middle = start + Math.floor((end - start) / 2);
    const ref = refs[middle];
    if (ref.tick === tick) return ref;
    if (ref.tick < tick) start = middle + 1;
    else end = middle;
  }
}

export const experienceLabels: Record<ExperienceRecord["kind"], string> = {
  own_state: "Own condition and inventory",
  entity_seen: "Visible entity",
  transient_seen: "Transient sighting",
  cue_seen: "Environmental cue",
  heard_speech: "Heard speech",
  action_feedback: "Action feedback",
  accepted_decision: "Accepted plan",
};

export const prettyValue = (value: unknown): string => JSON.stringify(value, null, 2);
export const reported = (value: number | null, unit = ""): string => value === null ? "Unknown" : `${value}${unit}`;
