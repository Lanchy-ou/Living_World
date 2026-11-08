# Living Island

A self-running 2D island simulation with LLM-driven residents. The world engine is the
source of truth; residents only propose intents; stories emerge from real events.

Status: P0 scaffold only. No game logic yet.

- Product document: [docs/product/living-island-v0.1-design.md](docs/product/living-island-v0.1-design.md)
- Specs (skeletons): [docs/spec/](docs/spec/)
- Architecture decisions: [docs/adr/](docs/adr/)
- Instructions for coding agents: [AGENTS.md](AGENTS.md)

## Layout

- `backend/` Python 3.13 package `living_island` (managed with `uv`)
- `frontend/` Vite + React + TypeScript (managed with `pnpm`)
- `scripts/` cross-platform helper scripts (Python)
- `content/` world and character definitions
- `runs/` local run output (gitignored)

## Quick start

```bash
uv sync --directory backend
pnpm --dir frontend install
uv run --directory backend pytest
pnpm --dir frontend dev
```

See [AGENTS.md](AGENTS.md) for the full command list.
