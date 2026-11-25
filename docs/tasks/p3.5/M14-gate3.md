# M14 Gate 3 — Ella live resident

## Owner pre-dispatch sheet · 2026-11-25

**Budget fit: 3 of 3 whole game days. Paid dispatch: HOLD. Owner release and
Gate 3 disposition: pending.** M12 and M13 are signed. DL-06 passed D7 with
the six JSON-only `/0.2` prompts. The recheck accepted 7/7 dispatches over
HTTP, parsed 5/6 first attempts and completed all six logical calls. Both
decision kinds parsed on their first attempt. The candidate needs a guarded
resident CLI entry point before the owner can release it. [M13 sign-off PR #69](https://github.com/Lanchy-ou/Living_World/pull/69)
· [DL-06 recheck](M14-provider-check.md#live-recheck-result)
· [2026-11-25 sizing ruling](../../spec/open-questions.md#oq-p35-m14-2-evidence-sufficient-for-the-paid-provider-check-and-horizon)

### Run and provider pins

| Field | Proposed run |
| --- | --- |
| Execution baseline | `3c51c311f8af1e20b7448e7ae4a28bb9f0f1fb91`. Pin the exact guarded implementation commit in the signed release and executable manifest after integration. |
| Run ID and output | `m14-ev06-ella` under a fresh ignored `runs/m14-ev06-ella/`. |
| Case | Ella (`ella`), schema `0.2` `explorer`, memory on. Ryan (`cautious`) and Mia (`cooperative`) use `rule-based-v0`. Production `compat-v1` with its registered bridge. |
| Seed and horizon | `20261108`; ticks 0–431 dispatch, target committed tick 432. A game day is 144 ten-minute ticks. Consolidation K is 36 ticks after sleep/faint begins. |
| Pack SHA-256 | `b488ae73053ca771d3c2cffa7fc48f5b44307b4ceab6e61aa34a9ced223f7e39` |
| Canonical vocabulary SHA-256 | `57554435492d6f3db83006a4510b292f8b0d1ebc70c3393663fd1a9ad94cf286` |
| Rule library SHA-256 | `9690f81feed90297093e314a6d07d87f041eaf73522e39295de4d4424e355b1b` |
| Effective config and map SHA-256 | `11f2bba2ad27f2d6b5342796b3871401b765aa2319c923a4e459a22c6acb6c3d` and `007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c` |
| Ella profile SHA-256 | `b87a43bb1eaa4546aa013ceef2bbd4ab90313bfc43aef3147ac780dd46c3f9c3` |
| Provider | `deepseek-responses`, `https://api.deepseek.com/responses`, alias `deepseek-flash` resolved to `DeepSeek-V4.1-Flash-1017` in the 2026-11-24 DL-06 evidence. Stateless, reasoning effort `none`, one schema in `text.format`, wire adapter `deepseek-responses-v2/0.1`. |
| Prompt and schema | Six JSON-only prompts at `/0.2`. Carry per-kind prompt and schema SHA-256 pins from the DL-06 recheck. [Prompt hashes](M14-provider-check.md#prepare-the-prompt-recheck) · [Recheck preflight](M14-provider-check.md#recheck-release-on-2026-11-24-utc) |
| Counter | `deepseek-flash1017-byte-upper-bound/0.4`; counter source `fdaf256a6f4558bf8722af2e744e10a816f312248768d3278b988820a36146bc`; tokenizer `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b`. |
| Context pressure | `pressure/0.1` on the full provider-framed input before inserting the pressure line. Model window 1,000,000, output reserve 8,000, input window 992,000. Band thresholds are 5%, 15%, 30% and 50% of the input window. The largest rehearsal input was 18,593 tokens including framing and any pressure line. |
| Tariff, CNY per million tokens | Dated DL-06 evidence for 2026-11-24 UTC. Cache-hit input / cache-miss input / output rates were **0.02 / 1 / 4 off-peak** and **0.04 / 2 / 8 peak**. The dated peak periods were weekdays 09:00–12:00 and 14:00–18:00 Beijing time, excluding Chinese public holidays. Use zero hits and the peak 2/8 rates for all holds. The owner attaches alias and tariff evidence covering the actual UTC dispatch date(s) at release. [Dated price source](M14-provider-check.md#owner-release-on-2026-11-24) |

The compatibility loader reproduced the three canonical hashes, effective
config and map from the local baseline. The accepted rehearsal uses the same
content, seed, profiles and wire pins. Its `/0.2` receipt SHA-256 is
`d470ea3c419f75d152dad471cb2b860026e68bf377874bb8f64ddfe017ceec43`. The retained
EV-04 sizing bundle is `dl06-ev06-sizing-evidence.json`, SHA-256
`f037286a10e3d807c5c6329c92521b044f1837bc7998d7e5e78079a497d9a362`.
[EV-05 rehearsal](M14-fake-workload.md) · [DL-06 `/0.2` sizing inputs](M14-provider-check.md#ev-06-day-sizing)

### Comparable calls and day sizing

Measured costs are CNY per logical call from the `/0.2` live recheck.
The central forecast uses all 15 measured DL-06 attempts, including local
rejections, with observed cache and output charges and input charges scaled
to the rehearsal's counted input per kind and day. Later input changes and
different cache behavior can shift that forecast. Each day column lists
rehearsed logical calls / dispatched attempts, including retries.

| Call kind | Measured recheck CNY | Day 1 | Day 2 | Day 3 | Greatest counted input per kind through days 1 / 2 / 3 |
| --- | ---: | ---: | ---: | ---: | --- |
| `decision` | 0.00715100 | 27/31 | 20/20 | 20/20 | 18,593 / 18,593 / 18,593 |
| `decision_after_recall` | 0.00719400 | 3/3 | 2/2 | 1/1 | 16,137 / 16,137 / 16,649 |
| `recall` | 0.00028100 | 3/3 | 2/2 | 1/1 | 306 / 439 / 518 |
| `morning` | 0.00100500 | 3/3 | 3/3 | 3/3 | 1,055 / 1,243 / 1,479 |
| `consolidation_selection` | 0.00298100 | 4/4 | 3/3 | 3/2 | 10,005 / 10,005 / 10,005 |
| `consolidation_change_set` | 0.00861496 | 3/3 | 3/3 | 2/2 | 14,421 / 14,421 / 14,421 |

The approved reserve uses the greatest counted input on each rehearsed
attempt, summed by day, with the 8,000-token output ceiling on every
dispatch. The running maxima above describe per-kind growth. The reserve
uses the actual attempt bounds below. Across sent attempts, index bytes grew
3,049 → 4,318 → 6,219 and day-log bytes were 89,598 → 57,030 → 67,945 as
daily attempt counts fell. [DL-06 usage and day sizing](M14-provider-check.md#measured-usage-and-settled-cny-by-attempt)

| Game day | Calls / attempts | Sent input bound | Output tokens held | Central off-peak CNY | Central peak CNY | Reserved peak CNY | Cumulative reserve CNY |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 43/47 | 534,641 | 376,000 | 0.311229 | 0.622458 | 4.077282 | 4.077282 |
| 2 | 33/33 | 364,236 | 264,000 | 0.208314 | 0.416628 | 2.840472 | 6.917754 |
| 3 | 30/29 | 353,542 | 232,000 | 0.206542 | 0.413084 | 2.563084 | 9.480838 |
| **Total** | **106/109** | **1,252,419** | **872,000** | **0.726085** | **1.452171** | **9.480838** | **9.480838** |

The phase cap is CNY 20. DL-06 settled **CNY 0.05343482** with **CNY 0**
outstanding, leaving **CNY 19.94656518** at pre-dispatch. Holding CNY 9.480838
leaves **CNY 10.46572718** outside the reservation. All three offered days fit
under the 2026-11-25 sizing ruling. [Phase ledger](P3.5-spend-ledger.md#opening-ledger)

### Runtime admission and safe stop

1. Acquire `C:\Temp\li-heavy.lock` exclusively with the card ID and start
   time. Bind the single run ID and output directory to the signed release,
   exact executable commit, inputs, tariff evidence, reconciled opening
   balance, 432-tick horizon and CNY 9.480838 reservation.
2. Before every initial attempt or retry across all six kinds, use the
   admitted wire's framed input bound and `max_output_tokens`. The next
   worst-case peak charge in CNY is `(2 × input + 8 × output) / 1,000,000`.
   Permit the attempt only if phase settled plus all unresolved holds plus
   that charge is at most CNY 20. Check and claim the slot together before I/O.
   Apply the same hold to overlapping consolidation dispatches and count
   prior DL-06 spend once. A terminal with known charge replaces its hold
   once. A timeout, interruption or missing usage keeps its worst-case hold
   pending reconciliation. Unbounded liability blocks further dispatches.
3. Track actual attempts and counted input by game day and kind, including
   retries, and update remaining rehearsal exposure when either grows. Stop
   when the revised peak exposure, including the candidate, would exceed
   the signed CNY 9.480838 reserve. Keep that check separate from the absolute
   phase cap. The reservation includes the estimated remaining rehearsal
   exposure as well as EV-06 spend and unsettled holds.
4. On refusal, latch the stop before another dispatch. Keep the prepared
   candidate, record its unsent budget refusal and reconcile every earlier
   durable attempt, including late charges. Seal at the next safe world
   boundary and record the committed tick, incomplete reason, whole game days,
   partial-day cost and closed waking periods. Release the host lock when the
   process exits. An operator budget stop produces no gameplay fallback.

### Required production allocation

`python -m living_island.sim.v2.cli --help` exposes only `equivalence` on the
assigned base. `sim.v2.harness.composition.compose` and `Recording` are Python
building blocks. The only shipped v2 `--live` command belongs to the DL-06
six-sample provider check. Its one-time forecast and UTC check apply to that
sample. `analysis.v2_spend` projects a static ledger. `ResidentSession` checks
its manual `stop_file` after publication, so it cannot veto a dispatch or
retry inside that boundary. The existing context guard measures window fit.

The smallest shared admission point is `agents/v2/calls/provider.py::attempt`,
after building `Dispatch` from the admitted wire and immediately before its
exclusive `journal.fact(..., "<n>.dispatch", ...)` claim. Both
`agents/v2/decision/caller.py::Caller.dispatch` and
`sim/v2/harness/consolidation/workflow.py::Workflow.advance` pass through it on
every retry. Inject an operator-owned admission/settlement policy, settle
from durable terminal or charge rows, and propagate a distinct refusal through
the caller and workflow to `ResidentSession` and its safe-stop record. The
stop must preserve audit and replay semantics, including an authorized
consolidation with earlier attempts and a refused later attempt. Existing
`TerminalStop` and incomplete recording provide the starting points. Checking
only at `transport.exchange` would leave a dispatch record for a vetoed call
because `attempt` claims it first. Checking only between ticks would miss
in-boundary retries.

The CLI needs a live command in `sim/v2/cli.py` delegating to the existing
composition, recording and provider adapter, with signed release wiring,
credential redaction, the guard and a verifier for the resulting capture.
Claude Code's allocation and independent fake tests of both callers' retry
refusal, unresolved liabilities and safe stop are prerequisites. The existing
inspection exporter requires a `FinishedRun` seal. A stopped run keeps its raw
partial evidence and needs verified partial-run handling before it can be
presented as an inspection artifact. [DL-04 composition](P3.5-DL-04.md#what-changed)
· [DL-05 replay](P3.5-DL-05.md#card-end-replay-evidence)

### Operator command and wall time

**Executable live command on `3c51c31`: unavailable.** The following is the
proposed exact command shape for the allocated CLI, from `F:\p35-w1\ev06`.
The signed release file would pin all values in the run and provider table.
Replace this command in the signed sheet with the verified invocation on the
guarded commit before running it.

```powershell
uv run --offline --locked --directory backend --env-file F:/p35-w1/ev06/.env python -m living_island.sim.v2.cli live-resident --release F:/p35-w1/ev06/runs/m14-ev06-ella-release.json --out F:/p35-w1/ev06/runs/m14-ev06-ella
```

The owner supplies `DEEPSEEK_API_KEY` in the live process environment. The
explicit `--env-file` would load the root `.env` in the owner's terminal.
With the key already injected, the owner can use `--no-env-file` in its place.
The existing DeepSeek adapter consumes the key via the caller's environment
wiring, as DL-06's wrapper does. `uv --offline` limits dependency resolution,
and the live runner would still make HTTPS requests.

Estimated **4–5 minutes to record** 432 ticks at the rehearsed attempt count,
plus **about 3 minutes** for offline replay, export and inspection validation.
The `/0.2` fake recording took 86.4 seconds and the complete receipt took 271.3
seconds. The DL-06 recheck spent 9.792 seconds across seven provider attempts,
or about 1.40 seconds per attempt. At 109 dispatches that adds about 152
seconds to recording before backoff. Live latency, retries and actual tick
work can change the estimate. [DL-06 recheck](M14-provider-check.md#live-recheck-result)

### Gate 3 evidence after the owner run

| Item | Status |
| --- | --- |
| Paid capture, realized horizon, spend by resident-day and fallback counts | Pending owner dispatch. Keep the raw audit, packet journal, opening and final checkpoints, dedicated run manifest and EV-04 sanitized evidence under `runs/`. |
| Offline rebuild | Pending paid capture. Run the DL-05 verifier with no key, network disabled and fail-on-call transport. Compare every reconstructed request, store-version hash, committed submission, event and final state to the originals. The replay API exists, and this baseline lacks a resident replay CLI. |
| Verified export and analysis walkthrough | Pending paid capture and seal. Load the matching `replay.json` in the viewer, open analysis mode and select the fresh inspection directory. Attach the actual resident/period/turn IDs and artifact hashes once selected. |
| Decision and memory trace | Pending. Select a model-origin outcome and trace earlier packet/day-entry through the K-boundary change set and record revision, then subsequent morning, sent recall, decision citation and world result. Distinguish rendered, dispatched and cited evidence. |
| Skill and starter evidence | Pending. Report self-found skill evidence or an evidenced zero after the run. The starter-only grass-cord axe is due at M15. |
| Prior engineering receipts | [MM-16/MF-14 and DL-19](P3.5-MM-02.md#gate-3-receipts) · [Round 3](M14-plan.md#4-done-when) · [EV-13 rehearsal](M14-fake-workload.md#receipts-and-verified-exports) · [PR-05 provenance](P3.5-PR-05-review.md) · [PR-06 provenance](P3.5-PR-06-review.md) |
| Owner signature | Pending. Record the signed release separately from the final Gate 3 disposition and evidence revision. |

With the future sealed artifacts at the proposed paths, the available
exporter and frontend commands are as follows. The export reads
`sanitized-evidence.json` in the resident audit directory for ledger joins.
Verify the new index and all referenced shards before selecting the live
trace in analysis mode. [EV-01 export contract](P3.5-EV-01.md)

```powershell
uv run --offline --no-env-file --locked --directory backend python -m living_island.analysis.v2.export ../runs/m14-ev06-ella/ella ../runs/m14-ev06-ella/ella/finished.json ../runs/m14-ev06-ella/replay.json ../runs/m14-ev06-ella/inspection-ella
pnpm --dir frontend dev
```
