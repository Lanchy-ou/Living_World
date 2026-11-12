# P3-01 independent review

Latest result: **Gate 2 PASS, round 2**, for
`659e1212f16e3f84ab60b370d4141c85b1d15d36`. See the appended round 2 record.
The round 1 findings below are retained as historical evidence. M8 owner approval
and implementation validation remain pending.

## Round 1

## Brief

Task ID / title: P3-01 review / Independent audit of the normative foundation package.

Reviewed commit: 729212ea1f5f44f1f35ddee4e24c83d9d8928c3f.
Baseline: 9bd45082002e87172312484a53c4787020bd584d.
Date: 2026-11-12.
Review branch: task/P3-01-spec-review.

Goal: assess completion against the P3-01 brief and identify actionable specification
defects before independent Gate 2 acceptance and owner M8 sign-off.
Non-goals: implement P3, amend author specifications, approve owner choices or make calls.
Allowed change: this review report only.

Reviewers were outside the P3-01 authoring team. The root integrated two focused
reviews of cognition/experience and decisions/recovery, and independently audited
delivery, evaluation, task scope and document invariants.

## Result

**CHANGES_REQUESTED.** All planned document categories are delivered, but two
specification issues require correction before Gate 2 PASS. This is not an M8
approval or a claim that the P3 runtime exists.

| ID | Priority | Finding | Location |
| --- | --- | --- | --- |
| G2-R1-01 | P1 / MAJOR | Repeated live continuation can reuse the same registered allocation | llm-decision-v0.1.md:548-553 |
| G2-R1-02 | P2 / MAJOR | Closed retrieval manifest cannot identify the required alternate selector | resident-experience-v0.1.md:327; p3-evaluation-v0.1.md:90-94 |

### G2-R1-01: Conserve budget across live continuations

[Decision/recovery section 7.1](../../spec/llm-decision-v0.1.md#71-completed-checkpoint)
restores the checkpoint's budget into fresh output and permits remaining registered
spend when no dispatch bytes follow its committed prefix. Section 6, lines 540-541,
keeps the source immutable. No registration/case-wide ownership or debit authority
is defined.

Counterexample: a clean checkpoint has a $2 allocation, $1 charged and $1 left.
Continuation A spends the last $1. Continuation B later resumes the same unchanged
checkpoint into another fresh directory and spends another $1. Each branch respects
its own restored $2 ledger; the registered case has spent $3. Concurrent resumes
produce the same problem. The evaluation receipt lifecycle does not specify a
single-use claim or repeated-resume refusal, and recovery uses the decision API.

Required correction: specify an authoritative, durable allocation-conservation
mechanism across a case's continuation lineage. Options include a single-owner
continuation handoff that refuses consumed checkpoints, or shared durable allocation
accounting. Separately authorized live forks may instead receive separate allocations.
Keep ordinary authorized continuation usable without unnecessary repeated approval.

Add sequential and concurrent double-resume vectors. Verify that crash recovery
cannot reset the ownership/debit state, and that a new output directory alone never
restores spent authorization.

### G2-R1-02: Record the actual retrieval strategy

[Experience section 5.3](../../spec/resident-experience-v0.1.md#53-inclusion-manifest-and-hashes)
fixes InclusionManifest.retrieval_profile to the literal recent-relevant-v0.
Sections 5.1/5.3 also require the baseline section 4 result and ranking.

[Evaluation VF-20](../../spec/p3-evaluation-v0.1.md#2-deterministic-fixtures-and-fault-matrix)
requires recent-only-fixture-v0, a distinct pinned identity and a different selection
order. Its concrete example returns sequences 7,6,5 rather than baseline 6,7,5.
Reporting the alternate identifier violates the closed manifest; reporting the
baseline identifier falsely describes the computation and conflicts with replay.
P3PolicyConfig.context_profile_id has no defined mapping that overrides these rules.

Required correction: define a registered retrieval identity and algorithm resolution
path, including the explicitly test-only alternative, and use it consistently in
context assembly, manifests, input identity and replay. Alternatively define an
explicit separate fixture schema/version. Do not silently relabel the alternate
algorithm or broaden production retrieval privileges.

VF-20 must verify truthful strategy identity, its expected order, and no-call
re-execution with that same pinned strategy.

## Completion assessment

- Submitted branch: task/P3-01-specs, fetched remote at reviewed commit.
- 15 changed documentation files: four owning specs, implementation plan, proposed
  ADR, question/amendment register, P3-01 handoff, six implementation cards and M8 sheet.
- The shared skeleton precedes member branches; four member integrations are recorded.
- Exact CR-005 amendment text is drafted in the register. Existing normative contracts
  have not been prematurely edited.
- Memory, environment/social interaction, cognitive transactions, fallback, logs,
  recovery, evaluation and character/debug UI all have explicit ownership.
- Six subsequent task cards are present with dependencies and file scopes.
- 29 proposed limit IDs are represented in the M8 sheet.
- M8-01 through M8-11 remain pending owner decisions. The pilot proposes $112 total
  ceiling, not an approved expenditure and not an estimate of expected actual spend.
- Application code, dependencies, content and generated files are unchanged.
  P3 implementation, live behavior and full runtime validation are not completed.

## Verification

| Check | Result |
| --- | --- |
| Fetch and revision comparison | Remote submission 729212e; base 9bd4508 |
| git diff --check 9bd4508 HEAD | PASS, exit 0 |
| Changed-file scope | Exactly 15 Markdown documentation files |
| Local Markdown links/anchors, UTF-8, fences and trailing whitespace | PASS; 57 links and 15 anchors |
| Baseline question-register prefix | Byte-identical |
| backend/frontend/content/scripts Git trees | Identical to baseline |
| New question IDs | OQ-085 through OQ-090 unique |
| Limit coverage | All 29 E/C/B/V IDs match M8 |
| P3 seed derivation | All six regenerated values match; exclusion from P2 seed lists checked |
| Proposed budget arithmetic | 33,792 microUSD maximum reservation per attempt; case caps cover their attempt maxima |
| Existing engine oracles, focused reviewer | Six passed: hearing/reply, out-of-range target, sleeping listener, invalid speech act, transient delivery/restore, resource actions including give |
| Provider capability/price premise | Snapshot, none effort, structured outputs and stated standard text rates corroborated in official model documentation; no account access or call tested |
| Full runtime CI, generated types and new P3 tests | NOT_RUN; documentation-only review, new runtime not implemented |
| Live calls / credential access | None |

Provider reference checked on 2026-11-12:
[OpenAI GPT-5.4 mini model documentation](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
This corroborates the stated premise only; registration still needs the specified
availability, pricing, schema and input-counter preflight.

No further blocking issue was established in experience capture, private perception,
goal transitions or the inspected physical examples. Preliminary questions about
restore-validation algorithms were not elevated: existing evidence rules and
saved deliveries/re-execution provide possible valid implementations.

## Handoff

### What changed

Added this independent review report. No author specification, code, acceptance record
or owner decision was modified. No author branch was committed, pushed or merged.

### Commands and results

Verification is recorded above. Review work uses the isolated root checkout at
D:/Codex/.codex/worktrees/p3-01-spec-review/Living_World.
The cognition reviewer used its own isolated task/P3-01-review-cognition checkout.
The decision reviewer used the root review checkout read-only after its worktree
creation tool stalled. Both reviewed the exact submitted commit.

### Deviations

One focused reviewer shared the root's immutable review checkout for read-only
inspection. No concurrent edits or author-team review were involved.

### Open questions

Resolve G2-R1-01 and G2-R1-02, then re-review the corrected commit. M8 owner decisions
remain pending; this review does not choose provider, limits or live allocations.

### Required fields

1. base_commit: 729212ea1f5f44f1f35ddee4e24c83d9d8928c3f (review target);
   result_commit: unknown (uncommitted review report).
2. status: CHANGES_REQUESTED.
3. scope_changed: no; independent review and completion report only.
4. human_interventions: 0 additional interventions after the initiating review request.
5. rework_rounds: 0 in this review; this is round 1.
6. verification: document/inventory/link/seed/budget checks and six focused existing
   engine oracles passed; full runtime CI, new implementation and live calls NOT_RUN.
7. open_questions: two review findings; owner M8 choices remain pending.

## Round 2: targeted rework review

Date: 2026-11-12.
Reviewed commit: `659e1212f16e3f84ab60b370d4141c85b1d15d36`.
Rework base: `729212ea1f5f44f1f35ddee4e24c83d9d8928c3f`.

**Gate 2 PASS for the P3-01 documentation package.** Both prior findings are
closed; no new actionable finding was established in the rework and its affected
consumers. This does not approve M8 choices, authorize live spending, or certify
an implemented runtime. The two focused reviewers remained independent of the
author team and read the exact target without changing author files.

### Findings disposition

- **G2-R1-01: CLOSED.** Decision sections 4.2, 6 and 7 define one enrolled case
  authority, an OS-managed process lock, current-head-only continuation and durable
  reservations before dispatch. Prepared-head reconciliation preserves consumption
  across publication crashes; offline recovery imports each reservation once.
  Checkpoints are replay mirrors, not fresh grants. Recorded replay never accesses
  live authority. BD-18..27 cover sequential, concurrent, crash and replay cases.
  Ordinary clean continuation uses the original remaining allocation without
  another approval. Evaluation, plan, ADR, OQ-090, M8 and downstream cards agree.
- **G2-R1-02: CLOSED.** Experience sections 4/4.1/5 define the actual strategy ID,
  closed profile binding and full-rank retrieval result. Configuration, retained
  context-profile.json, source pins and complete manifests must agree. Replay reruns
  that pinned algorithm; alternate selection is fake-only. EX-11/12 and VF-20 cover
  distinct order, empty recall, bounds and invalid identities. Downstream ownership
  is consistent: P3-02 defines the ports/bindings; P3-06 supplies alternate test code.

### Verification

| Check | Result |
| --- | --- |
| Exact submitted revision | HEAD and fetched origin/task/P3-01-specs at 659e1212 |
| git diff --check 9bd4508 HEAD | PASS, exit 0 |
| Scope | 14 Markdown files in rework; 15 in the full package |
| Inline Python UTF-8, balanced fences and local link/anchor audit | PASS, 59 links and 17 anchors across all 15 package documents |
| backend/frontend/content/scripts trees vs 9bd4508 | Identical |
| Baseline open-question prefix | Byte-identical |
| M8 numerical limit rows vs 729212e | All 29 rows byte-identical |
| Independent allocation arithmetic and crash-path review | PASS: reserve165, settled105, next60; no early refund or duplicated grant |
| Independent retrieval calculations | PASS: baseline [5,4,1,3,2,0], alternate [5,4,3,2,1,0]; 16-of-17 cutoff and EX-05 tie order |
| Cross-document review | Plan, evaluation, ADR, question register, M8 sheet and P3-02..07 synchronized |
| Runtime CI, real lock/crash tests, generation and new P3 tests | NOT_RUN; documentation-only. Required implementation proofs remain assigned to later tasks |
| Live calls / credentials / spend | None / none / zero |

Round 1 engine and provider-premise checks were not rerun: affected implementation
trees and numerical/provider choices are unchanged. No runtime result is inferred
from the paper test vectors. Authority support is explicitly single-host; distributed
authority migration is outside this proposal.

### Handoff (round 2)

What changed: appended this review and updated its latest-result pointer; preserved
the historical first-round findings. No author specifications or owner dispositions
were edited. No commit, push or merge to main was performed.

Commands/results: read exact rework diffs, ran git diff --check and the inline Python
document/scope/tree/prefix/limit audit above; all checks passed. Both independent
focused reviewers returned PASS. Both used the root review checkout read-only.

Deviations: none in review scope; read-only reviewers shared the immutable target.
Open questions: existing M8-01..11 and associated OQ dispositions remain owner choices.
Proceed to M8 review; implementation starts only after its required decisions and
contract amendments are applied.

1. base_commit: 659e1212f16e3f84ab60b370d4141c85b1d15d36 (review target);
   result_commit: unknown (uncommitted review report).
2. status: PASS (independent documentation Gate 2).
3. scope_changed: no; targeted rework review and affected-consumer checks only.
4. human_interventions: 0 additional interventions after the initiating review request.
5. rework_rounds: 1; this is review round 2.
6. verification: checks listed above PASS; implementation CI, lock/crash execution,
   generated types and live calls NOT_RUN.
7. open_questions: no remaining review finding; M8 owner decisions remain pending.
