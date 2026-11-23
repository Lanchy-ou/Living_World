# Gate 2 review: M13 plan and cards

- Reviewer: Claude Code session, independent of the planner.
- Reviewed: branch `task/P3.5-M13-cards` at `73abdca`, base `101361d`.
- Basis: P3.5 plan §3–§5, §8, §10; starter-content spec; M12 plan §2 note of 2026-11-23;
  owner instructions of 2026-11-23 (start M13 and M14 before the M12 Gate 3
  signature; add a performance card).

## Verdict

**Changes requested.** Four blocking items, all small. The structure, waves,
file ownership and test mapping are sound.

## Checks run by the reviewer

| Check | Result |
|---|---|
| Every starter-content test mapped once | CT-04–CT-13, CT-16, CT-18–CT-20 each map to exactly one card. CT-01–CT-03, CT-14, CT-15 and CT-17 stay in M12. Nothing is missing |
| Writable paths against M14 | Disjoint: M13 owns `content/packs/starter-v1/**`, `sim/v2/scenarios/**` and `tests/v2/m13/**`. M14 owns none of these |
| Paid calls | None planned. LLM-measured benefits are handed to M15 (D6) |
| Efficiency rules of M12 plan §2 | Copied into §6 |

## Findings

### B1: start conditions contradict the owner's decision

Wave 1 requires "PR-07 merged, compatibility equivalence passed, owner signed
M12". The owner decided on 2026-11-23 to start M13 and M14 before the M12
Gate 3 signature, while P3.5-PR-07 is still running. Change it:

- wave 1 (P3.5-CT-03, P3.5-CT-04 and the B2 card) starts on current
  `origin/main`;
- work that needs `sim/v2/cli.py` or `sim/equivalence/**` waits for PR-07 to
  merge;
- the M13 Gate 3 package (P3.5-CT-10) still waits for the signed M12.

Record the decision and its risk in §1: an M12 failure that needs an engine
fix may send M13 work back for rework.

### B2: the performance card is missing

The owner asked for a first M13 card that removes the copy cost. A profile of
the compatibility runner (`runs/m12-pr07-prefix-profile.dat`, 121 ticks)
puts about 85% of run time in `deepcopy`:

- pydantic `model_copy(deep=True)` on the decision path of
  `sim/v2/compat/policy_host.py`;
- the detached copies made by `World.pending_packets` in
  `world/v2/engine/tick.py`.

Add a wave 1 card, `P3.5-EN-08` (copy cost), with these terms:

- **Shared files:** request `policy_host.py` and `tick.py` under "Shared
  files". Both belong to merged M12 cards.
- **Goal:** remove copies that protect nothing (frozen or never-mutated
  data) and keep only the isolation the specs require. The detached packet
  delivery approved under OQ-P3.5-PR-05 must still hold.
- **Acceptance:**
  - the time per tick, measured before and after on the same case;
  - an equivalence rerun of the 20 acceptance seeds through PR-07's command
    after PR-07 merges, still identical per tick;
  - all existing tests pass.

It feeds D1, and it speeds up P3.5-CT-06's 40 held-out cases.

### B3: one heavy job at a time needs a mechanism

Both tracks and PR-07 share one host, which restarted several times under
parallel load. "One heavy job at a time" holds only if every executor can see
the other jobs. Add one rule to §6 for every M13 and M14 card:

- before a heavy job (full suite, matrix, week run, balance round, long fake
  workload), create `C:\Temp\li-heavy.lock` exclusively, with the card ID and
  start time inside;
- if the file exists, wait;
- delete it when the job ends, including on failure;
- a lock older than 12 hours with no live process may be removed, with a note
  in the handoff.

Use the same text as the M14 plan.

### B4: open questions sit at the top of the register

OQ-P3.5-M13-1 and OQ-P3.5-M13-2 are inserted at line 3 of
`docs/spec/open-questions.md`. Move them to the end, after the P3.5 entries.
The M14 branch also appends there, so the plan merged second rebases and
keeps both.

## Notes (no action)

- `backend/tests/v2/pack/test_recipe_free.py` exists (P3.5-CT-01, EN-22). It
  is a shared file, not an exclusive one. It is granted to P3.5-CT-03 for
  OQ-P3.5-M13-2, since no open card holds it. Record the grant in CT-03's PR.
- P3.5-CT-04's resumable driver should reuse PR-07's per-case receipt and
  resume mechanism once PR-07 merges, rather than add a second one.
- Card IDs `P3.5-CT-03`… share numbers with spec tests `CT-03`…; §4 says
  so. Keep it, but write "test CT-nn" and "card P3.5-CT-nn" in full in
  handoffs.
- D1's 30-minute budget is generous next to the measured 8–11 minutes per
  1,008-tick compatibility case under load. It is a sound starting point.

## Owner decisions (2026-11-23)

The owner approved all seven M13 decisions as recommended:

- **D1:** a 30-minute budget for one 1,008-tick week with three rule-based
  residents on `starter-v1`.
- **D2:** waves 1–3 form the §9 qualification stage.
- **D3:** P3-PERF-U1 is dropped for P3.5. Its branch stays intact.
- **D4:** Claude Code is the custodian for the single read-only M9 artifact
  search.
- **D5:** start with the published values. If §9 needs changed vectors,
  keep both sets and bring OQ-P3.5-M13-1 to the owner.
- **D6:** LLM-measured benefits and time use move to M15.
- **D7:** the narrow source-context recipe scan of OQ-P3.5-M13-2.

The owner also approved the review's changes: start before the M12
signature, the `P3.5-EN-08` performance card, and the host lock.

## Recheck at `62e4303`

**Accepted.** Rechecked `b91e19c` and `62e4303` against `73abdca`.

- B1: §1 records the early start and its risk. Wave 1 starts on current
  `origin/main`. Work on `sim/v2/cli.py` or `sim/equivalence/**` waits for
  PR-07, and P3.5-CT-10 waits for the signed M12.
- B2: card P3.5-EN-08 covers the shared-file requests, the detached delivery
  of OQ-P3.5-PR-05, a matched before-and-after timing pair, and a fresh
  20-seed rerun after PR-07 merges.
- B3: §6 carries the host lock in the same words as the M14 plan.
- B4: OQ-P3.5-M13-1 and OQ-P3.5-M13-2 sit at the end of the register.
- The owner's executor rules (local static checks and targeted pytest; the
  full suite on GitHub CI only; the test count; long runs once at the end of a
  card) are in §6 and on all nine cards.

Notes for dispatch:

- **Owner ruling, 2026-11-23:** the P3.5-PR-07 matrix runs 62 cases, the 20
  acceptance seeds plus P2's six-seed development matrix under OQ-060. The
  determinism rerun covers the 20 acceptance seeds. P3.5-EN-08's 20-seed
  rerun matches the second of these.
- P3.5-EN-08 asks the owner to confirm the 121-tick timing pair. The
  20-case campaign may use `--jobs 4`. Only the timing pair needs one
  worker. The executor runs the campaign, and Claude Code checks the
  receipts.
