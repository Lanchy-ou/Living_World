# Task P1-design-review-fixes

## Brief

The user authorized fixing the reviewed Claude P1 drafts. Scope: the existing staged agent
interface, replay frontend and implementation plan plus their change log. Keep them DRAFT;
do not land official specs, implement runtime/frontend code, delete files or change content.
Branch: `task/P1-design-review-fixes`.

## Handoff

### What changed

- Fixed all eight blocking review groups and the minor display/reference/test issues in
  `_design_staging/P1-design`; appended F1–F10 to the existing change history.
- Defined explicit A1/A2 proposals, canonical model ownership, restricted checkpoint phase,
  actor-local policy initialization, script identity/cursors and deterministic decision
  commitment. Added request/trace/output comparisons and preserved replay provenance.
- Froze observation lifecycle and committed-boundary observer ports; defined frame spooling,
  checkpoint prefixes and separate run/resume/reexecute CLI behavior.
- Completed ReplayBundle validation/export entry and display metadata; preserved nine tasks,
  two workers/four milestones with earlier real-output acceptance and no staging deletion.

### Verification

- `python -B -c` with an in-memory standard-library document/reference checker: exit 0,
  **30 checks passed**. It checked DRAFT status, balanced fences, heading order/uniqueness,
  the nine frozen triggers, ten task cards, AI-01..15 and FE-T01..13 IDs, F1..10 coverage,
  cancellation of unsafe cleanup, required state/port/schema names, explicit section
  references and unchanged hashes of the three formal specs plus default TOML.
  Reference calculations also checked request-hash sensitivity/order independence, event
  slices including a zero-event tick, and checkpoint-prefix exclusion of later log tails.
- `git -c safe.directory=E:/桌面/Living_World --no-optional-locks diff --check`: exit 0.
  This checks the tracked tree; the ignored drafts were checked separately above.
- `git -c safe.directory=E:/桌面/Living_World --no-optional-locks status --short --untracked-files=normal`:
  only this new task handoff is untracked; no tracked production diff.
- `Get-Command uv,pnpm -ErrorAction SilentlyContinue`: pnpm found, uv absent from current
  PATH. No tool installation or environment configuration change was attempted.

Production CI, schema generation and runtime tests are NOT_RUN: no production code,
dependency or implemented schema changed. The new engine/browser acceptance cases are
requirements for P1, not claims that those implementations already exist.

### Deviations

- The task edits the existing staged drafts in place, not a newly landed spec version.
  Explicit proposed choices and amendments are listed in change-log section E.
- `_design_staging/` is ignored by the existing local Git exclude; its files remain local
  review artifacts. Only this new handoff appears in the ordinary Git status.
- No independent reviewer or additional agent was spawned. No commit, merge or publication
  was performed; `result_commit` is not created. A later independent review remains needed.
- Per-command safe.directory was used without editing Git configuration. Creating the
  AGENTS-required task branch used approved filesystem escalation.

### Open questions

- Review/approve proposed A1/A2 and the listed ownership/time-sampling/checkpoint choices
  before P1-00/P1-01. The official specs still have the old context prohibition until A1.
- P1-01 must confirm import-linter and generated-schema/browser compatibility with actual
  models; P1-04/P1-06/P1-07 must prove the specified lifecycle/restore behavior in code.
- No balance changes or measured survival claims were introduced. P2 remains responsible
  for survival and canteen-benefit evaluation.
- Formal open-questions/spec files are unchanged: these unlanded proposals are tracked in
  the staged change log and this handoff for approval before the landing tasks.

### Input fingerprints (SHA-256)

| Staged input before this task | SHA-256 |
|---|---|
| CHANGES-from-GPT-draft.md | 82f1adfb35381df2c7345b5c419ff57ed5c1735ca3f8e0a694431d101412db8f |
| agent-interface-v0.1.md | f572394999c2372581aa4c6655fd51dad103dddc689c31018b7d91851ab88636 |
| p1-replay-frontend-v0.1.md | 3a91375e632ff9bacf1b9080eed538aa026e374f19fd0fb1c07bf5ac8e07da38 |
| p1-implementation-plan-v0.1.md | 8015db182756de54353a62a6f11b36485f5fa223ecaa3b5fd538690b5e98ebee |
