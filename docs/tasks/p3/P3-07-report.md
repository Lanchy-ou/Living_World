# P3-07 offline evaluation and inspection evidence

Status: IN_PROGRESS. This report is not M10 acceptance or live-trial authorization.

## Execution baseline and authority

The owner accepted P3-06 at `5d9eb1862df307a586635441a139c731d9e2e417` and authorized its publication and conditional merge. PR [#3](https://github.com/Lanchy-ou/Living_World/pull/3) retained that exact head. GitHub [CI run 43788061888](https://github.com/Lanchy-ou/Living_World/actions/runs/43788061888) completed backend, frontend and contract jobs successfully before merge. The head was rechecked immediately before an expected-head guarded merge.

P3-07 execution baseline: `34df3deb2abbf816926de89a7e3187aa0ec587b4`, fetched from origin/main after that merge. The accepted P3-06 commit is an ancestor. Worktree: `D:/Codex/.codex/worktrees/p3-07-offline/Living_World`; branch: `task/P3-07-offline-inspection`. The earlier worktrees and historical evidence are preserved.

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
| P3-07 backend implementation and focused tests | IN_PROGRESS. |
| Frontend checks, browser inspection and independent Gate 2 | NOT_RUN: implementation pending. |
| Complete repository checks, generation drift and eight historical hashes | NOT_RUN on the P3-07 result. |
| Registered V-04 long fake and raising-sentinel replay | NOT_RUN: explicit offline fixture/proof pending. |
| New real development/acceptance trials | NOT_RUN: no dispatch approval; multi-seed U1 upstream correction pending. |
| M10 owner acceptance | NOT_RUN: not requested until the required evidence is ready. |

Each completed verification will record exact commands, exits, counts, versions and artifact identities. Existing skips, environmental failures and unexecuted checks are reported separately.

## M10 pending evidence

- Independently reviewed offline evaluation, export, character view and debug view.
- U1 upstream acceptance/integration and versioned registrations for the full prescribed matrix.
- Exact code/registration SHA, model/counter identities, seeds, horizons, actors, attempt/token/money caps and stop conditions for any requested live dispatch.
- Fresh budget-ledger reconciliation at that separately authorized live preflight; historical balances cannot authorize execution.
- Complete registered cases and matched frozen P2 controls, with missing/invalid pairs and technical failures retained.
- Technical criteria separately reported from descriptive behavior; no claim of general intelligence, improved personality or seven-day real-model survival.
- Final one-page retrospective and owner M10 disposition.
