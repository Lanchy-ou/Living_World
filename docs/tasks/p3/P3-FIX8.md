# Task P3-FIX8: Generate discriminated replay event types

## Brief

```text
Task ID / title: P3-FIX8 / Generate discriminated replay event types
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8
Goal / non-goals: Generate the replay TypeScript event-to-payload relationship from the Python mapping. Preserve the wire JSON, runtime validation, and JSON Schema.
Lane / depends on: P3 architecture review R8. Starts at dcef8bb4d0e7f573a751c5767000059754d6d585 with independently reviewed FIX6 integrated.
Allowed files / forbidden dependencies: scripts/gen_types.py, formally regenerated frontend/src/api/generated outputs, eventView.ts, corresponding generator and frontend type tests, and this card. Frozen contracts and other consumers are outside the task.
Deliverables: Generated discriminated WorldEvent, typed event display, backend mapping regression test, and frontend narrowing and pairing type checks.
Acceptance (positive, negative, edge, determinism): A resident_moved event narrows to its coordinate payload. Invalid accesses and type/payload pairings are rejected. All existing replay fixtures pass, and repeated formal generation is byte-stable.
Verification commands: See the Gate 1 results below.
Open risks / deferred decisions: The FIX5 project configuration change will include the type fixture in the default frontend typecheck on the integration branch.
```

## Handoff

### What changed

- The formal generator refines the schema-derived replay TypeScript into a discriminated `WorldEvent` using `PAYLOAD_MODEL_BY_TYPE` from `world/facts.py`. It retains the generated envelope and payload field types. The two JSON schemas and the legacy contract TypeScript have identical content to the task base.
- `eventView.ts` reads narrowed payloads for summaries and failure codes. Resident matching still uses the replay viewer's configured reference fields, typed as optional string properties on the payload.
- The backend regression test compares all 25 generated event/payload pairs to their canonical Python models. The frontend type fixture checks narrowing from a replay bundle event, wrong payload fields, and mismatched discriminator/payload pairs.
- Implementer configuration used `gpt-6.1-sol`, reasoning effort `high`. Independent reviewer configuration, verdict, and any retest are `NOT_RUN` pending Gate 2. The requested reviewer profile is Astra / High.

### Commands and results

| Command | Exit | Result |
| --- | ---: | --- |
| `uv sync --directory backend --locked` | 0 | Locked backend dependencies installed |
| `pnpm --dir frontend install --frozen-lockfile` | 0 | Locked frontend dependencies installed |
| `uv run --directory backend ruff check . ../scripts/gen_types.py` | 0 | All checks passed |
| `uv run --directory backend ruff format --check . ../scripts/gen_types.py` | 0 | 160 files already formatted |
| `uv run --directory backend mypy src` | 0 | 88 source files checked |
| `uv run --directory backend lint-imports --no-cache` | 0 | 8 contracts kept, 0 broken |
| `uv run --directory backend pytest tests/unit/test_replay_contract.py --basetemp D:\t8-bc066348` | 0 | 90 passed, 0 skipped, including the shared replay fixtures |
| `pnpm --dir frontend lint` | 0 | Passed after correcting a bare expression in the type fixture |
| `pnpm --dir frontend typecheck` | 0 | Application project passed |
| `pnpm --dir frontend exec tsc --ignoreConfig --noEmit --strict --target ES2022 --module ESNext --moduleResolution bundler --allowImportingTsExtensions --verbatimModuleSyntax --noUnusedLocals --noUnusedParameters tests/worldEvent.typecheck.ts` | 0 | The standalone type fixture compiled with its three expected errors |
| `pnpm --dir frontend build` | 0 | Production build passed |
| `pnpm --dir frontend run test:schema` | 0 | 17 checks passed |
| `pnpm --dir frontend run test` | 0 | 151 passed, 0 failed, 0 skipped, including the shared replay fixtures |
| `uv run --directory backend python ../scripts/gen_types.py` | 0 | Successive generation produced identical SHA-256 hashes for all four generated files |
| `uv run --directory backend python ../scripts/gen_types.py` then `git diff --exit-code` | 0 / 0 | Regeneration after the implementation commit left a clean worktree |

### Deviations

None. The type fixture ran through standalone `tsc` on this task branch. FIX5 supplies default project inclusion for `tests/**/*.typecheck.ts` on the integration branch. Full backend pytest, integrated project typecheck, independent Gate 2, and GitHub Actions are `NOT_RUN` here. The first two belong to final integration verification.

### Open questions

None.

### Required fields

1. `base_commit`: `dcef8bb4d0e7f573a751c5767000059754d6d585`. `result_commit`: `fceb5b755fa66a61d4fdcc47a01bf804fa9bf76b`.
2. `status`: `ACCEPTED`. Gate 1 passed. Gate 2 verdict and retest `NOT_RUN`.
3. `scope_changed`: no.
4. `human_interventions`: 0.
5. `rework_rounds`: 0 independent-review rounds. Gate 1 caught and corrected the type fixture lint issue before handoff.
6. `verification`: see the commands and results above, including `NOT_RUN` items under Deviations.
7. `open_questions`: none.

### Independent Gate 2

PASS on `1b2f2fb0a7938d5c57c7c436f9198bfd4e1440d0`, implementation `fceb5b755fa66a61d4fdcc47a01bf804fa9bf76b`. Reviewer explicitly assigned GPT-6 Astra / High, separate from the author. Reviewed full diff, canonical mapping, generator, display behavior, interface/replay specifications and actual tests. All 25 event/payload pairs derive from PAYLOAD_MODEL_BY_TYPE. JSON schemas and legacy contract.ts are unchanged. No findings or rework.

Independent commands all exited 0: replay-contract pytest with fresh `D:/t8r-4a71e5` (90 passed, no skips), Ruff lint/format including the generator (160 files), mypy (88 files), import-linter (8 kept), frontend lint/typecheck/build, schema smoke (17 checks), frontend tests (151 passed, no skips), and standalone strict type fixture check. An in-memory suppression-removal probe produced exactly two TS2339 errors and one TS2322 error. Two formal generator runs produced identical hashes; git diff --exit-code and final clean status passed. Initial cache-lock errors were resolved by authorized retries; Git used per-command safe.directory.

Full backend and GitHub Actions were NOT_RUN by reviewer. Integration must verify FIX5's type-fixture inclusion and combined readonly/discriminated types; see P3-architecture-fixes.md for final results.
