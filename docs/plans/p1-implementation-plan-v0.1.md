# Living Island — P1 Implementation Plan v0.1

> **Approved v0.1 (2026-11-08).** Amendment A1 (agent interface) is applied by P1-01a and
> amendment A2 (replay) by P1-01b; until then `interface-contract-v0.1.md` and
> `world-rules-v0.1.md` are unchanged.

**Milestone P1, "The World Runs":** a deterministic world runs 1,008 ticks with non-LLM
residents, saves and restores, and the run can be inspected in an offline browser replay.

**Baseline:**
- `docs/spec/world-rules-v0.1.md`, `docs/spec/interface-contract-v0.1.md` and
  `docs/spec/balance-notes-v0.1.md` (Approved v0.1);
- `docs/spec/agent-interface-v0.1.md` and `docs/spec/p1-replay-frontend-v0.1.md` (landed by
  P1-00).

## 0. Management decisions

| ID | Decision | Rule |
|---|---|---|
| PM-01 | Serial critical path, limited parallelism | At most **two active workers**, including independent reviewers: a world-core lane and a side lane (§3). A builder pauses if a review needs the second slot. No automatic increase in P1. |
| PM-02 | Milestone → task | Every task is a runnable, testable behaviour slice with a declared file scope. |
| PM-03 | Three gates | Gate 1 (executor checks) and Gate 2 (independent review) for every task. Gate 3 (project owner) only at the four milestones in §4. |
| PM-04 | Process data | Seven required handoff fields (§6). |
| PM-05 | Replay first | No live server in P1. |
| PM-06 | Saves | Version mismatch is refused; no migration. |

**P1 does not include:** LLM providers, rule-based survival intelligence, memory, relationships,
dreams, runtime rule edits, WebSocket, art. Residents may die early; that is not a P1 failure.

## 1. P1 READY gate

- [x] P0-02 world rules, content and contract landed and approved.
- [ ] Record a passing CI run URL and commit SHA for the actual P1 base; historical green
      status is not evidence for an unverified current revision.
- [ ] P1-00 merged: agent-interface and replay-frontend specs landed; AGENTS.md updated.

## 2. Tasks

Each card lists its goal, file scope, dependencies, deliverables and acceptance. Tests ship
inside each task; there is no separate "write tests later" task. Scenario fixtures (configs and
scripts) live under `backend/tests/fixtures/`. They may override numeric values, but never
rules or the default content.

### P1-00: Land the P1 design specs (documentation only)

- **Scope:** `docs/spec/agent-interface-v0.1.md`, `docs/spec/p1-replay-frontend-v0.1.md`,
  `docs/tasks/p1-implementation-plan-v0.1.md`, `AGENTS.md`, `docs/tasks/_template.md`.
- **Deliver:**
  - copy the approved drafts;
  - add both specs to the AGENTS.md spec list;
  - add the three gates, the two-lane rule and the seven handoff fields (§6) to the AGENTS.md
    workflow rules;
  - add a task-card template (§5);
  - retain the staging folder; no cleanup or deletion is authorized by this task. Any later
    cleanup requires its own explicit paths/scope and the approval required by AGENTS.md.
- **Accept:** documentation diff only; CI green.

### P1-01a: World and agent contract (critical path, single owner)

- **Scope:** model/protocol stubs in world/protocol.py, world/state.py, world/facts.py,
  world/content.py, world/ports.py; agents/base.py and agents/types.py; sim/ports.py;
  persistence/content.py; contract/save.py and events/__init__.py re-exports; backend tests;
  docs/spec/interface-contract-v0.1.md and docs/spec/world-rules-v0.1.md (amendment A1 only).
  All Python paths are under backend/src/living_island unless otherwise stated.
- **Deliver:**
  - canonical Pydantic models in the ownership locations in §2.1: `WorldState`, `Perception`,
    `BoundaryPerceptionDelivery`, `ActionPlan`, `ActionIntent`, `ActionResult`, `WorldEvent` and
    every event payload, `SavePackage`, plus the vocabularies;
  - agent-side structures: DecisionRequest, DecisionOutcome, PolicyConfig, ScriptFixture,
    DecisionRecord, DecisionTraceManifest and ResidentRuntimeState;
  - the `Policy` / `ResidentRuntime` protocols;
  - a content loader for the TOML and map, with domain validation (World Rules §1.1–§1.2);
  - amendment A1 written into the Interface Contract and World Rules. A1 must explicitly
    amend the P1 DecisionContext prohibition and clarify event-type ownership in World Rules
    §0.3; do not leave those contradictions behind a field-only list.
  - frozen observation, event-allocation and boundary observer signatures in §2.1.
- **Accept:**
  - every model field matches the contract;
  - integers only, within declared ranges;
  - unknown fields are rejected;
  - the content loader rejects broken content;
  - existing type generation still runs clean;
  - import-linter is green.
- **Milestone M1:** after this task the world/agent contract is frozen for P1. Any later
  change needs a change request (§7).

### P1-01b: Replay contract and schema export (side lane, after P1-01a)

- **Scope:** contract/replay.py; scripts/gen_types.py and generated output (including
  `frontend/src/api/generated/replay.schema.json`); frontend/package.json and
  frontend/pnpm-lock.yaml for the Ajv2020 dependency; schema smoke tests;
  docs/spec/interface-contract-v0.1.md (amendment A2 only).
- **Deliver:** `ReplayBundle` and `DisplayFrame` models (replay-frontend §2.2); generated TS
  types plus a standalone ReplayBundle JSON Schema 2020-12; an Ajv2020 smoke test proving a
  valid raw bundle is accepted and a Contract-wrapper-shaped input is refused; shared
  valid/invalid cross-field fixtures (replay-frontend §2.3); amendment A2.
- **Accept:** generated types are clean; the smoke test passes; no hand-written second schema.
  After merge, replay-schema changes also need a change request.

M1 also checks a small import example from each consumer. No aliases or re-exports may
create world -> contract/events or agents -> contract -> world.state dependencies. Internal
schemas need not all be exported to frontend; SavePackage is backend-only, ReplayBundle is
the browser input. Add real DTO validators, not a parallel untyped object tree.

### P1-02: Space and perception (world lane)

- **Scope:** `world/` modules for the map, LOS, pathfinding and perception; tests.
- **Deliver:**
  - static map and terrain;
  - Bresenham LOS (World Rules §5.1 steps 1–4);
  - Dijkstra with the two test vectors (World Rules §5.3);
  - explored footprints;
  - exposure receipts;
  - `Perception` construction with bands, signs, cues and FruitBand.
  - begin_observation_tick/observe_step/finish_observation_tick from §2.1. P1-04 calls these
    for World Rules §5.1 steps 5–7; P1-02 owns accumulation, deduplication and sampling.
- **Accept:**
  - LOS edge cases;
  - both path test vectors;
  - no hidden spring coordinates and no remote stock in `Perception`;
  - receipts authorize only exposed IDs;
  - static terrain persists while dynamic stock does not.
  - an intermediate resident sign and near cue survive in the frozen observation result;
    novelty compares against tick-start receipts even after several observation calls.

### P1-03: Physical rules (world lane, after P1-02)

- **Scope:** `world/` modules for resources, physiology, the canteen and death; tests.
- **Deliver:** pure rule functions:
  - regrowth phases (World Rules §5.5);
  - integer need decay, gains and clamping;
  - the deprivation health loss;
  - final-tick physiology (World Rules §3);
  - canteen uniqueness and capacity;
  - death, corpse and drops, with merged ground piles;
  - fruit accounting.
- **Accept:**
  - property and invariant tests: no negatives, fruit conservation, canteen in exactly one
    place;
  - the deprivation death tick matches the balance notes (222 ticks without water).

### P1-04: Actions and settlement (world lane, critical path)

- **Scope:** `world/` action state machine, event allocator and tick phases 2–6 that belong to `world`;
  tests.
- **Deliver:**
  - all 11 actions with their preconditions and failure codes;
  - multi-step move_to with budget packing and the complete observation lifecycle in §2.1;
  - the completion set with the Xorshift32 shuffle (World Rules §5.4 and §5.6);
  - the interrupt priority and terminal handling (World Rules §4.3);
  - `talk` sessions and cooldowns;
  - receipt checks before live lookup;
  - `ActionResult` and events in emission order;
  - `BoundaryPerceptionDelivery` creation.
  - the world-owned event stream, deterministic IDs and same-tick seq allocation; external
    facts such as future fallback records enter through its typed append port, not a second
    ID allocator in events/persistence. Tick-zero allocation follows the same rule.
- **Accept:**
  - every action has positive/negative tests; contention tests cover shared resource/item/
    dialogue operations, with nonapplicable cases marked N/A rather than invented contests;
  - the Xorshift32 / shuffle test vectors;
  - the same seed and inputs produce identical event order;
  - no teleporting;
  - a dead resident never acts;
  - resource/physiology/death effects reuse P1-03 functions; movement/progress/event
    bookkeeping each have one world-owned update path.

Internal checkpoints (not new tasks): movement + captured perception; survival/item actions
and death; dialogue/session actions; integrated phases and result/interrupt ordering. Each
checkpoint must have runnable tests before starting the next. Movement/plan bookkeeping
belongs here; physiology/resource effects reuse P1-03 functions instead of duplicating them.

### P1-05: Events and persistence (side lane)

- **Scope:** `events/`, `persistence/`; tests.
- **Deliver:**
  - read-only event projections/re-exports and envelope validation; verify IDs allocated by
    world, never allocate a parallel sequence here;
  - canonical JSON encoding (Interface Contract §6.3);
  - JSONL writers for events and decision records;
  - atomic snapshot write and read for `SavePackage`;
  - config and map hashes;
  - version refusal.
  - verified loading of scripts and per-actor recording slices, trace manifests,
    `resume-origin.json`, and effective typed config/map retention; no source-run log mutation.
- **Accept:**
  - identical input gives identical bytes;
  - forward causal references are rejected;
  - a bad version, hash or JSON fails clearly;
  - an existing save is never overwritten in place.
  - a resume writes only post-checkpoint records into a distinct output directory and never
    touches the source run; changed script/trace identities are refused.

### P1-06: Simulation loop and residents (world lane, critical path)

- **Scope:** `sim/`, `agents/runtime.py`, `agents/policies/`, package __main__.py; tests.
- **Deliver:**
  - the boundary phases 1 and 7: deliver and ingest, decide, queue, commit;
  - deferred triggers;
  - `ResidentRuntime`;
  - `RandomPolicy`, `ScriptedPolicy` and `RecordedPolicy`;
  - the `wait` substitute;
  - decision records;
  - save and restore wiring;
  - the CLI contract in §2.1, including resume/reexecute commands and failure behavior;
  - the optional committed-boundary observer hook, called once at fresh tick zero and each
    newly completed tick, never again for the restored checkpoint boundary. It is exercised
    with an in-memory sink before P1-07 exists; a null observer does no display IO.
- **Accept:**
  - agent-interface tests AI-01 to AI-15;
  - 1,008 ticks finish without deadlock;
  - save at tick k and restore yields the same final state and event bytes as an uninterrupted
    run, checked with a scripted long-run fixture that keeps residents alive;
  - re-execution with `RecordedPolicy` is byte-identical.
  - post-commit/pre-ingest is the only checkpoint point; every living actor has its exact
    pending packet. Typed error substitutions increment ordinals once and preserve trace
    provenance; replay divergence stops without inventing a world failure event.
- **Milestone M2:** the project owner runs the CLI and checks one run's outputs.

Internal checkpoints: ingestion/one actor with an in-memory port; policies/recording;
multi-actor queueing and all-dead continuation; persistence/resume/reexecute and the 1,008-tick
scripted run. The long fixture may explicitly set numeric satiety/hydration decay to zero
(allowed by World Rules §1.1) while exercising nontrivial actions and checkpointing; it is
labelled a mechanics fixture, never survival-balance evidence. Never alter default content.

### P1-07: Replay export (side lane, after P1-06)

- **Scope:** contract/projections.py (conversion only, no schema changes), persistence replay
  capture/export modules, and sim/cli.py observer wiring only; tests/fixtures. The runner
  hook already belongs to P1-06 and must not need a rewrite here.
- **Deliver:** `DisplayFrame` capture at every committed boundary and `ReplayBundle` export.
- **Accept:**
  - frames 0..N with no gaps;
  - each frame equals the committed state;
  - no RNG, plans, receipts or private state in the bundle;
  - the bundle validates against the frontend schema;
  - one scripted export is committed as a fixture.
  - the already merged P1-08 viewer loads that real export, seeks correctly and diagnoses
    a recorded failure (M3 smoke test); this is not a dependency on an unmerged viewer task.
  - replay-frontend FE-T13: `run` and `reexecute` capture exactly one frame per committed
    boundary; `resume --export-replay` is refused. Export/import share the replay-frontend
    §2.3 cross-field invalid fixtures from P1-01b.

### P1-08: Replay viewer (side lane, starts after P1-01b)

- **Scope:** frontend source/tests/fixtures and package.json/pnpm-lock.yaml for test
  dependencies; no hand-editing generated files. Use the Ajv2020 dependency added in P1-01b
  rather than selecting a second validator or dialect.
- **Deliver:** browser validation from replay-frontend §2.3 and the viewer in §§3–5.
  Backend capture in §2.4 belongs to P1-06/P1-07, not to this frontend task.
- **Accept:** FE-T01 to FE-T10 and FE-T12 on fixtures. Gate 1/2 permit this task to merge
  before P1-07; the subsequent real-export smoke is P1-07's integration deliverable, not
  a circular prerequisite for merging P1-08.
- **Milestone M3:** after P1-07 and P1-08, the project owner loads a real exported bundle,
  inspects a failure and seeks to the final tick. Hand-made fixtures alone are insufficient.

### P1-09: Integration and P1 acceptance (world lane, last)

- **Deliver:**
  - full 1,008-tick runs: random policy on the default content, plus a scripted long-run;
  - save/restore and re-execution comparisons;
  - viewer demo on a real export (FE-T11);
  - backend runtime, bundle size and load time recorded (no targets set in advance);
  - README steps;
  - the P1 retrospective.
- **Milestone M4:** the project owner's final P1 acceptance.

### 2.1 Frozen ownership and integration ports (M1 deliverable)

| Location | Canonical definitions / responsibility | Allowed direction |
|---|---|---|
| world/protocol.py | Perception, plans/intents/results, deliveries, public vocabularies and action target/parameter aliases | standalone world-side protocol; never imports other world internals |
| world/state.py | WorldState/ActiveAction and physical state | world internals/protocol only |
| world/facts.py | WorldEvent, payload models, pure event-ID formatting | world internals/protocol only; no IO |
| world/content.py | typed effective config/static map and validation without IO | world only |
| world/ports.py | observation accumulator/result and engine ports below | world only; implementations P1-02/P1-04 |
| agents/types.py | DecisionContext/Request/Outcome, policy/script/record/runtime-state models and ID builders | world.protocol only; no contract/persistence/private world types |
| agents/base.py | Policy and ResidentRuntime protocols | agents.types and world.protocol only |
| contract/save.py | backend SavePackage envelope, reusing canonical world/agent types | imports world/agents; neither imports back |
| contract/replay.py | browser ReplayBundle/DisplayFrame models | public vocabularies, no sim dependency |
| contract/projections.py | pure WorldState -> DisplayFrame conversion | no mutation, rules or IO; implemented P1-07 |
| events/ | re-exports/read-only projections of world facts | no sim/persistence imports |
| persistence/content.py | file reading then world.content validation | world/content models, no rule implementation |
| persistence/ | JSONL/checkpoint/trace/frame-spool IO and validation | consumes DTOs, does not produce physical effects |
| sim/ports.py, sim/runner.py, sim/cli.py | observer declaration, scheduling, bootstrap/wiring | connect modules; agents never receive private snapshots |

Canonical models may be re-exported by contract for generation; never copy them or import
contract back into world/agents. events re-exports do not become a world dependency. This
ownership clarification is explicitly part of A1, including the World Rules §0.3 wording.
All unspecified private implementation helpers may be local, but these cross-task ports
and mutation boundaries cannot change without a change request.

```text
# world/content.py; typed metadata returned by the IO-free validated content model
WorldContent { config:EffectiveConfig,map_rows:array<string>,config_hash:string,map_hash:string }
# world/ports.py; signatures are normative, bodies arrive in the indicated tasks
create_engine(content:WorldContent,restored_world:WorldState|null) -> WorldEngine
begin_observation_tick(state:WorldState, completed_tick:integer,
                       content:WorldContent) -> ObservationAccumulator   # [CR-002]
observe_step(acc:ObservationAccumulator, state:WorldState,
             actor_id:string, position:Coord, step_index:integer) -> None
finish_observation_tick(acc:ObservationAccumulator, state:WorldState) -> ObservationBatch
ObservationBatch {
  physical_samples_by_actor: array<ObservationSample>,
  new_static_tiles_by_actor: array<{actor_id:string,tile_indices:array<integer>}>,
  exposure_receipt_updates: array<ExposureReceiptUpdate>,
  new_sight_actor_ids: array<string>
}
# P1-04: these are methods of one WorldEngine instance; only engine ports mutate state
initial_commit() -> WorldTickCommit          // fresh initialization only, tick zero
begin_tick() -> None                       // open next-tick buffer/reset seq before phase 1
start_intent(intent:ActionIntent) -> None
append_fact(type:EventType, actor_id:string|null,target_id:string|null,
            intent_id:string|null,llm_call_id:string|null,
            caused_by_event_ids:array<string>,payload:TypedEventPayload) -> WorldEvent
advance_tick() -> WorldTickCommit
WorldTickCommit { snapshot:WorldState, events:array<WorldEvent>,
                  pending_deliveries:array<BoundaryPerceptionDelivery> }
# sim/ports.py: synchronous callback, not an agent interface
BoundaryObserver(snapshot:WorldState, new_events:tuple<WorldEvent,...>) -> None
run(..., on_boundary_committed:BoundaryObserver|null) -> RunResult
```

ObservationAccumulator stores **[CR-002]** a private deep copy of the verified `content`
(observe_step and finish_observation_tick read content only from it) and a read-only tick-start receipt baseline, per-actor step
samples/unions and highest observed cue detail. Observe calls modify only this accumulator,
not receipts/footprints in WorldState. Capture visible descriptor values immediately.
Use completed_tick clock/radius for all samples and the boundary scan; there is no sub-tick
clock. P1-04 moves the actor through its own engine state, calls observe_step once per entry
with consecutive 1-based step indexes, then finishes the batch after physiology. It applies
receipt/footprint updates exactly once in phase 6, and builds triggers/results/packets from
the frozen batch. ObservationSample has all Perception fields **except** heard_utterances
and last_action_feedback; P1-04 attaches settlement hearing and terminal-result feedback
after resolving interrupts. P1-02 does not cancel actions or allocate event IDs. ExposureReceiptUpdate
is `{actor_id, entities, cue_detail_seen}` using Interface Contract §2.1 receipt entry types;
arrays are sorted and duplicate-free. Batch arrays sort by actor ID. Initial tick-zero scan
uses the same sampler without movement, seeds receipts and creates no NEW_SIGHT interrupt.
The receipt baseline is an immutable copy, so finishing/committing the batch cannot erase
the first-exposure comparison. Freezing the completed-tick radius convention requires its
explicit World Rules §5.1 clarification under A1.

EffectiveConfig is the typed TOML tree from world/content.py, with the landed field names;
persistence/content.py returns validated WorldContent with canonical config/map hashes.
create_engine initializes a fresh world or restores the supplied physical snapshot against
those verified content identities. Restoring must not regenerate initial resources/receipts
or initialization events; sim restores pending packets from SavePackage separately.

WorldTickCommit.snapshot/events are immutable copies, never references to mutable engine
objects. P1-04 owns tick numbering/event seq and buffers all facts, including boundary facts
submitted by sim before advance_tick. Sim calls begin_tick once before phase-1 input,
resetting seq to zero for the next completed tick; repeated/overlapping begin calls are
programming errors. start_intent queues an intent to start in phase 2, not an early physical
effect in phase 1. append_fact returns the allocated ID immediately for
utterance/causal references and rejects forward references. P1-05 only validates/serializes
these records. After a tick, sim flushes committed events/decisions, calls the observer,
flushes its optional spool, then writes any requested checkpoint. A callback/write error
stops the run; it never retries ingestion or silently omits a frame. Physical commit creation
is P1-04; durable publication/checkpoint orchestration is P1-06. This is the sole commit path.

CLI entry is `python -m living_island` (__main__.py delegates to sim/cli.py):

```text
run --config PATH --ticks N [--seed N] --policy random|scripted
    [--script PATH] --out NEW_DIR [--checkpoint-every N] [--export-replay]
resume --checkpoint PATH --source-run DIR --ticks ADDITIONAL_N --out NEW_DIR
reexecute --source-run DIR --out NEW_DIR [--export-replay]
```

Ticks may be zero; checkpoint interval must be positive. A CLI seed override changes the
effective typed config before hashing and world/RNG/policy initialization. Script is required
only for scripted mode; reject incompatible flags. Resume restores the saved policy/config,
not a command-line replacement, writes only post-checkpoint records plus `resume-origin.json`,
and refuses `--export-replay` (use `reexecute --export-replay` for a full bundle).
Reexecute runs from tick zero with RecordedPolicy, the immutable source manifest/config/map,
and source run_id; it does not invent a fresh run ID. Output paths must be distinct from
source paths and contain no existing run artifacts. Replay validation errors exit nonzero
with REPLAY_DIVERGED diagnostics, never a fabricated world event. P1-06 accepts the export
flag but rejects it as unavailable until P1-07 wires the observer; no pretend export file.
Always write tick-zero and final checkpoints (one checkpoint for a zero-tick run);
--checkpoint-every adds intermediate positive multiples. Copying a run never changes its
logical WorldState.static_map_ref: retain the configured relative reference, resolve it
to verified map.txt outside world, and never include an absolute/output path in world state.

## 3. Order and lanes

```text
P1-00 ─ P1-01a (M1)
          ├─ World lane: P1-02 ─ P1-03 ─ P1-04 ─ P1-06 (M2) ─ P1-09 (M4)
          └─ Side lane:  P1-01b ─ P1-05 ─ P1-08 ─ P1-07 (M3) ──┘
                         (P1-05 must merge before P1-06 starts)
```

- **Two workers, two lanes.** Each task uses its own task branch and an isolated worktree.
  Use the environment's managed worktree tools when provided; otherwise follow its approved
  Git workflow. Rebase/update from the accepted main revision before the next task. A lane
  is a scheduling role, not a long-lived branch that accumulates unreviewed tasks.
- Lanes never edit the same files. `contract/save.py` belongs to P1-01a and
  `contract/replay.py` to P1-01b; after each merges, changes go only through a change request
  handled by one owner.
- Merge order follows the arrows. Each merge into `main` is preceded by Gate 1 and Gate 2.
- The order P1-02 → P1-03 keeps the world lane serial. P1-08 may build on hand-made fixtures
  while the world lane runs; M3 waits for P1-07's real export. Reviewers use an available
  worker slot, pausing execution if necessary; do not implicitly create a third active worker.

## 4. Gates and milestones

- **Gate 1, executor:** run every AGENTS.md check and record the exact command, exit code and
  test counts. Anything not run is recorded as `NOT_RUN`.
- **Gate 2, independent reviewer:** check against the frozen specs for:
  - ownership;
  - leaks;
  - unapproved rules;
  - randomness and replay;
  - unnecessary abstraction.

  Findings are tagged `BLOCKER` / `MAJOR` / `MINOR` with file:line and evidence. Any blocker
  stops the merge; any unresolved MAJOR also blocks it. MINOR items need a documented disposition.
- **Gate 3, project owner, at milestones only:**
  - M1: world/agent contract frozen (after P1-01a);
  - M2: the CLI runs 1,008 ticks deterministically;
  - M3: the viewer works on a real P1-07 export (fixtures remain regression tests);
  - M4: final P1 acceptance.

## 5. Task-card template (`docs/tasks/_template.md`)

```text
Task ID / title:
Spec baseline (commit SHA):
Goal / non-goals:
Lane / depends on:
Allowed files / forbidden dependencies:
Deliverables:
Acceptance (positive, negative, edge, determinism):
Verification commands:
Open risks / deferred decisions:
```

## 6. Handoff record (in `docs/tasks/<phase>/<id>.md`, per AGENTS.md)

Required fields:
1. `base_commit` and `result_commit`;
2. `status`: `READY_FOR_REVIEW` / `CHANGES_REQUESTED` / `ACCEPTED` / `BLOCKED`;
3. `scope_changed`: yes or no, and who approved it;
4. `human_interventions`: count and reasons;
5. `rework_rounds`: count and root causes;
6. `verification`: commands, exit codes, test counts, `NOT_RUN` items;
7. `open_questions`.

Unknown values are written as unknown, never as zero. The P1 retrospective is computed only from
these records.

These seven measurement fields do not replace the AGENTS.md Handoff prose: include what
changed, commands/results, deviations and open questions. No result commit is invented before
one exists. Four milestone sign-offs cover routine acceptance; a blocking spec decision is
escalated when found rather than waiting for the next milestone.

## 7. Change requests

When a spec contradiction is found:
1. stop;
2. write a change request in `docs/spec/open-questions.md` with the impact, options and a
   recommendation;
3. the project owner decides;
4. one owner updates the spec, contract and ADR, then regenerates types and fixtures.

Downstream agents never edit frozen contracts on their own.

## 8. P1 acceptance matrix

| ID | Must hold | Evidence |
|---|---|---|
| A01 | Default content loads and validates | content tests |
| A02 | 1,008 ticks complete | CLI exit 0, outputs present |
| A03 | Resource, physiology, canteen and death rules hold | invariant tests, death scenario |
| A04 | Residents act only through the policy interface | AI tests; `WorldState` untouched |
| A05 | Perception is limited; world is isolated from memory | leak tests, import-linter |
| A06 | Deterministic | identical state and event bytes on re-execution |
| A07 | Save/restore keeps active actions and queues | restore comparison |
| A08 | Bad versions and hashes are refused | persistence tests |
| A09 | Offline replay of a real run | frames 0..1008 match committed states |
| A10 | Basic debugging | current action, inventory, failures, filters |
| A11 | CI and generated types clean | CI run on `main` |
| A12 | Records complete | handoffs, reviews, M1–M4 sign-offs, retrospective |

**Allowed:** early deaths, sparse events, dull stories.
**Not allowed:** resources from nowhere, hidden-state leaks, unrecorded randomness, actions that
bypass rules, a viewer that re-computes the world, a save that cannot continue the same action.
