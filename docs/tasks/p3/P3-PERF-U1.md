# P3-PERF-U1: operation-scoped committed-row verification cache

## Brief

- Task ID/title: P3-PERF-U1, repeated committed-record validation.
- Baseline: `a70aa23045ecfda8da6e0883f8af1265a16ae531` (frozen P3-07 backend candidate).
- Authorization: owner approved the independent performance fix, offline verification,
  and conditional local integration only after a nonauthor Gate 2. No push or main
  merge, real provider/credential use, or allocation grants are authorized.
- Lane: isolated `task/P3-PERF-U1-validation-cache` branch and worktree. P305-U1
  released production source ownership before work began. P3-07 frontend work
  proceeds on disjoint files in its own worktree.
- Goal: reuse successful exact canonical row decoding while retaining every
  current-byte, source, input, prefix, cross-record, recovery and authority check.
- Non-goals: no new saved schema, world behavior, scheduling, memory/cognitive
  reducer, allocation semantics, provider behavior, generic codec or P1/P2 changes.
- Allowed files: `persistence/p3.py`, `sim/p3.py` session plumbing,
  `persistence/p3_inspection.py`, dedicated cache tests/performance fixtures, and
  this task/evidence documentation.
- Deliverables: private bounded operation session; disabled/evicted equivalence
  and corruption tests; controlled prefix and short M6 measurements; explicit
  local candidate for independent review.
- Acceptance: cache misses use the original strict decoder; successful returns
  are independent; current bytes and all relationships still verify; no failure
  caching; complete short execution/reexecution bytes match with cache disabled
  and enabled; overflow changes performance only.
- Verification: locked dependencies, dedicated and affected P3 regression suites,
  static/import checks, unchanged generators; integrated full-suite and fresh
  historical hashes coordinated with the parent P3-07 task.

## Design

`_VerificationSession` is private and created once per `run_p3`, `resume_p3`,
`reexecute_p3`, `export_p3_replay`, or `verify_inspection_source` operation. The
same instance reaches the journal, checkpoint publication and authority verifier,
recursive ancestry/recovery, and boundary traversal. Low-level persistence callers
that do not supply a session retain uncached behavior. No global cache, disk cache,
allocation state, acceptance result or provider object is retained.

The key is the exact model class and the complete current canonical row bytes.
A miss calls the unchanged generic `decode_model`; only success can be stored.
The cache stores its own deep copy and returns an independent deep copy on hits.
Changing a valid row produces a miss; even a hit only supplies a DTO to the full
existing joins. Checkpoint/input/source reads and hashes are not memoized by this
session. Legacy event sequence validation remains unchanged on every checkpoint.

The default bound is **134,217,728 canonical row bytes (128 MiB)**. It is not a
Python heap bound. There is a finite number of retained nonempty canonical rows
within that payload bound, and all retained model graphs leave scope together.
The host had about 2.5 GiB free physical memory at the capacity decision. The
checkpoint-10 measurement retained 8.29 MB of canonical rows and about 55 MB of
traced Python allocations, with about 106 MB peak including verification
transients. This supports an explicit conservative bound rather than retaining
an entire unbounded 1,008-tick prefix.

Rows reused at least once are protected for the operation. To make room, the
oldest not-yet-reused rows are evicted. If those cannot make room, new rows bypass
storage and still decode fully. This avoids a prefix larger than capacity
repeatedly evicting every hot row during a full scan. Oversized rows and capacity
zero also decode fully without storage. Protected rows are released when the
operation finishes; no cross-run capacity or state exists.

## Handoff

### What changed

Added only successful P3 row-decode memoization and operation lifetime plumbing.
The frozen V-04 builder, all runtime/decision/recovery semantics, owner DTOs,
generic decoder, P1/P2 paths, and allocation authority implementation are unchanged.
See [measurement and verification evidence](P3-PERF-U1-evidence.md).

### Commands and results

All 332 affected tests passed in 751.76 seconds, exit 0, including 23 dedicated
cache tests, allocation/concurrency/crash/recovery/replay regressions and the full
frozen one-resident smoke. Ruff lint/format, mypy and all eight import contracts
passed. Both contract generators and the complete frontend baseline diff are
clean. The unchanged checkpoint-10 warm case measured 3.11x and the actual short
M6 run 2.23x faster; exact output bytes matched. Exact commands, timings, counts,
source pins and durable exit records are in the evidence document.

### Deviations

The initial negative test changed a valid standalone checkpoint health value; that
value was still accepted by the unchanged verifier. The test was corrected to
corrupt the retained config hash, which is an actual required join. The benchmark
initially tried to encode floating timing values using the integer-only runtime
canonical encoder. That encoder correctly refused them; benchmark evidence now
uses ordinary JSON. Two later short-benchmark preflights also refused a CRLF/LF source mismatch and
a case ID that still bound the prior registration name. Both were corrected before
execution, retaining all failed outputs. No correction changes runtime validation.

### Open questions

None about saved formats or validation semantics. Independent Gate 2, integrated
full verification and the fresh full V-04 generation/proof remain required. Short
measurements do not attest completion or acceptance of the 1,008-tick proof.

### Required fields

1. `base_commit` / `result_commit`: `a70aa23045ecfda8da6e0883f8af1265a16ae531` /
   production/tests candidate `4dda1241d73934e9e0646690123a6d80852b11c9`.
   The subsequent evidence-only handoff commit is reported separately.
2. `status`: `READY_FOR_REVIEW`; independent Gate 2 and conditional local integration pending.
3. `scope_changed`: no; separate performance scope explicitly approved by owner.
4. `human_interventions`: 1, approval of this independent fix and conditional local integration.
5. `rework_rounds`: 0 review rounds; four executor test/harness corrections documented above.
6. `verification`: 332 tests PASS (0 failures/skips), static/import/generator checks PASS;
   see evidence for argv and exit records. Integrated full-suite, fresh eight
   historical artifact hashes, frontend checks, independent Gate 2 and full V-04
   NOT_RUN here and explicitly delegated/coordinated with the parent task.
7. `open_questions`: none; no M10 or owner acceptance claim.
