# P3-CI1: Fetch full history in the backend CI job

## Brief

- Baseline: `8d5b44e65df42abec0fc738f66dc7a2bb6a05123`.
- Source: architecture review of `8d5b44e` (2026-11-14), finding 1 (P0), fix task R1.
- Goal: make the backend CI job able to read the frozen content that P3
  registrations pin to historical commits (for example `WORLD_COMMIT` in
  `scripts/p3_trials.py`), so the full backend suite can pass in CI again.
- Non-goals: no change to source, tests, fixtures, pins or other CI jobs.
- Allowed files: `.github/workflows/ci.yml` (backend job checkout step) and
  this card.
- Acceptance: with the fix, a checkout equivalent to CI passes the full
  backend suite; without it, the known P3 failures reproduce.
- Verification: full backend `pytest` in a shallow clone (current CI) and in
  a full-history clone (CI after the fix).
- Deferred: confirming on a real GitHub Actions run, which needs a push.

## Handoff

### What changed

The backend job's `actions/checkout@v4` step now sets `fetch-depth: 0`. The
action's default depth of 1 leaves out the pinned historical commits. P3 then
fails with `PersistenceError: pinned revision/blob is unavailable` in
`git_source_reader` (`persistence/p3.py`). All pinned commits found in
`scripts/p3_trials.py`, `backend/src` and the test fixtures (`7c13d78`,
`4a66f9b`, `506cfaf`, `eac4d29`) are ancestors of `main`, so a full-history
checkout contains them. The frontend and contract jobs are unchanged.

### Commands and results

Both clones were made from local `main` at `8d5b44e`. The source is identical
to this branch; only the workflow differs.

| Clone | Command | Result |
|---|---|---|
| `git clone --depth 1` (current CI) | `uv run --directory backend pytest --basetemp <scratch>` | 21 failed, 1655 passed, 24 skipped, 8 errors. All 29 are in `tests/p3/test_trial_registration.py` (20 + 8) and `tests/p3/test_one_resident.py` (1). The counts match the review and the GitHub CI log. |
| full-history clone (CI after fix) | same | 6 failed, 1678 passed, 24 skipped. The 6 failures are `Filename too long` from Windows `MAX_PATH` in deeply nested temp repositories, not missing objects. |
| full-history clone, `core.longpaths=true` | `pytest tests/p3/test_trial_registration.py tests/p3/test_one_resident.py` | 53 passed |

Result: with full history, all 1684 collected backend tests pass or skip as
designed. The ruff, mypy and lint-imports steps are unaffected because no
Python file changed.

### Deviations

- The review called this task `R1`. It is filed as `P3-CI1` because `P305-R1`
  already exists.
- `--basetemp` pointed into a scratch directory, because the default
  `%TEMP%\pytest-of-<user>` on the executor machine has a broken ACL
  (`PermissionError: [WinError 5]`). This affects only that machine.

### Open questions

- Windows contributors running the P3 registration tests from a deep path
  need `git config core.longpaths true`. CI (ubuntu) is not affected. A note
  in the setup docs could go into the review's R7 (README/AGENTS entry) task.

### Required fields

1. `base_commit` / `result_commit`: `8d5b44e65df42abec0fc738f66dc7a2bb6a05123` / unknown (set at merge)
2. `status`: `READY_FOR_REVIEW`
3. `scope_changed`: no
4. `human_interventions`: 0
5. `rework_rounds`: 0
6. `verification`: shallow-clone pytest exit 1 (21 failed, 8 errors); full-history pytest 1678 passed plus 6 path-length failures, which then passed 53/53 with `core.longpaths`; GitHub Actions run `NOT_RUN` (needs push)
7. `open_questions`: Windows `core.longpaths` note (see above)
