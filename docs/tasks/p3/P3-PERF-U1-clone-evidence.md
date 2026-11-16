# P3-PERF-U1 encode-once follow-up evidence

This is an offline performance/correctness follow-up within the already approved
exact-row cache and independent-copy scope. It is not a V-04 or M10 acceptance.

## Candidate and scope

Baseline: `ec531c112fd45199f591fd5095f5b6ac4b8e6247`.
Production/tests/helper candidate: `e6536fdb52de2df1792a44f87723ba573489cc20`.
Only `persistence/p3.py` changes production behavior, inside the private cache.
The existing owner DTO types serialize once after successful strict/canonical
validation. Hits deserialize only payloads made internally by that session.
No file/caller-provided pickle payload is accepted, persisted or exported.
Other BaseModel types retain the previous deep-copy implementation, including
local classes and custom/nonpicklable private state. Encoding failures fall back
to that implementation. A load compatibility failure reuses the normal decoder
and changes that entry to deep-copy storage; decoder errors are not swallowed.

The raw canonical byte limit remains 134,217,728 bytes. Admission order,
protected rows, eviction, bypass and all existing counters retain their meaning.
Payloads/fallback graphs and keys are additional heap; this is not a heap limit.
All current-byte, source, input, prefix, cross-record, recovery and authority-head
checks remain unchanged. No P3-07 worktree, frozen DTO, contract, provider,
authority implementation or world/runtime behavior was edited.

## Executor checks

Dedicated: **29 passed in 61.52 seconds**, including all 23 previous cases and
six new compatibility/isolation/encode-once/fallback cases. Durable affected
suite: **338 passed in 863.60s (0:14:23)**, exit 0. The full 24-tick one-resident
smoke and replay were included without shortening or skipping checks.

Durable runner records, exact argv, source SHA, stdout/stderr and exits:
`D:/Codex/.codex/visualizations/2026/11/15/01a1e002-e2a9-74c2-90cb-1f8758b358ad/perf-clone-followup-check-a`. Each step has `*-start.json` and `*-exit.json`.
Locked `uv sync --directory backend --locked --offline`, backend Ruff lint and
format (175 files), mypy (91 source files), and all eight import contracts passed.
The affected command ran `test_verification_cache`, `test_persistence`,
`test_allocation`, `test_recovery`, `test_reexecution`, `test_transactions`,
`test_inspection`, `test_compatibility`, `test_one_resident`, and
`test_three_residents`, with a fresh dedicated pytest base and command-scope
Git long-path configuration. These runs used the locked backend virtualenv.

An initial unprivileged Ruff cache write was denied; rerunning with `--no-cache`
passed. An initial read-only Git byte check used a Windows backslash safe-directory
value that Git did not recognize; the corrected forward-slash value passed.
Neither preflight changed production behavior. Lint line-length corrections were
completed before the dedicated and durable checks. Prior stopped/failed artifacts
remain preserved. The first external direct-byte comparison mistakenly read the
recorded output container rather than its returned `segment-0000` directory.
The corrected driver compared the actual 22 files directly; no runtime artifact
was changed. Its initial failure and unchanged original driver remain preserved,
and the evidence writer refused missing comparison evidence before writing files.
Frontend, generators, full-suite and historical-hash integration
checks are parent-owned; this backend-only follow-up does not claim new results
for those checks.

## Actual four-tick M6 comparison

Command (from backend):

```text
.venv/Scripts/python.exe -B tests/fixtures/p3/evaluation/performance/benchmark.py clone-short --out <fresh-output>
```

Result: `short/result.json`; direct byte proof: `direct-byte-comparison.json`.
The committed helper extracts only the exact prior `_VerificationSession` class
from trusted Git baseline source, identified by hash in the result. All surrounding
verifier/runtime code and current pinned inputs are identical in all five modes.
This isolates the sole production behavior changed by the follow-up. Two prior/new
pairs run in opposite orders; the disabled mode is reported separately. The source
Git reader is warmed by input construction. Run timing excludes replay/export.
All authorities are fresh isolated zero-money fake test authorities.

| Mode | Run seconds | Hits | Misses | Rows | Raw bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| disabled | 47.091176 | 0 | 1741 | 0 | 0 |
| baseline | 19.749694 | 1642 | 99 | 99 | 3,036,375 |
| enabled | 16.565953 | 1642 | 99 | 99 | 3,036,375 |
| enabled-repeat | 16.961847 | 1642 | 99 | 99 | 3,036,375 |
| baseline-repeat | 19.351024 | 1642 | 99 | 99 | 3,036,375 |

Prior-cache median: **19.550359 seconds**. Encoded-cache median:
**16.763900 seconds**, **14.25% less time** in this observation.
This actual-run observation is separate from clone/checkpoint timings. The
independent reviewer observed a smaller 7.32% reduction (prior median 26.047264
seconds versus encoded 24.140374 seconds) in
`../gate2-clone-followup/short-m6/result.json` under the same external evidence root.
These are separate host runs, not pooled samples or a guaranteed improvement;
the independent lower gain should remain visible when assessing value.
All five modes used seed 1292387875, all three primary actors and 12 exact
fake steps, including the unchanged timeout attempts. Direct byte comparison
passed for every one of the 22 source files in all five source and all five recorded directories, plus all five replay
exports. Request/result sequence and trace hashes also match. Reexecution provider
and authority raising sentinels recorded zero accesses in every mode.

## Committed-code checkpoint comparison

The same immutable checkpoint 10 was verified in eight unprofiled opposite-order
pairs using the exact prior cache class and the committed new class. Source SHA-256:
`0b3c1b556e28eee56b5c73c23a980d5f9fbabd864b26b6dfac8ad39a76db72fc`. Result: `prefix/result.json`.
Driver: `D:/Codex/.codex/visualizations/2026/11/15/01a1e002-e2a9-74c2-90cb-1f8758b358ad/perf-clone-diagnostic/measure_production_prefix.py`.
Driver SHA-256: `ff35c19c53bdc0fbba9eb540c0c98205693714952695c104075af655f044c947`.
`prefix/provenance.json` records argv and the protocol: one uncached source warmup,
one fill per cache, then eight alternating pairs; collection occurs before timing,
and result/counter assertions occur afterward. Profiling and allocation tracing
are absent from these timing trials. Provenance was recorded after the successful
run, without changing the executed driver or original result.
Warm whole-verifier wall medians: **0.811710 seconds prior**, **0.688257
seconds encoded**, **15.21% less time**. CPU medians:
0.812500 and 0.695312 seconds respectively.
Each retained 118 rows / 8,289,078 raw bytes, with 118 initial misses, 944 warm hits,
zero new warm misses and zero evictions. Encoded payloads add 8,802,845 bytes.
The retained source directory fingerprint remained unchanged; no authority or
provider was accessed.

## Separate allocation diagnostic and limits

Before implementation, the isolated encode-once prototype compared the same raw
capacity and protected-row policy. Its separate tracemalloc passes measured
retained cache allocations 52.331 MiB prior versus 16.350 MiB encoded, and warm
verification peaks 102.791 versus 75.972 MiB. These are traced Python allocations,
not RSS or a maximum heap guarantee. The committed representation has the same
8,802,845 encoded payload bytes on that checkpoint. The earlier prototype's 17.66%
whole-checkpoint timing is historical diagnostic evidence; the committed-code and
actual-M6 measurements above are the follow-up results.

Diagnostic artifact: external `perf-clone-diagnostic/encoded-once-rawbound-recovery/`
(`report.txt`, `result.json`, code, stdout/stderr and exit 0). It also checked 118
owner rows and 162,636 mutable collections, exact types/field sets/private/extras,
malformed inputs, and identical zero/1 MiB bounded-cache policy against baseline.
Deserialized result graphs can allocate more memory than deep copies even while
the encoded retained cache is smaller. Python/Pydantic class-state compatibility
remains a consideration; conservative non-owner and serialization-error fallbacks
preserve previous behavior without adding a persisted format.

Host activity, small sample size and different workloads limit timing conclusions.
No full V-04 throughput, completion time, real-provider behavior, new live authority
capacity, M10 acceptance, push or merge is claimed. Independent nonauthor Gate 2
and parent-controlled integration remain required for this candidate.
