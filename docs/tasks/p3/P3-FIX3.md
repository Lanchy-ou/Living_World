# P3-FIX3: Coordinate replay loading

## Brief

```text
Task ID / title: P3-FIX3 / Coordinate replay loading
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8
Goal / non-goals: Make the last load request authoritative and report unreadable replay files. Preserve validation, replay data and the existing playback on load failures.
Lane / depends on: Frontend architecture fixes / verified R1 baseline.
Allowed files / forbidden dependencies: App.tsx, loader.ts, loadCoordinator.ts, loading error types, frontend tests, and this card. The owner also authorized ErrorDetails.tsx for file-read copy. No DOM test framework.
Deliverables: Shared load coordinator, explicit file-read error, and deterministic regression tests.
Acceptance (positive, negative, edge, determinism): File selections can complete out of order. Example invalidates an older file request. A current read failure reports the file name and leaves the loaded replay intact. Neither stale successes nor stale failures are applied.
Verification commands: Locked frontend install, lint, typecheck, build, schema smoke test, focused load tests, full frontend tests, and Git whitespace checks.
Open risks / deferred decisions: None.
```

## Handoff

### What changed

- File selection, drag-and-drop and Example now submit through one coordinator. It increments the request ID before starting each load and applies only the current request's result.
- A failed file read becomes a `file_read` error in the existing stage alert. The error path leaves the replay store untouched, including the current tick.
- Five Node tests use controllable read promises and real validated replay fixtures. They cover out-of-order file completion, Example invalidation, an active read failure, and stale results after both success and failure.

### Commands and results

| Command | Exit | Evidence |
| --- | --- | --- |
| `pnpm --dir frontend install --frozen-lockfile` | 0 | 173 locked packages, pnpm 10.34.9 |
| `node --test frontend/tests/replay-loading.test.mjs` | 0 | 5 passed, 0 failed, 0 skipped |
| `pnpm --dir frontend lint` | 0 | ESLint passed |
| `pnpm --dir frontend typecheck` | 0 | TypeScript project checks passed |
| `pnpm --dir frontend build` | 0 | Vite built 149 modules |
| `pnpm --dir frontend run test:schema` | 0 | 17 checks passed |
| `pnpm --dir frontend run test` | 0 | 148 passed, 0 failed, 0 skipped |
| `git -c safe.directory=D:/Codex/.codex/worktrees/p3-fix3-replay-loading/Living_World -c core.longpaths=true diff --cached --check` | 0 | Implementation diff passed |
| Backend checks and type generation | NOT_RUN | Deferred to the final integration verification |
| GitHub Actions | NOT_RUN | Task branch is local |

### Deviations

The owner approved the narrow addition of `frontend/src/debug/ErrorDetails.tsx` on 2026-11-15. This lets the existing alert give file-read failures their own title, accessibility label and recovery hint.

### Open questions

None.

### Required fields

1. `base_commit` / `result_commit`: `ea27c67f326700e71a44c805ed6ca3a97c3d19f8` / `f7917621d95a08648eabc4f2e73b9ea9b5525446` (implementation and tests).
2. `status`: `READY_FOR_REVIEW`. Gate 1 passed. Implementer used GPT-6.1 Sol / High. Independent Gate 2 is pending, including the reviewer configuration, outcome and any recheck.
3. `scope_changed`: yes, approved by the project owner for the error view only.
4. `human_interventions`: 1, the project owner approved the error-view scope extension.
5. `rework_rounds`: 0 at initial handoff.
6. `verification`: see the commands and results above.
7. `open_questions`: none.
