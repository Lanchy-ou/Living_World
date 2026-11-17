# ADR 0009: World engine execution and dynamics

- Status: **Accepted** (owner M11, 2026-11-17). Existing specs stay in force
  until this ADR's spec replaces them.
- Date: 2026-11-15.
- Baseline: `bf5ed7d` (`task/P3.5-PR-01-protocol-adr`).
- Phase: P3.5, system 3 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: how the engine settles generic rules deterministically, runs processes,
  changes the world over time and persists artifacts. Rule format is ADR 0008;
  the action shape is ADR 0007.
- Spec to be written: `docs/spec/world-engine-v0.1.md`.
- Supersedes on acceptance: the settlement, timing and resource-dynamics parts of
  `world-rules-v0.1.md`.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
  The D2 change to interruption follows the owner's architecture discussion of
  2026-11-16 (ADR 0013 D3).

## Context

The v1 engine settles 11 hand-written actions with fixed preconditions, validates at
start and completion, orders conflicts by actor ID and uses one seeded RNG
(`resolution_rng_state_uint32` in `WorldState`). Fruit regrowth is a fixed engine
rule. ADR 0007 and ADR 0008 replace hand-written actions with data rules, add process
entities and success chances, and make world dynamics content. The engine must keep
byte-identical deterministic replay.

## Decision

### D1. Deterministic settlement

**[Owner]** Items first, then conditions:

1. Select candidate rules by trigger (`verb:<verb>`).
2. Keep the candidates whose item predicates (target, instruments, inputs)
   match. Conditions (actor state, surroundings, time) are not checked yet.
3. Among the remaining candidates whose conditions hold, choose the most
   specific (most item predicates plus conditions), then the lowest `rule_id`
   in byte order, and settle it.
4. If candidates remain but none has its conditions met, settle as unmet: no
   effect, the most specific candidate's `unmet` phenomenon (ADR 0007 D5), and
   that `rule_id` in the objective log.
5. If no candidate remains, settle as a no-match attempt: phenomena only, plus
   an objective `attempt_unmatched` event (ADR 0007 D5).

Example: rule A turns clay into pottery when heated next to a fire; rule B turns
heated clay into dried clay anywhere. Heating clay next to a fire gives pottery
(A has the same item predicate plus a condition, so it is more specific). Away from a fire it gives dried clay (B). If B did not
exist, it would give A's `unmet` phenomenon.

Further settlement rules:

6. Inputs are reserved at start and validated again at completion.
7. Conflicts between actors keep the v1 order: ascending actor ID, and the v1
   completion shuffle on its own stream (`world-rules-v0.1.md` §5.6), unchanged.
8. **[Owner]** Success chances do not use the v1 stream. Each roll is derived
   from the run seed and the roll's identity (tick, `rule_id`, intent or entity
   ID), not from its position in one shared sequence. One actor's extra attempt
   then never shifts the luck of other events, so runs that differ only in agent
   behaviour (for example memory on and off) see the same luck for the same
   events. This follows v1 §5.6: new randomness gets its own named stream.

### D2. Processes

- Personal timed actions keep the v1 duration and progress.
- **[Owner]** Only hard stops end an action from the world side (ADR 0007 D6).
  Speech, sightings and need thresholds are reported as notifications, not
  acted on; the resident decides at its turn (ADR 0013 D3). A stop, by the
  world or by the resident choosing another action, takes effect at a tick
  boundary and applies the rule's `on_interrupt`.
- Process entities hold progress that outlives one actor or accepts several
  contributors. `contribute` adds work until the rule's `work_ticks` total is
  reached (ADR 0007 D6).
- Process progress is world state and is saved in snapshots.

### D3. World dynamics as rules

- Regrowth, decay, a fire going out and tool wear are rules with `every:` or
  `when:` triggers (ADR 0008 D4).
- World rules run in a fixed phase of each tick, in `rule_id` order, then entity
  ID order.
- **[Owner]** Weather and seasons are deferred. When added, they are global
  state variables that rule conditions may read. The engine reserves a place
  for them but implements none in P3.5.

### D4. Artifacts

- Every artifact is an entity with an engine-allocated deterministic ID.
- An artifact is either on a tile or held (in an inventory or a container).
- Artifacts, their state, durability and `owner_id` are saved in snapshots.

### D5. Rule library changes and saves

- A save records the rule library and vocabulary hashes. Restore refuses a
  mismatch, as v1 refuses wrong versions. There is no implicit migration.
- A rule may be added during a run only at a boundary, logged as an objective
  `rule_added` event, so replay knows which rules applied at every tick.

## Consequences

- The engine becomes a generic interpreter of a closed rule language; per-recipe
  code is forbidden and tested against (ADR 0010 D4).
- Rule specificity ordering must be documented with test vectors, because two
  overlapping rules are a likely content mistake. The clay example in D1 is the
  first vector.
- Derived chance rolls need a fixed derivation function and test vectors in the
  spec, so any implementation reproduces the same rolls.
- Snapshots grow with the number of artifacts and processes; the storage plan
  is a separate discussion.

## Open questions

| ID | Question |
|---|---|
| Q1 | The tick phase order for world rules relative to actor settlement, physiology and hard stops. |
| Q2 | Is specificity "number of predicates" good enough, or should content declare explicit priorities? |
| Q3 | Do failed chance rolls consume inputs, part of them, or none? |
| Q4 | Can a process entity be abandoned, and does its progress decay? |
| Q5 | Limits on artifact count per tile and per world, for performance and snapshot size. |
