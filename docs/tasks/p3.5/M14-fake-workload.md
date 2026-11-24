# M14 fake workload rehearsal

Phase 1 delivers the bounded fixtures and the opt-in evidence command. Both long receipts and the EV-13 acceptance decision are pending. The 2026-11-24 executor instruction reserves the host for CT-06, then CT-07/08/09, before EV-05. Claude Code owns the push.

## Evidence cases

| Case | World and controllers | Seed | Horizon |
|---|---|---|---|
| Week | One shared island. Ella/explorer, Ryan/cautious, Mia/cooperative, Noah/maker and Iris/bold each use their own memory-on decision loop and fake byte transport. | 20261108 | 1,008 ten-minute ticks |
| Cost | Production compat-v1. Ella/explorer uses memory and the fake byte transport. Ryan and Mia use the normal rule controller. | 20261108 | 432 ten-minute ticks |

The week uses the merged, hash-admitted regrowth-2 configuration, its unchanged island map and the normal setup roster extended with Noah at (36,32) and Iris at (37,32). The higher fruit regrowth supports five scripted foragers. This composition is an EV-13 fixture outside the PR-07 equivalence matrix. The cost case uses the default production seed and setup. EV-06 can use this same seed for the comparison, subject to its paid registration.

The fake actors follow scripted routes between a tree and the spring, choose from their sent text, rest, drink, gather, eat and request recall. Their first decision exercises timeout, rate limit, server error and invalid output on retries. Noah also receives a nonretryable decision error. Ella's first selection receives a nonretryable provider error. The next successful change set must consume that pending period. An observed location supports an episodic addition alongside a reference to a missing memory. Short terminal branches retain the protected-floor no-dispatch record and abandonment at authorization, preparation and dispatch, including interrupted and late-return evidence.

## Operator command

The fake schedules sleep for 36 ticks when its K delivery fits within the case. Near the horizon it uses a shorter schema-valid sleep of 6–35 ticks. This leaves every authorized consolidation with a recorded disposition at export time. Its final waking period can remain open. The bounded tests exercise this same schedule.

From the repository root with the locked backend and frontend dependencies installed, run the following once when the scheduler releases the host to EV-05. The command takes the shared lock exclusively for both cases, fails immediately if occupied, creates a fresh ignored directory and prints its path. It releases its own lock on exit.

**Expected wall time.** Ten ticks including recording, replay and export took 47.26 seconds for five model residents and 8.20 seconds for Ella. Linear extrapolation gives about 79 minutes for the week and 6 minutes for Ella. Allow **1.5–3 hours for the combined session**. The opening ticks are unusually call-intensive. Later days have larger maps, contexts, store histories and exports. The full-duration timing remains unmeasured.

~~~powershell
uv run --directory backend/tests --project .. python -m v2.fake_workload.evidence --case both --lock C:\Temp\li-heavy.lock
~~~

For an affected-case rerun, use the applicable command in a later authorized session.

~~~powershell
uv run --directory backend/tests --project .. python -m v2.fake_workload.evidence --case week --lock C:\Temp\li-heavy.lock
uv run --directory backend/tests --project .. python -m v2.fake_workload.evidence --case ella --lock C:\Temp\li-heavy.lock
~~~

## Reading the artifacts

Each case's run manifest pins the commit, world setup, config, map, vocabulary, rule library, pack and profile contents and hashes. The packet journal is shared. The current recorder and exporter identify one decision per boundary. The week therefore retains five resident-local audit databases and inspection indexes over the same physical replay. The case receipt indexes these exports by resident and records each finished-run seal and index hash. The bounded tests require the same final world hash across all five views.

The replay verifier rebuilds prepared requests and dispatched wires, replays submissions against recorded packet and event bytes, checks store revisions and compares the finished checkpoint. Actual attempt wire hashes must also match what the fake transport received. The exporter reads the sealed journals. The verifier opens every indexed shard, checks numbered parts against the 8 MiB limit, then uses the shipped frontend importer to open a decision for each actor. To inspect the result manually, load the case's replay.json in the viewer, switch to analysis mode and select the corresponding inspection-<actor> directory. The display frames come from the actual world states. The display event list carries the required initialization envelope. The inspection attempts shard contains the authoritative WAP events.

The receipt records the exact period IDs and ticks for failures, commits, abandonments and pending membership, plus terminal counts, successful output forms and operation verdict counts. The cost case stages one accepted sample of each call kind in provider-check.sqlite on a separate fake transport. Each staged request retains its prepared record, original parts, wire hash and parsed terminal.

The daily rows give logical and dispatched counts by kind, retries, section UTF-8 bytes summed over sent attempts, the largest guarded and sent bodies, input bounds, scripted output bounds and recording wall time. The central forecast uses the pinned counter's input bound and fake assistant text, zero cache hits and historical M9 peak rates of CNY 2 input and CNY 8 output per million tokens. The second estimate allows the full 8,000 output tokens on each observed attempt. These are planning estimates based on the scripted call mix. Actual provider usage, cache behavior, live responses and the current tariff await DL-06. The fake charge is CNY 0. The separate D7 staging attempts are excluded from the daily totals. After both cases pass, comparison.json places the five-model total and Ella's two controller rosters alongside one another for each of the three comparable days. [Historical M9 price evidence](../p3/M9-evidence.md) · [Phase spend ledger](P3.5-spend-ledger.md)
