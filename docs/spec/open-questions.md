# Open Questions

Add an entry whenever the spec is missing or ambiguous. Do not invent rules or numbers:
record the question, make the smallest reversible assumption, and flag it in your handoff.

| ID | Date | Raised in task | Question | Assumption made | Status |
|---|---|---|---|---|---|
| OQ-001 | 2026-11-08 | P0-01 | The product doc names a module `interface` (player interaction, saving, observation, debugging) but the P0-01 structure has no such package; its responsibilities are spread over `sim`, `persistence` and `contract`. Is a separate `interface`/API package wanted later (FastAPI)? | None; no `interface` package created. | open |
| OQ-002 | 2026-11-08 | P0-01a | Memory import-linter contract has `unmatched_ignore_imports_alerting = "none"` because no memory module imports `world.protocol` yet. | Keep `none`; switch to `error` when the first memory module imports `world.protocol`. | open |
| OQ-003 | 2026-11-08 | P0-02 | Content-validation and engine tests listed in world rules §8 are P1 work. | None; only a minimal content test (`test_default_content.py`) is added in P0-02. | open |
| OQ-004 | 2026-11-09 | P1-01a | World Rules §1.2 says cue coordinates must match "the respective symbols" but only `M` maps to a cue. Are other cue kinds allowed? | `CueConfig.kind` accepts only `damp_moss`, and exactly one cue must sit on the single `M`. | open |
| OQ-005 | 2026-11-09 | P1-01a | "Need-band cutoffs are four strictly increasing interior values" (World Rules §1.1): is the upper bound strict? | Require `min_value < a < b < c < d < max_value`. | open |
| OQ-006 | 2026-11-09 | P1-01a | The `.map` grammar says LF line endings but not whether the last row needs one; the map hash includes a final LF. | Every row, including the last, must end in LF (the default map does). | open |
| OQ-007 | 2026-11-09 | P1-01a | Several fields have no declared range (goal `priority`; social counters). | Unspecified counters are nonnegative; `priority` is any integer. (Rework 1: the payload `action_type`/`failure_code` narrowing was removed; they are `string` per IC §3.2.) | open |
| OQ-008 | 2026-11-09 | P1-01a | AI §6 requires one pending packet per living actor but does not say whether `runtime_states` covers dead residents too. | `runtime_states` holds exactly one entry per world resident (alive or dead), in `actor_id` order; pending packets cover living actors only. | open |
| CR-001 | 2026-11-09 | P1-01a (G2-06) | Change request (plan §7): does IC §4 "invalid parameter shape → bounded failure" conflict with `ActionIntent` rejecting malformed shapes at construction (AI §3.1 layer 1)? | Owner-approved option A: IC §4 covers well-formed DTOs with invalid values (bounded world failure); malformed shapes cannot be constructed and are `INVALID_PLAN` in agents. Clarification added to IC §4, marked `[A1]`. | closed |
