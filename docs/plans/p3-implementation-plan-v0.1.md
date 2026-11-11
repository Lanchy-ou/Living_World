# Living Island - P3 implementation plan v0.1

> Proposed for M8, 2026-11-12. CR-005 option A approves scope only. This package
> becomes normative after independent Gate 2, owner M8 decisions and the explicit
> CR-005 amendment application. Existing contracts remain effective until then.

Baseline: `9bd45082002e87172312484a53c4787020bd584d` (origin/main after fetch).
P3-00 is an ancestor; CR-005 is approved (owner, 2026-11-11), option A.
All current-code citations in this package are `path:line` at this SHA unless
explicitly labelled as a historical reference. Proposed names are not existing APIs.

## 1. Shared interface skeleton

This section is the integration registry. The owning specification defines each
rule once; this registry fixes cross-part names, containment and ports. Members
must request interface changes from the lead before relying on them. The lead
updates and commits this registry before affected work continues.

### 1.1 Ownership

| Contract | Sole owning specification | Consumer |
| --- | --- | --- |
| Experience provenance, ingestion, retrieval, retention and intent references | resident-experience-v0.1.md | cognition, decisions |
| DecisionContextP3, provider projection, inclusion manifest | resident-experience-v0.1.md | provider adapter, evaluation |
| CognitiveDelta and permitted operations; resident cognitive vs policy-private state; decision transaction | llm-decision-v0.1.md | runtime, cognition |
| Snapshot composition, logs, links, cursors, interruption and compatibility | llm-decision-v0.1.md | persistence, evaluation |
| GoalProposal/GoalChange/GoalState transitions and evidence of completion | resident-cognition-v0.1.md | delta validator, ingestion |
| Identity, prompt templates, action descriptions and model response | resident-cognition-v0.1.md | context, provider |
| Evaluation metrics, fixtures, trial registration and inspection artifacts | p3-evaluation-v0.1.md | tests, analysis, frontend |
| File ownership, milestones, M8 decisions and CR process | this plan | all tasks |

The four specifications are siblings under `docs/spec/`. Their schemas apply only
to the opt-in P3 lane. The existing P1/P2 lane retains its serialized bytes and
reference hashes. No world, Perception, action or ReplayBundle schema changes.

### 1.2 Schema vocabulary and identity

Every object is closed (unknown fields rejected), all listed fields required;
`T|null` alone permits null. Integers are strict (booleans rejected). Counters are
nonnegative except an explicit tick cursor starting at -1. Strings are UTF-8;
canonical JSON and array order follow Interface Contract section 6.3. No floats
in deterministic state. Every new version must be validated literally; no implicit
upgrade, downgrade or inference from missing fields. Nested legacy DTOs retain
all of their current validation and omission behavior.

| Object | Version | Required fields (types); owner expands named types |
| --- | --- | --- |
| ExperienceRecord | enclosing store version | experience_id:string, owner_id:string, sequence:int, observed_tick:int, kind:ExperienceKind, source:SourceRef, payload:ExperiencePayload |
| ExperienceState | experience_schema_version = "0.1" | owner_id:string, last_ingested_tick:int (-1 initially), next_sequence:int, records:ExperienceRecord[], intent_refs:OwnedIntentRef[] |
| ResidentIdentity | identity_schema_version = "0.1" | actor_id:string, display_name:string, profile_id:string, values:string[], initial_direction:string, source_sha256:string |
| GoalProposal | enclosing delta version | text:string, completion:CompletionPredicate |
| GoalChange | enclosing delta version | operation:"continue" or "revise" or "abandon", expected_goal_id:string or null, proposal:GoalProposal or null |
| GoalState | goal_schema_version = "0.1" | current:Commitment or null, next_goal_sequence:int |
| CognitiveDelta | delta_schema_version = "0.1" | goal_change:GoalChange |
| ResidentCognitiveState | cognitive_schema_version = "0.1" | actor_id:string, identity:ResidentIdentity, experience:ExperienceState, goals:GoalState |
| DecisionContextP3 | context_schema_version = "0.2" | perception:Perception, identity:ResidentIdentity, goals:GoalState, recalled_experience:ExperienceRecord[], owned_intents:OwnedIntentRef[] |
| ContextAssembly | assembly_schema_version = "0.1" | context:DecisionContextP3, context_sha256:string, provider_projection:ProviderProjection or null, projection_sha256:string or null, manifest:InclusionManifest, error:"MANDATORY_OVERSIZE" or null |
| DecisionProposal | proposal_schema_version = "0.1" | actions:IntentTemplate[], cognitive_delta:CognitiveDelta |
| ResidentRuntimeStateP3 | runtime_schema_version = "0.2" | actor_id:string, policy_config:P3PolicyConfig, next_decision_ordinal:int, latest_perception_tick:int, cognitive_state:ResidentCognitiveState, policy_private:P3PolicyPrivateState |
| DecisionRecordP3 | record_schema_version = "0.2" | legacy decision identity/plan fields plus decision_id:string, context_sha256:string, projection_sha256:string or null, accepted_delta:CognitiveDelta, call_ids:string[], state_before_sha256:string, state_after_sha256:string; exact extension in decision spec |
| SavePackageP3 | save_schema_version = "0.2" | unchanged world and pending delivery DTOs; context_record_cursor:int, dispatch_record_cursor:int, log_prefixes:LogPrefix[], run_budget:BudgetLedgerP3, live_enabled:bool; full composition in decision spec |
| DecisionRequestP3 | request_schema_version = "0.2" | actor_id:string, tick:int, decision_ordinal:int, triggers:DecisionTrigger[], context:DecisionContextP3 |
| P3PolicyConfig | config_schema_version = "0.2" | policy_id:"llm-v0" or "rule-based-v0", seed:int, max_plan_actions:int, map_width:int, map_height:int, identity_sha256:string, prompt_version:string, prompt_sha256:string, action_schema_version:string, action_schema_sha256:string, context_profile_id:string, adapter_id:string, adapter_version:string, model_id:string, provider_settings:ProviderSettings, limits:DecisionLimits, pricing:PricingPin, fallback_config:PolicyConfig (rule-based-v0), trial_registration_sha256:string |
| P3PolicyPrivateState | private_schema_version = "0.1" | mode:"llm" or "fallback", fallback_state:RuleStateV0_1, last_fallback_ordinal:int or null |
| BudgetLedgerP3 | budget_schema_version = "0.1" | coordinator-owned committed debit totals and imported recovery reservations; exact fields in decision spec |

DecisionRecordP3 also contains `detail_code`, `fallback_error`, `policy_private_after`
and `budget_debits` with exact types in its owner. New context/dispatch/terminal-call
rows use literal version "0.1" and separate logs. The replay execution transport is
`recorded-p3-v0`, outside the saved primary `llm-v0` configuration; it preserves that
configuration to compare state. This does not add either new ID to the legacy PolicyId.
All actors in a P3 run use P3 envelopes; registered sorted unique `llm_actor_ids`
selects primary llm-v0 actors, with primary rule-based-v0 for the others. A deliberate
rule-only decision has status ok, matching primary/effective rule IDs, no calls,
no error or substitution and no fallback event. Its private mode starts fallback
and its frozen state persists continuously. This permits the one-LLM slice without
mixing record/save versions. The all-rule P2 comparison remains a separate legacy run.
Logs are `decisions-p3.jsonl`, `contexts-p3.jsonl`, `llm-dispatches.jsonl` and
`llm-calls.jsonl`; `decision-trace-p3.json` and `resume-origin-p3.json` identify their
verified lineage. Snapshot filenames retain the tick convention and dispatch by
explicit save version. Legacy paths and formats remain unchanged.

State is owned by the resident runtime, never by the provider. `policy_private`
contains the LLM bookkeeping and the frozen rule policy's private state, separate
from the shared cognitive state. Memory is IO-free and imports no agents, sim,
persistence or contract. Only submodules may import world.protocol.

Identifiers use existing actor/plan/intent/delivery IDs unchanged. New IDs are scoped
by run plus actor and are never parsed by splitting arbitrary actor IDs:
`decision_id = <run_id>:d:<actor_id>:<ordinal at least 6 decimal digits>`;
`call_id = <decision_id>:a<attempt_index>` (index starts at 0);
`experience_id = <actor_id>:e<sequence at least 6 decimal digits>`;
`goal_id = <actor_id>:g<sequence at least 6 decimal digits>`.
Validate IDs by rebuilding from typed identity fields. No UUIDs or wall clocks.
References across files include the run identity; resident-local IDs do not grant
cross-owner access. Plan IDs remain `<actor_id>:p<ordinal padded to 6>:i<index>`
for intents, with the existing plan prefix without the intent suffix.

Canonical processing: boundary tick, ascending UTF-8 actor ID, decision ordinal,
then attempt index. Experience sequences strictly increase; the experience spec
owns within-delivery capture order and retrieval tie breaks. Goal changes are
single operations, not unordered patches. Plans preserve intent order. Log cursors
count complete committed records, never bytes or the last record index.

### 1.3 Ports and commit boundaries

| Port (proposed pure signature unless stated) | Input | Output / writes |
| --- | --- | --- |
| ingest_experience | own delivery, own ExperienceState | new ExperienceState; no provider, objective log or hidden state_delta |
| advance_goal_evidence | own delivery, retained own intent refs, GoalState | GoalState with deterministic observed evidence only |
| assemble_context | latest own Perception, ResidentCognitiveState, explicit context profile | ContextAssembly; no IO or other actor reads |
| render_provider_request | ContextAssembly, DecisionRequest identity/triggers, pinned prompt/action schema | exact ProviderRequest; no hidden retrieval |
| provider.complete (external IO) | exact ProviderRequest, explicit attempt limits | ProviderResult; no state mutation |
| validate_proposal | DecisionProposal, own DecisionContextP3, policy configuration | ActionPlan plus staged CognitiveDelta, or classified rejection |
| stage_decision / commit_decision | immutable request, staged outcome / matching committed record | atomic resident state plus ordinal, accepted delta and policy-private update |
| export_state / restore | committed runtime / verified typed saved state | ResidentRuntimeStateP3 / runtime; refuses a half transaction |

**Ingestion:** validate consecutive delivery and actor first. Stage experience and
goal-evidence changes together, publish once, then sim acknowledges the delivery.
This happens at every living boundary, including those without a decision. Duplicate,
gap or mismatched delivery stops the run. Decision failure cannot undo ingested
experience. Only own delivered data and own accepted decisions create experience.

**Decision:** context and provider inputs derive from one frozen ingested state.
Validate actions and cognitive delta together. Rejected attempts change neither.
At most one request is pending per actor. Sim queues the effective plan and matching
record, then commits runtime once; no checkpoint or next tick in between. Rule
fallback produces an empty semantic delta (`continue` of the current goal); it
cannot assert goal completion. Ingestion owns observed completion.

**Persistence:** checkpoint stays phase 7, pre-ingestion, including tick zero.
World events, decisions, model attempts and P3 inspection data have distinct logs.
The decision spec defines the only durable-prefix authority and partial-tail rules;
logical runtime commit is not an atomic multi-file write. A dispatched but uncommitted
call may have incurred spend. Recovery must not silently redispatch it. Recorded
re-execution performs no provider, embedding, summary or reflection calls.

### 1.4 Shared design obligations

Each owner publishes a compact limits table with ID, proposed value, unit, rationale
and measurement. Prefix IDs `E-` (experience/context), `B-` (decision/provider), `C-`
(cognition), `V-` (evaluation). The lead includes every ID in the M8 sheet. Existing
world limits are references, never new P3 numbers. All choices remain proposed until
M8. New OQs start at OQ-085 and only the lead edits the register.

Do not expose unavailable source files as current facts. Read actual content paths.
Do not add physical completion evidence that the delivered DTO cannot supply. Engine-
dependent examples require local read-only probes or an existing exact test oracle.
No provider calls, credentials, dependency or runtime changes belong in P3-01.

## 2. Implementation sequence

The P3-00 slices are refined to make pure schemas/ports land before runtime and
adapter work. P3-02 includes the pure goal reducer and identity/prompt data contracts;
P3-05 integrates their behavior rather than inventing them late. P3-07 includes the
character panel and debug view; neither is silently deferred. No dates are promised.

| Task | Depends on | Result | Parallel file boundary |
| --- | --- | --- | --- |
| [P3-02](../tasks/p3/P3-02.md) | M8 and CR-005 applied | Pure state, experience/context, goals, prompt/action schemas and adapter ports | Foundation only; lands before 03/04 |
| [P3-03](../tasks/p3/P3-03.md) | P3-02 | Transaction, runtime/sim wiring, logs, checkpoint and recorded recovery using injected fakes | Runtime/persistence; no provider implementation |
| [P3-04](../tasks/p3/P3-04.md) | P3-02 | Provider adapter and frozen-rule fallback adapter; local fault tests | agents/llm implementation and dependency pins; no runtime/sim files |
| [P3-05](../tasks/p3/P3-05.md) | P3-03 and P3-04 | Integrated one-resident slice, registration/smoke entry point, M9 evidence | Sole integration writer after both merges |
| [P3-06](../tasks/p3/P3-06.md) | M9 | Three residents, isolation/social cases, alternate deterministic retrieval and provider fixtures | New integration fixtures/tests; no production expansion |
| [P3-07](../tasks/p3/P3-07.md) | P3-06 | Evaluation tool, inspection artifact, character/debug UI, registered trials, compatibility and M10 | Analysis/export/frontend; final integration after 06 |

03 and 04 may run together. Every other dependency is a merge prerequisite; no worker
may edit another active task's files. Shared-file fixes are returned to the owning task,
then dependents rebase. If independent frontend work is desired, split 07 into 07a
(export/analysis) then 07b (UI) with a frozen inspection schema; require an owner-approved
card amendment before starting the extra task. This package keeps six requested cards.

### 2.1 Implementation layout and imports (proposed)

Paths below are relative to `backend/src/living_island/`, except content and scripts.
New DTOs are separated from the legacy types so version dispatch cannot alter old bytes.

| Layer | Proposed implementation | Allowed direction |
| --- | --- | --- |
| Experience | memory/p3_types.py, memory/experience.py, memory/retrieval.py | world.protocol only; no agents/sim/persistence/contract/IO |
| Cognitive DTOs and pure reducers | agents/p3/types.py, context.py, cognition.py, prompts.py, ports.py | own memory DTOs and world.protocol |
| Runtime and transaction | agents/p3/runtime.py; agents/runtime.py factory dispatch | DTOs, pure reducers, injected provider/fallback ports |
| Provider and fallback adapters | agents/llm/provider.py, fallback.py, fake.py | agents/p3 ports, unchanged rule_based; provider IO only in provider adapter |
| Persistence | persistence/p3.py, characters.py; contract/p3_save.py | explicit runtime exports; no hidden reads into policies |
| Coordination | sim/p3.py plus existing CLI/runner/boundary integration | world ports and runtime ports; never duplicate world rules |
| Evaluation | analysis/p3.py and scripts/p3_experiments.py | typed retained records, no runtime/policy execution |
| Inspection | contract/p3_inspection.py, persistence/p3_inspection.py, frontend/src/p3/ | read-only export plus display; never resident input |

Existing guards remain intact: `backend/pyproject.toml:46` forbids world imports,
`:67`/`:75` restrict agents/memory to world.protocol, `:85` keeps events read-only,
`:102` forbids agents importing contract/persistence/sim, and `:112` restricts analysis.
P3-02 adds a forbidden-import contract from memory to agents, sim, persistence,
contract, anthropic, openai, httpx and requests, and changes the memory unmatched
world.protocol exemption to error only after its first real import. Extend analysis's
forbidden modules to agents.p3.runtime and agents.llm while allowing indirect DTO
imports exactly as today. No existing guard is weakened. Network/file IO in pure
reducers is additionally checked by import tests (stdlib IO cannot be exhaustively
expressed by the current contracts). Package __init__ files remain free of world imports.

### 2.2 Deferred extension ports

These are names and owners only; no P3 invocation, schema, psychological score or
production implementation is authorized.

| Later feature | Named port | Owner |
| --- | --- | --- |
| Consolidation | ExperienceConsolidator | memory |
| Forgetting | RetentionPolicy | memory |
| Reflection | ReflectionProposal | agents cognition |
| Relationship interpretation | SocialInterpreter | agents cognition |
| Emotion | AffectProjection | agents cognition |
| Dreams | SubjectiveInputAdmission | agents cognition; memory stores provenance |

The optional alternate deterministic selector fixture exercises the existing retrieval
port only. It does not implement long-term retrieval or a plugin registry.

## 3. Verification and compatibility

Integration checks include owner uniqueness, consistent names/IDs/versions, M8 limit
coverage, file-scope disjointness, local Markdown links and `git diff --check`.
The runtime implementation Definition of Done remains AGENTS.md; this documentation
submission does not claim an implementation or approval of M8.

### 3.1 Implementation executor checks

Run from the repository root for every code task (no new tests are required for this
P3-01 documentation task):

```sh
uv run --directory backend pytest
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv run --directory backend lint-imports --no-cache
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
uv run --directory backend python ../scripts/gen_types.py
git diff --exit-code -- frontend/src/api/generated
```

After committing intended changes, full `git diff --exit-code` must be clean. The
inspection schema must not be added to the frozen replay generation root. P3-07 uses
a separate generator and generated destination for its own versioned artifact. Check
`git diff --check` on each task; include `pnpm --dir frontend test` and
`pnpm --dir frontend run test:schema` for UI/contract tasks.

### 3.2 Historical compatibility identity

These are historical reference artifacts, not recomputed P3-01 results. Keep the
legacy lane exactly reproducible. Use the frozen P1 fixture, never the M6 default
for M4 comparison. Sources: [P1-09](../tasks/p1/P1-09.md) and
[P2-05](../tasks/p2/P2-05.md).

| Reference | Events SHA-256 | Decisions SHA-256 |
| --- | --- | --- |
| P1 M4 original inputs, reference commit 6d90824 | 2d68a49b495e46a150322711bc8fbb38779ad947c4345ec0f11c89bd08d03287 | ee614c057b02d65b67ee6ff5336e17434ab4aeb6026c710f853d7d599c36e4bd |
| P2 M7 seed 2600456787, code a22360d0ef4c39f08c887d463c7576022873c605 | 427f7f0536c4cedc77b365e821575465d83a60f90d857a73bdf8b45e8fb3574a | 67c490e74b963b32fa2393ec92b97d8f412f46c3146a5c20b6bc63a1d5add194 |

P1 final world: `113483069d74936a3fa5ecf0f719405dc7499698fc851cdc4b992a84e25357ed`;
P1 replay: `8e26d853b6bf324fa4a375f0edfca526c09754b78d7eaee9b96c615464dbfb83`.
P2 final world: `5efcf3eab02db3928bc55e4a226327acde2bbfee54abc898f7649d6e4302382c`;
P2 replay: `720bccc76cb1c3baff78a74bec7703e76764be777713b43df6e30d297f9d36e8`.
P2 rule source tree: `837f2f90f6b242477e43c25aec9b359ec51ba331`;
M6 content pin: `7c13d78ffd7d89006f6008c8a09f37ae97c253db`.
For other seeds compare the frozen algorithm/configuration on matched inputs; these
single-seed hashes are not universal constants for every run.

## 4. Milestones and gates

M8: owner freezes this package and CR-005 exact amendments after outside-team Gate 2.
M9: owner inspects the one-resident slice. M10: owner accepts the three-resident
foundation, evaluation, character/debug view and retrospective. These milestones
are proposed. Gate 1 and independent Gate 2 apply to every implementation task.

## 5. Task cards

Use `docs/tasks/_template.md`. Concurrent branches have disjoint writable files.

## 6. Handoff

Each task appends what changed, commands/results, deviations, open questions and
seven fields: base_commit/result_commit; status; scope_changed; human_interventions;
rework_rounds; verification (including NOT_RUN); open_questions. Unknown is explicit.

## 7. Change requests

A contradiction with a frozen specification is reported with current rule, requested
rule, impact, options and one recommendation in open-questions.md. Stop only the
affected work until owner disposition. Downstream workers do not edit frozen specs.
CR-005 text is drafted in its register entry and applied to Agent Interface and
Interface Contract only after M8. This task never merges into main.
