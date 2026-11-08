# Task P0-02: Land World Rules v0.1 into the repository

## Brief

## Context
World Rules v0.1-rc3 is approved by the user. It currently sits in the git-excluded
folder `_design_staging/P0-02-rc3/`. This task makes it the official version and cleans up.
No game logic. Do not change any rule, number or wording beyond what is listed below.

Branch: `task/P0-02-world-rules-landing`, created from `main`.
First check that `task/P0-02-rc3-review-fixes` has no commits beyond `main`, then delete it.

## 1. Move files (copy from `_design_staging/P0-02-rc3/`)
| From | To |
|---|---|
| docs/spec/world-rules-v0.1.md | docs/spec/world-rules-v0.1.md (replace skeleton) |
| docs/spec/interface-contract-v0.1.DRAFT.md | docs/spec/interface-contract-v0.1.md (delete old `interface-contract.md` skeleton) |
| docs/spec/balance-notes-v0.1.md | docs/spec/balance-notes-v0.1.md |
| content/worlds/default.toml | content/worlds/default.toml |
| content/worlds/default-island.map | content/worlds/default-island.map (byte-identical) |

Do NOT land: the change logs (rc1–rc3), the staging README, or `tools/validate_rc3.py`.

## 2. Status headers
In the three spec files and the TOML header comment, replace the
"candidate / NOT approved" status with:
> **Approved v0.1 (2026-11-08).** Rules and semantics are frozen. Numeric values in
> `content/worlds/default.toml` are candidates to be tuned in P2 without changing this spec.
> `Perception`, `ActionPlan`, `ActionIntent`, `ActionResult` and `DecisionTrigger` are frozen
> unless the agent-interface spec requires a change, which must go through a spec amendment task.
> `DecisionContext` remains provisional.

Change file references that point to `.DRAFT` names or change logs so they point to the landed names.

## 3. Rename Observation → Perception
- `backend/src/living_island/world/protocol.py`:
  - rename the placeholder `Observation` to `Perception`;
  - add an empty placeholder `ActionPlan` (docstring only).
- `backend/src/living_island/agents/base.py`: change the signature to
  `decide(perception: Perception) -> ActionPlan`.
- Update `AGENTS.md` (core principle 2, module boundaries, specs list) to say `Perception`,
  and reference `interface-contract-v0.1.md` and `balance-notes-v0.1.md`.
- Fix any test that references the old names.

## 4. Records
- `docs/adr/0002-world-rules-v0.1.md`, at most one page. It records:
  - 64×64 map at 50 m per tile, walking budget 8 per tick, candidate hydration decay 100
    (120 kept as a P2 comparison);
  - the canteen's value is a hypothesis, to be tested by the P2 with/without-canteen comparison;
  - the day-one water cue (damp moss), approved option C;
  - `world` builds `Perception`, and `agents` builds `DecisionContext`;
  - the freeze scope from section 2.
- Keep `docs/tasks/P0-02-rc3-review.md` as the history record.
- Create `docs/tasks/P0-02-world-rules-landing.md` containing this brief plus your handoff.
- `docs/spec/open-questions.md`: add one entry: "Content-validation and engine tests listed in
  world rules §8 are P1 work."

## 5. Minimal content test
Add `backend/tests/unit/test_default_content.py`. It must check:
- the TOML parses and contains no floats;
- the map has `map.height` rows of `map.width` characters with LF line endings;
- S, C and M each appear once, and each sits at the coordinates given in the TOML;
- the set of F tiles equals the configured fruit-tree positions;
- every resident starts on a passable tile.

Use only the standard library and pytest. Write nothing else.

## 6. Cleanup
After copying and verifying, delete `_design_staging/` entirely, and remove the
`_design_staging/` line from `.git/info/exclude`.

## Acceptance
- All AGENTS.md "Definition of done" checks pass, including the new content test.
- `git diff --stat main` shows only the files listed above.
- Compare the landed `default-island.map` with the staging copy by hash before deleting staging,
  and record the hash in the handoff.

## Deliverable
One commit: "P0-02: land World Rules v0.1". Do not merge; wait for review.
Reply with: `git diff --stat main`, every command's exit code, the map hash, and any deviations.

## Handoff

### What changed

- Landed the four spec/content files from `_design_staging/P0-02-rc3/`; deleted the old
  `interface-contract.md` skeleton. Change logs, staging README and `validate_rc3.py` not landed.
- Status headers replaced in the three spec files and the TOML header comment; `.DRAFT` and
  change-log references updated to the landed names.
- `Observation` → `Perception`, new `ActionPlan` placeholder, `Resident.decide` signature,
  `AGENTS.md` updated.
- ADR 0002, this task file, OQ-003, `test_default_content.py`.
- `docs/tasks/P0-02-rc3-review.md` (previously untracked) is committed as the history record.
- `_design_staging/` deleted and its line removed from `.git/info/exclude`.
- Old branch `task/P0-02-rc3-review-fixes` had 0 commits beyond `main`; deleted.

### Commands and exit codes (all 0)

`uv sync --directory backend` 0; `pytest` 0 (17 passed, incl. 5 new content tests);
`ruff check .` 0; `ruff format --check .` 0; `mypy src` 0; `lint-imports --no-cache` 0
(4 contracts kept); `pnpm install` 0; `lint` 0; `typecheck` 0; `build` 0;
`gen_types.py` 0 followed by a clean `git diff --exit-code` (0).

### Map hash

`default-island.map` SHA-256: `007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c`
(landed copy and staging copy identical, `cmp` clean; also identical to the rc2 map).

### Deviations

- Docstrings in `agents/__init__.py` and `world/__init__.py` mention `Observation`; updated to
  `Perception` for consistency (not in the brief's file list).
- Interface-contract title: removed the "(DRAFT)" suffix as a status label. Other titles still
  say "v0.1-rc3" and the balance-notes title still says "PROPOSED, NOT MEASURED", and the TOML
  `schema_version` is still `"0.1-rc3"`; none were changed (no rule/number/wording changes
  beyond the brief). Decide whether to rename these in a follow-up.
- Balance notes had no status line; the approved block was inserted under the title.
- The TOML header's first line "NOT ACCEPTED / NOT BALANCE-TESTED" was replaced by the block;
  its other comment lines are unchanged.
- Fixed a dangling "and" left in AGENTS.md "Module boundaries" by P0-01a while editing it.
- The ADR names the damp-moss cue as "approved option C" as stated in the brief; the option
  letter is not defined in the landed spec files.

### Open questions

- OQ-003 (engine and content-validation tests are P1 work).
