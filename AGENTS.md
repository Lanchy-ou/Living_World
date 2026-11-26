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
  `rule-policy-v0.1.md`, `p2-experiments-v0.1.md`, `frontend-design-v0.1.md`,
  `open-questions.md`).
- Implementation plans: `docs/plans/` (P1, P2, P3 and P3.5 plans: tasks, milestones
  and change requests).
- Decisions: `docs/adr/`. Task briefs and handoffs: `docs/tasks/<phase>/` (e.g. `docs/tasks/p1/`).

## Current phase and entry points

P3 is closed as a delivered foundation under the owner decision of 2026-11-16.
Long proof and full live evaluation are explicitly deferred, not passed.
Read [P3 closeout and P3.5 handoff](docs/tasks/p3/P3-closeout.md) before starting
new work; do not silently restart deferred trials or merge parked candidates.

- [P3 implementation plan](docs/plans/p3-implementation-plan-v0.1.md)
- P3 specifications for [resident experience](docs/spec/resident-experience-v0.1.md),
  [resident cognition](docs/spec/resident-cognition-v0.1.md),
  [LLM decisions and recovery](docs/spec/llm-decision-v0.1.md), and
  [evaluation and inspection](docs/spec/p3-evaluation-v0.1.md)
- [M9 acceptance and evidence](docs/tasks/p3/M9-evidence.md)

P3.5 design (M11) is complete. The owner accepted ADRs 0007–0014 on
2026-11-17, after approving the protocol change request CR-009
(`docs/spec/open-questions.md`). The
[world–agent protocol spec](docs/spec/world-agent-protocol-v0.1.md) was frozen
on 2026-11-17, and amended by the approved CR-010 and CR-011. The other seven
P3.5 specs were frozen on 2026-11-19 (task P3.5-SP-01). The P3 specs stay in
force for v1 runs; each P3.5 spec states which P3 parts it replaces for new work.

P3.5 is closed after the owner signed M12, M13 and M14. The M15 multi-resident
acceptance runs and the removal of v1 are deferred, not passed. Read the
[P3.5 closeout](docs/tasks/p3.5/P3.5-closeout.md) before starting new work.

- [P3.5 plan](docs/plans/p3.5-implementation-plan-v0.1.md) (system index,
  milestones M11–M15, acceptance runs, deferred P3 work)
- [P3.5 design review brief](docs/tasks/p3.5/P3.5-00-review-brief.md)
- P3.5 specifications for [rule representation](docs/spec/rule-representation-v0.1.md),
  the [world engine](docs/spec/world-engine-v0.1.md),
  [starter content](docs/spec/starter-content-v0.1.md),
  the [memory model](docs/spec/memory-model-v0.1.md),
  [memory formation](docs/spec/memory-formation-v0.1.md),
  the [decision loop](docs/spec/decision-loop-v0.1.md) and
  [evaluation](docs/spec/evaluation-v0.1.md), with the
  [owner decision sheet](docs/tasks/p3.5/P3.5-SP-01-decisions.md)

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

Run from the repo root on Windows, macOS or Linux. Use the tool versions in
[README.md](README.md#prerequisites) and install the locked dependencies.

```sh
# Locked setup shared by the relevant CI jobs
uv sync --directory backend --locked
pnpm --dir frontend install --frozen-lockfile

# Backend CI
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv run --directory backend lint-imports --no-cache
uv run --directory backend pytest

# Frontend CI
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend run test:schema
pnpm --dir frontend run test

# Contract CI
uv run --directory backend python ../scripts/gen_types.py
uv run --directory backend python ../scripts/gen_p3_inspection_types.py
uv run --directory backend python ../scripts/gen_v2_inspection_types.py
git diff --exit-code
```

For the backend checks, use a checkout with the pinned historical commits
available. The [CI workflow](.github/workflows/ci.yml) fetches full history for
that job. For local viewer development, run `pnpm --dir frontend dev`.

### Windows backend checks

Use `git config --local core.longpaths true` from the repository root when deep
test paths require it. P3 registration tests create temporary Git repositories
that can require the same setting. If they do, use Git's command-scope
configuration in a fresh PowerShell session so child Git processes inherit it.
Use an existing short, writable parent in place of `C:\Temp`. Each pytest run
needs a dedicated base path that does not already exist. Keep that path separate
from working directories and retained data because pytest may clear its base.

```powershell
# Optional command-scope configuration for the test repositories
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'core.longpaths'
$env:GIT_CONFIG_VALUE_0 = 'true'

$pytestBase = Join-Path 'C:\Temp' ('li-' + [guid]::NewGuid().ToString('N').Substring(0, 12))
uv run --directory backend pytest --basetemp $pytestBase
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
- Validate once, at the boundary (owner decision, 2026-11-20). Check data where it
  enters: a file, a wire message, a model response, or another package's public
  function. Turn it into typed data there. Inside, trust those types and earlier
  checks. Add no re-validation, `isinstance` checks or fallbacks for states they
  already rule out, and no compatibility shims for code that has not shipped. A
  check for a real, reachable case ships with a test that reaches it. Gate 2
  reviewers flag checks that no input can trigger.
- Scripts must be cross-platform: Python scripts or `package.json` scripts only.
- When done, append a "Handoff" section to `docs/tasks/<phase>/<id>.md`: what changed, commands
  run and their results, deviations, open questions, **plus** the seven required
  fields (plan §6).
- Every task passes Gate 1 (executor checks) and Gate 2 (independent reviewer). The project
  owner signs Gate 3 at the milestones listed in the relevant implementation plan §4.
- There is no fixed limit on active workers (owner decision, 2026-11-11). Each task has
  its own branch and an isolated worktree. Tasks running at the same time must not edit
  the same files. A reviewer never reviews work it helped write.
- A spec contradiction goes through the change-request steps (plan §7). Downstream agents
  never edit frozen contracts.
- Task cards follow `docs/tasks/_template.md`.

## Definition of done

Pass the commands above locally with locked dependencies. The jobs in the
[CI workflow](.github/workflows/ci.yml) map to these checks.

- `backend` installs with `uv sync --directory backend --locked`, then runs Ruff
  lint and format checks, mypy, import-linter, and pytest. On Windows, use a new
  dedicated `--basetemp` for each pytest run as shown above.
- `frontend` installs with `pnpm --dir frontend install --frozen-lockfile`, then
  runs lint, typecheck, build, `pnpm --dir frontend run test:schema`, and
  `pnpm --dir frontend run test`.
- `contract` installs both locked dependency sets, regenerates types, and
  verifies that `git diff --exit-code` is clean.
