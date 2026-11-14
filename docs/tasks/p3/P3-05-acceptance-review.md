# P3-05 central acceptance / M9

Date: 2026-11-14. Reviewed delivery: `e0d6c16` on
`task/P305-R2-u4-authorization`. Approved runtime:
`506cfaf65db92fd2079bd36a2a906100ac55d2d7`.

## Disposition

PASS for the one-resident integration and M9 smoke. The owner instructed
central review followed by publication if no issue was found. This records
that conditional acceptance; it does not start P3-06 or merge main.
The two earlier V-05 failures retain their original outcomes.

## Direct central verification

- Verified the canonical registration file digest
  `9bc3e90bf3bbc05f01acc96029f15f85aa1c8a000bc943e6d4357a3fb0428017`.
- Compared all 107 registered implementation/input pins with both the approved
  Git revision and the delivered files. No implementation drift.
- Read all 24 segments: Ella has 22 successful LLM decisions and 22 parsed
  calls, no substitution, validation rejection or unknown usage. Charged input
  is 372348, output 2315 and money 763216 micro-CNY. Maximum reserved input
  is 29962, within the unchanged 32768 limit.
- Recomputed the 123 recorded artifact digests and directly compared each
  source/replay pair. All matched, including final checkpoint, trace and replay.
- Rehashed all 1059 final snapshot entries and 476 pre-close entries: all match.
- Reviewed the independent Gate 2 and original-reader lineage verification.
  The replay harness caches only successful validations with exact checkpoint,
  origin and ordered log contents as its identity. No production code changed.
  A separate uncached end-to-end replay was not run; this limitation is retained.
- The unchanged code has recorded executor results of 1705 passes and three
  existing skips. Central review did not rerun that full suite or call an API.
  The 196 older historical digests are covered by the executor and independent
  review, rather than a third separate central historical audit.

## Retention and remaining scope

All trial registrations, failures, grants, ledgers, receipts, snapshots and
replay artifacts remain required evidence. The ignored replay cache harness
is also evidence and must be retained. Cleanup is restricted to disposable
Ruff cache entries; dependencies and frontend build are kept usable.
No run files or secrets are included in publication.

The three smoke cases total 38 attempts and CNY1.734080, leaving CNY148.265920
of the project ceiling. Provider invoices remain pending. PV-07 is explicitly
deferred to P3-07 by the evaluation specification and does not block M9.
P305-U1 remains a separate multi-seed issue. This single-resident result does
not establish three-resident or longer-run behavior.

## Handoff

1. `base_commit` / `result_commit`: `e0d6c16` / acceptance documentation commit.
2. `status`: ACCEPTED for P3-05 / M9 under the owner conditional instruction.
3. `scope_changed`: no implementation changes; branch publication only.
4. `human_interventions`: owner requested acceptance, push and cleanup.
5. `rework_rounds`: zero findings from this central evidence verification.
6. `verification`: 107 pins, 22 decisions/calls, exact accounting, 123 replay
   pairs and 1535 current snapshot entries passed; prior full suite and
   independent Gate 2 reviewed. No additional API calls.
7. `open_questions`: invoices, P305-U1 and later PV-07; main integration and
   P3-06 remain outside this publication.
