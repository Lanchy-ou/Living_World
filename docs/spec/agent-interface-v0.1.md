# Living Island — Agent Interface Spec v0.1

> **Approved v0.1 (2026-11-08).** Amendment A1 (agent interface) is applied by P1-01a and
> amendment A2 (replay) by P1-01b; until then `interface-contract-v0.1.md` and
> `world-rules-v0.1.md` are unchanged.

**Scope:** how a resident's decision-maker connects to the world. It defines the runtime and
policy interfaces, plan handling, P1 policies, decision records and save state. It does **not**
change physical world rules. Its proposed contract additions and ownership/context
clarifications are listed in §8; they are not approved or effective until amendment A1
lands in P1-01a. In particular, using DecisionContext in P1 requires explicitly amending
the current prohibition in Interface Contract §2.3.

> **[CR-005] M8 approved and applied, 2026-11-12.** P3 clauses below are normative;
> their versioned lane preserves the P1/P2 contract. See [M8 record](../tasks/p3/M8-decisions.md).

## 0. Decisions and phase boundaries

### 0.1 Confirmed direction

| ID | Decision | Engineering meaning |
|---|---|---|
| AG-01 | Versioned resident-local DecisionContext for each policy lane | P1/P2 retain their existing empty-memory DecisionContext. P3 policies receive DecisionContextP3, assembled in agents from the delivered Perception and that resident's own identity, goals and experience. No context is shared between residents. The P3 frozen-rule adapter maps only the allowed own inputs to the unchanged P2 context. |
| AG-02 | One decision returns an `ActionPlan` of 1..`agents.max_plan_actions` world actions (default 5) | `move_to` counts as one intent however many tiles and ticks it takes. |
| AG-03 | Replanning is event-driven | Without triggers the runtime keeps executing its queued plan (World Rules §4.4). |
| AG-04 | On LLM failure a rule-based policy takes over temporarily | The fallback uses the same resident's context only. It is logged (`agent_fallback_used`). Real fallback arrives in P2/P3. |

### 0.2 Phases

- **P1:** the runtime and policy interfaces; `RandomPolicy`, `ScriptedPolicy` and
  `RecordedPolicy`; plan validation and queuing; perception ingestion; decision records; save and
  restore of runtime state.
- **P2:** `RuleBasedPolicy` on the same interface, surviving without hidden map knowledge.
- **P3 [CR-005]:** LLMPolicy, bounded resident experience captured at every delivered
  boundary, deterministic retrieval, one current short-term commitment and recorded
  cognitive updates. Includes provider adapter, structured output, budget, timeout,
  bounded retry, stateful rule fallback, model-call records and recorded re-execution.
  Simulated time stays frozen while a decision is pending. The P3 character panel and
  developer debug view consume a separate read-only inspection artifact.
- **P4/P6:** consolidation, psychological forgetting, reflection, long-term belief and
  relationship rules, emotions, dreams and cognitive tools. P3 names extension ports
  and their owners only; bounded working-buffer eviction is not a forgetting model.
- **Deferred, not to be built early:** MCP, parallel model calls, agent-to-agent protocols,
  general plan interpreters or plugin frameworks.

### 0.3 Ownership

| Module | Owns | Must never |
|---|---|---|
| `world` | `WorldState`, action legality and settlement, `Perception`, `BoundaryPerceptionDelivery`, canonical physical fact models and event ID allocation | import any other `living_island` subpackage, including `contract`/`events`; trust model claims |
| `agents` | `ResidentRuntime`, policies, `DecisionContext` assembly, plan **structure** validation, decision records | write `WorldState`; read another resident's private state or the full map |
| `sim` | boundary phases, delivery, decision scheduling, plan queues, starting intents in `world`, checkpoints | change resources, positions or conditions except through `world` |
| memory (small P3 foundation; richer systems later) | Resident-local bounded experience, provenance and deterministic retrieval | import agents, sim, persistence or contract; inject unobserved facts; settle actions or perform IO |
| `persistence` | loading content/scripts/recordings and reading/writing snapshots and JSONL | compute rules; produce facts |
| `events` | re-exports of canonical fact models and read-only projections | allocate IDs independently; import `sim`/`persistence` |

## 1. Concepts and data flow

- **World action:** one of the 11 actions in World Rules §4.2. Consumes ticks, is validated and
  settled by `world`.
- **Cognitive operation:** recall, goal evaluation, reflection, model calls, parsing. Costs **zero
  ticks** (real time and budget only) and can never change world facts.
- **`BoundaryPerceptionDelivery`:** the per-actor packet world creates at every completed
  boundary (Interface Contract §2.2). It must be delivered to the resident's runtime exactly once,
  **whether or not a decision follows**.
- **`DecisionContext`:** `Perception` plus that resident's own profile, goals, memories, beliefs
  and plan summary (Interface Contract §2.3, still provisional).
- **`ActionPlan` / `ActionIntent`:** a proposal. `ActionResult` / `ActionFeedback` is the world's
  verdict; the resident only receives `visible_feedback`.

```text
world (phase 6) --> BoundaryPerceptionDelivery per living actor
sim   (phase 1) --> runtime.ingest(packet)          for every living actor, ascending actor_id
sim   (phase 1) --> runtime.decide(request)         only for idle actors that need a plan
runtime         --> policy.decide(request), validate structure --> DecisionOutcome
sim             --> queue effective plan, record + commit decision, start intent in world
world (phase 2..6) --> progress, settle, results, events, next packets
```

A resident never calls `world` directly. It only returns proposals; `sim` drives `world`.

## 2. Interfaces

### 2.1 `ResidentRuntime` (one instance per resident)

```text
ResidentRuntime {
  actor_id: string
  ingest(delivery: BoundaryPerceptionDelivery) -> None
  make_request(tick:integer,triggers:array<DecisionTrigger>) -> DecisionRequest
  decide(request: DecisionRequest) -> DecisionOutcome
  commit_decision(record: DecisionRecord) -> None
  export_state() -> ResidentRuntimeState         // for SavePackage, §6
}
```

**`ingest`** is called once per pending packet before any decision at that boundary,
in ascending actor_id order. It updates the runtime's private state: in P1/P2,
the latest Perception and decision bookkeeping; in the opt-in P3 lane, experience
ingestion and goal-evidence reduction under resident-experience-v0.1.md and
resident-cognition-v0.1.md. P1/P2 rule cue capture remains decision-only under
OQ-056; P3 does not reinterpret the frozen rule policy's private state. After it returns, `sim`
  advances `delivered_perception_ticks` for that actor (Interface Contract §5), then removes
  the pending packet. Validate actor ID, delivery ID and strictly consecutive observed ticks;
  a duplicate, gap or mismatched packet stops the run. It must not fail
  silently: an exception is a programming error and stops the run.
- **`decide`** delegates to the active policy and returns a finite outcome. It never loops or
  retries without bound (§2.4). Runtime converts a malformed normal plan to INVALID_PLAN;
  a malformed recorded plan is REPLAY_DIVERGED. No structure validation lives in frontend.
- **`make_request`** assembles context inside agents from the latest ingested packet and
  own profile/state. Require request tick=Perception.tick and actor/ordinal matching the
  runtime; a cold/stale runtime cannot decide. Sim supplies ordered deferred triggers,
  not private context from another actor. At most one request may await commitment.
- **`commit_decision`** is called by sim after it queues the effective plan and buffers the
  matching DecisionRecord. It validates this actor/current ordinal and advances the ordinal
  once, completing the policy-state transaction. Clear deferred triggers only then. A
  duplicate commit is a programming error. export_state refuses a half-committed decision;
  no save or next tick is allowed between decide and commit_decision. A stopped replay
  never commits its failed request.
- The runtime holds the resident's policy configuration, `decision_ordinal` and, from P3, the
  fallback policy. Switching to the fallback happens **inside** the runtime and is recorded.

### 2.2 `Policy`

```text
Policy {
  policy_id: string                               // e.g. "random-v0", "scripted-v0", "recorded-v0",
                                                  // "rule-based-v0" [CR-004]
  decide(request: DecisionRequest) -> DecisionOutcome
  export_state() -> object{}                     // policy-private state for saving; {} if none
}
DecisionRequest {
  actor_id: string,
  tick: integer,                                  // the boundary being decided
  decision_ordinal: integer,                      // 0-based count of this actor's decisions
  triggers: array<DecisionTrigger>,               // ordered, deduplicated (Interface Contract §2.5)
  context: DecisionContext
}
DecisionOutcome =
    { status: "ok",    policy_id: string, plan: ActionPlan }
  | { status: "error", policy_id: string, error_kind: DecisionError, detail: string }
  | { status: "replayed", policy_id: "recorded-v0", source_record: DecisionRecord }
```

- **Triggers use the landed vocabulary** (`ACTION_FAILED`, `ACTION_INTERRUPTED`, `URGENT_NEED`,
  `DIRECT_SPEECH`, `NEW_SIGHT`, `UTTERANCE_HEARD`, `REPLY_REQUIRED`, `WOKE`, `PLAN_FINISHED`),
  passed as an ordered array. Only the first request for each actor at tick zero has
  `triggers = []`; later requests need one or more deferred triggers. No new trigger
  code is introduced.
- **`DecisionError` (legacy P1/P2):** `INVALID_CONTEXT`, `INVALID_PLAN`,
  `SCRIPT_EXHAUSTED`, `REPLAY_DIVERGED`. P3 uses a separate DecisionErrorP3 in
  section 2.6; it does not widen this legacy serialized enum. Policy errors are
  never world failure_code values.
- **IDs are deterministic:** `plan_id = "<actor_id>:p<decision_ordinal, minimum 6 digits>"`
  and `intent_id = "<plan_id>:i<zero-based decimal index>"`. Use unbounded integer formatting,
  not truncation; index is below the configured plan limit. Shared pure builders in
  `agents/types.py` allocate these IDs; policies do not invent alternative formats.
- A decision uses `next_decision_ordinal`, starting at 0. After accepting either a normal
  plan or the error/wait substitute, increment it exactly once. Replayed decisions advance
  it once too. A stopped replay or unexpected exception cannot advance the committed cursor.
  No checkpoint is permitted during this decision transaction (§6).

### 2.3 `DecisionContext` in P1

`perception` is required and comes only from the delivered packet. `personality_profile` comes
from content (`profile_id`, `values: []`); `current_goals` holds the configured `initial_goal`
as `{goal_id: "initial", text, priority: 0}`. `recalled_episodes` and `beliefs` are `[]`, and
`current_plan_summary` is `null`. P1 must not fake memories. The unified shape does **not** mean
residents share context.

### 2.4 World actions vs cognitive operations

| Activity | Game time | Owner | Can change world facts? |
|---|---|---|---|
| Recall, evaluate goals, reflect, call a model, parse output | 0 ticks | `agents` / `memory` | No |
| `move_to`, `gather`, `eat`, `drink`, `fill_canteen`, `rest`, `sleep`, `give`, `pick_up`, `wait` | per World Rules | `world` | Yes, after validation |
| `talk` | per World Rules | `world` records the utterance | Produces an audible event |
| Dreams (P6) | simulation paused | player + `memory` | No |

**No zero-time loops.** `decide` must return within a bounded number of internal steps. P1
policies are single-step. The P3 limits on tool calls, tokens and latency belong to a separate
P3 spec; P1 implementers must not invent them.

### 2.5 Initialization and restoration

```text
PolicyConfig {
  policy_id: "random-v0"|"scripted-v0"|"recorded-v0"|"rule-based-v0", // [CR-004]
  seed: integer,                       // effective meta.seed, not a hidden RNG stream
  max_plan_actions: integer,           // effective agents.max_plan_actions
  map_width: integer, map_height: integer, // public grid bounds, no terrain/resource contents
  script_sha256: string|null,          // canonical ScriptFixture identity, scripted only
  source_trace_sha256: string|null,    // canonical DecisionTraceManifest identity, recorded only
  rule_params?: RuleParams             // [CR-004] present iff rule-based-v0, absent otherwise;
                                       // rule-policy-v0.1.md §8
}
OwnProfile { profile_id:string,initial_goal:string }
create_runtime(actor_id:string,policy_config:PolicyConfig,own_profile:OwnProfile,
               own_script:ActorScript|null,own_records:array<DecisionRecord>|null,
               restored_state: ResidentRuntimeState|null) -> ResidentRuntime
```

`own_profile` supplies only this resident's configured profile ID and initial goal.
`own_script` is `ActorScript|null`; `own_records` is `array<DecisionRecord>|null`.
`persistence` loads and validates files, and `sim` injects only the matching actor's slice.
Policies perform no file IO, never receive WorldState/full maps, and never open recordings
or scripts themselves. Only the required slice is non-null for scripted/recorded policies;
random needs neither. Config seed, plan limit and grid bounds must match the effective typed config.
Script/trace hashes must match the loaded inputs; missing actors, unknown policy IDs or
mismatched identities are startup errors, not wait substitutes. Paths are locators, not identity.
Creation starts ordinal/cursor at zero. Restore validates config and actor identity before
restoring counters. PolicyConfig is immutable and saved, so restore cannot silently swap
the seed, script, recording or policy version. All new P1-only version fields below are
the literal `"0.1"`; unknown versions are refused without migration.

**[CR-004] Rule lineage on restore.** `rule_params` is omitted from serialization when
null, so P1 `PolicyConfig` bytes are unchanged; an explicit `"rule_params": null` is
refused. When a restore has `rule_lineage` (a `rule-based-v0` runtime in the save or in
an ancestor checkpoint, or a `rule-based-v0` record in the verified decision prefix), the
restore rules and rejections RJ-1 to RJ-8 of CR-004 (`open-questions.md`, "CR-004")
apply. Without `rule_lineage`, restore is unchanged.

### 2.6 [CR-005] Opt-in P3 lane

P1/P2 interfaces, PolicyId values, version 0.1 serialization and reference hashes
remain unchanged. P3 uses the closed, explicitly versioned DecisionRequestP3,
DecisionContextP3, P3PolicyConfig, ResidentRuntimeStateP3 and DecisionRecordP3
specified by the P3 package. Their registry is p3-implementation-plan-v0.1.md
section 1; their owning definitions, validation and ordering are normative:

- resident-experience-v0.1.md owns experience, source references, retained own intents,
  retrieval/profile binding, DecisionContextP3, ProviderProjection and inclusion
  manifests recording the actual selected strategy;
- resident-cognition-v0.1.md owns identity/prompt inputs, GoalChange/GoalState and
  completion evidence, model-facing action descriptions and DecisionProposal;
- llm-decision-v0.1.md owns CognitiveDelta, permitted operations, the provider port,
  private policy state, decision transaction, call/budget records, durable case
  allocation ownership and recovery.

The P3 primary policy is llm-v0 for registered llm_actor_ids and rule-based-v0 for
other configured actors. Every actor uses P3 envelopes; deliberate rule-only decisions
are successful rule decisions, not LLM errors or fallback substitutions. recorded-p3-v0
is a no-call execution transport preserving recorded configuration/provenance. The new
LLM/replay IDs do not widen the legacy PolicyId union. Unknown versions are refused without implicit migration.
The P3 error vocabulary is INVALID_CONTEXT, INVALID_PLAN, INVALID_DELTA, PARSE_ERROR,
TIMEOUT, BUDGET, PROVIDER_ERROR and REPLAY_DIVERGED; the last stops before commit.
Detailed classification is owned by llm-decision-v0.1.md.

Resident cognitive state is distinct from policy-private rule/LLM bookkeeping and
from coordinator-owned spend. Ingestion and goal evidence stage and publish together;
failed decisions cannot undo ingestion. An accepted plan and CognitiveDelta commit
as one decision, with the matching ordinal, record, references and private-state
changes. Cognitive updates never write world state. Only delivered own feedback
can establish the physical completion allowed by the goal specification.

## 3. Plans

### 3.1 Validation (two layers)

1. **Structure (in `agents`, before queuing):**
   - `actor_id` matches;
   - `created_at_tick` equals `request.tick`;
   - the plan has 1..`PolicyConfig.max_plan_actions` intents;
   - IDs follow §2.2;
   - each `action_type`, `target` kind and `parameters` shape matches Interface Contract §2.4.

   A violation gives `error_kind = INVALID_PLAN`.
2. **Legality (in `world`, at action start and completion):** everything else. A plan that
   claims to see something does not make a remote action legal.

### 3.2 Queue and execution

- Intents execute in order, one physical action per actor per tick (World Rules §4.1). Nothing is
  pre-settled.
- A failed or interrupted action discards the unstarted remainder. The next decision happens at
  the next idle boundary with the generated trigger (World Rules §4.3, §4.4).
- While an action runs, the runtime still ingests every packet. Triggers that do not interrupt
  that action are deferred and stored (`deferred_decision_triggers`) until the actor is idle.
- At most one decision per actor per boundary.

### 3.3 Policy failure handling

- **P1:** a policy error from Random/Scripted is a defect. `sim` records it and substitutes a
  single-intent `wait` plan with `policy_id = "sim-fallback-wait"`, so time still advances. Test
  runs assert that this never happens unless the test caused it on purpose (AI-09).
  `REPLAY_DIVERGED` is different: it **stops the run**, because a replay that diverges is
  invalid. A bad recorded plan also stops with `REPLAY_DIVERGED`; it never becomes a new
  wait substitute. Unexpected exceptions stop the run rather than being hidden as policy errors.
  P1 policy faults are recorded in DecisionRecord only; do not invent an
  `agent_fallback_used` world-event reason outside the frozen catalog.
- **P3 [CR-005]:** Use the bounded classification, retry and stateful frozen-rule
  adapter lifecycle in llm-decision-v0.1.md. The next eligible decision may attempt
  the LLM only when the recorded authorization/budget permits. Valid world failures
  are feedback, not provider errors. The existing agent_fallback_used event uses
  only its frozen reason vocabulary, with detailed P3 failures in the decision log.
  A typed fallback failure uses the existing wait substitute; programming exceptions
  and replay divergence stop. No rejected attempt partially changes cognition.

### 3.4 Parallel model calls (future, not P1)

Parallel model calls are deferred beyond P3. P3 calls and commits actors serially
in canonical actor order. Any future parallel implementation requires a separate
review preserving the same boundary inputs and deterministic commit order.

## 4. P1 policies

### 4.1 `RandomPolicy` (`random-v0`): test traffic, not intelligence

It returns a **single-intent** plan using only delivered `context.perception` and the explicit
static PolicyConfig (seed, plan limit and public grid bounds), never hidden map contents.

**Candidate categories, in this fixed order** (a category is available only if it has at least
one target):

1. `wait`: always available.
2. `rest`: available when the stamina band is `critical` or `low`.
3. `sleep`: available when the stamina band is `critical`.
4. `eat`: available when own `fruit_count > 0` and the satiety band is not `strong`.
5. `drink` from the spring: available when a visible `spring` tile is Manhattan-adjacent and the
   hydration band is not `strong`.
6. `drink` from the canteen: available when `canteen_servings > 0` and the hydration band is not
   `strong`.
7. `fill_canteen`: available when the actor holds the canteen and a visible `spring` tile is adjacent.
8. `gather`: one target per visible, Manhattan-adjacent `fruit_tree` whose band is not `empty`,
   sorted by entity ID.
9. `pick_up`: one target per visible, adjacent `ground_fruit` (quantity 1) or ground `canteen`,
   sorted by entity ID.
10. `move_to`: targets are explored passable tiles at Manhattan distance 1–10, plus unexplored
    frontier tiles adjacent to an explored passable tile (World Rules §4.2). Apply the same
    distance 1–10 bound to both sets; deduplicate coordinates and sort by `(y, x)`.

`talk` and `give` are not random candidates. Social actions are exercised by `ScriptedPolicy`
tests. Same-tile interaction is included in "adjacent" (distance <=1). Known passable terrain
is beach/grass/woods/cave/fruit_tree/damp_moss. Frontier coordinates must be inside the
public PolicyConfig grid bounds, neighbor an explored passable tile and not already be
explored. Actual unknown terrain is never inspected; the world may reject it as impassable.

Each wait/rest/sleep/eat/drink/fill category has one candidate. Set `target=null` except
fill, whose target is the owned canteen ID. Drink has its stated source; other such actions
have `{}` parameters. Gather targets its exposed tree ID; pickup targets the item's tile,
quantity 1 and the matching item type. Move targets its tile. Every generated `reason` is
null. Null canteen servings count as no canteen candidate. Deliberately do **not** filter
by hidden stamina, inventory room, path reachability or canteen fullness: world failures
such as EXHAUSTED/INVENTORY_FULL/NO_PATH/ALREADY_FULL are legitimate test traffic, not policy
errors. The policy never duplicates world legality checks.

**Deterministic choice:** compute
`h(stage) = uint64_be(SHA-256(UTF8("<seed>|<actor_id>|<decision_ordinal>|<stage>"))[0:8])`.
Seed, ordinal and stage use decimal text without padding; seed comes from PolicyConfig.
Stage 0 picks the category: `h(0) mod (number of available categories)`. Stage 1 picks the
target within it: `h(1) mod (number of targets)`. The policy never touches `resolution_rng` and
has no saved state; the same inputs always give the same plan. Modulo bias is acceptable for a
test policy.

Early deaths are allowed in P1 and say nothing about balance. Their frequency/timing is
unmeasured; this spec does not predict death within a particular number of days.

### 4.2 `ScriptedPolicy` (`scripted-v0`): deterministic scenarios

```text
ScriptFixture {
  script_schema_version:"0.1", actors:array<ActorScript> // unique, sorted actor_id
}
ActorScript {
  actor_id:string, on_exhausted:"error"|"wait",
  plans:array<array<IntentTemplate>>
}
IntentTemplate { action_type:ActionType,target:ActionTarget,parameters:ActionParameters,
                 reason:string|null }
```

- All fields are required; unknown fields are rejected. Each authored plan has
  1..max_plan_actions templates. An empty plans array is allowed with explicit exhaustion
  behavior. Every configured resident must have one actor entry; no extra actor is allowed.
- The SHA-256 of canonical parsed ScriptFixture JSON, including all actors, is its identity.
  `persistence` verifies this and passes only ActorScript for this actor to the runtime.
- On each decision, return plans[cursor] with shared ID builders, then advance cursor once.
  At exhaustion, `error` returns SCRIPT_EXHAUSTED; `wait` returns a normal single wait plan.
  Both leave cursor at len(plans); subsequent decisions keep the same exhaustion behavior.
- Saved state is `{cursor:integer}`, in `0..len(plans)`, checked against the same script hash.
  Cursor movement and ordinal/record acceptance belong to one transaction; an unexpected
  exception stops the run without a checkpoint of partial progress.
- Purpose: the scenario tests a random policy cannot reliably produce. Examples: two residents
  racing for the last fruit; a death with drops and a pick-up; handing over the canteen; a
  request followed by a refusal; long save/restore runs with residents kept alive.
- It goes through the same validation and world rules as any policy.

### 4.3 `RecordedPolicy` (`recorded-v0`): re-execution

- It receives validated, immutable records for **this actor only** from persistence,
  indexed by decision_ordinal. It performs no file IO.
- Require a record for the current ordinal and exact actor/tick/triggers/request hash
  match. Missing/duplicate/out-of-order records, wrong versions or an invalid recorded
  effective plan are REPLAY_DIVERGED, never a newly substituted wait. Requests include
  the full delivered P1 context, so changed observations cannot pass solely because the
  tick and trigger labels happen to match. Sim/persistence validate every source run_id
  against the manifest and effective config before injecting per-actor records.
- Return `status="replayed"` with the source record. Sim queues that record's effective
  plan and preserves its original policy/error/substitution/llm_call_id provenance in the
  output decision log, including an original error/wait substitute. Do not recategorize
  that historical error as a fresh RecordedPolicy failure. Internal runtime config remains
  recorded-v0; it need not equal the source policy ID in the preserved record.
- Sim compares emitted world-event bytes to the source event stream at each commit and
  the final canonical WorldState hash to the source manifest. All source decisions/events
  must be consumed at the end; leftover/missing entries stop with REPLAY_DIVERGED.
- This supplies the P1 recording boundary P3 can extend; it does not implement LLM IO,
  retry or budget handling early.

### 4.4 `RuleBasedPolicy` (`rule-based-v0`) [CR-004]

Specified in `rule-policy-v0.1.md`.

## 5. Decision records

Each decision appends one canonical JSON line to `runs/<run_id>/decisions.jsonl`, written by
`persistence`. It uses the same canonical encoding as world events (Interface Contract §6.3).
These records are **not** `WorldEvent`s.

```text
DecisionRecord {
  record_schema_version: "0.1", run_id: string,
  tick: integer, actor_id: string, decision_ordinal: integer,
  policy_id: string, effective_policy_id: string, triggers: array<DecisionTrigger>,
  request_sha256: string,
  status: "ok"|"error", error_kind: DecisionError|null,
  plan: ActionPlan,                       // the plan actually queued, including the wait substitute
  substituted: boolean,                   // true when sim queued the wait substitute
  llm_call_id: string|null                // null until P3
}
DecisionTraceManifest {
  trace_schema_version:"0.1",run_id:string,config_hash:string,map_hash:string,
  final_tick:integer,record_count:integer,event_count:integer,
  decisions_sha256:string,events_sha256:string,final_world_sha256:string
}
```

Hashing always uses the canonical UTF-8 encoding in Interface Contract §6.3. Every SHA-256
field uses a lowercase 64-digit hexadecimal digest. The request
hash covers the complete DecisionRequest object (including context); log hashes cover
exact JSONL bytes with final LF. World hash covers the canonical final WorldState object,
without a trailing LF. The manifest is `decision-trace.json`; its canonical object hash
is PolicyConfig.source_trace_sha256. Its reference source run is immutable; these checks
prove agreement with that supplied reference, not authenticity of an independently edited
manifest. `persistence` verifies trace versions, file hashes/counts and contiguous per-actor
ordinals before replay. Sim enforces tick/triggers/request and world-output comparisons.

A committed normal decision has status ok, error_kind null, substituted false and matching
policy_id/effective_policy_id. A typed error has status error, non-null error_kind,
substituted true and effective_policy_id `sim-fallback-wait`; its effective wait intent has
null target/reason and empty parameters, with the same request ordinal's deterministic IDs.
No P1 record uses a null effective plan. Replayed decisions preserve the complete source
record, not a new record claiming the source policy ran again.

Decision records are buffered in boundary actor order, then flushed at commit. Partial
decisions do not become checkpoints. `decisions.jsonl` is distinct from P3's future model
call log; do not repurpose llm_record_cursor as its cursor. P1 preserves llm_call_id=null.

**[CR-005] P3 records.** The version 0.1 shapes and files above are unchanged.
P3 uses DecisionRecordP3 version 0.2 and the distinct context, dispatch and terminal
call records in llm-decision-v0.1.md. That specification owns all log names, links,
request/projection/state identities, attempt ordering, usage and committed cursors.
Record exact inputs, available raw responses, parsed results/errors and versions;
missing usage is unknown. Diagnostics are not unrecorded sources of simulation state.

## 6. Save and restore

The `SavePackage.agent_state` (Interface Contract §5) gains one entry per resident:

```text
ResidentRuntimeState {
  actor_id: string, policy_config: PolicyConfig,
  next_decision_ordinal: integer,
  policy_state: object{},                 // {} for random/recorded; {cursor} for scripted;
                                          // RuleStateV0_1 for rule-based (rule-policy §7) [CR-004]
  latest_perception_tick: integer         // -1 before the first ingest
}
```

- Queued plans, deferred triggers, delivery cursors and pending packets are already part of the
  landed `SavePackage`.
- **P1 save point:** only post-commit phase 7, before phase-1 ingestion of that boundary.
  Tick-zero initialization has the same save point. Every living actor has exactly one
  pending packet for the saved world tick. An after-ingest/before-decide checkpoint is
  explicitly unsupported in P1; refuse it rather than regenerating missing transient data.
  Thus latest_perception_tick is bookkeeping only: its full older cache is not needed on
  restore, because the mandatory pending packet is ingested before any decision. A restored
  runtime is cold and cannot decide before that fresh ingest. Cursor and tick consistency
  are validated; dead actors have no pending packet and never decide.
- A1 adds one root SavePackage field, `decision_record_cursor:integer`: the number of
  committed decision records. `event_cursor` equals `world.event_log_cursor`. Runtime ordinals
  count accepted decisions including substitutes, so their sum equals
  `decision_record_cursor`.
- **Resume is continuation-only.** Restore verifies config/map hashes, runtime inputs and the
  checkpoint's internal consistency (cursors, ordinals, one pending packet per living actor),
  then writes into a **new output directory** only the events and decisions produced *after*
  the checkpoint, plus `resume-origin.json`:
  `{source_run_id, checkpoint_tick, checkpoint_sha256, event_cursor, decision_record_cursor}`.
  It never copies, truncates, overwrites or appends to the source run's logs. Restore counters
  and complete active intents; ingest pending packets before requesting any new plan. Never
  re-draw previously queued/active plans.
- The byte-identity guarantee is checked by tests, not by the CLI: the source run's records
  up to the checkpoint cursors, followed by the continuation's records, must equal an
  uninterrupted run byte for byte (AI-08).
- Original typed config and map are retained as `config.json` and `map.txt` in each run
  directory. Restore/re-execution use these verified inputs, not an unchecked mutable path.
  The completion manifest is written only after a successful run. CLI source/output paths
  must resolve to distinct directories, and output must not already contain run artifacts.
- Version mismatch is refused, with no migration (v0.1 policy).

**[CR-005] P3 save and replay.** SavePackageP3 version 0.2 composes the unchanged
world/pending-delivery DTOs with ResidentRuntimeStateP3 and verified P3 log prefixes.
The sole checkpoint phase remains post-commit and pre-ingestion, including tick zero.
llm-decision-v0.1.md owns snapshot composition, durable commit publication, partial
tails, uncertain-call spend, continuation, version refusal and equality targets.
Its case allocation authority, separate from checkpoints, owns remaining live
capacity across all continuations. Ordinary current-head continuation retains its
original authorization; repeated/concurrent restores cannot duplicate that grant.
Recorded re-execution applies recorded accepted cognitive deltas/plans and deterministic
ingestion and the pinned retrieval strategy; it makes zero model, embedding, summary
or reflection calls and never acquires or changes a live allocation. Independent
live runs, including live continuations, are not promised identical outcomes.

## 7. P1 acceptance tests

| ID | Scenario | Must hold |
|---|---|---|
| AI-01 | The same context goes to Random, Scripted and a fake LLM test double | Same input shape; each returns a `DecisionOutcome`; `WorldState` is untouched |
| AI-02 | Resident A is in sight, B is out of sight | B's private state and remote stocks never appear in A's context |
| AI-03 | A plan with 0 or limit+1 intents, wrong IDs, or wrong parameter shapes | `INVALID_PLAN`; no mutation during structure validation; the recorded wait substitute later incurs ordinary tick metabolism |
| AI-04 | A multi-tile, multi-tick `move_to` | Counts as one intent; each step is executed and recorded by `world` |
| AI-05 | A scripted race for the last fruit | The loser gets `RESOURCE_TAKEN`; its remaining plan is discarded; it replans at the next idle boundary |
| AI-06 | Several triggers for one actor at one boundary | One decision, with an ordered, deduplicated `triggers` array |
| AI-07 | Same seed, content and actors | Random plans and IDs are identical across runs |
| AI-08 | Save during a `move_to` with queued intents; restore | No re-draw, no lost or repeated intents; events after restore match an uninterrupted run byte for byte |
| AI-09 | A deliberately broken policy | Error recorded, `wait` substituted, and the test is flagged as a policy fault |
| AI-10 | Record and re-execute; alter a request/plan, remove/duplicate a record, or change a file under its source manifest | Identical valid event bytes/final world hash; every invalid reference or divergence stops with `REPLAY_DIVERGED`, never a new wait |
| AI-11 | An uninterrupted sleeper with adequate needs | A packet is ingested at every boundary; no decision is made until the actor is idle |
| AI-12 | Save pre-ingest with transient sightings; attempt an after-ingest checkpoint | Restore delivers the exact packet once; unsupported checkpoint is refused |
| AI-13 | Restore a script with a changed hash, or change seed/policy/plan limit | Startup refusal; no unrecorded policy substitution |
| AI-14 | A recorded error/wait substitute, then save and resume | Original record provenance preserved; the continuation starts at the next ordinal; source-run logs are unchanged |
| AI-15 | Random candidates at map edges, null canteen, full inventory/full canteen and empty categories | Exact documented candidate ordering; bounded choice; permitted world failures do not become policy faults |

## 8. Additions to `interface-contract-v0.1.md` (applied in P1-01a as amendment A1)

1. `DecisionRequest`, `DecisionOutcome`, `DecisionError`, PolicyConfig and ScriptFixture:
   agents/sim-internal schemas; not resident access to the whole save or world state.
2. DecisionRecord, DecisionTraceManifest, `decisions.jsonl` and `decision-trace.json` (§5).
3. `SavePackage.agent_state.runtime_states: array<ResidentRuntimeState>`, the root
   `decision_record_cursor`, the restricted P1 checkpoint phase, and continuation-only
   resume with `resume-origin.json` (§6).
4. Deterministic plan/intent IDs and their decision transaction (§2.2).
5. **Explicitly amend Interface Contract §2.3:** replace the blanket P1 prohibition with
   permission for the minimal, empty-memory P1 context in §2.3 of this agent spec; richer
   cognition remains provisional until its later spec. This is not an unnoticed exception.
6. Clarify World Rules §0.3/Interface Contract ownership: world/facts.py holds canonical
   physical fact models/ID allocation; events re-exports and projects them read-only. World
   still imports no other subpackage. Use the plan's §2.1 module map; never solve type
   placement by weakening import-linter. This clarification requires the same explicit
   amendment review, not a silent code-only ownership change.
7. Clarify World Rules §5.1 observation sampling: all intermediate and final samples in one
   interval use its completed-tick clock/radius, with no sub-tick clock; separate physical
   sampling from hearing/feedback assembly as specified by the implementation plan §2.1.

No physical rule, Perception field, trigger vocabulary or action-result field changes.
Replay-only fields, schema export and frame capture are amendment A2 in the replay
frontend spec, applied in P1-01b. All amendments remain proposals until approved and landed.

## 9. Code layout (decided)

- `agents/types.py`: agent-only Pydantic schemas, policy configuration and shared ID builders.
- `agents/runtime.py`: `ResidentRuntime`, factory and `DecisionContext` assembly.
- `agents/policies/`: `random_policy.py`, `scripted.py`, `recorded.py`.
- `agents/rule_based/` (P2) and `agents/llm/` (P3) stay as they are.
- `agents/base.py` keeps the `Policy` protocol.

Agents import world types only through world.protocol and never import contract, world.state,
world.facts or a persistence implementation. Contract may import/re-export agent schemas for
save validation, but agents never import back from contract. The complete module map and the
world-to-sim observation/capture ports are fixed in the implementation plan §2.1 before M1.
