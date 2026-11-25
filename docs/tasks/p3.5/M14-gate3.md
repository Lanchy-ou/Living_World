# M14 Gate 3 — Ella live resident

## Owner pre-dispatch sheet · 2026-11-25

**The original peak run stopped at committed tick 185 of 432. The owner
authorized one replacement for 10:30–12:00 Beijing time on 2026-11-25.
Replacement dispatch and final Gate 3 disposition remain pending.**
M12 and M13 are signed. DL-06 passed D7 with
the six JSON-only `/0.2` prompts. The recheck accepted 7/7 dispatches over
HTTP, parsed 5/6 first attempts and completed all six logical calls. Both
decision kinds parsed on their first attempt. [M13 sign-off PR #69](https://github.com/Lanchy-ou/Living_World/pull/69)
· [DL-06 recheck](M14-provider-check.md#live-recheck-result)
· [2026-11-25 sizing ruling](../../spec/open-questions.md#oq-p35-m14-2-evidence-sufficient-for-the-paid-provider-check-and-horizon)

### Run and provider pins

| Field | Proposed run |
| --- | --- |
| Original executable commit | `92ce49726a653e62548655cd16e1aa8b6238c8fe`, based on `3c51c311f8af1e20b7448e7ae4a28bb9f0f1fb91`. The interruption and replacement pin are recorded below. |
| Preflight SHA-256 | `f4ba7105f050e8b4fc3516384ffe25512f66a225b05266289818c8da4fa39871` for the executable commit and this worktree's one-time capture directory. |
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
| Tariff, CNY per million tokens | Cache-hit input / cache-miss input / output rates are **0.04 / 2 / 8** for the released peak window on 2026-11-25 UTC. The off-peak rates are **0.02 / 1 / 4**. Peak periods are weekdays 09:00–12:00 and 14:00–18:00 Beijing time, excluding Chinese public holidays. All holds use zero hits and the peak 2/8 rates. Claude Code verified the official price page on 2026-11-24. [Official CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) |

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

### Guarded implementation

Claude Code allocated `agents/v2/calls/provider.py` and the new
`sim/v2/harness/live_resident.py` entry point to EV-06. `attempt()` calls the
optional hook immediately before its exclusive dispatch claim. The resident
command installs one admission policy around the synchronous composition, so
decision, recall, morning and both consolidation calls pass through it on
every retry. A refusal returns a typed budget stop to the runner. It leaves the
world at its last committed tick and preserves the unsent candidate, earlier
attempts and partial charges. The candidate has no dispatch fact or provider
call. The guard consumes rehearsal slots in dispatch order within each day and
kind. The reserved-total check includes settled EV-06 spend, outstanding
holds, the candidate quote and unused slots for the current and future days.
EV-04 reconciles the recorded costs against the signed opening ledger and
dated rates. Release loading requires a signed window and verifies that every
Beijing billing period it touches matches all three settlement rates in the
dated EV-04 row. [DL-04 composition](P3.5-DL-04.md#what-changed)
· [DL-05 replay](P3.5-DL-05.md#card-end-replay-evidence)

The runner journals completed boundaries and checkpoints each tick. Resume
uses the original capture directory and release. If a committed boundary's
checkpoint is missing, resume rebuilds it offline. An uncommitted dispatch
tail seals the run as incomplete and retains any unresolved hold. Inspection
exports seal the verified boundary prefix and link to the raw SQLite and
uncommitted-attempt count. The raw ledger includes the uncommitted attempts.
An authorized consolidation without a confirming boundary appears abandoned
in the inspection view. Its raw checkpoint retains the open period.
A budget stop at tick 0 produces replay and ledger evidence without an EV-01
view because there is no committed resident delivery to inspect.

### Owner release and operator command

Run the offline preflight from `F:\p35-w1\ev06`. It prints the release hash and
the pinned run, content, wire and rehearsal inputs.

```powershell
uv run --offline --locked --no-env-file --directory backend python -m living_island.sim.v2.harness.live_resident preflight --implementation 92ce49726a653e62548655cd16e1aa8b6238c8fe
```

On 2026-11-25 the owner told Claude Code “现在就可以做，不需要等空闲，预算可以提高”
and approved this sheet for a single paid run during the morning peak. The
CNY 9.480838 reservation fits the remaining CNY 19.94656518. The CNY 20 phase
cap applies. The release start was rounded up from 09:07:13 Beijing time.

The release and reconciled EV-04 bundle are in the ignored `runs/` directory.
The bundle preserves DL-06's accumulated evidence, with CNY 0.05343482 settled
and CNY 0 outstanding, and adds the 2026-11-25 peak tariff. The release loader
accepted the window and both file pins matched the offline preflight.
[Dated tariff and model evidence](M14-provider-check.md#owner-release-on-2026-11-24)
· [Official CNY pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

| Artifact | SHA-256 |
| --- | --- |
| `runs/m14-ev06-ella-ledger.json` | `decb81579d48dbcd15e1ad4cd43a6124b77af80406fd633cf9a42407d383d32d` |
| `runs/m14-ev06-ella-release.json` | `de10716851e3c9993a155be0b88f4870387b7c74a7d370318565ac1e2d3f5d99` |

| Field | Value |
| --- | --- |
| `dispatch_on` | `2026-11-25` UTC. |
| `approval` and `wire_evidence` | References to the owner release and the dated model, Responses wire and tariff verification. |
| `preflight_sha256` | `f4ba7105f050e8b4fc3516384ffe25512f66a225b05266289818c8da4fa39871` for this checkout and executable pin. |
| `ledger_sha256` | SHA-256 of the exact ledger file above. |
| `max_cny` | Decimal string `"9.480838"`. |
| `dispatch_from` and `dispatch_until` | `2026-11-25T09:10:00+08:00` inclusive through `2026-11-25T12:00:00+08:00` exclusive. The window uses the 2026-11-25 EV-04 peak rates throughout. |
| `beijing_public_holidays` | `{"2026-11-25": false}` based on the owner's release for the morning peak. |

The operator command for the original release follows. It used the terminal's
`DEEPSEEK_API_KEY` process environment. The
runner uses no dotenv loader. `uv --offline` applies to package resolution.
`--live` enables DeepSeek HTTPS. The command claims `C:\Temp\li-heavy.lock` and
the one-time output directory exclusively.

```powershell
uv run --offline --locked --no-env-file --directory backend python -m living_island.sim.v2.harness.live_resident run --live --implementation 92ce49726a653e62548655cd16e1aa8b6238c8fe --release F:/p35-w1/ev06/runs/m14-ev06-ella-release.json --ledger F:/p35-w1/ev06/runs/m14-ev06-ella-ledger.json --out F:/p35-w1/ev06/runs/m14-ev06-ella
```

Estimated **4–6 minutes to record** 432 ticks at the rehearsed attempt count,
including checkpoint I/O, plus **about 3–5 minutes** for a replay and
inspection export. The live command verifies the final ledger and capture
offline before returning. Separate `replay` and `export` commands each verify
the capture again.
The `/0.2` fake recording took 86.4 seconds and the complete receipt took 271.3
seconds. The DL-06 recheck spent 9.792 seconds across seven provider attempts,
or about 1.40 seconds per attempt. At 109 dispatches that adds about 152
seconds to recording before backoff. Live latency, retries and actual tick
work can change the estimate. [DL-06 recheck](M14-provider-check.md#live-recheck-result)

### Owner run interruption and recovery

The retained SQLite audit has 185 committed boundaries, 151 dispatch claims,
150 terminals and CNY 0.63257112 settled. The owner reported 130 successful
terminals and 20 invalid outputs. The last claim was written before use-credit
raised `KeyError` and never reached transport. The capture and its checkpoint
at tick 185 were inspected read-only.

| Audit sequence | Finding |
| --- | --- |
| 2486–2487 | The tick-103 mechanical write v112 → v113 created current intention `m:ella:93`, replacing `m:ella:92`. |
| 2717, 2722 | Ella's 48-tick sleep triggered the tick-140 consolidation. Change set v113 → v114 had no record edits. |
| 2795, 2798, 2801 | Morning at tick 152 selected `m:ella:93` for `p:ella:2`. Its full resident projection was stored as fragment `e49cc22013bdc6fcce91946d27921eceea778c6429bf15e2dffd25bcf418eb34` with memory source version `115:375d98f4ccd037f54080f9dd1395dff497122ca1daedb95c2f43ecf53bb85a7e`. It appeared in the first decision's `prefix`. |
| 2856–2857 | `ella:t000099` cleared the intention at tick 154. Its history record was still reachable. |
| 3630–3635 | Tick-184 turn `ella:t000129` set a new intention. The mechanical revision v173 → v174 evicted `m:ella:93` to enforce the 20-record intention history limit. Boundary 184 committed at seq 3633. The checkpoint runtime blob at seq 3635 captured cursor 3634 and store v174 while its frozen prefix still carried `m:ella:93`. |
| 3644–3645 | At tick 185 `ella:t000130:decision` prepared and claimed a request that still listed the same fragment in `prefix`. Use credit covered that section and tried to update the deleted store head before transport. There is no terminal or committed tick-185 boundary. |

Morning freezes the selected revision's bytes. The decision assembler appended
that prefix and the day log without checking whether the referenced IDs were
still resident-visible. The fixed assembler projects both carriers against
the current resident view on each decision. Consolidation applies the same
projection to the current and pending contexts against its frozen base view.
This retains legitimate history and exact revisions of visible records, and
keeps the raw receipts and append-only log for inspection. The DL-28
use-credit writer continues to credit first exposure from the actual sent
manifest. [MM-09 and memory visibility](../../spec/memory-model-v0.1.md#5-supersession-review-merging-and-forgetting)
· [DL-28 use credit](../../spec/decision-loop-v0.1.md#61-strength)

**Live resume is unavailable.** The archived release pins `92ce497` and the
fixed sources change that pin. The interrupted boundary also contains an
exclusive dispatch claim at seq 3645, so the existing recovery path seals the
tail without resending. The original one-time capture path stays occupied.
EV-04 projects a CNY 0.133982 worst-case hold for the unmatched claim until
the owner reconciles the pre-exchange failure. The projected phase total is
CNY 0.68600594 settled, leaving CNY 19.18001206 after the hold. No additional
paid run was authorized for this rework.

This read-only verification command passed through tick 185, with one
uncommitted claim. It bypasses the mutating run lock and writes no report
inside the retained capture. The verified world hash is
`de81117c231bfa2d9ee36ef61c47fbaa754fa3aa9026d7d27352529cd0a4c22b` and the
store hash is `78752437455d2cc84f2a6e81532e6845d37caa778055c9018774534a55ee2094`.

```powershell
uv run --offline --locked --no-env-file --directory backend python -c "from pathlib import Path; from living_island.sim.v2.harness.live_resident import Case, Capture, verify; r = verify(Capture.open(Path('F:/p35-w1/ev06/runs/m14-ev06-ella'), Case.load(), write=False)); print(r.replay.frames[-1].tick, r.tail_attempts, r.world_hash, r.store_hash)"
```

### Owner-approved replacement release

The owner authorized one replacement through Claude Code under the standing
approval. Gate 2 passed for `4e22110` and `e0802e5`, and Claude Code pushed
`e0802e5` for CI. The detached checkout at `F:/p35-w1/ev06r` is pinned to
`4e2211081cb26b36d4c450f0abffd6eb978213f2`. Its offline preflight finished at
10:10:53 Beijing time on Wednesday 2026-11-25, so the release uses
**10:30 inclusive to 12:00 exclusive** on that date. The one-time capture
directory there is still unclaimed.

The peak tariff remains CNY 0.04 / 2 / 8 per million cache-hit input,
cache-miss input and output tokens. The runtime guard reserves at zero cache
and peak rates. Against the CNY 20 cap, EV-04 reconciles **CNY 0.68600594
settled** and retains **CNY 0.133982** for the original claim at seq 3645.
The replacement reserve is **CNY 9.480838** against **CNY 19.18001206** of
headroom, leaving CNY 9.69917406 outside the new reserve.
[Dated pricing evidence](M14-provider-check.md#owner-release-on-2026-11-24)

The old and replacement executables use the same local run ID in separate
checkouts. The replacement ledger labels the original capture
`m14-ev06-ella-original`, preserving its 151 claims, 150 terminals and all
attempt identities. Seq 3645 remains unmatched at cursor
`03d3757ff50353a15c853d27c74863e5dabf6600907424736707e00ae26d0e06.0.dispatch.json`.
The original audit remained read-only and its SHA-256 matched
`ce3bc7c013caf26c8c179670932d835a080ef684fecd60e65cc6f9d6ab41e104` before
and after validating the replacement artifacts.

| Artifact in `F:/p35-w1/ev06r` | SHA-256 |
| --- | --- |
| CLI preflight | `6128432ff72b4c92519d4f9071e47aaa3b7c19aed1d6bd653b4e722e50fac1c4` |
| `runs/m14-ev06-ella-ledger.json` | `d7bff2daadbf64f99b6922ec8053d849ad661aad13c7a4f4b2c8c2e1362d5c3b` |
| `runs/m14-ev06-ella-release.json` | `fe29be71cff2dfe35a9ef782227fcc29fb0d072cf0ffd3b692caecad21e1f088` |

The owner runs the following during the released window. It loads only
`DEEPSEEK_API_KEY` into the process environment and removes it on exit.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06r' -ErrorAction Stop
try {
    $ev06Pattern = '^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(?:"(?<key>[^"]+)"|''(?<key>[^'']+)''|(?<key>[^#\s]+))(?:\s*#.*)?\s*$'
    $ev06KeyLine = Select-String -LiteralPath 'E:\桌面\Living_World\.env' `
        -Pattern $ev06Pattern -ErrorAction Stop | Select-Object -Last 1
    if ($null -eq $ev06KeyLine) { throw 'DEEPSEEK_API_KEY is missing or invalid.' }
    $env:DEEPSEEK_API_KEY = $ev06KeyLine.Matches[0].Groups['key'].Value

    uv run --offline --locked --no-env-file --no-sync --directory backend `
        python -m living_island.sim.v2.harness.live_resident run --live `
        --implementation 4e2211081cb26b36d4c450f0abffd6eb978213f2 `
        --release ../runs/m14-ev06-ella-release.json `
        --ledger ../runs/m14-ev06-ella-ledger.json --out ../runs/m14-ev06-ella
    if ($LASTEXITCODE -ne 0) { throw "EV-06 exited with code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
    Remove-Variable -Name ev06KeyLine -ErrorAction SilentlyContinue
}
```

### Gate 3 evidence after the owner run

| Item | Status |
| --- | --- |
| Paid capture, realized horizon, spend by resident-day and fallback counts | Incomplete at tick 185. The raw audit, packets, opening checkpoint and committed checkpoint remain under `runs/m14-ev06-ella/`. Full Gate 3 accounting and analysis remain pending. |
| Offline rebuild | Verified read-only through committed tick 185, including the unmatched claim in the audit tail. The DL-05 verifier rebuilt request wires and store revisions and checked committed submissions, events and final state without a provider transport. |
| Verified export and analysis walkthrough | Pending paid capture and seal. Load the matching `replay.json` in the viewer, open analysis mode and select the fresh inspection directory. Attach the actual resident/period/turn IDs and artifact hashes once selected. |
| Decision and memory trace | Pending. Select a model-origin outcome and trace earlier packet/day-entry through the K-boundary change set and record revision, then subsequent morning, sent recall, decision citation and world result. Distinguish rendered, dispatched and cited evidence. |
| Skill and starter evidence | Pending. Report self-found skill evidence or an evidenced zero after the run. The starter-only grass-cord axe is due at M15. |
| Prior engineering receipts | [MM-16/MF-14 and DL-19](P3.5-MM-02.md#gate-3-receipts) · [Round 3](M14-plan.md#4-done-when) · [EV-13 rehearsal](M14-fake-workload.md#receipts-and-verified-exports) · [PR-05 provenance](P3.5-PR-05-review.md) · [PR-06 provenance](P3.5-PR-06-review.md) |
| Owner release and Gate 3 | The owner approved the original peak run and one replacement for 10:30–12:00 Beijing time on 2026-11-25. Final Gate 3 signature and live evidence revision are pending. |

For a separately released replacement capture, run these commands from its
checkout in a terminal without the provider key. The export command verifies
all shards and writes the viewer replay to `runs/m14-ev06-inspection-source/replay.json`.
Load that replay, open analysis mode and select `runs/m14-ev06-inspection`.
[EV-01 export contract](P3.5-EV-01.md)

```powershell
uv run --offline --locked --no-env-file --directory backend python -m living_island.sim.v2.harness.live_resident replay --out ../runs/m14-ev06-ella
uv run --offline --locked --no-env-file --directory backend python -m living_island.sim.v2.harness.live_resident export --out ../runs/m14-ev06-ella --destination ../runs/m14-ev06-inspection
pnpm --dir frontend dev
```
