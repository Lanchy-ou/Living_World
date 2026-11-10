# P1 retrospective

This record covers the implementation cards in plan §2 through P1-09 acceptance and the
M4 sign-off (2026-11-09). The separate design-review draft repair predates implementation and is excluded
from the totals. Counts come from handoffs, acceptance records and the question register.
Earlier executor counts are labelled when a later rework has no updated count.

| Task record | Rework rounds | Recorded root causes | Human interventions | Scope changes |
|---|---:|---|---|---|
| [P1-00](P1-00-design-landing.md) | 0 | None recorded | Unknown (0 within the task) | No |
| [P1-01a](P1-01a.md) | 2 | Cross-object invariants were missed, Python defaults affected the wire format, and shallow copies were treated as immutable. Rework fixed probes individually before deriving checkpoint invariants and missed anchored paths and invalid committed errors. | 2 (two Gate 2 reviews and CR-001 option A, as grouped in the handoff) | Yes. Owner approved the question-log exception at M1. |
| [P1-01b](P1-01b.md) | 1 | Lax literal-zero validation, incomplete request/reply rules, incomplete namespace checks and a missing initialization-event check. | 0 in the initial handoff. Revised total unknown. | No in the initial handoff. |
| [P1-02](P1-02.md) | 2 | A global registry substituted for an underspecified port. Narrow interpretations and incomplete mutation and collision tests missed boundary cases. Round 1 trusted stored hashes instead of recomputing identity. | Unknown (2 known reviews) | Yes. Owner approved the CR-002 allowlist extension. Round 2 added no further scope. |
| [P1-03](P1-03.md) | 3 | Fruit accounting lacked an independent source ledger, stamina facts used the nominal cost, and the legal driver needed tick-start selection, a complete guard list and duration-aware actions. | Unknown (3 known inputs covering Gate 2 reviews and the OQ-021 decision) | No |
| [P1-04](P1-04.md) | 1 | Restore lacked prior event evidence, cooldown was checked at action start, coverage and the own-tile assumption were incomplete, OQ additions conflicted, and the append port admitted physical facts. | 2 (Gate 2 review and the owner's CR-003 decision and rework instructions) | Yes. Owner approved the CR-003 signature change. |
| [P1-05](P1-05.md) | 0 | No rework. The acceptance record carried storage hardening to P1-06. | 0 | No |
| [P1-06](P1-06.md) | 1 | The first resume demo restored an all-dead world. Fresh-run errors omitted the partial output path. | 0 in the initial handoff. Revised total unknown. | No. The card authorized the carried fixes. |
| [P1-07](P1-07.md) | 0 | No rework. The acceptance record carried the final-frame check and a test formatting fix to P1-09. | 0 | No |
| [P1-08](P1-08.md) | 1 | Baseline drift and OQ collisions, a missed payload domain check, an untested integral-decimal exemption, and too little fixture coverage for positions and seek. | 0 in the initial handoff. Revised total unknown. | No implementation scope change recorded. The owner approved the merge-order exception. |
| [P1-09](P1-09.md) | 0 | No rework. Gate 2 passed with two MINOR findings, recorded as OQ-052 and OQ-053. | 0 | No |

Total recorded rework rounds are 11. The phase-wide intervention total is unknown because
several task records give partial counts or only the initial handoff count.

## Change requests and lane order

| Request | Owner disposition |
|---|---|
| CR-001 | Option A separates malformed DTO shapes (agent `INVALID_PLAN`) from well-formed inputs that fail world validation. P1-01a and M1 recorded the contract clarification. |
| CR-002 | P1-02 passed verified content into observation initialization and enforced a shared entity ID namespace with reserved derived-ID prefixes. M2 recorded the approval. |
| CR-003 | P1-04 added a verified history prefix to `create_engine` for restore. P1-06 wired it into the runner. M2 recorded the approval. |

P1-08 merged before P1-05 with owner approval. The tasks shared no files or dependency,
and P1-05 still merged before P1-06 started. See the P1-08 Acceptance record.

## Open-question dispositions

The [register](../../spec/open-questions.md) has 39 P1 OQ entries, excluding three P0
entries and the three CRs. Numbering gaps are excluded. Dispositions come from the status
column, with `resolved` grouped with `closed`.

| Disposition | P1 entries | Notes |
|---|---:|---|
| Accepted | 29 | Includes the browser integral-decimal limitation, the continuation-only input decision, OQ-015 and OQ-017 (accepted at M4) and OQ-053. |
| Closed or resolved | 7 | OQ-012, OQ-014, OQ-018 (superseded by OQ-041), OQ-021, OQ-022, OQ-023 and OQ-040. |
| Open | 0 | None. |
| Deferred | 3 | OQ-049 (run naming under seed override), OQ-051 (replay warning threshold) and OQ-052 (intermediate-frame export check). All three move to P2. |

## Lessons for P2

- Derive cross-object invariants from the normative spec before implementation. Keep
  adversarial inputs such as valid-looking tampered checkpoints and mutable content in the
  regression suite.
- Resolve missing ownership or input at the frozen port before writing an implementation.
  CR-002 and CR-003 show the cost of compensating for a missing input later.
- Choose milestone demos that exercise the behavior being accepted. The tick-144 M2 and M4
  resumes preserve decisions by living residents. The P1-08 real-fixture smoke proves that
  the viewer and exporter agree on actual data.
- Record the final intervention count and scope disposition when accepting a rework. Several
  initial handoffs have useful counts that cannot serve as the final phase totals.
- Use P1-09's measurements as a starting point for an owner decision on replay warnings.
  The default-run deaths document an allowed outcome, while balance evaluation belongs to P2.
