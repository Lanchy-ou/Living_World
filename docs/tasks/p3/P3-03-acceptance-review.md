# P3-03 independent acceptance review

## Round 2 result (2026-11-12)

**PASS at `2867beb44de384077f8998532c76d2d850cf795a`. P303-A1 is closed.**
This section supersedes the initial CHANGES_REQUESTED disposition below, which is
retained as review history. No new actionable finding was established.

The coordinated foundation correction defines one shared InvalidFallbackPlan in
agents/p3/ports.py. Both submissions contain the same blob
`fa585f702ced1994632caa0018e93d0ae077b6e5`. RuntimeP3 catches only this type around
the adapter call, stages one wait with fallback_error=INVALID_PLAN, and preserves
the entire previous private state. Ordinary ValueError, RuntimeError and OSError
still propagate and require checkpoint recovery. The task cards document the
owner-approved shared-contract scope exception; no frozen spec or DTO changed.

Independent tests used the exact reviewed runtime with P3-04's actual production
fallback module at `41d5ecd4e652a2c4090247673c610939e8c7326a`, loaded from its source
directory through a process-local package path. The test printed both import paths
and asserted exception identity. All **20 real-adapter regressions passed in 3.90
seconds**, including malformed output, lifecycle state, continued decisions,
unexpected exceptions and replay without external calls. No source file was copied
or modified for this integration probe. Separately, the retained adapter fixture
is byte-identical to the latest production module and matches its recorded hash.

Independent checks:

- Exact task command (transactions, persistence, recovery, allocation,
  reexecution, legacy sim runs and persistence): **278 passed in 260.00 seconds**.
- Independent runtime reviewer: 29 typed-error/real-adapter/fatal-error tests passed.
- Ruff check/format: PASS, 148 files; Mypy: PASS, 85 source files;
  import-linter: all eight contracts kept.
- Exact local and fetched remote targets agree; implementation `e809cac` to final
  target changes the task handoff only. Rework diff whitespace check: PASS.
- Frozen specs/ADRs/product, world, memory, frontend, content and dependency paths
  are unchanged against `982988a`; frozen rule tree remains
  `837f2f90f6b242477e43c25aec9b359ec51ba331`.
- Separate P3-04 review closes P304-A1; see the round 2 result in
  [P3-04 acceptance review](P3-04-acceptance-review.md).

Tests used the author dependency environment with PYTHONPATH explicitly directed
to the exact local review checkout and fresh ignored output directories. Full
1348-test backend CI, frontend/generation and eight historical artifact comparisons
remain executor evidence; they were not rerun in this review. No model API,
credential access, implementation edit, main merge or P3-05 launch occurred.

### Round 2 handoff

1. base_commit: `2867beb44de384077f8998532c76d2d850cf795a`;
   result_commit: unknown (local uncommitted review report).
2. status: PASS independent acceptance review; no owner milestone sign-off implied.
3. scope_changed: no; review and report only.
4. human_interventions: zero additional interventions during this review.
5. rework_rounds: one acceptance recheck; no implementation authored by reviewers.
6. verification: independent checks above PASS; full CI and live calls NOT_RUN here.
7. open_questions: no blocking review findings. Integration and P3-05 remain
   separate downstream work.

## Publication during integration

The preceding local/uncommitted and no-merge statements describe the review turn.
On 2026-11-12 the owner subsequently requested integration into main. This report
is now included in that integration, without changing its findings or evidence.

## Initial review (historical)

## Brief

Date: 2026-11-12. Target: `584846d5c5477bfed3f8bbee30630a2ef0fda857`.
Remote: origin/task/P3-03-runtime, fetched and verified at the exact target.
Baseline: `982988ab9b87856dd62fe4cced426971b33b22df`.
Reviewed code candidate: `f97fbd7f0fcbc02b1c7a915cbee350dbde08d0e5`;
only the task handoff changes between that candidate and the final submission.
Review branch: task/P3-03-acceptance. This report is the only added file for this review.

## Result

**CHANGES_REQUESTED: one P2 shared fallback-seam integration blocker.**
The 250 task-specific tests pass. Allocation and persistence review found no other
established actionable defect. The finding below concerns the semantics of the
shared port used by both submitted tasks, not a request to implement all P3-05
integration inside P3-03 or to edit the other worker's files without coordination.

### P303-A1 — P2: typed malformed fallback failure aborts instead of substituting wait

Location: backend/src/living_island/agents/p3/runtime.py:544 (adapter call before
the try at line 545). Paired implementation: P3-04 submission `37a0384`,
backend/src/living_island/agents/llm/fallback.py, InvalidFallbackPlan.

The runtime calls fallback.decide outside its malformed-output handler. P3-04's
real FrozenRuleFallbackAdapter validates the rule result and raises the dedicated
InvalidFallbackPlan exception for a malformed plan. RuntimeP3.decide therefore
marks the runtime failed and propagates that exception; no wait DecisionRecord is
produced. The frozen llm-decision specification section 5 (line 554) instead
requires one wait substitute with the entire previous private state preserved.
Agent Interface section 3.3 explicitly distinguishes typed fallback failures from
programming exceptions. The shared ports module currently defines no common typed
failure carrier, so the two implementations disagree about this boundary.

Independent reproduction: load the exact P3-04 fallback module from `git show
37a0384:backend/src/living_island/agents/llm/fallback.py`, inject its real adapter
into the P3-03 transaction fixture, force budget-denied fallback, and substitute
only the frozen rule implementation with a malformed-plan fixture. The adapter
raises `InvalidFallbackPlan: malformed rule proposal`; runtime.decide propagates
it and export_state then raises `failed boundary requires checkpoint recovery`.
No API, source edit or change to either submission is needed to reproduce it.

Required closure: coordinate one shared typed failure contract through the
foundation owner, then align P3-03 and P3-04 with it. Add a cross-module regression
using the real fallback adapter, proving a single wait, fallback_error=INVALID_PLAN,
unchanged prior private state and a normally committable decision. Retain tests that
unexpected exceptions and IO faults terminate. Do not catch all ValueError or all
exceptions, and do not import a provider-private exception into a frozen port as
an unreviewed workaround. The independent P3-04 counter prerequisite remains a
separate open finding in P3-04-acceptance-review.md.

## Verification

- Independent exact task command: 250 passed in 272.31 seconds, including the
  five P3 task test files, test_sim_runs.py and tests/unit/persistence.
- Ruff check and format: PASS, 146 files. Mypy: PASS, 85 source files.
- Import-linter: PASS, all 8 contracts kept. git diff --check: PASS.
- Twelve frozen paths match the baseline, including world, frozen rule policy,
  shared P3 types/ports, memory, P3-04 files, dependencies, frontend, content and specs.
- Only twelve authorized files differ from the baseline. Legacy runtime change
  is the explicit P3 factory re-export; implementation candidate to target is docs-only.
- Independent allocation reviewer: PASS on slot enrollment, locks/generations,
  reservations, deferred settlement, prepared heads and idempotent offline recovery.
  No-I/O probes confirm six slots total 150000000 micro-CNY, maximum reservation
  81920 micro-CNY, and refusal of a seventh slot.
- Independent persistence/runtime reviewer: confirmed P303-A1 with the actual P3-04
  adapter; source pin/log/checkpoint/provenance audit found no additional defect.

Tests used the existing P3-03 dependency environment with PYTHONPATH pointing to
this review checkout and a fresh ignored worktree-local basetemp. Full 1320-test
backend CI, frontend checks, generation and eight historical hash comparisons are
executor evidence, not independently rerun or rehashed in this review. Live APIs,
credentials and paid trials were NOT_RUN; none is required for the reproduction.

## Handoff

Added this report only; no implementation changes, commit, push, main merge or
P3-05 launch. Preserved the existing local P3-04 acceptance report. Two independent
read-only reviewers assisted, with no implementation authorship or concurrent edits.

1. base_commit: `584846d5c5477bfed3f8bbee30630a2ef0fda857`;
   result_commit: unknown (uncommitted report).
2. status: CHANGES_REQUESTED.
3. scope_changed: no; independent acceptance review and shared-seam probe only.
4. human_interventions: 0 additional interventions after the initiating review request.
5. rework_rounds: 0 fixes during this review; one finding returned.
6. verification: independent 250 tests/static checks and focused probes PASS except
   the reproduced seam behavior; full CI and live calls NOT_RUN here.
7. open_questions: coordinated typed fallback failure contract and P303-A1 closure.
