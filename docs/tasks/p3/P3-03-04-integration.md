# Task P3-03-04: Integrate accepted runtime and adapters

## Brief

Task ID / title: P3-03-04 / Integrate accepted runtime and adapters into main.
Spec baseline: approved M8 application `cc2bf87285e2728d7c433b92c265ce22bbd7e923`.
Integration baseline: `982988ab9b87856dd62fe4cced426971b33b22df`.
Owner instruction, 2026-11-12: integrate both branches, then merge into main.

Goal: combine accepted P3-03 `2867beb44de384077f8998532c76d2d850cf795a` and
P3-04 `41d5ecd4e652a2c4090247673c610939e8c7326a`, preserve both histories,
verify the combined tree and record downstream readiness. P3-05 execution,
live provider calls, credential access and changes to frozen contracts are excluded.

Worktree: existing p3-01-spec-review checkout; branch task/P3-03-04-integration.
Allowed changes: merge the reviewed branches and update this integration card,
the two acceptance reports, P3-03/P3-04 acceptance status and P3-05 readiness.
Acceptance: both submissions are ancestors; combined tests and static/frontend
checks pass; generated files and eight historical compatibility hashes are unchanged;
independent Gate 2 passes; main advances without force or history rewriting.

## Handoff

### What changed

Two conflict-free merge commits combine the reviewed submissions. Code candidate
`93f95420c5a856b05d68bea277a08b04b0f984e4` contains their exact union. The shared
ports and foundation handoff overlap identically; no manual conflict resolution
or implementation edits were needed. The acceptance reports close P303-A1 and
P304-A1, and the task cards record acceptance and P3-05 dependency readiness.
Earlier executor handoff statuses remain historical evidence.

### Commands and results

Validation uses the existing P3-03 Python dependency environment with PYTHONPATH
pointing to this integration checkout. Frontend dependencies were installed from
the existing cache with `pnpm --dir frontend install --frozen-lockfile --offline`.

- Full backend: `python -m pytest --basetemp ../runs/p30304-integration-full1 -q`
  from backend: exit 0, **1473 passed, 3 skipped in 479.80 seconds**. The three
  existing dev-run cases require explicit opt-in and remain normal skips.
- Ruff check and format: exit 0; 154 files formatted.
- Mypy: exit 0, 88 source files; import-linter: exit 0, all eight contracts kept.
- Frontend lint, typecheck and build: exit 0 each.
- `python scripts/gen_types.py` and generated-file diff: exit 0; no changes.
- Historical compatibility: all eight fresh P1/P2 events, decisions, final-world
  and replay hashes match plan section 3.2. P1 artifacts came from the full-suite
  `test_default_1008_tick_cli_run0/first` run. P2 used `python -m living_island run
  --config content/worlds/default.toml --policy rule-based --seed 2600456787
  --ticks 1008 --checkpoint-every 144 --out runs/p30304-integration-p2`, followed
  by `reexecute --source-run runs/p30304-integration-p2 --out
  runs/p30304-integration-p2-recorded --export-replay`; both exited 0. P2 retained
  14351 events and 1305 decisions; recorded streams are byte-identical to source.
  Final replay SHA-256:
  `720bccc76cb1c3baff78a74bec7703e76764be777713b43df6e30d297f9d36e8`.
- All frozen spec/ADR/product, world, memory, frontend, content and dependency
  paths remain unchanged against the integration baseline. All 22 local document
  link targets exist; whitespace checks pass.
- Independent Gate 2: PASS from `/root/p30304_integration_gate2`. The reviewer
  verified the exact union of reviewed trees, unchanged rule source, shared
  exception identity, 29 actual-module fallback regressions and the final
  documentation. Its sole remaining condition was the P2 replay hash match,
  now verified above. The reviewer authored no integration changes.

### Deviations

No implementation scope deviation. The sandbox cannot open the existing pnpm
store lock; the same install/check/generation commands succeeded with reviewed
filesystem permissions. No dependency version was changed or downloaded.

### Open questions

No implementation finding. P3-05 owns live registration, mutable model/version/
pricing revalidation and the one-resident M9 demonstration. The approved overall
API cap remains CNY150; this integration spends zero and does not launch P3-05.

### Required fields

1. base_commit: `982988ab9b87856dd62fe4cced426971b33b22df`;
   result_commit: `93f95420c5a856b05d68bea277a08b04b0f984e4` (combined code;
   a subsequent documentation commit records completed validation).
2. status: ACCEPTED; Gate 1 and independent Gate 2 PASS, owner authorized main merge.
3. scope_changed: no; the owner explicitly authorized integration into main.
4. human_interventions: zero additional interventions after the integration request.
5. rework_rounds: zero; both branches merged without conflicts or new code changes.
6. verification: results above; live API, credentials and P3-05 NOT_RUN.
7. open_questions: none blocking integration; P3-05 remains separate and unstarted.
