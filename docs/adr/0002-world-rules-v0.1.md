# ADR 0002: World Rules v0.1

- Status: accepted
- Date: 2026-11-08
- Task: P0-02 (review history: `docs/tasks/P0-02-rc3-review.md`)

## Context

World Rules v0.1-rc3 was reviewed and approved. It is landed as `docs/spec/world-rules-v0.1.md`,
`docs/spec/interface-contract-v0.1.md`, `docs/spec/balance-notes-v0.1.md` and
`content/worlds/default.toml` (+ `default-island.map`). This ADR records the decisions that
are not obvious from the spec text.

## Decisions

- **Map scale and movement:** 64×64 tiles at 50 m per tile; walking budget 8 cost units per
  tick (terrain costs are integers in the TOML).
- **Hydration decay:** the candidate value is 100 per tick. 120 is kept as a separate P2
  comparison and is not the default. Map size, speed and hydration must not all be retuned
  in the same comparison.
- **Canteen value is a hypothesis.** It is not an established balance fact. P2 tests it by
  comparing runs with and without the canteen at fixed geometry and hydration. Nonholder
  deaths are not a success criterion.
- **Day-one water cue:** a vague physical cue (damp moss at (15,32)) pointing east, with no
  spring coordinates.
- **Ownership of perception and decision context:** `world` builds `Perception`; `agents`
  builds `DecisionContext` from a `Perception` plus the character's own memory and goals.
  This extends ADR 0001 (perception lives in `world/`).
- **Freeze scope:** rules and semantics are frozen. Numeric values in
  `content/worlds/default.toml` are candidates tunable in P2 without changing the spec.
  `Perception`, `ActionPlan`, `ActionIntent`, `ActionResult` and `DecisionTrigger` are frozen
  unless the agent-interface spec requires a change, which needs a spec amendment task.
  `DecisionContext` remains provisional.

## Consequences

- P1 implements the spec; content-validation and engine tests from world rules §8 are P1 work
  (OQ-003).
- Balance changes in P2 edit the TOML only; any rule change goes through a spec amendment task.
