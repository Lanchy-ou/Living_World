# Task P3-FIX9: Exhaustive action dispatch

## Brief

```text
Task ID / title: P3-FIX9 / Exhaustive action dispatch
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8
Goal / non-goals: Require an explicit dispatch decision in validation and settlement
  for every ActionType. Preserve existing actions, world rules and results.
Lane / depends on: Backend world / R1 accepted on main, no other architecture fix.
Allowed files / forbidden dependencies: world/actions.py, its focused action tests and
  this card. World Rules §4–5, Interface Contract §2.4 and module boundaries remain binding.
Deliverables: Explicit cases for actions handled elsewhere or requiring no direct effect,
  exhaustiveness guards, and a regression test for unhandled action types.
Acceptance (positive, negative, edge, determinism): Preserve existing action behavior
  and engine invariants. Adding a literal to ActionType without either dispatch case
  must fail mypy. Check the P1 long-replay reference hash on the integration branch.
Verification commands: See Handoff.
Open risks / deferred decisions: None.
```

## Handoff

### What changed

Both dispatch functions enumerate `move_to`, `rest`, `sleep`, `talk` and `wait`
as having no additional action-specific validation or direct settlement in this
module. Shared validation still runs first. The engine owns movement and dialogue
checks, progress applies movement and rest or sleep recovery, the engine settles
dialogue, and wait has no direct effect. Both functions end their action dispatch
with `typing.assert_never`, which mypy checks against the narrowed action type.

The regression test bypasses intent shape validation to verify both runtime guards.
To check the static contract independently, a temporary mypy shadow file added
`"unhandled_action"` to the existing `ActionType` declaration. The checked-in
protocol, action vocabulary and fixtures were untouched during the probe.

### Commands and results

| Command | Exit | Result |
| --- | ---: | --- |
| `uv sync --directory backend --locked --offline` | 0 | Installed 26 locked packages with Python 3.13.5. |
| `uv run --directory backend --locked --offline ruff check .` | 0 | Passed. |
| `uv run --directory backend --locked --offline ruff format --check .` | 0 | 159 files already formatted. Concurrent Ruff invocations emitted cache-write warnings. |
| `uv run --directory backend --locked --offline ruff format --no-cache --check .` | 0 | 159 files already formatted, with no warnings. |
| `uv run --directory backend --locked --offline mypy src` | 0 | No issues in 88 source files. |
| `uv run --directory backend --locked --offline lint-imports --no-cache` | 0 | 8 contracts kept, 0 broken. |
| `uv run --directory backend --locked --offline pytest --basetemp "$env:TEMP\lw-f9-c8710" tests/unit/test_engine_actions.py tests/invariants` | 0 | 37 passed (11 action tests and 26 invariant tests), 0 skipped. |
| `python -m mypy --no-incremental --shadow-file src/living_island/world/protocol.py "$env:TEMP\lw-f9-mypy-c7qliaq6\protocol.py" src/living_island/world/actions.py` from the backend directory, using its locked virtual environment | 1 (expected) | 2 errors in 1 source file. Each `assert_never` flagged `Literal['unhandled_action']` as incompatible with `Never`. The probe asserted both diagnostics and exited 0. |
| `git diff --check` | 0 | Passed. |

The full backend suite, P1 long-replay reference hash and replay bytes, frontend lint,
typecheck, build, schema and unit tests, and contract generation and clean diff are
`NOT_RUN` in this worktree and deferred to final integration validation. GitHub
Actions is `NOT_RUN` for the local task branch.

### Deviations

None. Implementation used GPT-6.1 Sol / High. Independent Gate 2 review and any
re-review are pending, with Astra / High requested. The reviewer's actual
configuration will be recorded with the review.

### Open questions

None.

### Required fields

1. `base_commit` / `result_commit`: `ea27c67f326700e71a44c805ed6ca3a97c3d19f8` /
   `fa531084fa2374ab0076172781a0f40589061c01` (implementation before this handoff).
2. `status`: `READY_FOR_REVIEW`.
3. `scope_changed`: no.
4. `human_interventions`: 0.
5. `rework_rounds`: 0.
6. `verification`: Targeted Gate 1 checks and expected mutation failure above.
   Final integration and independent Gate 2 are `NOT_RUN` here.
7. `open_questions`: none.
