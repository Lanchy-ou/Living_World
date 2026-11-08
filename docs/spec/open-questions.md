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
| OQ-007 | 2026-11-09 | P1-01a | Several fields have no declared range (event `action_type`/`failure_code` are typed `string`; goal `priority`; social counters). | Payload `action_type`/`failure_code` use the ActionType/FailureCode vocabularies; unspecified counters are nonnegative; `priority` is any integer. | open |
