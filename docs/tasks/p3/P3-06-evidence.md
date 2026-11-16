# P3-06 offline evidence

## Authority and execution baseline

The owner authorized P3-06 offline implementation, verification, independent Gate 2,
and read-only preparation for P3-07 on 2026-11-16. No new real API call, credential
read, spending authorization, historical evidence cleanup, or main merge is authorized.
The historical CNY1.734080 smoke total is not a fresh ledger audit or spending grant.

Fetched `origin/main` and verified its tip is
`3cc2c5ffdce2685c4d59079715cac28a2a427bee`, the supplied PR #2 merge commit.
The original checkout on `task/P3.5-EV-01-evaluation-adr` was preserved. Work is isolated
on `task/P3-06-offline-validation` in
`D:/Codex/.codex/worktrees/p3-06-offline/Living_World`.

Read AGENTS.md, the P3 implementation plan, P3-06/P3-07 cards, M8 decisions,
M9 evidence and acceptance review, and the experience, cognition, decision/recovery,
and evaluation specifications. M9 acceptance overrides older pending statements.
P3-07 production work remains dependent on P3-06 acceptance and merge.

Implementers were explicitly configured as GPT-6 Sol / High, with disjoint test and
fixture files in this one task worktree. P305-U1 analysis was GPT-6 Astra / High.
The lead cannot verify or change its own model/reasoning configuration through the
available tools and does not attest it as Astra / High. Gate 2 must be performed by
a separate GPT-6 Astra / High agent that did not contribute implementation or analysis.

## P305-U1: reproduced, upstream disposition required

The defect remains at the execution baseline. `TrialRegistration` version 0.1 has
one top-level `world_config_sha256`; retained-input validation compares it with the
complete effective world configuration, including `meta.seed`. Its case list permits
multiple unique seeds, which necessarily produce different effective hashes here.

The read-only offline probe loaded the frozen M6 TOML/map from
`7c13d78ffd7d89006f6008c8a09f37ae97c253db`, changed only seed in memory, and used the
existing `retained_fixture` helper. Every seed-specific single-case input passed
`validate_inputs`. The probe then assembled multi-case fake-purpose registrations,
summed caps, recomputed the canonical registration digest, and expanded each policy
template with that digest. Schema validation passed. Keeping the first case's
configuration hash produced the following results, with zero socket attempts:

| Group | Seed | Effective configuration SHA-256 | Multi-case input result |
| --- | --- | --- | --- |
| Development | 509071611 | 39eb2e023276193a42cb6f4b496b7bf77b3a2a01d22a9ec43f16e8a4cd8e5d9b | PASS |
| Development | 1945790632 | 84a39f1052561cf377e1b98594adbbae70cd0f5cfa1c968ef7d4e9b33f53c3f8 | REFUSED |
| Acceptance | 401604645 | cd9088324ec5b7fb0909e36660da5762637ee6c4fbc05a3234a3c6cdeff6c087 | PASS |
| Acceptance | 4054202024 | 868e42349e2a3281234621af0330b246cd881283400b326fda95260c5231cca1 | REFUSED |
| Acceptance | 538041037 | 999e1653bc85daae9925f2db4a181d0c83e0535f46bec0927fc074fa1209f458 | REFUSED |

Each refusal is `registered world input identities differ`. These are in-memory
contract fixtures using published seed values, not live registrations, trial results,
or behavior measurements. The first probe needed the existing unit-test helper path;
the corrected reproduction exited 0. No provider or allocation authority was used.

Retained reproduction: `D:/p306-u1-analysis/reproduce.py`, `output.json`, and
`report.txt`. Invoke the script with the worktree root as its sole argument, using
Python 3.13 and the locked backend environment. The retained rerun records helper
commit `9d2df69b9cd16b6394ab6e61e5d2f836b09748b8`; all relevant production and existing
fixture files are unchanged from the baseline, and the probe preserved concurrent
untracked task files. SHA-256 values are respectively
`53231ac50ebee8f74a4ef2e9a3f5a794245a4820af097d6b76b3f85e2ced2e3d`,
`75be69cf635294ce622e07c3184f62a20bf95748063fcb45198239604c288965`, and
`a136bfea2429a4fcae88a2688ca0a320eae54fb06e929cf0e2e890d558d3510a`.

This blocks V-02's two-seed registration and V-03's three-seed P3 registration, and
therefore complete acceptance pairs. Legacy P2 controls do not directly use this
validator. Single-case smoke, one-seed three-resident fakes, and V-04's one-seed long
fake are not inherently blocked. The launcher currently supports smoke/fake only;
development/acceptance launcher integration remains a separate P3-07 deliverable.

### Proposed upstream change, not implemented

Owner: P3-03 persistence / P3-01 evaluation contract, as already recorded in M9.
Current rule: one registration-level effective configuration hash for all cases.
Requested rule: an explicitly versioned registration representation with one effective
configuration hash per case, explicit matched-control identity, and shared map/source
pins. Recommendation: approve a separate upstream CR and task before implementation.

Affected files to assess in that task:

- `docs/spec/open-questions.md` and `docs/spec/p3-evaluation-v0.1.md` section 3.2:
  CR disposition and new versioned case/control hash semantics.
- `backend/src/living_island/contract/p3_save.py`: closed versioned registration models.
- `backend/src/living_island/persistence/p3.py`: version-aware input validation.
- `scripts/p3_trials.py`: version-aware registration construction/reading, coordinated
  with the separately owned P3-07 development/acceptance support.
- `backend/src/living_island/sim/p3.py`: audit all registration decoding consumers.
- Existing persistence, registration, and replay test files: multi-seed success,
  wrong-case/config/seed rejection, and historical registration/replay preservation.

Preserve version 0.1 bytes, meaning, and validation. Do not remove seed from the world
hash, reinterpret old hashes, split registrations to evade the defect, or weaken input
checks. Existing registration hashes bind policies, manifests, receipts, and allocation
identities; new versions require explicit dispatch and compatibility tests. A changed
registration hash never grants spending authority. P3-06 changes no frozen format,
historical registration, production validator, or specification.

## Verification record

### Isolation and social evidence

The isolation/social candidate is
`eb7191fec76e8a7f47697a06289ab264e20bfe50`. Its author ran the two assigned test
files: 11 passed in 33.80 seconds, with Ruff lint/format checks passing. This is
executor evidence, not independent acceptance. The initial construction failures
used incorrect fixture run/tick/plan identities; corrections preserved production
validation. No production defect was bypassed by weakening an assertion.

| Proof | Executable evidence |
| --- | --- |
| Three private decisions and replay | `test_three_primary_decisions_are_canonical_and_replay_without_external_access`: nine decisions in ella/mia/ryan order, distinct own goals/feedback/IDs, complete state replay with raising provider/fallback/authority sentinels, unchanged fake authority bytes |
| One event, two owners | `test_one_world_utterance_is_captured_independently_by_two_hearers`: same engine utterance, separate owner IDs and delivery sources |
| Privacy and conflicting histories | Non-hearer and conflicting-claim tests use engine deliveries; foreign store queries/deliveries refuse; no shared transcript or inferred missing speech |
| Social speech versus delivery | Request accept/refuse tests and `test_social_agreement_and_receiver_inventory_cannot_complete_an_own_give_goal`: agreement cannot transfer; failed give is attempted; only exact own successful give completes; receiving remains unverifiable |
| Moving target, interruption, contention | Engine OUT_OF_REACH after target movement, DIRECT_SPEECH interruption, and two givers competing for one free recipient slot; only one transfer succeeds |
| Replanning and capacity | Old feedback retains its copied intent after replanning; explicitly synthetic oversized packets evict memory without erasing current references or copied goal evidence; nondecision ingestion continues |

The engine-backed scenarios use existing test worlds; the oversized retention packet
is deliberately a typed synthetic boundary probe, not a claim that such speech can be
authored through the normal model contract. Receiver observations are not enriched
with objective-log donor attribution. No relationships, emotional state, reflection,
new action, or extra perception permission is introduced.

### Extension identities and exact replay

Full code candidate: `24dd65fb45a15f3dcdb77335e0cf1a455a160c17`.
The extension author reports 23 passed in 80.62 seconds. The combined executor and
independent reruns are recorded separately below. The test suite reads actual committed
HEAD sources, validates helper/tape bytes against Git, retains all 94 required production
inventory pins, and explicitly pins the test selector, provider helpers, tape, prompt,
profile, and pure dependencies. The recent-only implementation exists only in the
allowed test-helper directory. Production runtime, provider, and contracts are unchanged.

- EX-11 asserts exact distinct six-record ranks for both algorithms, projected order,
  complete manifest, hashes, and unchanged store.
- EX-12 covers empty recall and the 17-record limit. Equal context/projection hashes
  under empty recall do not excuse incorrect profile/manifest identity. Wrong or missing
  strategy/source/config/profile bindings and live fixture misuse refuse before external
  provider access. The live negative refreshes dependent hashes so it reaches the
  intended live-profile rejection.
- VF-20 runs all four adapter/selector combinations. Two distinct closed-tape adapters
  retain complete expected requests, wire bytes, counts, and results; missing/extra calls
  refuse. Their scripted 1/2 ms latency changes diagnostic audit bytes while physical
  and cognitive outcomes remain equal.
- Every source run is reexecuted with raising provider, fallback, and allocation-store
  sentinels. Complete checkpoints, context/decision/call/event logs, manifest identity,
  packing, and hashes match exactly.
- An additional two-tick, six-step tape creates divergent rankings for all three actors.
  Correct fixture replay matches, while an adversarial selector claiming the fixture
  identity but executing the default algorithm raises `ReplayDiverged`. Thus the replay
  proof does not rely solely on coincidentally identical one-tick recall.

The four original one-tick tapes and the additional two-tick tape are separate tracked
fixtures. No historical registration or previous tape was rewritten. Their authoring
used local deterministic provider responses; timings are scripted data, not measurements
of a hosted provider. Input pins use actual committed source, avoiding an assumption
that an unpinned callable or a new label is a verified implementation.

Implementation, complete executor testing, and independent code review are complete.
Final documentation review is recorded separately below. Results are actual executions;
the interrupted initial group is not counted as passing.

| Check | Exit | Result |
| --- | --- | --- |
| `uv sync --directory backend --locked` | 0 | Python 3.13.5; locked dependencies installed |
| `pnpm --dir frontend install --frozen-lockfile` | 0 | pnpm 10.34.9; locked dependencies installed |
| `uv run --directory backend mypy src` | 0 | 88 source files |
| `uv run --directory backend lint-imports --no-cache` | 0 | 8 kept, 0 broken |
| `uv run --directory backend ruff check .` | 0 | Full backend PASS on final code candidate |
| `uv run --directory backend ruff format --check .` | 0 | 165 files formatted |
| `pnpm --dir frontend lint` | 0 | PASS |
| `pnpm --dir frontend typecheck` | 0 | PASS |
| `pnpm --dir frontend build` | 0 | 150 modules |
| `pnpm --dir frontend test` | 0 | 154 passed; no skips |
| `pnpm --dir frontend test:schema` | 0 | 17 checks passed |
| `uv run --directory backend python ../scripts/gen_types.py` | 0 | Formal generation |
| `git diff --exit-code -- frontend/src/api/generated` | 0 | No generated drift |
| `uv run --directory backend pytest tests/unit tests/invariants tests/dev_runs --basetemp D:/p306-legacy-a` | 0 | 993 passed, 3 existing skips; 504.52 seconds |
| `uv run --directory backend pytest tests/p3/test_three_residents.py tests/p3/test_social_evidence.py tests/p3/test_extension_ports.py --basetemp D:/p306-new-final-a --tb=short` | 0 | 34 passed; 114.16 seconds; log `D:/p306-new-final-a.log` |
| `uv run --directory backend pytest tests/p3 --ignore=tests/p3/test_one_resident.py --ignore=tests/p3/test_three_residents.py --ignore=tests/p3/test_social_evidence.py --ignore=tests/p3/test_extension_ports.py --basetemp D:/p306-other-b --tb=short` | 0 | 706 passed, 21 existing skips; 999.13 seconds; persisted exit record `D:/p306-other-b.result.json` |
| `uv run --directory backend pytest tests/p3/test_one_resident.py --basetemp D:/p306-slice-b --tb=short` | 0 | 15 passed; 1408.64 seconds; persisted exit record `D:/p306-slice-b.result.json` |

Complete final backend result: **1,748 passed, 24 existing skips, 0 failed/errors**
across all 1,772 cases. The four successful groups contain 993+706+15+34 passes and
3+21 skips. The 24 skips are exactly the three opt-in P2 development checks and 21
retained-live-evidence checks. No skip condition changed. Existing regression files
and production sources stayed unchanged throughout the task; final task tests are
the independently reviewed code candidate. The interrupted earlier run contributes
no results to this final total. Both restarted-group exit codes are also retained in
`D:/p306-gate1-b.result.json`.

The legacy/invariant log is retained at `D:/p306-legacy-a.log`. Its three skips are
the existing opt-in P2 development checks; no skip was added or weakened. The fresh
P1 CLI run/resume/reexecute/replay artifacts are retained under
`D:/p306-legacy-a/test_default_1008_tick_cli_run0`. A separate hash check exited 0 and
matched all four P1 references; details are retained in `D:/p306-p1-hashes.json`.

The final collection check exited 0 and proves that the executor groups are
pairwise disjoint and exhaustive: 742 existing P3 + 996 legacy/invariant/development
+ 34 new P3-06 = 1,772 collected tests. The existing P3 portion is finally split into
15 one-resident tests and 727 other P3 tests. Full node-ID lists and counts are retained in
`D:/p306-collection.json`, with command output in `D:/p306-collection.log`. The existing
P3 group excludes exactly the three new task files; the new group runs those files
together. No test is omitted from the partition.
The exact four-way refinement is retained in `D:/p306-collection-final.json`; a
separate set-equality and uniqueness assertion exited 0 with counts 996/34/15/727.

Fresh P2 reference command (exit 0, tick 1008, 14,351 events, 1,305 decisions):

`uv run --directory backend python -m living_island run --config ../content/worlds/default.toml --policy rule-based --seed 2600456787 --ticks 1008 --checkpoint-every 144 --out D:/p306-p2-reference-a --export-replay`

The source artifacts and log remain at `D:/p306-p2-reference-a` and
`D:/p306-p2-reference-a.log`; the independent hash comparison exited 0 and is retained
in `D:/p306-p2-hashes.json`. Logs/replay are hashed as exact bytes; final world is
canonical sorted-key compact UTF-8 JSON, without LF. All eight references match:

| Artifact | P1 SHA-256 | P2 SHA-256 |
| --- | --- | --- |
| Events | 2d68a49b495e46a150322711bc8fbb38779ad947c4345ec0f11c89bd08d03287 | 427f7f0536c4cedc77b365e821575465d83a60f90d857a73bdf8b45e8fb3574a |
| Decisions | ee614c057b02d65b67ee6ff5336e17434ab4aeb6026c710f853d7d599c36e4bd | 67c490e74b963b32fa2393ec92b97d8f412f46c3146a5c20b6bc63a1d5add194 |
| Final world | 113483069d74936a3fa5ecf0f719405dc7499698fc851cdc4b992a84e25357ed | 5efcf3eab02db3928bc55e4a226327acde2bbfee54abc898f7649d6e4302382c |
| Replay | 8e26d853b6bf324fa4a375f0edfca526c09754b78d7eaee9b96c615464dbfb83 | 720bccc76cb1c3baff78a74bec7703e76764be777713b43df6e30d297f9d36e8 |

### Independent Gate 2

GPT-6 Astra / High reviewer `gate2` did not contribute implementation, fixtures,
upstream analysis, or documentation. Code disposition: **PASS** at
`24dd65fb45a15f3dcdb77335e0cf1a455a160c17` against baseline `3cc2c5f`.

- Independently reran all three task files: 34 passed in 112.09 seconds, exit 0,
  using locked environment Python `-B`, pytest with cache disabled, and fresh short
  basetemp `D:/p306g2-579384ef`. Source stayed frozen; `git diff --check` passed.
- Independently replaced the provider factory in process with a raising
  prepare/count/complete access sentinel. All seven invalid registration bindings
  refused with zero accesses, using `D:/p306g2neg-1o6k7_m4`.
- Independently audited all four A/B-by-selector tapes: exact request/wire/count/result,
  wrong request/wire refusal, three steps each, declared latency 1/2, and base proposals.
- Earlier independent checks passed the 11 social/isolation tests and five existing
  cases: `test_three_runtime_contexts_keep_conflicting_claims_and_nonhearing_store_separate`,
  `test_ex02_deferred_feedback_preserves_inline_ref_after_replan`,
  `test_ex09_buffer_eviction_keeps_current_owned_references`,
  `test_ex09_completed_evidence_survives_real_byte_eviction_and_pure_reexecution`, and
  `test_cg01_03_and_12_exact_goal_evidence_replay` (5 passed, 1.50 seconds).
- Scope review confirmed 12 permitted new test/fixture files, no production, script,
  or frozen-spec changes, and no actionable code finding. This is not owner acceptance.

The successful independent command from `backend` was
`.venv/Scripts/python.exe -B -m pytest tests/p3/test_three_residents.py tests/p3/test_social_evidence.py tests/p3/test_extension_ports.py --basetemp D:/p306g2-579384ef -q -p no:cacheprovider`.
Its process-local environment set bytecode suppression, safe.directory for the task
worktree, and core.longpaths=true. The reviewer did not claim a successful uv wrapper
invocation for that run.

Final overall Gate 2: **PASS** at handoff commit
`0916a4b017248f23becf1cbd90fa33f8ae17b4bd`. The independent reviewer read the final
persisted logs/exit records, recomputed the disjoint 1,772-node union, verified the
1,748-pass/24-existing-skip total and exclusion of the interrupted run, and checked
the seven handoff fields and scope. Only the two allowed task documents differ from
the reviewed code commit. No actionable finding remains.

After that handoff commit, the executor repeated
`uv run --directory backend python ../scripts/gen_types.py` (exit 0), full
`git diff --exit-code` (exit 0), and baseline-to-HEAD `git diff --check` (exit 0).
Worktree status was clean. The reviewer independently confirmed the resulting clean
diff; it did not claim to rerun the generator. The delivery tip adds only this final
review/check record. Task status remains **READY_FOR_REVIEW**, with owner acceptance
and main merge outstanding.

### Environment and retained diagnostic evidence

Initial sandbox Git fetch/branch operations required approved filesystem escalation;
command-local `safe.directory` handled ownership. No global Git configuration changed.
Long-running test subprocesses inherited only process-local `core.longpaths=true`.
The authoritative executor runs use fresh, dedicated short D-drive basetemps, checked
absent before first use. No existing data directory was used as basetemp.

One independent initial `uv` invocation could not open its cache lock and ran no tests;
the reviewer used the same locked environment's Python directly. Early author tests
also used fresh system-temp/E-drive directories before the final short-path runs.
Abandoned author diagnostics were cancelled explicitly (exit 1) after replacement runs
passed; those cancellations are not passing test results. Initial test-construction
errors and source-pin/negative-oracle tightening are retained as executor rework,
not production repairs or erased failures.

No preexisting original-checkout file was changed or reset. Newly created diagnostic
evidence remains untracked in `E:/桌面/Living_World/.p3ext-*` and
`E:/桌面/Living_World/g2-3213a65596`; the original checkout is therefore not claimed
clean. These directories contain this task's fake-run/diagnostic evidence and are not
staged or committed. Author console outputs are in tool history; one early interrupted
social-test temporary directory is no longer present. No bulk deletion or evidence
cleanup command was issued. The final evidence directories/logs above remain available.

The first full existing-P3 command used `D:/p306-oldp3-a` and is retained in
`D:/p306-oldp3-a.log`. During the app's worktree/context switch, the tool session
disappeared and the OS process was no longer present. Its log stops at 94% without
a terminal summary or exit result. This run is **INTERRUPTED / ENVIRONMENT**, not a
passing executor group. The affected 742 tests are rerun as two disjoint groups
(15 one-resident and 727 others), with fresh short basetemps `D:/p306-slice-b` and
`D:/p306-other-b`. The standalone hidden runner `D:/p306-gate1-runner-b.py` persists
each command, log, elapsed time, and exit code to matching `.log` and `.result.json`
files; it never clears or reuses existing directories. Previously completed legacy,
new-task, static, frontend, generation, and historical-hash checks retain their results.

## P3-07 read-only preparation

No P3-07 production file is changed. After acceptance and merge of P3-06, keep P3-07
serial: implement typed offline evaluation/export, then the separate inspection
schema/generator and character/debug interface, and then registered trial/report
integration. Resolve P305-U1 through its upstream owners before multi-seed trials.

Read-only source inspection confirms `App.tsx` owns replay import and display state,
`ResidentPanel.tsx` currently displays physical state/inventory/events, and
`InfoDrawer.tsx` mounts only the existing event/resource/legend views. There is no
current `frontend/src/p3` inspection implementation. A scope-compatible UI plan is
an optional P3 multi-file import and inspector state owned by App, a P3 character
section mounted in the resident panel, and a separate P3 debug view implemented
under `frontend/src/p3`. Keep existing drawer-tab definitions and replay-store/types
unchanged; the two legacy panels receive mounting changes only.

The P2 analysis modules already expose physical metric functions for resident outcomes,
contention, adaptation, and transfer-then-drink. P3 should add a typed read-only input
adapter and its own denominator/validity layer rather than treating a P3 save as a
legacy RunData. The analysis import guard still forbids policy/runtime dependencies;
inspection DTO access must follow the allowed contract boundary. The new schema root
and generator must not join the frozen replay generator's export list.

The prescribed inspection schema supplies one sample per actor per saved boundary,
including dead actors, and one shard per committed decision. UI selection joins
actor/tick and explicitly displays `latest_perception_tick`, since checkpoint samples
are pre-ingestion. Metric fixtures must retain exact numerator/denominator values,
null summaries for zero valid pairs, missing source lists, incomplete/early-ending
cases, and unknown usage/cost. These are requirements and a proposed layout, not
implemented or browser-verified P3-07 behavior.

Character inspection must join actor/tick, show stale state explicitly, and link
identity, goal, experience, and completion claims to committed sources. Debug inspection
must retain full context versus projection, actual strategy/profile/manifest identities,
attempts/errors, usage, and unknown cost. Imported prose is text only. The versioned
inspection format and generator stay separate from frozen ReplayBundle; legacy replay
imports remain usable without a sidecar. Reports/export/replay must neither open nor
mutate live allocation authority. Deduplicate by allocation and reservation ordinal,
reject conflicts and competing completed lineages, and retain original and approved
replacement trial outcomes independently.

V-04 long fake, actual browser inspection, live registered development/acceptance,
matched controls, and owner M10 are not established by this P3-06 test submission.
Prepare exact trial pins/caps/stop conditions only after offline implementation and
independent review; credential access and real execution require separate owner approval.

## Outstanding gates and explicit non-results

| Category | Disposition |
| --- | --- |
| Actually executed | Local commands, counts, hashes, and independent probes are listed above; pending commands are never inferred as passing |
| Existing skips | Three opt-in P2 development checks and 21 retained-live-evidence checks retain their original gating; no task skip was added |
| Environment | Initial Git/cache access and abandoned diagnostic processes are recorded above, separately from test outcomes; final authoritative basetemps are fresh short paths |
| NOT_RUN | New real API calls, live development/acceptance and matched-control matrix, V-04 long fake, P3-07 implementation/browser UI checks, GitHub CI for this unpushed branch, owner M10 |
| Waiting on upstream | P305-U1 versioned registration disposition and implementation before multi-seed V-02/V-03 execution |
| Waiting on owner | P3-06 acceptance and main merge; subsequent live work additionally requires exact approved registration/code/model/counter/seeds/ticks/actors/caps/stop conditions and a current ledger audit |

No real credential was read, no real allocation was issued, and no branch was
pushed or merged into main. Test authorities are isolated, fake, and zero-money.
