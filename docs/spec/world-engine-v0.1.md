# Living Island — World Engine v0.1 (P3.5 v2 lane)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §17 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
> Rework 1 (2026-11-18) answers the Gate 2 world-track review
> ([review](../tasks/p3.5/P3.5-SP-01-review-world.md) B01–B03, B11–B13, N01,
> N03, N05) and the resident-track findings assigned here (B09, B13), and uses
> the protocol as amended by CR-010.
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
- Every other entity gets an engine ID when it is created. The world keeps a
  creation counter `n`, saved in snapshots, that starts at 0 and grows by one
  per created entity, in creation order. The ID is
  `e:` followed by the first 16 hex digits of
  `SHA-256(canonical_json({"k":k,"n":n,"seed":seed,"stream":"entity"}))`,
  with `k = 0`, or the next `k` while the result equals an ID issued before.
  For example, with seed 20261108 entity `n = 0` is `e:380d791373097437` and
  `n = 1` is `e:cfa85a63518a57ef`; the first record is the bytes
  `{"k":0,"n":0,"seed":20261108,"stream":"entity"}`, with no line feed.
- The ID says nothing about when an entity was made. A resident cannot tell
  a fruit's age from its ID, since the fruit has no age property (owner,
  CT-D7). `created_tick` stays world-internal.
- `n` is an integer below 2^53 (`interface-contract-v0.1.md` §6), so it never
  overflows within any run. Engine IDs contain `:`, which content IDs cannot,
  so they never collide. IDs are never reused.
- A split stack's moving part, a merged stack's survivor and every output get
  their IDs by these rules only, so replay reproduces them.

## 2. World state and snapshots

`WorldState` v2 keeps the v1 fields that still apply (`interface-contract-
v0.1.md` §2.1: tick, clock, hashes, map, residents' position and alive flag,
exploration footprints, receipts, dialogue sessions, `resolution_rng` state,
event cursor) and adds:

| Field | Content |
|---|---|
| `entities` | Every non-resident entity: `entity_id`, `archetype_id`, `material_id`, `quantity`, `created_tick`, `owner_id`, place, component state, own true values, apparent overrides and tells. Sorted by entity ID |
| `entity_counter` | The creation counter `n` (§1) |
| `needs` | Per resident, the stored value of each enabled need, sorted by need ID |
| `awareness` | Per resident: `awake`, `asleep` or `unconscious`, and for `unconscious` the tick it ends |
| `active_actions` | Per actor: the complete intent, `tick_started`, elapsed work, due tick or `null`, route state, the chosen `rule_id`, the resolved and reserved items by slot, and any pending outcome decided at start |
| `phase_offsets` | Per entity and `every:` rule, from content |
| `fatigue_inputs` | Per resident, the counts of the last delivered packet that mental fatigue reads (§9.3) |
| `library` | `vocabulary_hash`, `rule_library_hash`, `pack_ids`, the active rule IDs, and the canonical parsed form of every rule added during the run (§13) |
| `pending_deliveries` | Per resident, each `BoundaryDelivery` built but not yet acknowledged, verbatim, with its `delivery_id` (protocol §5.3) |
| `deferred_feedback` | Per actor, the `ActionFeedback` entries and `action_ended` reports of actions that ended after that actor's packet was delivered (an actor stop at its turn, protocol §4.4), waiting for the next packet |
| `proposals` | Per open or answered proposal: utterance ID, speaker, addressee, terms, dialogue session, and whether it has been answered (`accept` or `refuse`), so reply checks (protocol §7.1) give the same result after restore |
| `agreements` | Every accepted agreement: `agreement_id`, proposal and acceptance IDs, terms, tick (protocol §7.2) |

- The v1 fields `fruit_nodes`, `ground_fruit` and the canteen record are
  replaced by entities.
- A snapshot holds everything above (ADR 0009 D4). It is taken only at a
  completed boundary, after commit (phase 7), as in v1
  (`interface-contract-v0.1.md` §5). Packets and deferred feedback are stored
  as built and are delivered once after restore, never rebuilt from state, so
  a save before acknowledgement neither loses nor repeats them.
- The agent side's checkpoint (memory store, turn state, decision records) is
  the decision-loop and memory specs'; `sim` saves both checkpoints at the
  same boundary.
- Restore refuses a snapshot whose vocabulary or library hash differs from
  the loaded content plus the snapshot's added rules. There is no implicit
  migration (ADR 0009 D5).

## 3. The tick

A completed tick `t → t+1` runs these phases. Phases 2 and 3 keep the v1
order exactly, which the compatibility check depends on.

| Phase | Name | What happens |
|---|---|---|
| 1 | Boundary input | Packets for `t` are delivered and acknowledged; turns are collected (decision-loop spec). Rules approved for addition are added, each with `rule_added`. For each turn that chooses a new action while one runs, that action stops by the actor at `t` and its `on_interrupt` applies (protocol §4.4) |
| 2 | Action progress | Actors in ascending ID order (protocol §2): first utterance check, start of a new action, then one tick of progress (§4) |
| 3 | Completion resolution | The completion set is shuffled and settled (§5) |
| 4 | World rules | 4a: every `every:` and `when:` rule other than process rules, in `rule_id` order, then subject entity ID order; 4b: process rules, one process at a time in entity ID order, one chosen rule each (§7.3, §8) |
| 5 | Physiology and death | Living residents in ascending ID order (§9) |
| 6 | Stops, waking and perception | End-of-tick hard stops of unfinished actions (death, fainting, exhaustion, target gone, waking), visibility, exploration, receipts, watching, reports and packets for `t+1` (§10) |
| 7 | Commit | As v1 (`world-rules-v0.1.md` §5.4 step 7) |

- All events of phases 1–6 belong to tick `t+1`, as in v1.
- A turn's model calls happen between phase 7 of one tick and phase 1 of the
  next, and the world clock does not move while one is outstanding (protocol
  §2). Consolidation calls are not turn calls: they run while the world
  continues, and `sim` waits for them only at their commit boundary (memory
  formation §3.1).

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
  action (ADR 0007 D6), as (stack ID, units) pairs; reserving never splits a
  stack. A reserved item cannot be used by another action of the same actor;
  since only its holder can move a held item and an actor has one action, no
  other actor can take it through a kernel action. World rules are not
  blocked by reservations (owner, EN-D3): if a world rule consumes or changes
  a reserved item, the completion check finds it (§5.2).
- `action_started` is emitted for every start, with the duration known at
  start, or `null` for movement and `contribute`. For an `act` whose items
  were resolved, `act_items` follows it (§11), whatever the outcome.
- The resolved items are also the actor's `running_action.items` and
  `items_used`, and the `start` view of watchers (protocol §4.1, §5.1, §5.4,
  CR-010), built from the apparent values at this start.
- A sleep verb (`awareness_during = "asleep"`) makes the actor `asleep` from
  this tick, with `resident_fell_asleep`.

### 4.2 One tick of progress

In this order, for the actor's running action:

1. **Exhaustion at progress.** If the action is a movement, or an `act`
   whose rule has `exhaustion_stops = true`, and the actor's stamina is at its
   minimum, the action stops with `EXHAUSTED` now, without progress, and joins
   the completion set as a fixed outcome (§5.1). This is v1's check
   (`world/engine.py` `_progress`). Usually the end-of-tick check (§10.1) has
   already stopped such an action at the previous boundary.
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
  `PATH_BLOCKED`, as v1 holds pending failures. Stops found at the end of the
  tick (§10.1) never join a completion set, as v1's boundary stops do not.
- It also holds every **lone utterance**. An utterance is attached only to
  the action its own turn started, and only when that action finishes in this
  tick. Every other utterance is lone: one on a `continue` turn (even when the
  continued action happens to finish in this tick), and one whose new action
  runs longer.
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
   - `act`: the chosen rule is revalidated as a whole, in the check order of
     rule representation §5.2: target, instrument slots, input slots, the
     declared conditions, then `world_limit` (ADR 0009 D1 item 6). No new
     rule is chosen. A failure is `settled/unmet` at completion, with
     `failed_check` naming the first failing check. It ends at this tick,
     having spent its work time (protocol §4.3).
   - If the checks pass and `success_per_mille < 1000`, the chance roll is
     drawn (§5.3). A failed roll is `settled/chance_failed`: inputs are kept or
     consumed as the rule's `on_chance_failed` says, and only the rule's
     `chance_failed_effects` apply (ADR 0009 Q3, rule representation §5.6).
   - Otherwise `settled/applied`: inputs are consumed, then `effects` in
     declared order, then `outputs` in declared order (§11), with quantities
     captured before the first effect (rule representation §3.4.1).
   - Each branch is applied atomically: its placements were admitted by
     `world_limit` before anything was spent (§12), so a settlement either
     applies whole or not at all.
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
  `interface-contract-v0.1.md` §6.3, hashed without any line terminator.
  4294967000 is `2^32 − (2^32 mod 1000)`, so every roll value is equally
  likely. A roll equal to `success_per_mille` fails.
- One actor's extra attempt never changes another event's roll at the same
  full identity (seed, tick, rule, intent ID). Another action can change a
  later turn's intent ID, so comparisons across runs compare rolls of equal
  identities, not of "the same" attempt.
- Rolls use no state and are not saved. `resolution_rng` is not consumed.
- World rules and process rules have no chance in this version (rule
  representation §5.8).

Test vectors:

| seed | tick | rule_id | subject | Accepted word | roll |
|---|---|---|---|---|---|
| 20261108 | 10 | `make_stone_axe` | `ella:t000003:a` | `u_0` = 1756018325 | 325 |
| 20261108 | 11 | `make_stone_axe` | `ella:t000003:a` | `u_0` = 2878674493 | 493 |
| 20261108 | 10 | `make_stone_axe` | `mia:t000003:a` | `u_0` = 1782285225 | 225 |
| 1 | 1 | `a` | `b` | `u_0` = 1347268418 | 418 |
| 1 | 1 | `a` | `b:3158505` | `u_0` = 4294967265 rejected; `u_1` = 2458963507 | 507 |

The first record is the bytes
`{"k":0,"rule_id":"make_stone_axe","seed":20261108,"stream":"chance","subject":"ella:t000003:a","tick":10}`;
with a line feed appended the word would be 976841585, which is wrong. With
roll 325, a rule with `success_per_mille = 325` fails and one with 326
succeeds.

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
| `give` | All or nothing: the items move to the recipient's inventory, merging stacks; a non-stackable item's `owner_id` becomes the recipient | Transfer sequence (below, `via:"give"`), then `action_succeeded` |
| `pick_up` (entity) | The quantity moves from the ground, a container or a process into the inventory; owner unchanged | Transfer sequence (`via:"pick_up"`), then `action_succeeded` |
| `pick_up` (tile) | The quantity is taken from the ground stacks of that archetype on the tile in ascending entity ID order | One transfer sequence per stack touched, in that order, then `action_succeeded` |
| `drop` | The items move to the tile or into the container or process, merging stacks | Transfer sequence (`via:"drop"`), then `action_succeeded` |
| `wait` | None | `action_succeeded` |
| `inspect` | None; the result carries the `InspectView` | `entity_inspected`, then `action_succeeded` |
| `contribute` | Work is added in phase 2 (§7.2); the action succeeds when its process completes (§7.3) | `process_progressed` (phase 2), `action_succeeded` |

**Transfer sequence.** For each source stack moved, in the order above:

1. If only part of the stack moves, `stack_split {from_id, new_id, quantity}`
   allocates the moving part's new ID (§1).
2. `item_transferred` with the frozen payload (protocol §9): the moving
   entity's ID, archetype, quantity, `from`, `to`, `via`, `owner_before` and
   `owner_after`.
3. If the moving entity is equal to a stack already at the destination,
   `stack_merged {from_id, into_id, quantity}`; the destination stack keeps
   its ID.

So every unit that changes hands carries one transfer ID and both owner
values, and its lineage through splits and merges is in the log.

- Inventory use is the sum of `quantity × slots_per_unit` over held
  top-level entities; the contents of a held container do not count. The
  capacity is a pack value (`inventory_slots`).
- A container's or process's use is the same sum over its contents, against
  its `capacity` (`CONTAINER_FULL`).
- A transfer that moves part of a stack gives the moving part a new engine
  ID (`stack_split`); a part that merges into an equal stack takes that
  stack's ID (`stack_merged`, §11).
- A `drop` into a container or process that would place a container inside
  itself or one of its own contents is `INVALID_TARGET`: such an entity does
  not accept the item (protocol §4.2). With the validator's rule that portable
  containers never accept containers (rule representation §3.1), this case
  cannot arise in a valid pack; the check stays as a guard.
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
- at least one of the process's rules is eligible: its slots fill from the
  contents and its conditions other than `work_complete` hold (rule
  representation §5.8, protocol §6.2).

Several contributors add one unit each. Work beyond `work_required` is
allowed and kept. `process_progressed {process_id, work_done, contributor_id}`
is emitted for each unit.

### 7.3 Completion

In phase 4b, after all other world rules, the engine visits the process
entities in entity ID order. For each, on the state at that moment, it takes
the eligible process rules whose `work_complete` holds and settles only the
most specific one, then the lowest `rule_id` (rule representation §5.8). Its
slots are bound from the contents (rule representation §5.2), its inputs are
consumed, then its effects and outputs apply, as one atomic branch (§12). If
`world_limit` refuses it, nothing happens this tick and the process keeps its
work. Every `contribute` running on that process then ends with success at
`t+1`.

- The process's `progress` descriptor reads `work_done` against the
  archetype's `work_required`, the same total for every rule (rule
  representation §2.2).

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

- **4a.** Every active `every:` and `when:` rule other than a process rule
  runs, in `rule_id` byte order (ADR 0009 D3). For each rule, its subjects are
  the entities that match its `subject` predicate when the rule's turn comes,
  in entity ID order. Entities created by this rule in this tick are not its
  subjects in this tick; those created by an earlier rule are.
- **4b.** Process rules run after 4a, one chosen rule per process (§7.3).
- Each application is one atomic branch: slots are bound (rule
  representation §5.2), quantities captured, `world_limit` checked, then
  effects and outputs apply (§12).
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
   are both **strictly above** the recovery minimums, after steps 1–2, gains
   the sleep health recovery, as v1 (`world/physiology.py`
   `apply_metabolism`, OQ-020). For example, with both at exactly 2500 health
   stays; with both at 2501 it gains.
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
  consolidation as ADR 0012 D3 requires. The world does not know K (protocol
  §6.3), so this is checked when `sim` composes a run from a pack and an
  agent configuration, which refuses the pair (decision-loop spec §10.5); the
  world's content loader does not read K.

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

### 9.5 Boundaries of sleep and fainting

The agent side counts waking periods from these world boundaries (memory
formation §2):

| Transition | World boundary | What the packet shows |
|---|---|---|
| A chosen sleep starts | The turn at boundary `t` chooses it; it starts in phase 2 of tick `t → t+1`, so that tick is already asleep (§9.1); `resident_fell_asleep` belongs to tick `t+1` | The packet for `t+1` is the first with `awareness = "asleep"` |
| A sleep fails at start | No sleep starts (for example an unmet sleep rule) | `awareness` stays `awake` |
| A faint | Mental fatigue reaches its maximum in phase 5 of tick `t → t+1`; the resident is unconscious from `t+1` for `faint_ticks` ticks | The packet for `t+1` is the first with `awareness = "unconscious"` |
| Waking | At the boundary where the sleep completes, is woken, or `faint_ticks` have passed | The packet for that boundary has `awareness = "awake"` and a `woke` report |
| Death while asleep or unconscious | The resident dies in phase 5; no further packet | — |

A chosen sleep of `d` ticks started at boundary `t` ends at boundary `t + d`.

### 9.6 Hearing and sight while not awake

- A resident hears an utterance emitted in tick `t → t+1` only if its
  awareness during that tick (§9.1) was `awake`. So speech emitted in the
  final tick of a sleep is not heard, on natural and on early waking, even
  when the sleep completes before the utterance in the shuffle, as v1
  (`world-rules-v0.1.md` §5.4 step 6: "excluding … residents asleep at
  emission").
- Sight while asleep follows the pack's `sight_while_asleep` (protocol §5.1,
  CR-010): in the compatibility pack phase 6 builds a sleeper's sight,
  receipts, footprint and `entity_first_seen` reports as for an awake
  resident; in the starter pack it builds none. Hearing and observed actions
  stay off in both. An unconscious resident never perceives.

## 10. Phase 6: stops, waking and perception

### 10.1 When each hard stop is detected

| Stop | Detected | Ends at | In a completion set |
|---|---|---|---|
| `EXHAUSTED` at progress, `PATH_BLOCKED` | Phase 2, when the action would progress (§4.2) | `t+1` | Yes, as v1 pending failures |
| `DEATH` | Phase 6, after a death in phase 5 | `t+1` | No |
| `FAINTED` | Phase 6, after a faint in phase 5 | `t+1` | No |
| `EXHAUSTED` at the end of the tick | Phase 6: an unfinished movement, or an `act` whose rule has `exhaustion_stops = true`, whose actor's stamina is at its minimum after phase 5, as v1 (`world/engine.py` `_resolve_boundary`) | `t+1` | No |
| `TARGET_GONE` | Phase 6, for a running `contribute` whose process no longer exists or is out of reach | `t+1` | No |
| `WOKEN` | Phase 6, after a waking crossing in phase 5 | `t+1` | No |

- Only unfinished actions are stopped in phase 6; an action that completed in
  phase 3 keeps its result, even if the resident then dies (protocol §4.4).
- When several phase 6 stops apply to one action, the first in the protocol's
  list wins: `DEATH`, `FAINTED`, `EXHAUSTED`, `TARGET_GONE`, `WOKEN`. A phase 2
  stop has already ended its action, so a later death does not replace it, as
  v1 keeps a failure from earlier in the tick (protocol §4.4, CR-010).
- Example, as v1: Ella moves with stamina 1 and Ryan waits. In tick 0 → 1
  Ella moves, physiology takes her stamina to 0, and her move stops
  `EXHAUSTED` at boundary 1. Ryan's wait is the only completion of tick 1 → 2,
  so the shuffle draws nothing for it. Detecting her exhaustion only in
  phase 2 of the next tick would add a second member and one draw.
- A stop applies the rule's `on_interrupt` (rule representation §5.4) and
  emits `action_stopped`.
- A contribute whose process completed in phase 4 succeeded there; it is not
  stopped by `TARGET_GONE`.

### 10.2 Perception and packets

The rest of phase 6 is v1's (`world-rules-v0.1.md` §5.4 step 6) with the v2
shapes: sight and exploration, transient sightings and cues, receipts,
watched actions (protocol §5.4), heard utterances (§9.6), feedback and
reports (protocol §5.3), then one `BoundaryDelivery` per living resident.
Descriptors are computed from apparent values and descriptor tables (rule
representation §2.2, §4.3).

- **Watched actions** (protocol §5.4, CR-010). For each action that started,
  stopped or settled in this tick and each watcher whose sight at this
  boundary includes the actor, the engine builds one `ObservedAction` per
  phase. `visible_items` uses the apparent views at this boundary: at `start`
  the resolved items (the same list as `act_items`, §11), at `stop` those that
  still exist, at `settle` those that still exist after settlement plus the
  outputs placed in the actor's inventory or on its tile. An item away from the
  actor is shown only if it is in the watcher's own perception. The actor's
  own `items_used` is that start list.
- A packet built for a boundary is stored in `pending_deliveries` until it is
  acknowledged (§2).

## 11. Events of rule effects and the engine

These complete protocol §9.

| `EventType` | Payload | Emitted when |
|---|---|---|
| `entity_created` | `{entity_id, archetype_id, material_id, quantity, place, owner_id, rule_id:string|null, source:string|null, made_from:array<{entity_id, quantity}>, process_id:string|null}` | An output is created, or content is placed at tick 0. `made_from` lists the stacks the settlement consumed (inputs and `consume` effects), in event order; `process_id` names the process a process rule ran on |
| `entity_consumed` | `{entity_id, archetype_id, quantity, rule_id}` | Inputs or a `consume` effect destroy matter |
| `matter_moved` | `{archetype_id, quantity, from:Place, to:Place, entity_id:string|null, rule_id}` | A `move` effect, such as fruit from a tree's store to an inventory; `entity_id` is the resulting stack, `null` when the destination is a store |
| `store_count_changed` | `{entity_id, archetype_id, before, after, rule_id, source:string|null}` | A store's count changes: a sourced refill (`source` set) or a `move` out of or into it |
| `entity_state_changed` | `{entity_id, field, before, after, rule_id}` | A `set_state` effect |
| `stack_split` | `{from_id, new_id, quantity}` | Part of a stack moves and gets a new ID (§1, §6) |
| `stack_merged` | `{from_id, into_id, quantity}` | A moving or created part merges into an equal stack |
| `needs_changed` | `{resident_id, changes:[{need_id, before, after}], causes:array<string>}` | A rule's completion need effect (`causes` is its rule ID), and once per resident in phase 5 for physiology and per-tick rule effects (`causes` holds `"physiology"` and those rule IDs, sorted) |
| `act_items` | `{rule_id:string|null, target:{kind, id:string|null, position:Coord|null}|null, slots:array<{slot:string|null, role, parts:array<{entity_id, archetype_id, material_id, quantity}>}>}` | Right after `action_started` of every `act` whose items were resolved, whatever the outcome: the target and the resolved items with their true archetype and material, by slot in slot order when a rule was chosen at start (`slot` null and submitted order otherwise). Objective analysis data, never resident-facing (evaluation spec §3.4) |
| `condition_witness` | `{intent_id, condition_id, entity_id}` | At an `applied` settlement, for each `entity_near` condition of the rule: the matching entity nearest the reference tile (then lowest ID), for example the shelter a sleeper used |
| `world_rule_applied` | `{rule_id, subject_id}` | Before the effect events of a world rule |
| `process_progressed` | `{process_id, work_done, contributor_id}` | A contribution adds work |

- `Place` is `{kind:"tile", position}`, `{kind:"held", holder_id}` (a
  resident's inventory), `{kind:"in", container_id}` (a container's or
  process's contents) or `{kind:"store", entity_id}`.
- A sourced output into a store emits `store_count_changed`, not
  `entity_created`, because store units are not entities (rule
  representation §3.1).
- **Order within one settlement:** inputs consumed by slot order, then
  `effects` in declared order, then outputs in declared order, then
  `act_settled` (protocol §9), then `attempt_unmatched` where it applies.
  Physical effects come before the result, as in v1.
- v1's `condition_updated`, `fruit_regrew` and the other v1 effect events are
  replaced by these (protocol §9); the equivalence projection reads state, not
  event names (protocol §11.3).

## 12. Limits

A pack sets `max_entity_units_world` and `max_entities_per_tile` (ADR 0009
Q5; owner, EN-D6).

- **The counted quantity.** The world count is the sum over all non-resident
  entities, wherever they are (tiles, inventories, contents), of
  `max(1, quantity)`. Store units are not entities and do not count. Every
  entity counts at least 1, so the number of entities never exceeds the
  count.
- **Who can change it.** Only rule effects (`create`, `consume`, `move` out of
  or into a store, a process created by `keep_progress`) and corpses change
  the count. A kernel transfer, a split, a merge or a death drop moves
  existing units and leaves it unchanged, so these are never refused and the
  world bound still holds.
- **The world bound is hard.** A rule branch is admitted only if
  `count + net ≤ max_entity_units_world − living_residents`, where `net` is
  the branch's change after merges; the reserve of one per living resident
  keeps room for its corpse. Then the count never exceeds the maximum.
- **The tile bound applies to rule placements.** A rule branch that would
  leave a tile with more than `max_entities_per_tile` entities after merges
  is not admitted. Kernel drops and death drops are not refused (the protocol
  has no such failure code); they can exceed the tile bound, which therefore
  limits per-tick rule work, not snapshot size.
- **Preflight.** `world_limit` (rule representation §3.3) is evaluated on the
  whole branch before anything is spent, consumed, worn or changed. A refused
  `act` settles `unmet` with `failed_check = "world_limit"`; a refused world
  or process rule does nothing this tick; a refused `partial` or
  `keep_progress` falls back to `lose` (rule representation §5.4).
- The loader refuses a pack whose placements already break a bound. The
  compatibility pack sets bounds that no v1 configuration can reach; reaching
  one there is a defect (starter-content spec §4.5).
- Snapshot size is bounded by the world bound. The storage plan for long runs
  is part of M13's time budget (plan §4).

## 13. Rule library changes and saves

- The run manifest and every snapshot record `vocabulary_hash`,
  `rule_library_hash` and `pack_ids` (ADR 0009 D5).
- A rule is added only in phase 1, with `rule_added {rule_id, content_hash,
  provenance}` (protocol §9). It can be chosen by actions that start in this
  tick or later. A running action keeps the rule chosen at its start.
- After an addition, the snapshot's `rule_library_hash` is the hash of the new
  library; the manifest's is the starting one, and the `rule_added` events
  link them.
- **Rule content for replay.** Every added rule is written, before its
  `rule_added` event, to the run's content-addressed store as
  `rules/<content_hash>.json`, its canonical parsed form (rule representation
  §1). Replay reads each `rule_added` event's rule from that store and checks
  the hash; the snapshot also holds the added rules (§2), so restore needs
  only the snapshot and the loaded packs. A missing or mismatching rule file
  refuses the replay.
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
- Restore after a save before acknowledgement delivers the stored packet and
  deferred feedback exactly once (§2), and the next packet repeats none of it.

## 15. Acceptance tests

| ID | Test |
|---|---|
| EN-01 | Phase order: a gather of a tree's last fruit in the tick it regrows sees the pre-regrowth stock; physiology after completion; perception last; the compatibility fixtures of protocol WAP-23 pass |
| EN-02 | Start order: the two actor orders of protocol WAP-27 and WAP-29 give the stated results |
| EN-03 | Selection: the four clay vectors of §5.4; an equal-specificity tie goes to the lowest `rule_id` and the validator reports it |
| EN-04 | Unmet at start names the most specific candidate and its first failing condition, ends at `t + attempt_ticks` and shows that rule's `unmet` phenomena; unmatched emits `attempt_unmatched` with the descriptor |
| EN-05 | Completion: two gathers of a last fruit give `applied` and `unmet` (`failed_check = "stock"`) in shuffle order; a target moved out of reach during a long `act` settles `unmet` at completion naming `target`; a reserved fruit consumed by a world rule settles `unmet` naming its slot |
| EN-06 | Chance rolls: the five vectors of §5.3, including the rejected first word; a record with a line feed appended gives a different word; a roll equal to `success_per_mille` fails and one below succeeds; a roll is unchanged when another actor adds an attempt in the same tick, compared at equal identities; `resolution_rng` is not consumed by rolls |
| EN-07 | `on_chance_failed`: `keep_inputs` keeps them, `consume_inputs` consumes them; `chance_failed_effects` wear the instrument |
| EN-08 | Completion set: in the compatibility pack the set and the shuffle draws equal v1's on the committed fixtures; a lone utterance joins the set with key `turn_id:u`; an attached utterance is emitted before its action settles; an utterance on a `continue` turn whose running action finishes in that tick is lone, so the set has two members, not one |
| EN-09 | Processes: two contributors add two units per tick; work stops while a required material is removed and resumes when it returns; the rule settles in phase 4b when `work_done` reaches `work_required`; both contributors succeed at `t+1`; outputs have no owner and name the process in `process_id`; two processes of one archetype completing in one tick with different contributors settle in entity ID order, each output linked to its own process |
| EN-10 | `TARGET_GONE`: a contribute whose process is taken apart stops at `t+1`; one whose process completes succeeds instead |
| EN-11 | World rules: `every:144` with offsets 0 and 24 fires at 144 and 24, 168, never at 0; a full tree emits nothing; an entity created by a rule is not its subject in the same tick |
| EN-12 | Physiology: the compatibility pack reproduces v1 need values exactly on the fixtures, including the final sleep tick, deprivation once, sleep health recovery and the gather cost moved to settlement. Recovery boundaries: a sleeping tick from health 9000, satiety 2525 and hydration 2600 ends with both at 2500 and health 9000; with either alone at 2500 health also stays; with both at 2501 health is 9015; a deprived sleeper loses health and does not recover; a final sleep tick still recovers |
| EN-13 | Asleep rates: with slower asleep rates, satiety and hydration fall less during sleep; the compatibility pack's equal rates leave v1 values unchanged |
| EN-14 | Mental fatigue: awake gain, per-utterance and per-sighting gains from the previous packet's counts, recovery asleep; reaching the maximum faints the resident, stops its action with `FAINTED` and makes it unconscious for `faint_ticks`; the world loader accepts a pack without reading K, and `sim` refuses composing a pack with `faint_ticks = 35` and an agent configuration with K = 36 |
| EN-15 | Waking: natural completion wins over a crossing in the same tick; an early crossing stops with `WOKEN`; an unconscious resident is not woken by a crossing |
| EN-16 | Hard stops: priority among phase 6 stops, including `DEATH` over end-of-tick `EXHAUSTED` at one check; a phase 2 `PATH_BLOCKED` or `EXHAUSTED` is not replaced by a death later in the tick; `on_interrupt` applies to every stop |
| EN-17 | Kernel transfers: stack split and merge IDs with `stack_split` and `stack_merged`; owner set by `give`, unchanged by `pick_up`; `CONTAINER_FULL`; container contents do not use inventory slots. A tile pickup taking from two stacks emits, per stack in ascending ID, split, `item_transferred` with both owner values, merge, and then one `action_succeeded`; `drop` and `pick_up` end with `action_succeeded` |
| EN-18 | Entity IDs: the two vectors of §1; IDs are identical on replay; an untouched stack observed hundreds of ticks later shows no creation tick; content IDs and `corpse@` IDs are kept; a collision moves to the next `k` |
| EN-19 | Limits (§12): at a count one below the bound minus the living residents, a rule creating one unit is admitted and one creating two is refused with `world_limit`, nothing spent; splits, merges, kernel transfers and death drops leave the count unchanged and are never refused; a death at the bound still creates its corpse; a refused `keep_progress` falls back to `lose`; a pack whose placements break a bound is refused |
| EN-20 | Library: a rule added in phase 1 is chosen by later starts, not by a running action; the snapshot hash changes and replay reproduces it from `rules/<content_hash>.json`; a missing or altered rule file refuses the replay; a snapshot with another hash is refused |
| EN-21 | Replay: two runs from one snapshot and the same recorded submissions give identical snapshots and event bytes, with no model call. Saved after phase 7 with an unacknowledged packet and deferred stop feedback, then restored, the packet and the old stop are delivered once; saved before a first reply to a proposal, the reply is accepted after restore, and after a refusal a second reply is refused; a store refill and a rule addition replay exactly |
| EN-23 | End-of-tick exhaustion (§10.1), against v1 with the fixture's seed: Ella moves with stamina 1 and Ryan waits; Ella stops `EXHAUSTED` at boundary 1, Ryan's wait is the sole completion of the next tick and `resolution_rng` stays at the state v1 shows (one completion, no draw); a gather whose stamina reaches zero after physiology stops the same way |
| EN-24 | Sleep and faint boundaries (§9.5): a sleep chosen at 100 for 36 ticks first shows `asleep` in the packet for 101 and wakes at 136; a faint in tick 100 → 101 first shows `unconscious` at 101 and wakes at `101 + faint_ticks`; an unmet sleep never shows `asleep` |
| EN-25 | Hearing while not awake (§9.6): speech emitted in the final tick of a sleep is not heard, whether the sleep completes before or after the utterance in the shuffle and on early waking; compatibility sight while asleep matches protocol WAP-32 |
| EN-26 | Watched items (§10.2): `act_items`, the actor's `items_used` and a watcher's `start` view list the same items; the `settle` view shows outputs in the actor's inventory and no consumed input |
| EN-27 | Analysis events (§11): an applied `act` emits `entity_created` with `made_from` naming its consumed stacks; a sourced store refill emits `store_count_changed` with the source; a sleep near a shelter emits `condition_witness` naming that shelter, and with two shelters in range the nearer one |
| EN-28 | Atomic branches: a settlement whose second output the limits refuse creates nothing, consumes nothing and applies no need effect of `completion` timing |
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
| EN-D6 | Limits on entities | Per tile and per world, set by the pack; a breaking output does not happen. Rework 1 makes the world bound hard by counting units in entities, which only rules and corpses change (§12) | Bounds snapshot size and per-tick work |
