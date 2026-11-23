# Gate 2 review: M14 plan and cards

- Reviewer: Claude Code session, independent of the planner.
- Reviewed: branch `task/P3.5-M14-cards` at `7af14f2`, base `101361d`.
- Basis: P3.5 plan §3–§5, §8–§10; memory-model, memory-formation,
  decision-loop and evaluation specs; M12 plan §2 note of 2026-11-23; owner
  instructions of 2026-11-23 (start before the M12 Gate 3 signature; CNY 20
  cap).

## Verdict

**Changes requested.** Three blocking items, all small. The plan is careful.
Its test mapping, file ownership, paid-step design and isolation rules are
sound.

## Checks run by the reviewer

| Check | Result |
|---|---|
| Every MM, MF, DL and EV test mapped once | 25 MM, 25 MF, 30 DL and 25 EV tests: none missing, none duplicated (scripted check). 14 EV tests go to M15, as listed |
| Round 3 halves deferred by M12 | MF-18 goes to P3.5-MF-01, DL-20 and DL-27 to P3.5-DL-05, EV-22 to P3.5-EV-03 |
| Writable paths against M13 | Disjoint: `memory/v2/**`, `agents/v2/{calls,context,recall,decision}/**`, `sim/v2/harness/**`, `analysis/v2*`, frontend feature folders. No M13 path |
| Paid calls | Exactly two (P3.5-DL-06 check, P3.5-EV-06 run), inside the CNY 20 cap, with a spend ledger and reservation before dispatch. Everything else uses the fake transport |
| Validate-once and recording rules | Stated in §6, including model output as the boundary |

## Findings

### B1: start conditions contradict the owner's decision

§2 says "All execution starts from accepted M12 including PR-07 and the
owner's M12 Gate 3". Wave 1 requires "M12 accepted". The owner decided on
2026-11-23 to start M13 and M14 before the M12 Gate 3 signature. Change it:

- waves 1 to 9 start on current `origin/main` as their own prerequisites
  merge;
- a card that needs `sim/v2/cli.py` waits for PR-07 to merge;
- the two paid steps (P3.5-DL-06, P3.5-EV-06) still wait for the signed M12,
  because a live run in the compatibility world relies on its equivalence.

Record the decision and its risk in §1: an M12 failure that needs an engine
or coordinator fix may send M14 work back for rework.

### B2: one heavy job at a time needs a mechanism

Add the same host lock rule as the M13 plan (M13 review, B3) to §6. The
long fake workload of P3.5-EV-05, full suites and M13's balance and week runs
must not overlap.

### B3: open questions sit in the middle of the register

OQ-P3.5-M14-1 and OQ-P3.5-M14-2 are inserted around line 800 of
`docs/spec/open-questions.md`, between P3-era entries. Move them to the end,
after the P3.5 entries. The plan merged second rebases and keeps both
branches' entries.

## Notes (no action)

- P3.5-DL-04 integrates fallback through `sim/v2/compat/policy_host.py`, which
  the M13 performance card (`P3.5-EN-08`) edits first. P3.5-DL-04 is in wave
  5, so the order works out; it rebases after that card.
- D6 needs the owner to name two additional resident profiles (names and five
  trait values each). Only P3.5-EV-05 (the five-resident rehearsal) needs
  them. Until then, synthetic fixture profiles are fine, as the plan says.
- The chain is long and mostly serial: 18 cards in 12 waves. That follows
  from the dependencies in the specs, not from the plan.
- P3.5-EV-07 deletes v1 files after the M14 signature. The card already asks
  for a per-file inventory and the owner's explicit approval.

## Owner decisions (2026-11-23)

The owner approved all seven M14 decisions as recommended:

- **D1:** DeepSeek Flash, with the alias resolution verified before
  spending.
- **D2:** a target of three game days, sized from measured costs within the
  CNY 20 cap. Hold the run and ask if fewer days fit.
- **D3:** a v2 manifest; P305-U1 stays parked.
- **D4:** confirm EV-D9; exploration needs no full trial registration.
- **D5:** the compatibility world, with one memory-on LLM resident (Ella)
  and rule-controlled companions.
- **D6:** schema 0.2 profiles in `content/characters/v2/` beside 0.1. The
  owner will name the two additional profiles before P3.5-EV-05; synthetic
  fixture profiles serve until then.
- **D7:** one prepared request of each of the six call kinds must be accepted
  and parsed before paid step 2.

The owner also approved the review's changes: start before the M12
signature, with the paid steps still after it, and the host lock.

## Recheck at `88c3807`

**Accepted.** Rechecked `52c51f3` and `88c3807` against `7af14f2`.

- B1: §1 records the early start and its risk. Waves 1 to 9 start on
  current `origin/main`, `sim/v2/cli.py` work waits for PR-07, and P3.5-DL-06
  and P3.5-EV-06 wait for the signed M12.
- B2: §6 carries the host lock.
- B3: OQ-P3.5-M14-1 and OQ-P3.5-M14-2 sit at the end of the register, after
  the M13 entries once both plans merge.
- The owner's executor rules are in §6 and on all 18 cards.

Owner input still needed later (not at dispatch):

- the two additional resident profiles before P3.5-EV-05 (D6);
- the sizes the cards propose for the P3.5-DL-05 replay, the P3.5-EV-05 cost
  rehearsal and the P3.5-EV-07 archive demonstration, each before its run.
