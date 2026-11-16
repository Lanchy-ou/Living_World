# P3-PERF-U1 verification evidence

This is offline performance/correctness evidence, not a simulation or M10
acceptance report. All paths below are retained external evidence directories;
none is a live authority. The prior incomplete V-04 source is read-only here.

## Source and prior run

Base: `a70aa23045ecfda8da6e0883f8af1265a16ae531`.
Implementation: `9a530e6cbbfe00408f10ab17a0afa85f71a56557`.
Benchmark JSON correction: `224ab59a44ee293279bc666ad1d87d97284bf29e`.

The previous V-04 authoring process was stopped by its owner after approval and
retained at `D:/p307-v04-generation-a`, with logs and disposition in
`D:/p307-v04-generation-a-check`. It published through boundary 21, exited
4294967295 after 1497.157 seconds, and wrote no golden tape. This task neither
resumes nor edits its source or authority. Fresh generation must use the reviewed
integrated implementation and a fresh isolated fake authority/output.

## Controlled prefix measurement

Durable successful run: `D:/p307-perf-check-b/prefix-{start,exit}.json` and stdout/
stderr logs. Result: `D:/p307-perf-prefix-b/result.json`.

```text
uv run --directory backend python tests/fixtures/p3/evaluation/performance/benchmark.py prefix --checkpoint D:/p307-v04-generation-a/source/checkpoint-0000000010.json --out D:/p307-perf-prefix-b
```

Exact checkpoint SHA-256:
`0b3c1b556e28eee56b5c73c23a980d5f9fbabd864b26b6dfac8ad39a76db72fc`.
The same immutable prefix, installed code and Git reader were used for every
measurement. Initial archived-Git warmup plus uncached verification took 8.329 s
and is reported separately. No authority/provider was accessed.

| Verification mode | Seconds | Hits | Misses | Retained rows | Retained canonical row bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Capacity zero | 2.433257 | 0 | 118 | 0 | 0 |
| Enabled cold | 2.897691 | 0 | 118 | 118 | 8,289,078 |
| Enabled warm | 0.781543 | 118 | 118 cumulative | 118 | 8,289,078 |

Warm verification was approximately 3.11 times faster in this observation. Cold
storage adds copy/allocation work. Counts cover session-decoded context, decision,
dispatch and call rows; unchanged legacy event validation still executes.
All logs together contain 225 rows / 8,334,174 canonical row bytes; largest row
162,259 bytes. There were no evictions. Source file hashes were unchanged.

A separate tracemalloc pass (excluded from timing comparisons) measured 54,989,865
current and 106,058,894 peak traced allocation bytes, including full verification
transients. These numbers are not process RSS or a total Python memory guarantee.
Timing measurements are single host observations with possible concurrent host
activity, not a new acceptance threshold or an extrapolated 1,008-tick result.

## Actual short M6 execution

PASS: `D:/p307-perf-check-d/short-{start,exit}.json` and logs, exit 0.
Result: `D:/p307-perf-short-d/result.json`. Implementation source was
`ff52774076218a98df9426873a9633255fba93d9` (production unchanged since 9a530e6).

```text
uv run --directory backend python tests/fixtures/p3/evaluation/performance/benchmark.py short --out D:/p307-perf-short-d
```

The helper registers a four-tick smoke-seed M6 case, all three primary LLM actors,
zero-money fake capacity, and source-pins both itself and the unchanged V-04 pure
tape builder. Separate fake authorities execute the same inputs with capacity zero
and enabled. The comparison requires every source file, all requests/results,
checkpoints, logs and trace to match exactly. Each then uses raising sentinels for
provider and authority during recorded execution and compares replay export bytes.
It never writes or regenerates the V-04 golden tape.

| Actual four-tick run | Seconds | Hits | Misses | Retained rows | Raw bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Capacity zero | 40.992810 | 0 | 1,741 | 0 | 0 |
| Enabled | 18.348388 | 1,642 | 99 | 99 | 3,036,375 |

Both runs used seed 1292387875 and all three primary LLM actors, with 12 exact fake
steps including Ella ordinal 1's two TIMEOUT attempts. Every source file was
byte-identical, as were both recorded executions and replay exports. Runtime
improvement was approximately 2.23 times for this observation. Source input creation
and subsequent replay/export checks are outside those run timings. The Git reader
is shared and warmed by input construction. Ordinary host activity remains a timing
limitation; no 1,008-tick timing is inferred.

- Registration SHA-256: `4f64dc3ef6082d8d89d31d922eeb64e0d9de55199b32e640565a2f7af21f45f8`.
- Request/result step-sequence SHA-256: `797ab2561ae175bda518072350965f268bc47169f947cf3a3a04935532c00d4d`.
- Trace SHA-256: `4b12d74350a31201241c30644773e0b9919d0c681e0ccbf6f6b11d5cd4790501`.
- Replay SHA-256: `765145ebff8114621a228ee395613d90c7e6d9a96661cfa16b66313e09399f6f`.
- Reexecution provider and authority accesses: exactly 0 in each run.

Exact measurement JSON, argv, per-file hashes and counters are also committed as
`backend/tests/fixtures/p3/evaluation/performance/checkpoint10-measurement.json`
and `m6-four-tick-measurement.json` for review. They are measurements, not golden
simulation acceptance artifacts.

## Executor checks

- `uv sync --directory backend --locked`: PASS, 26 locked packages.
- `pnpm --dir frontend install --frozen-lockfile`: PASS, 173 packages, pnpm 10.34.9.
- Dedicated initial tests: 20 PASS / 1 incorrect negative oracle; correction described
  in the task handoff. Fresh rerun included in the durable affected suite.
- Full affected suite: **332 passed in 751.76 seconds, exit 0, no skips**, at
  `4dda1241d73934e9e0646690123a6d80852b11c9`. This includes all 23 dedicated cache
  tests plus the complete existing persistence, allocation, recovery, reexecution,
  transactions, inspection, compatibility, one-resident and three-resident files.
  Command-scope `core.longpaths=true` was set. Base `D:/p307-10a52eff3e4d` was proved
  absent before pytest. Exact argv/start/exit and captured output are in
  `D:/p307-perf-check-d/regressions-{start,exit}.json`, `regressions-stdout.log`, and
  `regressions-stderr.log` (empty). The 24-tick frozen one-resident smoke and its
  full recorded replay completed; no expensive check was shortened or skipped.
- Ruff lint after implementation/helper formatting: PASS.
- Ruff format: PASS, 175 files formatted; mypy: PASS, 91 source files; import-linter:
  PASS, 8 kept / 0 broken.
- Both `gen_types.py` and `gen_p3_inspection_types.py`: PASS; generated diff clean.
- Complete frontend diff from baseline: empty. Frontend lint/type/build/UI tests
  NOT_RUN in this backend-only performance worktree; coordinated in P3-07.
- Integrated full-suite and fresh historical hashes: NOT_RUN here, parent-owned.

The initial benchmark evidence write failed because runtime canonical JSON forbids
floating timings. `D:/p307-perf-check-a/prefix-exit.json` retains exit 1 and traceback;
`D:/p307-perf-prefix-a` was not overwritten. Fresh run B used ordinary evidence JSON.

## Explicitly not claimed

No real model calls, credentials, real allocation grants, live authority access,
push/main merge, independent Gate 2, full V-04 completion, M10 or owner acceptance.
The parent P3-07 task coordinates integrated full-suite and fresh eight historical
P1/P2 artifact hashes after independent review and conditional local integration.

Two short-benchmark preflight failures are retained separately: run B refused a
working-tree CRLF helper that differed from its committed LF source; the files were
normalized to exact committed bytes before execution. Run C refused a renamed
registration whose case ID still bound the old registration name. The helper was
corrected to satisfy the unchanged identity rule and given `perf-short` fixture
identity. Neither preflight entered simulation or created an authority grant; each
failed output directory remains retained. No verifier was bypassed.

## Review handoff

Status: READY_FOR_REVIEW. Production is unchanged since
`9a530e6cbbfe00408f10ab17a0afa85f71a56557`; the final tested code/helper/tests
candidate is `4dda1241d73934e9e0646690123a6d80852b11c9`. Later changes only add this
handoff and the measured JSON evidence. The parent may integrate locally only
after the independent nonauthor Gate 2 passes. This author has not integrated,
pushed, or merged the branch.

## Parent integration record

After this author handoff, the independent reviewer passed candidate
`ec531c112fd45199f591fd5095f5b6ac4b8e6247`: 28 independently rerun tests and an
actual four-tick disabled/enabled M6 comparison, with identical source/recorded
and replay bytes and zero replay provider/authority sentinel accesses. Report:
`D:/perfg2-short-15adc0b5/P3-PERF-U1-Gate2-review.md`, SHA-256
`4ddaba84866f761a6fa904d1c0d7aff6d91d865ce84273c4028bb4136d91d9e6`.

The parent then exercised the owner's conditional local-integration permission,
cherry-picking the six upstream commits without conflict through P3-07 commit
`e2bed8ba71f72a597670c3ea29cde50a4dc70d4e`. This was local integration only;
there was no push or main merge. The original upstream branch and evidence remain
preserved. See [P3-07 report](P3-07-report.md) for subsequent integrated verification.
