# Task M8: Apply approved P3 foundation contracts

## Brief

Task ID / title: M8 / Owner decision recording and CR-005 application.
Spec baseline: `659e1212f16e3f84ab60b370d4141c85b1d15d36` (independent P3-01 Gate 2 PASS).
Goal: freeze the approved package, apply exact CR-005 amendments and provide a
reproducible starting point for P3-02. No runtime implementation, live calls or main merge.
Lane: owner-approved documentation task, branch `task/M8-freeze`.
Allowed files: P3 specifications, plan, ADR, question register, task/decision/review
records and the two CR-005 target contracts. Application code, generated files,
world rules and existing P1/P2 DTO fields are outside scope.
Deliverables: eleven recorded dispositions, thirteen applied amendment blocks,
DeepSeek/CNY150 accounting, independent application review and exact baseline pin.
Acceptance: contracts contain the approved blocks; money never inherits the former
USD authorization; repeated registrations cannot mint another pilot allocation;
historical source citations and P1/P2 code trees remain intact.
Verification: diff check, exact-block comparison, local-link/fence/UTF-8 audit,
currency/provider scan, integer budget arithmetic and independent review.
Open risks: live alias availability, exact schema compatibility and certified input
counter remain P3-04/live-registration prerequisites, not completed integration.

## Handoff

### What changed

Recorded the owner's 2026-11-12 approval of all eleven M8 decisions and subsequent
replacement of OpenAI/USD112 with DeepSeek and an aggregate CNY150 API ceiling.
Selected the documented deepseek-flash alias in non-thinking mode for the initial
adapter. Rates use peak uncached CNY pricing; missing/mismatched evidence blocks calls.
Allocated CNY5 smoke, two CNY20 development cases and three CNY35 acceptance cases.
Money may bind before attempt limits; original acceptance thresholds remain unchanged.
The old USD approval was superseded before any call or spend.

Applied all thirteen exact CR-005 blocks to Agent Interface and Interface Contract.
Marked the four P3 owning specs, plan and ADR accepted; resolved OQ-082..090 and
updated downstream task readiness. The shared six-slot approval record prevents
registration revisions from duplicating the CNY150 grant, including enrollment crashes.
Preserved the prior independent P3-01 review as historical evidence.

### Commands and results

- `git diff --check`: PASS.
- Inline Python document/link/anchor, exact amendment, scope and arithmetic checks:
  PASS: 18 documents, 65 local links / 18 anchors, all 13 exact blocks, unchanged
  code trees and replay section, all seven V rows synchronized, CNY arithmetic correct.
- Independent reviewer `m8_application_review`: PASS, including follow-up review of
  one-time slot enrollment and its initialization crash windows; read-only, no authorship.
- Official DeepSeek pricing and Responses documentation were read; no provider call,
  account access, credential read or spend occurred. Sources are in M8-decisions.md.
- Runtime CI, type generation, OS-lock fault injection and live integration: NOT_RUN;
  documentation-only. These remain mandatory in the implementation tasks.

### Deviations

Owner-directed provider and currency/budget change supersedes the first approval.
No world-rule change, additional psychological feature or acceptance relaxation.
The M8 application SHA is recorded in a following documentation commit to avoid a
self-referential commit hash. The next executor starts from the final pin commit.

### Open questions

No remaining M8 design decision. P3-04 must certify the counter and adapter;
P3-05/07 must retain actual registration/implementation/model evidence. These are
implementation obligations and do not block provider-independent P3-02.

### Required fields

1. base_commit: `659e1212f16e3f84ab60b370d4141c85b1d15d36`;
   result_commit: `cc2bf87285e2728d7c433b92c265ce22bbd7e923` (application); follow-up pin commit records it in P3-02.
2. status: ACCEPTED (owner M8 plus independent documentation application review).
3. scope_changed: yes; owner replaced provider/USD allocation with DeepSeek/CNY150.
4. human_interventions: 2 after the initiating approval: API-budget clarification,
   then the superseding DeepSeek/CNY150 instruction.
5. rework_rounds: 0 independent-review rejections; status cleanup and enrollment
   precision were checked during the initial application review.
6. verification: document checks and independent review PASS; runtime CI, generation,
   counter certification, live calls and credentials NOT_RUN.
7. open_questions: no unresolved M8 decision; implementation prerequisites above.

### Final baseline pin

The application SHA above is now recorded in P3-02 and the M8 owner record. This
follow-up changes only task/decision metadata and start instructions. The executor
records the final pin commit as execution base and verifies the application ancestry.
