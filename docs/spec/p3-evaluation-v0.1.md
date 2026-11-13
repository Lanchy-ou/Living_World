# Living Island - P3 evaluation and inspection specification v0.1

> **Accepted at M8, 2026-11-12.** The owner approved the P3 package and CR-005
> amendments, with DeepSeek and an aggregate CNY150 API ceiling superseding the
> earlier provider/USD proposal. See [M8 decision record](../tasks/p3/M8-decisions.md).
> Normative design; implementation and live verification remain separate tasks.

Baseline for every current-code citation: `9bd45082002e87172312484a53c4787020bd584d`.
Unqualified behavior below is **normative**. This document owns fixture coverage,
trial registration, P3 metrics and the separate inspection artifact. It references,
without redefining, [experience/context](resident-experience-v0.1.md),
[cognition/evidence](resident-cognition-v0.1.md) and
[decision/budget/recovery](llm-decision-v0.1.md). The
[plan](../plans/p3-implementation-plan-v0.1.md) owns task scopes and milestones.

## 1. P2-03 tool audit and reuse boundary

The actual P2 tool was inspected before this design. It is not a generic P3 runner.

| Capability now | Baseline evidence | P3 disposition |
| --- | --- | --- |
| Registered seed/revision/variant identities; immutable retained world inputs | `scripts/p2_experiments.py:65`, `:147`, `:181`, `:292` | Keep unchanged for historical P2 controls; reuse pin/hash validation pattern. |
| Batch invokes CLI with replay export and keeps failed/unpublished cases visible | `scripts/p2_experiments.py:344`, `:633`, `:884` | Preserve behavior; a new P3 driver registers every expected case before execution. |
| Public batch duration is fixed at 1,008; short test seam is not a valid short P2 case | `scripts/p2_experiments.py:60`, `:435`, `:651` | P3 driver takes registered horizon; do not relabel a short run as valid P2. |
| Loader and metrics take legacy DecisionRecord/SavePackage | `scripts/p2_experiments.py:395`; `backend/src/living_island/analysis/data.py:52` | New typed P3 loader and read-only plan/event view; never coerce P3 records into fake v0.1 records. |
| Technical checks require identical policy configs across actors and no substitution | `backend/src/living_island/analysis/validity.py:247`, `:264` | New P3 validator uses per-actor pins and allows declared LLM fallback. Existing P2 checks unchanged. |
| Physical metrics use frames/events and own accepted-plan joins | `backend/src/living_island/analysis/metrics.py:221`, `:372`, `:431`, `:583` | Reuse definitions and pure physical calculations; adapt the typed input boundary in new analysis/p3.py. |
| Paired summaries and the historical survival gate are P2-specific | `backend/src/living_island/analysis/compare.py:245`, `:343`; `scripts/p2_experiments.py:826` | New matched P3 report with the registered seeds/horizon; do not import 15/20 or seven-day claims. |
| Rerun launches the original command again and compares bytes | `scripts/p2_experiments.py:980`, `:1012` | Never use for live P3 reproducibility: recorded-p3-v0 is the no-call path; another live trial requires a new registration. |
| Existing character panel shows physical state/events; raw debug shows WorldEvent | `frontend/src/panels/ResidentPanel.tsx:34`; `frontend/src/debug/RawEvent.tsx:3` | Extend in P3-07 with section 6, not by inserting private cognition into ReplayBundle. |

New tooling is `scripts/p3_trials.py` (registration/preflight/run, P3-05),
`scripts/p3_experiments.py` (validate/report/inspection, P3-07),
`analysis/p3.py`, `contract/p3_inspection.py`, `persistence/p3_inspection.py` and
`scripts/gen_p3_inspection_types.py`. No P2 CLI, schema, metric or reference hash changes.
The character/debug UI is included in P3-07 (OQ-089); deferral needs an explicit M8
change to this deliverable. Relationships/emotions display no fabricated placeholder score.

## 2. Deterministic fixtures and fault matrix

A fake provider implements the same port, using a committed closed tape:
`{fake_schema_version:"0.1",fixture_id:string,steps:FakeStep[]}` where FakeStep is
`{actor_id:string,decision_ordinal:N,attempt_index:N,expected_request:ProviderRequest,
expected_wire:WireRequest,expected_input_tokens:N,result:ProviderResult}`. N is a strict nonnegative integer. Steps follow canonical
call order. Equality of the complete request is checked before returning the exact
result; prepare returns the exact expected wire and count_input_tokens returns the
pinned expected_input_tokens after checking both objects. Extra/missing calls fail
the fixture. Timings/usage are scripted data, not
sleeps or network IO. Fixture inputs pin code, world, profile, prompt and schema.
A no-call sentinel raises on prepare, complete and count_input_tokens in recorded mode.

The valid base response is canonical DecisionProposal JSON: one wait template
`{action_type:"wait",target:null,parameters:{},reason:null}` and
`{delta_schema_version:"0.1",goal_change:{operation:"continue",
expected_goal_id:<current ID or null>,proposal:null}}`. Model metadata/IDs are absent.
Variant responses change only the named field. A test harness obtains request bytes
from the approved pure builders and freezes the tape; it cannot weaken comparisons
or regenerate a golden tape after an unexplained mismatch.

| Fixture | Stimulus | Required exact oracle / owning rule |
| --- | --- | --- |
| VF-01 | Base response once | One dispatch, one accepted decision, ordinal +1, continue delta; no fallback. |
| VF-02 | Malformed JSON, then base response | Two attempts of the identical request; only second proposal accepted; two debits, one decision. |
| VF-03 | Two malformed JSON responses | Exactly two attempts; one effective rule plan, one fallback fact, continue delta; rejected output absent from experience. |
| VF-04 | Timeout twice; late success after terminal timeout | At most two attempts within the total deadline; TIMEOUT fallback; a response completing at/after the total deadline is rejected under the decision spec deadline vector, and late body cannot replace terminal row/plan. |
| VF-05 | Provider error then valid response | Two attempts; only valid proposal changes cognition; classified failed attempt retained. |
| VF-06 | Action valid, stale expected_goal_id; then valid | First attempt changes neither plan nor goal; second changes both only on commit. |
| VF-07 | Input mandatory bytes E limit+1; then request B token limit+1 | Separate cases; zero dispatch, correct local failure and rule fallback; full context retained. |
| VF-08 | Trial BudgetCaps.attempts=1 with malformed result; money cap below first reservation | First case one call then fallback; second zero calls. No SDK retry or budget borrowing. |
| VF-09 | Either usage count null | Both charged at full reservation, unknown_usage_count +1; nullable reported values retained. |
| VF-10 | Reported usage exceeds reservation | Retained overrun, live execution stops, technical trial FAIL; no silent refund/zero. |
| VF-11 | Raw body B cap and cap+1, empty body and no body | Exact cap accepted for parsing; over cap bounded prefix/output-limit, empty string distinct from null. |
| VF-12 | Reservation/log/checkpoint crashes plus sequential/concurrent restores, clean authorized continuation, lost authority and repeated replay | BD-18..27 exactly: same case has one durable grant, no stale/duplicate dispatch, pending reservations survive missing dispatch rows, ordinary current-head continuation requires no new approval, recorded replay never accesses authority. Existing BD-10/11 prefix/corruption rules still apply. |
| VF-13 | Truncated committed prefix, unknown version, wrong hash, missing row | Restore/replay refuses; no repair from world, provider or newer checkpoint guess. |
| VF-14 | Rule fallback twice, LLM success, later fallback | Private state entry/execute/return follows decision section 5; unexpired back-off preserved, no synthetic feedback. |
| VF-15 | Malformed fallback output vs raised programming exception | Typed malformed plan gives one wait substitute; unexpected exception stops without committed partial decision. |
| VF-16 | Nondecision transient, duplicate packet, retention/projection overflow | EX-01..10 exactly, including ordinal unchanged without decision and copied evidence after eviction. |
| VF-17 | Request/accept, failed give, completed give, receiving inventory change | CG-01..12 and engine-checked cognition section 4.3; speech alone never completes transfer. |
| VF-18 | Two conflicting stores and a non-hearing third resident | Each context contains own records only; absent speech remains absent; malicious strings create no role/tool. |
| VF-19 | Saved active/queued plan with memory; recorded rerun with sentinel | Identical world/events/decision rows/cognitive-private state and cursors; zero provider accesses. |
| VF-20 | Second fake adapter and second deterministic selector fixture, plus wrong/missing binding and live misuse | EX-11/12 through the existing profile-aware ports: actual strategy/config/manifest IDs agree, each source reruns its own pinned algorithm and manifest, unknown/mismatched/live-fixture bindings refuse before calls. No world/import-boundary change. |

Every closed schema gets positive, unknown-field/version, nullability and foreign-ID
cases. Each E/B/C limit gets exact-boundary and one-unit-over cases. These are test
obligations, not extra runtime rules. Run the short cases in default CI; the V-04 long
fake run is an explicit offline check. Its tape uses the base response for every decision except ella ordinal 1, whose
attempts 0 and 1 time out; the next eligible decision returns to the base response.
Use the smoke seed, three LLM-primary P3 residents, no player commands and no provider
dependency. Pin the fake counter/tape like every other fixture.
VF-20 uses adapter fixture-a and fixture-b with identical base proposals and latency
values 1 and 2 ms respectively: physical/cognitive state matches, diagnostic audit
bytes differ as declared. Its alternate selector is the experience owner's
recent-only-fixture-v0 under context profile p3-context-recent-only-fixture-v0; that
owner alone defines its algorithm, bindings and EX-11/12 exact oracles. Register it
with purpose=fake and fake_fixture_id="vf-20"; retain context-profile.json and pin the
tracked helper plus pure dependencies in input_pins and ImplementationPin.selector.
The production implementation inventory does not include tests, so those explicit
helper pins are required. Exercise both strategy identities with each fake adapter;
replay each source independently with a raising provider sentinel. Compare complete
assemblies, not only state hashes: even empty recall must retain its actual IDs.
Only source-verified fake replay can resolve the alternate; live registrations reject
it. The alternate stays test-only and requires no P3-06 production-code changes.

World failures/deaths are allowed in the long fake run; verify technical consistency,
not seven-day LLM survival. Existing invariant tests must remain green.

## 3. Registered live trials

### 3.1 Seed generation and case matrix

For each list L in smoke, development, acceptance order, try i=0,1,...:
`1 + uint32_be(SHA256(UTF8("living-island/p3/<L>/<i>"))[0:4]) mod (2^32-1)`.
Skip values in either frozen P2 list or any earlier P3 list/current list; stop at the
V count. The following lists were regenerated locally with this procedure:

| List | Seeds in registered order | Horizon T / LLM assignment |
| --- | --- | --- |
| smoke | 1292387875 | V-01; ella only; other two primary policies are rule-based-v0 |
| development | 509071611, 1945790632 | V-02; ella, mia, ryan |
| acceptance | 401604645, 4054202024, 538041037 | V-03; ella, mia, ryan |

Use the unchanged `s2-default:m6` configuration/map from
`7c13d78ffd7d89006f6008c8a09f37ae97c253db`; seed is the only world-input override.
P3-primary selection is explicit sorted unique llm_actor_ids; all actors use P3
runtime/record formats, with deliberate rule-primary decisions distinguished from
LLM fallback. Each acceptance seed also gets one separate legacy all-rule control
at the same T, seed and world inputs. No profile/cue/memory ablation is a hidden
additional arm. Such a trial requires its own future registration and allocation.

Smoke/development inform tuning. Freeze all implementation, profile/prompt/schema,
retrieval, provider/model/settings and price/counter identities before opening
acceptance. If any acceptance result informs a revision, retain it and register
acceptance-r1, r2, ... with the same generation formula and count, excluding every
previous P2/P3 seed. New acceptance runs need a new owner-approved budget; unused
allocations never transfer automatically. No restart or second model response is
free merely because it shares a seed.

### 3.2 Closed registration and execution receipt

Every object is closed; all fields required, nullable only where shown. Hash means
lowercase SHA-256. Strings/enums preserve literal values; arrays have declared order.
A registration is committed before its first live call, with owner approval recorded
in the task evidence. The canonical registration hash excludes no fields and is not
stored inside its own object.

```text
InputPin {path:string,sha256:Hash}
PolicyTemplate = P3PolicyConfig with trial_registration_sha256 removed
TrialCase {
  case_id:string, seed:integer [1,4294967295], ticks:positive integer,
  llm_actor_ids:string[], policy_templates:{actor_id:string,config:PolicyTemplate}[],
  caps:BudgetCaps
}
ControlCase {
  case_id:string,paired_case_id:string,seed:integer [1,4294967295],
  ticks:positive integer,policy_config:PolicyConfig,caps:BudgetCaps
}
TrialRegistration {
  registration_schema_version:"0.1", registration_id:string,
  purpose:"smoke"|"development"|"acceptance"|"fake", revision:positive integer,
  implementation_commit:string, implementation_pins:InputPin[],
  world_pin_commit:string, world_config_path:string, world_map_path:string,
  world_config_sha256:Hash, world_map_sha256:Hash,
  input_pins:InputPin[], cases:TrialCase[],controls:ControlCase[],aggregate_caps:BudgetCaps,
  fake_fixture_id:string|null
}
CaseReceipt {
  receipt_schema_version:"0.1", registration_sha256:Hash,
  registration_commit:string, executed_commit:string, case_id:string,
  command:string[], status:"not_started"|"running"|"complete"|"failed",
  exit_code:integer|null, trace_sha256:Hash|null,
  failure:string|null, run_directory:string, allocation_key:Hash|null
}
```

implementation_pins is the complete tracked backend/src, scripts, backend/pyproject.toml
and backend/uv.lock file inventory at implementation_commit, sorted by path. Execution
may be a descendant containing registration/docs changes only: every pinned source
and inventory must match. input_pins lists actual tracked profile JSON and prompt
files, plus files defining action contract, adapter/counter and context profile.
Resolved identity source objects are derived from the pinned config/profile by the
cognition spec and retained later by the decision spec; they are not assumed to
exist as repository input files. This inventory never
contains credentials. Paths are normalized repository-relative locators; reject
absolute paths, traversal, duplicates or unpinned dependent inputs. policy_templates
sort by actor ID and cover every world resident. Their policy_id equals llm-v0 iff
in llm_actor_ids. Seed/dimensions/plan limit match the effective world inputs.

No hash cycle: first hash the registration containing templates, then expand each
P3PolicyConfig by inserting trial_registration_sha256. The retained input manifest
hashes registration and expanded configs. Receipts, outside registration, record the
actual source commit and command. case_id is `<registration_id>.s<seed>`; each seed
appears once. registration_id matches `[a-z0-9-]+`; revision starts at 1. Cases preserve
seed-list order. Controls are empty except acceptance, where each case has exactly
one paired ControlCase: ID `<registration_id>.control.s<seed>`, equal seed/T, frozen
legacy rule-based-v0 base PolicyConfig and all caps zero. They sort in paired-case
order and receive their own receipt/output directory. They never use P3 template
expansion. aggregate_caps is the component-wise sum of case/control caps; no borrowing.
fake_fixture_id is non-null only for fake purpose; live registrations require null.
Every P3 case receipt has the decision spec's registration/case allocation_key,
unchanged across continuations. Legacy ControlCase receipts have null and create no
P3 authority. A receipt is evidence of execution, not a fresh budget grant.
For receipts, not_started has empty command and null exit/trace/failure; running has
the exact command and null exit/trace/failure; complete has exit0, trace hash and null
failure; failed has non-null failure, nullable actual exit and null completed trace.

Initial authorization enrolls each P3 case's allocation once using the decision spec's
canonical authority root and key. All worktrees/output paths resolve that same
enrollment; validate/run/resume never reconstruct missing authority from a receipt or
checkpoint. Registering the exact same registration/case again does not issue another
grant. Fake cases use isolated test authorities and zero money, never the live root;
recorded replay uses retained mirrors and does not enroll even a fake authority.

The driver creates a not_started receipt for every registered case before dispatch,
then atomically records running and complete/failed status. Missing receipts are
missing cases, never successful cases. Write under ignored runs/p3/<registration_id>/;
source inputs and prior run directories are immutable. Provider preflight checks
pinned availability, request-schema compatibility, proven token counter, prices,
.env-only secret injection and budget before calling. No secret appears in receipt,
command, request, artifacts or exception text. Invalid/missing prerequisite gives zero
calls. A changed price/counter/model requires a new registration approved before use.
Retain continuation receipts as one source-verified case lineage, not additional cases
or trials; a repeated run cannot overwrite the case receipt back to not_started.
The final case receipt identifies the authoritative completed lineage. Reports refuse
competing completed lineages for one allocation and never sum ancestor/suffix copies
as separate grants. Reservation identity is (allocation_key,reservation_ordinal);
deduplicate inherited evidence and reject conflicting entries rather than double-count.

### 3.3 CLI contract and live authorization

These are proposed commands to implement, not commands available in P3-01:

```sh
uv run --directory backend python ../scripts/p3_trials.py validate --registration <file>
uv run --directory backend python ../scripts/p3_trials.py run --registration <file> --case <case_id> --out <fresh-directory> --live
uv run --directory backend python ../scripts/p3_trials.py resume --registration <file> --case <case_id> --checkpoint <file> --out <fresh-directory> --live
uv run --directory backend python ../scripts/p3_trials.py resume --registration <file> --case <case_id> --checkpoint <file> --out <fresh-directory> --offline-recovery
uv run --directory backend python ../scripts/p3_experiments.py validate --registration <file> --receipts <directory>
uv run --directory backend python ../scripts/p3_experiments.py report --registration <file> --receipts <directory> --out <fresh-report-directory>
uv run --directory backend python ../scripts/p3_experiments.py inspect --source-run <directory> --out <fresh-inspection-directory>
```

validate/report/inspect have no provider access. run without --live refuses a live
registration; fake purpose and ControlCase accept no --live. Fake uses its pinned
tape; ControlCase invokes the legacy frozen rule path. The --case selector resolves
exactly one registered case or control, never an ad hoc seed. Credentials
are a launcher concern, not a model tool. Approval of M8 selects the profile; each
registration needs an explicit allocation before first live dispatch. M8 may approve
all the named allocations once; no repeated approval is required for that unchanged
registration. A new or revised allocation requires owner disposition.
run is first execution only; repeated run never resets an allocation. resume resolves
the already enrolled allocation, then obeys current-head/lock/recovery rules in the
decision spec. Ordinary authorized clean continuation asks for no further approval.
--live and --offline-recovery are mutually exclusive; offline recovery grants no live
spend and latches that case offline_only. Neither flag can change caps or establish a
new authority. A new output directory is only an artifact destination.
Recovery and recorded re-execution use the decision owner's API, not run again.
Report records exact invocation and source hashes; never writes into source runs.

## 4. Technical and behavioral acceptance

A live case is runtime-valid iff PV-01..06 pass; final M10 validity additionally
requires PV-07. M9 smoke reports inspection as pending until P3-07, not as passed. A crash/early stop is
invalid even if its prefix can be recovered. Expected-failure fixtures instead pass
when their specified refusal occurs; they are not counted as successful live cases.

| Check | Required evidence |
| --- | --- |
| PV-01 registration | Exact case/seed/T/input pins/actor assignment; complete receipt and exit 0. |
| PV-02 committed records | Final decision trace and tick-zero/final checkpoints validate; all decision/context/dispatch/call links and checkpoint-owned prefixes match the decision spec. |
| PV-03 world/replay | T+1 frames, exact event equality with events.jsonl, config/map/run identity, final world equality and unchanged physical invariant checks. |
| PV-04 cognition | Own-source/goal/intent references, ingestion cursors and every state hash validate; no foreign/private world input; all versions known. |
| PV-05 budget | One enrollment per registration/case; receipts and allocation mirrors agree; every dispatch/reservation counted once across the lineage, nullable usage preserved, caps respected, no orphan/pending/overrun in a complete case. BD-18..27 prove exclusion/recovery; reports are read-only. Unknown usage alone does not invalidate. |
| PV-06 no-call proof | Recorded re-execution with raising provider and authority sentinels reproduces the decision owner's equality targets, actual pinned retrieval strategy and complete manifest; zero grant/reservation/settlement/refund operations. |
| PV-07 inspection | Index and all shards validate; requested input/plan/goal/outcome links resolve; UI imports the artifact with unchanged replay. |

For legacy matched controls PV-02 verifies the legacy trace/checkpoint/log formats,
PV-04 checks legacy runtime/cursors, PV-05 requires zero
calls, PV-06 uses recorded-v0 and PV-07 requires the unchanged replay only; no fake
P3 state or inspection sidecar is generated. These scoped checks replace neither
legacy invariants nor the original P2 experiment gate.

M9 requires VF-01..19, runtime-valid smoke meeting V-05, and a headless inspection of a continuing/revised/abandoned goal
fixture. M10 requires VF-01..20, V-04 long fake proof, all acceptance cases and matched
controls technically valid, the character/debug view, full implementation checks,
and the V-05 operational threshold. Deliberate control-rule decisions are excluded
from LLM-share denominators. Invalid/missing acceptance cases fail the technical gate;
there is no successful-subset substitution or denominator shrinking to pass.

Survival, discovery, adaptation, social outcomes, profile differences and comparative
benefit are descriptive for this P3 pilot. No P2 15/20 threshold is silently imported.
Development reports V-05 descriptively and may inform tuning. Passing V-05 proves substantial use of the LLM interface, not intelligent behavior.
An owner can reject the demonstrated quality at M10; changing quantitative pass lines
requires pre-registration before another acceptance set. The one-day acceptance
horizon is not evidence of seven-day LLM survival. Fresh live runs are never promised
identical; recorded runs are the reproducibility test.

## 5. Metric definitions and exact oracles

### 5.1 Denominators and sources

For a complete case, D is all committed P3 decisions; L is those whose registered
primary policy is llm-v0. A is the set of dispatched attempts linked to L; uncommitted
orphan attempts are reported separately and invalidate completeness. Counts use unique
IDs. Actors are joined by ID; intent joins use the own accepted plan. Fractions are
reported as `{numerator,denominator,value}` with value=null when denominator=0,
otherwise an exact rational string `n/d` (no reduction required). Zero observations
are 0 counts, not missing data. A missing required artifact makes affected metrics
null with `missing_sources` and technical FAIL; never infer it from a different file.

| Metric | Definition / missing rule |
| --- | --- |
| llm_accepted_share | #L with effective_policy_id=llm-v0 and status=ok / #L; per actor and run. |
| fallback_share / wait_share | #L effective rule-based-v0 / #L; #L effective sim-fallback-wait / #L. These three shares sum to 1 for a complete case. |
| deliberate_rule_count | #D primary rule-based-v0; separate from fallback. |
| rejection_share | #A with validation_error in PARSE_ERROR, INVALID_PLAN, INVALID_DELTA / #A. Provider/timeout errors separately counted by error enum; raw JSON parse failure is included. |
| retry_share | #L with call_ids length>1 / #L. Zero-call budget/context decisions remain in #L. |
| unknown_usage_share | #A debit.usage_unknown / #A; reported input/output totals each null if any corresponding reported count is null. Also report known subtotal and missing count. |
| charged_tokens / cost_ceiling_micro_cny | Sum committed CallDebit input_charged/output_charged/money_charged plus separately labelled recovery_debits. This is conservative ledger accounting, never an invoice or zero for unknown usage. |
| latency_ms | On A results with non-null latency: count, min, max, median and p95; sorted nearest-rank p95 at ceil(0.95*n), even median exact half-sum. n=0 gives null summaries; report missing_latency_count. |
| context_oversize_share | #L detail_code=MANDATORY_OVERSIZE / #L; INPUT_LIMIT counted separately. |
| retrieval_inclusion_share | Across L manifests, sum experiences with projected=true / sum retrieved=true; denominator0 gives null. Report evicted_record_count and omitted reasons per manifest, never sum cumulative eviction counters across decisions. |
| goal_transitions | Count accepted goal_change operations by continue/revise/abandon; newly created goal IDs are revise count. Completion is the first appearance of current.status=observed_complete for a goal ID in any verified predecision context or checkpoint state, with inline evidence; terminal repeats count once. This includes completion followed by same-boundary revise/abandon before the next checkpoint. |
| goal_completion_share | Distinct evidenced completed goals / created goals, across committed accepted changes; report retired-incomplete and active-incomplete counts. No promise/text-based completion. A completion in final pending, un-ingested delivery is not yet cognitive completion. |
| evidence_violations | Count invalid/foreign/mismatched completion or experience source links; any count>0 is technical FAIL. |
| given/received, discovery, deprivation, survival, movement, contention/adaptation | Use p2-experiments sections 3/5 definitions exactly at registered T; P3 read-only plan view preserves accepted plans and ordinals. Report A1/repeat/unresolved and completed-give counts; interpretation records never replace objective outcomes. |

The inspector may join objective events for developer comparison, but does not supply
them back to cognition. Goal completion rate is easily changed by chosen goals; no
cross-policy quality claim uses it alone. Retrieval inclusion is an exposure measure,
not proof that a model used a memory. Prompt injection tests assert isolation/output
validation, not an unverifiable universal property of live text generation.

### 5.2 Matched frozen P2 comparison

Use frozen rule tree `837f2f90f6b242477e43c25aec9b359ec51ba331`, base params from
[P2-05](../tasks/p2/P2-05.md#p3-control-and-fallback-identity), same M6 content, seed,
T and command-free world as the P3 arm. The control runs the legacy policy path;
P3 changes resident decision policy only. Verify its P2 source identity and historical
reference hashes under the plan's original inputs before accepting comparison.
The existing P2 batch tool can still reproduce historical 1,008-tick control cases;
short matched controls are launched by the new driver and validated for registered T,
never marked as the original P2 experiment gate.

For each acceptance seed use only a pair with both arms valid; report pairs_expected,
pairs_used, omitted seed/reason, and raw per-case metrics. Any omitted pair fails
PV acceptance, although a descriptive subset summary may still be shown. For every
P2 scalar use d=P3-control; report ordered per-seed d, median/min/max and favorable/
unfavorable/tied counts using the frozen favorable-direction table. Descriptive
scalars get differences only. With zero pairs, summary values are null and counts0.
No tick-by-tick causal comparison after divergence; contention/RNG/paths can diverge.
No significance, general survival guarantee or improved personality claim from three
pilot seeds. Short M6 trials primarily test maintaining access, not blind discovery.

### 5.3 Synthetic metric vectors

| Vector | Inputs | Exact output |
| --- | --- | --- |
| VM-01 | L=4: two LLM ok, one rule fallback, one wait; A=4, one rejected and one unknown-usage | llm=2/4, fallback=1/4, wait=1/4; rejection=1/4; unknown=1/4; V-05 FAIL. Deliberate rule decisions, if any, change none of these denominators. |
| VM-02 | A has input reported [10,null], output [2,3]; charged inputs [10,100], outputs [2,20] | reported input total=null, known input subtotal10, missing input count1; reported output total5; charged totals110/22; unknown share1/2. |
| VM-03 | Latencies [10,20,null,40,50] | known count4, missing1, min10,max50,median30,p95=50. |
| VM-04 | Two created goals; one observed_complete seen in three samples, one retired after failed give | completed1/created2; retired-incomplete1, active-incomplete0; repeated terminal samples do not add completions. |
| VM-05 | No L; no calls; valid deliberate-rule trace | LLM/fallback/wait shares null, counts0; V-05 not applicable to a control, not a passing LLM trial. |
| VM-06 | Three registered pairs; one invalid control, two valid death differences [-1,+1] | pairs_expected3,pairs_used2; median0,min-1,max1,favorable1,unfavorable1,tied0; technical gate FAIL. With no valid pairs all summaries null/counts0. |

These are arithmetic/data-join fixtures, not assertions about simulated causality.
Physical social oracles use the cognition spec's baseline engine-checked examples.

## 6. Separate inspection artifact and UI

Export to a fresh directory after verifying the committed source; never change the
source or ReplayBundle. A bounded shard permits lazy local UI loading; no server,
network, executable HTML or live websocket is needed. Hash raw canonical JSON bytes
without a trailing LF; serialized files use exactly those bytes. All types are closed.

```text
ShardRef {file:string,sha256:Hash}
InspectionDecisionRef {decision_id:string,actor_id:string,tick:N,ordinal:N,shard:ShardRef}
InspectionSampleRef {actor_id:string,tick:N,shard:ShardRef}
P3InspectionIndex {
  inspection_schema_version:"0.1", run_id:string, config_hash:Hash,map_hash:Hash,
  final_tick:N,replay_sha256:Hash,trace_sha256:Hash,registration_sha256:Hash,
  actors:{actor_id:string,identity:ResidentIdentity}[],
  decisions:InspectionDecisionRef[],samples:InspectionSampleRef[]
}
DecisionInspection {
  inspection_schema_version:"0.1", record:DecisionRecordP3,context:ContextRecordP3,
  dispatches:AttemptDispatch[],calls:LLMCallRecordP3[],outcome_event_ids:string[]
}
ResidentInspection {
  inspection_schema_version:"0.1",tick:N,actor_id:string,
  latest_perception_tick:integer>=-1,identity:ResidentIdentity,goals:GoalState,
  recent_experience:ExperienceRecord[],retained_record_count:N,next_sequence:N,
  latest_decision_id:string|null,state_sha256:Hash
}
```

index.json actors sort by actor ID; decisions by tick/actor/ordinal; samples by tick/
actor. There is one sample for each actor at every saved boundary 0..T, dead included,
and one decision shard per committed decision. State samples project that boundary's
pre-ingestion runtime only. recent_experience is the last V-07 retained records in
ascending sequence, not inferred importance; the UI labels it Recent experience.
state_sha256 hashes the full saved ResidentRuntimeStateP3; it is verified at export,
not falsely reconstructible from this smaller sample. latest_decision_id is the last
committed decision of this actor before that saved boundary, null if none.

Decision shards contain exact owner DTOs, joined by run/decision/call IDs and hashes.
outcome_event_ids lists all source WorldEvents whose intent_id occurs in record.plan,
in event order through T; no event is invented for an unstarted intent. Full context,
provider projection, omission manifest, raw response and unknown usage remain separate
inspectable fields. The identity arrays equal retained runtime identities. A context's
perception actor/tick must equal its decision; shard actor/tick must equal index refs.

Files are `decision-<SHA256(UTF8(decision_id))>.json` and
`sample-<tick padded to 10>-<SHA256(UTF8(actor_id))>.json`. Names are validated literally
from typed IDs; no actor string is used as a filesystem component. Index filenames
are unique, flat and relative. V-06 applies separately to each shard; oversize fails
export explicitly, never truncates source/raw text or publishes a misleading partial
index. Hash index after export in the case report. Source artifacts remain available
for headless inspection on refusal; PV-07 is not passed by that refusal. Index cardinality
is bounded by the registered resident count R and T: exactly R*(T+1) sample refs and
at most R*T decision refs. It needs no independently chosen arbitrary row cap.

Export also copies the exact completed trace as trace.json and canonical registration as registration.json. replay_sha256/trace_sha256 hash exact source-file bytes; registration_sha256 hashes the canonical registration object. The viewer accepts index.json, trace.json, registration.json and referenced shards by one multiple-file local input, alongside the already loaded replay.
Validate index, required-file membership, each size/hash/schema and replay/trace/run/
config/map/actor joins before marking the import complete; unknown versions, duplicate
or missing files refuse. Verify a selected shard before display; lazy parsing is allowed.
The replay stays usable with no P3 files. Rendering is escaped plain text, not Markdown
HTML. A separate P3 schema/type generator writes only frontend/src/p3/generated/;
existing replay generated files remain unchanged.

At replay tick k, show the sample for k and label Cognition observed through tick
latest_perception_tick. Never label pre-ingestion state as having already consumed k.
The character panel adds identity values, initial direction, current goal/status,
completion evidence and Recent experience. Existing physical needs/inventory remain
from replay frames. No relationship/emotion values are invented. A decision selector
opens the exact context at its decision tick: full delivered data versus provider
projection, inclusion/omission/eviction, proposed/effective plan, accepted delta,
call chain, error, known/unknown usage, ceiling cost and latency. Unknown is visible,
not 0; intended does not claim action start. Links select source IDs, never grant
resident access. On death, stopped cognitive cursor remains explicit.

UI acceptance: load the same actor/tick from a valid pair; verify scalar and evidence
against source shards; switch to a boundary without decision; test stale cursor/death,
missing/wrong-run shard, HTML-looking speech, zero calls and unknown usage. Gate 2
checks the real rendered panel/debug view before M10, not only schema tests.

## 7. Approved limits (M8)

Each row recommends the stated profile. These are admission/inspection/acceptance
values, not world rules. All call/token/money caps apply independently per live case.
Budget units and accounting semantics belong solely to the decision spec.

| ID | Approved value and unit | Rationale | Measurement / decision evidence |
| --- | --- | --- | --- |
| V-01 | Smoke: 1 seed, T=24 ticks, 1 LLM actor; caps attempts48,input1572864 tokens,output98304 tokens,money5000000 micro-CNY (CNY5) | Exercise one integration before broad spending; money admission may bind before the attempt cap | Actual calls/usage/latency and accepted share in M9 smoke. |
| V-02 | Development: 2 seeds, T=48 ticks, 3 LLM actors; per-case caps attempts288,input9437184 tokens,output589824 tokens,money20000000 micro-CNY (CNY20) | Small tuning set, separate from acceptance | Each case measures reservations, actual usage, fallback and mandatory size; total allocation CNY40. |
| V-03 | Acceptance: 3 fresh seeds, T=144 ticks, 3 LLM actors; per-case caps attempts864,input28311552 tokens,output1769472 tokens,money35000000 micro-CNY (CNY35) | One-day pilot with matched controls, not a seven-day survival claim | Three complete valid pairs, raw per-seed metrics and total allocation CNY105. |
| V-04 | Long fake proof: 1 smoke-seed run, T=1008 ticks, 3 P3 actors; fake caps attempts6048,input198180864 tokens,output12386304 tokens,money0; 0 real provider calls | Exercise seven-day artifact/cursor/overflow recovery without paid model variability | Explicit offline run, source/recorded hashes and sentinel count0. |
| V-05 | Every registered LLM actor in each smoke and acceptance case: llm_accepted_share>=4/5; wait_count0; evidence/privacy violations0; all 3 pairs technically valid | Prevent acceptance of a mostly-rule substitute while keeping behavior quality descriptive | Exact per-actor integer comparison 5*accepted>=4*L, L>0; invalid/missing case fails. |
| V-06 | 2,097,152 canonical UTF-8 bytes per inspection shard | Bound one UI parsing unit while retaining complete request/attempt data | Export sizes; exact limit/limit+1 fixture; report largest shard and actual UI import behavior. |
| V-07 | 8 retained experience records per boundary/actor inspection sample | Compact recent history; full selected recall stays in decision shard | Exact sequence selection and source comparison, count0/8/more-than8 fixtures. |

V-01..03 aggregate ceiling is CNY150: CNY5 + 2*CNY20 + 3*CNY35.
The owner replaced the earlier USD112 authorization on 2026-11-12. No earlier USD
allocation remains spendable. The approved peak uncached price pin gives a maximum
B attempt reservation of 81920 micro-CNY (CNY0.081920). Full attempt maxima would
cost CNY3.932160 / CNY23.592960 / CNY70.778880 per smoke/development/acceptance
case. Thus money can bind before the token/attempt caps; these are independent
ceilings, not a guarantee of completing every maximal-size call. Budget refusal
uses the specified fallback and remains visible in the unchanged V-05 pass lines.
Do not shorten trials, lower pass thresholds, borrow another case's allocation or
replenish a failed run to manufacture acceptance. Report incomplete/failed evidence.
Peak uncached rates are reserved even off-peak or with cache hits. Usage settlement
uses that same conservative pin; discounts do not expand the authorization.
No paid probes outside the six allocations are authorized. Any charged integration
probe consumes its designated case's allocation and attempt count, and remains in
its evidence. P3-02/03/04 use offline fixtures only. An additional or revised trial
needs an explicit new owner disposition; a new registration hash alone grants no
money. The original six approved slots may each be enrolled once across all registration
revisions. The launcher records their single enrollment in the shared authorization
record before creating case authorities, under an exclusive process lock, with total
slot caps <=150000000 micro-CNY. Slots are keyed by the exact purpose/seed pairs in section 3.1, with the
corresponding approved case caps. Persist the slot-to-registration/case-key binding
before creating its empty case authority, under the same enrollment lock. A crash
before that first creation may finish the same initialization only when the durable
binding still says initializing and proves no case authority has been issued; mark
it issued durably before releasing the lock or allowing tick-zero publication.
An existing valid record is finalized/reused, never overwritten. After issued, a
missing authority refuses instead of re-creating capacity. Repeated enrollment for
a consumed slot or a different registration binding refuses. Missing/corrupt pilot
approval storage refuses all live enrollment. Fake/replay modes cannot acquire or
mutate this live approval record.
**[CR-007]** The completed original smoke may have exactly one owner-approved
linked replacement using the same seed, horizon and actor assignment. Its
separate authorization is stored in the same authority, pins the exact
replacement registration and completed original allocation, and preserves all
original records. Its caps and the original settled debits must fit the original
smoke envelope component-wise. The other five allocations and CNY150 ceiling
remain in force. Apply the same exclusive enrollment, crash recovery and
fail-closed issuance rules. The implementation approval alone gives no live
authority. The final hashes and caps require explicit owner dispatch approval.

**[CR-008]** One counter 0.4 smoke may follow the completed original and
CR-007 cases. Their settled debits and the new caps must fit the cumulative
smoke envelope. CR-008 raises only its attempt ceiling to 50. The new case
caps are 34 attempts, 1114112 input tokens, 69275 output tokens and 3000000
micro-CNY. The seed, horizon, resident assignment and per-request limits
remain fixed. Require separate owner approval of the final execution pins.

Prices/model availability and a proven input counter are live preflight requirements;
changed pins never silently authorize extra spend. No live calls were made by this
M8 documentation task.
