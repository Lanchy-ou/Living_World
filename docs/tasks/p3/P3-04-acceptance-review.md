# P3-04 independent acceptance review

## Round 2 result (2026-11-12)

**PASS at `41d5ecd4e652a2c4090247673c610939e8c7326a`. P304-A1 is closed.**
This section supersedes the initial CHANGES_REQUESTED disposition below, which is
retained as review history. No new actionable finding was established.

The production counter now includes both message contents, the provider's schema
prefix and spaced schema JSON, and all five structural token IDs. The retained
Flash-1017 tokenizer supports the UTF-8-byte nonexpansion proof: identity
normalization, nonexpanding splits, a complete byte alphabet and merge-only BPE.
Unknown counter identities/versions still refuse before dispatch; the bound is
enforced at the 32768-token limit without truncating requests.

Independent provider review verified the pinned official Responses converter,
renderer and API-alignment evidence. Public downloads of the exact release card,
encoding reference and tokenizer matched retained SHA-256 values. The full P3
suite also verifies all 19 retained artifact byte lengths and hashes. This is an
offline proof for the documented model/template. Future live registration must
still revalidate the mutable model alias/version/pricing and pin the implementation;
this review does not certify an unchanged future hosted service.

The coordinated shared exception has identical ports.py blobs on both branches
(`fa585f702ced1994632caa0018e93d0ae077b6e5`). The real P3-04 production fallback was
loaded with the reviewed P3-03 runtime at `2867beb`; all 20 cross-module tests passed.
Malformed proposals now yield one committable wait with unchanged prior private
state. Unclassified programming and IO exceptions remain fatal.

Independent checks:

- All P3 tests: **304 passed in 10.22 seconds**, including 125 adapter/fallback cases.
- Provider reviewer: 21 targeted proof/schema/counter tests passed.
- Ruff check/format: PASS, 142 files; Mypy: PASS, 83 source files;
  import-linter: all eight contracts kept.
- Exact local and fetched remote targets agree; final commit changes the handoff
  only. Diff whitespace check passes in the target checkout with its attributes;
  the upstream license's preserved CRLF bytes are intentional.
- Frozen specs/ADRs/product, world, memory, frontend, content and dependency paths
  are unchanged against `982988a`; frozen rule tree remains
  `837f2f90f6b242477e43c25aec9b359ec51ba331`.

Full 1267-test backend CI, frontend/generation and eight historical artifact
comparisons remain executor evidence; they were not rerun in this review.
No model API, credential access, implementation edit, main merge or P3-05 launch.

### Round 2 handoff

1. base_commit: `41d5ecd4e652a2c4090247673c610939e8c7326a`;
   result_commit: unknown (local uncommitted review report).
2. status: PASS independent acceptance review; no owner milestone sign-off implied.
3. scope_changed: no; review and report only.
4. human_interventions: zero additional interventions during this review.
5. rework_rounds: one acceptance recheck; no implementation authored by reviewers.
6. verification: independent checks above PASS; full CI and live calls NOT_RUN here.
7. open_questions: no blocking review findings; pre-live alias revalidation remains
   an integration prerequisite already documented by the executor.

## Publication during integration

The preceding local/uncommitted and no-merge statements describe the review turn.
On 2026-11-12 the owner subsequently requested integration into main. This report
is now included in that integration, without changing its findings or evidence.

## Initial review (historical)

## Brief

Date: 2026-11-12. Target: `37a0384a4701ec0a2ce7f25d35af67721ab4693f`, verified
against fetched origin/task/P3-04-adapters. Baseline: `982988ab9b87856dd62fe4cced426971b33b22df`.
Review branch: task/P3-04-acceptance. Allowed changes: this report only.
Goal: review the adapter/fallback implementation and its completion claim without
changing code, calling a provider, reading credentials or merging main.

## Result

**CHANGES_REQUESTED for full P3-04 acceptance.** One P2 delivery gap remains.
The offline adapter/fallback implementation passes the checks below, and the
production refusal is correct. This finding does not request removing that refusal.

### P304-A1 — P2: production counter acceptance prerequisite is not delivered

Location: backend/src/living_island/agents/llm/provider.py:286-288;
docs/spec/llm-decision-v0.1.md:167-172;
docs/tasks/p3/P3-04.md:176-181 and 211-213.

Production count_input_tokens validates the request then unconditionally raises
INPUT_COUNTER_UNAVAILABLE. complete calls that method, so every valid production
request refuses before transport access. The fake counter proves only its own
synthetic byte-unit count; its README explicitly disclaims a DeepSeek token bound.

The frozen specification expressly makes the counter proof and fixture suite
adapter acceptance prerequisites. The execution instruction requires an exact
counter or proven conservative bound, and refusal when that cannot be established.
That refusal is required behavior, not a waiver of the missing deliverable. Local
fake tests remove the need for paid integration; they do not certify the production
input bound. The handoff's blanket PASS/no-deviation completion interpretation
therefore overstates readiness. P3-05 cannot complete its live smoke/M9 path using
this production adapter as submitted.

Required closure: deliver the reviewed production counter/bound, pinned artifacts
and framing/model correspondence evidence, plus offline boundary fixtures covering
the complete charged request. Keep unavailable/mismatched counters fail-closed.
If the proof cannot be supplied under the existing provider contract, record an
explicit unresolved prerequisite and obtain a separately approved scope/spec change
before calling this task fully accepted. Do not silently defer it to P3-05, use the
fixture counter for production, weaken budget admission or make paid calls to bypass it.

## Independent verification

- Exact remote target, eight-file allowed scope and final handoff-only difference
  from implementation 5e2d0e4: PASS.
- Task-specific tests: 106 passed in 5.16 seconds.
- Entire P3 suite: 285 passed in 7.72 seconds.
- Ruff check/format: PASS (142 files); Mypy: PASS (83 source files);
  import-linter: all 8 contracts kept.
- Thirteen frozen source/spec/content/dependency/frontend paths are identical to
  the baseline. Rule tree remains 837f2f90f6b242477e43c25aec9b359ec51ba331.
- git diff --check: PASS.
- Independent read-only provider reviewer: confirms P304-A1; production refusal,
  absent/empty body, invalid UTF-8 and cap-plus-one mapping probes passed. No further
  actionable transport/mapping defect was established.
- Root inspected fallback projection, staged state ownership, continued fallback,
  return/re-entry and frozen-rule validation; no additional actionable finding.

The existing author environment was used with PYTHONPATH explicitly directed to
the exact review checkout. No implementation/test/spec files were changed.
The executor's 1,248-pass full suite and eight historical hashes were read as
executor evidence, not claimed as independent reruns here. Full backend/frontend
CI and live integration were NOT_RUN in this acceptance review; the missing
counter proof is not resolved by repeating those checks.

## Handoff

What changed: added this review report only. No commit, push, merge or downstream
task launch. Deviations: none; one independent read-only provider reviewer assisted.
Open question: P304-A1 must close or receive an explicit revised scope disposition.

1. base_commit: 37a0384a4701ec0a2ce7f25d35af67721ab4693f;
   result_commit: unknown (uncommitted review report).
2. status: CHANGES_REQUESTED for full acceptance.
3. scope_changed: no; independent review only.
4. human_interventions: 0 additional interventions after the initiating request.
5. rework_rounds: 0 fixes during this acceptance review; one finding returned.
6. verification: independent checks above PASS; full CI/historical reruns/live calls NOT_RUN.
7. open_questions: production input-counter certification and its acceptance scope.
