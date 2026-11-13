# M9 evidence: one-resident P3 integration

Status: READY_FOR_REVIEW. CR-006 offline integration is recorded below. The
original smoke failed V-05. A replacement trial awaits an allocation disposition
and owner approval. M9 and P3-07 inspection export/UI remain pending.

## Authority and scope

- Owner start instruction: 2026-11-13, exact main baseline
  `522762f81ef83d8ad51a52a9d021e13134810422`.
- Accepted runtime/adapter integration:
  [P3-03-04](P3-03-04-integration.md), code `93f9542`, containing P3-03
  `2867beb` and P3-04 `41d5ecd`. Both are verified ancestors of the baseline.
- [M8 authorization](M8-decisions.md) chooses DeepSeek, local `.env` injection,
  the six once-only pilot slots and an aggregate ceiling of 150000000 micro-CNY.
- This task uses only the smoke slot: seed `1292387875`, 24 ticks, Ella primary
  `llm-v0`; Mia and Ryan primary `rule-based-v0`. All use P3 records. The frozen
  world and rule implementation are unchanged.
- Smoke caps: 48 attempts, 1572864 input tokens, 98304 output tokens and
  5000000 micro-CNY. The two development slots retain 20000000 each; three
  acceptance slots retain 35000000 each. No transfer, refill or extra paid probe.
- Initial enrollment is separate from run/resume. All worktrees resolve the same
  repository-wide live authority. Normal clean continuation reuses its allocation.
  A missing authority is never reconstructed from a checkpoint.

## Nonsecret provider preflight evidence

Official documentation was checked on 2026-11-13 before any model call. The pinned
[expected evidence](../../../backend/tests/fixtures/p3/one_resident/live_preflight.json)
records the model/version, peak prices, adapter and certified counter identities.
A pinned snapshot does not make the hosted model alias immutable; live startup
must recheck current metadata and refuse detected drift or unavailable evidence.

- [Model and pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/):
  `deepseek-flash` identifies `DeepSeek-V4.1-Flash-1017`. Peak uncached rates remain
  2000000 input and 8000000 output micro-CNY per million tokens. Discounts never
  increase authorization.
- [Responses request schema](https://api-docs.deepseek.com/api/create-response/):
  the model, non-thinking setting and JSON Schema format remain supported.
- [Responses compatibility](https://api-docs.deepseek.com/guides/responses_api/):
  stateless requests omit unsupported store/background/history parameters.
- Adapter `deepseek-responses-v0` / `0.4`; counter
  `deepseek-flash1017-byte-upper-bound` / `0.3`; tokenizer SHA-256
  `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b`.
  The P3-04 proof and retained source inventory are preserved.
- The owner supplied an existing local `.env` locator. Only the outer live launcher
  reads it after offline validation; credentials never enter registrations,
  provider requests, receipts, logs or Git.

## Implementation ownership and independent review

Each author has an isolated worktree at the exact baseline:

| Role | Exclusive implementation files |
| --- | --- |
| Integration lead | Allowed sim integration if needed, immutable registrations, live preflight fixture, this sheet and P3-05 handoff |
| Launcher author | scripts/p3_trials.py, test_trial_registration.py, one_resident/launcher_* fixtures |
| Slice author | test_one_resident.py, one_resident/slice_* fixtures |
| Independent Gate 2 | Read-only review and verification in p3-05-gate2; no authored implementation, tests or documentation |

Frozen DTOs, reducers, provider/fallback internals, world rules, legacy serializers,
frontend and dependency pins are outside the editing scope.

An independent early review of exporter commit `2bdf6d6` found one P2 issue:
byte-identical checkpoints from clean zero-tick continuations were independently
matched to the same ancestor directory. Fix
`80985bce74d0bb9f7cbb56273a740e25a10b4c65` resolves the verified nearest-first
continuation chain before assigning frame segments. The nonauthor reviewer
reproduced the original failure and independently closed it: the seven frames of
an unsplit run, repeated-same-boundary continuation and sentinel reexecution export
are byte-identical; all source and allocation file hashes remain unchanged.
The integrated code subsequently passed the pre-live review below; final Gate 2
still requires the completed executor and smoke evidence.

Independent launcher review of `5d6867c` reproduced a second P2 finding:
invalid initial `--ticks=-1` mutated the receipt before the runtime rejected the
length, stranding an unused allocation with no checkpoint. The launcher owner
moved length validation ahead of mutation and made receipt publication follow
the first durable boundary. The same review requested explicit coverage for
crashes before checkpoint zero and after final allocation completion but before
trace/export/receipt completion. The invalid-ticks finding is independently closed at `1aa9296`.
Startup/complete-receipt fixes landed in `b4b4365`; prepared-final publication and
immutable invocation-chain recovery landed in `1329660`. The latter reuses the
existing allocation reconciliation API, catches only its typed closed outcome,
and verifies that generation, caps and reservation identities are unchanged.
Already-complete finalization never opens a case. No new grant or call is allowed.
The nonauthor review below independently passed the final prepared-publication
path and its crash regressions. Live execution still follows the separate
prerequisites and authorization recorded below.

### Independent pre-live code disposition

**PASS** on `eac4d29b3474d337ca312677e609d9e15ddd431a`, by the nonauthor
`p305_gate2` reviewer in its isolated worktree. It independently passed all 35
launcher tests in 499.37 seconds, including real process crashes at startup,
completed and prepared-final publication, and exact original-receipt recovery.
All previously reported code and slice-evidence findings are closed. Its separate
actual initial request measurement is 23082 input tokens, 2048 reserved output
tokens and 62548 micro-CNY. Its complete retained-tape recount and wire equality
also pass. Review worktree and diff checks are clean.

This was a pre-live code disposition, not final M9 or task acceptance. It required
the integrated task/full executor checks, committed 24-tick fake launcher proof,
current metadata/remaining-grant checks and actual smoke evidence. Those results
and the later independent findings/disposition are recorded below.

## Offline integration and tests

The original trial-source integrated task command exited 0:

```sh
uv run --directory backend pytest tests/p3/test_one_resident.py tests/p3/test_trial_registration.py --basetemp ../runs/p305-integrated-task-20261113 --junitxml ../runs/p305-integrated-task-20261113.xml
```

**50 passed in 1482.86 seconds**: 15 slice tests and 35 launcher tests. The
[fixture provenance and VF-01..19 map](../../../backend/tests/fixtures/p3/one_resident/slice_provenance.md)
identifies the integration seams and inherited owner vectors. Actual engine
request/accept/failure/receipt/success feedback now proves that only the exact
resident's successful give completes its give goal. Conflicting resident stores,
unheard claims, malformed replies, retry limits, money one micro-CNY below a
reservation, unknown usage, rule fallback/return, death, active/queued plans,
repeated zero-tick continuation, corrupted checkpoints and external-port replay
sentinels are covered.

Real subprocess crash tests cover invocation/initial-publication/receipt stages,
complete-authority finalization, prepared-final reconciliation and a crashed
resume before ownership moves. They use an explicitly registered two-tick,
zero-money fake case for their focused mechanical oracle. The principal frozen
world and the separately registered full launcher proof both retain all 24 ticks.
The once-only six-slot and BD-18..27 regression vectors remain in the full suite.

Earlier author/reviewer runs exposed a frozen-message test-construction error;
it was corrected with model_copy, not a DTO change. The integrated 50-case result
above supersedes the earlier split-run evidence. Independent review also closed
the added actual-engine VF-17 gap.

The replay exporter checks schemas, retained inputs/log prefixes, lineage,
frame/event cardinality and final trace identity. It does not independently seal
every intermediate world or reexecute the engine during export. A same-prefix,
valid-shape intermediate world edit is outside those structural checks. M9's
stronger proof compares the full source export with the independently recorded-
reexecuted export using raising provider/fallback/authority sentinels.

### Headless goal evidence

The passing lifecycle fixture is retained at
`runs/p305-integrated-task-20261113/test_goal_failure_completion_c0/run`.
These are Ella's exact post-ingestion predecision contexts joined to accepted
changes by decision ID; they do not label a pre-ingestion checkpoint as updated.

| Tick / ordinal | Current goal before decision | Accepted operation | Actual evidence / next plan |
| --- | --- | --- | --- |
| 0 / 0 | none | revise | Propose drink from canteen; create `ella:g000000` |
| 1 / 1 | `ella:g000000`, attempted | continue | Own `ella:p000000:i0` failed with `NO_ITEM`; no completion |
| 2 / 2 | `ella:g000000`, attempted | revise | Own `ella:p000001:i0` also failed; create wait goal `ella:g000001` |
| 3 / 3 | `ella:g000001`, observed_complete | continue | Delivered success for own `ella:p000002:i0`, observed at tick 3 |
| 4 / 4 | `ella:g000001`, observed_complete | abandon | Tick-3 inline evidence retained exactly before explicit abandonment |
| 5 / 5 | none | continue | No completion inferred from text or a pending result |

`test_engine_transfer_feedback_requires_own_completed_give` supplies the stronger
transfer oracle: a real request and acceptance do not transfer the canteen or
complete Ella's give goal; a failed give does not complete it; receiving the
canteen from Ryan changes inventory without completing it; only Ella's exact
successful give to Mia, delivered with its own accepted intent, completes it.
Other participants in this focused engine-protocol fixture are scripted test
intents. The principal island trial retains the actual frozen rule policies.

## Integrated executor checks

The original trial-source full executor command exited 0:

```sh
uv run --directory backend pytest --basetemp ../runs/p305-final-full-20261113 --junitxml ../runs/p305-final-full-20261113.xml
```

**1593 passed, 3 existing opt-in development skips, in 1812.66 seconds**.
The JUnit record is `runs/p305-final-full-20261113.xml`. The complete 50-task
subset also passed in this run. The following final-code checks exited 0:

| Check | Result |
| --- | --- |
| `uv run --directory backend ruff check . ../scripts/p3_trials.py` | PASS |
| `uv run --directory backend ruff format --check . ../scripts/p3_trials.py` | PASS; 159 files |
| `uv run --directory backend mypy src` | PASS; 88 source files |
| `uv run --directory backend lint-imports --no-cache` | PASS; all 8 contracts kept |
| `pnpm --dir frontend lint` | PASS |
| `pnpm --dir frontend typecheck` | PASS |
| `pnpm --dir frontend build` | PASS |
| `uv run --directory backend python ../scripts/gen_types.py` | PASS |
| `git diff --exit-code -- frontend/src/api/generated` | PASS; unchanged |
| Local Markdown file links | PASS; 39 across 5 changed documents, plus upstream handoff anchor |
| `git diff --check` / committed working-tree diff | PASS at this checkpoint |

### Corrected-source final executor checks

The final corrected implementation is
`de5a12ecc117fa0e20a2f7360af217a3d8887002`, byte-identical across backend, scripts,
content and frontend to the isolated frozen full-suite candidate
`ab4a3f6a08ea36880d56851332f19bbe85642f09`. The author and integration lead checked
that equality, and the independent reviewer repeated it. The same uv-created
CPython 3.13.5 virtual environment and unchanged lock file were used; PYTHONPATH
selects the candidate's source before the editable root package. No source was
changed during the suite.

Exact final command, from the isolated candidate's `backend` directory, with
`PYTHONPATH=D:/Codex/.codex/worktrees/p3-05-launcher/Living_World/backend/src`:

```text
D:/Codex/.codex/worktrees/p3-05-integration/Living_World/backend/.venv/Scripts/python.exe -m pytest -q --basetemp D:/Codex/.codex/worktrees/p3-05-launcher/test-temp-backend-offline-final-20261113-01 --junitxml=D:/Codex/.codex/worktrees/p3-05-launcher/Living_World/runs/p3/verification/backend-ab4a3f6.xml
```

Exit 0: **1594 passed, 3 existing skips in 2309.47 seconds (38:29)**. JUnit records
1597 cases, 0 errors, 0 failures, 3 skips and time2309.407 seconds. Its SHA-256 is
`90959b116290a0665fb3f32bf93071e5b073e0a5a8c4969d3cb13d27e4ff4e02`.
The integration lead and independent reviewer each parsed the final file. The
final task subset is **51 PASS: 15 slice + 36 launcher**, no skipped task case.
The added full-horizon regression also passed in the author's and reviewer's
separate three-case runs. This final suite supersedes the original 50/1593 counts
for corrected-source verification; original registered trial artifacts retain
their historical source and execution identities.

The three skips are unchanged opt-in `P2_RULE_RUNS` development checks, not missing
P3-05 cases. Root final Ruff, format, Mypy (88 sources), import contracts (8),
frontend lint/typecheck/build and type generation each exited 0 after integration.
Generated files remain unchanged. Final CLI `--help` also exited 0 without keys.
Original P1/P2 reference evidence remains exact; the final source diff leaves all
world/rule/legacy/contract/frontend/dependency bytes unchanged. Local file-link
validation covers 39 links across the five changed Markdown files, with no broken
links; the upstream handoff anchor is also valid. Diff checks pass.

## Frozen compatibility evidence

The unchanged P2 M7 reference was executed with:

```text
uv run --directory backend python -m living_island run --config ../content/worlds/default.toml --policy rule-based --seed 2600456787 --ticks 1008 --out ../runs/p305-p2-reference-20261113 --export-replay
```

Exit 0: tick 1008, 14351 events, 1305 decisions. Every published P2 reference matches:

| Artifact | SHA-256 |
| --- | --- |
| Events | `427f7f0536c4cedc77b365e821575465d83a60f90d857a73bdf8b45e8fb3574a` |
| Decisions | `67c490e74b963b32fa2393ec92b97d8f412f46c3146a5c20b6bc63a1d5add194` |
| Final world | `5efcf3eab02db3928bc55e4a226327acde2bbfee54abc898f7649d6e4302382c` |
| Replay | `720bccc76cb1c3baff78a74bec7703e76764be777713b43df6e30d297f9d36e8` |

The full-suite P1 fixture also completed its original 1008-tick reference run.
All four published hashes match exactly; its twin/resume/reexecution assertions
are included in the complete executor result above.

| P1 artifact | SHA-256 |
| --- | --- |
| Events | `2d68a49b495e46a150322711bc8fbb38779ad947c4345ec0f11c89bd08d03287` |
| Decisions | `ee614c057b02d65b67ee6ff5336e17434ab4aeb6026c710f853d7d599c36e4bd` |
| Final world | `113483069d74936a3fa5ecf0f719405dc7499698fc851cdc4b992a84e25357ed` |
| Replay | `8e26d853b6bf324fa4a375f0edfca526c09754b78d7eaee9b96c615464dbfb83` |

No reference, scenario, world, rule-policy or generated frontend source is edited.

## Registered full offline launcher proof

Implementation: `eac4d29b3474d337ca312677e609d9e15ddd431a`.
Registration commit: `c3364c4`; canonical registration SHA-256:
`6831584ac724912640b518f7302fa7326efe14e466139a30c198838be8327e85`.
Case: `p3-05-fake-r1.s1292387875`, full 24 ticks, isolated fake authority
`runs/p305-fake-authority-20261113`, zero money. Allocation key:
`00f7062baaa1c8f94ecd6faf659412419ddebf52ecf06a8d6e4a246bb97c4a1c`.

No-dispatch validation, explicit fake initialization and once-only enrollment
have each exited 0. The following exact run is recorded before execution:

```sh
uv run --directory backend python ../scripts/p3_trials.py run --registration ../content/experiments/p3/development/p3-05-fake-r1.json --case p3-05-fake-r1.s1292387875 --out ../runs/p3/p3-05-fake-r1/first --fake-authority ../runs/p305-fake-authority-20261113 --tape tests/fixtures/p3/one_resident/slice_smoke_tape.json
```

The full run exited 0 at tick 24. The complete receipt records execution commit
`f895d7609de371ffe64e41298a0a92d879e40027`; receipt SHA-256 is
`6bbd50e54bf16d4d402e5a4e6b92dd50f19cdb2962d19628f98b677c054645bf`.
Its allocation is complete, with exactly the checkpoint's allocation entries and
matching head/hash. Totals: 447 events, 67 decisions, 24/24 accepted Ella model
choices, 43 deliberate rule choices, zero fallback/wait substitutions, 24 fake
attempts, 240 input units, 480 output units, zero unknown usage and zero micro-CNY.
These are explicitly fake units and responses, not production usage or invoices.

Recorded replay also exited 0:

```sh
uv run --directory backend python ../scripts/p3_trials.py replay --source-run ../runs/p3/p3-05-fake-r1/first --out ../runs/p3/p3-05-fake-r1/recorded
```

All five logs, final checkpoint, trace and replay.json are byte-identical. The
25 frames cover ticks 0..24 and their event list equals events.jsonl. Hashes of
all 43 source files and all five isolated-authority files are unchanged. Raising
provider, fallback and authority sentinels were untouched. Audit details are
retained locally in `runs/p305-registered-fake-audit.json`.

| Artifact | SHA-256 |
| --- | --- |
| Events | `5e7bff239a44c91e8a91309cc6a126975b4591caa237db4d6ae9a44c58adb971` |
| Decisions | `959ac11d832932ec9665eb833e0a9c15670b96884578564ee4745fb0bd523af3` |
| Contexts | `070df33e1bb29599add7ddaba33093e18aac53f2a2ba0e30804c2bcf44d37980` |
| Dispatches | `265b34f0675e0982b2bc9c97b599fbc4fc794842d6e0d626fd732fc6b2ece662` |
| Calls | `ece18981ac32439862e7fc9f37206a850c313935663eb91ed6651fa0ca0f6804` |
| Final checkpoint | `6332fdd74ee5df9fabfe614bc3e23f0a936a70c0cc789873f6783ffe0fa394f8` |
| Trace | `944931537eea6d7871c57d79e4a768d8d03be9dcfe997d052cb1a59645d067e3` |
| Replay | `952961d0a119d58b93790cdf59bdcaa55bc2b43bde381bc064ead8465061d193` |

This fake authority does not enroll any M8 live slot.

## Registered live command and results

The authorized live prefix completed at tick 8, but its provider requests all
failed. The original planned live continuation is cancelled because the retained
schema is rejected by the endpoint. All offline executor checks passed before
this trial. This case cannot meet the V-05 acceptance threshold. Its immutable registration is
[development/p3-smoke-r1.json](../../../content/experiments/p3/development/p3-smoke-r1.json),
canonical/file SHA-256
`dcb337f07601f6c1b1abe9fd0a61f410a713a6caf26bcc7e4e7cf0d25e65ca5f`.
It pins reviewed implementation `eac4d29b3474d337ca312677e609d9e15ddd431a`,
94 implementation files and 13 input files. Case `p3-smoke-r1.s1292387875`
retains the approved 24-tick horizon and 5000000 micro-CNY cap.

- Effective world config: `03ae94b16856119b34286292b3e7b276bece3f887aeb9b7fd49cfbc05f6da0cc`.
- Frozen map: `007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c`.
- M6 content commit: `7c13d78ffd7d89006f6008c8a09f37ae97c253db`.
- Canonical live authority: `E:/桌面/Living_World/.git/living-island-p3/authority`.
- Six-slot approval: sibling `pilot-approval.json`; repository-wide initialization
  marker: `.git/living-island-p3-enrollment.json`. All three were absent at the
  pre-initialization check; none is reconstructed from run files.
- The first request's independently checked bound is 23082 input tokens plus
  2048 output tokens, reserving 62548 micro-CNY at the pinned peak prices.
- Current official model/version, Responses capabilities and prices were checked
  again before registration. The launcher rechecks public metadata, counter and
  remaining authority before reading the owner-provided local credential.

The following exact invocation sequence is recorded before any live dispatch.
After committing and validating registration, initialize the approved pilot once
and enroll only this smoke slot. Pause at tick 8 and continue the same case to
24, demonstrating normal authorized continuation without another grant or
approval. Output directories are fresh and remain under this registration.

```sh
uv run --directory backend python ../scripts/p3_trials.py validate --registration ../content/experiments/p3/development/p3-smoke-r1.json
uv run --directory backend python ../scripts/p3_trials.py initialize --live
uv run --directory backend python ../scripts/p3_trials.py enroll --registration ../content/experiments/p3/development/p3-smoke-r1.json
uv run --directory backend python ../scripts/p3_trials.py run --registration ../content/experiments/p3/development/p3-smoke-r1.json --case p3-smoke-r1.s1292387875 --out ../runs/p3/p3-smoke-r1/first --live --ticks 8 --dotenv "E:/桌面/Living_World/.env"
# NOT_RUN after HTTP_400; the no-call replacement is recorded below.
# uv run --directory backend python ../scripts/p3_trials.py resume --registration ../content/experiments/p3/development/p3-smoke-r1.json --case p3-smoke-r1.s1292387875 --checkpoint ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json --out ../runs/p3/p3-smoke-r1/continued --live --dotenv "E:/桌面/Living_World/.env"
uv run --directory backend python ../scripts/p3_trials.py replay --source-run ../runs/p3/p3-smoke-r1/continued --ancestor ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json --out ../runs/p3/p3-smoke-r1/recorded
```

Registration commit: `761d68d0d18773049ac34b93bc7639e66af8f6a4`.
No-dispatch validation, once-only live initialization and smoke enrollment each
exited 0. The persisted slot is issued to allocation
`239430e613050272e0a06e85f0660475ae1165c183ee0a78de4eb2fda842bdf1`.
The actual pre-dispatch remaining allowance is 48 attempts, 1572864 input tokens,
98304 output tokens and 5000000 micro-CNY. The other five bindings remain null;
the six caps sum to 150000000 micro-CNY. The retained check is
`runs/p305-live-enrollment-20261113.json`. Zero paid calls have occurred at this
pre-dispatch commit. The launcher will refresh metadata and remaining capacity
again before credential injection.

The report separates reported usage, conservative ledger charges, unknown usage
and provider invoice evidence. It never labels a conservative ceiling as a
confirmed invoice. Deliberate rule choices are excluded from the LLM acceptance
denominator; fallback and wait shares remain visible.

### Upstream P305-U3: live schema rejection and offline continuation

The first invocation exited 0 at its registered pause boundary, tick 8. Its
14 attempts all returned HTTP_400 / PROVIDER_REJECTED with missing usage. The
retained structured error identifies `^[^\uD800-\uDFFF]*$` as an invalid regex
in the JSON Schema. No successful provider proposal was received: all seven Ella decisions in the
live prefix used the typed rule fallback. The exact response/request remains in the ignored run artifacts; no credential is retained.

The checkpoint ledger charges 909760 micro-CNY conservatively, not a confirmed
invoice. No missing usage is counted as zero. P305-U3 was returned to the P3-04 adapter owner. Its investigation and the
independent reviewer locate the pattern in frozen `agents/p3/prompts.py:101`
(P3-02). Current provider rules require the schema to be sent unchanged, so a
shared schema disposition is now with the lead/foundation owner. A local Python
regex compilation succeeds; the evidence specifically proves incompatibility
with the hosted schema validator, not universal invalidity. The reviewer also
reproduced the retained HTTP_400 as a typed provider error through the real
adapter offline, with null usage and zero external calls. Frozen
contracts and the already-enrolled registration are not modified. No new slot,
refill or paid retry outside this failed case is authorized or performed.

The originally planned live `resume` above WILL NOT RUN. The following replacement
is recorded before execution: finish the registered horizon using the explicit
no-provider offline recovery mode, then replay that complete failure lineage.
This preserves the failed live prefix and demonstrates recovery; it cannot turn
the failed live trial into a V-05 pass or an M9 acceptance result.

```sh
uv run --directory backend python ../scripts/p3_trials.py resume --registration ../content/experiments/p3/development/p3-smoke-r1.json --case p3-smoke-r1.s1292387875 --checkpoint ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json --out ../runs/p3/p3-smoke-r1/continued --offline-recovery
uv run --directory backend python ../scripts/p3_trials.py replay --source-run ../runs/p3/p3-smoke-r1/continued --ancestor ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json --out ../runs/p3/p3-smoke-r1/recorded
```

The source reached tick 24 with 66 committed decisions and 595 events: Ella
has 23 primary-LLM decisions, all effective rule fallback (seven provider failures,
then 16 `RECOVERY_OFFLINE` decisions); Mia has 21 and Ryan 22 deliberate rule
choices. The complete lineage has 0/23 LLM acceptance and 0/23 wait substitutions.
The live prefix alone is 0/7 accepted. The continuation added zero attempts,
charges or unknown-usage entries. No model-authored goal was created; its 23
`continue` deltas are fallback preservation, not demonstrated model cognition.
This is failed-smoke/recovery evidence, distinct from the passing headless goal
fixture and the passing registered fake case.

P3-04 published the non-production U3 evidence package at
`ec7524cd1f5716f67a084090a2e4829cb9088c5b` (substantive regression
`1279f4be03ff2bade7e41e9a9a16e5a2430db7b3`), independently reviewed for evidence
only. It preserves the actual HTTP error and confirms the unchanged request/counter.
It does not fix or authorize a changed schema, and is not consumed as a new live
implementation. The lead confirmed that P3-02 owns the coordinated version change.

### Independent late finding: offline completion metadata

The nonauthor reviewer reproduced a P3-05 launcher defect while the original
registered offline continuation was still running. At the final horizon,
`isinstance(provider, TapeProvider)` introspects the strict no-external-access
provider's `__class__` attribute and raises its sentinel. This is a metadata
completion error, not a new API call. It occurs after trace/allocation completion
and before final receipt/export publication.

The original execution retained its registered source. The launcher author
prepared a narrow isolated fix and full-horizon CLI regression without weakening
the sentinel. The completion error occurred as predicted; its receipt/history
was preserved and the already-tested metadata-only finalizer was used under the
original source, without a new grant, generation, call or settlement:

```sh
uv run --directory backend python ../scripts/p3_trials.py finalize --registration ../content/experiments/p3/development/p3-smoke-r1.json --case p3-smoke-r1.s1292387875 --ancestor ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json
```

Replay immutability was snapshotted after this legitimate finalization, retaining
the failed invocation history. The source fix was independently reviewed and
integrated only after original artifact recovery/replay completed; its final
executor result is recorded separately. This local fix does not repair the
separately failed hosted schema or authorize another smoke.

### Finalized recovery and recorded replay audit

The original offline continuation reached tick 24, published its final trace and
completed allocation generation 2, then reproduced the independently predicted
metadata error with CLI exit 1. The metadata-only `finalize` command above exited
0 with zero dispatches and zero new allocations. All 11 authority file hashes
match the preserved pre-finalization snapshot. The exact failed receipt remains
in both `lineage/.../failure.json` and `finalizations/.../previous.json`; it was
not erased by publishing the completed receipt.

The completed receipt retains original offline execution commit
`61d57dff18945398fa2ad5f16bfd4b0ce471a3c1` and its exact invocation. Receipt SHA-256:
`8da11781d524b4056cb045b8f3c795029ea2d5cc6e89681b6635fb0f2058a025`.
The original live invocation was executed at pre-dispatch commit
`1658d5947dd7138579dc56136f85fb1e246d2426`; finalization did not relabel it as a
successful hosted-model trial.

Recorded reexecution then exited 0, tick 24, external calls 0. All five verified
full-lineage logs, final checkpoint, trace and replay.json are byte-identical.
The replay has exactly 25 frames and 595 matching events. All 97 source, receipt,
approval/authority and enrollment-marker file hashes are unchanged across replay.
Provider, fallback and authority sentinels remain strict and untouched.

Read-only audit records (ignored local artifacts):
`runs/p305-before-finalize.json`, `runs/p305-live-before-replay.json`, and
`runs/p305-live-audit.json`. Source segments are `runs/p3/p3-smoke-r1/first` and
`continued`; reexecution segments are `recorded/segment-0000` and `segment-0001`.
These artifact-integrity checks PASS for the retained failed/recovered case;
the mandatory hosted-model acceptance gate remains FAIL.

| Measurement | Observed value |
| --- | --- |
| Attempts / outcome | 14 / all provider_error, HTTP_400 |
| Accepted / fallback / wait, full Ella lineage | 0/23 / 23/23 / 0/23 |
| Live-prefix accepted / fallback / wait | 0/7 / 7/7 / 0/7 |
| Retry decisions | 7/23 full lineage; 7/7 live prefix |
| Parse/plan/delta rejections | 0/14; provider errors are reported separately |
| Unknown usage | 14/14; input and output totals null; known subtotals 0, missing counts 14 each |
| Charged input / output | 340192 / 28672 tokens; conservative reservations for unknown usage |
| Ledger cost ceiling | 909760 micro-CNY; actual invoice unknown |
| Latency | 14 known / 0 missing; min317, median342, p95=405, max405 ms |
| Maximum input reserve / request bytes / response bytes | 26254 tokens / 56724 / 219 |
| Mandatory / projected context high water | 8054 / 24145 canonical UTF-8 bytes |
| Retained experience high water, all residents | 77 records / 49849 canonical record-array bytes |
| Retrieved/projected experience selections | 343/343; 551 per-manifest retrieval-limit omissions; maximum recall16 |
| Eviction / mandatory oversize / input-limit refusal | 0 / 0 / 0 |
| Model-authored goals / evidenced completions | 0 / 0; no completion share inferred from zero created goals |

The smoke slot is complete and cannot reuse its uncharged 4090240 micro-CNY.
The other five approved slots remain unbound (aggregate caps 145000000 micro-CNY),
within the original 150000000 ceiling. No unused smoke balance is transferred.

| Full-lineage artifact | SHA-256 |
| --- | --- |
| Contexts | `4b35dfe53d3ab1781786586b7d379e7115a6e6ef54aafe91105b85fb5c674e25` |
| Decisions | `7e0b8ceaf9a0494aed6ce0c385c8fbcbf36776131827bf6ca95dee53a4cebc21` |
| Events | `8dd1f67b8040c3cb267a753f3e22da405cce0742edd057d28e7dcfe37f1268bc` |
| Calls | `d36675c5a4b6cdc5badef54b82dbd652cb942c874e5988a592d1983f245507a1` |
| Dispatches | `eb890a5d3743bb942d79f4540647ef0975c80d02be9cec6a71d22b8a476c7342` |
| Final checkpoint | `961ae2f0b0c5a1c258747a1018bd1fc0ad4f85642e1ebf6ef68444f31fb5da14` |
| Trace | `94bc7b412b04fb1ea2e7588615923a4e3065b72e878aa8d73180e6c6641a77af` |
| Replay | `13754f712693cfea74ebe519bbee8e102795a7269356c9c8e3fb922524ad83b2` |

### Reviewed launcher correction after preserving the original trial

The independent author fixed only the final type guard and added a full-horizon
CLI regression in `ab4a3f6a08ea36880d56851332f19bbe85642f09`, integrated as
`de5a12ecc117fa0e20a2f7360af217a3d8887002`. The guard inspects the concrete Python
type without reading any provider-instance attribute. The strict sentinel and
closed-tape consumption checks are preserved. Author targeted checks: 3 PASS;
independent reviewer: 3 PASS in 54.40 seconds, closing this local P2 finding.
The regression checks exit 0, complete receipt/trace/export, no provider/network/
credential accesses, unchanged charges/entries/caps and unchanged source artifacts.

All backend, scripts, content and frontend bytes at the integrated candidate
match the independently tested author candidate. Its full backend suite passed
1594/3 skips, including 51 task cases; final integrated Ruff/format/Mypy/import/
frontend/type-generation checks also pass. Exact commands and proof are above.
The original worktree remained frozen until recovery/replay completed; the final
suite's isolated candidate worktree remains frozen throughout. The implementation and input pins inside both historical registrations
remain unchanged. For original run/validation/finalization reproduction, use the
source-compatible commit `0fd8a0085d9e06f3f3979a1a400c2e78158fcaa5`, which includes
the committed registrations. The corrected launcher must refuse to run an old
registration with changed implementation bytes; this is intentional pin enforcement,
not a license to change an enrolled registration or retry the live case.

## Upstream follow-up P305-U1

Owner: P3-03 persistence / P3-01 evaluation contract. This does not block the
single-case smoke, but must be resolved before a multi-seed development or
acceptance registration in P3-07. The launcher author and independent reviewer
confirmed that TrialRegistration has one `world_config_sha256`, while
`persistence.p3.validate_inputs` compares it to the effective config hash including
`meta.seed`. The two approved development seeds therefore have different hashes;
one registration cannot satisfy both. There is no implemented base-config hash
interpretation that resolves this conflict. No frozen file is changed in P3-05.
The finding is returned to the upstream owner for an explicit contract disposition.

## Upstream follow-up P305-U2: resolved for the retained smoke inputs

Owner: P3-04 provider token counter. The baseline certified byte upper bound
correctly refused the actual first smoke request at 45161 versus B-05's 32768,
with zero calls. An initial ASCII-only refinement admitted that request but left
22 of the 24 retained user messages outside its non-ASCII allowance. P3-05
returned both reproductions to the owning task without changing frozen limits,
required context, prompts or provider internals.

The owner delivered the proven ASCII/basic-Han refinement, its source certificate,
24-request regression and independent Gate 2 in
`e5095a585b5f18289653be437074debf7a2ac199`. See the
[P3-04 follow-up handoff](P3-04.md#final-p305-u2-follow-up-handoff-2026-11-13)
and [counter proof](../../../backend/tests/fixtures/p3/provider/README.md).
The approved upstream range is consumed as a dependency correction:

| Upstream commit | Integrated task commit | Purpose |
| --- | --- | --- |
| `1ac2a95340264c12451a9b12ff26f6a41df3d4aa` | `4e58866` | Certified ASCII BPE prefix and explicit response-model mismatch refusal |
| `035fbab63b45daa0ecf463acf542d2921556d528` | `8475e57` | Certified basic-Han partitions and all 24 retained requests |
| `52ab6548e31d41876009402990a5669604ac6906` | `8914b60` | Literal-marker proof clarification |
| `e5095a585b5f18289653be437074debf7a2ac199` | `2c30754` | Final upstream evidence and seven-field handoff |

Only the upstream task-card header needed merge resolution; both the accepted
2026-11-12 baseline and the new follow-up status/references are retained. Provider
code, tests and proof fixtures match the published upstream delivery byte-for-byte.
No shared DTO, dependency package, world, rule or legacy serializer changed.

The integration lead independently loaded the exact pinned pure counter and
checked all 24 retained request/wire pairs: bounds 23082 through 27561, all within
32768, with identical wire bytes and zero external calls. Only the counter identity
metadata was bound to the production counter for this probe; no message or wire
content was changed. Final provider source SHA-256:
`8081323909dc0eb1539481e2cdecb4185d882bfa9f9e834b0a023e1c01fa467a`.
Expected live pins are adapter `deepseek-responses-v0/0.4` and counter
`deepseek-flash1017-byte-upper-bound/0.3`; tokenizer/model identity is unchanged.

Upstream evidence: 195 adapter tests, 374 independent P3 tests, full executor
1337 passed/3 existing skips, all plan checks and all eight P1/P2 reference hashes.
These are explicitly upstream results; P3-05's integrated checks are recorded
separately. The counter remains conservative for other Unicode and may refuse
other long inputs. An alias echo does not attest hosted weights, so live startup
still checks current official version/pricing evidence. No paid probe was used.

## Final independent Gate 2 record

Reviewer: `p305_gate2`, a nonauthor working read-only in its isolated worktree.
Reviewed evidence/handoff commit:
`8d67d31b2742c0f08366c70ffd98d47bf430371b`.
Corrected implementation: `de5a12ecc117fa0e20a2f7360af217a3d8887002`, identical
to tested candidate `ab4a3f6a08ea36880d56851332f19bbe85642f09`.
Disposition, 2026-11-13: **NEEDS_UPSTREAM_REWORK**. This is not an overall PASS,
full task acceptance or M9 acceptance.

One **P1 blocker, P305-U3**, remains: the hosted validator rejects the schema
pattern emitted by frozen `agents/p3/prompts.py:101`. All 14 live requests returned
HTTP_400, so Ella's live acceptance is 0/7 and the complete recovered lineage is
0/23 (`5*0 < 4*23`). The owner-coordinated schema repair and explicit replacement-
trial/allocation disposition are required before any new paid trial.

The reviewer found no remaining P3-05-owned implementation blocker. It independently
confirmed the corrected source equality; final JUnit1594 PASS/3 existing skips and
all 51 task cases PASS; complete five-log/checkpoint/trace/replay equality; 25 frames
and 595 events; all 97 pre-replay and 11 pre-finalization authority hashes unchanged;
and preservation of the original failure receipt in both history locations.
All earlier owned exporter, launcher and slice findings are closed. Final documents
were checked for truthful separation of historical trial source, corrected source,
passing offline checks and failed live acceptance. Review used no credential or
external calls and authored no implementation, tests or repository documentation.

Keep task status **READY_FOR_REVIEW** for owner/upstream disposition. The final
publication commit adds this review record only; it does not change the reviewed
implementation, registrations, artifacts, limits or acceptance threshold.

## M9 disposition

The mandatory live V-05 gate failed. M9 is not ready for acceptance. Independent
review of the retained offline failure lineage passed, and the owned completion
finding is closed. The corrected-source full suite and all executor checks pass.
Independent Gate 2's final acceptance disposition is NEEDS_UPSTREAM_REWORK because
of U3, as recorded above. A future
smoke needs a centrally approved schema correction and explicit replacement-trial
disposition; the consumed slot cannot be reset or silently reused. No main merge
or P3-06 start is authorized by this task.

## CR-006 integration and replacement smoke proposal (2026-11-13)

The continuation branch `task/P3-05-u3-finish` starts at `f84aaae`. It applies
the complete P3-02 U3 delivery `2b198ad` (including the allocation and
persistence test fixture pins), P3-04's U3-only verification changes through
`8102eb3`, and central disposition `cd5ca0d`. The P3-04 U2 production adapter
and counter were already in the base. Source and tests for the three imported
deliveries were checked against the relevant upstream Git blobs. The only
production changes are the approved P3-02 action contract and version pins.

The first independent review of `60fe91e` reproduced a failing full-horizon slice
test using the historical 0.1 tape with the new adapter. Correction
`0ffa1f87a4d85511909c389ccf151e5f1407d79b` gives the test a separate 0.2 tape
and exercises explicit refusal of the original tape by the 0.2 adapter. The
new tape and test do not replace either historical registration. See the
[fixture provenance](../../../backend/tests/fixtures/p3/one_resident/slice_provenance.md).

### Executor results for the corrected candidate

The 0.2 candidate passed 1621 tests with three existing opt-in skips in six
disjoint pytest selections. All 51 P3-05 task cases passed. Ruff, Mypy, all
eight import contracts, frontend lint/typecheck/build and unchanged generated
types passed. Fresh P1 and P2 runs matched all eight published hashes. See
the [continuation handoff](P3-05.md#handoff-cr-006-continuation-2026-11-13) for
the commands and report paths.

The separate 0.2 fake run completed tick 24, with Ella's 24/24 scripted
decisions accepted, zero monetary debit and zero external calls. The
recorded reexecution matched the five logs, final checkpoint and trace
byte-for-byte. The trace SHA-256 is
`442b57dec5a1d6ae376e5caf97e8ce13ee90d8cbcc0b695ff02e7fb05c2163db`.
Hosted acceptance and costs for the proposed replacement are pending.

### Independent Gate 2 for the offline integration

Nonauthor reviewer `p305_gate2` passed the corrected candidate `0ffa1f8` in an
independent detached snapshot. The reviewer executed the 24-step schema 0.2
slice through its full horizon and reexecuted it with raising external-access
sentinels. All five logs, final checkpoint and trace matched byte-for-byte.
The leading six cases in the reviewer's corrected task run passed before the
duplicate broad run was stopped. This is focused independent evidence.

The reviewer also ran 452 focused schema/provider/allocation/persistence/
cognition/recovery/reexecution/transaction cases on `60fe91e`, all passing
in 240.78 seconds. Their source and test blobs match the corrected candidate.
The JUnit file is `p305-u3-gate2-focused.xml` in local system temp, SHA-256
`2e528bbcc795d365d4210940e1507e9f65f8e3821285dcd38e4d96e47598f923`.
Six launcher vectors in the initial review passed, including once-only
enrollment, crash recovery, and no-call full-horizon offline recovery.
The initial slice's known stale-tape failure is closed by the corrected run.

The independent reviewer validated both old registrations under their
pinned-compatible `0fd8a00` source and reexecuted the original failed live
lineage to tick 24 with zero external calls. It verified all 13 recorded
output digests, 97 pre-replay and 11 pre-finalization authority digests, and
both original failure receipt copies. The pilot approval and allocation
SHA-256 values are, respectively,
`a2cc35219335e3d3f8908257c4c0c1b3a912da912c3e8044bb13ed20f31713fd` and
`1b11dbc07b5a6494842931a02312b0d680b8af76d773b58b2c91f14c9684cefb`.
The reviewer independently reconstructed the draft registration hash, first
request reservation and budget calculation below. This disposition covers
offline integration. The original live V-05 remains FAIL.

### Proposed registration and code pins

| Pin | Proposed value |
| --- | --- |
| Reviewed offline implementation candidate | `0ffa1f87a4d85511909c389ccf151e5f1407d79b` |
| Draft registration schema / revision / ID | `0.1` / `1` / `p3-smoke-u3-r1` |
| Draft registration SHA-256 | `5177a9a069d5e06a3f2d0e4622a6c6be73b5d5494cea820c19189ee01f1c6bd1` |
| Case and horizon | `p3-smoke-u3-r1.s1292387875`, seed 1292387875, 24 ticks |
| Primary policies | Ella `llm-v0`; Mia and Ryan `rule-based-v0` |
| World source | `7c13d78ffd7d89006f6008c8a09f37ae97c253db` |
| World config / map SHA-256 | `03ae94b16856119b34286292b3e7b276bece3f887aeb9b7fd49cfbc05f6da0cc` / `007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c` |
| Action contract | `p3-actions/0.2`, SHA-256 `bf8afebe7d4d494def9cdc8c3b7a9514e868b1f82ae9f1ad8de968d38c0aaa14` |
| Prompt and context | `p3-resident/0.1`, SHA-256 `7122e5bb50194db0251afe18d4b194e0d15e63dc9699ffa079545ed341eed9a1`, `p3-context-v0` |
| Model, adapter and counter | `deepseek-flash` / `DeepSeek-V4.1-Flash-1017`; `deepseek-responses-v0/0.4`; `deepseek-flash1017-byte-upper-bound/0.3` |

The draft hash is the canonical `TrialRegistration` built by
`build_registration(repository, "0ffa1f87a4d85511909c389ccf151e5f1407d79b",
purpose="smoke", registration_id="p3-smoke-u3-r1")` with both the single case
and aggregate caps set to the proposed row below before validation and canonical
serialization. The draft conforms to the DTO. The current launcher validates
against the original M8 caps and cannot enroll the draft. The approved authority
implementation will change source pins, so its final immutable registration
bytes, exact code SHA and hash require a new review and explicit dispatch
approval. No live registration was created or enrolled in this continuation.

The credential-free initial preflight measured 24106 reserved input tokens, 2048
reserved output tokens and 64596 micro-CNY. Public model/version, peak pricing
and Responses metadata were checked against the registered assumptions. The
peak uncached rates are CNY2 input and CNY8 output per million tokens. Refresh
metadata at live startup under the final pins. Hosted schema acceptance remains
untested. [DeepSeek model and pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
and [Responses API](https://api-docs.deepseek.com/api/create-response/).

### Budget and upstream disposition

| Amount | Attempts | Input tokens | Output tokens | micro-CNY |
| --- | ---: | ---: | ---: | ---: |
| Original issued smoke caps | 48 | 1572864 | 98304 | 5000000 |
| Original settled debits (all usage unknown) | 14 | 340192 | 28672 | 909760 |
| Arithmetic balance of original smoke envelope | 34 | 1232672 | 69632 | 4090240 |
| Proposed replacement hard caps | 34 | 1114112 | 69632 | 2785280 |
| Cumulative smoke exposure at replacement cap | 48 | 1454304 | 98304 | 3695040 |

The original allocation is complete at generation 2. The original provider
invoice remains unknown. Under the pinned peak prices a maximal attempt costs
`32768 * 2 + 2048 * 8 = 81920` micro-CNY. The proposed money cap covers 34 such
attempts. A case with 24 first attempts has ten additional attempts available.
The cap controls admission and reservations. If provider-reported usage causes an
overrun, record the full debit, stop live dispatch, and fail technical validity.
A budget refusal or excess fallback can still fail V-05.

The total ceiling remains 150000000 micro-CNY (CNY150). The only issued
allocation is the old smoke. The other five bindings are null and their caps
sum to 145000000 micro-CNY. The current headroom after booked spend is
149090240 micro-CNY (CNY149.09024). After the proposed maximum additional
spend, headroom would be 146304960 micro-CNY (CNY146.30496), including the
145000000 micro-CNY for the other five slots. The remaining 1304960 micro-CNY
within the smoke envelope would remain unused. The current arithmetic
balance carries no dispatch authority.

Current M8 and the 0.1 authority fix six once-only bindings. The original
smoke binding is issued and complete. A different registration for its purpose
and seed fails closed. Request an explicit owner disposition for the evaluation
and persistence owners to implement one linked, once-only replacement within
the existing smoke envelope. Preserve the original approval, registration,
allocation, logs and failure receipts byte-for-byte. The replacement record
should bind the immutable old allocation and settled debits, and the new
registration and hard caps in the same repository-wide authority. Review the
effective combined caps, duplicate/concurrent refusal and crash recovery before
final registration. The alternatives of resetting the old slot or creating an
independent pilot would invalidate the original accounting constraints.
This change requires an upstream change request and review. CR-006's offline
approval does not authorize it.

### Conditional trial and reporting

After upstream review and explicit owner approval of the final pins and hard
caps, validate and enroll once. Use new output and receipt paths for the
replacement case. Run the same 24-tick registration with an initial
`run --ticks 1` pause, then inspect Ella's first decision and settled ledger
before any live continuation. The pinned transaction policy permits up to two
attempts in that decision. If the schema rejection recurs or admission/authority
fails, stop live dispatch, preserve the partial evidence and use the recorded
offline recovery path when possible. Upon successful preflight and first
decision, resume the same allocation to the registered horizon, with zero
additional paid probe or grant. Reexecute retained inputs
with raising provider, fallback and allocation sentinels and verify all five
logs, final checkpoint, trace and replay across the lineage.

Report Ella's accepted/L, fallback/L, wait/L, rejected/dispatched,
unknown-usage/dispatched, reported usage, conservative ledger charges, invoice
if known, and technical validity. V-05 requires `L > 0` and
`5 * accepted >= 4 * L`, zero wait substitutions and zero evidence/privacy
violations. Mia and Ryan's deliberate rule decisions are excluded. Preserve the
original failure and label the replacement result independently. M9 disposition
belongs to the owner.

## CR-007 replacement approval candidate (2026-11-13)

The owner approved the implementation and independent offline review of the
linked authorization. The [CR-007 task card](P305-R1.md) records its scope and
verification. The separate `task/P305-R1-replacement-authority` branch pins the
reviewed implementation `4a66f9b9054546b79bd42d84d103485af373db51`.

The proposed immutable
[replacement registration](../../../content/experiments/p3/development/p3-smoke-u3-r1.json)
is schema 0.1, revision 1, case `p3-smoke-u3-r1.s1292387875`, and has canonical
SHA-256 `7e63f9d2fe41330f262e409bf942186aedbbfd5d829d65e54c5e580bb161081e`.
This registration supersedes the earlier budget draft for owner approval.
It binds 94 implementation pins, 13 input pins, the same 24-tick world and
Ella-only LLM assignment, and the reviewed 0.2 action contract. The allocation
key will be `91170f39b60ba3979d53a27fe8bd2fe95dc8142fbcf9d3e91984948fc6a46b78`
if issued. Pure preflight measures 24106 input tokens, 2048 output tokens and
64596 micro-CNY for the initial reservation.

The hard admission caps remain 34 attempts, 1114112 input tokens, 69632
output tokens and 2785280 micro-CNY. The original completed smoke retains
909760 micro-CNY in conservative debits. The maximum combined admission
exposure is 3695040 micro-CNY across 48 attempts. The total ceiling remains
150000000 micro-CNY, with 149090240 currently unspent, or 146304960 after
the proposed replacement cap. The original invoice and replacement metrics
are pending. Original V-05 remains FAIL.

After explicit approval of these pins and caps, use `authorize-replacement`
with the exact registration hash above and original allocation SHA-256
`1b11dbc07b5a6494842931a02312b0d680b8af76d773b58b2c91f14c9684cefb`.
The command records the link and its independent guard beside the pilot
approval. Then enroll the exact registration, run with the existing
credential injection and fresh public preflight, and pause at tick 1.
Inspect the first decision and both possible attempt outcomes before any
live continuation. Use fresh replacement receipt and output paths. The
original authority, registration, failure and replay bytes remain retained.

No real authorization, enrollment, credential read or API call was performed
in CR-007 implementation. The proposed replacement remains pending owner
approval. M9 remains pending owner disposition.
