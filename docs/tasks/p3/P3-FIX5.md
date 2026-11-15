# Task P3-FIX5: Read-only replay store and bundle ownership

## Brief

```text
Task ID / title: P3-FIX5 / Read-only replay store and bundle ownership
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8
Goal / non-goals: Publish read-only state and give the store exclusive ownership of its replay snapshot. Keep playback, selection, camera and recorded motion semantics.
Lane / depends on: Frontend replay store / reviewed FIX3 integrated at b3fe49abfa28379e832d65e2be3c13dcf8205fa3.
Allowed files / forbidden dependencies: Replay types and store, motion, required consumer type signatures, corresponding frontend tests and this card. The owner authorized narrowly scoped typecheck configuration. Frozen specifications and the generated contract are outside this task's scope.
Deliverables: Deeply read-only state and replay data, independent initial cameras, one-time replay isolation on load and runtime and compile-time regression coverage.
Acceptance (positive, negative, edge, determinism): Existing playback, selection, camera and motion tests pass. Typecheck rejects direct state writes. Mutating the caller's replay leaves the loaded copy intact. Motion keeps stable cache identity across playback and sees fresh data on reload.
Verification commands: Locked frontend install, lint, typecheck, production build, schema smoke checks, frontend tests and git diff --check.
Open risks / deferred decisions: The first load of each replay takes one clone and one freeze traversal of its JSON data.
```

## Handoff

### What changed

- `ReplayStore.load()` takes a `structuredClone()` of the validated input and recursively freezes the clone. The caller can continue editing its own input. The store exposes the same owned replay object throughout playback and camera, filter and selection updates. A new load provides a new key to the motion cache.
- `getState()` exposes a deeply read-only snapshot. A new state starts with a fresh camera and filters. Store commands replace the snapshot and freeze new camera and filter values. Playback touches only the fixed-size state object.
- Reader types are derived from the generated replay types. The validator still returns the writable wire shape. Scene grouping and resident lookup accept read-only collections.
- Three runtime tests exercise camera isolation, original input aliasing, frozen snapshots and motion across playback and reload. A TypeScript fixture checks seven forbidden writes, including writes through a frame helper and into an event payload.

### Commands and results

| Command | Exit | Result |
| --- | --- | --- |
| `pnpm --dir frontend install --frozen-lockfile` | 0 | Locked install completed with pnpm 10.34.9 and Node 24.15.0. The initial sandboxed invocation exited 1 because access to pnpm's store lock was denied. |
| `pnpm --dir frontend lint` | 0 | Passed. |
| `pnpm --dir frontend typecheck` | 0 | Passed with all seven expected-error assertions active. |
| `pnpm --dir frontend exec tsc --project tsconfig.app.json --listFilesOnly` | 0 | The compiler listed `tests/replay-store.typecheck.ts`. |
| `pnpm --dir frontend build` | 0 | TypeScript and Vite built the viewer. |
| `pnpm --dir frontend run test:schema` | 0 | 17 smoke checks passed. |
| `pnpm --dir frontend run test` | 0 | 151 passed, 0 failed, 0 skipped. |
| `git diff --check` and `git diff --cached --check` | 0 | Passed. |
| Backend checks, contract regeneration | `NOT_RUN` | Scheduled for final integration verification. |
| Manual browser checks and GitHub Actions | `NOT_RUN` | The task was verified locally with the automated frontend checks above. |

### Deviations

The owner authorized the `frontend/tsconfig.app.json` inclusion of `tests/**/*.typecheck.ts` on 2026-11-15. The validator import and the two read-only collection parameter changes are consumer type changes within the existing allowance.

### Open questions

None.

### Required fields

1. `base_commit` / `result_commit`: `b3fe49abfa28379e832d65e2be3c13dcf8205fa3` / `bd05220736751ae06993a0547927bb8165787240` (implementation and tests).
2. `status`: `ACCEPTED`. Implementer GPT-6.1 Sol / High. Independent Gate 2 passed with GPT-6 Astra / High; evidence follows below.
3. `scope_changed`: Yes. The owner authorized the narrow TypeScript test configuration change on 2026-11-15.
4. `human_interventions`: 1. Owner authorization for the TypeScript test configuration change.
5. `rework_rounds`: 0. No reviewer-requested changes yet.
6. `verification`: Gate 1 passed. See commands, exit codes, counts and `NOT_RUN` entries above.
7. `open_questions`: None.

### Independent Gate 2

PASS on `8130177b8d4fb1c85ea7be4d85986264f336827b`, implementation `bd05220736751ae06993a0547927bb8165787240`. Reviewer explicitly assigned GPT-6 Astra / High, separate from the author. Verified accepted FIX3 ancestry, authorized scope, deep readonly public types, distinct cameras, caller-input isolation, recursive runtime freezing and stable motion-cache identity. No blocking findings or code rework. The author handoff's type-test count was corrected from six to seven by the lead.

Independent pnpm frontend test (151 passed, no skips), test:schema (17 checks), lint, typecheck and build all exited 0. `pnpm --dir frontend exec tsc --project tsconfig.app.json --noEmit --listFiles` confirmed fixture inclusion. An in-memory compiler-host probe removed the suppressions and observed seven genuine readonly errors. A runtime probe verified 483 frozen-object visits, patch isolation, old snapshots, follow behavior and exactly one structuredClone per load with none during playback. Whitespace check passed and reviewed worktree was clean. Initial pnpm sandbox engine-lock errors were resolved by authorized escalated reruns. Backend, generation, browser/manual and GitHub Actions were NOT_RUN by this reviewer; final integration verification follows in P3-architecture-fixes.md.
