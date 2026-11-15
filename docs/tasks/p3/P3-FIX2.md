# Task P3-FIX2: Legacy boundary isolation and restored plan validation

## Brief

```text
Task ID / title: P3-FIX2 / Legacy boundary isolation and restored plan validation
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8
Goal / non-goals: Isolate returned commits; reject modified queued/active legacy plans
  before resume output or simulation advancement. Preserve formats and normal results.
Lane / depends on: First architecture-fix batch; merged P3-CI1 and successful CI verified
  by the lead before assigning this unified baseline.
Allowed files / forbidden dependencies: sim/boundary.py, persistence/resume.py,
  corresponding backend unit/invariant tests, and this task card only. No frozen
  specs, generated files, APIs, secrets, live trial authorization, or P3-06 work.
Deliverables: Implementation, regression tests, reviewable branch, this handoff.
Acceptance (positive, negative, edge, determinism): Nested returned state mutation
  cannot affect subsequent boundaries. Queue identity and complete remaining suffix,
  active intent identity and progress must agree with committed records/events.
  Legal active, exhausted, failed, interrupted, dead and deferred-trigger states
  resume unchanged; P1 CLI flow and historical reference hashes remain identical.
Verification commands: Scoped pytest, backend ruff/format/mypy/import-linter,
  P1 reference integration and artifact hashing. Full final CI matrix is lead-owned.
Open risks / deferred decisions: Independent Gate 2 pending; no specification changes.
```

## Handoff

Implementation configuration: Astra / High (`gpt-6-astra`, high), as assigned by
the lead. Independent reviewer configuration: pending assignment; requested
Astra / High. The implementer has not performed Gate 2.

Branch: `task/P3-FIX2-boundary-resume`.
Worktree: `D:/Codex/.codex/worktrees/p3-fix2-boundary-resume/Living_World`.

### What changed

- `BoundaryLoop.boundary` and `advance()` return deep copies of the internal commit.
  Tests mutate nested snapshot collections and pending perceptions, then compare
  six subsequent commits, decisions and checkpoints with an untouched control.
- Legacy resume derives each actor's most recent committed plan and its started
  prefix from the verified decision/event history. The checkpoint must contain
  exactly the complete unstarted suffix, including its original plan identity and
  creation tick. Missing, truncated, duplicated, consumed or superseded queues fail.
- An unfinished started intent must equal the saved active intent. Its start tick,
  elapsed ticks, remaining ticks and route cursor must agree with the current
  boundary's progress event. Completed or unstarted intents cannot become active.
  Missing or unexpected active actions fail as well.
- Validation occurs during ancestry verification before a continuation staging
  directory is created. The same checks apply to parent checkpoints.
- Legacy scheduling does not decide while an action is active, so its latest
  decision is the relevant plan. Deferred triggers leave the suffix intact until
  idle scheduling, whereas failure/interruption/death discard it at the completed
  boundary. Tests explicitly preserve all of those distinctions, including a
  multi-tick invalid attempt with a pending failure.

### Commands and results

Commands run from the task worktree unless otherwise stated. Exit codes refer to
the named command, not a following shell command. No tests were newly skipped.

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --directory backend --locked` | 0 | 26 locked packages installed; Python 3.13.5. Initial sandbox attempt exited 1 on the uv cache lock; authorized elevated retry succeeded. |
| `uv run --directory backend pytest tests/unit/test_sim_boundaries.py tests/unit/test_legacy_resume_progress.py tests/unit/test_sim_runs.py tests/unit/test_p1_integration.py --basetemp D:/f2-c-1115` | 0 | 59 passed in 260.29 s; no skips. Includes the 1008-tick mechanics and original P1 CLI/replay integrations. |
| `uv run --directory backend pytest tests/unit/test_legacy_resume_progress.py tests/unit/test_sim_boundaries.py --basetemp D:/f2-d-1115` | 0 | 33 passed in 4.74 s; no skips. Includes three compatibility cases added after the longer suite started; 62 distinct cases across the two successful runs. |
| `uv run --directory backend ruff check .` | 0 | All checks passed. |
| `uv run --directory backend ruff format --check .` | 0 | 160 files already formatted. |
| `uv run --directory backend mypy src` | 0 | 88 source files clean. |
| `uv run --directory backend lint-imports --no-cache` | 0 | 8 contracts kept, 0 broken; 124 files and 565 dependencies analyzed. |
| `git -c safe.directory=<worktree> diff --check` | 0 | Clean whitespace. |

Earlier unsuccessful validation attempts are retained as part of the evidence:

- The first targeted pytest invocation (`--basetemp D:/tmp/f2-a-1115`) exited 1
  during collection: the new test imported `PersistenceError` from a package that
  does not re-export it. The import was corrected to `persistence._codec`.
- The next invocation (`--basetemp D:/tmp/f2-b-1115`) exited 1 with 10 passed and
  49 setup errors because `D:/tmp` did not exist. A fresh short path directly below
  `D:/` fixed the environment issue. No existing temporary directory was reused or
  deleted.
- Initial scoped lint reported import ordering and long-line formatting; the
  formatter fixed them. After the three additional tests, format checking exited 1
  for one wrapping difference; formatting and the final check succeeded.

The P1 integration's completed artifacts remain at
`D:/f2-c-1115/test_default_1008_tick_cli_run0`. A read-only Python command using
`hashlib.sha256`, `json.loads`, and `canonical_json_bytes` hashed `first`'s final
checkpoint world and `replay.json` (exit 0). Both match P3 plan section 3.2 exactly:

| Artifact | SHA-256 |
| --- | --- |
| Canonical final WorldState | `113483069d74936a3fa5ecf0f719405dc7499698fc851cdc4b992a84e25357ed` |
| `replay.json` bytes | `8e26d853b6bf324fa4a375f0edfca526c09754b78d7eaee9b96c615464dbfb83` |

The integration also asserted original/reexecuted replay byte equality and
uninterrupted/resumed final checkpoint and event/decision stream equality.

NOT_RUN for this isolated task: full backend pytest/invariant matrix, frontend
lint/typecheck/build/test:schema/test, type generation and generated-diff check.
These are assigned to the lead's final integration validation. GitHub Actions:
NOT_RUN for this task because nothing has been pushed. Baseline CI success is
a prerequisite checked by the lead, not evidence of this task's cloud CI status.

### Deviations

No scope or format changes. Windows Git branch creation initially required an
authorized elevated retry for the shared repository ref lock; Git used per-command
`safe.directory`. No global Git settings changed. These targeted tests do not
create nested Git repositories, so `core.longpaths` was not needed here.

No real API calls, secret reads, trial authorizations, pushes, merges into main,
or file/worktree deletions occurred. All failed-run evidence remains untouched.

### Open questions

None. The frozen legacy scheduling semantics support latest-plan ownership;
there was no need to copy P3 behavior where it differs or request a spec change.
Gate 2 remains pending; the lead will append its independent conclusion and any
reverification evidence.

### Required fields

1. `base_commit` / `result_commit`: `ea27c67f326700e71a44c805ed6ca3a97c3d19f8` /
   `d20378b19db31029141bf8b745addf5b60383e5d` (implementation and tests; this card
   is recorded in a following documentation commit).
2. `status`: `READY_FOR_REVIEW`; scoped Gate 1 passed; Gate 2 pending.
3. `scope_changed`: no.
4. `human_interventions`: 0; existing task authorization covered worktree,
   dependency installation and Git operations.
5. `rework_rounds`: 0 independent-review rounds; executor test setup/format
   corrections are documented above.
6. `verification`: commands, exit codes, counts and NOT_RUN items above; full
   combined CI verification belongs to the lead's final integration handoff.
7. `open_questions`: none; no frozen-spec edits requested.
