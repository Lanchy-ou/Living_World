# Living Island — World Engine v0.1 (P3.5 v2 lane)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §17 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
>
> Implements [ADR 0009](../adr/0009-world-engine.md). Works with the frozen
> [world–agent protocol](world-agent-protocol-v0.1.md) and with
> [rule representation](rule-representation-v0.1.md). When frozen, it
> supersedes for new work in the v2 lane the settlement, timing and
> resource-dynamics parts of `world-rules-v0.1.md` (§3 physiology, §4.1
> timing, §5.4–§5.6). Sight, hearing, pathfinding and movement (§5.1–§5.3)
> are kept unchanged. The v1 text stays in force for v1 runs.

## 0. Scope

### 0.1 Covered here

- Entity IDs and the v2 world state, and what a snapshot holds (ADR 0009 D4).
- The tick phases (ADR 0009 Q1) and where each check, effect, stop and
  report happens.
- How an `act` is settled: rule selection, reservation, completion, chance
  rolls (ADR 0009 D1).
- How kernel actions settle and what events they emit.
- Process entities and contributions (ADR 0009 D2).
- World rules (ADR 0009 D3).
- Base physiology, awareness, mental fatigue, fainting and waking.
- The events of rule effects (protocol §9 delegates them here).
- Rule library changes and saves (ADR 0009 D5), limits (Q5) and
  determinism.

### 0.2 Owned elsewhere

| Subject | Spec |
|---|---|
| Intent, perception, feedback, reports, speech checks, hard-stop list | `world-agent-protocol-v0.1.md` (frozen) |
| Rule format, matching, specificity count, validator, conservation | `rule-representation-v0.1.md` |
| Every value: rates, durations, thresholds, limits, fatigue coefficients | `starter-content-v0.1.md` |
| Turn scheduling and model calls between ticks | `decision-loop-v0.1.md` |

The engine is a generic interpreter of the rule language. It contains no code
for any recipe, archetype or material ID (ADR 0009 consequences, ADR 0010 D4).

## 1. Entity IDs

- Entities placed by a pack keep their content IDs (rule representation
  §4.4). The compatibility pack keeps the v1 IDs of trees and the canteen
  (protocol §11.2).
- Corpses keep the v1 form `corpse@<resident_id>`.
- Every other entity gets an engine ID when it is created:
  `e:<tick, 10 digits>:<n, 4 digits>`, where `n` counts creations in that
  tick from zero in creation order. For example, the third entity created in
  tick 7 is `e:0000000007:0002`. Engine IDs contain `:`, which content IDs
  cannot, so they never collide. IDs are never reused.
- A split stack's moving part, a merged stack's survivor and every output get
  their IDs by these rules only, so replay reproduces them.

## 2. World state and snapshots

`WorldState` v2 keeps the v1 fields that still apply (`interface-contract-
v0.1.md` §2.1: tick, clock, hashes, map, residents' position and alive flag,
exploration footprints, receipts, dialogue sessions, `resolution_rng` state,
event cursor) and adds:

| Field | Content |
|---|---|
| `entities` | Every non-resident entity: `entity_id`, `archetype_id`, `material_id`, `quantity`, `created_tick`, `owner_id`, place, component state, apparent overrides and tells. Sorted by entity ID |
| `needs` | Per resident, the stored value of each enabled need, sorted by need ID |
| `awareness` | Per resident: `awake`, `asleep` or `unconscious`, and for `unconscious` the tick it ends |
| `active_actions` | Per actor: the complete intent, `tick_started`, elapsed work, due tick or `null`, route state, the chosen `rule_id`, the resolved and reserved items by slot, and any pending outcome decided at start |
| `phase_offsets` | Per entity and `every:` rule, from content |
| `fatigue_inputs` | Per resident, the counts of the last delivered packet that mental fatigue reads (§9.3) |
| `library` | `vocabulary_hash`, `rule_library_hash`, the active rule IDs and `pack_ids` |

- The v1 fields `fruit_nodes`, `ground_fruit` and the canteen record are
  replaced by entities.
- A snapshot holds everything above (ADR 0009 D4). It is taken only at a
  completed boundary, after commit (phase 7), as in v1
  (`interface-contract-v0.1.md` §5).
- Restore refuses a snapshot whose vocabulary or library hash differs from
  the loaded content. There is no implicit migration (ADR 0009 D5).

## 3. The tick

A completed tick `t → t+1` runs these phases. Phases 2 and 3 keep the v1
order exactly, which the compatibility check depends on.

| Phase | Name | What happens |
|---|---|---|
| 1 | Boundary input | Packets for `t` are delivered and acknowledged; turns are collected (decision-loop spec). Rules approved for addition are added, each with `rule_added`. For each turn that chooses a new action while one runs, that action stops by the actor at `t` and its `on_interrupt` applies (protocol §4.4) |
| 2 | Action progress | Actors in ascending ID order (protocol §2): first utterance check, start of a new action, then one tick of progress (§4) |
| 3 | Completion resolution | The completion set is shuffled and settled (§5) |
| 4 | World rules | Every `every:` and `when:` rule, process rules included, in `rule_id` order, then subject entity ID order (§8) |
| 5 | Physiology and death | Living residents in ascending ID order (§9) |
| 6 | Stops, waking and perception | Hard stops of unfinished actions, waking, visibility, exploration, receipts, watching, reports and packets for `t+1` (§10) |
| 7 | Commit | As v1 (`world-rules-v0.1.md` §5.4 step 7) |

- All events of phases 1–6 belong to tick `t+1`, as in v1.
- Model calls happen between phase 7 of one tick and phase 1 of the next.
  The world clock does not move while one is outstanding (protocol §2).

## 4. Phase 2: action progress

For each living actor, in ascending actor ID order:

1. **First utterance check.** If the actor's turn carries an utterance, its
   first check runs now, before the actor's own action starts or advances
   (protocol §7.1). A failure is kept.
2. **Start.** If the turn carries an intent, it starts now (§4.1). An
   unconscious or sleeping actor has no turn.
3. **Progress.** The actor's running action, new or old, advances one tick
   (§4.2), unless its outcome was decided at start.

Lower-ID actors have started and advanced before a higher-ID actor's start
checks run, which is the protocol's start rule (§2). No shared inventory or
resource transfer settles in this phase, as in v1.

### 4.1 Starting an action

- Kernel actions run their start checks (protocol §4.2). A failure fixes the
  outcome now: it ends at `t + invalid_attempt_ticks` with its failure code.
- `act` runs the generic checks (protocol §4.3), resolves item choices
  (protocol §3.2) and selects a rule:
  1. **Candidates**: the active rules with trigger `verb:<verb>`.
  2. **Item match**: keep the candidates the intent matches (rule
     representation §5.2). Conditions are not checked yet.
  3. **Choose**: among the remaining candidates whose conditions all hold,
     take the most specific (rule representation §5.3), then the lowest
     `rule_id` in byte order. The action runs for that rule's work time.
  4. **Unmet**: if candidates remain but none has its conditions met, the
     outcome is fixed now as `settled/unmet` at start: the most specific
     candidate (then lowest `rule_id`) is named, its first failing condition
     is `failed_check`, and its `unmet` phenomena are the feedback.
  5. **Unmatched**: if no candidate remains, the outcome is fixed now as
     `settled/unmatched`, with the verb's comparison-table phenomena and an
     `attempt_unmatched` event carrying the attempt descriptor (rule
     representation §5.7, §6).
  Unmet and unmatched outcomes end at `t + attempt_ticks` of the verb
  (protocol §4.3).
- **Reservation.** The items in a chosen rule's slots are reserved for the
  action (ADR 0007 D6). A reserved item cannot be used by another action of
  the same actor; since only its holder can move a held item and an actor has
  one action, no other actor can take it through a kernel action. World rules
  are not blocked by reservations (owner, EN-D3): if a world rule consumes or
  changes a reserved item, the completion check finds it (§5.2).
- `action_started` is emitted for every start, with the duration known at
  start, or `null` for movement and `contribute`.
- A sleep verb (`awareness_during = "asleep"`) makes the actor `asleep` from
  this tick, with `resident_fell_asleep`.

### 4.2 One tick of progress

In this order, for the actor's running action:

1. **Exhaustion.** If the action is a movement, or an `act` whose rule has
   `exhaustion_stops = true`, and the actor's stamina is at its minimum, the
   action stops with `EXHAUSTED` now, without progress (§10.1). This is v1's
   check (`world/engine.py` `_progress`).
2. **Per-tick need effects** of the chosen rule apply, clamped, as v1's rest
   and sleep gains do in this phase.
3. **Movement** traverses steps under its budget, recomputing sight after
   each step, exactly as v1 (`world-rules-v0.1.md` §5.1, §5.3). A blocked next
   step stops the movement with `PATH_BLOCKED` (§10.1). Completed steps stay.
4. **Contribution.** A running `contribute` adds one unit of work to its
   process when §7.2 allows it.
5. Elapsed work advances by one. An action that reaches its due tick, and a
   movement that enters its target, joins the completion set.

An action whose outcome was fixed at start joins the completion set at its
due tick without progressing. `action_progressed` is emitted for each
unfinished action, as v1.

## 5. Phase 3: completion resolution

### 5.1 The completion set

- The set holds every action due in this tick, including actions whose
  outcome was fixed at start and actions stopped in phase 2 by `EXHAUSTED` or
  `PATH_BLOCKED`, as v1 holds pending failures.
- It also holds every **lone utterance**: an utterance whose turn's action
  does not finish in this tick (a `continue`, or a longer action). An
  utterance whose turn's action finishes in this tick is attached to that
  action instead.
- Sort by `(actor_id, key)`, where `key` is the intent ID, or `turn_id + ":u"`
  for a lone utterance. Then apply the v1 Fisher–Yates shuffle with
  `resolution_rng` to the whole set (`world-rules-v0.1.md` §5.4 step 3, §5.6,
  unchanged; ADR 0009 D1 item 7).
- In the compatibility pack every utterance rides a one-tick `wait` that
  finishes in the same tick (protocol §11.2), so there are no lone utterances
  and the set has exactly the v1 members. The shuffle then draws exactly as
  v1 does.

### 5.2 Settling each member, in shuffled order

1. An attached or lone utterance gets its second check and is emitted if it
   passes (protocol §7.1). An attached utterance is emitted before its
   action settles, as v1 `talk` spoke before settling.
2. An action whose outcome was fixed (at start or by a phase 2 stop) gets
   that result.
3. Otherwise the completion checks run:
   - Kernel actions: their completion checks (protocol §4.2), then their
     effects (§6).
   - `act`: the chosen rule is revalidated as a whole: every slot still
     holds its reserved items and meets its predicate, the target still
     exists and is within reach, and every condition holds (ADR 0009 D1 item
     6). No new rule is chosen. A failure is `settled/unmet` at completion,
     with `failed_check` naming the slot (target, item slot) or condition. It
     ends at this tick, having spent its work time (protocol §4.3).
   - If the checks pass and `success_per_mille < 1000`, the chance roll is
     drawn (§5.3). A failed roll is `settled/chance_failed`: inputs are kept or
     consumed as the rule's `on_chance_failed` says, and only the rule's
     `chance_failed_effects` apply (ADR 0009 Q3).
   - Otherwise `settled/applied`: inputs are consumed, then `effects` in
     declared order, then `outputs` in declared order (§11).
4. The result is final. A completed action is never failed afterwards
   (protocol §4.4).

Earlier members change the state that later members are checked against, so
two gathers of a tree's last fruit give one `applied` and one `unmet` at
completion, decided by the shuffle, as v1.

### 5.3 Chance rolls

A roll is derived from the run seed and its identity, never from a shared
sequence (ADR 0009 D1 item 8):

```text
record_k = canonical_json({"k":k, "rule_id":rule_id, "seed":seed,
                           "stream":"chance", "subject":subject, "tick":tick})
u_k      = first 4 bytes of SHA-256(record_k), big-endian unsigned
roll     = u_k mod 1000, for the first k = 0, 1, 2, ... with u_k < 4294967000
success  = roll < success_per_mille
```

- `seed` is `meta.seed`; `tick` is the completed tick `t+1` of the
  settlement; `subject` is the intent ID. `canonical_json` is the encoding of
  `interface-contract-v0.1.md` §6.3. 4294967000 is `2^32 − (2^32 mod 1000)`,
  so every roll value is equally likely.
- One actor's extra attempt never changes another event's roll, so runs that
  differ only in agent behaviour see the same luck for the same events.
- Rolls use no state and are not saved. `resolution_rng` is not consumed.
- World rules and process rules have no chance in this version (rule
  representation §5.8).

Test vectors (`k = 0` in each):

| seed | tick | rule_id | subject | `u_0` | roll |
|---|---|---|---|---|---|
| 20261108 | 10 | `make_stone_axe` | `ella:t000003:a` | 1756018325 | 325 |
| 20261108 | 11 | `make_stone_axe` | `ella:t000003:a` | 2878674493 | 493 |
| 20261108 | 10 | `make_stone_axe` | `mia:t000003:a` | 1782285225 | 225 |
| 1 | 1 | `a` | `b` | 1347268418 | 418 |

The first record is the bytes
`{"k":0,"rule_id":"make_stone_axe","seed":20261108,"stream":"chance","subject":"ella:t000003:a","tick":10}`.

### 5.4 Specificity ties

Settlement uses the specificity count of rule representation §5.3 and breaks
ties by the lowest `rule_id` (ADR 0009 Q2; owner, EN-D2). Content declares no
priorities. The validator lists equal-specificity overlaps as warnings, so
authors see them. ADR 0009's clay vectors:

| Rules present | Attempt | Result |
|---|---|---|
| A (clay + heat, near fire), B (clay + heat) | Next to a fire | A: specificity 2 + 1 beats B's 2 |
| A, B | Away from a fire | B: A's condition fails, B holds |
| A only | Away from a fire | `unmet` at start with A's `unmet` phenomena |
| Neither | Any | `unmatched` |

## 6. Kernel actions

The checks are the protocol's (§4.2). Effects and events:

| Action | Effect at success | Events |
|---|---|---|
| `move_to` | As v1 | `resident_moved` per step, then `action_succeeded` |
| `give` | All or nothing: the items move to the recipient's inventory, merging stacks; a non-stackable item's `owner_id` becomes the recipient | `item_transferred` (`via:"give"`), then `action_succeeded` |
| `pick_up` (entity) | The quantity moves from the ground, a container or a process into the inventory; owner unchanged | `item_transferred` (`via:"pick_up"`) |
| `pick_up` (tile) | The quantity is taken from the ground stacks of that archetype on the tile in ascending entity ID order | One `item_transferred` per stack touched |
| `drop` | The items move to the tile or into the container or process, merging stacks | `item_transferred` (`via:"drop"`) |
| `wait` | None | `action_succeeded` |
| `inspect` | None; the result carries the `InspectView` | `entity_inspected`, then `action_succeeded` |
| `contribute` | Work is added in phase 2 (§7.2); the action succeeds when its process completes (§7.3) | `process_progressed` (phase 2), `action_succeeded` |

- Inventory use is the sum of `quantity × slots_per_unit` over held
  top-level entities; the contents of a held container do not count. The
  capacity is a pack value (`inventory_slots`).
- A container's or process's use is the same sum over its contents, against
  its `capacity` (`CONTAINER_FULL`).
- A transfer that moves part of a stack gives the moving part a new engine
  ID; a part that merges into an equal stack takes that stack's ID and emits
  `stack_merged` (§11).
- Sight and paths read static terrain only, as v1. The v0.1 loader therefore
  refuses an archetype whose `footprint` has `blocks_movement` or `opaque`
  set to `true`; those fields are reserved for a later version.

## 7. Processes

### 7.1 What a process is

A process entity has `process` and `container` (rule representation §3.1,
§5.8). Its materials are its contents. Its progress is `work_done`, world
state saved in snapshots (ADR 0009 D2). It is created by a rule output, or
by `keep_progress` (rule representation §5.4).

### 7.2 Contributions

In phase 2, a running `contribute` adds one unit to `work_done` if, at that
moment:

- the process exists and is within the contributor's reach (protocol §4.2);
  and
- at least one of the process's rules has every slot filled by the contents
  and every condition other than `work_complete` holding (protocol §6.2).

Several contributors add one unit each. Work beyond the requirement is
allowed and kept. `process_progressed {process_id, work_done, contributor_id}`
is emitted for each unit.

### 7.3 Completion

In phase 4, at the process's place in the world-rule order (§8), among its
process rules whose slots are filled and whose conditions, `work_complete`
included, all hold, the most specific (then lowest `rule_id`) settles: its
inputs are consumed from the contents, then its effects and outputs. Every
`contribute` running on that process then ends with success at `t+1`.

- Outputs of a process rule have no `owner_id`: a world rule creates them,
  and several residents may have built them.
- A process whose materials are taken out keeps its `work_done`; work stops
  counting until the materials are back.

### 7.4 Abandoned processes

A process does not decay and is never removed by the engine in this version
(ADR 0009 Q4; owner, EN-D4). Content may still add a `when:` rule that acts on
`age` or `process.work_done`. A process with no contributor costs nothing per
tick, because work only counts in phase 2.

## 8. Phase 4: world rules

- Every active `every:` and `when:` rule runs, in `rule_id` byte order (ADR
  0009 D3). For each rule, its subjects are the entities that match its
  `subject` predicate when the rule's turn comes, in entity ID order.
  Entities created by this rule in this tick are not its subjects in this
  tick; those created by an earlier rule are.
- An `every:<n>` rule applies to a subject at completed tick `k ≥ 1` when
  `k mod n` equals the subject's phase offset for that rule (rule
  representation §3.5), so it never fires at tick 0. This is the v1 regrowth
  schedule (`world-rules-v0.1.md` §5.5).
- A subject for which the rule's slots are filled and conditions hold
  settles as `applied`; otherwise nothing happens and no event is emitted, as
  v1 emits no regrowth fact when a tree is full.
- Each application emits `world_rule_applied {rule_id, subject_id}` followed
  by the events of its effects.
- Phase 4 runs after completion resolution, so a gather that settles in phase
  3 sees the pre-regrowth stock, as in v1.
- Weather and seasons are not implemented. A later version adds them as
  global state that conditions may read (ADR 0009 D3); this version reserves
  the `world.globals` field of the snapshot, always empty.

## 9. Phase 5: physiology, awareness and death

### 9.1 Awareness during a tick

Physiology uses the awareness the resident had during phase 2 of this tick:
`asleep` while a sleep verb ran, including its final tick; `unconscious`
while fainted; otherwise `awake`. This keeps v1's rule that the final sleep
tick still counts as sleep (`world-rules-v0.1.md` §3).

### 9.2 Base physiology

For each living resident in ascending ID order, with pack values
(starter-content spec), each step clamped:

1. Hunger and thirst: satiety and hydration fall by the pack's awake or
   asleep rate. The rates are separate so the starter pack can make them
   slower asleep (protocol §6.3, owner PR-D6); the compatibility pack sets
   both to the v1 rates.
2. Stamina: an awake resident loses the awake rate. A resident that moved at
   least one tile this tick loses the movement extra cost once. Rule effects
   (rest, sleep, gather) were already applied in phases 2 and 3.
3. Deprivation: if satiety or hydration is at its minimum, health falls by
   the deprivation loss, once.
4. Otherwise, an asleep or unconscious resident whose satiety and hydration
   are at least the recovery minimums gains the sleep health recovery.
5. Mental fatigue, if enabled (§9.3).
6. One `needs_changed` event per resident with every change of this phase and
   the per-tick rule effects of phase 2 (§11).
7. Death: health at its minimum kills the resident: `resident_died`,
   `corpse_created`, then every held entity is placed on the tile in entity ID
   order, merging stacks, with `item_transferred` events (`via:"drop"`). The
   running action is stopped with `DEATH` in phase 6.

Steps 1–4 and 7 are the v1 rules with v1 values in the compatibility pack.
v1 applied gather's stamina cost in this phase; the compatibility rule
applies it at settlement instead (phase 3). Both are decrements clamped at the
minimum with no gain in between, so the result is the same.

### 9.3 Mental fatigue

Mental fatigue is a world need computed only from world quantities (ADR 0012
D3). It never reads token counts or anything agent-side. With pack
coefficients:

```text
awake:            v += awake_per_tick + per_utterance_heard × U + per_first_sighting × S
asleep/unconscious: v −= recovery_per_tick_asleep
```

- `U` and `S` count the `utterance_heard` and `entity_first_seen` reports in
  the packet delivered to this resident at the boundary that started this
  tick, saved in `fatigue_inputs`.
- `rest` counts as awake: it rests the body, not the mind. Whether a short
  sleep clears much is set by `recovery_per_tick_asleep` (ADR 0012 Q1).
- When `v` reaches the need's maximum, the resident **faints**: it becomes
  `unconscious` for `faint_ticks` (pack value), emits `resident_fainted`, and
  its running action stops with `FAINTED` in phase 6.
- `faint_ticks` must be at least K, the unconsciousness that ends a waking
  period (memory-formation spec), so that fainting always leads to
  consolidation as ADR 0012 D3 requires. The loader refuses a pack that breaks
  this.

### 9.4 Waking

- A sleeper wakes at its chosen duration: the sleep completes in phase 3 and
  the resident is awake from `t+1`, with `resident_woke {early:false}` and a
  `woke` report.
- A sleeper wakes early when one of its needs crosses a threshold marked
  `wakes` in this tick (protocol §6.3): its sleep stops with `WOKEN` in phase
  6, with `resident_woke {early:true}`. A sleep that completed in phase 3 of
  the same tick is not woken; completion wins, as v1.
- An unconscious resident wakes when its `faint_ticks` have passed, with
  `resident_woke {early:false}` and a `woke` report. Waking thresholds do not
  wake an unconscious resident (owner, EN-D5).

## 10. Phase 6: stops, waking and perception

### 10.1 When each hard stop is detected

| Stop | Detected | Ends at |
|---|---|---|
| `EXHAUSTED`, `PATH_BLOCKED` | Phase 2, when the action would progress (§4.2) | `t+1` |
| `DEATH` | Phase 6, after a death in phase 5 | `t+1` |
| `FAINTED` | Phase 6, after a faint in phase 5 | `t+1` |
| `TARGET_GONE` | Phase 6, for a running `contribute` whose process no longer exists or is out of reach | `t+1` |
| `WOKEN` | Phase 6, after a waking crossing in phase 5 | `t+1` |

- Only unfinished actions are stopped in phase 6; an action that completed in
  phase 3 keeps its result, even if the resident then dies (protocol §4.4).
- When several phase 6 stops apply to one action, the first in the protocol's
  list wins: `DEATH`, `FAINTED`, `TARGET_GONE`, `WOKEN`. A phase 2 stop has
  already ended its action, so a later death does not replace it, as v1 keeps
  an `EXHAUSTED` failure from earlier in the tick.
- A stop applies the rule's `on_interrupt` (rule representation §5.4) and
  emits `action_stopped`.
- A contribute whose process completed in phase 4 succeeded there; it is not
  stopped by `TARGET_GONE`.

### 10.2 Perception and packets

The rest of phase 6 is v1's (`world-rules-v0.1.md` §5.4 step 6) with the v2
shapes: sight and exploration, transient sightings and cues, receipts,
watched actions (protocol §5.4), heard utterances, feedback and reports
(protocol §5.3), then one `BoundaryDelivery` per living resident. Descriptors
are computed from apparent values and descriptor tables (rule representation
§2.2, §4.3).

## 11. Events of rule effects and the engine

These complete protocol §9.

| `EventType` | Payload | Emitted when |
|---|---|---|
| `entity_created` | `{entity_id, archetype_id, material_id, quantity, place, owner_id, rule_id:string|null, source:string|null}` | An output is created, or content is placed at tick 0 |
| `entity_consumed` | `{entity_id, archetype_id, quantity, rule_id}` | Inputs or a `consume` effect destroy matter |
| `matter_moved` | `{archetype_id, quantity, from, to, entity_id, rule_id}` | A `move` effect, such as fruit from a tree's store to an inventory; `entity_id` is the resulting stack |
| `entity_state_changed` | `{entity_id, field, before, after, rule_id}` | A `set_state` effect |
| `stack_merged` | `{from_id, into_id, quantity}` | A moving or created part merges into an equal stack |
| `needs_changed` | `{resident_id, changes:[{need_id, before, after}], causes:array<string>}` | A rule's completion need effect (`causes` is its rule ID), and once per resident in phase 5 for physiology and per-tick rule effects (`causes` holds `"physiology"` and those rule IDs, sorted) |
| `world_rule_applied` | `{rule_id, subject_id}` | Before the effect events of a world rule |
| `process_progressed` | `{process_id, work_done, contributor_id}` | A contribution adds work |

- `place` is `{kind:"tile", position}` or `{kind:"held", holder_id}`.
- **Order within one settlement:** inputs consumed by slot order, then
  `effects` in declared order, then outputs in declared order, then
  `act_settled` (protocol §9), then `attempt_unmatched` where it applies.
  Physical effects come before the result, as in v1.
- v1's `condition_updated`, `fruit_regrew` and the other v1 effect events are
  replaced by these (protocol §9); the equivalence projection reads state, not
  event names (protocol §11.3).

## 12. Limits

- A pack sets `max_entities_per_tile` and `max_entities_world` (ADR 0009 Q5;
  owner, EN-D6). Stacks count as one entity.
- A rule output that would break a limit does not happen: an `act` settles
  `unmet` at completion with the reserved `failed_check = "world_limit"`
  (rule representation §3.3), and a world rule's application is skipped.
  Kernel transfers and death drops are exempt: they move existing matter, and
  a death never fails.
- The loader refuses a pack whose placements already break a limit.
- Snapshot size grows with entities; the limits bound it. The storage plan
  for long runs is part of M13's time budget (plan §4).

## 13. Rule library changes and saves

- The run manifest and every snapshot record `vocabulary_hash`,
  `rule_library_hash` and `pack_ids` (ADR 0009 D5).
- A rule is added only in phase 1, with `rule_added {rule_id, content_hash,
  provenance}` (protocol §9). It can be chosen by actions that start in this
  tick or later. A running action keeps the rule chosen at its start.
- After an addition, the snapshot's `rule_library_hash` is the hash of the new
  library; the manifest's is the starting one, and the `rule_added` events
  link them. Replay applies the same additions at the same boundaries.
- Rules are never removed or changed during a run in this version.

## 14. Determinism and replay

- Every phase iterates in a stated order: actors by ID, the completion set
  by the v1 shuffle, world rules by `rule_id` then entity ID, physiology by
  resident ID, entity placement by entity ID.
- `resolution_rng` keeps its single v1 consumer, the completion shuffle.
  Chance rolls are derived (§5.3). Nothing else is random.
- No phase reads agent-side data, wall-clock time or model latency.
- Given the same snapshot, content, recorded turn submissions and rule
  additions, re-execution gives the same canonical snapshots and the same
  event bytes (`interface-contract-v0.1.md` §6.3), with no model call
  (protocol §12).

## 15. Acceptance tests

| ID | Test |
|---|---|
| EN-01 | Phase order: a gather of a tree's last fruit in the tick it regrows sees the pre-regrowth stock; physiology after completion; perception last; the compatibility fixtures of protocol WAP-23 pass |
| EN-02 | Start order: the two actor orders of protocol WAP-27 and WAP-29 give the stated results |
| EN-03 | Selection: the four clay vectors of §5.4; an equal-specificity tie goes to the lowest `rule_id` and the validator reports it |
| EN-04 | Unmet at start names the most specific candidate and its first failing condition, ends at `t + attempt_ticks` and shows that rule's `unmet` phenomena; unmatched emits `attempt_unmatched` with the descriptor |
| EN-05 | Completion: two gathers of a last fruit give `applied` and `unmet` (`failed_check = "stock"`) in shuffle order; a target moved out of reach during a long `act` settles `unmet` at completion naming `target`; a reserved fruit consumed by a world rule settles `unmet` naming its slot |
| EN-06 | Chance rolls: the four vectors of §5.3; a roll is unchanged when another actor adds an attempt in the same tick; `resolution_rng` is not consumed by rolls |
| EN-07 | `on_chance_failed`: `keep_inputs` keeps them, `consume_inputs` consumes them; `chance_failed_effects` wear the instrument |
| EN-08 | Completion set: in the compatibility pack the set and the shuffle draws equal v1's on the committed fixtures; a lone utterance joins the set with key `turn_id:u`; an attached utterance is emitted before its action settles |
| EN-09 | Processes: two contributors add two units per tick; work stops while a required material is removed and resumes when it returns; the rule settles in phase 4 when `work_done` reaches `work_ticks`; both contributors succeed at `t+1`; outputs have no owner |
| EN-10 | `TARGET_GONE`: a contribute whose process is taken apart stops at `t+1`; one whose process completes succeeds instead |
| EN-11 | World rules: `every:144` with offsets 0 and 24 fires at 144 and 24, 168, never at 0; a full tree emits nothing; an entity created by a rule is not its subject in the same tick |
| EN-12 | Physiology: the compatibility pack reproduces v1 need values exactly on the fixtures, including the final sleep tick, deprivation once, sleep health recovery and the gather cost moved to settlement |
| EN-13 | Asleep rates: with slower asleep rates, satiety and hydration fall less during sleep; the compatibility pack's equal rates leave v1 values unchanged |
| EN-14 | Mental fatigue: awake gain, per-utterance and per-sighting gains from the previous packet's counts, recovery asleep; reaching the maximum faints the resident, stops its action with `FAINTED` and makes it unconscious for `faint_ticks`; a pack with `faint_ticks < K` is refused |
| EN-15 | Waking: natural completion wins over a crossing in the same tick; an early crossing stops with `WOKEN`; an unconscious resident is not woken by a crossing |
| EN-16 | Hard stops: priority among phase 6 stops; a phase 2 `EXHAUSTED` is not replaced by a death later in the tick; `on_interrupt` applies to every stop |
| EN-17 | Kernel transfers: stack split and merge IDs; owner set by `give`, unchanged by `pick_up`; `CONTAINER_FULL`; container contents do not use inventory slots |
| EN-18 | Entity IDs: engine IDs follow `e:<tick>:<n>` in creation order and are identical on replay; content IDs and `corpse@` IDs are kept |
| EN-19 | Limits: an output beyond `max_entities_per_tile` settles `unmet` with `world_limit`; kernel transfers and death drops are exempt; a pack whose placements break a limit is refused |
| EN-20 | Library: a rule added in phase 1 is chosen by later starts, not by a running action; the snapshot hash changes and replay reproduces it; a snapshot with another hash is refused |
| EN-21 | Replay: two runs from one snapshot and the same recorded submissions give identical snapshots and event bytes, with no model call |
| EN-22 | No recipe code: the engine passes its tests with the synthetic test pack only, and a scan finds no archetype, material or rule ID of any real pack in engine code (ADR 0010 D4) |

## 16. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0009 Q1 Phase order | §3, owner EN-D1 |
| ADR 0009 Q2 Specificity or priorities | Count with `rule_id` ties, owner EN-D2 (§5.4) |
| ADR 0009 Q3 Inputs on a failed roll | Declared per rule (`on_chance_failed`), applied in §5.2 |
| ADR 0009 Q4 Abandoned processes | No decay, owner EN-D4 (§7.4) |
| ADR 0009 Q5 Limits | Per-tile and per-world entity limits, owner EN-D6 (§12); values in the starter-content spec |
| ADR 0012 Q1 Mental fatigue formula (mechanism) | §9.3; coefficients in the starter-content spec |
| ADR 0007 Q8 Process decay | §7.4 |
| Protocol §14: start order in tick phases | Phase 2 (§4) |
| Protocol §14: reserved items and world changes | Not protected; completion checks report them, owner EN-D3 (§4.1) |

## 17. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| EN-D1 | Where do world rules run in a tick? | After completion resolution, before physiology (phase 4), as v1 regrowth | Keeps the compatibility check exact and lets a gather see pre-regrowth stock |
| EN-D2 | Specificity count, or explicit priorities? | Count only; ties by lowest `rule_id`; the validator warns about equal overlaps | One rule fewer for content authors; the warning catches mistakes |
| EN-D3 | Are reserved items protected from world rules? | No. Decay or wear may change them; the completion check then settles the action `unmet` naming the slot | Simple and physical: fruit can rot in your hand |
| EN-D4 | Do abandoned processes decay? | No, in this version | Nothing in the starter content needs it; content can add a `when:` rule later |
| EN-D5 | Does hunger or thirst wake a fainted resident? | No; unconsciousness lasts `faint_ticks` | Fainting must last at least K to end a waking period (ADR 0012 D3) |
| EN-D6 | Limits on entities | Per tile and per world, set by the pack; a breaking output does not happen | Bounds snapshot size and per-tick work |
