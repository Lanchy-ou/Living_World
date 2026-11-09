# Task P1-00: Land the P1 design specs (documentation only)

## Brief

### Context
The user has approved three P1 design documents. They sit in the git-excluded folder
`_design_staging/P1-design/`. This task makes them official. Documentation only: no code,
no contract changes. Amendments A1/A2 are NOT applied here; they belong to P1-01a/P1-01b.

### Branch
- Create `task/P1-00-design-landing` from `main`.
- First confirm `task/P1-design-review-fixes` has no commits beyond `main`, then delete it.
  Its untracked `docs/tasks/P1-design-review-fixes.md` is kept and committed in this task
  as a history record.

### 1. Copy files (from `_design_staging/P1-design/`)
`docs/spec/agent-interface-v0.1.md`, `docs/spec/p1-replay-frontend-v0.1.md` and
`docs/tasks/p1-implementation-plan-v0.1.md`, each to the same path in the repository.

Do NOT land `CHANGES-from-GPT-draft.md`. Do NOT delete or modify `_design_staging/`;
the reviewer compares against it, and the user will remove it later.

### 2. Status headers
Replace each file's "DRAFT for user approval ..." status line with:
> **Approved v0.1 (2026-11-08).** Amendment A1 (agent interface) is applied by P1-01a and
> amendment A2 (replay) by P1-01b; until then `interface-contract-v0.1.md` and
> `world-rules-v0.1.md` are unchanged.

Change no other wording. If a link or path is now wrong after the move, fix only that.

### 3. AGENTS.md
- Specs list: add `agent-interface-v0.1.md` and `p1-replay-frontend-v0.1.md`, and the plan
  `docs/tasks/p1-implementation-plan-v0.1.md`.
- Workflow rules, in short form: Gate 1 and Gate 2 for every task (Gate 3 only at M1–M4);
  at most two active workers including reviewers, each task on its own branch and worktree;
  every handoff keeps the existing prose plus the seven required fields (plan §6); spec
  contradictions go through the change-request steps (plan §7) and downstream agents never
  edit frozen contracts; task cards follow `docs/tasks/_template.md`.
- Keep AGENTS.md concise: link to the plan for details.

### 4. Other files
- `docs/tasks/_template.md`: the plan §5 task-card template plus the seven handoff fields.
- `docs/adr/0003-p1-design.md` (one page): one `ResidentRuntime` per resident with `ingest` +
  `decide`; Random, Scripted and Recorded policies; DecisionContext allowed in P1 via A1;
  replay-first with a single-file `ReplayBundle`; continuation-only resume, resumed runs not
  exporting replays; 10 tasks + P1-00, two lanes, milestones M1–M4.
- `docs/tasks/P1-00-design-landing.md`: this brief plus the handoff.

### Acceptance
- `git diff --stat main` shows only the three landed documents, AGENTS.md, `_template.md`,
  ADR 0003 and the two task files; nothing else removed.
- All AGENTS.md "Definition of done" checks pass.
- `interface-contract-v0.1.md` and `world-rules-v0.1.md` are byte-identical to `main`.

### Deliverable
One commit "P1-00: land P1 design specs". Push the branch; do not merge. Reply with
`git diff --stat main`, every command's exit code, and any deviations.

## Handoff

### What changed

- Landed the three approved P1 documents (agent interface, replay frontend, implementation
  plan) from `_design_staging/P1-design/`; `CHANGES-from-GPT-draft.md` not landed.
- Replaced each status paragraph with the Approved v0.1 block; no other wording changed. No
  link or path needed fixing.
- AGENTS.md: spec list, P1 plan link, and five short workflow rules pointing at the plan.
- Added `docs/tasks/_template.md` and `docs/adr/0003-p1-design.md`.
- `docs/tasks/P1-design-review-fixes.md` (previously untracked) is committed as history.
- `task/P1-design-review-fixes` had 0 commits beyond `main`; deleted. `_design_staging/`
  untouched.

### Commands and exit codes (all 0)

`uv sync --directory backend` 0; `pytest` 0 (17 passed); `ruff check .` 0;
`ruff format --check .` 0; `mypy src` 0; `lint-imports --no-cache` 0 (4 contracts kept);
`pnpm install` 0; `lint` 0; `typecheck` 0; `build` 0; `gen_types.py` 0 followed by a clean
`git diff --exit-code` on generated files (0). No code changed.

### Deviations

- The "status line" in each file is a two- or three-line paragraph (it also held the "Based on
  the landed ..." and, in the plan, the "Revised from the GPT draft ..." sentences). The whole
  paragraph was replaced by the block, as the brief says; those sentences are gone.
- A blank line follows the status block so the next paragraph is not merged into the quote.
- The plan's own P1-00 card does not list ADR 0003, so the plan and brief differ slightly in
  scope; the brief was followed and the plan text left unchanged.
- The plan's P1 READY gate still shows P1-00 and the CI URL unchecked; the plan was not edited
  beyond the header.

### Open questions

- None new. The plan's READY-gate item "record a passing CI run URL and commit SHA" is still
  open (GitHub Actions has not been observed from this environment).

### Required fields

1. `base_commit`: 57a9bd35877613a061aecf287ee3b048b8589639; `result_commit`: the tip of
   `task/P1-00-design-landing` (a commit cannot record its own SHA)
2. `status`: READY_FOR_REVIEW
3. `scope_changed`: no
4. `human_interventions`: unknown (0 within this task)
5. `rework_rounds`: 0
6. `verification`: commands and exit codes above; 17 tests passed; NOT_RUN: GitHub Actions
7. `open_questions`: see above
