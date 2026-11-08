# ADR 0001: Repository structure and module boundaries

Terminology note: `Observation` was renamed `Perception` in ADR 0002.

- Status: accepted
- Date: 2026-11-08
- Task: P0-01

## Context

Several coding agents (Claude Code, Codex, others) work in this repository, and the
repository is their only shared context. The design requires that the world is the source
of truth, that residents never see full world state, and that the frontend and backend
cannot drift apart.

## Decisions

### Monorepo layout

One repository: `backend/` (Python 3.13, uv, src layout, package `living_island`),
`frontend/` (Vite, React, strict TypeScript, pnpm), plus `docs/`, `content/`, `art/`,
`scripts/`, `runs/`. Scripts are Python or package.json scripts so they run on Windows.

### Module boundaries

Enforced by import-linter in CI:

- `world` is pure: no other `living_island` subpackage, no LLM or network libraries.
- `agents` and `memory` may touch `world` only via `world.protocol`.
- `events.narrative` is read-only: it must not import `sim` or `persistence`.

### Perception lives in `world/`

Building an `Observation` requires full world state, so observation building is part of
`world`. Agents receive only the resulting `Observation` type from `world.protocol`. This
makes the perception boundary a static, checkable import rule rather than a convention.

### JSON Schema contract pipeline

pydantic models in `living_island.contract` are the single definition of frontend-facing
data. `scripts/gen_types.py` exports JSON Schema and runs `json-schema-to-typescript` to
produce `frontend/src/api/generated/contract.ts`, which is committed. CI regenerates and
fails on `git diff` if it is stale. No FastAPI/OpenAPI dependency at this stage.

### AGENTS.md as the single instruction file

`AGENTS.md` holds all agent instructions. `CLAUDE.md` contains only `@AGENTS.md` so every
tool reads the same text.

## Consequences

- Boundary violations fail CI instead of relying on review.
- Adding an API layer later (see OQ-001) must not weaken these rules.
- Storage stays JSON snapshots + JSONL; no database until a later ADR.
