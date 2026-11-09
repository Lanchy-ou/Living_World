# Living Island — World Rules Spec v0.1

> **Approved v0.1 (2026-11-08).** Rules and semantics are frozen. Numeric values in
> `content/worlds/default.toml` are candidates to be tuned in P2 without changing this spec.
> `Perception`, `ActionPlan`, `ActionIntent`, `ActionResult` and `DecisionTrigger` are frozen
> unless the agent-interface spec requires a change, which must go through a spec amendment task.
> `DecisionContext` remains provisional.

**Repository path:** `docs/spec/world-rules-v0.1.md`  
**Companion files:** `content/worlds/default.toml`, `content/worlds/default-island.map`, `docs/spec/balance-notes-v0.1.md`, `docs/spec/interface-contract-v0.1.md`.

**Separation of concerns:** This specification defines mechanics, invariants, algorithms, data ownership and parameter names. Tunable values are in TOML; their initial values and rationale are in Balance Notes. This is not an implementation request.

## 0. Decisions, scope and ownership

### 0.1 Confirmed product direction

1. **Moderate survival pressure:** good decisions can keep three residents alive over the seven-day acceptance run, but mismanagement can cause death. No scripted rescue.
2. **One unique canteen:** it starts in one resident's inventory, can be passed physically and supports journeys away from the sole spring.
3. **Three newly acquainted shipwreck survivors:** they know each other's names and the cave area, but not remote resources; their profiles and goals differ. Initial interpersonal attitudes are neutral *in the agent-layer initialization*, not tracked as a world rule.
4. **Persistent deaths:** a corpse remains, inventory moves to ground, and other characters only learn of death by perception or testimony.
5. **Autonomous world:** fixed steps, finite perception, three independently controlled LLM residents at end acceptance, rule-based resident baseline/fallback, consequential social interaction, memory, limited dream intervention, real-event narrative, and save/restore.
6. **Water opening:** the spring's precise location is initially unknown; a real, local environmental cue suggests a direction but does not supply coordinates (approved after the first review).

### 0.2 Candidate engineering defaults, subject to review and testing

Two resource types (fruit and water), one hand-authored 64×64 map at ~50 m per tile (an island of roughly 2.5–3 km across), no carnivore/combat, optional single herbivore later; the canteen is the only tool. rc3 retains rc2 geometry and walking speed, but lowers the candidate hydration decay to 100 per tick. Canteen value is measured by avoided dedicated water trips, longer multi-stop journeys and physical water delivery to companions, not by making cave sleep mandatory or making nonholders die. Outdoor sleep may already restore full stamina; the cave bonus is capped and is not a guaranteed incentive. World settlement is single-threaded; LLM planning is synchronous and freezes simulated time. No construction, trade economy, theft, multiplayer or speculative narrative. All numeric balances and the tile scale are **proposals**, not additional product approvals. Map size, speed and hydration must not all be retuned in the same comparison.

### 0.3 Module boundaries (normative)

- **`world`** owns authoritative physical state, exploration footprints, line of sight, action legality, movement, event facts and `Perception`. It MUST NOT import `agents`, `memory`, `persistence`, rendering, networking or any LLM SDK.
- **`agents`** builds `DecisionContext` from a `Perception` plus that character's own memory, beliefs and goals. Rule-based and LLM policies output the same `ActionPlan` / `ActionIntent` schema; neither can mutate `WorldState`.
- **`memory`** owns personal episodic memory and relationship interpretation; objective facts do not automatically become trust scores. A physical gift/refusal/request is recorded by the world; its psychological meaning is agent-layer work at P4.
- **`sim`** coordinates tick boundaries, decisions, recorded LLM responses, commands and checkpoints; it never edits authoritative world state by bypassing `world`.
- **`events`** ~~defines immutable factual event records and~~ **[A1]** re-exports the immutable factual event records and provides read-only in-memory projections; **`persistence` alone** performs JSON snapshot/JSONL file IO. **`contract`** defines serialization DTOs consumed by frontend and debugging tools.
- **[A1] Event-type ownership.** The canonical `WorldEvent` envelope, every payload model, the `EventType` vocabulary and event-ID formatting live in `world` (`world/facts.py`), and only the world engine allocates event IDs. `events` re-exports and projects them read-only and allocates nothing; `world` still imports no other `living_island` subpackage (implementation plan §2.1).

## 1. Map, physical scale and authored input

### 1.1 Scale, positions and terrain

`(x,y)` are integers with `(0,0)` at top left; x grows east, y grows south. `map.width` and `map.height` specify dimensions. Each tile represents an approximately square land patch of side `map.tile_size_m`; `map.tile_meaning` documents the interpretation. **Tile size is not tick length.** Orthogonal adjacency means Manhattan distance `|dx|+|dy| <= 1` (including same-tile for item access). No diagonal movement.

The plain-text `.map` format is precisely defined in §1.2. To enter a tile, movement consumes *integer path cost units* defined by `map.step_cost_*`. A walking resident has `map.walk_cost_budget_per_tick` units to spend each simulation tick, so one tick may traverse several tiles. Travel is performed as actual, adjacent tile steps; each entered tile has a movement event, and the last entered position becomes authoritative at the tick boundary. No instant position assignment to a distant target. If the next tile's cost exceeds remaining budget, wait for the next tick; unused budget is not carried over.

Sight radius and hearing radius are in **tiles**, derived from this physical scale; they are not walking-time radii. `perception.hearing_radius_tiles` applies to clearly spoken outdoor speech (not whispering). The resulting effective radius is an approximation appropriate to the small first prototype.

Reject invalid content at creation, not during play: dimensions, tile size, movement budget, each action duration, regrowth period, inventory capacity and plan limit must be positive integers; each passable entry cost must be in `1..map.walk_cost_budget_per_tick`. `needs.min_value` is 0; maximum is positive; initial conditions and urgent/recovery/sign thresholds are within bounds; decay/cost/gain rates are nonnegative. Need-band cutoffs are four strictly increasing interior values. Initial stock/servings are within their nonnegative capacities, seed is in `1..2^32-1`, phases are in `0..fruit.regrow_ticks-1`, initial canteen owner is a configured resident, and IDs/marker positions are unique in their respective domains. Tick minutes divide 1440; start hour is in `0..23`, and `0 <= day_start_hour < day_end_hour <= 24`. Perception radii are nonnegative integers. Physical configuration contains no floats.

### 1.2 `.map` file grammar, underlying terrain and validation

- UTF-8, no BOM, LF (`\n`) line endings. Exactly `map.height` nonempty rows; each row is exactly `map.width` ASCII characters. No headers, comments, blank lines, tabs or trailing spaces. Top-left character is `(0,0)`.
- Allowed characters: `~` sea (impassable); `.` beach (passable); `,` grass (passable); `W` woods (passable, slow, opaque); `^` rock (impassable, opaque); `S` spring (impassable, interactive from adjacent tile); `C` cave (passable shelter); `F` fruit-tree patch (passable **underlying woods**, opaque; applies `map.step_cost_fruit_tree`); `M` damp-moss patch (passable **underlying grass**, clear; applies `map.step_cost_damp_moss`). Thus an `F` amid grass is still a wooded patch — never infer the underlying terrain from neighbors.
- Exactly one `S`, one `C`, one `M`; one `F` for each configured `[[world.fruit_trees]]`, with a one-to-one coordinate match. The `world.spring`, `world.initial_cave` and `[[world.cues]]` coordinates must match the respective symbols. All resident spawns must be on passable tiles. The map border is ocean in this scenario. Resource placements, cues and the initial canteen inventory come from content; fruit inventories start empty (§2). Never generate unconfigured resources randomly at runtime.
- `M` is an **actual visual landmark**, not a hidden objective waypoint. At normal line of sight it looks like a dark, wet-looking patch; when the character is within `perception.cue_detail_radius_tiles` and has line of sight, the detailed physical clue indicates an eastward damp drainage trace. This implies a possible water source but never gives `world.spring` coordinates or certainty. Once seen, a character may share their impression through `talk`; whether they believe it or remember it belongs to `agents`/`memory`.
- The nine normative `terrain` values exposed by Perception are `sea`, `beach`, `grass`, `woods`, `rock`, `spring`, `cave`, `fruit_tree`, `damp_moss`, mapping respectively to `~ . , W ^ S C F M`. These are tile classifications; an `F` still has wooded movement/occlusion semantics and an `M` grassy semantics. Do not emit raw map symbols or interchangeable terrain labels in DTOs.
- On world creation at tick zero, calculate the initial per-resident visibility footprint and persist it **before** the first decision; the corresponding objective exploration facts appear after `world_initialized`. The map file defines static terrain. Fruit stock, item drops, corpses, action progress and regrowth are stored in `WorldState`, not encoded in `.map`.

### 1.3 Clock and day/night

Time advances in fixed increments `time.tick_minutes`, with day length `1440 / time.tick_minutes` ticks (must divide evenly). Local game clock at tick `t` is `time.start_hour * 60 + t * time.tick_minutes`, modulo 1440. Daylight is `[time.day_start_hour, time.day_end_hour)`; the end hour itself is night. Night reduces sight radius; it does not prohibit movement. Simulated time does **not** elapse during a synchronous LLM wait, player pause or dream dialogue.

## 2. Authoritative state and data ownership

`WorldState` owns: schema/version and run IDs; tick/clock; `config_hash` and `map_hash`; immutable/static map reference; fruit nodes (stock, growth phase), fruit-regrown and fruit-consumed lifetime counters; residents' position, `alive`, **`satiety`, `hydration`, `stamina`, `health`**; inventories; the unique canteen's current location/servings; ground objects and nonblocking corpses; active physical action and its progress; pairwise dialogue-turn/cooldown state (objective speech bookkeeping only); each resident's **objectively observed static tiles**; one seeded RNG state; event sequence/cursor and permitted rule overrides.

All four condition values are integers in the inclusive range `[needs.min_value, needs.max_value]` where **higher is better**. All gains, losses, thresholds and per-tick rates are integers. No authoritative floating-point values, decimal arithmetic, inferred timestamps, or model-generated numeric physical deltas.

World exploration footprints are a durable set of tile indices actually observed by each resident. A known tile's **static** terrain can be supplied from this footprint without divulging remote live stocks. The last-seen fruit quantity, a belief about whether a spring is safe, a rumor of an animal, social trust and character goals are **subjective agent memory**, never world-side facts. The world does not read, rank or mutate such memories.

World also retains private **exposure receipts** per resident: unique `(entity_id, entity_type, observed_position)` triples and the highest cue-detail level actually exposed. These receipts are permission/audit facts, not remembered claims: no stock, need values, trust or interpretation is retained in them, and they are never supplied wholesale to agents. A current or past receipt authorizes an entity-ID target; a `pick_up` tile target requires a receipt for that item type at that tile. Static movement targeting still uses the explored footprint. Receipts are saved, including exposures captured while moving. Receipt validity does not imply that the entity still exists or is still in reach; normal start/completion checks remain mandatory.

Separate stores (in the save package) contain resident profiles, goals, subjective memories/relationships, objective event log, and recorded LLM call inputs/outputs. World has no reference into memory objects. Only `world` may settle physical state; only the `memory` subsystem may change interpreted relationships. A character's private memory is not visible in another character's `Perception`.

Fruit is an integral item count; an individual fruit occupies one inventory slot. The canteen has one unique item ID, occupies one slot and has an integer serving count between zero and `canteen.capacity_servings`. It exists in exactly one place: one live inventory or one ground tile. Inventory item count is bounded by `inventory.slot_capacity`. Death creates a persistent, nonblocking corpse object, then transfers inventory to ground items atomically. There is no decay/burial/resurrection in v0.1.

All residents start with zero fruit. The canteen starts with the configured owner and servings. Ground fruit and corpses start empty; dialogue counters start empty. Same-tile fruit drops merge into a single pile; its ID `ground_fruit@<x>,<y>` is a spatial handle, not an item-generation ID. A zero-quantity pile is removed; a later pile at that position reuses the handle. Corpse ID is `corpse@<resident_id>`; there is no respawning in v0.1. Exclude the observer from its own `visible_entities`.

## 3. Physiology, food, water and resource balance

At **every completed tick**, including during rest/sleep, subtract `needs.satiety_decay_per_tick` and `needs.hydration_decay_per_tick` from every living resident; clamp within `[needs.min_value, needs.max_value]`.

Awake residents additionally lose `needs.stamina_awake_decay_per_tick`. If movement traversed at least one tile during a tick, apply `needs.stamina_move_extra_cost_per_tick` once that tick (not once per tile). Finishing `gather` costs `needs.stamina_gather_cost_per_completion`. `rest` restores `needs.stamina_rest_gain_per_tick` each active tick **while also applying awake decay**; `sleep` restores `needs.stamina_sleep_gain_per_tick` plus `needs.stamina_sleep_cave_bonus_per_tick` if on or orthogonally next to the cave, and incurs **no awake decay**. Clamp all results.

`eat` consumes one owned fruit, increments satiety by `needs.satiety_gain_per_fruit` (capped); `drink` restores hydration by `needs.hydration_gain_per_serving` either directly from adjacent spring or by spending one canteen serving. A `fill_canteen` action at the adjacent spring fills it to capacity. Spring water is inexhaustible; no portable drinking water exists apart from canteen servings.

If either satiety or hydration equals the minimum **after metabolism**, apply `needs.health_loss_per_tick_if_deprived` once (not twice). Otherwise, a sleeping resident above both configured recovery thresholds gains `needs.health_recovery_sleep_per_tick`. Health reaching zero triggers death, cancellation of active action, corpse creation, inventory drop and objective events. Stamina zero prohibits beginning or continuing movement/gathering; rest, sleep, eat and drink remain possible. Physiology uses the action that was active during this tick, even if it completed in phase 3: the final sleep tick has sleep recovery, no awake decay, and is eligible for sleep health recovery. Apply phase-2 rest/sleep gains with clamping, then phase-5 awake decay and movement/gathering costs with clamping. No hidden supply, forced rescue or narrator-driven state mutation is allowed.

Each fruit tree's `stock` begins at `fruit.initial_stock_per_tree`, capped by `fruit.max_stock_per_tree`. At scheduled regrowth ticks, increase stock by up to `fruit.regrow_per_cycle`, without exceeding the cap. **No stock is created when already full.** Regrowth is independent for each tree and uses its configured phase offset (§5.5). All fruit creation/consumption/transfers are included in conservation accounting.

## 4. Action protocol and action semantics

### 4.1 Contracts and preconditions

`Perception` is produced by `world`: own condition descriptors, exact own inventory, currently visible terrain, currently visible entities (residents, corpses, **fruit trees with their stock band**, **ground items**, the canteen when on the ground, cues), **transient sightings** (entities seen during this tick's movement steps but no longer visible at the tick boundary, §5.1 step 5), world-owned discovered **static** tiles, perceived utterances and perceivable action feedback. Every entity an action can target (`gather`, `pick_up`, `give`, `talk`) must be referable by an ID or position that `Perception` exposes. It contains no memory IDs, recollections, beliefs or goals. `DecisionContext` is built **only in `agents`** by adding private memory, beliefs, values and goals to `Perception`. **Its shape is provisional**: the agent-interface spec (due before P3) decides how a resident agent works — e.g. cognitive tools such as recall that cost no game time versus world actions that cost ticks, and whether one decision may involve several model turns. ~~P1 depends only on `Perception`, `ActionPlan`, `ActionIntent` and `ActionResult`.~~ **[A1]** P1 world settlement depends only on `Perception`, `ActionPlan`, `ActionIntent` and `ActionResult`; P1 agents additionally build the minimal empty-memory `DecisionContext` defined by the Interface Contract §2.3 as amended, which never reaches world settlement. Detailed field-level schemas and vocabularies are in the Interface Contract.

An `ActionPlan` contains between one and `agents.max_plan_actions` structured `ActionIntent`s in intended execution order. `ActionIntent` has intent/actor/plan IDs, `action_type`, typed target, typed parameters and an optional explanatory `reason`. The reason is nonauthoritative metadata. Submission cannot modify world state. An `ActionResult` references its intent and records start/finish ticks, `success|failure|interrupted`, a failure code when applicable, factual state change and feedback visible to that actor.

Start preconditions are checked at action start; mutable conditions are checked again at completion. An action invalid at start consumes exactly `actions.invalid_attempt_ticks` before a failure result is emitted. A failure at completion consumes elapsed action time. If an action becomes interrupted at a tick boundary, progress is discarded except for movement already completed and stamina already restored during rest/sleep. Any planned future actions are discarded and agent reevaluation is requested.

An `ActiveAction` saves its **complete ActionIntent**, including target and typed parameters; it never relies on a queued plan to reconstruct the current action. Queued plans hold only not-yet-started intents. At most one physical action per actor advances per tick; the next intent cannot start until the following tick. For an action starting at boundary `t`, the first progress interval is `t -> t+1`; a duration of `d` completes at `t+d`. `give` and `pick_up` fruit quantities must be positive integers and transfers are all-or-nothing; insufficient owned quantity is `NO_ITEM`, insufficient ground quantity is `ITEM_TAKEN`. An unexposed target fails `INVALID_TARGET` before querying its live contents.

### 4.2 Action table (durations in configuration)

| `action_type` | Mandatory preconditions and target | Duration / progression | Successful effect | Principal failure codes |
|---|---|---|---|---|
| `move_to` | alive, positive stamina; target tile known passable or one unexplored frontier tile adjacent to already explored passable tile; world plans through explored passable terrain | Each tick up to `map.walk_cost_budget_per_tick` cost units, many adjacent steps possible | authoritative position advances tile-by-tile; complete on entering target | `DEAD`, `EXHAUSTED`, `INVALID_TARGET`, `PATH_BLOCKED`, `NO_PATH` |
| `gather` | alive, positive stamina; fruit tree Manhattan-adjacent; one slot free | `actions.gather_ticks`; stock checked again at completion | tree stock −1; inventory fruit +1; gathering stamina cost | `DEAD`, `EXHAUSTED`, `OUT_OF_REACH`, `RESOURCE_TAKEN`, `INVENTORY_FULL` |
| `eat` | alive; own at least one fruit; satiety below maximum | `actions.eat_ticks` | one fruit consumed; satiety increased, capped | `DEAD`, `NO_ITEM`, `NO_NEED` |
| `drink` | alive; hydration below maximum; `parameters.source` is `spring` (adjacent) or `canteen` (owned, filled) | `actions.drink_ticks` | hydration increased; canteen charge spent only when source is canteen | `DEAD`, `NO_WATER`, `OUT_OF_REACH`, `NO_ITEM`, `NO_NEED` |
| `fill_canteen` | alive; owns canteen; adjacent to spring; not full | `actions.fill_canteen_ticks` | refill to capacity | `DEAD`, `NO_ITEM`, `OUT_OF_REACH`, `ALREADY_FULL` |
| `rest` | alive | `actions.rest_ticks`; per-tick gains | stamina restored as ticks pass | `DEAD` |
| `sleep` | alive | `actions.sleep_ticks`; per-tick gains | stamina restored, with possible cave bonus | `DEAD` |
| `talk` | alive; addressed resident alive within hearing radius; valid `speech_act` and referenced request when replying | `actions.talk_ticks` | one structured utterance; any awake resident in hearing radius at emission hears it | `DEAD`, `INVALID_TARGET`, `OUT_OF_HEARING`, `INVALID_SPEECH_ACT`, `INVALID_REPLY`, `DIALOGUE_LIMIT` |
| `give` | alive; target resident alive, Manhattan-adjacent; owned `fruit` count or unique `canteen`, recipient has room | `actions.give_ticks` | atomic item move to recipient; no separate consent action | `DEAD`, `NO_ITEM`, `OUT_OF_REACH`, `INVENTORY_FULL`, `INVALID_TARGET` |
| `pick_up` | alive; targeted ground item same or adjacent tile; inventory has capacity | `actions.pick_up_ticks` | atomic ground → inventory transfer | `DEAD`, `ITEM_TAKEN`, `OUT_OF_REACH`, `INVENTORY_FULL` |
| `wait` | alive | `actions.wait_ticks` | no direct state effect; ordinary needs still decay | `DEAD` |

`talk` `speech_act` is one of `statement`, `request`, `accept`, `refuse`. `request` MUST contain `{item_type, quantity}` where item_type is `fruit` or `canteen`, quantity is positive integer (canteen quantity exactly one). `accept` / `refuse` MUST contain `in_reply_to` referencing a **prior request utterance ID**, and speaker must be that request's addressee; reply target must be original requester. A response has no physical transfer — use `give` separately. A request/refusal is recorded as an objective act, without computing trust. A conversation is at most `social.max_dialogue_turns` **utterances**; one utterance equals one turn. A conversation session is keyed by the unordered pair of participants; it begins with their first addressed utterance and continues if their next addressed utterance is within `social.dialogue_gap_ticks` ticks of the previous one. A longer gap closes the session. On reaching the configured maximum, the pair cannot start another session until `social.dialogue_cooldown_ticks` ticks have elapsed after that final utterance; an extra utterance fails `DIALOGUE_LIMIT`. World retains only factual turn/cooldown counters, not relationship interpretations. No theft or long-distance shouting in v0.1.

### 4.3 Multi-tick interruption table (normative)

Triggers are examined **at tick boundaries**, after completions, physiology and perception updates. If a completion and an interrupt happen on the same tick, completion wins; otherwise interruption occurs before the next tick's progress. Urgent crossing means from above to `<= agents.urgent_*_below`, not every subsequent tick below it.

For an **unfinished** action, death takes precedence and emits `action_interrupted(reason=DEATH)`. Next, zero stamina terminates unfinished `move_to`/`gather` with `action_failed(failure_code=EXHAUSTED)`. A physically blocked movement step is a failure `PATH_BLOCKED`, not an interruption. Otherwise simultaneous applicable soft interrupts use priority `URGENT_NEED`, then `DIRECT_SPEECH`, then `NEW_SIGHT`; emit exactly one ActionResult. `status=interrupted` has `failure_code=null` and the chosen `interruption_reason`; success/failure have `interruption_reason=null`. Retain all co-occurring decision triggers in their defined order, even though the result has only one reason. A completed action is never retroactively failed by exhaustion or death later in that tick.

| Active action | Important new visible resource/person | New addressed audible `talk` | Urgent need threshold crossed | Action-specific failure | Player pause / dream |
|---|---|---|---|---|---|
| `move_to` | sightings are detected at every step (§5.1 step 5); interrupt after current tick's last completed tile, replan | interrupt at next boundary | interrupt at next boundary | next blocked tile fails before entering; no rollback of prior steps | pause freezes, never cancels |
| `gather` | do not interrupt for generic sightings | interrupt before next tick (unless just completed) | interrupt before next tick | resource taken at settlement → failure | pause freezes, never cancels |
| `rest` | no interruption | interrupt at next boundary | interrupt at next boundary | death immediately cancels | pause freezes, never cancels |
| `sleep` | no interruption | **does not hear / wake**, no delivered utterance | interrupt at next boundary | death immediately cancels | dream may run only while sleeping and paused; resume still asleep |

A speaker's utterance is heard by all **awake** residents within range, including listeners other than the addressee. Sleeping residents do not receive a delayed replay of missed speech. `move_to` can also stop after a tick where its own planned endpoint becomes invalid; there is no mid-tile interruption. Prior movement, already-paid need costs and already-created events are never rolled back.

### 4.4 Agent reevaluation triggers

When plan finishes; an action fails or is interrupted; a need **crosses** a configured urgent threshold; a newly visible salient person/resource/corpse/cue appears; an utterance is heard; a conversation requires a reply; or a sleeper wakes. Deduplicate same-tick triggers per actor; one decision per actor per boundary. LLM is not called every tick. If the soft per-day call budget is exceeded or a synchronous call fails/times out, record fallback and use the deterministic rule-based resident policy; do not pass the world clock forward while a request is outstanding.

An ongoing action receives observations but no new plan unless §4.3 terminates or interrupts it. Other triggers accumulate until the next idle boundary. At an idle boundary, deferred triggers request one reevaluation and discard unstarted intents before accepting a replacement plan; with no triggers, execute the next queued intent without a planner call. Exhausting a plan always supplies `PLAN_FINISHED`. Dead actors never request decisions. Tick zero requests the first plan after its initial packet is delivered.

## 5. Exact deterministic algorithms and settlement

### 5.1 Sight: radius + Bresenham occlusion

1. Candidate target tile must lie inside the map and have Manhattan distance `<= perception.day_radius_tiles` or `perception.night_radius_tiles`; no diagonal distance rounding or floats.
2. For each candidate in ascending `(y,x)` order, cast a **standard integer Bresenham line** from observer center `(x0,y0)` to target center `(x1,y1)`: `dx=abs(x1-x0)`, `dy=-abs(y1-y0)`, `sx=sign(x1-x0)`, `sy=sign(y1-y0)`, `err=dx+dy`; repeatedly evaluate `e2=2*err`, update x when `e2>=dy`, and y when `e2<=dx`, with the *same pre-update e2*.
3. Intervening tiles containing `W`, `F` or `^` **block further sight**; `~`, `.`, `,`, `M`, `S`, `C` do not. The blocking tile itself is visible if it is the target. The observer's starting tile never blocks sight, even if `F` or `W`. No supercover/corner rule is added in this version.
4. A tile at the configured radius edge is visible if not occluded. Visible entities occupy visible tiles. Updated explored-static-tile footprints are recorded only for tiles actually seen. Historical visibility does not reveal current resources outside sight.
5. **Per-step visibility during movement.** Because one tick may contain several `move_to` steps, the visible set is recomputed (steps 1–4) **after every entered tile**, not only at the tick boundary. The union of all tiles seen during the tick is added to the explored footprint. Entities seen at an intermediate step, but not visible from the tick-end position, are reported in `Perception.transient_sightings`. Keep one entry per entity ID, using its **last** intermediate sighting and the descriptor values captured there, never remote values read at delivery time. `seen_at_step` is 1-based within that actor's movement this tick. Include resident observable signs as well as fruit bands/ground quantities. Entities visible at tick end appear only in `visible_entities`. LOS is not assumed symmetric: A seeing B does not imply B sees A. **[A1] Sampling clock.** Every intermediate step sample and the boundary scan of one interval use the clock and sight radius of that interval's completed tick (`t+1` for `t -> t+1`); there is no sub-tick clock. Physical sampling (this step and step 6) is separate from hearing and action-feedback assembly: `heard_utterances` and `last_action_feedback` are attached after settlement and interrupt resolution, as specified by the implementation plan §2.1.
6. **Novelty and cues.** `NEW_SIGHT` means the first exposure of an entity ID to that resident, or the first upgrade of a cue from distant to near. All six entity types are salient; exclude self. Moving a previously exposed entity, seeing it again, a known tree changing band, or a ground pile reusing its spatial handle does not alone retrigger `NEW_SIGHT`. Compare against receipts at the start of this tick; multiple sightings produce one trigger per actor. Initial tick-zero exposures seed receipts but do not create an interrupt before the first decision. `environmental_cues` contains every cue actually observed in this interval, retaining the highest detail observed (near beats distant); this preserves a near inspection even if the actor walks away before the boundary. Cue-detail descriptions are captured when seen, not reconstructed from hidden state later.
7. **Reliable boundary delivery.** A completed boundary creates one immutable `BoundaryPerceptionDelivery` per living actor, including its full Perception and ordered decision triggers. Step sightings describe the just-completed interval and are an explicit exception to the prohibition on historical dynamic stock. They never become a remote-stock query. The packet remains pending until sim delivers it once to that actor's runtime at the next boundary-input phase, whether or not the actor needs a new plan. A checkpoint includes all pending packets and delivery cursors. Restore delivers the same packets before making decisions; it must not rebuild them from the final position. Only after delivery is acknowledged may world/sim discard the packet. Remembering its contents beyond that delivery belongs to the agent. At tick zero publish initial packets with empty transient arrays.

### 5.2 Hearing and cue inspection

A clearly spoken utterance emitted by `talk` reaches awake listeners with Manhattan distance `<= perception.hearing_radius_tiles` at emission settlement (including same-tile listeners). Rocks and woods do not attenuate hearing in v0.1. A detailed `M` environmental clue appears only at Manhattan distance `<= perception.cue_detail_radius_tiles` **and** if line of sight is unobstructed; otherwise a visible `M` tile exposes only its generic appearance. The cave/water cue does not grant a hidden route, spring coordinate or perfect water knowledge.

### 5.3 Pathfinding and movement budget

Use **Dijkstra shortest path** on four cardinal neighbors. Entering a tile incurs the corresponding positive integer `map.step_cost_*`; impassable tiles cannot be entered. Path search uses the actor's **explored passable static tiles**, except one final adjacent, unexplored frontier tile may be considered as a candidate. For path search, a permitted unexplored final frontier tile is tentatively assigned `map.step_cost_grass` without revealing its terrain. On reaching it in actual execution, the authoritative map checks passability and uses the **actual** entry cost; if insufficient movement budget remains, the step waits until the next tick. An impassable target fails with `PATH_BLOCKED` and becomes observable as a failed physical attempt, without moving into it.

**Tie-breaking is defined by the algorithm, not by a path-ordering property.** The normative algorithm is:

1. Priority queue keyed by `(total_integer_cost, y, x)` of the node; pop the smallest key; skip nodes already finalized.
2. Expand the popped node's neighbors in exactly `N, E, S, W` order.
3. A neighbor's distance and predecessor are updated **only if the new cost is strictly lower**. On an equal cost, the first predecessor found is kept.
4. The route is reconstructed from the target back through predecessors. There is no random tie-break and no claim that the result is the lexicographically smallest direction sequence.

Required test vectors: (a) on an open 3×3 grass grid, `(0,0) → (1,1)` gives `[E, S]`; (b) on the **fully explored** default map, the cave `(13,32)` to the spring-adjacent tile `(37,30)` costs 36 units. All route tiles are marked explored for these geometry tests; they do not grant initial residents map knowledge. Implementations must reproduce both.

At each movement tick take as many successive route steps as fit `map.walk_cost_budget_per_tick`, in route order. A step emits `resident_moved` at its entry; the per-tick movement budget resets next tick. Paths may be recomputed at the next tick boundary after an interrupt; completed steps remain authoritative.

### 5.4 Synchronous decision and conflict settlement order

A completed simulation tick `t -> t+1` always uses these phases:

1. **Boundary input:** deliver and acknowledge pending boundary Perception packets before decisions, in ascending `actor_id` order. Agents may ingest observations without planning. Use the delivered physical snapshot, including transient sightings, for eligible idle actors' decisions; do not rebuild it. Validate queued player commands. No runtime rule parameter is editable in P1; its rule override object remains empty. Later permitted parameter changes must have been submitted while paused, are staged until resume, and take effect at this next completed tick with a `config_changed` event. Synchronous LLM calls freeze tick progression. Accepted plans are queued in actor order; invalid-at-start actions become one bounded pending failure, not zero-time loops.
2. **Action progress:** process actors ascending by `actor_id`: start/advance pending actions; movement traverses legal tile steps under its budget and emits ordered `resident_moved`, recomputing visibility after each step (§5.1 step 5); `rest` and `sleep` recover stamina; any due completions (including last movement step) join the completion set. Partially completed actions carry progress to the next tick. No shared inventory or resource transfer settles in this phase.
3. **Completion resolution:** sort **all** due completions by `(actor_id,intent_id)`; apply one seeded Fisher–Yates shuffle to the *entire* set (not merely to disputed resources), then validate mutable preconditions and settle them sequentially. For a conflict on a last fruit/item the first eligible completion wins; later completions fail (`RESOURCE_TAKEN` or `ITEM_TAKEN`). Each result creates authoritative events. This phase can complete `eat`, `drink`, `talk`, `give`, `pick_up`, etc. Failed actions do not revert elapsed time.
4. **Regrowth:** process configured fruit nodes by ascending node ID, applying their due phase schedule. There is no random regrowth.
5. **Metabolism/death:** process living residents by ascending `actor_id`; apply need changes, condition events, deaths and item drops. `alive=false` residents skip later decisions/actions. Apply any necessary extra movement/gathering stamina expenditure exactly once at this tick's physiology update.
6. **Perception/interrupts:** recompute tick-end visible tiles; merge them with the per-step union from phase 2 into exploration footprints; build `transient_sightings` and cue observations; collect newly perceptible events and utterance deliveries previously emitted at settlement (excluding the speaker and residents asleep at emission); evaluate terminal failures, interrupts and decision triggers as in §4.3. Update private exposure receipts and publish boundary delivery packets. New observations cannot retroactively alter already-settled actions this tick.
7. **Commit:** publish final tick number `t+1`, event sequence/cursor and RNG state. All events generated in phases 1–6 belong to completed tick `t+1` and are buffered in emission order until this commit. Append the canonical ordered records; snapshots may be taken only at this completed boundary. All pending physical progress, complete active intents, exposure receipts, boundary delivery packets, delivery cursors, per-actor future plans and deferred triggers are saved for continued execution.

No concurrent actor may write `WorldState` directly; one world engine owns all mutations. World-regrowth and physiology happen **after action completion**, so the resource stock seen by a simultaneous gather attempt is the pre-regrowth stock.

### 5.5 Regrowth phases

Each tree has an integer `regrow_phase_offset_ticks` in `[0, fruit.regrow_ticks-1]` stored in content and state. At completed tick `k >= 1`, node regrowth is due if `k % fruit.regrow_ticks == regrow_phase_offset_ticks`. Thus phase zero first regrows at `fruit.regrow_ticks`, never tick zero. Nodes have individually specified offsets; they do not all regenerate at the same boundary. If stock is already capped, skip creation and emit no regrowth fact. No resetting of phase on harvest.

### 5.6 One explicitly specified RNG stream

The only authoritative random stream in v0.1 is `resolution_rng`, initialized with nonzero `meta.seed` as a **32-bit unsigned Xorshift32** state (mask after shifts):

`x ^= (x << 13) & 0xffffffff; x ^= x >> 17; x ^= (x << 5) & 0xffffffff; x &= 0xffffffff; output x`.

The only consumer is the tick-completion Fisher–Yates shuffle in §5.4. Sort completions first. For `i` descending `n-1` through `1`, sample `j` uniformly from `[0,i]` by drawing `uint32` until `< 2^32 - (2^32 mod (i+1))`, then `j = drawn mod (i+1)`, swap entries i and j. Empty or singleton completion sets consume **zero** draws. Every accepted draw is persisted in the resulting RNG state at commit. Rule-based exploration is deterministic; it must not draw secretly from global randomness. Any future stochastic ecology receives a *separately specified, named stream*, not this one.

## 6. Memory, social consequences, dreams and death

The physical world records factual `utterance_spoken` (`request`, `accept`, `refuse`, `statement`), `utterance_heard`, `item_given`, `resident_died`, `corpse_created`, `item_dropped`, etc. It **does not** store `trust`, compute a trust delta, infer intention or give everyone global death knowledge. Agent/memory P4 may interpret these records, retain subjective impressions and update beliefs/relationships; this has no physical effect except through future proposed actions.

At death, remove resident from the active population, create a corpse at current tile and drop all inventory contents including a canteen with its current servings. Corpse does not block movement. It remains a visible object until a future feature changes the rule. No other resident receives a global death notification; only direct visible evidence and delivered in-world testimony can affect their awareness.

Dream conversations are available while a character is sleeping and game time is paused. The player cannot issue authoritative physical commands through a dream. On awakening, agent/memory integrates at most a small, low-confidence, forgettable dream fragment; the original text and exact retention/debug policy are handled by the separate P6 spec, **not `world`**. “Faint thoughts” follow the same agent-side channel. The world event log may audit a non-secret intervention's metadata but must not act on its semantic content.

## 7. Events, serialization, replay and interfaces

Exact event envelopes, event catalog, `Perception`, `DecisionContext`, `ActionIntent`, `ActionPlan`, `ActionResult`, visible descriptors and DTO rules are in **`interface-contract-v0.1.md`**. Every physical mutation is represented by a factual event; per-tick condition and action-progress deltas may be aggregated by resident. Each event is tagged with `(tick, seq_in_tick)`, the latter assigned monotonically beginning at zero each tick. `event_id` is derived from `(run_id,tick,seq_in_tick)`; past event IDs never change. Audit events may coexist, but agent observations are permission-filtered, not direct event-log access.

A save package includes an authoritative snapshot; original typed config and map hashes; objective event cursor; `resolution_rng` state; outstanding plans/action progress; each resident's exploration footprint; separate memory/profile state; relevant pending utterance deliveries; and recorded model input/output decisions. JSON snapshots and JSONL events are owned by persistence, with atomic snapshot replacement. A UI event playback and a **deterministic re-execution** are not the same operation. The re-execution comparator and canonical encoding are in the contract's Determinism Appendix.

## 8. Hard invariants and tests

1. All authoritative conditions are **integers** in bounds; all stocks/servings are integers and nonnegative; unique canteen has exactly one current location and consistent ownership.
2. Fruit conservation at each tick: `initial_on_trees + actual_regrowth = current_on_trees + resident_inventory_fruit + ground_fruit + fruit_consumed_by_residents` (plus any expressly added animal-consumption sink in P5). Every accounted gain/loss has a source/sink event.
3. Dead residents cannot initiate/complete actions, hold inventory, or be immediately known dead outside others' perception. Corpse/drop creation is atomic and persistent.
4. `world` does not import `memory`; `Perception` contains no private memories, beliefs, future world-state facts, remote live stocks or other resident's exact needs. Previously explored tile IDs reveal **static terrain only**.
5. One action cannot bypass distance, ownership, capacity, stamina or target preconditions. Concurrent attempts for a single stock/item cannot both succeed.
6. Simulated time freezes during LLM wait and pause; invalid actions cannot trigger infinite zero-time retries; unfinished actions and deferred interruption triggers survive tick-boundary save/restore.
7. The same snapshot, effective config, map, RNG state, ordered commands and recorded decisions produce the same **canonical authoritative snapshot and objective event JSONL bytes**. Frontend display and provider latency are excluded.
8. World events obey total order; causal references point only to previously emitted event IDs. Narration is read-only and cites actual event IDs.

Before P1 starts, validate authored map grammar/positions, configuration domains and the route/arithmetic claims. During P1 implementation, add engine tests for line-of-sight edge cases, Dijkstra tie-break, Xorshift32/shuffle, regrowth, interrupt priority, resource/item invariants, same-tick contention, complete-intent and boundary-packet save/restore, and canonical two-run re-execution. These engine tests are P1 exit criteria, not tests a nonexistent engine must pass before P1 starts. A seven-game-day run using rule-based residents validates balance only **after implementation**; this draft claims no measured survival odds.

## 9. Open checks — not delegated to implementers

- Exact numerical balance, walk budget, physical tile size and environmental clue effectiveness are **engineering candidates** pending review and simulation, not measured results. Route costs quoted in the balance notes were computed with the §5.3 algorithm on the authored map; survival outcomes were not.
- The canteen's strategic value is a design goal, not a guarantee. P2 first compares water trips, useful task time, journeys and water delivery with/without the canteen at fixed geometry and hydration. Compare hydration candidates 100 and 120 separately. If benefit is negligible, reconsider local resource placement or the value proposition before increasing global deprivation; do not make nonholder deaths a success criterion.
- Whether the default rule-based policy can discover the spring in time must be tested; do not grant it the unseen spring coordinate. Water options have already been resolved by the product owner in favor of a vague physical cue.
- Detailed Agent memory retrieval/relationship dynamics, dream text persistence, optional herbivore and model-provider operational timeout are later milestone specs and cannot silently alter authoritative P0 world mechanics.
