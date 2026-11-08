# Living Island — v0.1 Initial Design Document (Draft 0.1)

> **Status**: Product scope confirmed based on 12 user decisions; technical implementation details are still proposals and not frozen.  
> **Positioning**: A self-running desert-island world + autonomous AI characters + limited god-like intervention + stories that emerge naturally from real events.  
> **Goal of this phase**: Prove the world can run stably, character behavior is constrained by the real environment, interactions produce feedback, and past experiences influence future choices.

> **[Claude note · Overview]** The original text is unchanged; all comments are inserted as "[Claude note]" blockquotes after the relevant paragraphs. Labels: **Confirmed** = change already agreed in discussion; **Suggestion** = addition still to be decided.
>
> Overall assessment: this is a solid **product document** (positioning, principles, scope and acceptance are clear), but not yet a **technical spec** that development can start from — it contains no concrete numbers, no action list and no data structures. Keep this file as the product document and write a separate "World Rules Spec v0.1" as the real P0 deliverable, covering: map and tiles, time scale, character state and numbers, action table (preconditions / duration / effects / failure codes), conflict resolution, observation and action data structures, event format, frontend–backend interface contract, invariants.
>
> Main confirmed changes:
> 1. No carnivore in v0.1; at most one herbivore species;
> 2. Only one tool, with one effect;
> 3. Add rule-based residents as a balancing tool, control group and fallback;
> 4. Move animals and tools after LLM residents and social features;
> 5. Frontend uses React + TypeScript, but only displays state and sends commands;
> 6. Save as JSON snapshots first; defer SQLite;
> 7. LLM calls are synchronous (world waits); no "stale intent" handling;
> 8. Record LLM inputs and outputs to support replay.

## 1. Product Vision and Design Principles

The player creates and observes a desert island that runs on its own. The residents are driven by independent Agents with limited perception, survival needs, personality, goals and memory. Even if the player does nothing, characters explore, look for food and water, communicate, help or refuse to help each other, and actually change the world state. The player is like a god with **limited powers**: they can observe, configure some rules, and influence characters' cognition through dreams or faint thoughts, but cannot directly force their actions.

**Core product experience**: Watch the loop "behavior → world feedback → new perception/memory → next behavior"; stories emerge from real actions and consequences, not from pre-written scripts.

**Mandatory principles**:
1. **The world is the source of truth**: characters can only propose intents; the world engine validates and resolves actions. The LLM cannot declare resource gains, character movement or another character's consent on its own.
2. **Actions must land**: important choices must become concrete actions, state changes, failure feedback or traceable relationship changes — not conversations detached from world state.
3. **Perception is not omniscience**: characters only know nearby information, their own state, and what they can recall or learn from others.
4. **Memory is not objective history**: the objective event log is separate from characters' subjective memories; characters can forget, misunderstand or disbelieve information.
5. **Game before experiment**: aim for a fun, continuous, believable autonomous world; v0.1 need not be a scientific experiment platform.
6. **Extensible but not over-abstracted**: keep interfaces for swapping models, adding rules and adding characters, but do not build a general mod platform in v0.1.

> **[Claude note · Suggestion]** The principles are accurate; principles 1, 3 and 4 should be hard checks in code review. Add principle 7:
>
> **Reproducibility**: fixed random seed, log all events, record the input and output of every LLM call; the same save + the same recording can be replayed tick by tick without new model calls. This is the foundation for debugging, cost control and controlled experiments.

## 2. v0.1 Scope

### 2.1 Confirmed In Scope

- One fixed-size, savable/restorable, standalone island; 2D top-down map.
- Terrain and locations: woods, fruit trees, grassland, fresh water, cave/initial shelter.
- Plants and resources: basic gathering, consumption and regrowth.
- **Three animal species**: two herbivores and one somewhat aggressive carnivore. Animals can be rule-driven; no LLM required.

> **[Claude note · Confirmed]** No carnivore in v0.1. Attack, damage and fleeing form a whole subsystem and can kill characters on day one (see the last risk in Section 12). v0.1 keeps at most one herbivore as environmental pressure ("competing with residents for fruit"); animals can also be omitted entirely at first, validating only the character–resource loop. Carnivores and combat move to v0.2.

- **Three independent LLM characters**: different initial personalities and goals, individually configurable starting tools such as an axe or knife; capable of survival, social interaction, memory and goal adjustment.

> **[Claude note · Confirmed]** Only one tool with one effect, e.g. "axe: improves gathering efficiency". Knife and other tools come later. The three personalities' behavioral differences need dedicated testing (see the Section 3 note).

- Survival rules: hunger, thirst, stamina, health, death; day/night and time progression.
- Actions: explore, move, gather, drink, eat, rest, use basic tools, talk, ask for help, share/refuse to share items; respond to animal threats when necessary.
- Fixed time step: pause, single-step, speed-up; v0.1 only advances while the program runs and saves on close; world updates and LLM decision frequency are decoupled.

> **[Claude note · Suggestion]** Initial time values: 1 tick = 10 in-game minutes, 144 ticks per day; walking one grass tile 1 tick, one forest tile 2 ticks, gathering and drinking 1 tick each, sleeping 48 ticks.
>
> **[Claude note · Confirmed]** LLM decisions are **synchronous**: when a resident needs a decision, the world waits for the reply before advancing to the next tick; thinking consumes no game time. Save only at tick boundaries.

- Limited perception, individual memory, simple relationships; important events can change later decisions.
- Player: configure rules at world creation; at runtime, limited environment parameter adjustment, observing characters, dream conversations and planting faint thoughts; interventions are traceable but not direct control.

> **[Claude note · Suggestion]** Narrow "limited runtime parameter adjustment" in v0.1 to: modifying a few parameters (e.g. resource regrowth rate) only while **paused**, each change producing a config event. More complex runtime rule editing comes later.

- Event log and narrative display: the timeline is based on real world events; the narrator may not fabricate game facts.
- Model interface is swappable; characters do not share internal memory and interact only through the world.
- Art exploration: during v0.1 development, accumulate and compare different 2D art styles and build a swappable asset pipeline.

> **[Claude note · Suggestion]** Keep art exploration as a side track, but exclude it from P1–P5 pass criteria. The frontend first draws tiles as colored blocks on Canvas; the asset interface (tile pixel size, layer order) is fixed in the spec first, and a unified style is chosen at the acceptance stage.

### 2.2 Explicitly Out of Scope

Multiplayer online, a full player-facing character editor, mod platform, complex weather, reproduction, farming tech tree, complex trade economy, factions/marriage, complex ecosystems, 3D, demanding animation, scripted storylines. Strict scientific reproducibility is not a product goal for now.

> **[Claude note · Confirmed]** Per the notes above, add to "out of scope": carnivores and combat, multiple tools, arbitrary runtime rule editing, multiple dream memory-integration strategies (v0.1 implements one), database storage (v0.1 uses JSON snapshots).

## 3. v0.1 Acceptance Goals

**Core milestone: The Island Is Alive**: with no player input, three LLM characters with different personalities act autonomously on the island for at least seven in-game days; they handle survival needs, have interactions with real consequences, and important experiences influence later behavior.

### 3.1 Required Functional Acceptance

| Dimension | Requirement |
|---|---|
| World keeps running | Seven in-game days complete with no deadlock, state corruption, unbounded requests or flows requiring manual takeover; characters may die — surviving seven days is not mandatory |
| World rules | Resources never appear from nothing; action validation is explicit; paths, inventory, time and life state are consistent; failures have reasons |
| Autonomous behavior | Survival loop runs without player input; characters replan on need changes or important events |
| Character differences | Personality/goals enter the decision input and show in observable behavior; differences need not appear every run |
| Social interaction | Can talk, ask for help, share or refuse; at least one interaction with real consequences verified in a dedicated test scenario |
| Memory continuity | Important experiences enter later decision context and influence behavior in traceable cases |
| Perception boundary | Characters cannot query unknown objective world state outside their view |
| Dream intervention | Player can hold dream conversations or plant faint thoughts; characters can accept/question/ignore; compliance not guaranteed |
| Save/restore | World, character goals, memories, relationships, inventory, time and unfinished tasks can be saved and restored |
| Observability | User can trace key behaviors and consequences via the map, character panel and event timeline |

> Note: **Seven days of autonomous running** is a technical acceptance criterion; **naturally compelling stories** is a product-quality observation and should not be a hard pass/fail per run. Otherwise the system is tempted to fake dramatic events.

> **[Claude note]** Separating "seven days of autonomous running" (technical acceptance) from "are the stories compelling" (quality observation) is one of the best judgments in this document; keep it.
>
> **[Claude note · Suggestion]** Make some items measurable:
> - **Character differences**: add a **personality-swap test**. Same random seed, swap the three personalities and rerun; check whether share/refuse counts, exploration range, food hoarding, etc. move with the personality. This also detects "LLMs are inherently friendly, so personality differences get flattened".
> - **Memory continuity**: add a **memory ablation test**. Rerun the same scenario with memory retrieval off; behavior should differ observably.
> - **Autonomous behavior**: add a **baseline comparison**. Run the same scenario with rule-based residents and show which behaviors LLM residents produce that rule-based ones don't.
> - **World keeps running**: record LLM calls, tokens and latency per in-game day as a cost baseline.
> - **Save/restore**: "unfinished tasks" only need saving at tick boundaries; restore continues from the same tick.
> - **New: replayability**: replaying a full run with recorded LLM replies yields results identical to the original, event by event.

## 4. World Model and Rules

### 4.1 Authoritative State

World State includes at least: world time, map tiles and terrain, resource stock and regrowth progress, plants, animals, character positions and attributes, items and inventories, shelter state, in-progress actions, rule parameters, RNG state/seed, event sequence number.

> **[Claude note · Suggestion]** Store an **LLM call log** separately from World State: input observation, prompt version, model name, raw output, parsed result, latency, token count. It is not world state but is part of the save, used for replay and debugging.

### 4.2 Basic Causal Rules

- Gathering deducts from the world's available stock, then enters the character's inventory per rules; limited by distance, time, possible tool requirements and stamina.
- Characters consume food/water; actions and rest affect stamina; injuries affect health; health reaching zero can cause death.
- Water sources and fruit trees have explicit replenishment and regrowth rules; inventories must not be secretly changed to sustain a story.
- The two herbivores have basic movement, foraging and avoidance logic; the carnivore has basic roaming, approaching and attacking. Attacks must be resolved through distance, duration and damage rules.
- Tools are concrete items with uses and owners; v0.1 implements only limited tool effects. Whether to add tool wear, recipes and crafting is left for later.
- Characters facing danger can flee or avoid it; safety reactions can be handled by the rule layer without calling the LLM every time.

> **[Claude note · Confirmed]** The "two herbivores + carnivore + attack" rules here simplify in v0.1 to at most one herbivore (movement, foraging, avoiding residents); attack, damage and flee rules move to v0.2. Tool rules implement only one effect, per the Section 2.1 note.
>
> **[Claude note · Suggestion]** In v0.1, "safety reactions handled by the rule layer" mainly cover survival thresholds, e.g. automatically heading to a known water source when thirst reaches a dangerous level, without waiting for the LLM.

### 4.3 Time and Decision Frequency (technical proposal, not frozen)

The engine advances in fixed ticks with pause/step/speed-up. Movement and gathering take multiple ticks; the LLM makes a new high-level decision only when there is no valid plan, a goal is completed, an action fails, an important event occurs, or a conversation/reflection is needed. Speeding up does not require proportionally more LLM calls.

Actions are resolved in a deterministic order; if multiple characters contend for the same resource, validate together and resolve by a deterministic rule to avoid negative inventory. LLM responses have latency, so intents must be revalidated before submission; stale intents are rejected or replanned.

> **[Claude note · Confirmed]** Synchronous waiting is decided: the world does not advance until the LLM returns, so v0.1 has no "stale intents" and that complexity can be dropped. Preconditions are still validated at resolution.
>
> **[Claude note · Suggestion]** Two "deterministic rules" must be written concretely in the spec:
> - **Conflict resolution**: e.g. each tick, shuffle residents' resolution order with the seeded RNG and validate/resolve in that order; first come first served, the later one gets a failure code like `RESOURCE_TAKEN`.
> - **Decision triggers**: list them explicitly, e.g. plan completed, action failed, sees a new person or resource, someone speaks to them, a need crosses a threshold, waking up each day.

## 5. Agent Model

### 5.1 Character State

Each character has: identity, personality/values, initial long-term goals, updatable mid/short-term goals, position/items/physiological state, known world information, relationship state, memory, current action plan, decision config and model adapter.

**Stable vs. mutable boundary**: basic needs like hunger/thirst come from world rules; personality and values are relatively stable; goals can be spontaneously created, revised and abandoned; personality change requires accumulated experience, not a single generation rewriting it.

### 5.2 Perception

Agent input is not the full World State but an observation built by `ObservationBuilder` from current position, perception range and existing knowledge. Observable content and subjective memory are clearly separated. Conversation information can spread but is not automatically treated as fact.

### 5.3 Hybrid Decision Architecture

- **LLM layer**: long/mid-term goals, current task selection, important trade-offs, language communication, reflection after important events.
- **Rule execution layer**: pathfinding, per-tick movement, resource gathering, item transfer, basic danger reactions, action timing, result checking.
- **World referee layer**: checks preconditions, changes authoritative state, produces result events; never accepts direct world modification from the LLM.

Use structured action intents: `action_type`, `target`, `parameters`, `reason` (optional), `plan_id`. Execution returns `success/failure`, concrete changes and perceivable feedback, rather than letting the Agent self-report completion.

> **[Claude note · Confirmed]** Add **rule-based residents** (simple utility rules: thirsty → find water, hungry → find food, tired → rest, otherwise explore), implementing the same interface as LLM residents. Three uses:
> 1. Run the world and balance numbers before the LLM is connected;
> 2. Serve as a control group to measure what the LLM adds;
> 3. Serve as the **fallback** for Section 13 item 4: when the LLM times out, errors or exceeds budget, the resident temporarily switches to rule-based behavior.
>
> **[Claude note · Suggestion]** Constrain LLM output with structured output (tool calling or JSON schema); a parse failure counts as a failed decision and is logged; retry once, and if it fails again, fall back to rule-based behavior.

### 5.4 Multi-Agent Interaction

The three Agents have independent decision contexts and memories and do **not** call each other's models directly. Talking, sharing items, asking for help and refusing all happen through in-world interaction actions; conversation requires basic position/contact conditions, and information transfer cannot exceed the defined perception or communication rules. Relationship state updates gradually from behavior and memory.

> **[Claude note · Suggestion]** Talking is itself an action; define in the spec: everyone within the speaker's hearing range receives it (including non-addressees, enabling "eavesdropping"); talking consumes game time; cap the number of exchanges per conversation to prevent two LLMs chatting forever.

## 6. Memory System, Dreams and Faint Thoughts

### 6.1 Layered Structure

1. **Working context**: current observation, current task, recent action results; short-lived.
2. **Episodic memory**: important events experienced by the character, with time, subjective interpretation, people involved and source.
3. **Long-term beliefs/relationships**: relatively stable understanding of places, people, dangers and values; revisable by new experiences.
4. **Objective world event log**: belongs to the engine, is not any character's memory; used for the timeline, debugging and saves.

Memory retrieval scores by relevance, recency, importance and the character's current goals; a memory existing does not mean every LLM decision retrieves it. Retrieval can start with simple rules; v0.1 does not require a vector database.

> **[Claude note · Suggestion]** v0.1 starts with the simplest approach: episodic memories stored as a chronological list; a nightly "reflection" before sleep compresses the day into a few summaries written to long-term beliefs; at decision time, take the top N by "involves currently visible people/places + importance + recency". Consider vector retrieval only once memory volume actually grows.

### 6.2 Dream Conversations

The player enters a dream interface when a character is resting/sleeping and talks with them. Dream text is a **subjective, uncertain cognitive input** — not world fact and not a high-priority system instruction. After waking, memories are integrated by a configurable strategy:
- keep no original dialogue;
- keep a small fuzzy episodic fragment;
- distill into one low-confidence long-term thought that can be forgotten/questioned;
- or form no retrievable memory.

"Deleting the dream conversation" and "deleting memory" are different operations: after the dialogue text is deleted, the character may still keep the integrated subjective memory. The objective intervention log can record time, target, intervention type and result without permanently storing the original dream text. If the original text is not kept, verbatim replay is limited; this trade-off should be explicit for debug vs. release mode.

> **[Claude note · Confirmed]** v0.1 implements only one integration strategy: after waking, keep **a small fuzzy episodic fragment**, tagged with dream as source, low confidence, forgettable. The other three are future options.
>
> **[Claude note · Suggestion]** Keep the original dream text during development for replay and debugging; whether release mode deletes it is decided later.

### 6.3 Planting Faint Thoughts

This does not write the player's request into an enforced system prompt; it enters the character's cognition as a memory fragment whose **source is dream/intuition, with limited confidence, able to fade**. E.g. "the north seems worth exploring" — the character may consider, doubt or ignore it; it must never directly update world truth.

## 7. Player and God Permissions

**At creation**: configure terrain/resources/initial characters/tools/rule parameters within allowed ranges.  
**At runtime**: observe and follow characters; pause, step, speed up; limited environment parameter changes; spawn characters (interface reserved; v0.1 may support initial configuration only); enter dream conversations; plant faint thoughts.  
**Limits**: cannot directly set a character's next action, cannot arbitrarily rewrite a character's past memories, cannot change world facts via the narrative layer. Runtime rule changes produce traceable config events and must pass parameter validation.

The "character memory panel" the player sees is a god's-eye visualization; it does not mean characters can read each other's memories.

> **[Claude note · Suggestion]** Narrow runtime permissions per the Section 2.1 note: v0.1 only allows modifying a few parameters while paused; "spawn characters" keeps the interface only and is not implemented.

## 8. Events and Narrative

The engine appends important action results to the event log, including at least: event ID, game time, character/object, action or event type, success/failure, state-change summary, related event IDs where needed. Example: `ask for food → refuse to share → hunger worsens → change exploration goal`.

**The narrative layer is read-only**: it selects, groups and summarizes real events into daily timelines and character stories; it may polish language but must not invent facts that did not happen. The event log can be detailed for debugging; player-facing display should filter and aggregate.

> **[Claude note · Suggestion]** Event format additions:
> - every event has a tick number and a sequence number within that tick;
> - action events carry failure codes;
> - events caused by an LLM decision link to its call log ID (see the Section 4.1 note), so "Ryan refused to share" can be traced back to what he saw and what the model output.
>
> The event format is also the frontend replay file format and belongs in the interface contract.

## 9. UI and Art

### 9.1 v0.1 Interface

- **Central map**: 2D top-down island showing terrain, plants, animals, characters, locations and basic action feedback.
- **Character sidebar**: name, personality summary, current goal, health/hunger/thirst/stamina, carried items, recent observations, important memories and relationships.
- **World timeline**: event log, filter by character, key story fragments.
- **Run controls**: pause, step, speed, save/load.
- **God controls**: rule config, dream window, faint-thought injection (with permission boundaries and logging).
- **Developer debug view**: what the Agent actually saw, the action it proposed, validation failure reasons, model latency and call cost; not necessarily exposed to regular players.

> **[Claude note · Confirmed]** Add frontend features by phase: P1 map replay and time controls; P3 character panel and developer debug view; P6 timeline and god controls. Build the debug view early — it is the main tool for judging whether LLM residents behave sensibly.

### 9.2 Art Exploration

Keep a 2D art exploration side track during v0.1: try pixel art, simple illustration and other directions, collect style boards and swappable asset samples. Fix the asset interface first (grid size, layers, character facing/animation conventions), then choose a unified final style. Avoid heavy art production before rules and gameplay are validated. Record licenses and sources of third-party assets.

## 10. Proposed Technical Architecture (not a product decision; pending technical review)

```text
UI / Player & God Controls
          |
     Application API
          |
  Simulation Coordinator ---- Save / Load
          |
  +-------+-----------------------+
  |                               |
World Engine (authoritative)   Agent Runtime
  |                               |
Rules / Actions / Animals     Observation Builder
  |                           Planner / LLM Adapter
Event Log                     Memory / Beliefs
  |                               |
  +------------ Action Intent <---+
          |
   Validation & Settlement
          |
      World State
```

**Proposed initial stack**: Python for the world core, scheduling and Agent Runtime; FastAPI for the API; SQLite for world state, events and memory; React + TypeScript for the 2D map and management UI; pytest for rule and integration tests. Rendering library and model provider are not locked in.

> **[Claude note · Confirmed]** Frontend uses React + TypeScript (Vite, TS strict mode, ESLint) with these constraints:
> - **No game logic in the frontend**: it only displays the world, shows events and character info, and sends player commands; reachability, legality and similar checks are always done by the backend.
> - **Contract first**: frontend–backend data (snapshots, events, character panel, player commands) is defined as pydantic models; FastAPI generates the OpenAPI description, and a tool like openapi-typescript generates TS types automatically, so the two sides cannot drift.
> - **Replay first, live later**: the first frontend reads the event log file and replays it tick by tick; once the world core is stable, add live observation over WebSocket, using the same event format.
> - **Simple rendering**: start with colored blocks on HTML Canvas; choose PixiJS or similar after the art direction is set.
>
> **[Claude note · Confirmed]** Storage: v0.1 uses JSON snapshots at tick boundaries + an event log file (JSONL); SQLite is deferred until memory volume grows.
>
> **[Claude note · Suggestion]** Use type annotations throughout the world engine and Agent runtime (dataclass / pydantic); the `world` module must not import rendering, networking or LLM dependencies.

**Module boundaries**:
- `world`: pure world state, time, rules, resources, animals and resolution; no LLM SDK dependency.
- `agent`: character perception, planning, task execution and model adapters; may not modify world state directly.
- `memory`: episodic memory, beliefs, retrieval, forgetting and dream integration.
- `events`: authoritative events, audit records and read-only narrative projections.
- `interface`: player interaction, saving, observation and developer debugging.

## 11. Development Order and Phase Deliverables

| Phase | Runnable vertical slice | Pass criteria |
|---|---|---|
| P0 · Spec & prototype | World state schema, rule list, minimal map prototype, project structure, CI | Action interface and state ownership clear; basic tests run |
| P1 · World core | Fixed tick, map, resources and regrowth, character move/gather/eat/drink, saving | Runs continuously and restores without LLM; resource conservation tests pass |
| P2 · Ecology & tools | Two herbivores, one carnivore, damage/death, basic tools | Animal actions are rule-controlled; danger and tools cause real state changes |
| P3 · One Agent → three Agents | Limited perception, LLM intent generation, validation/failure feedback, goal updates, three isolated characters | Task loop runs with no player input; characters cannot read unknown info |
| P4 · Social & memory | Talk, ask/share/refuse, relationships, episodic memory and long-term beliefs | Interactions have consequences; important past events influence future choices |
| P5 · God & narrative | Dreams, faint thoughts, limited rule config, event timeline, character panel | Interventions cannot force actions; stories only cite real events |
| P6 · Acceptance & art integration | Seven-day run, failure recovery, basic performance/cost stats, style samples | Meets Section 3 acceptance; playable build |

**Key engineering habits**: maintain issues/acceptance criteria per phase; have Coding Agents implement small, verifiable changes; test world rules, save migration, memory and LLM adapters independently. Record human interventions, rework and regressions in the agent-driven engineering process as evidence for a project-management retrospective.

> **[Claude note · Confirmed]** Reorder phases: world first, then rule-based residents, then LLM; move animals and tools after social and memory.
>
> | Phase | Content | Pass criteria |
> |---|---|---|
> | P0 · Spec & contract | Finalize product doc; "World Rules Spec v0.1"; interface contract; repo structure, CI, instructions file for coding agents | Action table, numbers table and event format complete; coding agents can start from them |
> | P1 · World core + replay frontend | Fixed tick, map, resource regrowth, need decay, move/gather/eat/drink/rest, death, JSON saves; random-behavior residents; frontend map replay and time controls | Seven in-game days run in seconds; invariant tests pass; save/restore works |
> | P2 · Rule-based residents & balancing | Rule-based residents; tune resource and need numbers | Survival is feasible but tight: survivable with enough resources, competition under scarcity |
> | P3 · LLM residents | Replace one, then all three; perception, structured actions, failure feedback, decision triggers, LLM recording and replay, call budget and fallback; character panel and debug view | Survival loop with no player input; no out-of-range perception; costs recorded |
> | P4 · Social & memory | Talk, ask/share/refuse, relationships; episodic memory, nightly reflection, long-term beliefs | Personality-swap and memory-ablation tests show observable differences |
> | P5 · Environment expansion | At most one herbivore; one tool | Animals and tools cause real state changes without breaking balance |
> | P6 · God & narrative | Dreams (one integration strategy), paused parameter adjustment, timeline, read-only narrative | Interventions cannot force actions; narrative only cites real events |
> | P7 · Acceptance | Full seven-day run, replay consistency, cost stats, art style samples | Meets Section 3 acceptance (including notes) |
>
> **[Claude note]** "Record human interventions, rework and regressions" is valuable; write a one-page retrospective at the end of each phase as the project-management practice output.

## 12. Risks and Mitigations

| Risk | v0.1 mitigation |
|---|---|
| LLM only chats, never acts | Action intents must go through the executor; conversations need triggers and world feedback |
| Characters know distant things they shouldn't | Observation builder strictly limits input; regression tests cover unknown info |
| Model hallucinations change game facts | Structured actions + world referee validation + failure feedback |
| LLM latency/cost stalls the world | Event-driven planning, plan reuse, call budget, timeout fallback |
| Concurrent gathering makes resources negative | Unified world resolution, deterministic action order, inventory invariant checks |
| Memory bloat, dreams becoming instruction injection | Memory summaries and retrieval budget, source tags, low-priority cognitive injection |
| Stories look great but are unrelated to the world | Read-only narrative citing event IDs; no fabricated objective events |
| Too much art/gameplay up front | Fixed gameplay acceptance line; art exploration on a separate track from core rules |
| Animal attacks crash the game early | Balance animal distribution and danger; test multiple initial states |

> **[Claude note · Suggestion]** Additional risks:
>
> | Risk | v0.1 mitigation |
> |---|---|
> | LLM too friendly; personality differences flattened | Personality-swap test; spell out personality-specific behavioral tendencies with examples in prompts |
> | Unstable LLM output format | Structured output constraints; retry once on parse failure, then fall back to rule-based behavior |
> | Two characters talk forever | Cap exchanges per conversation; talking consumes game time |
> | Hard-to-reproduce bugs, costly debugging | Random seed + LLM recording and replay |
>
> The last row, "animal attacks crash the game early", no longer applies in v0.1 since the carnivore is removed; keep it for v0.2.

## 13. Details Still to Design (do not change the 12 confirmed directions)

1. **Map spec and time scale**: tile size, game time per tick, action durations, day/night ratio.
2. **The three animal species and behaviors**: food chain, attack triggers, damage/flee rules.
3. **Initial character configuration**: backgrounds, initial goals, tool allocation, and whether all characters share an initial shelter.
4. **Model call budget and fallback strategy**: high-level decisions allowed per game day; how characters safely continue existing actions when the model is unavailable.
5. **Dream triggers and retention**: when dreams can be entered, user options to save/delete original text, automatic memory integration rules.
6. **Rule editing boundaries**: which parameters can change at runtime directly, which require pausing or a new world.
7. **UI rendering tech and art spec**: map grid, asset sizes, camera, criteria for evaluating style candidates.

These are later technical design / gameplay refinement questions and do not overturn the confirmed product direction.

> **[Claude note]** Items 1, 3 and 4 cannot be deferred and must be fixed in the P0 spec: without the time scale and action durations, the world core cannot be implemented.
>
> **[Claude note · Suggestion]** Initial values for each item:
> 1. 32×32 map; 1 tick = 10 minutes, 144 ticks per day; daytime 06:00–20:00, perception radius halved at night.
> 2. Simplified per notes: v0.1 has at most one herbivore and no attacks.
> 3. The three share an initial shelter (cave); the only tool is one axe owned by one of them — ownership alone can create "lend it or not" interactions.
> 4. The fallback is the rule-based resident; budget initially estimated at ~20 high-level decisions per character per game day, revised after measuring in P3.
> 5. v0.1 allows entering dreams only while the character sleeps; one fixed integration strategy (see the Section 6.2 note).
> 6. v0.1 only allows modifying a few parameters while paused.
> 7. Decided: React + TypeScript + Canvas; tile size initially 32 px.

---

## Appendix: Index of the 12 Confirmed Decisions

1. Seven days of autonomous running; interaction feedback is real and grounded in the world; stories have causality.
2. Fixed island, plant resources, two herbivores and one carnivore, survival and death, small starting tools for characters.
3. Fixed tick; pause/step/speed-up; advances while running; LLM calls decoupled from world updates.
4. Limited perception; knowledge comes from observation, memory and communication.
5. Basic needs set by rules; values stable; long-term goals can be generated, adjusted and abandoned.
6. LLM handles high-level planning/dialogue/reflection; code handles concrete execution and basic survival reactions.
7. Requests, dialogue, sharing, refusal, simple relationships; no complex social system.
8. Layered memory; dreams as uncertain memory input; original dialogue can be deleted or leave only scattered long-term fragments.
9. Creation-time configuration separate from runtime god intervention; dreams and faint thoughts are the main interventions; decisions are not forced.
10. No scripted plot; read-only narrative driven by objective events.
11. 2D top-down, state and event sidebars; accumulate multiple art styles during development.
12. Standalone world, 3 LLM characters, social/memory/dreams, configurable rules and saves; swappable models; no multiplayer/editor/mods/complex ecology for now.

> **[Claude note]** Decision 2's "two herbivores and one carnivore" is adjusted per the notes to at most one herbivore in v0.1, with the carnivore moved to v0.2; decision 3 adds synchronous waiting and the initial value "1 tick = 10 minutes"; decision 11 adds React + TypeScript as the frontend stack. All other decisions are unchanged.
