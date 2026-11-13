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
This closes that finding only; full Gate 2 awaits the integrated candidate.

Independent launcher review of `5d6867c` reproduced a second P2 finding:
invalid initial `--ticks=-1` mutated the receipt before the runtime rejected the
length, stranding an unused allocation with no checkpoint. The launcher owner is
moving length validation ahead of mutation and making receipt publication follow
the first durable boundary. The same review requested explicit coverage for
crashes before checkpoint zero and after final allocation completion but before
trace/export/receipt completion. The invalid-ticks finding is independently closed at `1aa9296`.
Startup/complete-receipt fixes landed in `b4b4365`; prepared-final publication and
immutable invocation-chain recovery landed in `1329660`. The latter reuses the
existing allocation reconciliation API, catches only its typed closed outcome,
and verifies that generation, caps and reservation identities are unchanged.
Already-complete finalization never opens a case. No new grant or call is allowed.
Independent review of the final prepared-publication path is pending; live
enrollment has not begun.

## Offline integration and tests

Pending implementation results. Required evidence includes the one-Ella complete
loop, real frozen-rule fallback and return, goal revise/continue/abandon and own
feedback, failed physical actions, private-state isolation, active/queued living
resume, budget/case ownership and no-call replay with raising external-port sentinels.
The [fixture provenance and VF-01..19 map](../../../backend/tests/fixtures/p3/one_resident/slice_provenance.md)
identifies named integration and inherited owner tests. The original 14-case author
run had 13 passes and one frozen-DTO test-construction failure. The corrected
negative case and newly added actual-engine VF-17 transfer case both pass; the
independent reviewer reproduced the same results and closed both findings. This
is passing evidence for 15 distinct cases across runs, not a claim of a single
final integrated suite run.

The principal source run completed 24 ticks: Ella 24 accepted fake decisions,
Mia 21 and Ryan 22 deliberate frozen-rule decisions, zero substitutions, 240
charged fake input units, 480 fake output units and zero micro-CNY. Raising
provider/fallback/authority sentinels reproduced its checkpoint, trace and all
five logs exactly. Its source artifacts are retained in the author's isolated
worktree under `runs/p305-slice-final-01/test_frozen_smoke_world_one_mo0/run`;
recorded output is its sibling `recorded/segment-0000`. Full launcher execution
with a committed closed-tape registration is still required before live smoke.

The launcher author passed the original 33-case recovery suite on `7150bbc`,
then five affected/new completion vectors on `cdab3cf`. The final suite has 35
cases. Process-crash mechanics use an explicitly registered two-tick, zero-money
fake case; this does not shorten the required 24-tick smoke or principal fake run.

Current executor checkpoint (before final slice and upstream counter integration):
`test_reexecution.py` passed 8 tests in 180.89 seconds; the launcher author's
`test_trial_registration.py` passed 24 tests in 132.17 seconds. Backend Ruff,
format check, Mypy (88 source files), all eight import contracts, frontend
lint/typecheck/build and frozen type-generation comparison passed. These are
intermediate checks, not the final candidate's full-suite result. The initial
misspelled path `tests/p3/test_reexecute.py` collected no tests (exit 1); it was
corrected to `test_reexecution.py` before the eight-test successful run.

The replay exporter validates checkpoint schemas, input and committed log prefixes,
lineage, frame/event cardinality and the final trace identity. It does not provide
an independent cryptographic seal on every intermediate world or semantically
reexecute the engine during export. The reviewer demonstrated that a same-prefix,
valid-shape intermediate health edit is outside those structural checks. This is
the frozen display-contract trust boundary, not a claimed rejection guarantee.
M9's stronger evidence is an exact comparison of the complete source export with
the independently recorded-reexecuted export using raising external-port sentinels.

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

Full launcher completion, immutable receipt, export and sentinel replay results
remain pending. This fake authority does not enroll any M8 live slot.

## Registered live command and results

NOT_RUN yet. The exact committed registration, implementation/input hashes, case,
canonical authority, preflight result, remaining caps, invocation and fresh output
path will be recorded here before the first dispatch. No API spend has been made
by this task at this stage. Calls may begin only after offline integration passes.

The completed report will separate reported usage, conservative ledger charges,
unknown usage and any provider invoice evidence. It will not label a conservative
ceiling as a confirmed provider invoice. Deliberate rule decisions will be excluded
from the LLM acceptance denominator; fallback and wait shares remain visible.

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
