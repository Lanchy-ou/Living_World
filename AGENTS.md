# AGENTS.md

Single instruction file for all coding agents (Claude Code, Codex, others). `CLAUDE.md`
only points here. The repository is the only shared context between agents.

## Project

Living Island is a self-running 2D island simulation with LLM-driven residents. A
deterministic world engine owns all state; residents (rule-based or LLM) only propose
intents; the frontend only displays state and sends commands.

- Product document: `docs/product/living-island-v0.1-design.md` (read the "[Claude note]"
  blocks too; notes marked "Confirmed" override the original text).
- Specs: `docs/spec/` (`world-rules-v0.1.md`, `interface-contract-v0.1.md`,
  `balance-notes-v0.1.md`, `agent-interface-v0.1.md`, `p1-replay-frontend-v0.1.md`,
  `open-questions.md`).
- P1 plan: `docs/plans/p1-implementation-plan-v0.1.md` (tasks, lanes, gates, handoff
  fields, change requests).
- Decisions: `docs/adr/`. Task briefs and handoffs: `docs/tasks/<phase>/` (e.g. `docs/tasks/p1/`).

## Source of truth order

When documents disagree: `docs/spec/` > `docs/adr/` > `docs/product/` > code.
If code disagrees with the spec, the code is wrong (or the spec needs a task to change it).

## Core principles

1. **The world is the source of truth.** Agents only propose intents; the world validates
   and resolves them. No LLM output may change world state directly.
2. **Perception is not omniscience.** Agents only receive a `Perception` built by the
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
  `httpx`, `requests`, `fastapi`. It builds `Perception` (the perception boundary) and holds
  `world/protocol.py` (`Perception`, `ActionPlan`, `ActionIntent`, `ActionResult`).
- `agents` and `memory` may use `world` only through `living_island.world.protocol`.
  The top-level `agents/__init__.py` and `memory/__init__.py` must not import from `world`;
  submodules, including subpackages such as `agents/llm/`, may import only `world.protocol`.
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
- When done, append a "Handoff" section to `docs/tasks/<phase>/<id>.md`: what changed, commands
  run and their results, deviations, open questions, **plus** the seven required
  fields (plan §6).
- Every task passes Gate 1 (executor checks) and Gate 2 (independent reviewer). Gate 3
  (project owner) applies only at milestones M1–M4 (plan §4).
- At most two active workers, counting reviewers. Each task has its own branch and an
  isolated worktree (plan §3).
- A spec contradiction goes through the change-request steps (plan §7). Downstream agents
  never edit frozen contracts.
- Task cards follow `docs/tasks/_template.md`.

## Definition of done

All CI steps pass locally: ruff, mypy, lint-imports, pytest, frontend lint/typecheck/build,
and type generation leaves `git diff --exit-code` clean.
