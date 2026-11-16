# P3-07 offline evaluation and inspection evidence

Status: IN_PROGRESS. This report is not M10 acceptance or live-trial authorization.

## Owner-directed execution adjustment

On 2026-11-16 the owner reported that the long verification took too much time
and requested an adjusted approach and a plain-language explanation. The actual
deliverables are the resident identity/goal/experience panel, a view of the
evidence behind each decision, and an offline evaluation report. Those features
and their ordinary automated/browser checks are implemented. The outstanding
1,008-tick fake run checks long-duration record/replay consistency; it is not a
real-model behavioral trial.

At source freeze `74fed105a0723fc91932a34f35a00bfe3a493770`, all repository command
checks passed: 1,880 backend tests, 24 existing skips, 164 frontend tests, 17 schema
checks, the other static/build/generation checks and eight historical hashes.
The independent consolidated review found no new implementation issues. Final
task Gate 2 remains pending the long proof and final handoff. Complete command
evidence is `p307-gate1-74fed10-complete.json` in the chat evidence directory.

Generation C was deliberately stopped after 12,309.486 seconds, preserving
checkpoint 132 with 395 decisions and 396 fake calls. Its automatic fixture-commit
and proof worker was stopped first. Exact PIDs, parents, creation times and task
commands were checked before targeted termination; no unrelated process or file
was removed. The original wrapper exit record is retained. This interrupted run
is **not passed**, has no tape and has no completed long proof. Its disposition
is `D:/p307-v04-generation-c-check/disposition.json`. All three interrupted
authoring attempts remain retained. There is no active automatic long restart.

A bounded read-only checkpoint-132 diagnosis found that all 1,582 retained row
decodes hit the cache, but full context graphs were still reconstructed and
intrinsic hashes repeatedly computed. An external prototype preserved the
surrounding validation function bodies and returned equal verified checkpoints:
two warm complete verifications took 6.79/7.10 seconds before and 1.64/1.65 seconds
with private context facts. This approximately 4.2x result is feasibility evidence,
not a production result or full-horizon forecast. A separate compression probe
also identified a possible way to keep later rows within bounded memory while
still comparing their complete current bytes. Cold timings were not controlled
comparisons, and no cold speedup is claimed.

The existing independently authorized P3-PERF-U1 task now owns this bounded
follow-up. Its internal representation and capacity design must be documented;
all current-byte, source, relationship, authority and recovery checks remain.
The public independent-copy contract and every frozen format remain unchanged.
The sequence is focused tests, preserved-prefix capacity measurements, a short
actual M6 equivalence test, affected regressions and independent Gate 2. Local
integration remains conditional on that independent review. A new 1,008-tick run
must wait for a reasoned execution-time range and explicit stop conditions;
another small benchmark improvement alone does not justify a blind restart.

The M10 preparation plan separately lists the prescribed seed/cap/control matrix,
exact future dispatch-packet fields and pending U1 integration. It is not a grant
or live dispatch request. New real trials, unavailable original M9 source-run
compatibility, U1 downstream integration and owner M10 acceptance remain pending.

## Execution baseline and authority

The owner accepted P3-06 at `5d9eb1862df307a586635441a139c731d9e2e417` and authorized its publication and conditional merge. PR [#3](https://github.com/Lanchy-ou/Living_World/pull/3) retained that exact head. GitHub [CI run 43788061888](https://github.com/Lanchy-ou/Living_World/actions/runs/43788061888) completed backend, frontend and contract jobs successfully before merge. The head was rechecked immediately before an expected-head guarded merge.

P3-07 execution baseline: `34df3deb2abbf816926de89a7e3187aa0ec587b4`, fetched from origin/main after that merge. The accepted P3-06 commit is an ancestor. Worktree: `D:/Codex/.codex/worktrees/p3-07-offline/Living_World`; branch: `task/P3-07-offline-inspection`. The earlier worktrees and historical evidence are preserved.

The subsequent [main push CI run 43789848036](https://github.com/Lanchy-ou/Living_World/actions/runs/43789848036) also completed all three jobs successfully.

The owner authorized offline implementation, independent review and browser checks. P3-07 is to remain local and READY_FOR_REVIEW when complete: no automatic push or merge. No real model calls, key reads or new live budget authorizations are permitted. Historic smoke accounting is not a fresh spending grant.

## Serial execution and file ownership

P3-07 remains one task. Its backend/export/generator phase precedes its character/debug UI phase; there is no parallel production split. The backend author is configured as Astra / High. The later UI author is to use Sol / High. A separate nonauthor Astra / High reviewer performs Gate 2. These describe tool-requested child configurations; the lead's own model configuration is not independently verified.

The lead owns this report, the task handoff, retrospective and README integration. The backend author owns only the task's new backend modules/tests/fixtures, new experiment and inspection-generator scripts, the inspection generation command and generated P3 output. The UI author starts after the backend handoff and owns only permitted frontend implementation/test paths. Existing replay schemas and P2 tooling remain unchanged.

## P305-U1 disposition

The multi-seed registration defect remains on this baseline. Registration 0.1 has one top-level effective world configuration hash, while the unchanged hash includes seed. It cannot validate all cases of the two-seed development or three-seed acceptance matrix. This does not block single-case offline reports, inspection/UI or the single-seed V-04 fake proof.

On 2026-11-16 the owner approved the separately submitted versioned correction as an independent upstream task. Its branch is `task/P305-U1-registration-v02` in `D:/Codex/.codex/worktrees/p305-u1-registration/Living_World`, from the same merged baseline. Approval covers the proposed frozen-spec amendments and mechanical decoder changes, offline verification and independent review; it grants no live calls, spending or merge.

Approved design: preserve 0.1 models, serialized artifacts and hash meaning unchanged; introduce explicit closed 0.2 registration models with an exact original TOML `world_config_source_sha256` plus an effective `world_config_sha256` on each trial and control case. Reconstruct each effective configuration from the pinned world source with only seed overridden. Controls match the paired seed, horizon, map and configuration and retain the legacy zero-cap path. Unknown/mixed versions and wrong source/derived identities refuse. Existing registrations, enrollments and historical evidence are never upgraded or rewritten.

The upstream task owns the evaluation registration specification, open-question entry, core registration models, persistence readers, mechanical sim decoder routing, `scripts/p3_trials.py` and their existing regression tests. P3-07 does not edit those files. Until the upstream change is independently reviewed and accepted for integration, P3-07 uses current 0.1 interfaces and reports multi-seed trial execution as blocked. No registration splitting, seed-free hashing or skipped check is an allowed workaround.

## Verification ledger

| Check | Current result |
| --- | --- |
| P3-06 publication, exact-head and GitHub checks | PASS before merge, as recorded above. |
| P3-07 locked backend setup | PASS: 26 locked packages installed. |
| P3-07 locked frontend setup | PASS: 173 packages, pnpm 10.34.9. |
| P3-07 backend implementation and integrated tests | PASS at `74fed105a0723fc91932a34f35a00bfe3a493770`: 1,880 passed, 24 existing skips, zero failures. The separately reopened performance follow-up requires new affected verification. |
| Frontend lint/typecheck/build/tests/schema | PASS at `97fb75a336ff48aab596eee26f5548aa4c447ccf`: 164 tests and 17 schema tests. Three unused-disable warnings in generated P3 types; no lint errors. |
| Actual browser inspection | PASS: six positive, nine negative and two source-navigation checks in Chrome 157.0.8103.78; details below. |
| Independent P3-07 Gate 2 | Backend, UI, prior PERF and integrated consolidation reviews PASS for their stated scope; final task disposition PENDING long proof, new PERF follow-up and final handoff. |
| Complete repository checks, generation drift and eight historical hashes | PASS at `74fed10`: all 14 non-pytest commands exited zero, both generators produced no diff, and all eight fresh historical hashes matched. |
| Registered V-04 long fake and raising-sentinel replay | NOT_COMPLETE: C deliberately stopped at checkpoint 132 under owner execution adjustment; no frozen tape or complete proof. A/B interruptions also retained. |
| New real development/acceptance trials | NOT_RUN: no dispatch approval; multi-seed U1 upstream correction pending. |
| M10 owner acceptance | NOT_RUN: not requested until the required evidence is ready. |

Each completed verification will record exact commands, exits, counts, versions and artifact identities. Existing skips, environmental failures and unexecuted checks are reported separately.

### Completed serial implementation and browser evidence

Backend/export/generator work froze at `a70aa23045ecfda8da6e0883f8af1265a16ae531`
before the Sol / High UI implementation began. UI source froze at
`97fb75a336ff48aab596eee26f5548aa4c447ccf`. Both are local P3-07 commits.
The new report separates VM metrics, technical validity, allocation arithmetic
and missing immutable issuance evidence. A caller-supplied slot mapping is not
proof of authorization; issuance provenance remains MISSING/technical FAIL until
appropriate immutable evidence is supplied through an approved interface. No live
authority is consulted to fill this gap.

The executor used a fresh headless Chrome profile and local Vite server, selecting
actual files through the browser's file inputs. Committed `ui-manifest.json` and
`ui-edge-manifest.json` identify all source archives, replay and inspection bytes.
Evidence is retained at:

- `D:/p307-browser-positive-a/result.json`: character provenance, literal imported
  HTML, same-boundary completion/replanning, unknown usage/latency/cost,
  nondecision state, stale/dead residents and zero-call decisions.
- `D:/p307-browser-negative-a/result.json`: unknown version, wrong run/config/map,
  missing/duplicate file members, damaged shards and unrelated replay reject; rejection clears
  stale inspection while replay remains usable. A legacy replay without a sidecar
  imports and advances normally. No remote network requests were observed.
- `D:/p307-browser-sources-a/result.json`: accepted decision and objective event
  links seek their committed source tick and identifier.

Screenshots and DOM assertions accompany each result. The executor visually
inspected character/debug layouts, the literal `<img ...>` speech and the Unknown
usage/cost fields. Imported markup created no image or JavaScript dialog. Browser
checks observed no uncaught runtime exception. These are synthetic fixture checks,
not real-model behavioral evidence.

The independent UI-only Gate 2 also passed: 10 focused tests and nine actual
browser scenarios, including a separate missing-sample refusal, with five
screenshots inspected and no runtime exceptions or dialogs. Its generic omitted
file check omitted `trace.json`; the separate probe verifies a sample shard is
also required. Report: `p307-gate2-ui/P3-07-UI-Gate2-review.md` in the chat evidence
directory, SHA-256
`13aae6574a9e255c3c12242c90c887cc8ac42cbc155d70bbbf6643c72452fd4b`.
This review covers frozen frontend `97fb75a`; final full-task Gate 2 remains pending.
Registration 0.2 parsing and per-case configuration joins are downstream work after
the separate U1 is accepted for integration; this candidate's generated schema and
UI deliberately remain on the current 0.1 contract.

### Separate U1 review result

The approved upstream implementation is local at
`69d1f53bfb0c385e0a48cf253968ab6d8e798c7d`. Independent Gate 2 passed; final report:
`D:/u1g2probe-pbs6p86w/P305-U1-Gate2-final-review.md`, SHA-256
`817c8f8628515167deb6988b65f31c378bb2c1d17a76b6de77b9b423ba40ca26`.
Its full backend suite passed 1,793 tests with 24 existing skips; frontend and
generation checks passed. Original M9 source-run compatibility is explicitly
NOT_RUN because only receipts/preflight evidence remain at the known historical
locations. No missing history was reconstructed. U1 has not been integrated into
P3-07, pushed or merged, and its approval is not a live dispatch grant.

### Long-proof performance observation

The explicit V-04 generation started from clean production sources at
`b5dfb5736eb63948b7e8f416c1bfa716ea758574`. Its durable evidence lives in
`D:/p307-v04-generation-a-check/`, with source artifacts in
`D:/p307-v04-generation-a/`. The owner approved the separately proposed
P3-PERF-U1 persistence optimization and conditional local integration after
independent Gate 2 on 2026-11-16. The authoring process was then stopped at its
identified process ID, with checkpoint 21 the latest published boundary observed.
`disposition.json` records the interruption, `tape_written:false` and `passed:false`.
Every source artifact and log remains intact. This is not a completed V-04 proof
or a passed replay; a fresh run will follow the reviewed optimization.

A read-only profile of committed checkpoint 10 took 13.870 seconds on this
Windows host: 6.983 seconds in retained-input reading (including 105 cold Git
source reads) and 6.683 seconds in complete committed-log validation. The profile
is retained as `checkpoint10-profile.txt` in the chat's visualization evidence
directory. A normal run already caches Git blobs; repeated typed/canonical log
validation remains substantial. Concurrent checks and profiler overhead make this
a diagnostic observation, not a controlled performance benchmark or an ETA.

No runtime checks were removed or bypassed. The approved separate upstream
optimization will reuse successfully validated immutable row decodes within one
verification session, while still re-reading/hashing source bytes, checking every
cross-record link and preventing mutable-object cache contamination. It needs its
own scoped implementation, corruption/continuation tests and independent review;
it is tracked as P3-PERF-U1, rather than an undeclared P3-07 runtime expansion.
The owner permits local integration only after independent Gate 2; no push or
main merge is authorized. P305-U1 source ownership was explicitly frozen/released
at `3c04d44d524461c142c3a2469c9a2ede39605c00` before this new writer starts.

The separate candidate `ec531c112fd45199f591fd5095f5b6ac4b8e6247` passed
independent Gate 2. The reviewer reran 28 tests and a four-tick M6 comparison:
34.800252 seconds uncached versus 16.252358 seconds cached, with all 22 retained
source/recorded files and replay bytes equal, and zero replay provider/authority
sentinel accesses. Report: `D:/perfg2-short-15adc0b5/P3-PERF-U1-Gate2-review.md`,
SHA-256 `4ddaba84866f761a6fa904d1c0d7aff6d91d865ce84273c4028bb4136d91d9e6`.
The six approved commits were then cherry-picked locally, without conflict,
through P3-07 commit `e2bed8ba71f72a597670c3ea29cde50a4dc70d4e`. No remote branch
was pushed and main was not changed. Full integrated verification remains pending.

### Review rework and final backend freeze

An independent backend advisory review identified two incomplete report paths:
the single-registration CLI cannot yet consume immutable issuance archives across
all slots/replacement runs, and missing receipts incorrectly leave an empty
accounting subset with a zero cost and a passing sub-status. Overall case validity
already failed closed, but those accounting outputs needed correction. Serial
backend rework after the UI freeze added a closed archive manifest with an
externally supplied owner-approved digest, explicit contained file/hash bindings,
frozen pilot/replacement/predecessor validation and relocated source verification.
It retains missing expected allocations as unknown totals with a separate known
subtotal. Embedded original authority/run paths remain comparison strings; no live
authority path is followed, grant created or frozen format changed. The two fixes
now pass executor tests; final independent execution remains pending.
The advisory report is retained in the chat evidence directory as
`P307-backend-advisory-review.md`, SHA-256
`0532ca4e32f278539f5722a4038fe2043b6d83aef1944aaf0d9f147e767940c0`.
Its offline reproducer confirms both findings. The reviewer reported no further
actionable metric/export findings against pre-rework `e2bed8ba`; this advisory
review does not replace final Gate 2.

The final backend freeze is `a1278858e86d3e7b6da2a66ee12a72316030e18c`.
Command: `uv run --directory backend pytest tests/p3/test_evaluation.py
tests/p3/test_inspection.py tests/p3/test_compatibility.py --basetemp
D:/p307-6619ebaee3c1 -q -ra`: 103 passed in 275.76 seconds, exit 0, no skips.
The additional archive/owner-focused selection passed 18 tests in 29.46 seconds.
Ruff lint/format (176 files), mypy (91 files), all eight import contracts and both
formal generators passed with no generated diff. After tests completed, three
owned files were normalized to exact committed LF bytes; 163 executing source,
script and fixture files were compared with their Git blobs with zero mismatches.

The first actual positive report test exposed tuple-valued frozen P2 physical
summaries that the P3 DTO encoder could not serialize. Report JSON now uses the
existing P2 canonical data encoder; metric arithmetic and inspection serialization
are unchanged. The initial failure remains at `D:/p307-4a06360263c7`; a regression
asserts the complete emitted report bytes. Actual fake archive/source/replay tests
exercise the full offline path with raising external-port sentinels. Canonical
synthetic snapshots cover six-slot and CR-007/008 rules; they do not replace or
reconstruct missing historical M9 run evidence. This is one review rework round.

## Completed first integrated check and interrupted authoring

At clean freeze `443b1626c16265c1b9dc74ff9d9602001a2953e7`, the complete backend
test tree passed in three disjoint partitions: 993 legacy tests plus three
existing skips, 15 one-resident tests, and 866 remaining P3 tests plus 21 existing
skips. Total: **1,874 passed, 24 skipped, zero failures**. The three P2 skips
require the existing long-run opt-in. The 21 P3 skips require
`P305_U4_RETAINED_RUN` to locate the original retained M9 source; they are not
failed checks and are not tests requesting new real model calls. Those original
source files remain unavailable. Evidence: `p307-gate1-443b162-complete.json` in
the chat evidence directory, with exact argv, fresh bases and exit records linked.

All 14 non-pytest checks at that same freeze exited zero, including locked setup,
backend static checks, frontend lint/typecheck/build, 164 frontend tests, 17 schema
checks, both formal generators and a clean generation diff. The three generated
ESLint warnings remain informational. Fresh P1 and P2 runs matched all eight
historical hashes (`p307-p1-integrated-hashes.json` and
`p307-p2-integrated-hashes.json`). These results attest this freeze; the following
cache integration requires its own final checks.

Generation B used the exact same freeze and retained outputs in
`D:/p307-v04-generation-b/` and `D:/p307-v04-generation-b-check/`. On 2026-11-16 at
04:54 UTC, its recorded process IDs and the remaining P3 test wrapper no longer
existed; neither had written a completion exit record. The cause was not
established. The latest published V-04 boundary was tick 35, with no tape or proof.
New disposition files record these interruptions; no artifacts were removed or
overwritten. The interrupted P3 partition was rerun completely at the unchanged
freeze in `D:/p307-p3-remaining-b-check/` (866 passed, 21 existing skips,
1,358.73 pytest seconds, exit zero). Its incomplete predecessor is not counted.
Generation B remains **NOT_COMPLETE**, rather than a behavioral failure or a
completed long proof. Hidden local Windows process creation now separates long
verification workers from the tool-host process lifetime; no scheduled task,
service or persistent machine setting was created.

## Reviewed cache follow-up within the approved upstream scope

The approved P3-PERF-U1 follow-up preserves the exact 128 MiB raw-byte admission
bound, protected-row policy and every current-byte/source/relationship/authority
check. Only validated concrete owner DTOs use an internally encoded, operation-local
copy representation; it is never read from external input or persisted. Other
models retain the former deep-copy path, and compatibility failures fall back.
No saved schema, world behavior, provider, budget or inspection format changed.

Candidate `f3bcf77e1d3c3be375d633fb33bf317df7ebf2b2` contains tested code
`e6536fdb52de2df1792a44f87723ba573489cc20` and evidence-only follow-up. The executor
passed 29 dedicated tests and all 338 affected regressions (863.60 seconds,
zero skips/failures), static/import checks and an actual five-mode short M6
comparison. The independent reviewer passed 33 tests and separately compared all
22 source/recorded files and replay exports across five modes, with zero external
provider/authority sentinel accesses. Final review SHA-256:
`627ff4a52578f406d1ec2da26dc4df22a38980a84a0bd586839e1dc95eee3882`, report
`gate2-clone-followup/P3-PERF-U1-clone-Gate2-review.md` in the chat evidence directory.

The committed checkpoint benchmark measured a 15.21% median reduction. Actual
four-tick measurements differed by host conditions: 14.25% executor, 7.32%
independent reviewer. They are separate measurements, not pooled values or V-04
throughput estimates. Earlier prototype timing/memory evidence is explicitly
separate in [the upstream follow-up report](P3-PERF-U1-clone-evidence.md).

After final independent PASS, the two upstream commits were cherry-picked locally
without conflict through `5738788a1eaf9debc8242d05d763ae23273c1a29`. Neither branch
was pushed and main was not merged. A fresh final integrated check and V-04
generation C follow this documentation freeze. No frozen tape exists yet, so no
golden result was regenerated to conceal a mismatch.

## M10 pending evidence

- Independently reviewed offline evaluation, export, character view and debug view.
- U1 upstream acceptance/integration and versioned registrations for the full prescribed matrix.
- Exact code/registration SHA, model/counter identities, seeds, horizons, actors, attempt/token/money caps and stop conditions for any requested live dispatch.
- Fresh budget-ledger reconciliation at that separately authorized live preflight; historical balances cannot authorize execution.
- Complete registered cases and matched frozen P2 controls, with missing/invalid pairs and technical failures retained.
- Technical criteria separately reported from descriptive behavior; no claim of general intelligence, improved personality or seven-day real-model survival.
- Final one-page retrospective and owner M10 disposition.
