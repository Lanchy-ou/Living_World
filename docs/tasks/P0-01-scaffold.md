# Task P0-01: Repository scaffold

## Brief

Create the repository skeleton for Living Island (self-running 2D island simulation with
LLM-driven residents). Do NOT implement any game logic.

Fixed decisions: monorepo at the repo root; backend Python 3.13 + `uv`, src layout, package
`living_island`; frontend Vite + React + strict TypeScript + ESLint + `pnpm`; contract =
pydantic models -> JSON Schema -> `json-schema-to-typescript` -> TS types (no FastAPI);
storage later = JSON snapshots + JSONL (no database); English for code/comments/docs;
all scripts cross-platform (Python or package.json scripts).

Requirements (summary of the original brief):

1. Git: `git init` on `main`; `.gitattributes` (`* text=auto eol=lf` + binary image rules);
   `.gitignore` (Python, Node, `.venv`, `runs/*` keeping `.gitkeep`, `.env`); `.env.example`.
2. Backend: runtime dep `pydantic` only; dev deps `pytest`, `hypothesis`, `ruff`, `mypy`
   (strict), `import-linter`; `world/protocol.py` placeholders; `contract/` placeholder model
   `SnapshotMeta(schema_version, tick)`; one smoke test importing every subpackage;
   import-linter contracts enforced in CI:
   1. `world` imports no other `living_island` subpackage and none of `anthropic`, `openai`,
      `httpx`, `requests`, `fastapi`;
   2. `agents` and `memory` import from `world` only via `world.protocol`;
   3. `events` narrative code must not import `sim` or `persistence` write paths.
3. Frontend: Vite React TS, `strict: true`, ESLint, minimal `App` drawing a placeholder grid
   on a Canvas; `src/api/generated/` generated-only with a "do not edit" README.
4. Type generation: `scripts/gen_types.py` exports JSON Schema into
   `frontend/src/api/generated/` then runs the pnpm script producing `contract.ts`; output
   is committed.
5. CI: backend ruff, mypy, import-linter, pytest; frontend install, lint, typecheck, build;
   contract: regenerate then `git diff --exit-code`.
6. `AGENTS.md` (< ~150 lines) with Project, Source of truth order, Core principles, Module
   boundaries, Commands, Workflow rules, Definition of done; `CLAUDE.md` is one line
   `@AGENTS.md`.
7. Spec skeletons (headings + one-line descriptions, no content, no numbers):
   `world-rules-v0.1.md`, `interface-contract.md`; plus `open-questions.md`.
8. ADR 0001: monorepo layout, module boundaries, perception in `world/`, JSON Schema
   contract pipeline, AGENTS.md as the single instruction file.

Out of scope: tick loop, world rules, residents, LLM SDKs, FastAPI, WebSocket, rendering
beyond a placeholder grid, spec content, pushing to any remote.

Acceptance (clean clone):

```
uv sync --directory backend
uv run --directory backend ruff check .
uv run --directory backend mypy src
uv run --directory backend lint-imports
uv run --directory backend pytest
pnpm --dir frontend install
pnpm --dir frontend lint
pnpm --dir frontend build
uv run --directory backend python ../scripts/gen_types.py   # then: git diff --exit-code
```

Also verify import-linter: temporarily add `import living_island.sim` inside `world/`,
confirm `lint-imports` fails, revert. Deliverable: single commit on `main`
"P0-01: repository scaffold" and this handoff.

## Handoff

### What changed

Created the full scaffold per the target structure: git config files, `AGENTS.md`/`CLAUDE.md`,
docs (product doc copied byte-identical, spec skeletons, open questions, ADR 0001), backend
package with 3 import-linter contracts, frontend (Vite + React + strict TS + ESLint, Canvas
placeholder grid), `scripts/gen_types.py` with committed generated output, CI workflow.

### Commands run and results

See the final reply for the full output. Summary: `uv sync`, `ruff check`, `mypy src`,
`lint-imports` (3 kept, 0 broken), `pytest` (12 passed), `pnpm install`, `lint`, `typecheck`,
`build`, and `gen_types.py` followed by `git diff --exit-code` (clean) all pass locally.

Import-linter negative test: appended `import living_island.sim` to `world/__init__.py`;
`lint-imports` exited 1 reporting `living_island.world -> living_island.sim` as a broken
contract; change reverted.

### Deviations

- `events/narrative.py` added (not in the target tree) so contract 3 has a concrete module
  to target.
- `scripts/gen_types.py` writes a combined `contract.schema.json` (one schema with `$defs`)
  so a single `contract.ts` is produced; `json2ts` is invoked through a `gen:types` pnpm script.
- TypeScript pinned to `~6.0` because `typescript-eslint` 8.72 refuses TS 7.0.
- `pnpm@10.34.9` pinned via `packageManager`; `uv`/`pnpm` were not installed on this machine
  and were installed locally (`pip install --user uv`, `npm i -g pnpm@10 --prefix ~/.tools`).
  Corepack failed here (EPERM/EXDEV), so this is not repo-visible.
- Added `ruff format --check` to CI and AGENTS.md (extra to the brief). Build backend is
  hatchling.
- `SnapshotMeta` uses `extra="forbid"` so the generated TS type has no index signature.

### Open questions

- OQ-001 in `docs/spec/open-questions.md`: whether a separate `interface`/API package is wanted.
- The Python minimum is `>=3.13`; CI relies on `setup-uv` fetching Python 3.13 (not verified
  on GitHub, since nothing is pushed).
