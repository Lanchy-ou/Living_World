# AGENTS.md

Single instruction file for all coding agents (Claude Code, Codex, others). `CLAUDE.md`
only points here. The repository is the only shared context between agents.

## Project

Living Island is a self-running 2D island simulation with LLM-driven residents. A
deterministic world engine owns all state; residents (rule-based or LLM) only propose
intents; the frontend only displays state and sends commands.

- Product document: `docs/product/living-island-v0.1-design.md` (read the "[Claude note]"
  blocks too; notes marked "Confirmed" override the original text).
- Specs: `docs/spec/` (`world-rules-v0.1.md`, `interface-contract.md`, `open-questions.md`).
- Decisions: `docs/adr/`. Task briefs and handoffs: `docs/tasks/`.

## Source of truth order

When documents disagree: `docs/spec/` > `docs/adr/` > `docs/product/` > code.
If code disagrees with the spec, the code is wrong (or the spec needs a task to change it).

## Core principles

1. **The world is the source of truth.** Agents only propose intents; the world validates
   and resolves them. No LLM output may change world state directly.
2. **Perception is not omniscience.** Agents only receive an `Observation` built by the
   world; they never see full world state.
3. **The narrative never invents facts.** Narrative code is read-only over the event log.
4. **Memory is not objective history.** The event log (engine-owned) is separate from
   subjective character memory.
5. **Reproducibility.** Seeded RNG everywhere; every LLM call is recorded (input, prompt
   version, model, raw output, parsed result, latency, tokens) so runs replay without
   new model calls.
6. **No game logic in the frontend.** It displays and sends commands only.

## Module boundaries

Python package `living_island` (`backend/src/living_island/`). Enforced by import-linter
(`backend/pyproject.toml`) in CI:

- `world` imports no other `living_island` subpackage, and no `anthropic`, `openai`,
  `httpx`, `requests`, `fastapi`. It contains perception (observation building) and
  `world/protocol.py` (`Observation`, `ActionIntent`, `ActionResult`).
- `agents` and `memory` may use `world` only through `living_island.world.protocol`, and
  only their submodules (e.g. `agents/base.py`) may import it. Package `__init__.py` files
  must not import anything from `world`.
- The whole `events` package (not just `events.narrative`) must not import `sim` or
  `persistence`.
- `agents` never modify world state; `sim` is the only coordinator that connects them.
- `contract` holds the pydantic models shared with the frontend.
- `frontend/src/api/generated/` is generated from `contract`; never hand-edit it.

## Commands

Run from the repo root. Works on Windows, macOS and Linux.

```bash
# Backend setup
uv sync --directory backend

# Backend checks
uv run --directory backend pytest
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv run --directory backend lint-imports --no-cache

# Frontend
pnpm --dir frontend install
pnpm --dir frontend dev
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build

# Regenerate TS types from the pydantic contract
uv run --directory backend python ../scripts/gen_types.py
```

## Workflow rules

- One task = one branch `task/<id>-<slug>`. Stay within the task's scope.
- Do not edit `docs/spec/`, `docs/product/` or `docs/adr/` unless the task says so.
- If the spec is missing or ambiguous: do NOT invent rules or numbers. Add an entry to
  `docs/spec/open-questions.md`, make the smallest reversible assumption, and flag it in
  your handoff notes.
- Never hand-edit generated files. Never commit `runs/` contents or secrets (`.env`).
- Every world-rule change ships with tests; invariant tests (`backend/tests/invariants/`)
  must stay green.
- Code, comments and docs are written in English.
- Scripts must be cross-platform: Python scripts or `package.json` scripts only.
- When done, append a "Handoff" section to `docs/tasks/<id>.md`: what changed, commands
  run and their results, deviations, open questions.

## Definition of done

All CI steps pass locally: ruff, mypy, lint-imports, pytest, frontend lint/typecheck/build,
and type generation leaves `git diff --exit-code` clean.
