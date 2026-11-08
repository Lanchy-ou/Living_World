# Task P0-01: Repository scaffold

## Brief

## Context
Living Island is a self-running 2D island simulation with LLM-driven residents.
The attached design document (Living_Island_v0.1_Design_Draft_annotated_EN.md) is
the product document. Read it fully, including all "[Claude note]" blocks — notes
marked "Confirmed" override the original text.

This workspace is shared by multiple coding agents (Claude Code, Codex, others).
The repository itself is the only shared context between them.

This task creates the skeleton only. Do NOT implement any game logic.

## Fixed decisions (do not change)
- Monorepo, repo root = current working directory.
- Backend: Python 3.13, `uv`, src layout, package name `living_island`.
- Frontend: Vite + React + TypeScript (strict), ESLint, `pnpm`.
- Contract: pydantic models → JSON Schema → `json-schema-to-typescript` → TS types.
  No FastAPI in this task.
- Storage later = JSON snapshots + JSONL; no database.
- Repo language: English for code, comments and docs.
- Dev platform is Windows: every script must be cross-platform
  (Python scripts or package.json scripts; no bash-only or PowerShell-only scripts).

## Target structure
```
.
├── AGENTS.md
├── CLAUDE.md                 # exactly one line: @AGENTS.md
├── README.md
├── .gitignore  .gitattributes  .env.example
├── .github/workflows/ci.yml
├── docs/
│   ├── product/living-island-v0.1-design.md   # the attached doc, copied unchanged
│   ├── spec/world-rules-v0.1.md               # headings only
│   ├── spec/interface-contract.md             # headings only
│   ├── spec/open-questions.md
│   ├── adr/0001-repo-structure-and-module-boundaries.md
│   ├── tasks/P0-01-scaffold.md                # this brief + your handoff notes
│   └── retros/.gitkeep
├── backend/
│   ├── pyproject.toml
│   ├── src/living_island/
│   │   ├── __init__.py
│   │   ├── world/        # authoritative state, tiles, time, rules, actions, resolution, perception
│   │   │   └── protocol.py   # placeholder: Observation, ActionIntent, ActionResult types
│   │   ├── agents/       # resident interface, rule_based/, llm/ (planner, adapters, prompt building)
│   │   ├── memory/       # episodic memory, beliefs, retrieval, reflection, dream integration
│   │   ├── events/       # authoritative event log handling + read-only narrative projection
│   │   ├── sim/          # coordinator: tick loop, decision triggers, budget, fallback
│   │   ├── persistence/  # JSON snapshots, JSONL events, LLM call recording/replay
│   │   └── contract/     # pydantic models shared with the frontend
│   ├── prompts/.gitkeep
│   └── tests/{unit,invariants,scenarios,replay}/
├── frontend/
│   └── src/{api/generated,replay,render,panels,controls,debug}/
├── content/{worlds,characters}/.gitkeep
├── art/LICENSES.md
├── scripts/gen_types.py
└── runs/.gitkeep             # contents gitignored
```
Each Python subpackage gets an `__init__.py` whose docstring states its
responsibility and what it must NOT do (take this from the design doc, Section 10).

## Requirements

### 1. Git
- `git init`, default branch `main`.
- `.gitattributes`: `* text=auto eol=lf` (plus binary rules for images).
- `.gitignore`: Python, Node, `.venv`, `runs/*` (keep `.gitkeep`), `.env`.
- `.env.example` with placeholder names for LLM API keys (no real values).

### 2. Backend
- Runtime dependency: `pydantic` only.
- Dev dependencies: `pytest`, `hypothesis`, `ruff`, `mypy` (strict), `import-linter`.
- `world/protocol.py`: empty placeholder classes with docstrings only.
- `contract/`: one placeholder model, e.g. `SnapshotMeta(schema_version: str, tick: int)`.
- One smoke test that imports every subpackage.
- import-linter contracts (must be enforced in CI):
  1. `living_island.world` imports no other `living_island` subpackage, and none of:
     `anthropic`, `openai`, `httpx`, `requests`, `fastapi`.
  2. `living_island.agents` and `living_island.memory` may import from
     `living_island.world` ONLY via `living_island.world.protocol`.
     (Agents must never see full world state — this enforces the perception boundary.)
  3. `living_island.events` narrative code must not import `living_island.sim`
     or `living_island.persistence` write paths (keep it read-only; a simple
     forbidden contract is enough for now).

### 3. Frontend
- Vite React TS template, `strict: true`, ESLint configured.
- Minimal `App` that draws a placeholder grid on an HTML Canvas. No game logic.
- `src/api/generated/` holds generated files only; add a README there saying "do not edit".

### 4. Type generation
- `scripts/gen_types.py`: exports JSON Schema from `living_island.contract` models
  into `frontend/src/api/generated/`, then calls the pnpm script that runs
  `json-schema-to-typescript` to produce `contract.ts`.
- Commit the generated output.

### 5. CI (`.github/workflows/ci.yml`)
Backend: ruff, mypy, import-linter, pytest.
Frontend: install, lint, typecheck, build.
Contract: run type generation, then `git diff --exit-code` (fails if generated types are stale).

### 6. AGENTS.md (keep it under ~150 lines)
Sections:
- **Project**: one paragraph + pointers to `docs/product/` and `docs/spec/`.
- **Source of truth order**: `docs/spec/` > `docs/adr/` > `docs/product/` > code.
- **Core principles**: the world is the source of truth; agents only propose intents;
  perception is not omniscience; the narrative never invents facts; reproducibility
  (seeded RNG, every LLM call recorded).
- **Module boundaries**: dependency rules as in import-linter, in plain words.
- **Commands**: exact commands for setup, test, lint, typecheck, type generation, frontend dev.
- **Workflow rules**:
  - One task = one branch `task/<id>-<slug>`; stay within the task's scope.
  - Do not edit `docs/spec/`, `docs/product/` or `docs/adr/` unless the task says so.
  - If the spec is missing or ambiguous: do NOT invent rules or numbers. Add an entry
    to `docs/spec/open-questions.md`, make the smallest reversible assumption,
    and flag it in your handoff notes.
  - Never hand-edit generated files; never commit `runs/` or secrets.
  - Every world-rule change ships with tests; invariant tests must stay green.
  - When done, append a "Handoff" section to `docs/tasks/<id>.md`: what changed,
    commands run and their results, deviations, open questions.
- **Definition of done**: all CI steps pass locally.

### 7. Spec skeletons (headings + one-line description each; NO content, NO numbers)
`world-rules-v0.1.md`: Map & tiles · Time scale · Character state & numbers ·
Needs decay · Action table (preconditions / duration / effects / failure codes) ·
Conflict resolution · Decision triggers · Perception rules · Conversation rules ·
Resources & regrowth · Death · Invariants.
`interface-contract.md`: Snapshot format · Event format (tick, seq, failure code,
llm_call_id) · LLM call log format · Character panel view · Player commands · Versioning.

### 8. ADR 0001
Record: monorepo layout, module boundaries, perception placed in `world/`,
JSON Schema contract pipeline, AGENTS.md as the single instruction file.

## Out of scope
Tick loop, world rules, residents, LLM SDKs, FastAPI, WebSocket, rendering beyond a
placeholder grid, filling in spec content, pushing to any remote.

## Acceptance
All of these pass on a clean clone:
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
Also verify import-linter works: temporarily add `import living_island.sim` inside
`world/`, confirm `lint-imports` fails, then revert. Report this in the handoff.

## Deliverable
- A single commit on `main`: "P0-01: repository scaffold".
- Handoff section in `docs/tasks/P0-01-scaffold.md`.
- Reply with: the final tree (depth 3), the output of every acceptance command,
  any deviations and why, open questions.

## Handoff

### What changed

Created the full scaffold per the target structure: git config files, `AGENTS.md`/`CLAUDE.md`,
docs (product doc copied byte-identical, spec skeletons, open questions, ADR 0001), backend
package with 3 import-linter contracts, frontend (Vite + React + strict TS + ESLint, Canvas
placeholder grid), `scripts/gen_types.py` with committed generated output, CI workflow.

### Commands run and results

Exit codes (all 0): `uv sync --directory backend` 0; `ruff check .` 0; `ruff format --check .` 0;
`mypy src` 0; `lint-imports` 0 (3 contracts kept); `pytest` 0 (12 passed);
`pnpm --dir frontend install` 0; `lint` 0; `typecheck` 0; `build` 0;
`gen_types.py` 0, then `git diff --exit-code` 0 (clean).

Import-linter negative test: appended `import living_island.sim` to `world/__init__.py`;
`lint-imports` exited 1 reporting `living_island.world -> living_island.sim` as a broken
contract; change reverted.

### Deviations

- `events/narrative.py` added (not in the target tree) so contract 3 has a concrete module
  to target.
- `scripts/gen_types.py` writes a combined `contract.schema.json` (one schema with `$defs`)
  so a single `contract.ts` is produced; `json2ts` is invoked through a `gen:types` pnpm script.
- TypeScript pinned to `^6.0.3` (in `frontend/package.json`) because `typescript-eslint` 8.72
  refuses TS 7.0.
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
