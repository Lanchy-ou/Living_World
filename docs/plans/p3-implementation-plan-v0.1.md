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
| SavePackageP3 | save_schema_version = "0.2" | unchanged world and pending delivery DTOs; exact runtime composition and verified log prefixes in decision spec |

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

To be integrated after the four owning specifications. P3-02 through P3-07 receive
separate cards, precise file ownership, prerequisite decisions and executable checks.

## 3. Verification and compatibility

Integration checks include owner uniqueness, consistent names/IDs/versions, M8 limit
coverage, file-scope disjointness, local Markdown links and `git diff --check`.
The runtime implementation Definition of Done remains AGENTS.md; this documentation
submission does not claim an implementation or approval of M8.

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
