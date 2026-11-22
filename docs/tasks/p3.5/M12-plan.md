# P3.5 M12 plan: the new engine runs the old world

Milestone M12 of the [P3.5 plan](../../plans/p3.5-implementation-plan-v0.1.md)
§4 is done when the v2 engine with the compatibility pack matches the
committed v1 projections on the fixed seed set, with the rule-based policy
through its adapters, and the synthetic-pack engine tests and the rule-pack
extension test pass (ADR 0007 D8, ADR 0010, ADR 0014 D3). The owner checks
the equivalence report at Gate 3.

Spec baseline: `8c803ed`, main after PR #5. All eight P3.5 specs are frozen;
the tests named below are the acceptance tests of those specs.

## 1. Decisions for the owner

These are set by the M12 task cards (protocol §11.1 asks the cards to set
the tag and the removal point). The owner approved all five as recommended
on 2026-11-19, so D5 now applies to every M12 card.

| # | Decision | Recommended answer | Why |
|---|---|---|---|
| D1 | Where v2 code lives | Beside v1, never inside it: `world/v2` (protocol, rules, engine), `sim/v2` (coordinator, compatibility pack binding and adapters), `sim/equivalence` (projection format and extractors), `persistence/v2`, `agents/v2` (the port). v1 modules are not edited | v1 stays frozen and keeps running until the removal point; the import-linter purity of `world` extends to `world/v2` |
| D2 | Archive tag and removal point | Tag `v1-archive` on the main commit where P3.5-PR-03 merges. Remove the v1 engine only after M14 Gate 3, in a separate task | The P3 LLM runtime (`sim/p3.py`, `agents/p3`) runs on the v1 world until the M14 decision loop replaces it; removing v1 earlier leaves no LLM path |
| D3 | Round 3 edge cases with a memory or evaluation half | M12 tests the world side; the memory count (MF-18), the qualifying-use count (EV-22) and the recall manifest (DL-20, DL-27) go to the M14 cards | Memory, evaluation and the decision loop are not built in M12 |
| D4 | Size of the v1 fixtures | At most 50 MiB in total; above that, P3.5-PR-03 stops and asks | Fixtures live in Git |
| D5 | Review weight for code tasks | Gate 1 plus one independent Gate 2 round and one recheck; an interface-preserving edge case found in review becomes a test in a named card instead of blocking | Spec review needed many rounds; code has tests that catch regressions |

## 2. Order and parallel work

| Wave | Cards | Starts when |
|---|---|---|
| 1 | [P3.5-PR-03](P3.5-PR-03.md) v1 archive and projections; [P3.5-PR-04](P3.5-PR-04.md) protocol types; [P3.5-RR-01](P3.5-RR-01.md) rule loader and validator | Now |
| 2 | [P3.5-CT-01](P3.5-CT-01.md) engine-test pack; [P3.5-CT-02](P3.5-CT-02.md) compatibility pack | P3.5-RR-01 merged |
| 3 | [P3.5-EN-01](P3.5-EN-01.md) engine core | P3.5-PR-04, P3.5-RR-01, P3.5-CT-01 merged |
| 4 | [P3.5-EN-02](P3.5-EN-02.md) act settlement; [P3.5-EN-04](P3.5-EN-04.md) physiology and stops | P3.5-EN-01 merged |
| 4b | [P3.5-RR-02](P3.5-RR-02.md) footprint flag refusal (owner decision on CR-P3.5-EN-01, 2026-11-20) | Now; touches no file of an open card |
| 5 | [P3.5-EN-03](P3.5-EN-03.md) processes; [P3.5-EN-06](P3.5-EN-06.md) speech; [P3.5-PR-05](P3.5-PR-05.md) coordinator | P3.5-EN-02 merged (P3.5-PR-05 needs only P3.5-EN-01 to start) |
| 6 | [P3.5-EN-05](P3.5-EN-05.md) perception and watching | P3.5-EN-02, P3.5-EN-04, P3.5-EN-06 merged |
| 7 | [P3.5-EN-07](P3.5-EN-07.md) persistence and replay | P3.5-EN-01 to P3.5-EN-06 merged |
| 8 | [P3.5-PR-06](P3.5-PR-06.md) policy adapters and bridge | P3.5-PR-03, P3.5-PR-05, P3.5-CT-02, P3.5-EN-07 merged |
| 9 | [P3.5-PR-07](P3.5-PR-07.md) equivalence and the M12 report | All others merged |

Each card is one branch (named in the card), one worktree and one Gate 2. A
card may start before its dependencies merge only on its own new files, and
it rebases before review.

From the P3.5-EN-03 and P3.5-EN-06 rechecks on, the rest of M12 runs under the
[orchestration runbook](M12-orchestration.md) (owner decision, 2026-11-21).
The runbook replaces the one-recheck limit of D5 with a fix-until-pass
review loop, and records how decisions are made while the owner is away.
On 2026-11-22 the owner extended the unattended run to all of P3.5, with
provisional Gate 3 packages ([P3.5 runbook](P3.5-orchestration.md)).

## 3. File ownership

Each path has one owner. Concurrent branches never write the same file.

| Path | Owner |
|---|---|
| `world/v2/__init__.py` | Shared: P3.5-PR-04 and P3.5-RR-01 both create it with exactly `"""Living Island v2 world lane (P3.5)."""` and a final newline, so identical additions merge cleanly |
| `world/v2/protocol.py` (or `protocol/`), `backend/pyproject.toml` import-linter section | P3.5-PR-04 |
| `world/v2/rules/**`, `content/vocabulary/**` | P3.5-RR-01; then P3.5-RR-02 |
| `world/v2/engine/{__init__,ids,state,tick,validate,items,kernel,limits,events}.py` | P3.5-EN-01; after P3.5-EN-01, `tick.py` and `state.py` change in one branch at a time, noted in its handoff |
| `world/v2/engine/settle.py`, `match.py`, `conditions.py`, `effects.py`, `chance.py`, `descriptors.py` | P3.5-EN-02 (P3.5-EN-01 creates the `settle.py` stub) |
| `world/v2/engine/processes.py`, `world_rules.py` | P3.5-EN-03 (stub from P3.5-EN-01) |
| `world/v2/engine/physiology.py`, `stops.py` | P3.5-EN-04 (stub from P3.5-EN-01) |
| `world/v2/engine/perception.py`, `observe.py`, `reports.py` | P3.5-EN-05 (stub from P3.5-EN-01) |
| `world/v2/engine/speech.py`, `terms.py` | P3.5-EN-06 (stub from P3.5-EN-01) |
| `world/v2/engine/snapshot.py`, `persistence/v2/**` | P3.5-EN-07 |
| `sim/v2/__init__.py` | Shared: P3.5-CT-02 and P3.5-PR-05 both create it with exactly `"""Living Island v2 coordination (P3.5)."""` and a final newline |
| `sim/v2/compat/{__init__,config,registry}.py`, `content/packs/compat-v1/**` | P3.5-CT-02 |
| `sim/v2/{runner,turns,manifest}.py`, `agents/v2/**` | P3.5-PR-05 |
| `sim/v2/compat/{adapters,bridge,receipts,policy_host}.py` | P3.5-PR-06 |
| `sim/equivalence/{__init__,projection,v1_extract}.py`, `scripts/gen_v1_projections.py`, `backend/tests/fixtures/v1_projection/**`, `backend/tests/equivalence/**` | P3.5-PR-03 |
| `sim/equivalence/{v2_extract,compare}.py`, `sim/v2/cli.py`, `docs/tasks/p3.5/M12-equivalence-report.md` | P3.5-PR-07 |
| `backend/tests/fixtures/v2/packs/engine-test*/**` | P3.5-CT-01; then P3.5-RR-02 |
| `backend/tests/v2/engine/conftest.py` | P3.5-EN-01 (shared engine test fixtures, owner decision 2026-11-20); after P3.5-EN-01, one branch at a time, noted in its handoff |
| Wave 5 shared engine files | P3.5-EN-03: `tick.py`, `state.py`, `settle.py`, `effects.py`; P3.5-EN-06: `validate.py`, `events.py` (owner decisions, 2026-11-21). During recheck, the orchestrator allocated one additional edit to EN-03 in merged EN-04's `stops.py` under M12 runbook sections 5 and 6.1. It preserves a contribution's fixed start failure through its scheduled completion (B3, 2026-11-22) |
| Wave 6 shared engine files | EN-05 held `tick.py`, `state.py` and the common engine test fixture for packet capture and acknowledgement. It updated `effects.py`, `settle.py`, `kernel.py`, `items.py`, `processes.py` and `physiology.py` for the packet data recorded in the [handoff](P3.5-EN-05.md). The [independent review](P3.5-EN-05-review.md) records the scope, adjusted tests, provisional container and progress assumptions, and proposed WAP-19 change. |
| `backend/tests/v2/<area>/**` | The card that names that directory |

Paths without a prefix are under `backend/src/living_island/`.

## 4. Where each acceptance test is run

| Spec tests | Card |
|---|---|
| WAP-11 (schema), WAP-12 (shape), WAP-13 | P3.5-PR-04 |
| WAP-02, WAP-10, WAP-20, WAP-22, WAP-27; EN-02, EN-17, EN-18, EN-19 | P3.5-EN-01 |
| WAP-01, WAP-06, WAP-21; EN-03 to EN-07, EN-08 (actions), EN-27, EN-28, EN-33, EN-35, EN-36; RR-06 to RR-10, RR-12, RR-14, RR-15, RR-17, RR-18, RR-26 to RR-28, RR-32, RR-35, RR-37; the ADR 0014 D3 rule-pack test | P3.5-EN-02 |
| EN-09, EN-10, EN-11, EN-30, EN-31, EN-34; RR-19, RR-20, RR-21, RR-38 (run time) | P3.5-EN-03 |
| WAP-04, WAP-18, WAP-24, WAP-33 (test pack); EN-12 (test pack), EN-13 to EN-16, EN-23 (analogue), EN-24; RR-16 | P3.5-EN-04 |
| WAP-05, WAP-07, WAP-08, WAP-14, WAP-17, WAP-19, WAP-31, WAP-32 (analogue), WAP-36, WAP-37; EN-25, EN-26, EN-32; RR-13 | P3.5-EN-05 |
| WAP-03, WAP-09, WAP-29; EN-08 (utterances) | P3.5-EN-06 |
| WAP-05, WAP-19 (restore), WAP-11 (saves), WAP-16 (engine); EN-20, EN-21, EN-29; RR-22 (boundary), RR-23 | P3.5-EN-07 |
| RR-01 to RR-05, RR-11, RR-22 (validator), RR-24, RR-25, RR-29, RR-30, RR-31, RR-33, RR-34, RR-36, RR-38 (validator) | P3.5-RR-01 |
| CT-14; EN-22 | P3.5-CT-01 |
| CT-01, CT-03, CT-15 and CT-17 (load); WAP-34; RR-29 (compatibility pair) | P3.5-CT-02 |
| WAP-02, WAP-12, WAP-16 (end to end, with fallback turns) | P3.5-PR-05 |
| WAP-23, WAP-25, WAP-28, WAP-30, WAP-35 | P3.5-PR-06 |
| WAP-15, WAP-26, WAP-32 and WAP-33 (against v1); CT-02, CT-15, CT-16 (canteen), CT-17 (run time), the compatibility halves of CT-10 and CT-11; EN-01, EN-08 (compatibility draws), EN-12, EN-13 (compatibility), EN-23 | P3.5-PR-07 |
| v1 sides of WAP-23, WAP-27 to WAP-30, WAP-32, WAP-33, WAP-35, EN-23, CT-15, CT-17 | P3.5-PR-03 |

The other starter-content tests (CT-04 to CT-09, CT-12, CT-13, CT-16 for
the clay pot, CT-18 to CT-20) belong to M13. The memory, decision-loop and
evaluation tests belong to M14 and M15, except the M12 row of evaluation §8.

## 5. The eight Round 3 edge cases

Handed to M12 by the Gate 2 Round 3 reviews
([world](P3.5-SP-01-review-world.md), [resident](P3.5-SP-01-review-agent.md))
and the owner's Round 3 decision (decision sheet §3, row 5).

| Edge case | Card | Part outside M12 (D3) |
|---|---|---|
| One cue upgrade across receipt restore | P3.5-PR-06 | — |
| Competing captured fits | P3.5-EN-02 | — |
| Removal from a dense tile | P3.5-EN-02 | — |
| The 4b snapshot excludes new subjects | P3.5-EN-03 | — |
| Gift on the wake boundary | P3.5-EN-05 | Memory count (MF-18): M14 |
| Start versus settle audiences | P3.5-EN-05, restore half P3.5-EN-07 | — |
| Split source and return | P3.5-EN-02 | Qualifying use (EV-22): evaluation work |
| Unfit deliberate recall | P3.5-PR-05 | Recall manifest (DL-20, DL-27): M14 |

## 6. Rules for every card

- Strict lane: Gate 1 (the commands in each card, from AGENTS.md), then an
  independent Gate 2 by a reviewer who did not write the work; the owner
  signs Gate 3 for M12 on the equivalence report.
- Engine tests use the `engine-test` pack and packs extending it; only
  PR-06 and PR-07 run `compat-v1`.
- v1 tests stay green in every branch; v1 modules are not edited (D1).
- A contradiction with a frozen spec goes through the change-request steps
  (plan §7); a missing or ambiguous rule goes to `docs/spec/open-questions.md`
  with the smallest reversible assumption, flagged in the handoff.
- Each card's handoff follows the template, with the seven fields.
- The frozen v1 registration check inspects the loaded `living_island`
  modules, so a v2 import during pytest collection can fail v1 tests
  (P3.5-RR-01 review, N2). Gate 1 runs
  `tests/p3/test_trial_registration.py` in the same pytest session as the
  card's own tests. If it fails, the card moves its v2 imports inside the
  tests.
- Validate once, at the boundary (AGENTS.md workflow rules). For example,
  the engine wraps validated rules and packs in typed structures once, and
  later code reads those structures without checking each field again.
