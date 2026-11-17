# Living Island — World–Agent Protocol v0.1 (P3.5 v2 lane)

> **Draft (2026-11-17), task P3.5-PR-02. Not frozen.** The owner answered the
> decision sheet on 2026-11-17 (§15). Gate 2 has not run.
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

### 3.2 `Intent`

```text
Intent {
  intent_id:string, turn_id:string, actor_id:string,
  action:"move_to"|"give"|"pick_up"|"drop"|"wait"|"inspect"|"contribute"|"act",
  verb:VerbId|null,                        // required for act, null otherwise
  target:Target|null,
  instruments:array<ItemRef>,              // act only; used, not consumed
  inputs:array<{ref:ItemRef,quantity:integer}>, // act only; consumed
  params:object{},                         // closed shape per action or verb
  reason:string|null                       // debugging only; never affects settlement
}
Target   = {kind:"tile",position:Coord} | {kind:"entity",id:string} | {kind:"resident",id:string}
ItemRef  = {kind:"item",id:string}
```

Kernel action shapes:

| `action` | `target` | `params` | Meaning |
|---|---|---|---|
| `move_to` | `tile` | `{}` | Walk to a tile, as v1 |
| `give` | `resident` | `{item:ItemRef,quantity:integer}` | Move a held item to an adjacent resident |
| `pick_up` | `entity` (an item on the ground, in a container or in a process entity) | `{quantity:integer}` | Take an item into the inventory |
| `drop` | `tile` (own or adjacent) or `entity` (a container or process entity) | `{item:ItemRef,quantity:integer}` | Put a held item down or into something |
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

1. **Agents (shape).** Known action; target kind allowed; `params` match the
   closed shape; `verb` is in the vocabulary and present only for `act`;
   quantities positive; no item listed twice; `continue` only with a running
   action; utterance shape (§7.1). A failure is `INVALID_TURN`, an agent-side
   error recorded in the call log. It never reaches the world (as v1
   `INVALID_PLAN`, CR-001).
2. **World (state).** Kernel preconditions (§4.2) and generic `act`
   preconditions (§4.3), then rule settlement for `act`.

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
    kind:"applied"|"chance_failed"|"unmet"|"unmatched"
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

### 4.3 Generic `act` preconditions

Checked by the world before rule matching, in this order. The first failure
ends the attempt with its code after `invalid_attempt_ticks`, as v1 does for an
action invalid at start (`world-rules-v0.1.md` §4.1):

1. The actor is alive (`DEAD`).
2. Every reference has a receipt (`INVALID_TARGET`).
3. Every instrument and input is held in the stated quantity (`NO_ITEM`).
4. The target is within the verb's declared reach (`OUT_OF_REACH`). Each verb
   declares its reach in the vocabulary: same tile, adjacent, or none.

Everything else (properties, actor state, surroundings, time) belongs to rule
conditions and is reported only as phenomena. Settlement order and chance
rolls follow ADR 0009 D1 and the world-engine spec.

**Tick cost.** A matched rule takes its `work_ticks`. An unmet or unmatched
attempt takes the verb's `attempt_ticks`, declared per verb in the vocabulary
and at least 1 (owner, PR-D2). Every attempt that passes §4.3 costs at least
one tick (ADR 0007 D5). The values are content (starter-content spec).

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
- A resident that chooses another action stops the running one at the next
  boundary: `stop = {by:"actor"}`, feedback `stop_reason = "own_choice"`.
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
  last_action_feedback:ActionFeedback|null,
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
- While `awareness` is not `awake`, `visible_tiles`, `visible_entities`,
  `transient_sightings`, `environmental_cues`, `heard_utterances` and
  `observed_actions` are empty. `needs`, position and inventory stay.
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
  reports:array<WorldReport>               // ordered by kind (list below), then subject ID
}
WorldReport {
  kind:"action_ended"|"need_band_changed"|"utterance_heard"|"entity_first_seen"|
       "action_observed"|"progress_step"|"woke",
  subject_id:string|null,                  // intent, need, utterance, entity or process ID
  addressed:boolean|null,                  // utterance_heard only
  band:NeedBand|null                       // need_band_changed only: the new band
}
```

- `delivery_id`, packet pending and acknowledgement, and checkpoint rules are
  as in v1 (`interface-contract-v0.1.md` §2.2, "Physical delivery, not
  memory"). Pending packets survive save and restore.
- Reports are facts about this boundary, not instructions. The world never
  marks a report as urgent and never asks for a turn. The harness maps reports
  to notification classes and turns (decision-loop spec, ADR 0013 D3).
- `need_band_changed` is reported whenever a need band changes. The critical
  band for hunger or thirst is the case the harness may not mute.
- `progress_step` is reported when the progress descriptor of the actor's
  running action or of a process entity it contributes to changes. Progress is
  never reported every tick (ADR 0013 D3).
- `entity_first_seen` follows the v1 `NEW_SIGHT` exposure rule
  (`interface-contract-v0.1.md` §2.5).
- `DecisionTrigger`, deferred trigger sets and `InterruptionReason` do not
  exist in v2.

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
- It sees who acted, the action or verb, the target, the visible items used
  and the phenomena that the vocabulary marks as visible to watchers. It never
  sees `rule_id`, the settlement kind, true values, `on_inspect` values or the
  actor's own feedback.
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
  hunger or thirst reaches the critical band. Nothing else wakes it in this
  version; speech does not, as in v1 (owner, PR-D6). An early wake stops the
  sleep with `WOKEN`.
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
- A failed utterance produces no `utterance_spoken` event. Its failure code
  reaches the speaker in `last_utterance_feedback`; the action is unaffected.

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
| `act_settled` | `{verb, rule_id:string|null, kind:"applied"|"chance_failed"|"unmet"|"unmatched", phenomena:array<string>}` | An `act` settles |
| `attempt_unmatched` | `{verb, descriptor:AttemptDescriptor}` | Right after `act_settled` with `kind = "unmatched"` |
| `resident_moved` | as v1 | Each entered tile |
| `item_transferred` | `{item_id, archetype_id, quantity, from:{kind,id}, to:{kind,id}, via:"give"|"pick_up"|"drop", owner_before:string|null, owner_after:string|null}` | A kernel transfer succeeds |
| `entity_inspected` | `{entity_id, descriptors}` | An `inspect` completes |
| `action_observed` | `{observer_id, actor_id, observed_intent_id}` | A watcher receives an `ObservedAction` |
| `utterance_spoken` | `{utterance_id, addressee_id:string|null, speech_act, text, terms:object|null, in_reply_to:string|null}` | An utterance passes validation |
| `utterance_heard` | `{utterance_id, listener_id}` | Each listener, sorted by listener ID, right after `utterance_spoken` |
| `agreement_accepted` | `{agreement_id, proposal_id, acceptance_id, terms}` | Right after the accepting `utterance_spoken` |
| `exploration_updated` | as v1 | New static tiles enter a resident's explored footprint |
| `resident_fell_asleep` | `{resident_id, duration_ticks}` | A sleep starts |
| `resident_woke` | `{resident_id, early:boolean}` | A sleeper wakes |
| `resident_fainted` | `{resident_id}` | Mental fatigue reaches its maximum |
| `resident_died`, `corpse_created` | as v1 | Death |
| `rule_added` | `{rule_id, content_hash, provenance}` | A rule is added at a boundary (ADR 0009 D5) |
| `agent_fallback_used` | `{resident_id, turn_id, reason, fallback_policy_id}` | `sim` uses the fallback policy for a turn (ADR 0013 D7) |

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
interrupts of `world-rules-v0.1.md` §4.3 on its own side (ADR 0007 D8).

| v1 intent | v2 submission |
|---|---|
| `move_to` | `move_to`, same tile |
| `gather` tree | `act` verb `gather`, target the tree entity |
| `eat` | `act` verb `eat`, input one unit of the held fruit stack |
| `drink {source:"spring"}` | `act` verb `drink`, target the spring |
| `drink {source:"canteen"}` | `act` verb `drink`, instrument the held canteen |
| `fill_canteen` | `act` verb `fill`, instrument the canteen, target the spring |
| `rest` | `act` verb `rest` |
| `sleep` | `act` verb `sleep`, `duration_ticks` = v1 `sleep_ticks` |
| `talk` | an utterance plus `wait`; the compatibility pack sets `wait_ticks` = `talk_ticks`, checked at load |
| `talk` `request` | `propose` with the addressee as promisor and `give_item` to the speaker |
| `give`, `pick_up`, `wait` | the kernel action of the same name |

For the timings to match, the compatibility pack sets the `attempt_ticks` of
each compatibility verb to the v1 `invalid_attempt_ticks`, checked at load: a
v1 start failure that becomes an unmet rule then takes the same time.

The perception adapter maps v2 `Perception` and reports to the v1
`Perception` and triggers that the policy reads: need bands by need ID, fruit
stacks to `fruit_count`, the canteen item to `canteen_id` and servings, fruit
trees to `fruit_band`, and reports to v1 `DecisionTrigger` codes.

### 11.3 Equivalence projection

Compared per tick, against the committed v1 fixtures:

- each resident: position, alive, the four need values (exact integers),
  fruit count, and canteen holding and servings;
- each fruit tree's stock, each ground fruit pile, the canteen's place and
  servings, and corpses;
- the ordered list of utterances (tick, speaker, addressee, speech act, text,
  request terms);
- the ordered list of action outcomes per resident, mapped: v1 `success` to
  `success` or `act_settled` `applied`; v1 `failure` with a dropped code to the
  matching `unmet` settlement; v1 `interrupted` to `stopped` by the actor
  (the rule-based policy's own interrupt); v1 `EXHAUSTED` and `PATH_BLOCKED`
  during an action to the hard stops of the same name.

Seed set: the P2 acceptance matrix (`p2-experiments-v0.1.md` §1–§2), same
seeds and horizon. Event IDs and byte equality are not compared, because the
event catalog changes (ADR 0007 D8).

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
| WAP-01 | For one `act` set up four ways (applied, chance failed, unmet, unmatched), `ActionFeedback` differs only in `phenomena`; `settlement` and `rule_id` appear only in `ActionResult` and events |
| WAP-02 | `continue` with no running action is `INVALID_TURN` in agents and reaches no world port |
| WAP-03 | An utterance on a turn with `continue` is heard at `t+1`, and the running action's progress and end tick are unchanged |
| WAP-04 | Two hard stops at one boundary report the higher one (§4.4); a completed action is never failed afterwards |
| WAP-05 | An actor's new intent stops the running action at the next boundary with `by: "actor"`, and the rule's `on_interrupt` applies |
| WAP-06 | A material with an apparent value shows it in perception, while settlement uses the true value |
| WAP-07 | `inspect` returns `on_inspect` descriptors; they never appear in later `EntityView`s |
| WAP-08 | A watcher in sight receives `ObservedAction` with watcher-visible phenomena only; a resident out of sight receives none; neither sees `rule_id` or true values |
| WAP-09 | `propose` then `accept` emits `agreement_accepted`; `accept` without a matching proposal is `INVALID_REPLY`; a second answer to one proposal fails |
| WAP-10 | A resident picks up an item owned by another; the world allows it, and `item_transferred` records both owners |
| WAP-11 | Adding a rule to the library leaves `action_schema_sha256` unchanged; adding a verb changes it |
| WAP-12 | `TurnSubmission` has no field for intention, mute list, citations or context pressure, and settlement is identical whatever the agent-side state |
| WAP-13 | A DTO with an unknown `schema_version` is refused |
| WAP-14 | While asleep, perception holds needs, position and inventory only, and the sleeper receives no utterance |
| WAP-15 | The compatibility pack with the rule-based policy matches the committed v1 projections on the seed set (§11.3) |
| WAP-16 | Replaying a recorded run from its submissions makes no model call and reproduces the event log byte for byte |
| WAP-17 | A deceptive material is shown with its true `material_id` and its apparent values, both on sight and on `inspect`; perception is identical for a resident that has used it before and one that has not |
| WAP-18 | A sleeper wakes at the end of `duration_ticks` or when hunger or thirst becomes critical, and is not woken by speech; a `duration_ticks` outside 6–54 is `INVALID_TURN` |

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
| Carried to the starter-content spec | Slower hunger and thirst during sleep, starter pack only (PR-D6, §6.3) |
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
