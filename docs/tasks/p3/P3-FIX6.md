# Task P3-FIX6: Replay event pagination

## Brief

```text
Task ID / title: P3-FIX6 / Replay event pagination
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8
Goal / non-goals: Make every filtered event reachable, including crowded single ticks,
  without changing replay data, event ordering, filtering, or select-to-seek behavior.
Lane / depends on: Frontend / unified baseline after the R1 fix.
Allowed files / forbidden dependencies: EventList.tsx, one small pagination helper,
  frontend pagination tests, and this task card. No virtual list dependency.
Deliverables: Previous/Next controls, tick-aware page bounds, regression tests.
Acceptance (positive, negative, edge, determinism): All 201 validated tick-zero events
  appear across two pages in original order. Empty filters and page bounds are handled.
  Filtering and selecting an event on a later page preserve the existing replay behavior.
Verification commands: Frontend install --frozen-lockfile, lint, typecheck, build, schema
  smoke test and frontend suite, with targeted Node tests for the pagination regression.
Open risks / deferred decisions: No open specification questions.
```

## Handoff

### What changed

The event list displays up to 150 filtered events per page in replay order. Previous and
Next are disabled at their respective bounds. A tick, filter, or replay change clears any
manual page choice and opens the page containing the first match at or after the current
tick. When all matches precede that tick, it opens the last page. Selection at the same
tick preserves the page. An event click still uses the store's selection and seek command
and displays the selected event's raw JSON.

The regression tests validate a frame-zero-only replay with 201 events before asserting
page coverage and bounds. They also cover both filters, an empty result, and store selection
and seek from a later page.

### Commands and results

| Command | Exit | Result |
| --- | ---: | --- |
| `pnpm --dir frontend install --frozen-lockfile` | 0 | Locked pnpm 10.34.9 installed 173 packages from the local store. |
| `node --test frontend/tests/event-pagination.test.mjs` | 0 | 3 passed, 0 skipped. |
| `pnpm --dir frontend lint` | 0 | ESLint passed. |
| `pnpm --dir frontend typecheck` | 0 | TypeScript passed. |
| `pnpm --dir frontend build` | 0 | Production build passed. |
| `pnpm --dir frontend run test:schema` | 0 | 17 checks passed. |
| `pnpm --dir frontend run test` | 0 | 146 passed, 0 skipped. |
| `git diff --cached --check` | 0 | Staged implementation passed whitespace validation. |

Backend lint, format, mypy, import checks and pytest, contract regeneration and its clean
diff are NOT_RUN here and scheduled for the final integration checks. GitHub Actions
are NOT_RUN for this unpushed branch. Manual browser checks are NOT_RUN at Gate 1.

### Deviations

Initial sandboxed pnpm commands exited 1 before execution because the Windows pnpm store
lock was outside the sandbox. All frontend checks above passed with access to that lock.
No dependency or project configuration changed.

### Open questions

None.

### Required fields

1. `base_commit` / `result_commit`: `ea27c67f326700e71a44c805ed6ca3a97c3d19f8` /
   `7fb1d4fedd7e92abffe736dc43c184f9d600a0ab` (implementation and tests).
2. `status`: `READY_FOR_REVIEW`. Implementer gpt-6.1-sol / Medium. Gate 2 pending,
   reviewer configuration and reproduction results NOT_RUN at this handoff.
3. `scope_changed`: No.
4. `human_interventions`: 0.
5. `rework_rounds`: 0.
6. `verification`: Gate 1 task checks passed. See command table and NOT_RUN entries.
7. `open_questions`: None.
