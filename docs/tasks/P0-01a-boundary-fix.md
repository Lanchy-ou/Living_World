# Task P0-01a: Fix import boundaries (follow-up to P0-01)

## Brief

Branch: task/P0-01a-boundary-fix. Scope: only the items below.

1. In `backend/pyproject.toml`, contract 2: add these plain ignore entries:
   `living_island.agents -> living_island.world.protocol`
   `living_island.memory -> living_island.world.protocol`
   Set `unmatched_ignore_imports_alerting = "error"`.
2. Contract 3: widen it to the whole `living_island.events` package.
   It must not import `living_island.sim` or `living_island.persistence`.
3. Add a permanent positive case: create `agents/base.py` with a typing-only
   `Resident` Protocol, `decide(observation: Observation) -> ActionIntent`,
   imported from `living_island.world.protocol`. Add no logic.
4. Copy the full P0-01 brief into `docs/tasks/P0-01-scaffold.md`, above the Handoff section.
   In the Handoff, fix the TypeScript version text (it is `^6.0.3`, not `~6.0`)
   and replace "see final reply" with the exit code of each command.
5. Create `docs/tasks/P0-01a-boundary-fix.md` containing this brief and a Handoff section.

Acceptance: all P0-01 acceptance commands pass. Then, in a scratch copy, run these
three probes and record the exit codes:
- `agents/__init__.py` imports `world.protocol` → pass
- `agents` imports `living_island.world` → fail
- `events/__init__.py` imports `sim` → fail

Deliver one commit. Merge to `main` only if all checks pass.

## Handoff

### What changed

- `backend/pyproject.toml`: contract 3 now covers all of `living_island.events`; contract 2
  is split into one contract for `agents` (`unmatched_ignore_imports_alerting = "error"`)
  and one for `memory`; see Deviations.
- `backend/src/living_island/agents/base.py`: typing-only `Resident` Protocol.
- `docs/tasks/P0-01-scaffold.md`: full brief added above the Handoff; TypeScript version
  and exit codes fixed.

### Commands run and results (exit codes)

All P0-01 acceptance commands, run on this branch: `uv sync` 0; `ruff check .` 0;
`ruff format --check .` 0; `mypy src` 0; `lint-imports --no-cache` 0 (4 contracts kept);
`pytest` 0; `pnpm install` 0; `lint` 0; `typecheck` 0; `build` 0; `gen_types.py` 0 with a
clean working tree afterwards.

Probes in a scratch copy of `backend/` (all run with `lint-imports --no-cache`):

| Probe | Expected | Actual exit code |
|---|---|---|
| `agents/__init__.py` imports `world.protocol` | pass | **1 (fail)** |
| `agents/__init__.py` imports `living_island.world` | fail | 1 (fail) |
| `events/__init__.py` imports `living_island.sim` | fail | 1 (fail) |
| extra: a new `agents/<submodule>.py` imports `world.protocol` | pass | 0 (pass) |

### Deviations

1. **Plain ignore entries cannot match the brief's own positive case.** An ignore entry
   `living_island.agents -> living_island.world.protocol` matches only imports made by the
   `living_island.agents` package module itself (`agents/__init__.py`), not by
   `agents/base.py`. With `unmatched_ignore_imports_alerting = "error"` and
   `base.py` as the positive case, the plain entries fail with "No matches for ignored
   import" (observed). I used the wildcard `living_island.agents.** -> living_island.world.protocol`,
   which matches `base.py` and any future agent submodule, and the check stays at `"error"`.
2. **Probe 1 fails as a consequence.** The wildcard does not match `agents/__init__.py`
   itself, so an import of `world.protocol` there is reported as a violation. Allowing both
   would need both entries, and then the plain one is unmatched (error) unless
   `agents/__init__.py` permanently imports the protocol. Submodules (the real use) pass.
3. **`memory` contract split out with `unmatched_ignore_imports_alerting = "none"`.** No memory
   module imports `world.protocol` yet, so its ignore entry is unmatched today and `"error"`
   would fail. Switch it to `"error"` when the first memory module imports the protocol.
4. **Stale cache:** a plain `lint-imports` run in the scratch copy once reported a failure on
   an already-restored tree; `--no-cache` passed. Probes and the final run used `--no-cache`.

### Open questions

- For probe 1, should `agents/__init__.py` itself be allowed to import `world.protocol`
  (add a plain entry plus a permanent import there), or is "submodules only" what you want?
- Should CI run `lint-imports --no-cache` to avoid stale results?
