# Living Island — World–Agent Protocol v0.1 (P3.5 v2 lane)

> **Draft (2026-11-17), task P3.5-PR-02. Not frozen.** The owner answered the
> decision sheet on 2026-11-17 (§15). Revised after the first Gate 2 review
> ([P3.5-PR-02 review](../tasks/p3.5/P3.5-PR-02-review.md), B-01–B-06,
> N-01–N-02) and again after its round 2 (§7 of that report, R2-B-01–R2-B-03,
> R2-N-01–R2-N-02); the second revision is not yet reviewed.
>
> Implements [ADR 0007](../adr/0007-world-agent-protocol.md) under CR-009
> option A ([open questions](open-questions.md)). When frozen, it supersedes for
> new work in the v2 lane: the action, perception and feedback parts of
> `interface-contract-v0.1.md` and `agent-interface-v0.1.md`, and
> `world-rules-v0.1.md` §4.2–§4.4. Those files stay unchanged as the v1 record,
> and stay in force for v1 runs.

**Conventions.** As in `interface-contract-v0.1.md`: field lists are
normative field descriptions, not code; types are `string`, `integer`,
`boolean`, `null`, `array<T>` and `object{...}`; `?` marks an optional field;
physical values are integers. "v1" is the frozen protocol; "v2" is this one.
"Must" and "never" are normative.

## 0. Scope and ownership

### 0.1 Covered here

- The data that crosses between `world` and `agents` through `sim`: turn
  submissions, intents, results and feedback, perception and boundary
  delivery.
- Speech, dialogue sessions and agreements, as far as the world records them.
- Hard stops, and the world reports from which the harness derives
  notifications.
- The objective events that protocol-level actions produce (§9).
- How the model-facing schema is generated (§10).
- Migration from v1 (§11).

### 0.2 Owned elsewhere

| Subject | Successor spec |
|---|---|
| Rule format, vocabularies (verbs, properties, need IDs, components, effects, phenomena), validator, conservation | `rule-representation-v0.1.md` |
| Settlement order, tick phases, chance rolls, processes, world dynamics, entity ID format, artifacts in snapshots | `world-engine-v0.1.md` |
| Content packs and values (durations, radii, capacities, the compatibility pack) | `starter-content-v0.1.md` |
| Turn scheduling, notification classes, mute lists, working context, model requests | `decision-loop-v0.1.md` |
| Memory records written from agreements and observations | `memory-model-v0.1.md`, `memory-formation-v0.1.md` |
| Metrics on agreements, watching and learning paths | `evaluation-v0.1.md` |

This spec names vocabulary terms by kind only (`VerbId`, `PropertyId`,
`NeedId`, `PhenomenonId`, `ArchetypeId`, `MaterialId`, `DescriptorValue`). Their members are
defined in the rule-representation spec and content packs. The protocol never
contains a rule, a recipe or a content value.

### 0.3 Roles

| Party | Does | Never |
|---|---|---|
| `world` | Builds `Perception`, validates intents, settles actions, emits objective events and world reports | Reads agent-side data; decides that a resident should stop, replan or sleep |
| `sim` | Delivers boundary packets, decides which residents get a turn (decision-loop spec), passes submissions to the world, records fallback | Changes world state itself |
| `agents` | Assembles context, calls the model, validates shapes, returns one `TurnSubmission` | Sees `WorldState`; changes world state |

The import boundaries of AGENTS.md are unchanged. The module that holds the v2
protocol models takes the place of `world/protocol.py` in the import-linter
contracts: `agents` and `memory` import only that module from `world`. The
module path is set by the M12 task cards.

## 1. Versions and identity

- Every v2 DTO carries `schema_version: "wap/0.1"`. A reader refuses any other
  value. There is no implicit migration from v1 shapes (ADR 0007 D8).
- A run manifest pins the protocol version, the vocabulary hash and the rule
  library hash (ADR 0009 D5).
- IDs are strings; ticks, counts, coordinates and quantities are integers.
- Entity IDs are opaque strings allocated by the world, unique within a run and
  never reused. Their format is a world-engine spec choice. Resident IDs come
  from configuration.
- `turn_id = "<actor_id>:t<turn ordinal, at least 6 digits>"`. The ordinal
  counts this actor's turns from zero and advances exactly once per committed
  turn, including a fallback turn or a replayed one.
- `intent_id = "<turn_id>:a"`. A turn has at most one intent. The `plan_id` of
  ADR 0007 D2 becomes `turn_id`, because v2 has no plans (ADR 0007 D7).
- `utterance_id` is the event ID of its `utterance_spoken` event, as in v1.
  `agreement_id` is the event ID of its `agreement_accepted` event.

## 2. The turn cycle

1. The world completes tick `t` and builds one `BoundaryDelivery` (§5.3) per
   living resident.
2. `sim` delivers every packet. The harness decides which residents get a turn
   at boundary `t` (decision-loop spec). A resident gets a turn when it wakes,
   when its action ends, and when the harness turns a world report into a
   notification. An unconscious resident gets no turn.
3. Each resident with a turn returns one `TurnSubmission` (§3.1).
4. `sim` passes the submissions to the world in ascending actor ID order. The
   world validates them and settles tick `t → t+1`.

- The world clock stays frozen while a turn's model call is outstanding.
  Consolidation is the exception (ADR 0013 D3, ADR 0012 D2).
- A resident with a running action and no turn keeps that action.
- A resident whose action ended always gets a turn, so a living, conscious
  resident is never idle without one. At tick zero every living resident gets
  a turn after its first packet is delivered.

## 3. Turns and intents

### 3.1 `TurnSubmission`

```text
TurnSubmission {
  schema_version:string, turn_id:string, actor_id:string,
  observed_tick:integer,                   // the boundary this turn answers
  action:{kind:"continue"} | {kind:"intent",intent:Intent},
  utterance:Utterance|null
}
```

- Exactly one action choice per turn (ADR 0007 D7). `continue` is valid only
  while the actor has a running action (`Perception.running_action`).
- `TurnSubmission` holds the world-facing part of a turn only. Intention
  updates, mute lists, memory citations and context data stay in `agents` and
  never reach the world (ADR 0013 D2, D3, D10).
- The fallback policy returns the same shape. The world cannot tell which
  policy produced a submission; `sim` records fallback separately (§9).
- **Identity is assigned, never chosen.** The harness fills `schema_version`,
  `turn_id`, `actor_id` and `observed_tick`, and the nested `intent_id`,
  `turn_id` and `actor_id`, from the outstanding turn. A model never supplies
  them: its output carries only the action choice, the utterance and the
  agent-side fields of the decision-loop spec.
- **Binding check.** Before the world port receives a submission, `sim`
  checks that the actor has an outstanding turn at `observed_tick`, which is
  the current boundary; that `turn_id` names that turn's ordinal; that the outer
  and nested `actor_id` and `turn_id` agree; and that
  `intent_id = turn_id + ":a"`. A mismatch is `INVALID_TURN` (§3.4): no world
  effect, and the ordinal does not advance.
- **Exactly once.** The ordinal advances once, when a submission for the turn
  is committed, whether it came from the model, a retry or the fallback
  policy. A second submission for a committed turn, or one for an earlier
  boundary, is refused with no effect and recorded. How the harness recovers
  from `INVALID_TURN` (retry or fallback) is the decision-loop spec.

### 3.2 `Intent`

```text
Intent {
  intent_id:string, turn_id:string, actor_id:string,
  action:"move_to"|"give"|"pick_up"|"drop"|"wait"|"inspect"|"contribute"|"act",
  verb:VerbId|null,                        // required for act, null otherwise
  target:Target|null,
  instruments:array<ItemChoice>,           // act only; used, not consumed
  inputs:array<{item:ItemChoice,quantity:integer}>, // act only; consumed
  params:object{},                         // closed shape per action or verb
  reason:string|null                       // debugging only; never affects settlement
}
Target     = {kind:"tile",position:Coord} | {kind:"entity",id:string} | {kind:"resident",id:string}
ItemChoice = {kind:"item",id:string}                   // one named instance or stack
           | {kind:"held",archetype_id:ArchetypeId}    // any held items of this kind
```

Kernel action shapes:

| `action` | `target` | `params` | Meaning |
|---|---|---|---|
| `move_to` | `tile` | `{}` | Walk to a tile, as v1 |
| `give` | `resident` | `{item:ItemChoice,quantity:integer}` | Move held items to a neighbouring resident |
| `pick_up` | `entity` (an item on the ground, in a container or in a process entity) | `{quantity:integer}` | Take that item into the inventory |
| `pick_up` | `tile` | `{archetype_id:ArchetypeId,quantity:integer}` | Take items of a kind from the ground of that tile, as v1 |
| `drop` | `tile` or `entity` (a container or process entity) | `{item:ItemChoice,quantity:integer}` | Put held items down or into something |
| `wait` | `null` | `{}` | Pass `wait_ticks` (content value) |
| `inspect` | `entity` | `{}` | Reveal `on_inspect` properties (§5.2) |
| `contribute` | `entity` (a process entity) | `{}` | Add work each tick until the process completes or the actor stops |
| `act` | per verb: the target kinds the verb declares | the verb's closed parameter shape | Resolved against the rule library (§4.3) |

- `act` with a `verb` is the only way to use a rule. `gather`, `eat`, `drink`,
  `fill`, `rest` and `sleep` are verbs (ADR 0007 D2), not kernel actions.
- `sleep` takes a required `params: {duration_ticks:integer}` from 6 to 54
  ticks (1 to 9 hours; owner, PR-D4). Both packs use these bounds; v1
  `sleep_ticks` = 48 lies inside them. The world wakes the sleeper at that time
  unless something wakes it earlier (§6.3).
- `instruments` and `inputs` are empty for kernel actions. For `act`, an item
  appears at most once across instruments and inputs.
- Quantities are positive integers.
- **Item choice.** `{kind:"held",archetype_id}` names the actor's own held
  items of that kind, so it needs no receipt. The world resolves all choices
  of an intent at the start check, in two passes:
  1. Named choices (`{kind:"item"}`) are reserved first: instruments in listed
     order, then inputs in listed order. A named item that is not held is
     `NO_ITEM`.
  2. Then by-kind choices: instruments in listed order (one instance each),
     then inputs in listed order. Each takes the held stacks of its archetype
     in ascending entity ID order, skipping anything already reserved.
  - Not enough unreserved held items is `NO_ITEM`, a world-side shortage. The
    same item named twice is a shape error (`INVALID_TURN`, §3.4).
  - Resolved items are then fixed for the action; a stack larger than needed
    is split (§5.1). Replay resolves the same way, because it reads the same
    world state.
  - The single `params.item` of `give` and `drop` resolves by the same rules.
- `pick_up` by tile takes from the ground stacks of that archetype on that
  tile, in ascending entity ID order, at completion. It is a place-and-kind
  request, not a reserved item: whatever stacks of that kind lie there at
  completion count, as in v1. It needs a receipt for an item of that kind at
  that tile, as v1 (`interface-contract-v0.1.md` §2.1).

### 3.3 References and exposure

- A resident may reference only entities it holds or has been exposed to,
  checked against backend-private exposure receipts, as v1 does
  (`interface-contract-v0.1.md` §2.1). A missing receipt is `INVALID_TARGET`,
  checked before any live lookup.
- `instruments` and `inputs` must be held by the actor.
- A receipt authorizes a reference only; reach, holding and existence are
  still checked.
- The world never lists rules and never tracks which rules a resident knows.
  Receipts record what was shown to a resident, not what it concluded. Known
  recipes come only from the resident's own memory, assembled by `agents`
  (ADR 0007 D3).
- A resident starts knowing its drives (it feels hunger and thirst) and the
  verbs it may try, never which items work (owner, PR-D1). The decision-loop
  spec writes this into the system instructions.

### 3.4 Validation layers

1. **Agents (shape).** The binding check (§3.1); known action; target kind
   allowed; `params` match the closed shape, including `duration_ticks` within
   its bounds; `verb` is in the vocabulary and present only for `act`;
   quantities positive; no item listed twice; `continue` only with a running
   action; utterance shape, including the term kind, its required fields and
   positive quantities and work (§7). A failure is `INVALID_TURN`, an
   agent-side error recorded in the call log. It never reaches the world (as v1
   `INVALID_PLAN`, CR-001).
   - A shape failure anywhere in a submission, its utterance included, voids
     the whole turn: neither the action nor the utterance reaches the world.
2. **World (state).** Kernel preconditions (§4.2), generic `act`
   preconditions (§4.3), then rule settlement for `act`. The utterance is
   validated on its own (§7.1): a world-level utterance failure voids only the
   utterance, and the action goes on.

## 4. Results and feedback

### 4.1 `ActionResult` (authoritative) and `ActionFeedback` (resident-facing)

```text
ActionResult {
  intent_id:string, actor_id:string,
  tick_started:integer, tick_finished:integer,
  outcome:"success"|"failure"|"settled"|"stopped",
  failure_code:FailureCode|null,           // outcome = failure only
  stop:{by:"world",reason:HardStop}|{by:"actor"}|null, // outcome = stopped only
  settlement:{                             // act only; never resident-facing
    rule_id:string|null,
    kind:"applied"|"chance_failed"|"unmet"|"unmatched",
    at:"start"|"completion",
    failed_check:string|null               // unmet only: item slot or condition ID
  }|null,
  state_delta:array<StateDelta>,           // internal, as v1
  visible_feedback:ActionFeedback,
  event_ids:array<string>
}
ActionFeedback {
  intent_id:string,
  status:"done"|"failed"|"stopped",
  failure_code:FailureCode|null,           // kernel preconditions only
  stop_reason:HardStop|"own_choice"|null,
  phenomena:array<PhenomenonId>,           // act only; sorted, unique
  inspected:InspectView|null               // inspect only (§5.2)
}
```

- An `act` that reaches settlement ends with `status = "done"` and its
  phenomena, whatever the settlement kind. Success, a failed chance roll, an
  unmet rule and no matching rule are told apart only by their phenomena and by
  what the resident perceives afterwards (ADR 0007 D5). `settlement` never
  reaches a resident.
- An `act` that fails a generic precondition (§4.3) ends with
  `status = "failed"` and a failure code, like a kernel action. This tells the
  resident a perceivable fact (too far, not held), never anything about rules.
- `stopped` reports a hard stop or the actor's own choice. The rule's
  `on_interrupt` applies in both cases (ADR 0007 D6).
- `state_delta` stays internal, as in v1.

### 4.2 Failure codes

`DEAD`, `INVALID_TARGET`, `NO_PATH`, `PATH_BLOCKED`, `OUT_OF_REACH`, `NO_ITEM`,
`ITEM_TAKEN`, `INVENTORY_FULL`, `CONTAINER_FULL`, `NOT_A_PROCESS`, `EXHAUSTED`,
`OUT_OF_HEARING`, `INVALID_SPEECH_ACT`, `INVALID_REPLY`, `INVALID_TERMS`,
`DIALOGUE_LIMIT`.

- Kept from v1 with the same meaning: `DEAD`, `INVALID_TARGET`, `NO_PATH`,
  `PATH_BLOCKED` (at start), `OUT_OF_REACH`, `NO_ITEM`, `ITEM_TAKEN`,
  `INVENTORY_FULL`, `EXHAUSTED` (a move started with zero stamina),
  `OUT_OF_HEARING`, `INVALID_SPEECH_ACT`, `INVALID_REPLY`, `DIALOGUE_LIMIT`.
- Dropped, because the checks become rule conditions reported as phenomena:
  `RESOURCE_TAKEN`, `NO_NEED`, `NO_WATER`, `ALREADY_FULL`.
- New: `CONTAINER_FULL` (`drop` into a full container or process entity),
  `NOT_A_PROCESS` (`contribute` to an entity that is not an open process),
  `INVALID_TERMS` (§7.2).
- Speech failure codes apply to the utterance, never to the action (§7.1).
- A kernel action invalid at start consumes `invalid_attempt_ticks` (content
  value) before its failure result, and a failure at completion consumes the
  elapsed time, as in v1 (`world-rules-v0.1.md` §4.1).

**Kernel preconditions.** Reach is a Manhattan distance between the actor's
tile and the target's tile. `give` needs a distance of exactly 1, a
neighbouring tile and never the same tile, as v1 (OQ-063). The other kernel
actions need a distance of at most 1, the same tile or a neighbour, as v1
`pick_up`. "Within reach" below means the distance the action needs.
Durations are content values. Every check below runs in the order listed, the
first failure is reported, and receipts are checked before any live lookup.
Where an action exists in v1, the order is the v1 order. Every action first
checks that the actor is alive (`DEAD`).

| Action | Start checks, in order | Completion |
|---|---|---|
| `move_to` | As v1 (`world-rules-v0.1.md` §4.2): positive stamina (`EXHAUSTED`), a known passable target or an allowed frontier tile (`INVALID_TARGET`), a path (`NO_PATH`), the first step free (`PATH_BLOCKED`) | Tile by tile as v1; `EXHAUSTED` and `PATH_BLOCKED` during the walk are hard stops (§4.4) |
| `give` | Receipt for the recipient, which exists, is alive and is not the actor (`INVALID_TARGET`); the recipient is at distance exactly 1 (`OUT_OF_REACH`); the items are held (`NO_ITEM`); the recipient has room (`INVENTORY_FULL`) | After `give_ticks`, the same checks again with the same codes; the transfer is all or nothing |
| `pick_up` (entity) | Receipt; the entity exists and is a portable item on the ground, in a container or in a process entity (`INVALID_TARGET`); its tile, or its holder's tile, is within reach (`OUT_OF_REACH`); the quantity is there (`ITEM_TAKEN`); the actor has room (`INVENTORY_FULL`) | After `pick_up_ticks`, the same checks again; ownership is never checked (§8) |
| `pick_up` (tile) | Receipt for that kind at that tile (`INVALID_TARGET`); the tile is within reach (`OUT_OF_REACH`); the ground holds the quantity of that kind (`ITEM_TAKEN`); the actor has room (`INVENTORY_FULL`) | After `pick_up_ticks`, the same checks again |
| `drop` (tile) | The items are held (`NO_ITEM`); the tile is within reach and passable (`OUT_OF_REACH`, `INVALID_TARGET`) | After `drop_ticks`, the items are still held (`NO_ITEM`) |
| `drop` (entity) | Receipt; the entity exists and is a container or a process entity that accepts items (`INVALID_TARGET`); the items are held (`NO_ITEM`); the entity is within reach (`OUT_OF_REACH`); it has room (`CONTAINER_FULL`) | After `drop_ticks`, the same checks again |
| `wait` | None beyond being alive | After `wait_ticks` |
| `inspect` | Receipt; the entity exists (`INVALID_TARGET`); it is held, or within reach (`OUT_OF_REACH`) | After `inspect_ticks`, if it still exists and is in reach, the result carries the `InspectView`; otherwise the hard stop `TARGET_GONE` |
| `contribute` | Receipt; the entity exists (`INVALID_TARGET`); it is an open process entity (`NOT_A_PROCESS`); it is within reach (`OUT_OF_REACH`) | Work counts each tick while the required materials are present (ADR 0007 D6). Success when the process completes; `TARGET_GONE` if it disappears or leaves reach |

- A target missing at the start check is a failure code after
  `invalid_attempt_ticks`. A target or reserved item that disappears while the
  action runs is a hard stop (`TARGET_GONE`, `INPUT_GONE`, §4.4): it takes the
  elapsed time and applies `on_interrupt`.

### 4.3 Generic `act` preconditions

Checked by the world before rule matching, in this order. The first failure
ends the attempt with its code after `invalid_attempt_ticks`, as v1 does for an
action invalid at start (`world-rules-v0.1.md` §4.1):

1. The actor is alive (`DEAD`).
2. Every named reference has a receipt (`INVALID_TARGET`).
3. The target exists and fits the verb's declared target: its kind (tile,
   entity or resident) and, if the verb declares one, its class, such as a
   container (`INVALID_TARGET`).
4. Every instrument and input is held in the stated quantity, after resolving
   item choices, and so is the target if the verb declares that it must be
   held (`NO_ITEM`).
5. The target is within the verb's declared reach, a range of Manhattan
   distances (`OUT_OF_REACH`). A held target is always within reach.

Each verb declares its target kinds, its optional target class, whether the
target must be held, and its reach in the vocabulary (rule-representation
spec). The compatibility verbs copy the v1 values.

Everything else (properties, actor state, surroundings, time) belongs to rule
conditions and is reported only as phenomena. Settlement order and chance
rolls follow ADR 0009 D1 and the world-engine spec.

**Tick cost and timing.** Each outcome has a fixed elapsed time:

| Case | Ends at | Result |
|---|---|---|
| A generic precondition fails | `t + invalid_attempt_ticks` | `failure` with its code |
| No rule matches, or the matched rule is unmet at start | `t + attempt_ticks` of the verb | `settled`, `unmatched` or `unmet` |
| A rule matches and runs | `t + work_ticks` | `settled`, `applied` or `chance_failed` |
| The running rule is unmet when revalidated at completion | `t + work_ticks` | `settled`, `unmet`, with that rule's `unmet` phenomenon |
| A target or reserved item disappears while running | The boundary where it is gone | `stopped`, `TARGET_GONE` or `INPUT_GONE` |

- `attempt_ticks` is declared per verb in the vocabulary and is at least 1
  (owner, PR-D2). Every attempt that passes §4.3 costs at least one tick (ADR
  0007 D5). The values are content (starter-content spec).
- At completion the rule chosen at start is revalidated as a whole (its item
  predicates, conditions and reserved inputs, ADR 0009 D1); no new rule is
  chosen. For example, two residents start gathering the last fruit of a tree;
  the second to complete finds the stock empty and settles `unmet` at its
  completion tick, having spent its work time.
- The objective record of an `unmet` settlement names the first failing check
  (`failed_check`: an item slot or a condition ID, in declared order) and
  whether it failed at start or completion. Residents never receive these
  (§4.1).

### 4.4 Hard stops

`HardStop` vocabulary, in priority order:

1. `DEATH`
2. `FAINTED`: mental fatigue at its maximum (ADR 0012 D3)
3. `EXHAUSTED`: stamina at zero during a movement or a rule that declares it
4. `PATH_BLOCKED`: the next movement step is blocked
5. `TARGET_GONE`: the target no longer exists or left reach
6. `INPUT_GONE`: a reserved input or instrument is no longer held
7. `WOKEN`: a sleeper is woken before its chosen duration (§6.3)

- Only these end an action from the world side (ADR 0007 D6). When several
  apply at one boundary, the first in this list is reported; the others are
  not reported for that action.
- A completed action is never failed afterwards, as in v1.
- A resident that chooses another action at a turn stops the running one at
  that turn's boundary: `stop = {by:"actor"}`, feedback
  `stop_reason = "own_choice"`. The stopped action makes no progress in the
  next tick, and the new action starts at the same boundary, as a v1
  interruption did. Its `tick_finished` is that boundary. Because the packet
  for that boundary was already delivered, the stop's feedback and its
  `action_ended` report arrive in the next packet (§5.3).
- v1 `EXHAUSTED` and `PATH_BLOCKED` during an action were failure codes. In v2
  they are hard stops during an action and failure codes only at start. The
  equivalence projection maps them (§11.3).

## 5. Perception

### 5.1 `Perception`

```text
Perception {
  schema_version:string, actor_id:string, tick:integer,
  awareness:"awake"|"asleep"|"unconscious",
  needs:array<{need_id:NeedId,band:NeedBand}>,   // sorted by need_id
  own_position:Coord,
  inventory:array<ItemView>,                     // exact, sorted by entity_id
  running_action:{
    intent_id:string, action:string, verb:VerbId|null,
    tick_started:integer, progress:DescriptorValue|null
  }|null,
  visible_tiles:array<{position:Coord,terrain:Terrain}>,
  explored_static_tiles:array<{position:Coord,terrain:Terrain}>,
  visible_entities:array<EntityView>,            // sorted by entity_id; excludes self
  transient_sightings:array<EntityView & {seen_at_step:integer}>,
  environmental_cues:array<{
    cue_id:string,position:Coord,detail_level:"distant"|"near",
    physical_description:string,direction:string|null
  }>,
  heard_utterances:array<HeardUtterance>,        // §7.1
  observed_actions:array<ObservedAction>,        // §5.4
  action_feedback:array<ActionFeedback>,        // every action ended since the previous packet
  last_utterance_feedback:UtteranceFeedback|null
}
ItemView   { entity_id:string, archetype_id:ArchetypeId, material_id:MaterialId|null,
             quantity:integer, descriptors:array<Descriptor> }
EntityView { entity_id:string, kind:"resident"|"corpse"|"item"|"structure"|"process"|"feature",
             archetype_id:ArchetypeId|null, material_id:MaterialId|null,
             position:Coord, quantity:integer|null,
             descriptors:array<Descriptor>,
             observable_signs:array<VisibleSign> }   // residents only; [] otherwise
Descriptor { property_id:PropertyId, value:DescriptorValue }
NeedBand   = "critical"|"low"|"moderate"|"good"|"strong"   // critical is always the worst state
```

- `needs` lists the need IDs that the active packs declare. The compatibility
  pack declares satiety, hydration, stamina and health; the starter pack adds
  mental fatigue (ADR 0012 D3). A band always reads from worst (`critical`) to
  best (`strong`), so for mental fatigue `critical` means most tired.
- While `awareness` is not `awake`, the senses are off: `visible_tiles`,
  `visible_entities`, `transient_sightings`, `environmental_cues`,
  `heard_utterances` and `observed_actions` are empty. Everything else stays:
  `needs`, position, inventory, `running_action`, `explored_static_tiles` and
  the feedback fields. Speech missed while asleep is never replayed later, as
  in v1.
- `Terrain` and `VisibleSign` keep their v1 vocabularies
  (`interface-contract-v0.1.md` §2.5); the vocabulary spec may add members.
- `explored_static_tiles` keeps its v1 meaning: static map data the world
  delivers, in both memory arms (ADR 0007 D4). Dynamic facts never enter it.
- Stackable archetypes (declared in content) are held and shown as stacks with
  one entity ID and a `quantity`. Splitting a stack allocates a new ID for the
  part that moves.
- `Perception` never contains: true values that differ from apparent values,
  `on_inspect` or `on_use` values, rule IDs, settlement kinds, unmatched
  attempt descriptors, another resident's needs (beyond `observable_signs`),
  `owner_id`, memory, intentions or any agent-side data.

### 5.2 Observability and appearances

- Each property declares `visible`, `on_inspect` or `on_use` (ADR 0008 D2).
  `visible` properties appear in `EntityView` and `ItemView`. `on_inspect`
  properties appear only in an `inspect` result. `on_use` properties never
  appear as values; they show only through phenomena.
- A material may declare an apparent value for a property, and an instance may
  override it in content. Perception reports the apparent value; settlement
  uses the true value (ADR 0007 D4). Apparent values do not change over time in
  this version.
- `inspect` reports apparent values too. Only use reveals the truth, through
  phenomena (owner, PR-D3).
- **Recognition by experience** (owner, PR-D3). A newcomer cannot see through a
  deceptive appearance; an experienced resident can. The world shows every
  resident the same thing and keeps no record of who knows what; recognition
  lives in memory:
  - A deceptive material is always shown with its true `material_id` and
    `archetype_id`. Only property values are deceptive. A resident that has
    learned how a material behaves ("vines look strong but snap") can
    recognize the next vine by its identity.
  - An instance that overrides its material's apparent value must declare a
    *tell*: a true `visible` or `on_inspect` property that sets it apart from
    ordinary instances of that material, for example "fibres look dry". The
    world never says what a tell means. The rule-representation spec defines
    tells, and its validator refuses an override without one.
  - Because recognition is memory, a memory-off resident loses it at a period
    boundary, as intended (ADR 0014 D2). A world-side familiarity count would
    instead carry knowledge across periods in both arms.

```text
InspectView { entity_id:string, archetype_id:ArchetypeId|null, material_id:MaterialId|null,
              descriptors:array<Descriptor> }   // visible and on_inspect properties
```

### 5.3 `BoundaryDelivery` and world reports

```text
BoundaryDelivery {
  delivery_id:string, actor_id:string, observed_tick:integer,
  perception:Perception,
  reports:array<WorldReport>               // total order: kind, subject ID, threshold ID
}
WorldReport {
  kind:"action_ended"|"need_band_changed"|"need_threshold_crossed"|"utterance_heard"|
       "entity_first_seen"|"action_observed"|"progress_step"|"woke",
  subject_id:string|null,                  // see the table below
  addressed:boolean|null,                  // utterance_heard only
  band:NeedBand|null,                      // need_band_changed only: the new band
  threshold_id:string|null                 // need_threshold_crossed only
}
```

- `delivery_id`, packet pending and acknowledgement, and checkpoint rules are
  as in v1 (`interface-contract-v0.1.md` §2.2, "Physical delivery, not
  memory"). Pending packets survive save and restore and are delivered exactly
  once.
- Reports and `action_feedback` cover what happened since this actor's
  previous packet, and are never repeated in a later packet.
- `action_feedback` lists every action of this actor that ended since its
  previous packet, in order of `tick_finished`, then intent ID. It usually
  holds one entry. It holds two when the actor replaced a running action at
  its turn: the old action stopped at that boundary, after the packet had
  been delivered, so its feedback arrives in the next packet together with
  the result of the new action if that one has also ended (§4.4).
- Reports are in a total order: kind in the order of the table below, then
  `subject_id`, then `threshold_id` (a null `threshold_id` first).
- Reports are facts about this boundary, not instructions. The world never
  marks a report as urgent and never asks for a turn. The harness maps reports
  to notification classes and turns (decision-loop spec, ADR 0013 D3).
- `DecisionTrigger`, deferred trigger sets and `InterruptionReason` do not
  exist in v2.

How each report is built. Fields not listed are `null`.

| `kind` | `subject_id` | One report per | Built when |
|---|---|---|---|
| `action_ended` | The intent ID | Entry of `action_feedback` | Always with that entry: an action that ended since the previous packet, with any outcome |
| `need_band_changed` | The need ID; `band` is the new band | Need whose band differs from the band in this actor's previous packet | Never at tick zero |
| `need_threshold_crossed` | The need ID; `threshold_id` names the threshold | Downward crossing of a named threshold | The need went from above the threshold to at or below it during the last tick; never again while it stays below (the v1 crossing rule, `interface-contract-v0.1.md` §2.5) |
| `utterance_heard` | The utterance ID; `addressed` is true when this actor is the addressee | Utterance in `heard_utterances` | Always with the heard utterance |
| `entity_first_seen` | The entity or cue ID | First exposure of an entity ID, or a cue's first upgrade from distant to near | The v1 `NEW_SIGHT` rule; exposures at tick zero seed receipts without reports |
| `action_observed` | The observed intent ID | `ObservedAction` delivered (§5.4) | Always with the observation |
| `progress_step` | The actor's intent ID, or the process entity ID | Change of a progress descriptor | The descriptor of the actor's running action, or of a process entity it contributes to, changed in the last tick |
| `woke` | `null` | Waking | The actor woke at this boundary (§6.3) |

- Named thresholds are declared per need in content (rule-representation and
  starter-content specs). The report names the need and the threshold, never a
  value.
- A pack may also mark a threshold as waking a sleeper (§6.3).
- The critical band of hunger or thirst is the notification the harness may
  not mute (ADR 0013 D3).

### 5.4 Watching

```text
ObservedAction {
  actor_id:string, intent_id:string, tick:integer,
  action:string, verb:VerbId|null,
  target:Target|null,
  visible_items:array<{entity_id:string,archetype_id:ArchetypeId|null,
                       material_id:MaterialId|null,descriptors:array<Descriptor>}>,
  phenomena:array<PhenomenonId>            // only phenomena declared visible to watchers
}
```

- A resident sees another resident's action when the actor is in its sight at
  the boundary where the action starts, stops or settles (ADR 0007 D10).
- It sees who acted, the action or verb, the visible items used and the
  phenomena that the vocabulary marks as visible to watchers. It never sees
  `rule_id`, the settlement kind, true values, `on_inspect` values or the
  actor's own feedback.
- **The target is projected for each watcher, never copied from the intent.**
  `target` holds the actor's target only when the watcher itself perceives it
  at that boundary: a tile in the watcher's `visible_tiles`, or an entity or
  resident in its `visible_entities` or own inventory. Otherwise `target` is
  `null`. For example, A walking towards a distant tile that B cannot see
  shows B only that A is walking. `visible_items` follows the same rule.
- Watching creates no receipt. A watcher gains a receipt for a target only
  through its own perception (§3.3), never because another resident chose
  that target.
- Kernel actions (`give`, `pick_up`, `drop`, `contribute`) are watched the same
  way, so residents can see who gave or took what.

## 6. Timed actions, processes and sleep

### 6.1 Timed actions

- Duration and progress keep the v1 rule: an action starting at `t` progresses
  first in `t → t+1`; duration `d` finishes at `t+d`.
- No world soft interrupts (ADR 0007 D6). Speech, sightings, need bands and
  progress only produce reports.

### 6.2 Process entities

- `contribute` adds one unit of work per tick while the process's required
  materials are present (ADR 0007 D6). It runs until the process completes, a
  hard stop applies, or the actor stops it.
- `drop` puts materials into a process entity; `pick_up` takes items out,
  including outputs, whoever owns them (§8).
- Progress appears as a coarse descriptor in `EntityView` and
  `running_action.progress`.

### 6.3 Sleep and waking

- A sleeper's `awareness` is `asleep`; a fainted resident's is `unconscious`.
  Neither takes a turn.
- The world wakes a sleeper at the end of its chosen duration, or earlier when
  a need crosses a threshold that the pack marks as waking (§5.3). Nothing else
  wakes it in this version; speech does not, as in v1 (owner, PR-D6). An early
  wake stops the sleep with `WOKEN` at the boundary after the crossing. When
  the chosen duration ends at that same boundary, the sleep completes instead,
  as completion wins in v1.
  - The starter pack marks the critical-band boundary of hunger and of thirst
    as waking (owner, PR-D6).
  - The compatibility pack marks the v1 urgent thresholds of satiety,
    hydration and stamina (`agents.urgent_*_below`) as waking, because waking
    a sleeper at an urgent crossing is a v1 mechanic (`world-rules-v0.1.md`
    §4.3). It keeps the v1 band cutoffs unchanged, so the policy's inputs do
    not change.
- Later direction, not in this version: being addressed directly wakes a
  sleeper (owner, PR-D6).
- Hunger and thirst fall more slowly during sleep than while awake (owner,
  PR-D6). This is a starter-pack mechanic: the compatibility pack keeps the v1
  rates, so the equivalence check is unaffected. The rates are starter-content
  values; because slower decay makes survival cheaper, they are an
  owner-approved exception under ADR 0010 D3 and stay within its survival
  tolerance.
- A wake produces a `woke` report, and the resident gets a turn.
- How long unconsciousness ends a waking period is a memory-formation value
  (K, ADR 0012 D2). The world does not know K.

## 7. Speech and agreements

### 7.1 Utterances

```text
Utterance {
  addressee_id:string|null,                // null only for a statement to everyone in range
  speech_act:"statement"|"propose"|"accept"|"refuse",
  text:string,                             // adapter-level length cap
  terms:Terms|null,                        // required for propose, null otherwise
  in_reply_to:string|null                  // required for accept and refuse, null otherwise
}
HeardUtterance {
  utterance_id:string, speaker_id:string, addressee_id:string|null,
  speech_act:string, text:string, terms:Terms|null, in_reply_to:string|null,
  heard_at_tick:integer
}
UtteranceFeedback { utterance_id:string|null, failure_code:FailureCode|null }
```

- An utterance may ride on any turn, next to an action or `continue`. It never
  stops or delays the action (ADR 0007 D10).
- It is emitted during the settlement of `t → t+1` and heard by every awake
  resident within hearing radius at emission, the speaker excluded. Listeners
  receive it in their boundary `t+1` packet. This is the v1 `talk` timing
  without the action.
- Hearing radius, dialogue sessions, the per-session turn cap, the quiet gap
  and the cooldown keep their v1 rules (`world-rules-v0.1.md` §4.2) and
  content values.
- `accept` and `refuse` must reply to a `propose` addressed to the speaker,
  and must be addressed to its speaker; otherwise `INVALID_REPLY`. A proposal
  is answered at most once.
- A statement with `addressee_id = null` is heard by everyone in range. It
  opens or continues no dialogue session, because sessions are keyed by an
  addressed pair (`world-rules-v0.1.md` §4.2).
- World-level checks, in this order, keep the v1 `talk` order: the addressee
  has a receipt, exists and is alive (`INVALID_TARGET`); it is within hearing
  radius (`OUT_OF_HEARING`); the speech act is allowed (`INVALID_SPEECH_ACT`);
  a reply is valid (`INVALID_REPLY`); the terms are valid (`INVALID_TERMS`,
  §7.2); the session cap allows it (`DIALOGUE_LIMIT`). The first failure is
  reported.
- A failed utterance produces no `utterance_spoken` event. Its failure code
  reaches the speaker in `last_utterance_feedback` at `t+1`; the action is
  unaffected.
- Utterances emitted in one tick are ordered as the world-engine spec settles
  them. In the compatibility pack that order must equal the v1 completion order
  of the same `talk` actions (§11.2).

### 7.2 Agreements

```text
Terms {
  promisor_id:string, promisee_id:string,  // the speaker and the addressee, in either role
  what:{kind:"give_item",item:ItemSpec}
     | {kind:"return_item",item_id:string}
     | {kind:"be_at",position:Coord}
     | {kind:"contribute",process_id:string,work_ticks:integer},
  due_tick:integer|null                    // required for be_at
}
ItemSpec = {item_id:string} | {archetype_id:ArchetypeId,quantity:integer}
```

- The words of an utterance stay free. Only `propose` carries terms, from this
  closed set of four kinds, which the objective log can check (ADR 0007 D10;
  owner, PR-D5). `due_tick` is optional, except for `be_at`.
- A `return_item` promise is met only when the same item instance (`item_id`)
  comes back, never another item of the same kind (owner, PR-D5).
- Both parties of an accepted agreement get a mechanical record, one as
  promisor and one as promisee (owner, PR-D5). The record format is the
  memory-model spec.
- An agreement exists only when the addressee answers the proposal with
  `accept`. Then the world emits `agreement_accepted` (§9) with both utterance
  IDs and the terms. Accepting moves nothing.
- The world never enforces an agreement and never judges it kept or broken.
  Evaluation judges from objective events (ADR 0014 D2).
- The world checks terms only for well-formedness against what the speaker
  can reference: the promisor and promisee are the speaker and the addressee;
  `item_id`, `process_id` and positions are exposed to the speaker; quantities
  and work are positive; `due_tick` is later than the current tick. Otherwise
  `INVALID_TERMS`.
- v1 `request` maps to `propose` with the addressee as promisor and
  `give_item` to the speaker (§11.2).

## 8. Ownership

- An entity may record `owner_id`: its maker, or the recipient of a `give`
  (ADR 0008 D6). Ownership is world state and appears in objective events.
- Ownership restricts nothing. Any resident may pick up, use or take an item
  another owns, including process outputs; the world never refuses it. This
  replaces the v1 rule of no theft (`world-rules-v0.1.md` §4.2) in v2.
- `owner_id` is not in `Perception`. A resident learns who made or gave
  something by watching or by being told.

## 9. Objective events

The v1 envelope is kept (`interface-contract-v0.1.md` §3.1), with
`schema_version = "wap/0.1"`, `intent_id` set for intent-caused events and
`llm_call_id` unchanged. Event ID format, ordering and causal references keep
the v1 rules. Residents never receive events wholesale.

Events produced by this protocol:

| `EventType` | Payload | Emitted when |
|---|---|---|
| `world_initialized` | `{config_hash, map_hash, vocabulary_hash, rule_library_hash, pack_ids:array<string>, initial_snapshot_hash}` | Run start |
| `action_started` | `{action, verb:string|null, turn_id, duration_ticks:integer|null}` | The world accepts an intent |
| `action_progressed` | `{action, elapsed_ticks, remaining_ticks:integer|null, route_cursor:integer|null}` | Each tick of an unfinished action |
| `action_succeeded` | `{action}` | A kernel action completes |
| `action_failed` | `{action, verb:string|null, failure_code}` | A kernel or generic `act` precondition fails |
| `action_stopped` | `{action, verb:string|null, by:"world"|"actor", reason:HardStop|null}` | A hard stop or the actor's own choice |
| `act_settled` | `{verb, rule_id:string|null, kind:"applied"|"chance_failed"|"unmet"|"unmatched", at:"start"|"completion", failed_check:string|null, phenomena:array<string>}` | An `act` settles |
| `attempt_unmatched` | `{verb, descriptor:AttemptDescriptor}` | Right after `act_settled` with `kind = "unmatched"` |
| `resident_moved` | as v1 | Each entered tile |
| `item_transferred` | `{item_id, archetype_id, quantity, from:{kind,id}, to:{kind,id}, via:"give"|"pick_up"|"drop", owner_before:string|null, owner_after:string|null}` | A kernel transfer succeeds |
| `entity_inspected` | `{entity_id, descriptors}` | An `inspect` completes |
| `action_observed` | `{observer_id, actor_id, observed_intent_id}` | A watcher receives an `ObservedAction` |
| `utterance_spoken` | `{utterance_id, addressee_id:string|null, speech_act, text, terms:object|null, in_reply_to:string|null}` | An utterance passes validation |
| `utterance_heard` | `{utterance_id, listener_id}` | Each listener, sorted by listener ID, right after `utterance_spoken` |
| `agreement_accepted` | `{agreement_id, proposal_id, acceptance_id, terms}` | After the `utterance_heard` events of the accepting utterance |
| `exploration_updated` | as v1 | New static tiles enter a resident's explored footprint |
| `resident_fell_asleep` | `{resident_id, duration_ticks}` | A sleep starts |
| `resident_woke` | `{resident_id, early:boolean}` | A sleeper wakes |
| `resident_fainted` | `{resident_id}` | Mental fatigue reaches its maximum |
| `resident_died`, `corpse_created` | as v1 | Death |
| `rule_added` | `{rule_id, content_hash, provenance}` | A rule is added at a boundary (ADR 0009 D5) |
| `agent_fallback_used` | `{resident_id, turn_id, reason, fallback_policy_id}` | `sim` uses the fallback policy for a turn (ADR 0013 D7) |

- An accepting utterance emits, in this order: its `utterance_spoken`, the
  `utterance_heard` events sorted by listener ID, then `agreement_accepted`.
  `agreement_accepted` names the proposal's and the acceptance's
  `utterance_spoken` events in `caused_by_event_ids`, so causal references
  point only backwards, as in v1.
- `AttemptDescriptor` is the normalized descriptor of ADR 0007 D5: the verb
  plus the property signatures of target, instruments and inputs. Its exact
  form is shared with rule conditions and defined in the rule-representation
  spec, so a proposed rule can be back-tested on it (ADR 0007 D9).
- Effects of rules (entities created or consumed, component state, need
  changes, world dynamics) emit events defined by the world-engine spec.
- v1 events with no v2 counterpart: `stamina_action_cost_applied`,
  `fruit_gathered`, `fruit_consumed`, `water_drank`, `canteen_filled`,
  `fruit_regrew`, `item_given`, `item_picked_up`, `item_dropped`,
  `action_interrupted`. Rule effects and `item_transferred` replace them; the
  equivalence projection maps them (§11.3).

## 10. Model-facing schema

- The schema of a turn's world part is generated from the protocol version,
  the verb vocabulary (verb IDs, their target kinds and parameter shapes) and
  the reference kinds only. Rule library contents never enter it, so adding a
  rule changes neither the schema nor its hash (ADR 0007 D1, D7).
- The full model response adds the agent-side fields of the decision-loop spec
  (intention update, mute list, memory citations). Those never reach the world.
- The schema is identified by `action_schema_sha256` over its canonical bytes,
  recorded with every model call. CI keeps the P3 drift check between the
  generated schema and the protocol models.
- Where and how the schema is sent (once, in the structured-output field) is
  the decision-loop spec (ADR 0007 D7).

## 11. Migration from v1

### 11.1 Lanes

- v1 stays frozen. The compatibility pack (starter-content spec) expresses the
  11 v1 actions on the v2 kernel and rules.
- Before the v1 engine is removed, the expected projections (§11.3) are
  generated from the v1 engine at the archive tag and committed as fixtures.
  The M12 task cards set the tag name and the removal point. v1 runs then
  replay from the tag only (CR-009).
- The viewer does not load v1 replay bundles after the removal; v1 runs are
  viewed at the archive tag (owner, PR-D7). No v1 contract models are kept for
  display.
- Unknown versions are refused, with no implicit migration.

### 11.2 Adapters for the rule-based policy

The rule-based policy keeps its v1 plan queue and reproduces the v1
interrupts of `world-rules-v0.1.md` §4.3 on its own side (ADR 0007 D8). Two
adapters and one feedback bridge connect it to v2.

**Supported profile.** The compatibility pack runs only v1 configurations
with `talk_ticks = wait_ticks = invalid_attempt_ticks = 1`, the v1 default; it
refuses any other profile at load. It sets the `attempt_ticks` of each
compatibility verb to `invalid_attempt_ticks`, so a v1 start failure that
becomes an unmet rule takes the same time. It keeps the v1 entity IDs of
trees, the canteen and corpses, so receipts and targets map one to one. Its
verbs copy the v1 reach and target constraints, and its rules declare their
conditions in the v1 check order.

**Intent adapter.** It converts the policy's next v1 intent when that intent
starts, from the current perception. It keeps a table from each v2
`intent_id` to the v1 intent ID the policy issued, so every result reaches the
policy under its v1 identity.

| v1 intent | v2 submission |
|---|---|
| `move_to` | `move_to`, same tile |
| `gather` tree | `act` verb `gather`, target the tree entity |
| `eat` | `act` verb `eat`, input `{held: fruit}` × 1 |
| `drink {source:"spring"}` | `act` verb `drink`, target the spring tile |
| `drink {source:"canteen"}` | `act` verb `drink`, instrument `{held: canteen}` |
| `fill_canteen` target | `act` verb `fill`, target the submitted v1 target entity, kept as given. The verb declares its target class (a container) and that the target must be held, so a wrong target is `INVALID_TARGET` and an unheld canteen is `NO_ITEM`, in the v1 order; the spring and fullness are rule conditions |
| `rest` | `act` verb `rest` |
| `sleep` | `act` verb `sleep`, `duration_ticks` = v1 `sleep_ticks` |
| `talk` | `wait` carrying the utterance. `statement` stays `statement`; `request {item_type, quantity}` becomes `propose` with the addressee as promisor, the speaker as promisee and `give_item {archetype_id, quantity}`; `accept` and `refuse` keep their act and `in_reply_to` |
| `give {item_type, quantity}` | `give`, the same recipient, item `{held: item_type}`, same quantity |
| `pick_up {tile, item_type, quantity}` | `pick_up` by tile, same archetype and quantity |
| `wait` | `wait` |

- Item choice by kind (§3.2) lets every v1 intent convert without inventing an
  item ID: a v1 `eat`, `give` or canteen `drink` with nothing held fails
  `NO_ITEM` at the world, and a short ground pile fails `ITEM_TAKEN`. Where
  v1 checked a rule condition before such a check, the order can differ; the
  supported domain (§11.3) lists those cases.
- Utterance IDs are opaque strings in both versions and pass through
  unchanged, so `in_reply_to` needs no table.
- The reverse mapping, used by the perception adapter and the projection,
  turns a `propose` with the addressee as promisor and `give_item` of fruit or
  the canteen back into a v1 `request {item_type, quantity}`.

**Legacy feedback bridge.** In v2 a rule failure reaches a resident only as
phenomena (§4.1). The v1 policy needs v1 failure codes instead, for example
`RESOURCE_TAKEN` to back off from an empty tree. The bridge supplies them
without widening what any resident sees:

- Owner and scope: `sim` runs it, only for the rule-based policy, and only in
  the compatibility pack.
- Input: the authoritative `ActionResult` of the policy's own actions
  (outcome, failure code, stop, and for `act` the settlement with `rule_id`
  and `failed_check`), and the compatibility pack's table from
  (`rule_id`, `failed_check`) to v1 failure codes. The pack validator refuses
  a compatibility rule whose checks are not all in that table.
- Output: for each ended action, one v1 `ActionResult` and `ActionFeedback`
  under the v1 intent ID, with the v1 status, failure code or interruption
  reason and ticks (mapping in §11.3), and the v1 triggers that result
  produces.
- The output goes only to the policy's private state and decision record. It
  never enters a model context, a memory or a `Perception`. When the policy
  runs as the fallback for an LLM resident, the output still stays in the
  policy, and fallback actions stay out of the resident's mind as before (ADR
  0013 D7).
- The ordinary v2 `ActionFeedback` is unchanged: `settlement`, `rule_id` and
  `failed_check` never reach a resident (WAP-01).

**Joined talk result.** A v1 `talk` is one v2 turn: a `wait` carrying the
utterance. The bridge joins the wait's entry in `action_feedback` and
`last_utterance_feedback` into exactly one v1 `ActionResult` for the policy,
under the v1 talk intent ID and with the wait's ticks: `success` when the
utterance succeeded, otherwise `failure` with the utterance's failure code. The
joined failure produces the v1 trigger `ACTION_FAILED`, so the policy discards
its queued intents and applies its failed-talk back-off, as in v1
(`rule-policy-v0.1.md`). Only the bridge joins them; in v2 itself a failed
utterance never fails an action (§7.1).

**Perception adapter.** It maps v2 perception and reports to the v1
`Perception` and triggers that the policy reads:

- need bands by need ID; fruit stacks to `fruit_count`; the canteen item to
  `canteen_id` and servings; trees to `fruit_band`; ground fruit stacks to
  ground piles; heard `propose` utterances to v1 requests (above);
- reports to v1 `DecisionTrigger` codes, in the v1 trigger order with every
  applicable code kept: `action_ended` to the triggers of the bridge's v1
  result, or `PLAN_FINISHED` when the queue is empty; `need_threshold_crossed`
  of an urgent threshold to `URGENT_NEED`; `utterance_heard` to
  `UTTERANCE_HEARD`, plus `DIRECT_SPEECH` when addressed, plus
  `REPLY_REQUIRED` for an addressed request; `entity_first_seen` to
  `NEW_SIGHT`; `woke` to `WOKE`.

The compatibility pack declares the v1 urgent thresholds as named thresholds
(§5.3). With these triggers the policy applies the v1 interruption table
itself: where v1 would interrupt a running awake action, the adapter gives the
policy the v1 `interrupted` result and trigger at that boundary, as v1 did, and
the policy chooses its next intent; the running action stops by the actor at
that boundary (§4.4). The v2 stop feedback that arrives in the next packet
(§5.3) is matched to it and not passed on again. A sleeper is woken by the
world instead (§6.3), because it has no turn.

### 11.3 Equivalence projection

Compared per tick against the committed v1 fixtures:

- each resident: position, alive, the four need values (exact integers),
  fruit count, and canteen holding and servings;
- each fruit tree's stock, each ground fruit pile, the canteen's place and
  servings, and corpses;
- the ordered list of utterances: tick, speaker, addressee, speech act, text
  and request terms (via the reverse mapping of §11.2);
- per resident, the ordered list of action outcomes with `tick_started` and
  `tick_finished`, mapped as below, and the policy's next decision.

| v1 result | v2 counterpart |
|---|---|
| `success` | Kernel `success`, or `act` settled `applied` |
| `failure` at start with a code v2 keeps (`DEAD`, `INVALID_TARGET`, `NO_PATH`, `PATH_BLOCKED`, `EXHAUSTED` of `move_to`, `OUT_OF_REACH`, `NO_ITEM`, `ITEM_TAKEN`, `INVENTORY_FULL` of a transfer) | The same failure code, at `t + invalid_attempt_ticks` |
| `failure` at start with a code that became a rule check (`RESOURCE_TAKEN`, `NO_NEED`, `NO_WATER`, `ALREADY_FULL`; `EXHAUSTED` and `INVENTORY_FULL` of `gather`; `OUT_OF_REACH` of `fill`) | `act` settled `unmet` at start, at `t + attempt_ticks`; the bridge maps (`rule_id`, `failed_check`) to the v1 code |
| `failure` at completion of a kernel action (for example `ITEM_TAKEN` of the loser of two pickups of the last fruit) | The same kernel failure code at completion, at `t` + the action's duration |
| `failure` at completion represented by a rule check (for example `RESOURCE_TAKEN` of the loser of a contested gather) | `act` settled `unmet` at completion, at `t + work_ticks`, mapped by the bridge |
| Failed `talk` | The joined talk result (§11.2) |
| `interrupted` `DEATH` | `stopped` by the world, `DEATH` |
| `interrupted` `URGENT_NEED` of a sleeper | `stopped` by the world, `WOKEN` |
| `interrupted` `URGENT_NEED`, `DIRECT_SPEECH` or `NEW_SIGHT` of an awake action | `stopped` by the actor at the same boundary. The bridge's v1 result carries the v1 reason, which the projection compares |
| `failure` `EXHAUSTED` or `PATH_BLOCKED` during movement or gathering | `stopped` by the world, same name |
| Completed, then death in the same tick | The completion stands in both |

**Supported domain.** The equivalence promise covers every intent the frozen
rule-based policy produces, and scripted v1 intents of the same shapes, with
two stated exceptions:

1. Scripted inputs that fail several checks at once, where v1 checked a
   condition that v2 makes a rule condition before a check that v2 makes
   generic. There are two: `gather` with no stamina and a missing or
   unreachable tree (v1 `EXHAUSTED`; v2 `INVALID_TARGET` or `OUT_OF_REACH`),
   and `drink` with full hydration and no reachable spring or no canteen held
   (v1 `NO_NEED`; v2 `OUT_OF_REACH` or `NO_ITEM`). v2 reports its own order
   (§4.3). Other combined failures keep the v1 order, because kernel actions
   copy it (§4.2) and compatibility rules declare their conditions in it.
2. A second reply to one request. v1 accepts it; v2 answers a proposal at most
   once (§7.1) and reports `INVALID_REPLY`.

Fixtures pin the v2 outcome of each exception (WAP-26). M12 checks that no run
of the P2 matrix reaches one; if one does, the equivalence check fails and the
case goes through a change request. The adapter never invents an item ID; an
intent it cannot convert is refused, recorded, and never reaches the world.

**Seeds and fixtures.** The P2 acceptance matrix (`p2-experiments-v0.1.md`
§1–§2), same seeds and horizon, is the trajectory regression. Random seeds do
not guarantee that every branch above occurs, so committed scripted fixtures
pin each one (WAP-23). Event IDs and byte equality are not compared, because
the event catalog changes (ADR 0007 D8).

## 12. Determinism and replay

- All v2 DTOs and events use the v1 canonical encoding and integer rules
  (`interface-contract-v0.1.md` §6). Arrays are sorted as stated; where not
  stated, by ID.
- Nothing in settlement reads wall-clock time, model latency or agent-side
  data.
- A recorded run replays from its recorded `TurnSubmission`s with no model
  call. Within the v2 lane, replay reproduces the event log byte for byte.
- `TurnSubmission`s are part of the decision record; how agents store them is
  the decision-loop spec.

## 13. Acceptance tests

| ID | Test |
|---|---|
| WAP-01 | For one `act` set up four ways (applied, chance failed, unmet, unmatched), `ActionFeedback` differs only in `phenomena`; `settlement`, `rule_id` and `failed_check` appear only in `ActionResult` and events |
| WAP-02 | Binding (§3.1): `continue` with no running action, a nested actor or turn that differs from the outstanding turn, a stale `observed_tick`, a malformed `intent_id`, and a shape error in the utterance are each `INVALID_TURN` with no world effect; a second submission for a committed turn is refused; the ordinal advances exactly once for the turn finally committed, including a fallback turn |
| WAP-03 | An utterance on a turn with `continue` is heard at `t+1`; the running action's progress and end tick are unchanged; the addressee's packet has `utterance_heard` with `addressed = true` and an overhearing resident's has `addressed = false` |
| WAP-04 | Two hard stops at one boundary report the higher one (§4.4), for each named pair; a completed action is never failed afterwards, including by death in the same tick |
| WAP-05 | An actor replaces an unfinished gather G at boundary `t` with a one-tick wait W: G finishes at `t` with `by: "actor"` and makes no further progress, its `on_interrupt` applies, W starts at `t` and finishes at `t+1`. The packet for `t+1` carries both in `action_feedback`, G before W, with two `action_ended` reports; saved before acknowledgement and restored, it is delivered once, and the next packet repeats neither |
| WAP-06 | A material with an apparent value shows it in perception, while settlement uses the true value |
| WAP-07 | `inspect` returns `on_inspect` descriptors, which never appear in later `EntityView`s; `inspect` out of reach is `OUT_OF_REACH`; a target gone before completion stops with `TARGET_GONE` |
| WAP-08 | A watcher in sight receives `ObservedAction` with watcher-visible phenomena only; a resident out of sight receives none; neither sees `rule_id` or true values. A visible actor walking to a tile the watcher cannot see, or acting on an entity hidden from it, shows `target = null` and gives the watcher no receipt; a visible target is shown |
| WAP-09 | `propose` then `accept`, heard by two listeners, emits `utterance_spoken`, two `utterance_heard` sorted by listener, then `agreement_accepted` with backward causal links. `accept` without a matching proposal is `INVALID_REPLY`; a second answer, including after a `refuse`, fails. Each term kind is accepted when well formed; wrong parties, unexposed references and a `due_tick` not in the future are `INVALID_TERMS` |
| WAP-10 | A resident picks up an item owned by another; the world allows it, and `item_transferred` records both owners; stack splits, container and process transfers, capacity limits and a race for the last item settle as §4.2 states |
| WAP-11 | Adding a rule to the library leaves `action_schema_sha256` unchanged; adding a verb changes it; a save with a different vocabulary or library hash is refused |
| WAP-12 | `TurnSubmission` has no field for intention, mute list, citations or context pressure; settlement is identical whatever the memory, intention, mute state or context pressure on the agent side, and whichever policy produced the submission |
| WAP-13 | A DTO with an unknown `schema_version` is refused |
| WAP-14 | While asleep or unconscious the senses are off (§5.1): no visible entities, no heard utterances, no observations, and missed speech is not replayed after waking; needs, position, inventory, running action, explored static tiles and feedback stay |
| WAP-15 | The compatibility pack with the rule-based policy matches the committed v1 projections on the seed set (§11.3) |
| WAP-16 | Replaying a recorded run from its submissions makes no model call and reproduces the event log byte for byte, including fallback turns and reports |
| WAP-17 | A deceptive material is shown with its true `material_id` and its apparent values, both on sight and on `inspect`; perception is identical for a resident that has used it before and one that has not |
| WAP-18 | In the starter pack a sleeper wakes at the end of `duration_ticks` or when hunger or thirst crosses into the critical band; in the compatibility pack, at a v1 urgent crossing. Completion wins when both fall on one boundary; speech never wakes; an already-critical need at sleep start does not wake again until a new crossing; `duration_ticks` of 6 and 54 are accepted and 5 and 55 are `INVALID_TURN` |
| WAP-19 | Report construction (§5.3): one boundary with an ended action, addressed and overheard speech, a band change, a threshold crossing, a first sighting and a cue upgrade, an observed action, a progress step and a wake yields exactly the expected report array, in the total order of §5.3. Two thresholds of one need crossed in one tick give two reports ordered by threshold ID. Saved before acknowledgement and restored, the packet is delivered once, and the next packet repeats none of it |
| WAP-20 | Kernel preconditions (§4.2): for each kernel action, a target in reach, out of reach, of the wrong kind and missing gives the stated code; when several checks fail, the first in the table wins. `give` to a recipient at distance 0, 1 and 2 gives `OUT_OF_REACH`, success and `OUT_OF_REACH`; a distant recipient with no fruit held gives `OUT_OF_REACH`, as v1 |
| WAP-21 | `act` timing (§4.3): a generic failure ends at `t + invalid_attempt_ticks`; unmet or unmatched at start at `t + attempt_ticks`; a contested last fruit settles the loser `unmet` at completion at `t + work_ticks`; a target gone mid-action stops with `TARGET_GONE` and applies `on_interrupt`; a missing target together with a missing input reports `INVALID_TARGET` |
| WAP-22 | Item choice (§3.2): named choices are reserved before by-kind ones, so `[{held: X}, {item: e1}]` with `e1 < e2` held resolves to `e2` and `e1` in either listed order, and with only `e1` held reports `NO_ITEM`; by-kind choices take stacks in ascending ID order across several stacks, split a larger stack and never use one instance twice; the same resolution follows after replay or restore. `pick_up` by tile counts whatever stacks of that kind lie there at completion, and reports `ITEM_TAKEN` when they are too few |
| WAP-23 | Committed scripted migration fixtures (§11.3), each asserting the packet actually delivered to the policy (v1 intent ID, status, code, triggers), ticks, queue disposal, back-off key and the next decision: urgent crossings inside one band for satiety, hydration and stamina, awake and asleep; urgent, direct speech and a new sight together, with v1 priority and every trigger kept in v1 order; `DIALOGUE_LIMIT`, `OUT_OF_HEARING` and `INVALID_REPLY` on an accept followed by a queued give, under the v1 talk intent ID; two talks competing for the last dialogue slot beside a non-talk completion; a request round trip; unfinished death; completion then death in one tick; natural and early waking; an empty tree at start and a contested last fruit (`RESOURCE_TAKEN`), and gather with no stamina or no room; `give` at distance 0; `fill_canteen` with a tree as target, and the correct-target control; two pickups of the last ground fruit (loser `ITEM_TAKEN` after its pickup time); a first reply; transfers by kind, including too few items; a profile with `talk_ticks = 2` refused at load |
| WAP-24 | A threshold crossing inside one band is reported once, is not repeated while the need stays below, is reported again after the need recovers and falls once more, and is never reported at tick zero |
| WAP-25 | Bridge separation (§11.2): two compatibility outcomes with identical resident feedback (for example an empty tree and a full inventory on `gather`) give different bridge outputs; no bridge output appears in any model context, memory or `Perception`; a compatibility pack whose rule checks are not all in the code table is refused at load; outside the compatibility pack there is no bridge |
| WAP-26 | Domain exceptions (§11.3): `gather` with no stamina and an unreachable tree reports `OUT_OF_REACH`; `drink` with full hydration and no canteen held reports `NO_ITEM`; a second reply to one request reports `INVALID_REPLY`. Each outcome is pinned and listed as outside the equivalence promise |

## 14. Disposition of the ADR 0007 open questions

| ADR Q | Disposition |
|---|---|
| Q1 Instinct and recipes | Owner, PR-D1 (§3.3) |
| Q2 Attempt tick cost | Owner, PR-D2 (§4.3); values in the starter-content spec |
| Q3 First verb vocabulary | Rule-representation spec. This spec fixes only the compatibility verbs `gather`, `eat`, `drink`, `fill`, `rest`, `sleep` (§11.2) |
| Q4 Phenomenon vocabulary, watcher visibility | Rule-representation spec. This spec requires a watcher-visibility flag per phenomenon (§5.4) |
| Q5 Deceptive appearances | Owner, PR-D3 (§5.2); tells are defined in the rule-representation spec |
| Q6 Watching | Resolved (ADR 0007 D10); §5.4 |
| Q7 Physiology effects | Rule-representation spec |
| Q8 Process decay | World-engine spec |
| Q9 Equivalence projection and seeds | Decided here (§11.3) |
| Q10 Speech during actions | Resolved (ADR 0007 D10); §7.1 |
| Q11 Hard stops | Decided here (§4.4) |
| Q12 Sleep length | Owner, PR-D4 (§3.2) |
| Q13 Agreement terms | Owner, PR-D5 (§7.2); record format in the memory-model spec |
| ADR 0012 Q7 What wakes a sleeper | Owner, PR-D6 (§6.3) |
| CR-009 open item: v1 replay bundles in the viewer | Owner, PR-D7 (§11.1) |
| Carried to the starter-content spec | Slower hunger and thirst during sleep, starter pack only (PR-D6, §6.3); the named need thresholds of each pack and which wake a sleeper (§5.3, §6.3); the compatibility pack's map from (`rule_id`, `failed_check`) to v1 failure codes (§11.3); the durations `drop_ticks` and `inspect_ticks` (§4.2) |
| Carried to the rule-representation spec | How named need thresholds and their waking mark are declared (§5.3); condition and item-slot IDs for `failed_check` (§4.3); a verb's target kinds, target class, must-be-held flag and reach range (§4.3); tells (§5.2); the watcher-visibility flag of phenomena (§5.4) |
| Carried to the memory-formation spec | K must lie within the sleep bounds of 6–54 ticks (PR-D4) |
| Later direction, not this version | Being addressed directly wakes a sleeper (PR-D6) |

## 15. Owner decisions (2026-11-17)

The owner answered the decision sheet on 2026-11-17. Each answer is applied in
the section named.

| ID | Question | Owner decision | Applied in |
|---|---|---|---|
| PR-D1 | What does a resident know at birth? (ADR 0007 Q1) | Drives and verbs only: it feels hunger and thirst and may try `eat` or `drink` with anything; which items work is learned. Recommended option, accepted | §3.3 |
| PR-D2 | What does an unmet or unmatched attempt cost? (ADR 0007 Q2) | A per-verb `attempt_ticks`, at least 1; a matched rule takes its `work_ticks`. Recommended option, accepted | §4.3 |
| PR-D3 | Does `inspect` see through a deceptive appearance? (ADR 0007 Q5) | No: `inspect` reports apparent values and only use reveals the truth. The owner added that a newcomer cannot recognize a deception but an experienced resident can. Recognition lives in memory: the true material identity is always shown, and an instance-level override needs a tell | §5.2 |
| PR-D4 | Sleep length bounds (ADR 0007 Q12) | 1 to 9 hours: `duration_ticks` from 6 to 54. The owner changed the recommended 6–72 | §3.2 |
| PR-D5 | Agreement terms (ADR 0007 Q13) | Four kinds (`give_item`, `return_item`, `be_at`, `contribute`); optional `due_tick`, required for `be_at`; a return is the same item instance; both parties get a mechanical record. Recommended option, accepted | §7.2 |
| PR-D6 | What wakes a sleeper besides the end of its chosen duration? (ADR 0012 Q7) | Hunger or thirst reaching the critical band; speech does not wake in this version. The owner added two directions: hunger and thirst fall more slowly during sleep (starter pack), and being addressed directly wakes a sleeper in a later version | §6.3 |
| PR-D7 | Should the viewer keep loading v1 replay bundles after the v1 code is removed? (CR-009) | No: v1 runs are viewed at the archive tag. Recommended option, accepted | §11.1 |

The spec goes to Gate 2 with these answers.
