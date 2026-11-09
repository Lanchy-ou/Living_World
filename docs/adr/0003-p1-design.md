# ADR 0003: P1 design

- Status: accepted
- Date: 2026-11-08
- Task: P1-00 (specs: `docs/spec/agent-interface-v0.1.md`,
  `docs/spec/p1-replay-frontend-v0.1.md`; plan: `docs/plans/p1-implementation-plan-v0.1.md`)

## Context

P1 ("The World Runs") makes the landed World Rules v0.1 executable: a deterministic world runs
1,008 ticks with non-LLM residents, saves and restores, and can be inspected in an offline
browser replay. This ADR records the decisions that shape that work.

## Decisions

- **Resident runtime:** one `ResidentRuntime` per resident, with `ingest` (take the world's
  delivery) and `decide` (propose an `ActionPlan`). Residents never touch world state.
- **Policies:** P1 ships three: Random, Scripted and Recorded. No LLM provider and no
  survival intelligence in P1.
- **DecisionContext in P1:** allowed, through amendment A1 (applied by P1-01a), which amends
  the current prohibition in Interface Contract §2.3 and clarifies event-type ownership.
- **Replay first:** no live server. The backend exports a single-file `ReplayBundle` of
  per-tick display frames; the browser validates and plays it locally. Amendment A2 (applied
  by P1-01b) adds the replay contract.
- **Resume:** continuation only. A resumed run writes only post-checkpoint records to a new
  directory and does not export a replay; a full bundle comes from `reexecute`.
- **Process:** 10 tasks plus P1-00, two lanes (world and side), at most two active workers,
  Gate 1 and Gate 2 for every task, Gate 3 at milestones M1–M4.

## Consequences

- The agent-interface and replay specs are approved but their contract changes are not
  effective until A1 and A2 land; the interface contract and world rules are unchanged until then.
- Changes to frozen contracts go through the change-request steps in the plan (§7).

## Addendum: M1 (2026-11-09, P1-01a)

- **A1 landed** in `interface-contract-v0.1.md` and `world-rules-v0.1.md` (marked `[A1]`).
  The world/agent contract is frozen for P1; later changes need a change request (plan §7).
- **CR-001 (owner-approved, option A):** Interface Contract §4 "invalid parameter shape"
  covers well-formed DTOs with invalid values, which world settles as a bounded failure.
  Malformed shapes cannot be constructed and are `INVALID_PLAN` in agents (Agent Interface §3.1).
- OQ-004 to OQ-008 accepted as recorded in `docs/spec/open-questions.md`.
