# Living Island — Interface Contract v0.1

> **Approved v0.1 (2026-11-08).** Rules and semantics are frozen. Numeric values in
> `content/worlds/default.toml` are candidates to be tuned in P2 without changing this spec.
> `Perception`, `ActionPlan`, `ActionIntent`, `ActionResult` and `DecisionTrigger` are frozen
> unless the agent-interface spec requires a change, which must go through a spec amendment task.
> `DecisionContext` remains provisional.

**Conventions:** JSON-shaped field lists below are normative **field descriptions, not Python/TypeScript code**. Types use `string`, `integer`, `boolean`, `null`, `array<T>` and `object{...}`; optional fields are marked `?`. Physical values must be integers.

## 1. DTO boundaries and identity

- `WorldState` is authoritative and backend-private; no frontend or model receives it wholesale.
- `Perception` is built by **`world`**, physical and filtered; never contains memory IDs, beliefs, goals or subjective remembered resource status.
- `DecisionContext` is assembled by **`agents`**: `Perception` + the one resident's memory, beliefs, values and goals. It is never sent to world settlement.
- `ActionPlan` and `ActionIntent` are proposals, not state changes. `ActionResult` has an authoritative internal form and a filtered actor-visible feedback form.
- Event IDs, intent IDs, run IDs, plan IDs, utterance IDs and entity IDs are **strings**; tick, event sequence, counts, coordinate and condition values are **integers**.
- Coordinates always have shape `object{x:integer,y:integer}`; the TOML content's `[x,y]` is a different configuration syntax and must be converted explicitly.

## 2. JSON-shaped core field lists

### 2.1 `WorldState` (backend only; saved by persistence)

```text
WorldState {
  schema_version: string,
  world_id: string, run_id: string, tick: integer,
  config_hash: string, map_hash: string,
  static_map_ref: string,
  residents: array<ResidentPhysicalState>,
  fruit_nodes: array<{id:string, position:Coord, stock:integer, regrow_phase_offset_ticks:integer}>,
  cave: Coord, spring: Coord, cues: array<{id:string,kind:string,position:Coord}>,
  ground_fruit: array<{position:Coord,quantity:integer}>,
  lifetime_fruit_regrown:integer, lifetime_fruit_consumed:integer,
  unique_canteen: {id:string, holder_id:string|null, ground_position:Coord|null, servings:integer},
  corpses: array<{id:string,resident_id:string,position:Coord,death_tick:integer}>,
  dialogue_sessions:array<{pair_ids:array<string>,turn_count:integer,last_utterance_tick:integer,cooldown_until_tick:integer}>,
  active_actions: array<ActiveAction>,
  explored_tiles_by_resident: array<{resident_id:string,tile_indices:array<integer>}>,
  exposure_receipts_by_resident: array<{
    resident_id:string,
    entities:array<{entity_id:string,entity_type:EntityType,position:Coord}>,
    cue_detail_seen:array<{cue_id:string,detail_level:"distant"|"near"}>
  }>,
  resolution_rng_state_uint32: integer,
  next_event_seq_in_tick: integer, event_log_cursor: integer,
  rule_overrides: object{}
}
ResidentPhysicalState {
  id:string, position:Coord, alive:boolean,
  satiety:integer, hydration:integer, stamina:integer, health:integer,
  fruit_count:integer
}
ActiveAction {
  intent:ActionIntent, // complete immutable intent, including target and parameters
  tick_started:integer, elapsed_ticks:integer, remaining_ticks:integer|null,
  route:array<Coord>|null, route_cursor:integer|null,
  pending_failure_code:string|null
}
```

`explored_tiles_by_resident` is objective visibility history of **static tiles** (`index = y * map.width + x`, sorted ascending), not remembered stocks. Exposure receipts contain only actually exposed entity references/positions and cue detail levels; they never contain stock history or interpretations and are backend-private. Seed receipts from initial Perception, and update them from actual later sightings and each boundary's own identity/inventory exposure (including a newly received canteen). An actor must have a receipt for an entity-ID target; `pick_up` requires an item-type receipt at its target tile. Missing receipt is `INVALID_TARGET`, checked before looking up remote live state. All ordinary legality checks still apply. Queued plans contain only **unstarted** intents and are stored in the *sim/agent save section*. Active actions save complete intents independently of those queues.

### 2.2 `Perception` — world-owned, physical, filtered

```text
Perception {
  schema_version:string, actor_id:string, tick:integer,
  own_condition:{
    satiety:NeedBand, hydration:NeedBand,
    stamina:NeedBand, health:NeedBand
  },
  own_position:Coord,
  own_inventory:{fruit_count:integer,canteen_id:string|null,canteen_servings:integer|null},
  visible_tiles:array<{position:Coord,terrain:Terrain}>,
  visible_entities:array<{
    entity_id:string,
    entity_type:EntityType,
    position:Coord,
    observable_signs:array<VisibleSign>,   // residents only; [] otherwise
    fruit_band:FruitBand|null,             // fruit_tree only
    quantity:integer|null                  // ground_fruit only: exact count of the pile
  }>,
  transient_sightings:array<{              // last intermediate sighting per entity ID,
    entity_id:string,entity_type:EntityType, // not visible from the tick-end position
    position:Coord,seen_at_step:integer,
    observable_signs:array<VisibleSign>,
    fruit_band:FruitBand|null,quantity:integer|null
  }>,
  explored_static_tiles:array<{position:Coord,terrain:Terrain}>,
  environmental_cues:array<{
    cue_id:string,position:Coord,detail_level:"distant"|"near",
    physical_description:string,direction:string|null
  }>,
  heard_utterances:array<{
    utterance_id:string,speaker_id:string,addressee_id:string,
    speech_act:SpeechAct,text:string,request_item_type:string|null,
    request_quantity:integer|null,in_reply_to:string|null,
    heard_at_tick:integer
  }>,
  last_action_feedback:ActionFeedback|null
}
```

`Perception` never includes another person's exact health/needs, future fruit growth, hidden spring coordinate, full event log, entire map, beliefs/goals or arbitrary historical dynamic resource states. The sole transient exception is the descriptor actually captured during the just-completed tick, delivered through its saved boundary packet. Never refresh that descriptor from hidden live state. `environmental_cues` includes cues observed at intermediate steps as well as at tick end, retaining the highest detail actually seen this interval; sort by cue ID. Previously explored terrain is static map data; it does not enable a remote fruit-stock query. `own_inventory` is exact because the character can inspect their possessions. World samples after each move step and at spawn/tick boundaries; remembered interpretations belong to agents.

**Entity IDs and targeting.** Fruit trees appear as `fruit_tree` entities with their configured ID (e.g. `fruit_03`) and a `FruitBand`, never an exact stock. A ground fruit pile has ID `ground_fruit@<x>,<y>` and an exact `quantity`; merge drops at one tile, remove zero-quantity piles, and reuse the spatial ID if fruit is dropped there later. A corpse has ID `corpse@<resident_id>`. A ground canteen appears as `canteen`; a carried one appears only in its holder's `own_inventory`. Every `gather`, `pick_up`, `give` and `talk` target must be an exposed reference; an agent may reuse an earlier ID, verified by the private receipts in §2.1. Own inventory authorizes `fill_canteen` for its owned ID. These permissions never bypass current reach, ownership or stock checks. Exclude self from visible entities. Transient sightings are delivered exactly once for their observed boundary, not discarded before delivery or regenerated after restore.

**Physical delivery, not memory.** After each completed tick (and at tick zero), world creates the immutable packet below for each living actor. Its Perception is filtered using that tick's observations. Sim delivers every packet before next-tick decisions, even when an ongoing action means no planner call. A delivery acknowledgment and the recipient runtime's ingestion are one checkpoint-consistent operation; save either the pending packet or the acknowledged cursor plus the ingested agent state, never an acknowledged-but-uningested packet. P1 may checkpoint only completed world boundaries and must not checkpoint in the middle of acknowledgment. Pending packets survive save/restore and are delivered before new plans. The world does not retain consumed descriptor history; retaining memories belongs to agents.

```text
BoundaryPerceptionDelivery {
  delivery_id:string,actor_id:string,observed_tick:integer,
  perception:Perception,
  decision_triggers:array<DecisionTrigger>
}
DeferredDecisionTriggers { actor_id:string,reasons:array<DecisionTrigger> }
```

`delivery_id = run_id + ":perception:" + zero-padded-10-digit-observed_tick + ":" + actor_id`. `Perception.tick` equals `observed_tick`. A packet is pending until acknowledged once. `seen_at_step` starts at 1 and resets per actor per tick. One transient entry per entity ID uses the last intermediate sample; an entity visible at tick end is excluded from that array. A packet can deliver near cue detail even if the cue is no longer visible at tick end. This is a report of actual recent observation, not omniscience.

While an actor has an active action, ingestion may accumulate deferred trigger codes but cannot replace its plan unless the interruption table terminates that action. At the next idle boundary, a nonempty deferred set requests one reevaluation and discards unstarted intents; otherwise the next queued intent starts without a new decision. Clear the deferred set only after accepting its replacement plan. Exhausted plans produce `PLAN_FINISHED`; tick zero requests the initial plan. No decision is made for dead actors.

### 2.3 `DecisionContext` — assembled and owned by agents (PROVISIONAL)

> **Provisional until the agent-interface spec (before P3).** That spec decides how a resident agent works: cognitive tools such as recall or checking the known map that cost no game time, world actions that cost ticks, and how many model turns one decision may use. P1 must not implement or depend on this structure; P1 residents (random/rule-based) consume `Perception` and emit `ActionPlan` only.

```text
DecisionContext {
  perception:Perception,
  personality_profile:{profile_id:string,values:array<string>},
  current_goals:array<{goal_id:string,text:string,priority:integer}>,
  recalled_episodes:array<{
    memory_id:string,source:"observation"|"speech"|"dream"|"reflection",
    summary:string,confidence_band:NeedBand,related_entity_ids:array<string>
  }>,
  beliefs:array<{subject:string,claim:string,confidence_band:NeedBand}>,
  current_plan_summary:string|null
}
```

This object does **not** imply that world stores the memory fields. Agent-layer retrieval, partial forgetting, relationship scores and dream integration are scoped to P4/P6.

### 2.4 `ActionPlan`, `ActionIntent`, `ActionResult`

```text
ActionPlan {
  plan_id:string,actor_id:string,created_at_tick:integer,
  intents:array<ActionIntent>  // length 1..agents.max_plan_actions
}
ActionIntent {
  intent_id:string,plan_id:string,actor_id:string,
  action_type:"move_to"|"gather"|"eat"|"drink"|"fill_canteen"|
              "rest"|"sleep"|"talk"|"give"|"pick_up"|"wait",
  target:{kind:"tile",position:Coord}|
         {kind:"entity",id:string}|
         {kind:"resident",id:string}|null,
  parameters:ActionParameters,
  reason:string|null
}
ActionResult {
  intent_id:string,actor_id:string,
  tick_started:integer,tick_finished:integer,
  status:"success"|"failure"|"interrupted",
  failure_code:string|null,
  interruption_reason:InterruptionReason|null,
  state_delta:array<{path:string,before:integer|string|boolean|Coord|null,
                     after:integer|string|boolean|Coord|null}>,
  visible_feedback:ActionFeedback,
  event_ids:array<string>
}
ActionFeedback {
  intent_id:string,status:"success"|"failure"|"interrupted",
  failure_code:string|null,interruption_reason:InterruptionReason|null,
  visible_effects:array<string>
}
```

`state_delta` is **internal, authoritative**; it must never be returned verbatim as a resident-facing field. An Agent only sees `visible_feedback`. A `reason` from an LLM is stored for debugging but cannot override preconditions. `ActionIntent` IDs must be unique within one run and stable in recorded replays.

Success has both code/reason fields null; failure has a listed failure code and null interruption reason; interrupted has null failure code and one InterruptionReason. Only one result is emitted per intent. Full intent data is present in ActiveAction even when there are no remaining queued intents. `last_action_feedback` reports this boundary's terminal result or null, never a replay of an older boundary's result. An action starting at `t` progresses first in `t -> t+1`; duration `d` finishes at `t+d`. A queued successor can start no earlier than the next tick.

**Typed `ActionParameters`:**

| Action | Required `target` | Required `parameters` (JSON shape) |
|---|---|---|
| `move_to` | `tile(position)` | `{}` |
| `gather` | `entity(fruit_tree_id)` authorized by the exposure receipts in §2.1 | `{}` |
| `eat` | `null` | `{}` |
| `drink` | `null` | `{source:"spring"|"canteen"}` |
| `fill_canteen` | `entity(canteen_id)` | `{}` |
| `rest`, `sleep`, `wait` | `null` | `{}` |
| `talk` | `resident(id)` | `{speech_act:SpeechAct,text:string,request?:{item_type:"fruit"|"canteen",quantity:integer},in_reply_to?:string}` |
| `give` | `resident(id)` | `{item_type:"fruit"|"canteen",quantity:integer}` |
| `pick_up` | `tile(position)` | `{item_type:"fruit"|"canteen",quantity:integer}` |

For `talk`: `request` is mandatory only when `speech_act=request`, `in_reply_to` mandatory only when `speech_act=accept|refuse`, neither permitted otherwise. `text` is human-readable speech, may be empty when structured act carries meaning, and has an adapter-level length cap. All request/give/pick_up quantities are positive integers; canteen quantity must be exactly 1. Fruit transfers are all-or-nothing; insufficient owned fruit is `NO_ITEM`, insufficient ground fruit is `ITEM_TAKEN`, and insufficient receiving capacity is `INVENTORY_FULL`. `fill_canteen` target must be the unique owned canteen; adjacency is validated against spring. No attempt to transfer a serving without transferring the canteen is valid.

### 2.5 Five-level descriptors and visible signs

**`Terrain` vocabulary (exact):** `sea`, `beach`, `grass`, `woods`, `rock`, `spring`, `cave`, `fruit_tree`, `damp_moss`, mapping to `~ . , W ^ S C F M` respectively. Raw map characters are not DTO values.

**`EntityType` vocabulary (exact):** `resident`, `corpse`, `fruit_tree`, `ground_fruit`, `canteen`, `cue`. The same vocabulary applies to visible entities, transient sightings and exposure receipts.

**`InterruptionReason` vocabulary and priority:** `DEATH`, `URGENT_NEED`, `DIRECT_SPEECH`, `NEW_SIGHT`, in that precedence order. For unfinished movement/gathering, zero stamina is a failure `EXHAUSTED`, after death handling but before soft interruptions; a blocked step fails `PATH_BLOCKED`. `BLOCKED` is not a second interruption spelling for that failure. Completed actions keep their completion result.

**`DecisionTrigger` vocabulary and array order:** `ACTION_FAILED`, `ACTION_INTERRUPTED`, `URGENT_NEED`, `DIRECT_SPEECH`, `NEW_SIGHT`, `UTTERANCE_HEARD`, `REPLY_REQUIRED`, `WOKE`, `PLAN_FINISHED`. Deduplicate codes and order arrays by this list. A terminal action result generates its corresponding trigger; natural plan exhaustion generates `PLAN_FINISHED`; natural sleep completion generates `WOKE`. Urgent crossing uses the authoritative condition crossing rule, not NeedBand changes. Every heard utterance generates `UTTERANCE_HEARD`; addressed speech also generates `DIRECT_SPEECH`, and an addressed request generates `REPLY_REQUIRED`. A trigger does not cancel an action unless World Rules §4.3 says it does. Deferred triggers accumulate as an ordered unique set until a new plan is requested. No model decision is requested for a dead actor.

`NEW_SIGHT` is first exposure of an entity ID or first distant-to-near cue upgrade, compared with receipts at tick start; all six types are salient, excluding self. Reappearance, changed position or changed resource band alone is not new. Initial exposures seed receipts without interrupting the first decision. This definition is a reviewable rc3 choice, not a claim that every future policy must value every sighting equally.

**`NeedBand` vocabulary (exact):** `critical`, `low`, `moderate`, `good`, `strong`. Interpret `perception.need_band_cutoffs = [a,b,c,d]`: `[min,a)` critical; `[a,b)` low; `[b,c)` moderate; `[c,d)` good; `[d,max]` strong. The very same five-level mapping applies to satiety, hydration, stamina, health and any agent-layer subjective confidence **as a convenience vocabulary only** (no numeric confidence is authoritative).

**`FruitBand` vocabulary (exact):** `empty` if stock = 0; `few` for `1..perception.fruit_few_max`; `many` above this threshold. Only visible (or transiently sighted) `fruit_tree` entities expose stock bands.

**`VisibleSign` vocabulary (exact):** `weak` when visible resident health is below `perception.visible_weakness_health_below`; `dehydrated` when hydration is below `perception.visible_dehydration_hydration_below`; `fatigued` when stamina is below `perception.visible_fatigue_stamina_below`. These are **observable signs**, not numbers, and may coexist. When no sign applies, use empty array `[]`; do not insert `none` as an extra mutually exclusive label. Corpse has `entity_type=corpse`, not a `dead` condition band.

**`SpeechAct` vocabulary (exact):** `statement`, `request`, `accept`, `refuse`. An utterance ID is the associated objective `utterance_spoken.event_id`. For accept/refuse, `in_reply_to` must reference a prior request utterance addressed to this speaker; reply addressee must be the original requester. No gift occurs from acceptance alone. A pairwise conversation session is keyed by sorted participant IDs, and the turn count / maximum / quiet gap / capped-session cooldown follow World Rules §4.2 (`social.max_dialogue_turns`, `social.dialogue_gap_ticks`, `social.dialogue_cooldown_ticks`); an over-cap attempt fails `DIALOGUE_LIMIT`.

## 3. Objective event envelope and catalog

### 3.1 Envelope

```text
WorldEvent {
  schema_version:string,run_id:string,event_id:string,
  tick:integer,seq_in_tick:integer,type:EventType,
  actor_id:string|null,target_id:string|null,
  intent_id:string|null,llm_call_id:string|null,
  caused_by_event_ids:array<string>,
  payload:object{}
}
```

`event_id = run_id + ":" + zero-padded-10-digit-tick + ":" + zero-padded-6-digit-seq`, with zero-based `seq_in_tick` inside each tick. At `tick=0`, `world_initialized` is first. At each later tick, sequence begins at zero and increases by one per emitted event. Events are written in emission order, never regrouped by type. Event causal references must point only to already-emitted IDs (never forward). For an LLM-backed intent, `llm_call_id` references a **separate call log**; deterministic IDs never contain latency or wall-clock time.

### 3.2 Exhaustive v0.1 event catalog

Fields below are **payload** fields; envelope fields are not repeated. `Coord` is `{x,y}`. All quantity/need values are integer. Fields are mandatory unless marked `?`.

| `EventType` | Payload field list | Emitter / trigger |
|---|---|---|
| `world_initialized` | `{config_hash:string,map_hash:string,initial_snapshot_hash:string}` | `sim`/world creation at tick 0 |
| `config_changed` | `{parameter:string,old_value:integer,new_value:integer,effective_tick:integer}` | permitted paused parameter edit validated at next boundary |
| `action_started` | `{action_type:string,plan_id:string,duration_ticks:integer|null}` | `world` accepts an intent |
| `action_progressed` | `{action_type:string,elapsed_ticks:integer,remaining_ticks:integer|null,route_cursor:integer|null}` | `world` updates unfinished active action at each tick |
| `resident_moved` | `{from:Coord,to:Coord,step_cost_units:integer}` | each entered tile during `move_to` |
| `action_succeeded` | `{action_type:string,result_code:"OK"}` | completion after successful final validation |
| `action_failed` | `{action_type:string,failure_code:string}` | invalid start after bounded interval; failed completion/blocked move |
| `action_interrupted` | `{action_type:string,reason:InterruptionReason}` | interruption at documented boundary with the priority in §2.5 |
| `fruit_gathered` | `{tree_id:string,quantity:integer,stock_before:integer,stock_after:integer}` | successful `gather` |
| `fruit_consumed` | `{quantity:integer,satiety_before:integer,satiety_after:integer}` | successful `eat` |
| `water_drank` | `{source:"spring"|"canteen",servings:integer,hydration_before:integer,hydration_after:integer,canteen_servings_after:integer|null}` | successful `drink` |
| `canteen_filled` | `{canteen_id:string,servings_before:integer,servings_after:integer}` | successful `fill_canteen` |
| `stamina_action_cost_applied` | `{amount:integer,reason:"gather"|"move"}` | stamina expenditure for movement/gathering at physiology phase |
| `fruit_regrew` | `{tree_id:string,quantity:integer,stock_before:integer,stock_after:integer}` | due successful regrowth after completion settlement |
| `condition_updated` | `{resident_id:string,satiety_before:integer,satiety_after:integer,hydration_before:integer,hydration_after:integer,stamina_before:integer,stamina_after:integer,health_before:integer,health_after:integer}` | per-tick combined physiology change; may include rest/sleep gains |
| `utterance_spoken` | `{utterance_id:string,addressee_id:string,speech_act:SpeechAct,text:string,request:{item_type:string,quantity:integer}|null,in_reply_to:string|null}` | successful `talk`; `utterance_id` equals this event's event ID |
| `utterance_heard` | `{utterance_id:string,listener_id:string}` | each awake in-range listener other than speaker at settlement; including non-addressee |
| `item_given` | `{from_id:string,to_id:string,item_type:"fruit"|"canteen",quantity:integer,canteen_id:string|null}` | successful `give` |
| `item_picked_up` | `{resident_id:string,position:Coord,item_type:"fruit"|"canteen",quantity:integer,canteen_id:string|null}` | successful `pick_up` |
| `resident_died` | `{resident_id:string,position:Coord,cause:"DEPRIVATION"}` | health reaches minimum |
| `corpse_created` | `{corpse_id:string,resident_id:string,position:Coord}` | death transition |
| `item_dropped` | `{resident_id:string,position:Coord,item_type:"fruit"|"canteen",quantity:integer,canteen_id:string|null,canteen_servings:integer|null}` | death inventory transfer to ground |
| `exploration_updated` | `{resident_id:string,newly_seen_tile_indices:array<integer>}` | new visible static terrain entered explored footprint; sorted indices |
| `agent_fallback_used` | `{resident_id:string,reason:"TIMEOUT"|"PARSE_ERROR"|"BUDGET"|"PROVIDER_ERROR",fallback_policy_id:string}` | `sim` selects rule-based policy at decision boundary |
| `god_intervention_recorded` | `{intervention_id:string,recipient_id:string,kind:"dream"|"faint_thought",transcript_retained:boolean}` | player-authorized intervention metadata; no semantic text injected into world |

**Event ordering within one operation:** `action_started` precedes `action_progressed`; physical effect event (e.g. `fruit_gathered`, `utterance_spoken`) precedes `action_succeeded`; death emits `resident_died`, `corpse_created`, then `item_dropped` entries ordered (`fruit`, then `canteen`). `utterance_heard` immediately follows its `utterance_spoken`, sorted by listener ID; listening delivery is queued for the next decision boundary and does not depend on a later world tick. `condition_updated` precedes `resident_died` if the latter resulted from condition decline. Duplicate facts must not be emitted from `events` and `persistence`: events are created once by world/sim and written once by persistence.

Events that expose exact needs, inventories or private debug data are **not** delivered wholesale to resident models. `Perception` filters objective events into the allowed `heard_utterances` and `last_action_feedback` fields.

## 4. Failure-code catalog

`DEAD`, `EXHAUSTED`, `INVALID_TARGET`, `PATH_BLOCKED`, `NO_PATH`, `OUT_OF_REACH`, `RESOURCE_TAKEN`, `INVENTORY_FULL`, `NO_ITEM`, `NO_NEED`, `NO_WATER`, `ALREADY_FULL`, `OUT_OF_HEARING`, `INVALID_SPEECH_ACT`, `INVALID_REPLY`, `DIALOGUE_LIMIT`, `ITEM_TAKEN`. Invalid plan JSON / model timeout are **agent-adapter** failures (recorded in the call log and `agent_fallback_used`), not fake world action failures. An invalid parameter shape becomes a bounded action failure `INVALID_TARGET` or the most specific listed code, not an uncaught exception.

## 5. Snapshot, model-call log and persistence boundaries

```text
SavePackage {
  save_schema_version:string,
  world:WorldState,
  agent_state:{
    profiles:array<object{}>,goal_states:array<object{}>,
    personal_memories:array<object{}>,relationships:array<object{}>,
    queued_plans:array<ActionPlan>, // unstarted intents only; active intent lives in world
    deferred_decision_triggers:array<DeferredDecisionTriggers>,
    delivered_perception_ticks:array<{actor_id:string,last_observed_tick:integer}>
  },
  event_cursor:integer,
  llm_record_cursor:integer,
  pending_perception_deliveries:array<BoundaryPerceptionDelivery>,
  canonical_config_hash:string,canonical_map_hash:string
}
LLMCallRecord { // separate recording JSONL, not WorldEvent
  call_id:string,actor_id:string,tick:integer,
  prompt_version:string,model_name:string,
  decision_context:DecisionContext,
  raw_response:string,parsed_plan:ActionPlan|null,
  outcome:"ok"|"parse_error"|"timeout"|"provider_error",
  token_input:integer|null,token_output:integer|null,
  latency_ms:integer|null // diagnostic; excluded from deterministic comparison
}
```

`persistence` is the only filesystem writer (snapshots via atomic replacement, world events append to JSONL, model calls append to another JSONL). World uses no IO libraries. JSON snapshots can restore only on completed tick boundaries, including pending active-action progress and pending deliveries. Runtime editable parameters require their own explicit `config_changed` events. A UI playback rehydrates a display projection from event records; an authoritative re-execution recomputes world state using recorded decisions.

At the end of tick `k`, every living actor has one packet for `k` pending until delivery; tick-zero initialization follows the same rule. `delivered_perception_ticks` starts at -1 per actor and advances monotonically after ingestion. An actor cannot acknowledge tick `k` twice. Snapshot the pending packets verbatim; do not rebuild transient observations from WorldState on restore. Runtime rule edits are disabled in P1 (`rule_overrides={}`); the `config_changed` event is reserved for the later explicitly permitted parameter list. No implementer may choose editable parameters during P1.

## 6. Determinism appendix

### 6.1 Forbidden nondeterminism in authoritative flow

No wall-clock time, real timestamps, UUID generation, globally shared random calls, unordered dict/set iteration, object memory addresses, locale-dependent sorting, platform-dependent floating-point arithmetic, `NaN`/Infinity, browser/renderer state or unrecorded model decisions may affect authoritative actions, order, resources, event payloads or deterministic identifiers. Networking latency and token/cost measurements may be saved as **diagnostics only** in LLMCallRecord; they are not replay equality targets.

### 6.2 Ordering and integer constraints

- All simulated time, coordinates, health/needs, durations, counters, phases, step costs and amounts are integers. Divide only with specified integer operations; do not silently round floats.
- Residents are processed in ascending UTF-8 ID order where the World Rules Spec calls for actor order; positions/tiles are sorted by `(y,x)`, entity IDs by ascending ID. For serialized WorldState arrays: residents/fruit nodes/corpses/exploration groups/receipt groups sort by ID; receipt entities by `(entity_id,position.y,position.x)` with unique triples; cue details by cue ID; dialogue sessions sort by their ordered pair IDs; active actions by `(intent.actor_id,intent.intent_id)`; ground fruit by `(y,x)`; tile indices ascending; event causal references preserve creation order. Visible/transient entities sort by entity ID, visible signs by `weak,dehydrated,fatigued`, and environmental cues by cue ID. Boundary packets sort by `(observed_tick,actor_id)`; delivery cursors and deferred-trigger groups by actor ID, trigger codes by §2.5. Plan intents preserve submitted order. Need bands use strict ordered integer cutoffs.
- Dijkstra uses the queue key `(total_cost,y,x)`, neighbor order `N,E,S,W`, and replaces a predecessor only on a strictly lower cost (World Rules §5.3, with its two test vectors). Bresenham and per-step visibility match the World Rules Spec exactly.
- All completions first sort `(actor_id,intent_id)` then a single Xorshift32-based Fisher–Yates shuffle; no other system consumes `resolution_rng`.
- Regrowth offsets are per-tree and do not consume RNG. Objective causal links are ordered by event emission sequence. Fruit drop order is `fruit`, then canteen.
- Event `seq_in_tick` starts at zero, increments by one for each emission; `event_id` is a deterministic string. No producer may independently allocate event IDs outside the append coordinator.

### 6.3 Canonical encoding and byte-identical replay

Authoritative snapshot and WorldEvent JSONL use **UTF-8 without BOM, LF line endings, JSON object keys sorted lexicographically, no insignificant whitespace, JSON escaping determined by `ensure_ascii=false`, and integral numeric literals only** (e.g. Python-equivalent `sort_keys=True, separators=(',',':'), ensure_ascii=False, allow_nan=False`). Each JSONL record ends in exactly one `\n`. JSON array order is normative: each collection has a documented sort order, and model-supplied ordered plans retain authored order. Empty arrays stay `[]`, nulls stay JSON `null`; no runtime-dependent field omission.

**“Byte-identical replay” means:** given an identical completed-tick save package, canonical effective config and map, exact persisted `resolution_rng` state, identical ordered player commands, and **recorded** LLM decisions (no fresh calls), re-execution produces (1) an identical canonical authoritative `WorldState` snapshot at every compared checkpoint and (2) identical bytes for the corresponding objective `WorldEvent` JSONL segment. It does **not** mean identical web UI pixels, logging timestamps, provider latency, token-use diagnostics, or raw response streaming boundaries. The recorded LLM `parsed_plan`, not an unrecorded fresh model call, supplies each decision.

Config identity is SHA-256 of the canonical parsed typed TOML configuration (object keys sorted, arrays in declaration order); map identity is SHA-256 of the canonical UTF-8 `map.width`×`map.height` map bytes including final LF. The run ID is configured and stable. If the replay starts after a saved event cursor, compare only the segment after that cursor, not the entire historical file.

## 7. Clarifications required before implementation freeze

- This contract enumerates fields and vocabularies but does not generate production Pydantic or TypeScript code. Those implementations must be reviewed separately.
- Decisions about memory retrieval heuristics, whether dream transcripts are retained in production, optional herbivore behavior and a provider-specific timeout are not frozen by this file.
- This version does not assert success rates or performance numbers; seven-day viability is a future measured acceptance result.
