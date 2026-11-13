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
- Adapter `deepseek-responses-v0` / `0.2`; counter
  `deepseek-flash1017-byte-upper-bound` / `0.1`; tokenizer SHA-256
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

## Offline integration and tests

Pending implementation results. Required evidence includes the one-Ella complete
loop, real frozen-rule fallback and return, goal revise/continue/abandon and own
feedback, failed physical actions, private-state isolation, active/queued living
resume, budget/case ownership and no-call replay with raising external-port sentinels.
VF-01..19 will be mapped to named new or inherited regression evidence.

Current executor checkpoint (before final slice and upstream counter integration):
`test_reexecution.py` passed 8 tests in 180.89 seconds; the launcher author's
`test_trial_registration.py` passed 24 tests in 132.17 seconds. Backend Ruff,
format check, Mypy (88 source files), all eight import contracts, frontend
lint/typecheck/build and frozen type-generation comparison passed. These are
intermediate checks, not the final candidate's full-suite result. The initial
misspelled path `tests/p3/test_reexecute.py` collected no tests (exit 1); it was
corrected to `test_reexecution.py` before the eight-test successful run.

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

## Upstream follow-up P305-U2

Owner: P3-04 provider token counter. The original certified byte upper bound
rejects the real first smoke request before dispatch: 45161 input tokens exceeds
B-05's 32768. This is reproduced with the unchanged M6 world, approved smoke seed,
Ella explorer identity, production prompt/schema and the real Responses adapter;
system and user UTF-8 sizes are 15286 and 15691 bytes respectively. The remaining
bound covers schema/framing. The runtime correctly records
`INVALID_CONTEXT / INPUT_LIMIT`; no credential or provider call was used.

The finding was returned to the P3-04 owner for a separately reviewed, proven
counter refinement. Initial upstream analysis reports an ASCII-only partial BPE
bound of 30209 for this request, retaining the full byte bound for non-ASCII text.
That result is preliminary until its implementation and independent review land.
P3-05 does not alter the frozen input cap, context, prompt or provider internals,
and will not use a synthetic counter as live evidence. Live execution remains
blocked until the reviewed counter admits the actual request and the committed
registration pins its exact identity and source bytes.

## M9 disposition

Pending evidence, independent Gate 2 and owner review. No M9 acceptance declaration,
main merge or P3-06 start is authorized by this task.
