# Living Island - LLM decision and recovery specification v0.1

> **Accepted at M8, 2026-11-12.** The owner approved the P3 package and CR-005
> amendments, with DeepSeek and an aggregate CNY150 API ceiling superseding the
> earlier provider/USD proposal. See [M8 decision record](../tasks/p3/M8-decisions.md).
> Normative design; implementation and live verification remain separate tasks.

Baseline for current-code citations: `9bd45082002e87172312484a53c4787020bd584d`.
All unqualified rules are **accepted P3 behavior**. The
[registry](../plans/p3-implementation-plan-v0.1.md#1-shared-interface-skeleton)
fixes cross-part names. [Experience](resident-experience-v0.1.md) owns context,
projection, ingestion and retention; [cognition](resident-cognition-v0.1.md) owns
goals, evidence, identity and prompt rendering. This file owns CognitiveDelta,
decision commitment, policy-private state, logs and recovery.

## 1. Existing behavior and compatibility

| Existing behavior | Baseline evidence |
| --- | --- |
| Runtime validates consecutive own deliveries and builds empty-memory context | `backend/src/living_island/agents/runtime.py:96`, `backend/src/living_island/agents/runtime.py:114` |
| A pending decision prevents export; policy state finishes at runtime commit | `backend/src/living_island/agents/runtime.py:200`, `backend/src/living_island/agents/runtime.py:207` |
| Rule policy stages state, commits accepted outcomes and refuses pending export | `backend/src/living_island/agents/rule_based/policy.py:722`, `:730`, `:737` |
| Rule feedback requires a retained issued intent; next state holds new plan refs | `backend/src/living_island/agents/rule_based/policy.py:300`, `:662` |
| Save validates pre-ingest deliveries and ordinals; coordinator saves empty cognitive placeholders and llm cursor zero | `backend/src/living_island/contract/save.py:64`; `backend/src/living_island/sim/boundary.py:75` |
| Append logs and boundary publication are separate operations | `backend/src/living_island/persistence/logs.py:160`; `backend/src/living_island/sim/runner.py:153` |
| Fallback event reasons are TIMEOUT, PARSE_ERROR, BUDGET, PROVIDER_ERROR; world port allocates fact IDs | `backend/src/living_island/world/facts.py:242`; `backend/src/living_island/world/ports.py:196` |
| Legacy decisions reject non-null llm_call_id; recorded policy verifies request hash | `backend/src/living_island/agents/types.py:163`; `backend/src/living_island/agents/policies/recorded.py:45` |
| Trace verifies file hashes/counts; sim compares world results | `backend/src/living_island/persistence/trace.py:44`; `backend/src/living_island/sim/runner.py:105` |

P3 is a separate opt-in serialization lane. Add no default/null fields to legacy
PolicyConfig, DecisionContext, DecisionRecord, ResidentRuntimeState, SavePackage or
DecisionTraceManifest. Keep legacy IDs, paths, hashes and fallback behavior. P1/P2
stays schema 0.1, including omitted absent rule_params. Dispatch readers by explicit
versions; refuse unknown versions, mixed decision streams and implicit upgrades.
A P3 run uses P3 state for every resident. Registration llm_actor_ids selects primary
llm-v0 actors; other actors use a continuously stateful rule-based-v0 primary in the
same P3 envelopes. Matched all-rule control is a separate legacy run. No automatic
migration from a P2 save.

Frozen P2 control identity is in [P2-05](../tasks/p2/P2-05.md#p3-control-and-fallback-identity):
rule tree `837f2f90f6b242477e43c25aec9b359ec51ba331`, code
`a22360d0ef4c39f08c887d463c7576022873c605`, scenario pin
`7c13d78ffd7d89006f6008c8a09f37ae97c253db`. Section 5's adapter leaves that tree
unchanged. M4 hashes in [P1-09](../tasks/p1/P1-09.md) and P2-05 event/decision/world
hashes remain implementation oracles with their retained historical inputs.

## 2. Closed schemas and ownership

Registry required/null, strict-integer and canonical-encoding rules apply. `Hash`
means 64 lowercase SHA-256 hexadecimal characters; `N` is integer >= 0. Arrays keep
declared order. No secret is a field. Other owners' nested types are not redefined.

### 2.1 State and configuration

```text
CognitiveDelta {
  delta_schema_version:"0.1", goal_change:GoalChange
}
ResidentCognitiveState {
  cognitive_schema_version:"0.1", actor_id:string,
  identity:ResidentIdentity, experience:ExperienceState, goals:GoalState
}
P3PolicyPrivateState {
  private_schema_version:"0.1", mode:"llm"|"fallback",
  fallback_state:RuleStateV0_1, last_fallback_ordinal:N|null
}
ResidentRuntimeStateP3 {
  runtime_schema_version:"0.2", actor_id:string, policy_config:P3PolicyConfig,
  next_decision_ordinal:N, latest_perception_tick:integer >= -1,
  cognitive_state:ResidentCognitiveState, policy_private:P3PolicyPrivateState
}
P3PolicyConfig {
  config_schema_version:"0.2", policy_id:"llm-v0"|"rule-based-v0",
  seed:integer [1,4294967295], max_plan_actions:integer >= 1,
  map_width:integer >= 1, map_height:integer >= 1,
  identity_sha256:Hash, prompt_version:string, prompt_sha256:Hash,
  action_schema_version:string, action_schema_sha256:Hash,
  context_profile_id:string, adapter_id:string, adapter_version:string,
  model_id:string, provider_settings:ProviderSettings, limits:DecisionLimits,
  pricing:PricingPin, fallback_config:PolicyConfig, trial_registration_sha256:Hash
}
ProviderSettings {
  api:"deepseek-responses", reasoning_effort:"none", store:false,
  tools:[], background:false, stream:false,
  input_counter_id:string, input_counter_version:string
}
DecisionLimits {
  profile_id:"p3-bounded-v0.1", max_attempts:2,
  attempt_timeout_ms:30000, decision_timeout_ms:60000,
  retry_delay_ms:0, max_input_tokens:32768, max_output_tokens:2048,
  max_request_bytes:131072, max_response_bytes:262144
}
PricingPin {
  currency:"CNY", date:string (YYYY-MM-DD), source_url:string,
  input_micro_cny_per_million_tokens:N, output_micro_cny_per_million_tokens:N
}
DecisionRequestP3 {
  request_schema_version:"0.2", actor_id:string, tick:N,
  decision_ordinal:N, triggers:DecisionTrigger[], context:DecisionContextP3
}
```

CognitiveDelta has exactly one operation carrier, goal_change. Cognition owns its
three operations and validation. It cannot append memories, set confidence, mutate
identity, complete a goal, edit policy state or write arbitrary JSON paths. An invalid
goal_change rejects the whole proposal. Accepted actions and delivered evidence
create experience through the experience specification.

Runtime owns cognitive state regardless of policy. Rule fallback owns only its
private RuleStateV0_1; adapters own no resident state. Coordinator owns run budget;
the case allocation authority in section 4.2 alone grants live spending capacity.
All nested actor/owner IDs equal runtime actor; experience.last_ingested_tick equals
latest_perception_tick. Identity is immutable and its canonical object hash equals
identity_sha256. Owners initialize goals/experience; mode starts llm, last fallback
ordinal null, rule commitment/capacity null and rule arrays empty. A rule-primary
actor instead starts mode=fallback (private-state lifecycle label only), never makes
a provider call and never emits a fallback event merely for being a control actor.

Config seed, plan limit and dimensions match effective retained world config.
fallback_config is the legacy rule-based-v0 config with base parameters, matching
seed/plan limit/dimensions and null script/trace hashes. P3 config hash covers every
field, pricing and limits included; restore checks against retained registration.
No mutable config path changes it. M8 selects DeepSeek, CNY accounting and local credentials.
The initial adapter is deepseek-responses-v0 with model_id=deepseek-flash and reasoning_effort=none; another provider
requires an explicit new adapter/config version, not untyped settings.

The API model ID is an alias, not an immutable dated snapshot. Retain the official
model-version evidence (currently DeepSeek-V4.1-Flash-1017), retrieval date and hash
as an input pin at registration. Do not invent a dated API model ID or claim live
model immutability. Before each live run/continuation verify that published version
and prices still match; detected drift stops dispatch until a reviewed new pin is
registered. Recorded replay relies on exact retained outputs and never calls the alias.
PricingPin uses peak uncached CNY rates: input 2000000 and output 8000000 micro-CNY
per million tokens. No exchange rate, cache or off-peak discount creates extra capacity.
All money fields, including reservation/debit/ledger totals, use integer micro-CNY
(1000000 = CNY1); unknown or mixed currency is refused.

### 2.2 Provider port

```text
ProviderRequest {
  provider_request_version:"0.1", model_id:string,
  messages:[{role:"system",content:string},{role:"user",content:string}],
  response_schema:object (pinned DecisionProposal JSON Schema),
  settings:ProviderSettings, max_output_tokens:2048
}
WireRequest {
  wire_schema_version:"0.1", method:"POST", origin:"https://api.deepseek.com",
  path:"/responses", content_type:"application/json", body_base64:string
}
ProviderResult {
  provider_result_version:"0.1",
  outcome:"response"|"timeout"|"provider_error"|"output_limit",
  raw_response:string|null, raw_body_base64:string|null, observed_body_bytes:N,
  response_complete:boolean, response_text:string|null,
  provider_request_id:string|null, token_input:N|null, token_output:N|null,
  latency_ms:N|null, provider_error_code:string|null
}
ProviderAdapter.prepare(request:ProviderRequest) -> WireRequest
ProviderAdapter.count_input_tokens(request:ProviderRequest,wire:WireRequest) -> N
ProviderAdapter.complete(request:ProviderRequest,wire:WireRequest,
                         timeout_ms:integer) -> ProviderResult
```

**[CR-006, owner-approved 2026-11-13]** Cognition owns the versioned action schema.
For `p3-actions/0.2`, retain and count the newly generated exact request/schema
bytes; do not reuse 0.1 schema, wire hashes or reservation estimates. The adapter
must not rewrite the schema to obtain provider compatibility. Old 0.1 execution
and recovery remain bound to their original source/registration/schema pins;
offline migration is not authorized by CR-006. A new schema dependency requires
offline exact-wire/counter regression and independent review before integration.
CR-006 authorizes no new live registration, replacement trial or budget grant.

Cognition owns exact two-message rendering and action_schema_sha256 (descriptions
plus proposal schema); prompt_sha256 hashes the template bytes. Retain messages,
schema, settings and adapter version. Counter is pure, pinned and counts all charged
input, schema framing included, or returns a proven upper bound. Counter proof and
fixture suite are adapter acceptance prerequisites; missing or uncertified counter
causes startup refusal INPUT_COUNTER_UNAVAILABLE before any calls. No network token
counting endpoint is permitted.
No unquantified margin is allowed. Registration pins counter implementation hash.

prepare is pure and produces exact nonsecret outbound body bytes. Both canonical
ProviderRequest and decoded wire body must fit B-08; body is canonical UTF-8 JSON.
The pinned adapter mapping must preserve messages/schema/settings exactly; complete
verifies the prepared hash and sends body bytes unchanged. No SDK body rewriting or
hidden defaults. The DeepSeek wire body sets model, the exact system/user input,
reasoning.effort=none, max_output_tokens=2048, stream=false, tools=[], tool_choice=none
and text.format={type:"json_schema",name:"resident_decision",schema:<pinned schema>}.
ProviderSettings.store/background=false are semantic guarantees of this stateless
synchronous lane; omit unsupported store/background fields from the wire body.
No previous_response_id, conversation, search, image, file or other tool input is sent.
P3-04 must verify schema and response/usage mapping with pinned fixtures; API format
compatibility alone does not establish exact adapter correctness. Authentication is added only as a header and never retained; all
other headers are fixed by wire.content_type. Attempt IDs/time never enter the body.
Count the same prepared wire request; do not regenerate it between counting/logging
and sending. Changing the mapping changes adapter_version and implementation pin.

No conversation history, tools, hidden retrieval or raw invalid output is appended.
Attempt ID/timeout are transport metadata outside ProviderRequest. SDK retries are
zero; only section 3 retries. No streaming/parallel calls. A late response is audit-only
and cannot replace a terminal row or alter state after timeout.

raw_body_base64 preserves exact retained response bytes; null iff no body arrived
(empty body is ""). observed_body_bytes counts bytes actually read, not total body
size. Read at most B-07 plus one sentinel byte; retain the first B-07. If the sentinel
exists, response_complete=false and OUTPUT_LIMIT; total unreceived size is unknown.
raw_response is strict UTF-8 decoding of retained bytes, or null if invalid/no body;
never replace malformed characters. Invalid UTF-8 without overflow yields PARSE_ERROR/
INVALID_JSON, retaining raw bytes. response_text is extracted output or null. Never
parse incomplete output. Headers/secrets and private chain-of-thought are excluded.

## 3. Decision transaction

The proposed P3 runtime port is separate from the legacy return type:

```text
create_p3_runtime(actor_id:string, policy_config:P3PolicyConfig,
                 own_identity:ResidentIdentity, restored_state:ResidentRuntimeStateP3|null,
                 live_enabled:boolean, provider:ProviderAdapter|null, budget:DecisionBudgetPort,
                 attempts:AttemptJournalPort, own_records:DecisionRecordP3[]|null)
                 -> ResidentRuntimeP3
ResidentRuntimeP3.ingest(delivery:BoundaryPerceptionDelivery) -> None
ResidentRuntimeP3.make_request(tick:N,triggers:DecisionTrigger[]) -> DecisionRequestP3
ResidentRuntimeP3.decide(request:DecisionRequestP3) -> DecisionRecordP3
ResidentRuntimeP3.commit_decision(record:DecisionRecordP3) -> None
ResidentRuntimeP3.export_state() -> ResidentRuntimeStateP3
CallReservation {
  allocation_key:Hash,reservation_ordinal:N,call_id:string,
  input_reserved:N,output_reserved:N,money_reserved:N
}
DecisionBudgetPort.admit(call_id:string,input_tokens:N,output_tokens:N,
                         provider_request_sha256:Hash,wire_body_sha256:Hash)
                        -> CallReservation|null
DecisionBudgetPort.commit(decision_id:string,debits:CallDebit[]) -> None
AttemptJournalPort.stage_context(record:ContextRecordP3) -> None
AttemptJournalPort.before_call(context:ContextRecordP3,record:AttemptDispatch) -> None
AttemptJournalPort.after_call(record:LLMCallRecordP3) -> None
```

decide returns a fully validated **staged** record; run_id is established by own
delivery. It does not advance ordinal or publish cognitive/private state. Sim queues
and buffers that exact record, commits its reserved debits through the budget port
and calls commit_decision; runtime checks equality with its staged record. No save,
export or tick between these operations. Both validators run before mutation; failure
stops the boundary. Each record's budget and runtime commits occur exactly once.
Only sim/persistence implement global budget and durable journal ports; agents cannot
read their storage. The live budget port is bound to the case's held allocation lock
and generation; it cannot be built from run_budget alone. admit durably reserves in
that authority before returning. before_call verifies this exact reservation and
must durably flush before returning; after_call
retains terminal audit. No journal read/query method is exposed.
After preparation and before admission, stage_context durably appends exactly one
full context row for every decision, including rule-primary and zero-call decisions.
Calls occur in the same tick/actor order as decisions, so a later actor's dispatch
cannot overtake an earlier actor's context. before_call verifies the already staged
context identity and appends only the dispatch; retries never append another context.
All such rows remain uncommitted until checkpoint publication. A failed context flush
stops the boundary before dispatch. A reservation already persisted before a later
flush failure is retained for recovery, never released by process rollback.
No separate zero-call publication path exists.

Runtime instantiates the frozen fallback from fallback_config and saved private state.
own_records is null for live/control execution and the actor's verified complete record
slice for recorded-p3-v0. In recorded mode provider is null; in live mode it is required
only for registered LLM actors with live_enabled. Replay stages recorded debits without
admission or dispatch. Factory verifies identities/config/version before returning;
wrong actor/config is startup refusal. A control runtime may use provider=null.

### 3.1 Errors and boundaries

```text
DecisionErrorP3 = INVALID_CONTEXT | INVALID_PLAN | INVALID_DELTA | PARSE_ERROR |
                  TIMEOUT | BUDGET | PROVIDER_ERROR | REPLAY_DIVERGED
DetailCode = null | MANDATORY_OVERSIZE | INPUT_LIMIT | OUTPUT_LIMIT |
             INVALID_JSON | INVALID_ACTION | INVALID_COGNITION |
             ATTEMPT_TIMEOUT | DECISION_TIMEOUT | ADMISSION_DENIED |
             PROVIDER_REJECTED | INTERRUPTED_CALL | RECOVERY_OFFLINE
```

Programming exceptions, invalid restored input, broken hashes and replay divergence
stop the run; never hide them with fallback. INVALID_CONTEXT means typed mandatory
context cannot fit; stale tick, wrong actor or broken invariants are programming errors.

Classify in this order: adapter timeout -> TIMEOUT/ATTEMPT_TIMEOUT; provider_error ->
PROVIDER_ERROR/PROVIDER_REJECTED; output_limit -> PARSE_ERROR/OUTPUT_LIMIT; invalid
UTF-8/JSON/top-level shape -> PARSE_ERROR/INVALID_JSON; invalid action shape/IDs ->
INVALID_PLAN/INVALID_ACTION; invalid goal change -> INVALID_DELTA/INVALID_COGNITION.
If both action and goal are invalid, action classification wins; neither is committed.

| Step | Rule | Mutation |
| --- | --- | --- |
| Ingest | Stage own experience and goal evidence together, then acknowledge once | Cognitive state/cursor even without a decision |
| Prepare | Freeze request/assembly; calculate identities and fit | None |
| Admit | Check live mode, time and registered call/token/money caps | Durable dispatch reservation only |
| Call | One bounded result, world time frozen | Terminal attempt audit only |
| Validate | Exactly one JSON object; actions and delta valid together | None |
| Retry | Classified failure, identical request, next index, budgets rechecked | None |
| Select | First valid proposal or section 5 fallback | Stage plan/delta/private state/debits |
| Commit | Sim queues/buffers matching plan/record; runtime validates and publishes once | Own plan refs/experience, delta, private state, ordinal, budget debits |
| Advance | Sim emits existing fallback fact; world executes | World changes physical state |
| Publish | Flush logs then phase-7 snapshot | Durable boundary per section 6 |

Retry PARSE_ERROR, INVALID_PLAN, INVALID_DELTA, TIMEOUT, PROVIDER_ERROR or OUTPUT_LIMIT
only within all B limits/budgets. INPUT_LIMIT, MANDATORY_OVERSIZE and admission refusal
make zero calls. Stop at first valid response: no voting, repair call or hidden retry.
Later world action failures are not provider failures. Validate action structure;
world alone validates physical legality.

Plan, accepted delta, own plan refs/experience, private state, ordinal and debits are
one logical transaction. Rejecting it discards all staged changes. Sim cannot save or
advance between decide and commit. Classified failure never undoes ingested experience.
Fatal exception discards the partial boundary; recover prior durable checkpoint.

### 3.2 Record and equality

```text
DecisionRecordP3 {
  record_schema_version:"0.2", run_id:string, decision_id:string,
  tick:N, actor_id:string, decision_ordinal:N, policy_id:"llm-v0"|"rule-based-v0",
  effective_policy_id:"llm-v0"|"rule-based-v0"|"sim-fallback-wait",
  triggers:DecisionTrigger[], request_sha256:Hash, status:"ok"|"error",
  error_kind:DecisionErrorP3|null, detail_code:DetailCode, plan:ActionPlan,
  substituted:boolean, llm_call_id:string|null, context_sha256:Hash,
  projection_sha256:Hash|null, accepted_delta:CognitiveDelta, call_ids:string[],
  state_before_sha256:Hash, state_after_sha256:Hash,
  fallback_error:"INVALID_PLAN"|null, policy_private_after:P3PolicyPrivateState,
  budget_debits:CallDebit[]
}
```

This record does not inherit the legacy validator. policy_id equals actor config.
For llm-v0, ok means valid LLM output: no errors/detail, substituted=false, effective
llm-v0. For rule-primary controls, ok means accepted rule output: effective
rule-based-v0, no errors/detail/calls/debits, substituted=false and continue delta.
Otherwise status error and
substituted=true with rule/wait effective policy and primary failure. REPLAY_DIVERGED
is never committed. fallback_error is set only when malformed rule output causes
the existing single wait substitute; unexpected rule exceptions stop.

call_ids holds all dispatched attempts in index order (zero to B-01 entries).
llm_call_id is successful call for ok, else last call or null if none. Rebuild all IDs
with registry builders. Plan actor/tick/ordinal always match even for substitute.
Every joined context/dispatch/call shares run, decision and request identities.
No call belongs to two decisions.

| Hash | Canonical object without final LF |
| --- | --- |
| request_sha256 | Full DecisionRequestP3, not projection |
| context_sha256 | ContextAssembly.context |
| projection_sha256 | Exact ProviderProjection; null on assembly failure |
| state_before_sha256 | Full committed ResidentRuntimeStateP3 after ingest, before request |
| state_after_sha256 | Full ResidentRuntimeStateP3 after commit, including next ordinal |
| provider_request_sha256 | Exact ProviderRequest, stable across retries |

State hashes exclude pending transactions and global budget. Latency, wall clocks,
provider IDs and raw chunk boundaries are outside semantic equality. Budget debits
derived from usage are separately recorded deterministic inputs; replay copies them.
Audit-file hashes still bind exact original bytes; replay copies audit rows without
inventing new timings.

## 4. Budget and attempt recording

### 4.1 Admission ledger

Live trials supply explicit evaluation-registered attempt, input-token, output-token
and integer micro-CNY caps before startup. No unlimited/default live trial. Fake
fixtures register deterministic caps and zero prices. Pin conservative uncached
rates; ignore cache discounts for admission. This is an admission cap, not a guarantee
about a provider invoice. Usage exceeding its reservation is a provider contract
violation: retain the result, stop live execution and report overrun.

```text
CallDebit {
  call_id:string, input_reserved:N, output_reserved:N, money_reserved:N,
  input_reported:N|null, output_reported:N|null,
  input_charged:N, output_charged:N, money_charged:N, usage_unknown:boolean
}
BudgetCaps { attempts:N, input_tokens:N, output_tokens:N, micro_cny:N }
BudgetLedgerP3 {
  budget_schema_version:"0.1", allocation_key:Hash, caps:BudgetCaps,
  attempts_charged:N, input_charged:N, output_charged:N, money_charged:N,
  unknown_usage_count:N, recovery_debits:CallDebit[]
}
```

Reserve `I=count_input_tokens(request,wire)`, `O=max_output_tokens` and
`money_reserved=ceil(I*input_rate/1000000)+ceil(O*output_rate/1000000)` with integer
arithmetic. Admit iff the authoritative allocation's settled/recovery charges plus
all reserved entries plus this attempt stay <= every cap. Never use a checkpoint's
remaining balance for admission. Compare each dimension independently: attempts=0
admits no calls; a zero money cap permits a zero-money fake reservation. Calls are serial in
canonical actor order. Reservations consume capacity before decision commitment and
hold their full amounts until checkpoint finalization, even after a terminal result.

If both reported counts exist and fit reservations, charge them and the same rounded
formula. If either is unknown, charge both full reservations, usage_unknown=true;
preserve nullable reported counts, never turn unknown into zero. No later refund
changes the simulation; invoice reconciliation is an external report. Every dispatched
attempt becomes one debit, including invalid retries. Committed decision debits plus
recovery_debits sum exactly to ledger totals; unknown_usage_count counts unknown debits.
An overrun uses max(reported,reserved) in recovery accounting and invalidates the trial.

### 4.2 Durable allocation ownership and continuation

One registered case has one allocation for its entire execution and continuation
lineage. Its key is SHA-256 of the canonical object
`{registration_sha256:Hash,case_id:string}` without LF. Caps equal that exact
TrialCase's caps; case allocations cannot borrow from each other. Their sum stays
within the registration aggregate. Output directories, checkpoint copies, receipts,
process restarts and replays never create an allocation or reset its consumption.

```text
AllocationHead {
  checkpoint_sha256:Hash, checkpoint_tick:N, input_manifest_sha256:Hash,
  run_directory:string, reservation_cursor:N
}
AllocationEntry {
  reservation:CallReservation, provider_request_sha256:Hash, wire_body_sha256:Hash,
  state:"reserved"|"settled"|"recovery", debit:CallDebit|null,
  terminal_call_sha256:Hash|null
}
CaseAllocationP3 {
  allocation_schema_version:"0.1", allocation_key:Hash,
  registration_sha256:Hash, case_id:string, caps:BudgetCaps, generation:N,
  status:"ready"|"running"|"offline_only"|"complete",
  head:AllocationHead|null, prepared_head:AllocationHead|null,
  pending_recovery_sha256:Hash|null,
  entries:AllocationEntry[]
}
```

The launcher enrolls one canonical, local authority root when the allocation is
first authorized. It is shared by all launchers/worktrees and outside all run/output
directories. The create-once enrollment binds the registration/case key to
`<authority_root>/allocations/<allocation_key>.json` and its persistent lock file.
Only initial authorized enrollment may create this record (empty entries, generation
0, status ready, null heads/pending recovery). A run/resume cannot enroll a second root, re-create a
missing record, restore an older authority from a checkpoint, or treat a copied
record as an independent grant. Missing/mismatched authority or enrollment refuses
live use with ALLOCATION_UNAVAILABLE; retained artifacts remain replayable offline.
This is a single-host authority with durable local storage, not a distributed lease.
Moving/cloning authority storage is not an ordinary continuation and is not supported
as a way to obtain live capacity. Store loss never permits automatic re-enrollment.

Hold an OS-managed exclusive process lock on that case's persistent lock file for
the whole live execution, including provider IO, terminal logging, checkpoint writes
and shutdown. Do not replace/unlink the locked file. Acquisition is nonblocking:
another holder gives ALLOCATION_BUSY and zero calls. There is no clock/TTL expiry,
force takeover or timeout-based budget reset; process death releases the lock.
Under the lock, validate the authority, reconcile prepared_head, then atomically
increment generation before running. Every reservation, dispatch and publication
checks the held lock and generation; a stale handle stops with ALLOCATION_STALE.
These are coordinator startup/integrity errors, never resident fallback reasons.
A persisted running status with no OS lock holder is recoverable; that status alone
neither blocks lock reacquisition nor proves that a prior call did not happen.

entries are ordered by reservation.reservation_ordinal = array index, starting at
0, with unique call_id and matching allocation_key. reserved has null debit and
terminal_call_sha256; settled has its exact debit and non-null terminal row hash;
recovery has its conservative debit and the terminal hash when available. All debit
IDs/reservation amounts match the entry. Count every entry as one consumed attempt.
terminal_call_sha256 hashes the canonical terminal row object without LF.
For reserved entries, use full reserved tokens/money; for settled/recovery, use the
debit's charged values. Recovery charges are at least the full reservation. A repeated
call_id is ALLOCATION_DUPLICATE_CALL, never an idempotent permission to send again.
Terminal results do not refund capacity until their boundary becomes durable.

On every authority load, head.reservation_cursor equals the length of its verified
checkpoint allocation_entries, and entries up to that cursor equal the checkpoint
mirror byte-for-byte. The remaining suffix consists of reserved entries, or the
recovery entries named by pending_recovery_sha256. A prepared target preserves the
entire finalized prefix and resolves only this suffix using verified terminal/origin
evidence. A cursor beyond entries, changed prefix or inconsistent target is an
integrity refusal, never a reason to reset or recompute allowance from a snapshot.
A null head is allowed only before tick-zero publication, with an empty entry array.

Admission atomically appends and durably flushes a reserved entry **before** the
dispatch log can be flushed or any network IO can start. Keep it even if the later
dispatch write fails or no response arrives. The run's decision transaction commits
its replay ledger, not a second grant or an additional authority debit. Only section
6's checkpoint finalization changes covered entries from reserved to settled once.
No later correction of usage refunds a finalized charge. Rejected duplicate restores
consume no attempts; they also receive no copy of remaining capacity.

head identifies the only checkpoint eligible to continue this case, not every
historical checkpoint with a valid hash. A clean continuation must match head exactly;
after another continuation advances it, the old source gives ALLOCATION_STALE.
A duplicate request while the first runs gives ALLOCATION_BUSY; after completion
it gives ALLOCATION_CLOSED. A clean pause with no progress may reacquire the same
head using the same entries and remaining capacity. status complete closes the case
at its registered horizon; offline_only can transition only to complete, never back
to live-capable ready/running, within this allocation.
None of these transitions resets caps, entries or generation.

Ordinary already-authorized continuation of the current clean head needs **no new
owner approval**. It reuses the original grant, not its original amount. A new trial,
changed registration/caps or additional live allocation needs a separate authorized
registration. Crash recovery follows section 7; copied or stale checkpoints may be
used for read-only recorded replay, which cannot acquire or modify this authority.

### 4.3 Log schemas

```text
ContextRecordP3 {
  context_record_version:"0.1", run_id:string, decision_id:string,
  request:DecisionRequestP3, assembly:ContextAssembly,
  provider_request:ProviderRequest|null
}
AttemptDispatch {
  dispatch_schema_version:"0.1", run_id:string, decision_id:string,
  call_id:string, actor_id:string, tick:N, decision_ordinal:N, attempt_index:N,
  request_sha256:Hash, context_sha256:Hash, projection_sha256:Hash,
  provider_request_sha256:Hash, provider_request:ProviderRequest,
  wire_request:WireRequest, wire_body_sha256:Hash,
  allocation_key:Hash, reservation_ordinal:N,
  prompt_version:string, action_schema_version:string,
  adapter_id:string, adapter_version:string, model_id:string,
  input_reserved:N, output_reserved:N, money_reserved:N
}
LLMCallRecordP3 {
  call_schema_version:"0.1", run_id:string, decision_id:string,
  call_id:string, actor_id:string, tick:N, decision_ordinal:N, attempt_index:N,
  dispatch_sha256:Hash, result:ProviderResult,
  parsed_proposal:DecisionProposal|null, validation_error:DecisionErrorP3|null,
  detail_code:DetailCode, debit:CallDebit
}
```

Context rows are one per committed decision; assembly retains inclusion manifest.
assembly.context must equal request.context and every corresponding hash must agree.
provider_request is null only when preparation produced no dispatchable request.
After durable authority admission and before network IO, append and durably flush exact input/reservation to
llm-dispatches.jsonl. Flush failure means no dispatch. Each terminal call row joins
one dispatch; parsed_proposal exists iff JSON/schema parsing succeeded, including
later semantic rejection. Only fully valid proposals may be accepted. At durable
boundary, llm_record_cursor=dispatch_record_cursor=sum(committed call_ids lengths).
Attempt rows sort tick, actor ID, ordinal, attempt index; context/decision rows sort
tick, actor ID. No credentials, headers or environment values are retained.
wire_body_sha256 hashes decoded exact outbound body bytes; verify it before sending
and during replay audit. Retries have identical provider_request and wire body hashes.
The allocation key/ordinal, call ID, both request hashes and reserved amounts match
exactly one authority entry. No dispatch without this entry is valid.

Incomplete tails cannot be promoted to accepted decisions. Missing terminal row
means unknown usage. Complete orphan rows are billing evidence only. Explicit null
distinguishes absent response from empty response and parse failure.

## 5. Stateful rule fallback (OQ-083)

The P3 wrapper is fallback-adapter-v0.1; standalone rule-based-v0 remains frozen.
It projects the latest raw Perception, profile_id with values=[], initial direction
as legacy initial goal, recalled_episodes=[], beliefs=[], current_plan_summary=null
into legacy DecisionRequest. Preserve actor/tick/global ordinal/triggers. No P3
memory is disguised as current perception; no hidden world or synthetic history.

| Prior mode / result | Adapter action | New private state |
| --- | --- | --- |
| Initial llm / primary fails | Initial rule state; decide once | fallback; accepted rule state; current ordinal |
| fallback / primary fails | Preserve full state; frozen rule handles current packet/expiry | fallback; accepted next state; current ordinal |
| fallback / primary succeeds | Do not execute rule; freeze its state | llm; old rule state/last fallback ordinal |
| llm after accepted LLM / primary fails | Clear stale rule commitment/issued_intents; remove only deadlines <= current tick; preserve unexpired failures/local entries, cues/capacity; execute once | fallback; accepted next state; current ordinal |
| Any / malformed rule output | Discard staged rule change; single wait substitute | Entire prior private state unchanged |

Refresh is staged and published only upon acceptance. No rule entries gain facts from
LLM output or shared experience; no unexpired failure deadline is shortened. Frozen
rule learning stays decision-only: during LLM control, experience captures all own
packets but rule private state does not. M8 approved this explicit tradeoff; it
avoids retrospective fake perceptions and preserves P2 behavior. Shared OwnedIntentRef
is independent of rule issued_intents, resolves own delayed feedback before replacement
and embeds resolved history. Clearing private refs cannot erase ingested evidence.
No old delivered feedback is replayed into the rule policy.

All fallback plans use current global ordinal and are captured as own effective
accepted decisions. Delta is continue(expected current goal ID, proposal=null),
including terminal/current-null cases permitted by cognition. Goal evidence ingestion
continues; fallback cannot assert completion or silently revise. Next eligible
decision tries LLM again unless budget/live mode denies dispatch. No cooldown, extra
tick, alternate scheduler or model call is added.

Sim emits exactly one agent_fallback_used fact per substituted decision through the
existing world append_fact port, in actor order before starts. Its tick is the
engine's newly opened interval tick; decision tick remains the prior committed
boundary (`backend/src/living_island/world/engine.py:276`, `backend/src/living_island/world/engine.py:326`).
actor_id/payload.resident_id are this actor; target_id/intent_id null;
llm_call_id matches decision; caused_by_event_ids=[]. fallback_policy_id is effective
rule or wait. Reasons map TIMEOUT -> TIMEOUT; PARSE_ERROR/INVALID_PLAN/INVALID_DELTA
-> PARSE_ERROR; INVALID_CONTEXT/BUDGET -> BUDGET; PROVIDER_ERROR -> PROVIDER_ERROR.
Detailed error and fallback defect stay in the decision record; no new world reason.
Rule-primary controls use the same continuous rule lifecycle but no LLM attempts,
substitution flag, error or fallback fact. A malformed rule-primary plan is a defect:
record INVALID_PLAN/INVALID_ACTION with sim-fallback-wait and fallback_error=INVALID_PLAN,
then mark the trial technically invalid; no agent_fallback_used event because no LLM
failed. Unexpected rule-primary exceptions stop the run.
For rule-primary actors, last_fallback_ordinal records the last accepted rule execution
ordinal too; it is private lifecycle bookkeeping, never the fallback metric numerator.

## 6. Save composition and integrity

```text
LogPrefix { name:string, records:N, sha256:Hash }
AgentStateP3 {
  profiles:[], goal_states:[], personal_memories:[], relationships:[],
  queued_plans:ActionPlan[], deferred_decision_triggers:DeferredDecisionTriggers[],
  delivered_perception_ticks:DeliveryCursor[], runtime_states:ResidentRuntimeStateP3[]
}
SavePackageP3 {
  save_schema_version:"0.2", world:WorldState, agent_state:AgentStateP3,
  event_cursor:N, llm_record_cursor:N, decision_record_cursor:N,
  context_record_cursor:N, dispatch_record_cursor:N,
  pending_perception_deliveries:BoundaryPerceptionDelivery[],
  canonical_config_hash:Hash, canonical_map_hash:Hash, input_manifest_sha256:Hash,
  log_prefixes:LogPrefix[], run_budget:BudgetLedgerP3,
  allocation_entries:AllocationEntry[], live_enabled:boolean
}
```

Four placeholder arrays stay empty: runtime cognitive state is the only authoritative
copy. Runtime/queue/cursor arrays sort by actor ID. Existing pre-ingest invariants
S1-S11 apply with P3 runtime; pending packets retained verbatim. Also validate:

- context_record_cursor=decision_record_cursor=sum(next_decision_ordinal).
- llm_record_cursor=dispatch_record_cursor=sum(call_ids lengths); cursors are counts.
- log_prefixes lists exactly contexts-p3.jsonl, decisions-p3.jsonl, events.jsonl,
  llm-calls.jsonl, llm-dispatches.jsonl in filename order; records agree with cursors;
  hashes cover precisely their complete committed LF-terminated lines.
- Context/call/dispatch/decision references and hashes resolve; no duplicate IDs,
  missing committed rows, skipped attempt indices or dangling references.
- Rule-state validation uses saved fallback config and runtime tick/ordinal.
  Unknown nested versions/fields and invalid references are refused.
- Ledger totals match committed debits and verified recovery origins. Caps, pricing,
  identity/template/schema/context/adapter IDs match retained inputs. Verification
  and replay need no credential.
- allocation_entries is the immutable settled/recovery prefix for this checkpoint;
  no reserved entry is allowed. Its allocation key, order, unique call IDs and debit
  sum equal run_budget; normal entries join dispatch/call rows, recovery entries join
  verified origins. It is a replay mirror, never a live authority or reusable grant.

Publish an atomic checkpoint every completed boundary, tick zero included. First
durably flush complete event/decision/context/dispatch/call prefixes, then atomically
publish checkpoint-<tick padded to 10 decimal digits>.json using the protocol below.
Snapshot is the simulation-state commit authority; the allocation owns spend even
before a snapshot exists. Append success alone is not simulation commitment. Never
save a pending decision or a normal dispatch without a verified terminal row.
Authority entries may still be reserved while their finalized snapshot mirror is
being published; the ordered protocol below completes them. No self hash in
snapshot. Persistence uses platform durable-file APIs and tests each crash point;
world performs no IO.
P3 snapshot bytes are canonical UTF-8 JSON without LF; checkpoint_sha256 hashes those
exact bytes. This rule applies only to the new P3 snapshot format.

Under the held allocation lock, first derive candidate allocation_entries from the
verified terminal rows and any imported recovery entries. Flush the candidate's log
prefixes, compute exact snapshot bytes/hash, then durably set prepared_head to that
hash, tick, input manifest, output locator and entry count. Only then atomically
publish the snapshot. Finally atomically replace authority head with prepared_head,
clear prepared_head and finalize its covered entries to the snapshot's exact prefix;
at the registered final tick set status complete. No further dispatch or clean lock
release precedes this finalization. For a nonfinal clean pause set status ready;
offline_only remains offline_only until final closure; complete takes precedence at
the horizon and the saved live_enabled remains false. Snapshot excludes authority heads, generation,
status, pending recovery pointer and paths, so there is no self/hash cycle or
nondeterministic replay state. Candidate settled entries are only staged evidence
until the target checkpoint exists and verifies; preparing bytes releases no capacity.

On reacquisition, a prepared target with exact valid snapshot bytes and prefixes is
finalized once before accepting a source checkpoint. If that target is absent, clear
prepared_head, retain the old head and every reservation, then apply section 7's tail
rules. A present partial/corrupt target is an integrity refusal, never permission to
fall back to an older grant. A crash after publication but before head finalization
therefore cannot make the old checkpoint spendable again. Tick zero uses this same
publication protocol; no provider dispatch is allowed until its head is finalized.

Retained inputs have this closed schema in p3-inputs.json:

```text
P3InputManifest {
  input_manifest_version:"0.1", run_id:string,
  files:[{name:string,sha256:Hash}]
}
ImplementationPin {
  implementation_pin_version:"0.1", code_commit:string (40 lowercase hex),
  modules:[{role:"adapter"|"counter"|"goal"|"runtime"|"schema"|"selector",
            files:[{path:string,sha256:Hash}]}]
}
```

files contains exactly the names below, sorted by UTF-8 name; no directory separators,
duplicates, missing/extra entries or null hashes. Verify bytes before parsing. Module
roles appear exactly once in the enum's listed order, each with a nonempty path-sorted
unique file list. Paths are repository-relative POSIX paths to tracked source files,
with no absolute path or `..`; hashes cover source bytes at code_commit. The archived
source revision must be available for replay. No adapter/counter identity is inferred
from a mutable installation. Snapshot input_manifest_sha256 hashes canonical manifest
object without LF; manifest does not hash itself.

| Filename | Exact retained contents |
| --- | --- |
| config.json | Existing canonical typed effective world config |
| map.txt | Existing canonical map bytes |
| p3-policy-configs.json | Canonical array of `{actor_id:string,config:P3PolicyConfig}`, sorted by actor ID |
| identities.json | Canonical ResidentIdentity array sorted by actor ID |
| identity-sources.json | Canonical array of cognition section 1 resolved source objects `{actor_id,display_name,profile:ProfileDocument,initial_direction}`, sorted by actor_id; verify each identity.source_sha256 against this object |
| prompt.txt | Cognition's pinned canonical prompt-template bytes |
| action-schema.json | Canonical cognition-owned ModelActionContract |
| context-profile.json | Canonical experience-owned ContextProfile; exact config/manifest strategy binding |
| trial-registration.json | Canonical evaluation-owned registration |
| implementation.json | Canonical ImplementationPin |

All actors share the registration's prompt/action/context-profile/adapter/counter/limit/pricing pins;
actor identity and primary policy membership vary. Registration is hashed before
expanding per-actor P3PolicyConfig and must not include their full config hashes (that
would be circular). Input manifest is assembled last. Recorded configuration's
trial_registration_sha256 and all content hashes must agree with retained bytes.
The selector role pins the selected strategy and pure dependencies, including tracked
test helpers for a fake-only selector. Registration input_pins includes those helpers
even though its production implementation inventory excludes tests. Validate the
experience spec's profile table, actual manifest IDs and the fake-only restriction;
matching recall bytes alone cannot establish strategy identity.
Continuation prefixes include verified ancestors; output contains suffix logs/origin
and byte-identical retained inputs. Source files are never modified or repaired.

## 7. Restore, interrupted calls and replay

### 7.1 Completed checkpoint

Verify snapshot, all prefix counts/hashes/links, inputs and ancestor chain before
creating output. Source/destination distinct; output fresh. Restore active progress,
queued intents, all cognitive/private state and budget. Runtime is cold until exact
pending packet ingested; never redraw active/queued plans.

For live continuation, acquire the existing case authority and reconcile publication
before validating that the source is its current head. No extra dispatch bytes is
necessary but not sufficient: there must also be no authority entries beyond the
checkpoint's allocation_entries. A clean head uses the authority's remaining registered
budget with no repeated approval, even from a fresh output directory. Separate live continuations are not promised identical. Fake/recorded
continuations must match event/decision/world/cognitive state. Legacy P1/P2 restoration
uses its original path.

### 7.2 Partial tails and billing

| Tail relative to chosen checkpoint | Required result |
| --- | --- |
| No extra dispatch bytes or authority reservations; partial event/decision/context tail | Preserve source, ignore tail for state, continue current head under the same allocation |
| Authority reservation beyond head, even with no dispatch bytes | Ordinary live resume refuses INTERRUPTED_CALL_RECOVERY_REQUIRED; do not release or redispatch it |
| Complete extra dispatch, with or without result | Ordinary live resume refuses INTERRUPTED_CALL_RECOVERY_REQUIRED |
| Partial/unparseable extra dispatch or ambiguous attempt | Same refusal; never guess whether call occurred |
| Truncation/hash error inside committed prefix or missing file | Refuse all restore/replay; never trim to manufacture validity |
| Invalid later checkpoint after a valid earlier one | Report corruption; never silently choose the older one |

Inspect both the authority tail and run logs while holding the lock; checkpoint-only
inspection cannot prove zero spend. No SDK idempotency assumption permits repeating a possibly billed request. Explicit
offline-recovery may continue through rule fallback only, with zero new provider
calls for the whole continuation. It must start at current authority.head, just like
live continuation; a pending recovery reopens only its recorded source checkpoint.
Old heads are stale after either mode advances, and complete refuses either mode.
First durably retain the pre-recovery authority
tail, orphan run artifacts and a complete immutable ResumeOriginP3, stored by its
canonical hash under the enrolled authority root. Then atomically latch the same
authority offline_only, set pending_recovery_sha256 to that origin and transition
the listed entries to recovery. On a crash, a non-null pointer resumes that exact
origin; do not construct or import a second one. A source copy is retained in the
new output's resume-origin-p3.json; its hash and all referenced artifacts must agree.
Copy every referenced orphan artifact and authority-tail byte into the output's
immutable `recovery-evidence/<sha256>.bin`, using the hash as the filename. Resolve
orphan_artifacts by their name/hash mapping to these files (or verified retained
ancestor copies), never by opening the authority root during replay. Duplicate
hashes may share one exact file. Flush those files and the origin before publishing
the first recovery checkpoint; missing or mismatched evidence refuses replay.
Finalizing the first recovery checkpoint clears the pointer only after the imported
entries/origin are durable. Unreferenced pre-latch evidence creates no consumption.
Import one recovery debit per authority reservation beyond the chosen head, in
ordinal order, charging full reserved amounts; reported usage may only increase
charge. Missing terminal rows mean unknown usage. A missing/partial dispatch row
still has the authority's complete reservation identity and amounts: do not invent
another placeholder debit or lose that reservation. A dispatch with no matching
authority entry, conflicting hashes or an unverifiable tail refuses recovery.
Mark those same authority entries recovery once; never append another reservation
for an import. Reopening recovery must finish/reuse this same transition and origin,
not charge it twice. A valid prepared recovery checkpoint finalizes normally.

ResumeOriginP3 is closed:
`{origin_version:"0.2",source_run_id,checkpoint_tick,checkpoint_sha256,log_prefixes,
source_input_manifest_sha256,recovery_mode:"complete"|"offline",
allocation_key:Hash,orphan_artifacts:[{name,sha256}],
recovery_entries:AllocationEntry[],recovery_debits:CallDebit[]}`.
Types: IDs/names are strings, tick N, hashes Hash, log_prefixes LogPrefix[]. Sort
artifact names; bind complete source-file bytes, including the retained authority-tail
copy. recovery_entries contain the exact recovery-state entries; recovery_debits are
their non-null debits in reservation order. Complete mode has empty orphan/entry/debit arrays.
Import once into run_budget and its allocation_entries mirror; ancestry validation
rejects repeat import. Repeating offline recovery against the same source may only
finish the already recorded case transition, never establish a second live lineage. If debt
exceeds cap, mark trial invalid while allowing physics with zero further model spend.

Every offline llm-primary decision has PROVIDER_ERROR/RECOVERY_OFFLINE; interruptions
are evidenced by origin/orphan records, not a consumable error flag. No new call_ids
or debits. Rule-primary controls retain their ordinary success/defect semantics.
Orphan call records stay
under origin, even if their uncommitted decision ID equals a later fallback decision.
They never become part of committed call prefix or accepted proposals.

### 7.3 Recorded re-execution

recorded-p3-v0 is an execution mode; keep each original primary config.policy_id
for state equality. Recompute own deliveries, experience, goal evidence, context and request
identities. Require actor/tick/triggers/ordinal/version/state-before hash equality.
Validate recorded effective plan/delta, apply accepted goal/experience changes and
install recorded policy_private_after/debits once. Compare state-after and full
checkpoint cognitive/private state/budget/allocation_entries plus canonical world and event bytes.

No provider.complete, count_input_tokens, new selectors or summaries. Verify the
retained ContextProfile against config/manifest and selector implementation pins;
rerun that exact strategy (including the fake-only alternate in its fake lineage),
packing and complete manifest, and hash-check retained exact provider request. Preserve
source decision rows byte-for-byte including fallback provenance; copy original
context/dispatch/call audit rows without new timings. Missing/corrupt/inconsistent
data stops REPLAY_DIVERGED; no wait or model substitution.
Recorded replay uses an isolated in-memory budget mirror: it reads only retained
allocation entries/origins, never opens the authority, acquires a lock, enrolls a
grant, reserves, settles or refunds real capacity. Replaying a checkpoint repeatedly
or concurrently leaves real spend unchanged; replay outputs cannot become live
continuations. Historical authority ownership/generations are not replayed operations.

For an offline recovery lineage, replay reaches the source checkpoint, verifies the
origin and then imports recovery_entries/recovery_debits and live_enabled=false exactly once before
processing its first suffix boundary. Subsequent checkpoint resumes use the saved
ledger/live flag; they never reimport that origin. Orphan calls stay outside normal
call/dispatch cursors and are never replayed as decisions. A fresh re-execution of a
multi-origin lineage applies each verified origin only at its own checkpoint boundary.

Successful full run publishes decision-trace-p3.json after final checkpoint:
`{trace_schema_version:"0.2",run_id,config_hash,map_hash,final_tick,
input_manifest_sha256,final_checkpoint_sha256,log_prefixes,final_world_sha256,
final_runtime_states_sha256,final_budget_sha256}`.
Types: run_id string, final_tick N, log_prefixes LogPrefix[], other fields Hash.
Hash canonical objects (without LF), log prefix bytes (with LF). No completion trace
for interrupted runs. ReplayBundle stays 0.1 unchanged. Separate evaluation/debug
artifact is never resident input.

## 8. Approved limits (M8)

Every row was approved at M8. Measurement does not silently change a bound.

| ID | Approved value / unit | Rationale | Measurement / review |
| --- | --- | --- | --- |
| B-01 | 2 dispatched attempts per decision | One retry, finite cognition | Histogram; third-dispatch refusal |
| B-02 | 30,000 ms per attempt | Bound stalled synchronous world | Injected deadlines; p50/p95/max latency |
| B-03 | 60,000 ms total decision attempt time | Bound two waits | Clock-controlled frozen-boundary fixture |
| B-04 | 0 ms retry delay; 0 SDK retries; 1 concurrent call | One owner of retries/order | Instrument actual adapter invocation order/count |
| B-05 | 32,768 input tokens per attempt | Bounded context plus descriptions | Pinned counter; maximum and rejection frequency |
| B-06 | 2,048 output tokens per attempt | Bounded action/goal JSON | Length, invalid and truncation distribution |
| B-07 | 262,144 raw response bytes per attempt | Bounded malformed bodies with audit | Limit/limit+1 fixture; one sentinel byte is detection only |
| B-08 | 131,072 canonical request UTF-8 bytes per attempt | Bound schema/prompt plus projection | Worst registered input; observed maximum; boundary fixtures |
| B-09 | 1 rule execution per failed primary decision | No fallback loop | Malformed fallback causes one wait only |
| B-10 | 1 checkpoint per completed boundary | Explicit durable commit authority | Bytes/write latency per game day; crash matrix |

Trial attempt/token/money caps belong to [evaluation](p3-evaluation-v0.1.md).
Legacy world limits are unchanged; P3 text limits belong to cognition. B-03 measures
monotonic elapsed attempt preparation/wait/validation time; wall time never enters
deterministic state. If less than B-02 remains, use that positive remainder as attempt
timeout; if none remains, TIMEOUT/DECISION_TIMEOUT with no further dispatch.
Measure from entry to prepare with a monotonic clock. Immediately before final
proposal acceptance, check elapsed time again: elapsed >= B-03 rejects even a valid
proposal as TIMEOUT/DECISION_TIMEOUT. Its parsed proposal/raw result/debit remain in
the attempt row, validation_error=TIMEOUT and detail_code=DECISION_TIMEOUT; no delta
or plan from it is accepted and no retry remains. Elapsed < B-03 permits ordinary
validation/selection. This deadline check takes precedence over the attempt's other
validation result at that point. Fallback/commit follow without another provider call;
B-03 bounds primary decision processing, not disk publication or rule execution.

## 9. Decision and recovery vectors

These are exact implementation oracles. Goal/experience data uses the owning specs'
constructors; they introduce no physical world outcomes.

| ID | Input / fault | Exact expected result |
| --- | --- | --- |
| BD-01 | No goal; valid wait and continue(null,null), attempt 0 | One call; plan actor:p000000, intent i0; ordinal 1; one own decision experience; mode llm |
| BD-02 | Valid wait but wrong expected goal ID on a0; valid a1 | INVALID_DELTA first, no partial mutation; two debits; only a1 committed |
| BD-03 | Both attempts malformed JSON | PARSE_ERROR/INVALID_JSON; one rule execution; continue delta; call_ids a0,a1 and llm_call_id a1; one fallback event |
| BD-04 | Mandatory projection oversized | Zero dispatch/call/debits; context row; INVALID_CONTEXT/MANDATORY_OVERSIZE; one fallback |
| BD-05 | I=100,O=20; rates 750000 input/4500000 output micro-CNY per million; actual=(80,10) | Reserve 75+90=165 micro-CNY; charge 60+45=105; unknown=false |
| BD-06 | Same reservation; reported=(80,null) | Charge tokens=(100,20), money=165, unknown=true; preserve reported null |
| BD-07 | Money cap=200, charged=40, next reservation=165 | Refuse 205>200; zero attempt; BUDGET/ADMISSION_DENIED |
| BD-08 | Failure expires tick 36; fallback reentry tick 35 after LLM | Clear private commitment/issued refs; keep failure to 36; shared refs/evidence remain |
| BD-09 | Same entry tick 36 | Expired failure removed; cues/capacity retained; no synthetic feedback |
| BD-10 | Snapshot decisions=7,calls=9; orphan dispatch a0 without result | Live resume refuses; offline imports one unknown full reservation; no provider |
| BD-11 | Truncated call inside checkpoint's declared 9 rows | Refuse even if 8 rows parse; no repair |
| BD-12 | Replay committed fallback decision | Original decision/event/delta/private state; zero provider/counter calls |
| BD-13 | A and B need calls at one boundary | Canonical actor order; B cannot consume A's pending reservation |
| BD-14 | Failed own give ingested; malformed model output then fallback wait | Failure experience remains; model text/wait cannot assert completed give |
| BD-15 | Registered rule-primary actor decides | ok/effective rule, no calls/error/substitution/fallback event; private rule state advances |
| BD-16 | Actor A has mandatory oversize, actor B calls at the same boundary | stage_context appends A then B; B dispatch follows both; context cursor counts two only at durable boundary, and A has no dispatch. |
| BD-17 | Valid response arrives within attempt timeout; parsing/validation ends at elapsed 60,000 ms (or later) | TIMEOUT/DECISION_TIMEOUT, retained parsed proposal and debit, no accepted model delta, one fallback. At 59,999 ms the otherwise valid proposal is accepted. |
| BD-18 | H0 is the current clean head with the allocation profile below; A resumes H0, publishes H1 after call c0 with actual (80,10), then B requests H0 | Authority has one settled entry, totals (attempts1,input80,output10,money105); B gets ALLOCATION_STALE, zero calls, no changed totals or new allocation. |
| BD-19 | A and B concurrently request H0 | Exactly one process holds the stable case lock and may dispatch; the loser gets ALLOCATION_BUSY with zero calls/reservations. After A publishes H1 the loser cannot use H0. No TTL takeover. |
| BD-20 | Clean pause at H1 from BD-18; resume current H1, next call reserves/reports (20,10) | No new approval or grant; same allocation key, new ordinal1, reserve/charge60, final totals (2,100,20,165). While c0 was unfinalized at H0, a second (100,20) reservation was refused because 165+165>200, even after c0 reported (80,10). |
| BD-21 | Crash immediately before authority reservation is durable | No dispatch is permitted, no new entry; reacquire current H0 and continue using the original grant without approval. |
| BD-22 | Reservation c0 (100,20,165) is durable; crash before dispatch log flush or after dispatch with no result | Ordinary live resume refuses in both cases, including the empty dispatch-log case. Offline recovery imports exactly one entry/debit, totals (1,100,20,165), unknown=true, no redispatch. |
| BD-23 | c0 terminal result/debit105 is durable, but crash before its checkpoint publication | Authority still holds reserved165; offline recovery charges full165 once, reported counts remain (80,10), unknown=false. No 60-unit refund or duplicate debit. |
| BD-24 | Candidate H1 contains settled c0/debit105; crash after checkpoint publication but before authority finalize | Valid prepared H1 automatically finalizes to head H1, totals (1,80,10,105), without approval; H0 is stale. If target is absent, retain reserved165 and require offline recovery; if present but corrupt, refuse all continuation. Preparing bytes alone never releases165. |
| BD-25 | Crash after latching c0 recovery but before its first offline checkpoint; reopen recovery, then repeat after it publishes H1 | Reuse pending_recovery_sha256 and the same entry ordinal0; final totals remain (1,100,20,165). H0 cannot create a second continuation after H1; current H1 stays offline_only. Zero provider calls throughout. |
| BD-26 | Two sequential or concurrent recorded re-executions of H1; authority is unavailable or locked by another process | Each replay rebuilds the identical budget/allocation mirror from retained evidence with zero provider/counter/authority accesses. External entries, generation and spend never change; replay output is not a live grant. |
| BD-27 | Copied checkpoint or new output/root; missing authority, mismatched key, duplicate c0, or closed case | Respectively ALLOCATION_UNAVAILABLE/key validation refusal/ALLOCATION_DUPLICATE_CALL/ALLOCATION_CLOSED; zero dispatch and no cap reset. Same valid authorization never licenses another authority for this key. |

BD-18..27 use one fixed registration/case, caps `(attempts=2,input_tokens=200,
output_tokens=40,micro_cny=200)` and BD-05 rates. H0/H1 stand for exact verified
checkpoint identities, not mutable filenames. c0 reserves 165 and known usage charges
105; the smaller second call charges 60. These tiny fake-only caps are test inputs,
not new M8 live limits. These allocation-port unit vectors supply reservation amounts
directly; full decision fixtures retain B-06 max_output_tokens=2048. Test real OS lock contention with two local processes plus
injected durable-write crash points; do not substitute an in-memory mutex proof.

Physical reach/duration/hearing/completion vectors belong to cognition/experience and
use unchanged engine fixtures. BD-05..07 are integer arithmetic oracles, not measured
provider costs. All vectors are proposed tests, not claims that P3 is implemented.

## 10. Implementation verification

P3-03 proves atomic runtime/debit/cursor commitment, allocation enrollment/lock/head
ownership, all reservation/log/checkpoint crash points, BD-18..27, cold restore and
unknown-version refusal using fakes. P3-04 proves exact
request capture, deadline handling, no SDK retries, counter bounds, response cap and
fallback lifecycle without changing the rule tree. P3-07 proves recorded execution,
compatibility hashes and reports storage cost. Use AGENTS.md checks and meaningful
new tests; type generation leaves unchanged replay schema clean. No runtime tests
or model calls are claimed by this documentation task.
