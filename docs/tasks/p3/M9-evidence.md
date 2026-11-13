# M9 evidence: one-resident P3 integration

Status: IN_PROGRESS. This sheet prepares owner review; it does not declare M9
accepted. P3-07 inspection export/UI remains pending and is not claimed as PV-07 PASS.

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

This is a code disposition, not final M9 or task acceptance. The review explicitly
requires the integrated task/full executor checks, committed 24-tick fake launcher
proof, current metadata/remaining-grant checks and actual smoke evidence. Final
independent Gate 2 will review those results before owner M9 review.

## Offline integration and tests

The exact integrated task command exited 0:

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

The full command is now running; no full-suite PASS is claimed yet:

```sh
uv run --directory backend pytest --basetemp ../runs/p305-final-full-20261113 --junitxml ../runs/p305-final-full-20261113.xml
```

It collected 1596 items, including the three existing opt-in development skips.
The following final-code checks have already exited 0:

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
| Local Markdown file links | PASS; 37 across 5 changed documents, plus new upstream handoff anchor |
| `git diff --check` / committed working-tree diff | PASS at this checkpoint |

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

P1 reference verification will be recorded from the full executor suite. No
reference, scenario, world, rule-policy or generated frontend source is edited.

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

The smoke is prepared but NOT_RUN. Offline full-suite completion remains a
prerequisite. Its immutable registration is
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
uv run --directory backend python ../scripts/p3_trials.py resume --registration ../content/experiments/p3/development/p3-smoke-r1.json --case p3-smoke-r1.s1292387875 --checkpoint ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json --out ../runs/p3/p3-smoke-r1/continued --live --dotenv "E:/桌面/Living_World/.env"
uv run --directory backend python ../scripts/p3_trials.py replay --source-run ../runs/p3/p3-smoke-r1/continued --ancestor ../runs/p3/p3-smoke-r1/first/checkpoint-0000000008.json --out ../runs/p3/p3-smoke-r1/recorded
```

No live authority has been initialized, no live slot enrolled, and no API spend
incurred at this documentation checkpoint. Initialization/enrollment results and
the actual remaining grant will be added before dispatch. The completed report
separates reported usage, conservative ledger charges, unknown usage and provider
invoice evidence. It never labels a conservative ceiling as a confirmed invoice.
Deliberate rule choices are excluded from the LLM acceptance denominator;
fallback and wait shares remain visible.

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

## M9 disposition

Pending evidence, independent Gate 2 and owner review. No M9 acceptance declaration,
main merge or P3-06 start is authorized by this task.
