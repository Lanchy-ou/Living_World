# P3 resident-agent foundation proposal v0.1

> Draft, 2026-11-11. Architecture and delivery proposal, not a normative specification
> or approved implementation plan. Existing specs remain authoritative. CR-005 proposes
> moving a small memory foundation from P4 into P3. No corresponding contract or
> runtime change is applied by this document.

## 1. Outcome and scope

Build a resident who persists across decisions: stable identity, bounded experience,
an ongoing goal, world-validated actions and feedback that can change the next choice.
Future memory, social and environmental features should extend explicit boundaries with
focused compatibility tests, instead of requiring a new agent loop.

The owner's priorities are memory, environment interaction and interpersonal interaction.
Human experience motivates scenarios; it is not a claim of scientifically accurate
psychology. Acceptance uses observable behavior and traceable consequences.

P2 is accepted at M7. Use the frozen rule policy and M6 inputs in
[P2-05](../tasks/p2/P2-05.md) as control/fallback. The original blind-start inputs remain
useful stress cases; default-island survival alone does not establish exploration skill.

### Proposed P3 working slice

- Persistent identity and explicit current goal/commitment.
- Bounded, source-tagged recent experience from delivered perception, including
  boundaries without a model decision; deterministic baseline retrieval.
- Model-independent context assembly and structured decision proposals.
- Existing physical/social actions, with resident-local interaction history.
- Provider adapter, bounded failure handling, rule fallback and complete call records.
- Save/restore and recorded re-execution of action and cognitive decisions.
- Separate inspection artifacts linking context, memories, plan, accepted cognitive
  updates and actual outcomes. These artifacts are not resident input.

### Later features with extension points

Long-term retrieval, forgetting, consolidation, belief revision, relationships, emotions,
autonomous long-term goal creation, reflection, learned skills and dreams.
P3 does not invent their psychological scores or update formulas. It does not add a
general plugin engine, MCP, generated-code execution, direct model-to-model messaging,
parallel model calls or live WebSocket UI.

## 2. Responsibilities and ownership

Reuse ResidentRuntime, Policy, Perception and ActionPlan. The names below describe
responsibilities; exact Python signatures and schemas belong to P3-01.

| Responsibility | Owner and input | Output / extension boundary |
| --- | --- | --- |
| Physical truth and sensing | world; authoritative state and rules | Per-actor deliveries and feedback; no cognition imports |
| Resident lifecycle | agents.runtime; own deliveries and identity | Ingestion, decision commit and restore; same port for sim |
| Experience and retrieval | memory; resident-local records | Versioned store and bounded selections; replaceable retrieval |
| Goals and commitment | agents; own state, feedback and accepted proposals | Versioned goals and owned plan references |
| Context assembly | agents; perception, goals and retrieved experience | Bounded provider context plus inclusion manifest |
| Decision policy | agents; context and own policy state | Proposed actions and permitted cognitive updates |
| Model adapter | agents.llm; explicit request/configuration | Raw response, usage and classified result; no memory ownership |
| Coordination | sim; runtimes and world ports | Ordered boundary phases; no duplicate physical rules |
| Storage/diagnostics | persistence; explicit serializable exports | Snapshots and logs; no backdoor into resident knowledge |

Keep memory free of imports from agents, sim, contract and persistence, avoiding a
cycle when agents uses it. Memory DTOs live under memory; agents maps them to context.
Only submodules may use world.protocol. Memory processing is IO-free; persistence
writes exported state. P3-01 enumerates import-linter additions rather than weakening
existing boundaries.

### Three kinds of information

1. Objective world facts: owned by the engine; available to offline analysis.
2. Delivered experience: what this resident saw, heard or received as feedback.
3. Interpretation: what this resident inferred, believed, intended or summarized.

Hearing "fruit is in the north" establishes that those words were heard, not that fruit
exists there. Old observations are dated; a previously observed tree may now be empty.
A confidence label is subjective, not a measured probability. P3-01 must explicitly
resolve the existing use of physiological NeedBand for memory confidence.

## 3. Experience, context and goals

### Experience store

Proposed common metadata: owner, deterministic resident-local ID, observation tick,
kind, permitted source references, related known entities and bounded content. Derived
summaries/interpretations also retain derivation references and a distinct tag.
Required fields, lengths, ordering and retention are frozen in P3-01 (OQ-082).

- Capture only own delivered fields and own accepted decisions, never the objective
  event log or hidden ActionResult.state_delta.
- References use delivery IDs/ticks, exposed utterance IDs and owned intent IDs.
  Feedback can omit targets; resolve through retained own intent references.
  Missing references stay unknown; do not query hidden events to repair them.
- Preserve transient sightings and speech under explicit retention rules. Ordinary
  repeated observations may be compacted by a documented deterministic rule.
- World-provided exploration remains static-map knowledge; do not introduce a second
  authoritative map. Historical dynamic observations carry their observation times.
- Retrieval is owner-scoped in code, not just a prompt instruction. Test with
  residents who have conflicting knowledge.
- Initial retrieval is deterministic and bounded. Define ties, expiry, overflow and
  source-reference retention before implementation. No vector service is required.

### Context assembly

Separate mandatory current information from selected historical material. Version and
record the selection/budget rules. P3-01 defines mandatory fields (identity, needs,
triggers, commitment, action contract and relevant feedback are proposed candidates).
If mandatory content cannot fit, classify the failure and fall back; do not silently
truncate it. Optional retrieval must report selection/truncation in the inspection data.

Speech and memory text are data, not instructions that grant permissions. A resident's
request cannot alter the action schema or reveal another store. IDs mentioned in speech
are claims, not authorization to inspect those entities.

Retain the full decision context and exact provider request, prompt/template and schema
versions, plus selected record IDs. P3-01 defines which input identities cover the full
context and the provider projection. Model adapters do not perform hidden retrieval.

### Goals and commitments

Propose configured long-term direction and one current commitment per resident (OQ-084).
The model may propose short-term goals and explicit continue/revise/abandon transitions.
Normal action generation cannot rewrite identity or stable values. Multiple long-term
goals and personality evolution remain later extensions.

Distinguish intended, attempted and observed-complete. Model text cannot establish a
completed physical transfer. Objective completion requires matching visible feedback;
ambiguous or subjective progress stays interpretation. Retain enough owned intent links
for delayed feedback after replanning or fallback.

## 4. Environment and interpersonal interaction

Existing actions keep their preconditions, timing and consequences. Publish versioned
model-facing action descriptions and structured output schemas derived from or checked
against those contracts. A future action requires world validation, sensing/feedback
design and tests; registering a tool alone cannot add physical behavior. Do not expose
Python, filesystem access or engine mutation tools to residents.

Social interaction follows the embodied loop: talk consumes time and hearing determines
delivery. Each recipient interprets its own packet. A request, acceptance, promise and
completed give are separate records. No shared transcript grants everybody access to
everything said. Reply references and dialogue termination keep existing world rules.

Example: A asks B for water, B agrees, then fails to reach A. A remembers the request
and heard reply; neither resident records a completed transfer without permitted
evidence. A future relationship module may interpret this history without changing
give settlement or exposing B's private reasoning to A.

## 5. Transaction, fallback and recovery

### Ingestion and decision lifecycle

Preserve the existing pre-ingestion checkpoint boundary and exactly-once delivery
checks. Ingestion deterministically applies experience once per packet. It makes no
model calls and must reproduce from a prior checkpoint and its pending delivery.
A failed decision does not erase already received experience.

At each eligible idle boundary:

1. Assemble the actor's context and record its input identities/versions.
2. Invoke the policy through bounded model attempts; simulated time stays frozen.
3. Validate plan structure and allowed cognitive updates together. Discard invalid
   attempts' cognitive updates; retries cannot partially mutate resident state.
4. On a final policy failure, obtain the recorded fallback outcome.
5. Commit effective plan, accepted cognitive delta, ordinal, budget accounting and
   fallback private state as one logical decision transaction; record every attempt.
6. Execute through world. Later visible feedback becomes new experience and may
   trigger a decision under existing interruption and trigger rules.

Ordered multi-actor boundary commits and IO remain in sim/persistence. Logical
atomicity does not imply atomic writes across files. P3-01 must specify committed
cursors, partial tails and incomplete-run handling. A call may have been billed before
a crash; its uncommitted response cannot silently become a committed decision.
Completed-checkpoint continuation and interrupted-call recovery need separate guarantees.

### Fallback

Shared resident experience continues during fallback. The rule policy's private state
is separate from the LLM state. P3-01 must define inactivity, stale commitments, pending
intent references and return to the LLM; the frozen P2 policy is stateful, not a stateless
helper (OQ-083). Preserve its baseline identity; any required adapter is explicit.
Valid world failures are not provider failures. Programming defects and replay
divergence still stop the run under existing rules.

### Replay and model-call recording

Re-execution uses recorded effective plans and accepted cognitive deltas, with no fresh
model calls, summaries or embeddings. Deterministic ingestion/retrieval uses pinned
versions and verified inputs. Compare cognitive state as well as world state at
checkpoints. Fresh live-model continuations are not promised to match one another.

Every attempt records parent decision ID, exact request, versions, available raw output,
parsed result/error, usage and latency. Multiple attempts need explicit linkage beyond
the existing single llm_call_id. Missing usage is unknown, not zero. No private
chain-of-thought is required; proposals and observable evidence support debugging.
Wall-clock diagnostics remain outside deterministic equality targets. Limits are OQ-082.

## 6. Extensibility checks

| Future feature | Main extension | What stays intact | P3 proof |
| --- | --- | --- | --- |
| Another model | Adapter and configuration | Resident identity, stores, world actions | Swap fake providers without world edits |
| Long-term retrieval | Store/retrieval implementation | Runtime ingestion and action execution | Second deterministic selector on identical records |
| Forgetting/reflection | Provenance-preserving memory transformation | Objective history and replay semantics | Derived-record fixture keeps source links and replays |
| Trust/resentment | Local interpretation of social experience | Talk/give settlement and other actors' privacy | Different interpretations remain isolated |
| Environmental action | Explicit action/perception/world contract change | Provider and memory machinery | Review required change locations; no new action in P3 |
| Dreams | Future authorized, tagged cognitive input | Physical truth and instruction priority | Tagged-claim fixture cannot mutate world state |

Fixtures exercise generic provenance/isolation; they do not ship production dreams,
relationship scores, reflection or a new runtime cognitive ingress API.

## 7. Delivery sequence and proposed gates

Each implementation task gets a template-based card, separate branch/worktree and
Gate 1/2. There is no fixed worker limit, per the owner's 2026-11-11 decision in
AGENTS.md. Concurrent tasks must have non-overlapping file ownership, and a reviewer
must not review work it helped write. Dependencies determine the execution order.
No target date before cost measurements.

| Task | Deliverable | Exit evidence |
| --- | --- | --- |
| P3-00 (this task) | Proposal, change inventory and questions | Independent document review; unresolved decisions labelled |
| P3-01 | Normative P3 specs, CR decisions, schemas, limits and task cards | Concrete contracts approved at proposed M8 |
| P3-02 | Resident state, experience ingestion/retrieval, context assembly | Non-decision sightings, privacy, overflow and restore tests |
| P3-03 | Cognitive decision transaction, call records, budget ledger and persistence | Fake-response/retry/crash/replay tests |
| P3-04 | Provider adapter and stateful fallback | Fake fault matrix; configured live smoke after budget/credential selection |
| P3-05 | One resident with goals and existing actions | Continuity and evidence-backed progress; proposed M9 review |
| P3-06 | Three residents and extension fixtures | Social consequences, isolation and strategy replacement |
| P3-07 | Evaluation, diagnostics, compatibility and retrospective | Registered live results, fallback share, costs; proposed M10 |

M8: approve specifications and the phase amendment. M9: review the one-resident
foundation. M10: P3 acceptance. These are proposed new milestones, not already approved.
P3-01 freezes limits, model configuration, live-call budgets and quantitative pass lines
before dependent implementation/experiments. Existing P1/P2 gates remain unchanged.

### Acceptance scenarios to specify in P3-01

- A transient sighting during movement reaches the next decision's experience store.
- Failed gathering changes a later proposal without creating hidden resource knowledge.
- An interrupted delivery goal resumes or is explicitly abandoned with recorded evidence.
- A false heard claim remains distinct from observation; later contradictions do not
  rewrite the history of what was heard.
- Out-of-hearing residents receive no conversation; stores cannot be cross-read.
- Accepted speech followed by failed give does not become a completed transfer.
- Store/context overflow is deterministic and retains required referential integrity.
- Malformed cognitive output, timeout and budget exhaustion produce no partial state.
  Fallback and return preserve experience and decision identity.
- A checkpoint with active/queued actions and populated memory restores correctly.
  Recorded continuation reproduces decisions, cognitive state and world; corruption fails.
- Provider and retrieval implementations can change without editing physical execution.

Fake providers test deterministic semantics. Registered, separately budgeted live
trials evaluate behavior. Compare with P2 on matched inputs and report LLM/fallback
shares, invalid plans, adaptation, interactions, survival, tokens and latency.
Do not silently import P2's survival threshold into P3. Record prompt, model, schema,
code and content identities; keep evaluation inputs separate from tuning.

## 8. Changes requiring specification work

CR-005 in the [question register](../spec/open-questions.md) requests the P3 memory
scope amendment. P3-01 must supply exact schema diffs and compatibility behavior for:

- Agent Interface phase allocation and ownership of resident-private state.
- DecisionContext provenance, goals/commitment and bounded provider projection.
- DecisionOutcome/DecisionRecord cognitive deltas, fallback provenance and call linkage.
- PolicyConfig, policy IDs/errors, runtime state, budget/call cursors and restore rules.
- Call logs, interrupted calls and the existing fallback event schema.
- Action descriptions checked against unchanged world contracts.
- Import boundaries and explicit old-save/version acceptance or refusal.

Preserve P1/P2 semantics and established serialized bytes. Choose versioned compatibility
or explicit migration/refusal; never guess unknown state versions. No replay UI schema
change is presumed: initial inspection can use a separate offline artifact.

OQ-082: numerical bounds, retention and evaluation/budget policy.
OQ-083: fallback state lifecycle.
OQ-084: initial goal model.
These are resolved before affected implementation, not improvised by downstream workers.

## 9. References and dependency choice

Checked 2026-11-11. References inform design; they do not override repository contracts.

- [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview): explicit state,
  durable execution and persistence. Retain our boundary coordinator unless integration
  proves compatible with its ordering and checkpoint rules.
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents):
  simple composable design and clear tools. Prefer explicit ports before a plugin engine.
- [Generative Agents (2023)](https://arxiv.org/abs/2304.03442): memory, planning and reflection.
  Use these as cognitive responsibilities, not proof of human-psychology fidelity.
- [Voyager (2023)](https://voyager.minedojo.org/): feedback-driven improvement and reusable
  skills. Its executable generated skills are not adopted under our current action boundary.

Recommendation: extend our small runtime with explicit ports. Any framework dependency
proposal must demonstrate perception isolation, boundary ordering, cognition replay and
compatible recovery. No framework dependency is chosen by this draft.
