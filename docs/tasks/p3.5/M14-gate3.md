# M14 Gate 3 — Ella live resident

## Owner pre-dispatch sheet · 2026-11-25

**The owner selected the tick-442 capture as the M14 live evidence.** It
passes the original 432-tick horizon and records Ella's death by
deprivation. The tick-185 and tick-432 captures are retained separately.
[Current Gate 3 table](#m14-live-evidence)
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
10:10:53 Beijing time on Wednesday 2026-11-25. The released window was
**10:30 inclusive to 12:00 exclusive** on that date.

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

The operator command for that release follows. It loads only
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

### Replacement evidence and owner walkthrough

This 432-tick capture is retained evidence from the first replacement.
The owner selected the later [tick-442 capture](#m14-live-evidence) for M14.

| Item | Status |
| --- | --- |
| Paid capture and realized horizon | The replacement in `F:/p35-w1/ev06r/runs/m14-ev06-ella/` completed 432 ticks, three whole game days. Ella, Mia and Ryan were alive at the final checkpoint. Ella had one open waking period, `p:ella:1`, and zero closed waking periods. |
| Spend and model use | 331 logical calls, 343 attempts, 330 successful parses, 13 invalid outputs and one fallback turn. Replacement spend was CNY 1.65184272 with no outstanding replacement charges. The phase ledger settles CNY 2.33784866 and retains the original CNY 0.133982 hold. |
| Offline rebuild | DL-05 replay passed through tick 432 with zero provider calls and zero uncommitted attempts. World SHA-256 `7a5e39b559bc672ae75ba806d2cd248a1270ff708500434f1fcf5a94ec1a97bd`. Store SHA-256 `6ffbf5f9ae3d21bb4c0e766c27ea88caf9047f023732ff892d2cb7622895ca7d`. The original capture has its own read-only verification through tick 185 and is retained as incident evidence. |
| Verified export and analysis walkthrough | EV-01 export passed with 331 decision records and all 2,092 referenced shards verified. The frontend importer opened the replay and the selected trace. [Artifact hashes and viewer steps](#artifact-verification-and-viewer-steps) |
| Decision and memory trace | The packet-to-action trace below is verified from the live journal. There are zero K-boundary consolidations, consolidation change sets, morning calls, sent recalls, use-credit writes and valid citations. The full continuity trace required by M14 is missing. |
| Skill and starter evidence | Zero skill records and zero self-found skill hypotheses. All 109 replacement store revisions contain only personality, social and intention record bodies. The starter-only grass-cord axe is due at M15. |
| Prior engineering receipts | [MM-16/MF-14 and DL-19](P3.5-MM-02.md#gate-3-receipts) · [Round 3](M14-plan.md#4-done-when) · [EV-13 rehearsal](M14-fake-workload.md#receipts-and-verified-exports) · [PR-05 provenance](P3.5-PR-05-review.md) · [PR-06 provenance](P3.5-PR-06-review.md) |
| Owner disposition | Retained as earlier evidence. This capture completed the horizon and lacked cross-period continuity. |

#### Realized spend and model use

Game days group dispatch ticks into 144-tick intervals. Each invalid output
counts as a charged attempt. Ryan and Mia were rule-controlled and had zero
model attempts or provider cost. [EV-04 reconciliation](P3.5-spend-ledger.md#opening-ledger)

| Ella game day | Dispatch ticks | Logical calls | Attempts | Invalid outputs | Model turns | Fallback turns | Settled CNY |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0–143 | 135 | 138 | 3 | 135 | 0 | 0.52210456 |
| 2 | 144–287 | 96 | 101 | 6 | 95 | 1 | 0.47855816 |
| 3 | 288–431 | 100 | 104 | 4 | 100 | 0 | 0.65118000 |
| **Replacement total** | **0–431** | **331** | **343** | **13** | **330** | **1** | **1.65184272** |

The only fallback was `ella:t000136` at decision tick 145 after two invalid
outputs. The world tagged it at `m14-ev06-ella:0000000146:000030`. All claims
were `decision` calls. The admitted request counter ranged from 11,271 to
239,954 tokens, with zero omissions. The 343 attempts recorded 59 `clear`,
162 `busy` and 122 `crowded` pressure readings. Provider usage was 13,363,968
cached input tokens, 341,326 uncached input tokens and 54,329 output tokens.
At the peak tariff those categories settled CNY 0.53455872, CNY 0.68265200
and CNY 0.43463200 respectively. The replacement used 343 attempts against
109 in rehearsal. It settled CNY 1.65184272 against the CNY 1.452171
central peak forecast and the CNY 9.480838 peak reserve. It reached the
horizon without an accounting stop.

The inspection cost projection allocates settled input charges in proportion
to counted tokens per sent section. Provider usage determines the actual
charge for each attempt. The aggregate section estimates reconcile to EV-04
at the ledger's pico-CNY precision.

| Sent section | Counted tokens | Estimated input CNY |
| --- | ---: | ---: |
| `system` | 41,160 | 0.001512700629 |
| `prefix` | 132,055 | 0.004853247868 |
| `day_log` | 17,185,054 | 0.480398920992 |
| `current_state` | 658,113 | 0.021077820491 |
| `schema` | 3,207,393 | 0.117877196857 |
| Wire framing and tokenization | 21,042,928 | 0.591490833163 |
| **Total input** | **42,266,703** | **1.217210720000** |

Output added CNY 0.43463200 and unassigned cost was CNY 0. The total is
CNY 1.65184272 across 343 attempts.

#### Live trace and the missing continuity links

1. At tick **356**, packet `m14-ev06-ella:perception:0000000356:ella` showed
   fruit at `fruit_02` through `perception.visible_entities[0]`. The builder
   logged it as `d:p:ella:1:629` (seq 6270). The `day_log` fragment
   `941b1722d5ebab22083b1c7cc08620196cdfa53c81cc61230b554760c7c267f2`
   was rendered in the full request and sent on `ella:t000283:decision`
   (seq 6283–6284, wire
   `f5a3e4a01672d81c35fa750ca3eea0acd618e5f871bcd761840d0d74ee9553c1`).
   The model submitted `ella:t000283:a` to gather from the observed tree.
2. That adopted output became day entry `d:p:ella:1:632`. Its set-intention
   mechanically wrote `m:ella:62` in v78 → v79 at seq 6293 (record blob
   `ec1b4e83c9771d7a04bbb3430de9170eb228c712207a28aa8a1d1a2b3697b9b9`).
   The gather transferred fruit `e:e72084c65d28c600` to Ella and settled
   under `compat_gather_fruit` at `m14-ev06-ella:0000000358:000022`.
3. At tick **358**, packet `m14-ev06-ella:perception:0000000358:ella`
   delivered the gather result in `perception.action_feedback[0]`. Its day
   entry `d:p:ella:1:637` (seq 6323) was sent as a `day_log` fragment with
   hash `60a3c96adefdc8ffae81a94db38142790eed58afa134bd5a521762e432121df4`.
   The same request rendered and sent `m:ella:62` in `current_state`, at
   revision `79:7fc6c1acd3afe5988e04db227dde4db9dc843200103dbfc851af67147df0b32b`
   and fragment hash `cb8dc424101dd3764b204b1a027300274a4d5489d4a930a769df72259d7bc44e`.
   The `ella:t000285:decision` wire was
   `76cd95c785795acfb828cc2fd0d8ac14838489410e8edd854c42fbbbc688d708`
   (seq 6332–6333). The model returned a paraphrase of the gather feedback
   in `cite`, and the validator recorded it as invalid. No valid citation
   was bound. The current-state intention earned zero use credit under DL-28.
4. The model-origin submission `ella:t000285:a` ate the same fruit at world
   tick **359**. `m14-ev06-ella:0000000359:000017` consumed the fruit, and
   `m14-ev06-ella:0000000359:000019` recorded `compat_eat_fruit` applied
   with `tastes_good`. Satiety rose from 2550 to 4550 in the intervening
   `needs_changed` event. The recording establishes delivery of the
   intention to the model. Reliance on that intention is unverified.

The sole sleep was `ella:t000121` at decision tick **125**. The world
recorded a six-tick sleep at `m14-ev06-ella:0000000126:000002` and a wake at
`m14-ev06-ella:0000000131:000014`. The wake packet logged
`d:p:ella:1:269`. Ella resumed deciding in `p:ella:1`. She never reached
the 36-tick K boundary. The audit has zero consolidation authorizations and
zero morning, recipe-recall or deliberate-recall receipts. All 331 decisions
belong to `p:ella:1`. The adopted turns have 959 invalid citation entries and
zero valid ones. Without a committed change set or any recall, the live chain
from earlier-period memory to citation cannot be supplied by this capture.

#### Artifact verification and viewer steps

Paths in the table are relative to `F:/p35-w1/ev06r/runs/`.

| Artifact | SHA-256 |
| --- | --- |
| `m14-ev06-ella/resident.sqlite` | `4130e1d92d2fc5c58d3092b035b97ab194228eca30b966776d4f6a1ac7adea63` |
| `m14-ev06-ella/result.json` | `df27ea736ef43abf7efd9e7cec825a4d3e29801a42aafe812526729612f3517b` |
| `m14-ev06-ella/checkpoints/432.json` | `002094ea1966a1b9e589c38567fc66266ed0e75b8d0b49700019a6570370c104` |
| `m14-ev06-ella/sanitized-evidence.json` | `152dc7d9155f4d46bbea98a82ab5b3b14c9b948929c68dd9af7399b15f129afe` |
| `m14-ev06-inspection-source/capture.json` | `004407f318269793e8a68cbe4efe5728d98410911041c8d803df149fd221ff35` |
| `m14-ev06-inspection-source/finished.json` | `ded1521fc44c44faf4d306ee737b312657fb23bace431113aa9d90dd4d26ddbb` |
| `m14-ev06-inspection-source/resident.sqlite` | `71440531f6bf05aa36df4f6bce8be488d74729a9f9e1b18c6ab2f45b44193eb9` |
| `m14-ev06-inspection-source/replay.json` | `8f54eb91a4a8a6ff98bf152490c14dd427e33258aacaeb78b2dd02aa7634fa85` |
| `m14-ev06-inspection/index.json` | `1510c68611e67a0c453f7ebeeb6e41beddfdfaee7dcdfd6def8c29ea4160fcc1` |

| Inspection shard | SHA-256 |
| --- | --- |
| Sleep decision `ella:t000121` | `e75f13e8c5669ce0fd565faaef101b2672e916e55a93fa3045dd0a2eadc4f47e` |
| Gather decision `ella:t000283` | `5d3385d291a441008be502c75246969ac5af6c6a599ea01b7237a6f33dfbfce7` |
| Eat decision `ella:t000285` | `f35bd971f72a6ca36f743f398d310e1a2d6f85600388ebf66a56cdd82498dad6` |
| Cost | `ad8e39541dcbf2764e8f1634c207f51c20b32ee25a7b9c2343bb3ddfee2c0168` |
| Metrics | `76dd20b21fb479d3f10fae40e767f8b5f71688c527b8241fc0664e8636868d3c` |

The capture receipt binds the finished export to raw SQLite through seq 7460.
The seal pins all 432 packet batches. The batches for ticks 356 and 358 have
SHA-256 `d680fdb67d177fcaeb936e319f72ce04a63a8a3953793b60b2c3e9dda4d1ae1b`
and `02202e935f7f30ca9aa1700241419cd4576f7c7d87a90d59daeab76d90f4d24f`
respectively. The verified index has 1,296 packet deliveries and 109 memory
revisions. Its metrics record zero skill hypotheses, consolidation rows and
memory-use observations.

The offline commands below ran at the pinned replacement checkout, with the
provider key removed from the process environment. The export command uses a
fresh destination and verifies every referenced inspection shard. To repeat an
export, choose a fresh `--destination`, which also creates a sibling
`-source` directory. [EV-01 export contract](P3.5-EV-01.md)

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06r'
Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06r'
uv run --offline --locked --no-env-file --no-sync --directory backend python -m living_island.sim.v2.harness.live_resident replay --out ../runs/m14-ev06-ella
uv run --offline --locked --no-env-file --no-sync --directory backend python -m living_island.sim.v2.harness.live_resident export --out ../runs/m14-ev06-ella --destination ../runs/m14-ev06-inspection
```

Start the viewer with `pnpm --dir frontend dev` from a checkout with the
locked frontend dependencies. Use the local URL printed by the command. The
viewer validator accepted all 433 display frames. The replay file contains
the initialization event and map frames. Detailed world events and call
evidence are in the inspection directory. The frontend importer accepted
all 2,093 files, opened the three turns and their source packets, and read
the cost totals. This validation used the viewer's importer under Node
with the same frontend sources as the pinned executable.

1. Click **Open replay…** and choose
   `F:/p35-w1/ev06r/runs/m14-ev06-inspection-source/replay.json`.
2. Click **Open inspection…**. Navigate into
   `F:/p35-w1/ev06r/runs/m14-ev06-inspection/` and select `index.json` and
   every shard in that directory with Ctrl+A. Open **Decision debug** in
   the lower right to enter analysis mode.
3. In **Inspection record → Decisions**, choose `ella:t000121` at tick
   125 and expand its sleep outcome. Then choose `ella:t000283` at tick
   356 for the gather and `ella:t000285` at tick 358 for the subsequent
   eat decision. **Open source packet** shows the exact perception and day
   entries. Expand **Full request · sent** and **Decision, citations and
   telemetry** to compare the outgoing evidence with citation validation.
   Open the `act_settled` outcome to see the world tick.
   **Inspection record → Analysis → cost** shows the resident-day costs.

### Owner-approved fixed-packet probe

The owner approved one short probe on 2026-11-25 with a total cap of
**CNY 0.50**. Offline preflight completed at **12:36:08 Beijing time**,
before the 13:40 cutoff. The original window of 12:00–14:00 Beijing time
expired without a dispatch. Its off-peak cache-hit, cache-miss and output
rates were CNY 0.02, 1 and 4 per million tokens. The reservation uses peak
rates of CNY 0.04, 2 and 8. [Dated pricing evidence](M14-provider-check.md#owner-release-on-2026-11-24)

The probe uses `compat-v1` verb descriptions and schema, Ella's explorer
profile, the pinned DeepSeek Responses transport and model
`DeepSeek-V4.1-Flash-1017`, and the byte upper-bound counter `/0.4`. Both
decision prompts are `/0.4`. Five synthetic packets pin the inputs and
judgment separately from the previous capture. The post-recall fixture has
a staged successful recall so the probe sends only the two decision
stages required for citation comparison. [Owner sleep and map rulings](../../spec/open-questions.md#oq-p35-m14-3-sleep-duration-and-recovery-cues)

| Packet | Counted input | Pass criterion |
| --- | ---: | --- |
| Initial decision with a day entry and a prior prose citation | 11,344 | Return an act with at least one bare ID that binds to a sent day entry and zero invalid citations. |
| Decision after staged recall | 11,330 | Return an act with a bare memory or day-entry ID that binds to the sent recalled fragment and zero invalid citations. |
| Low stamina, no urgent need | 10,987 | Choose `sleep` for 36–54 ticks. The lower bound evaluates the choice against K and is not disclosed in the prompt. |
| Shore at `(36,31)`, blocked target `(35,31)`, spring at `(38,31)` | 11,164 | Select `move_to` on an explored land tile adjacent to the spring. Valid targets in this packet are `(37,31)`, `(38,30)` and `(38,32)`. |
| Fixed follow-up at `(37,31)` | 11,068 | Choose `drink` from the adjacent spring with no target or instrument. The fixed packet is assessed independently of the prior reply. |

Overall pass requires all five criteria on the first attempt and fully
settled usage within the cap. Prep measured 55,893 counted input tokens
and holds the 8,000-token limit on each of the five outputs. With zero
cache hits the reserve is **CNY 0.431786 at peak**. The expired off-peak
window would have cost up to CNY 0.215893. Before each claim the runner
checks the signed window, settled probe charges plus outstanding holds and
the worst-case peak cost of the candidate against the probe and phase
limits. There are no retries or fallbacks. The output directory is
exclusive and the probe cannot resume.

The pinned phase evidence carries CNY 2.33784866 settled and the original
CNY 0.133982 hold, leaving CNY 17.52816934 of phase headroom. EV-04 tariff
rows are date-scoped. The wrapper ledger therefore retains the earlier
peak-billed evidence byte for byte and supplies a separate
probe slice. It combines their reconciled totals without re-rating the
earlier claims. [Phase ledger](P3.5-spend-ledger.md#opening-ledger)

| Original input under `runs/m14-ev06-probe-inputs/` | SHA-256 |
| --- | --- |
| `probe.py` | `2311fc5191834afe96864e0bb784fe0fcc9cfc2be94218cf519c980ef0c02f4f` |
| `preflight.json` | `d62e75351de574c0494aed4ce5f5900972bffad0859936ac62ccdafed3ff739b` |
| `packets.json` | `36af51cf9e3f2414de48e3bb19b2ccb5a0e68c7f606f45afdf126def609b3421` |
| `ledger.json` | `cec755e00f94383f7461726f8290cf69cde01403355747fcbc8036ec7f802fd9` |
| `release.json` | `6082375d506217fc8a3b7c0783f6731fb6980e0159f01afa86af2379b6c72b85` |

The executor ran the affirmative and negative cases with fake transport.
The fixture bound exact citations, accepted the qualifying sleep and
adjacent approach, and rejected prose, a six-tick sleep and a blocked
target. Cap and closed-window cases sent nothing and wrote no claim.
The live output is reserved for `runs/m14-ev06-probe/`. It will contain
the input packets, durable provider audit, verdicts and probe-only EV-04
ledger. A full replacement needs separate owner authorization.

#### Peak-window reissue

Gate 2 passed for `f794cb4`, including the runner pinned above. The owner
reissued the one-time probe for **Wednesday 2026-11-25, 15:10 inclusive to
18:00 exclusive Beijing time**. Offline validation reproduced the existing
preflight and packet bytes. The reviewed runner refused the original
off-peak tariff for the new window. With the owner's approval, the ledger
wrapper's probe-only settlement row now uses peak cache-hit, cache-miss and
output rates of CNY 0.04, 2 and 8 per million tokens. The embedded phase
ledger remains byte-identical and retains the CNY 0.133982 hold.

The preflight SHA-256 is unchanged. The runner, pass rule, CNY 0.50 cap and
CNY 0.431786 peak reserve carry forward. The original release and wrapper
pins above document the expired window. Use the reissued files at the same
paths. The offline release check passed with the peak row. It confirmed
15:10 is admitted and 18:00 is excluded. The live output is still unclaimed.

| Active input under `runs/m14-ev06-probe-inputs/` | SHA-256 |
| --- | --- |
| `ledger.json` | `18d7dabb0c1c01eee041c3b636ff45d47873e7286a10c7f247e3991618e93690` |
| `release.json` | `7931ba791d19e73ac837be7951153c14d8b124a924af7266aaf91943ee0e354a` |

Use this PowerShell block from the EV-06 checkout during the released
window. A nonzero exit preserves the probe evidence for review.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06' -ErrorAction Stop
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06'
$ev06ProbeHash = (Get-FileHash -LiteralPath 'runs/m14-ev06-probe-inputs/probe.py' -ErrorAction Stop).Hash
if ($ev06ProbeHash -ine '2311fc5191834afe96864e0bb784fe0fcc9cfc2be94218cf519c980ef0c02f4f') {
    throw 'EV-06 probe script differs from the verified release.'
}
try {
    $ev06Pattern = '^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(?:"(?<key>[^"]+)"|''(?<key>[^'']+)''|(?<key>[^#\s]+))(?:\s*#.*)?\s*$'
    $ev06KeyLine = Select-String -LiteralPath 'E:\桌面\Living_World\.env' `
        -Pattern $ev06Pattern -ErrorAction Stop | Select-Object -Last 1
    if ($null -eq $ev06KeyLine) { throw 'DEEPSEEK_API_KEY is missing or invalid.' }
    $env:DEEPSEEK_API_KEY = $ev06KeyLine.Matches[0].Groups['key'].Value

    uv run --offline --locked --no-env-file --no-sync --directory backend `
        python ../runs/m14-ev06-probe-inputs/probe.py --live `
        --release ../runs/m14-ev06-probe-inputs/release.json `
        --ledger ../runs/m14-ev06-probe-inputs/ledger.json
    if ($LASTEXITCODE -ne 0) { throw "EV-06 probe exited with code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
    Remove-Variable -Name ev06KeyLine -ErrorAction SilentlyContinue
}
```

#### Fixed-packet probe result

The peak-window probe finished with five settled first attempts and no
outstanding probe charges. **Three of five passed** at **CNY 0.03291064**.
Both citation cases bound valid IDs to sent evidence with no invalid
citations. The initial act cited `d:p:ella:1:2`. The post-recall act cited
that packet's `d:p:ella:1:2` and recalled `m:ella:1`. The fixed adjacent
packet selected `drink`.

| Failed sample | Returned act and the model's stated reason |
| --- | --- |
| `sleep`, `ella:t000096:decision` | Moved to `(34,32)`. “Curious about the unknown tile and the woods beyond; stamina is low but exploring nearby is worth it.” Terminal seq 62. |
| `spring_approach`, `ella:t000100:decision` | Moved to the spring tile `(38,31)`. “Low hydration; head to the known spring.” Terminal seq 67. |

| Retained probe artifact under `F:/p35-w1/ev06/runs/m14-ev06-probe/` | SHA-256 |
| --- | --- |
| `result.json` | `faa814a87731a7e3c6b77c3f911824b20432219cc2cb2c23a55c89018857472e` |
| `provider-probe.sqlite` | `d6e05924490ab94ae50be96965a5343e7a6b499b85e06d3b0a93ac5c282598c1` |
| `ledger-evidence.json` | `433b101a5162a324203ed67eda8306fce9a4b6b9c1043cb91d3a273d571d5795` |

The owner kept the sleep cue and approved an adjacent-drinking reminder
in the map's spring line. The owner extended the full run horizon to 576
ticks. Phase spend is now **CNY 2.37075930 settled** with **CNY 0.133982
held**, leaving **CNY 17.49525870** before the new reserve. [Horizon amendment](../../spec/open-questions.md#oq-p35-m14-2-evidence-sufficient-for-the-paid-provider-check-and-horizon) · [Spring display follow-up](../../spec/open-questions.md#oq-p35-m14-4-reading-explored-terrain-and-water-approaches)

### Four-day full-run sizing

The new case runs Ella, memory on, with Ryan and Mia rule-controlled in
`compat-v1` at seed `20261108` for **576 ticks**. The map part is now
`state-map/0.3` and tells Ella to drink from a tile next to an explored
spring. All sleep wording and rules carry forward. The compatibility
pack has mental fatigue disabled, so a qualifying sleep is the available
route to the 36-tick waking-period boundary in this case. The four-day
extension gives the resident more time to choose such a sleep.
[Compatibility physiology](../../spec/starter-content-v0.1.md#41-needs-and-physiology) · [Waking-period rule](../../spec/memory-formation-v0.1.md#2-the-waking-period-boundary)

The 576-tick EV-05 Ella rehearsal uses the normal host with a fake
transport and network calls disabled. It records each sent input bound in
dispatch order and counts retries as separate attempts. Reserve each sent
bound at zero cache and CNY 2 per million input tokens plus the 8,000-token
output cap at CNY 8 per million, all at peak. The runtime stop guard uses
the same cap, settled spend, outstanding holds and scheduled remainder
checks as the previous release.

| Game day | Rehearsed attempts | Counted input bound | Output tokens held | Peak reserve CNY |
| --- | ---: | ---: | ---: | ---: |
| 1 | 47 | 551,104 | 376,000 | 4.110208 |
| 2 | 33 | 375,923 | 264,000 | 2.863846 |
| 3 | 29 | 363,856 | 232,000 | 2.583712 |
| 4 | 36 | 423,035 | 288,000 | 3.150070 |
| **Total** | **145** | **1,713,918** | **1,160,000** | **12.707836** |

All four days fit the CNY 17.49525870 phase headroom. CNY 4.78742270
remains outside the reservation. The CNY 0.133982 hold for the original
unmatched claim stays in the release ledger. The ledger retains both
replacement and probe costs and keys the prior completed 432-tick run as
`m14-ev06-ella-replacement-432` to distinguish it from the next capture.
[Phase ledger](P3.5-spend-ledger.md#opening-ledger)

#### Rehearsed waking-period continuity

The fake workload completed and replayed all 576 ticks offline. At tick
46 Ella chose 36 ticks of sleep. Packet `ev05-ella:perception:0000000047:ella`
and event `ev05-ella:0000000047:000002` confirm sleep started. She woke
naturally at `ev05-ella:0000000082:000006`. The same boundary closed
`p:ella:2` with selection `p:ella:2:47:selection` and committed change set
`p:ella:2:47:change_set`, advancing the store from v19 to v54 and producing
`m:ella:5`. At tick 82 the adopted `p:ella:3:morning` selected `m:ella:1`,
and `ella:t000010` was a model-origin decision in `p:ella:3`. These are
scripted workload results. The paid run will supply the live behavior
evidence.

| Artifact under `F:/p35-w1/ev06/runs/m14-ev06-576-fake/` | SHA-256 |
| --- | --- |
| `ella/resident.sqlite` | `780d8b45c5fea228399b51b71cf64e5905ffd25dbbc558ff70c94c5f10a6fe07` |
| `receipt.json` | `9a8d6806445bea7f6cb097721228f34199d4e4f3d615a5026c04ff400cb9f1d7` |
| `inspection-ella/index.json` | `edd3c965701088b6056454c61137f10b44f9befe8aa959e6e725f480d89dc35f` |
| `continuity.json` | `5f48163bd93a909771c4a4664a8538f74c597a6905018cccdaa556a1db76a7e9` |

#### Four-day live release

The detached checkout at `F:/p35-w1/ev06r2` pins executable commit
`7e5ffc52c63760551899cdd73f9d7467c249f616`. Its locked offline preflight
finished at **15:36:29 Beijing time on 2026-11-25**, before the 17:15
cutoff. The released window is **15:30 inclusive to 18:00 exclusive
Beijing time on Wednesday 2026-11-25**. The release validation matches
the peak cache-hit, cache-miss and output rates of CNY 0.04, 2 and 8 per
million tokens. The pack, vocabulary, profile, setup, seed and action
schema hashes match the prior pinned case. M13 calibration is unchanged.
[Peak tariff evidence](M14-provider-check.md#owner-release-on-2026-11-24)

| Input in `F:/p35-w1/ev06r2/runs/` | SHA-256 |
| --- | --- |
| `m14-ev06-ella-preflight.json` | `baab10d2064c225b037f6945dd9791d196f1a24cd06d9745ea71599d632b9a52` |
| `m14-ev06-ella-ledger.json` | `c0bf0bbb19be5c4fbf5e7cdad50ed13fa5194cf7b97106d63d36ccfc67ef897d` |
| `m14-ev06-ella-release.json` | `23afb05ddddc69cb1826274f1c15da51b0a6f797bf3c5f56078f6814419150a5` |

Run this PowerShell block in the released window. The guard checks the
window before loading the key. The one-time capture directory is
`F:/p35-w1/ev06r2/runs/m14-ev06-ella/`.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06r2' -ErrorAction Stop
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06r2'
$ev06Start = [DateTimeOffset]::Parse('2026-11-25T15:30:00+08:00')
$ev06End = [DateTimeOffset]::Parse('2026-11-25T18:00:00+08:00')
$ev06Now = [DateTimeOffset]::UtcNow
if ($ev06Now -lt $ev06Start -or $ev06Now -ge $ev06End) {
    throw 'Outside the EV-06 release window on 2026-11-25, 15:30–18:00 Beijing.'
}
try {
    $ev06Pattern = '^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(?:"(?<key>[^"]+)"|''(?<key>[^'']+)''|(?<key>[^#\s]+))(?:\s*#.*)?\s*$'
    $ev06KeyLine = Select-String -LiteralPath 'E:\桌面\Living_World\.env' `
        -Pattern $ev06Pattern -ErrorAction Stop | Select-Object -Last 1
    if ($null -eq $ev06KeyLine) { throw 'DEEPSEEK_API_KEY is missing or invalid.' }
    $env:DEEPSEEK_API_KEY = $ev06KeyLine.Matches[0].Groups['key'].Value

    uv run --offline --locked --no-env-file --no-sync --directory backend `
        python -m living_island.sim.v2.harness.live_resident run --live --through 576 `
        --implementation 7e5ffc52c63760551899cdd73f9d7467c249f616 `
        --release ../runs/m14-ev06-ella-release.json `
        --ledger ../runs/m14-ev06-ella-ledger.json --out ../runs/m14-ev06-ella
    if ($LASTEXITCODE -ne 0) { throw "EV-06 exited with code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
    Remove-Variable -Name ev06KeyLine -ErrorAction SilentlyContinue
}
```

### M14 live evidence

The owner accepted this capture against the original 432-tick horizon on
2026-11-25. The runner reports `incomplete` and `resident_died` at tick 442
because the released run had a 576-tick limit. The last world step committed
normally. The four-day extension had assumed fainting, which is disabled in
`compat-v1`. The two earlier captures remain archived. [Owner decision](../../spec/open-questions.md#oq-p35-m14-2-evidence-sufficient-for-the-paid-provider-check-and-horizon)

| Gate 3 item | Verified live evidence |
| --- | --- |
| Capture and horizon | `F:/p35-w1/ev06r2/runs/m14-ev06-ella/`, executable `7e5ffc52c63760551899cdd73f9d7467c249f616`. Three complete game days and ten ticks of day four. No interruption or budget refusal. |
| Death | `m14-ev06-ella:0000000442:000007` records `DEPRIVATION`. Satiety reached zero at tick 300 and stayed there. At death hydration was 9,100 and health fell from 60 to zero. [World cause chain](#starvation-and-food-finding) |
| Spend and model use | 311 logical calls, 328 attempts, 310 parsed responses, 18 invalid outputs, and one fallback turn. CNY 1.76211228 for this run and no outstanding charge. The phase settles CNY 4.13287158 and retains the earlier CNY 0.133982 hold. [Resident-day accounting](#realized-m14-resident-day-accounting) |
| Periods and memory | `p:ella:1` closed at 305 and `p:ella:2` at 420 after 36 ticks of sleep each. Both change sets committed empty revisions and both mornings adopted an existing-memory selection. `p:ella:3` ended with Ella's death. The complete carried-memory trace below reaches a valid citation and a world result. All proposed consolidation edits were dropped, so this capture has no consolidation-created record to trace. [Memory trace](#live-continuity-through-a-carried-intention) |
| Citations and use credit | 766 adopted citation entries, with 748 valid and 18 invalid IDs. Zero prose citations. There were 384 record credits across 83 dispatches. [Citation and credit counts](#citations-and-memory-use) |
| Skill and starter evidence | Zero skill record bodies in 397 audited store revisions. Neither consolidation wrote a record. Starter-only grass-cord axe evidence remains due at M15. [M15 food-finding finding](#starvation-and-food-finding) |
| Offline verification and viewer | Replay matched through 442 with zero provider calls. EV-01 verified all 2,414 inspection shards. The frontend importer opened the three example records. [Replay, seals and viewer steps](#live-artifact-verification-and-viewer-steps) |
| Retained evidence | The interrupted tick-185 capture remains in `F:/p35-w1/ev06/runs/m14-ev06-ella/`. The earlier 432-tick capture remains in `F:/p35-w1/ev06r/runs/m14-ev06-ella/`. |
| Owner disposition | The owner accepted the horizon and designated this capture as the live evidence. Gate 3 remains for owner review, including the absence of consolidation-created records. |

#### Realized M14 resident-day accounting

Game days group dispatch ticks into 144-tick intervals. Ella was the only
model-controlled resident. Mia and Ryan used rule policies and incurred
zero provider spend.

| Ella game day | Dispatch ticks | Logical calls | Attempts | Invalid outputs | Model decision turns | Fallback turns | Settled CNY |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0–143 | 126 | 128 | 2 | 126 | 0 | 0.50088848 |
| 2 | 144–287 | 98 | 110 | 13 | 95 | 1 | 0.76576228 |
| 3 | 288–431 | 78 | 80 | 2 | 74 | 0 | 0.45628568 |
| 4, partial | 432–441 | 9 | 10 | 1 | 9 | 0 | 0.03917584 |
| **M14 run** | **0–441** | **311** | **328** | **18** | **304** | **1** | **1.76211228** |

There were 17 retries. Attempts comprised 322 decisions, two consolidation
selections, two change sets and two mornings. No recall call was sent. The
single fallback was `ella:t000152` at tick 176 after invalid output and used
`rule-based-v0`. The guard omitted zero fragments. The pinned counter
measured 3,731–164,307 input tokens per dispatch. [Phase ledger](P3.5-spend-ledger.md#opening-ledger)

The sent manifests allocate the CNY 1.33262428 input charge as follows.
Output contributed CNY 0.42948800 and unassigned cost was zero. The
allocation estimates use the counter's section shares. EV-04 prices actual
provider usage at the peak tariff.

| Sent section | Counted tokens | Estimated input CNY |
| --- | ---: | ---: |
| `system` | 65,144 | 0.004558246145 |
| `prefix` | 246,574 | 0.024385744303 |
| `day_log` | 11,414,808 | 0.557066603278 |
| `current_state` | 608,456 | 0.049818042665 |
| `schema` | 3,017,912 | 0.194469644726 |
| Wire framing and tokenization | 9,141,952 | 0.493864412495 |
| `index_header` | 24 | 0.000014193280 |
| `index` | 9,303 | 0.006936486960 |
| `required_records` | 952 | 0.000553533830 |
| `selected_records` | 1,634 | 0.000957372318 |

#### Live continuity through a carried intention

1. At tick **269**, packet `m14-ev06-ella:perception:0000000269:ella`
   delivered completed rest feedback through `perception.action_feedback[0]`.
   Its day entry `d:p:ella:1:526` is at seq 5597. `ella:t000221` cited
   it, chose a 36-tick sleep and set an intention to drink after waking
   before searching for food. The adopted output became `d:p:ella:1:527`
   at seq 5613 and supplied the source for mechanical intention
   `m:ella:184` in store revision v237 at seq 5617 (record body
   `eae4e6f5b99c07b739d343c4f5389eb179b9ef19b9783a57cb740680022d2462`).
2. Sleep started at `m14-ev06-ella:0000000270:000002` and ended naturally
   at `m14-ev06-ella:0000000305:000008`. The sent change-set input
   `p:ella:1:270:change_set` (seq 5830, wire
   `89a41e78aa3ff5727dc95634a43b04a4979128896bbf9bfede49858cb42a2efa`)
   carried both day entries and selected `m:ella:184` at v237. Its
   proposal to supersede that intention (`op3`) was dropped for authority.
   The committed v239 → v240 change-set revision at seq 5834 has zero
   edits. The intent record kept content hash
   `26cf5f300f2b182281e5084d90303dc24754065a004da78d222dd422b5ed7e9e`.
   `p:ella:1` closed at tick 305 (seq 5839).
3. At tick **305**, `p:ella:2:morning` received the v240 index and
   current intention, then selected `m:ella:184` (seq 5858). The full
   `ella:t000222:decision` request **rendered and sent** the earlier
   intention in `prefix` and `current_state`. The prefix fragment is
   `ac3c83eda91d45651d59eedc28eaba2d38bb8b643a16d498826c4d8a3ac8dd3f`.
   The current-state fragment is
   `662cd53d7a6ff5fd44b84edd9cfd27afebc82ee4a873b05017834a564ccb017b`.
   Dispatch seq 5864 pins wire
   `d4bb989d124c39b4c72b04ffbd7f479bc4b0829f29ba03294b190f87c38802fd`.
   Ella **cited** `m:ella:184`, and seq 5870 binds that ID to both
   immutable v240 fragments. DL-28 credited the prefix exposure once.
4. `ella:t000222:a` submitted an untargeted `drink` at replay tick **305**.
   At replay tick **306**, `m14-ev06-ella:0000000306:000007` applied
   `compat_drink_spring` and `...:000006` raised hydration from 5,100 to
   10,000 before the ordinary physiology step. The dispatch and citation
   prove the source was sent and named. The world result confirms the
   drink, while the action reason also refers to the immediate body state.

The second sleep started at tick 385 and ended naturally at tick 420.
`p:ella:2:385:change_set` wrote v377 → v378 with zero edits (seq 7851).
Its receipt closed `p:ella:2` (seq 7856) and `p:ella:3:morning` adopted
nine existing IDs (seq 7872). Across the two change sets, all 11 proposed
operations were dropped: six for format, two for authority and three for
dependency. Both receipts record zero episodic records created. The
verified cross-period chain carries an existing intention through a
committed revision. A consolidation-created or revised memory has no
live example in this capture.

#### Citations and memory use

Counting each adopted decision's `cite` array once gives **766** entries
across 304 outputs. The arrays agree with the 304 binding facts. Of 517
day-entry IDs, 515 bound validly. Of 249 memory IDs, 233 bound validly.
The 18 invalid entries were still ID-shaped. There are 303 turns with a
valid citation and 225 with a valid memory citation. The preliminary
2,020 figure is unreproduced on the adopted-act denominator.

Dispatch-time use accounting records **384 credits across 83 unique
decision dispatches** and ten record IDs. `p:ella:1` has zero credits,
`p:ella:2` has 213 on 64 dispatches, and `p:ella:3` has 171 on 19. In the
example, seq 5865 credits the four sent prefix records, including
`m:ella:184`, before the terminal. Seq 5870 separately records the model's
citations. The revision audit traces v0 through v397 and contains 556
record bodies: 489 intention, 66 social and one personality. There are
zero skill bodies. A `skills_hypothesis` string in the dropped episodic
proposal `op1` supplies no skill record or self-found witness.

#### Starvation and food finding

Ella never raised satiety or acquired a carried item. The world reports
satiety crossing below 2,000 at tick 221 (`m14-ev06-ella:0000000221:000003`)
and reaching zero while asleep at tick 300
(`m14-ev06-ella:0000000300:000008`). Health fell from 10,000 by 70 each
tick from 300 through 441, then fell from 60 to zero at tick 442
(`m14-ev06-ella:0000000442:000006`). The adjacent `resident_died` event
`m14-ev06-ella:0000000442:000007` names `DEPRIVATION` at `(44,31)`.
Hydration was 9,100 and stamina 7,920 at death. Satiety stayed zero, which
identifies starvation as the recorded deprivation chain.

For M15, Ella's 17 `gather` intents all failed `INVALID_TARGET`. Both
`eat` intents resolved `unmatched`. Her delivered terrain never showed a
fruit-tree tile and her entity view supplied no fruit or fruit-tree ID.
At tick 342 the engine's unmatched-eat descriptor
`m14-ev06-ella:0000000342:000014` listed `e:4613441a83dc497f`, a fruit item
Mia carried. Ella's tick-341 and tick-342 packets showed an empty inventory
and no fruit entity. Ella never saw a fruit tree and invented her gather
targets. The same world applied seven gathers and five eats for each
rule-controlled companion. Ella drank successfully 12 times. For M15,
the food-finding case is discovering a fruit tree, selecting an exposed
gather target and acquiring food in time to eat.

#### Live artifact verification and viewer steps

The offline rebuild verified through tick **442** with **zero provider
calls** and **zero uncommitted attempts**. The final world SHA-256 is
`0e2c0e8036730c8a889af4f3a8dff72e47887956c4c102d2bcc280760e8e47c7` and
the final memory store SHA-256 is
`76d82558db63a828c8741e3931a9d3fb4043e5addcd5003cfc22545cd7c851fe`.
The seal verified 442 packet batches, the replay and the sealed SQLite.
The exporter verified all **2,414** referenced shards, including 305
decisions, 311 calls, 1,326 resident deliveries and 397 store revisions.
The capture receipt binds the raw audit hash and cursor 8307. The frontend
importer validated all 443 replay frames, opened the three inspection
records below and showed Ella dead with satiety zero at tick 442. The
replay supplies map frames. Detailed world events are in inspection.

| Artifact under `F:/p35-w1/ev06r2/runs/` | SHA-256 |
| --- | --- |
| `m14-ev06-ella/resident.sqlite` | `d0f86cf03d0b18c94cc81a39e3ceef22d6c885bb75057d8975fc2ee9f93568f9` |
| `m14-ev06-ella/result.json` | `eae888545ed38318924a708a238f2912078abbb2acc49b198d956291dafa547b` |
| `m14-ev06-ella/checkpoints/442.json` | `5474d41784e5fe7909315b65a01539a415068605756f73b381af291fede96f31` |
| `m14-ev06-ella/sanitized-evidence.json` | `5099f7fba05dfd19f928cdb638484600d52a270d55ed7a2e137183814ad81543` |
| `m14-ev06-inspection-source/finished.json` | `f859bf9cc0ee8efa63c8fcbd2357e05c8d992ae62744f9668790676be02dc764` |
| `m14-ev06-inspection-source/capture.json` | `8f6248de500076494cd62d32d4b33e4435924333d2bd5ab447438b880af67ae8` |
| `m14-ev06-inspection-source/resident.sqlite` | `3c5021d3a878d49b5f46dd04e1af7f98168798a8fbd9fb624129280fabf78d6b` |
| `m14-ev06-inspection-source/replay.json` | `1331ae601df35696f434833aa4ea89aeed7ca663ec751d76b1f7e2eeab251686` |
| `m14-ev06-inspection/index.json` | `9a83925b97ce0f1e4f6254d48471d7c07082c21499b8c126d480a423a6bbf250` |

| Inspection shard | SHA-256 |
| --- | --- |
| Consolidation `p:ella:1:270` | `7a99bc1ef5a3336a0cc301a56e9fa5510504ff11ea4e295c0c060a2d4a71ac26` |
| Morning `p:ella:2:morning` | `06097f76f746d3d7b7a7a1552173d038ce4374eded7d8cd6233b0f41ae8a857e` |
| Decision `ella:t000222` | `22c025b90afd37cf2caedc1efb94267140f8de90a4214010b7597b3ce9ade8d3` |
| Decision packet `m14-ev06-ella:perception:0000000305:ella` | `efa3439e9c708391660c0930e1cb1c5e7d3aa7130b5e20c74d040bb5acc10984` |
| Cost | `e2b2586f1f8648bf446785dd6fa093662b72bab3d05c1df42ab7cb301503f54a` |
| Metrics | `7ce6a7eb8707d295d3e945c53f71aa2011b16848284aa9d780dbcce9a69cb5a6` |

The executor rebuilt and exported from the executable checkout with the
provider key removed from the process environment. A repeat export
requires a fresh destination and creates its own sibling `-source`
directory.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06r2'
Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06r2'
uv run --offline --no-env-file --locked --no-sync --directory backend python -m living_island.sim.v2.harness.live_resident replay --out ../runs/m14-ev06-ella
uv run --offline --no-env-file --locked --no-sync --directory backend python -m living_island.sim.v2.harness.live_resident export --out ../runs/m14-ev06-ella --destination ../runs/m14-ev06-inspection
```

Start the viewer with `pnpm --dir frontend dev` in a checkout with the
locked frontend dependencies. Use **Open replay…** to load
`F:/p35-w1/ev06r2/runs/m14-ev06-inspection-source/replay.json`. Use
**Open inspection…** to select `index.json` and every JSON shard inside
`F:/p35-w1/ev06r2/runs/m14-ev06-inspection/`. Open **Decision debug** in the
lower right and use **Inspection record** for the three linked views.

1. **Period boundaries → `p:ella:1:270`.** At tick 305, expand the
   consolidation record and the two calls. Look for `op3` and the empty
   committed write to v240.
2. **Calls → `p:ella:2:morning`.** At tick 305, expand the sent request and
   parsed output. Find `m:ella:184` in the index and selected IDs.
3. **Decisions → `ella:t000222`.** Open the source packet and inspect
   **Cited · m:ella:184**, **Full request · sent**, and
   **Decision, citations and telemetry**. Expand `act_settled` and use
   **Show ella at tick 306** beside it to jump to the applied drink.

### Consolidation contract repair and one-time probe

The tick-442 capture showed two committed change sets with no edits. The new
`consolidation_selection/0.4` and `consolidation_change_set/0.4` prompts describe the
existing authority and evidence rules. The change-set schema shows `new:<n>`
refs, the 160-character single-line gist limit, exact content fields for
episodic, belief and skill additions, the source forms and the read-only
status of intentions. The sent user input shows the actual change-set call
ID for inferred evidence and carries the full resident-safe personality
revision even when the model selects no records. The existing validator,
commit rules and M13 calibration pins are unchanged.
[Memory formation §§3.2–3.5](../../spec/memory-formation-v0.1.md#32-call-1-selection)
· [Memory model §§2–3](../../spec/memory-model-v0.1.md#2-the-record-envelope)

The offline regression stages all 11 captured operations against the recorded
base records and sent allowlists. Each primary verdict below matches the audit.
The regression also commits an observed episodic record, an inferred belief
citing `new:1` and a one-step trait change. The next fake morning receives the
new episode's store ID and selects it into its prefix.

| Call | Operation | First recorded reason | Rule or dependency |
| --- | --- | --- | --- |
| `p:ella:1:270:change_set` | `op1` | `format` | `new-1` is outside the producer-ref format. The gist was 187 characters and the episodic content used unsupported fields. Its inferred source also named decision call `ella:t000221`. |
| same | `op2` | `format` | `new-2` is outside the producer-ref format. The episode used `needs_at_wake` and a string `position` in its content. |
| same | `op3` | `authority` | Tried to supersede intention `m:ella:184`. |
| same | `op4` | `depends_on` | Cited `op3`'s intended target. Its `new-3` ref, 190-character gist, episodic `steps` field and inferred call ID also violated the contract. |
| `p:ella:2:385:change_set` | `o1`, `o2`, `o3` | `format` | Used store-style refs `m:ella:249`, `m:ella:250` and `m:ella:251` for adds and proposed kind `observation` with unsupported content. |
| same | `o4` | `authority` | Tried to update intention `m:ella:248`. |
| same | `o5` | `format` | Proposed curiosity +1 while its current value and maximum were both 4. The old request also omitted the full personality revision, which trait provenance requires. |
| same | `o6` | `depends_on` | Shared the personality mutation with dropped `o5`. |
| same | `o7` | `depends_on` | Shared that mutation with dropped `o5` and `o6`. |

The captured parsed reply hashes are
`db7ab967cedaad3940d02e792969bec8a734c413621e7305148654cbca30b2fc` and
`6e8909748b3e20c176772866ab89c4f374400f17dec5fc2df9ad8b720e12ff2f`.
The regression fixture SHA-256 is
`e0a3b0c3e007ad70303043a2791e559f1a4befc9f2008cd71d5f00811051fe3b`.

#### Probe release

The owner authorized one paid probe on 2026-11-25. The released window is
**Wednesday 2026-11-25, 18:10 inclusive to 23:50 exclusive Beijing (+08:00)**.
The operator script uses the confirming inputs at checkpoints 271 and 386
of the tick-442 capture in read-only mode. It makes one selection and one
dependent change-set attempt per period. It starts each period from that
period's own original base and commits only to a scratch store. The
historical capture and its inspection export remain intact.

**Pass rule.** All four calls must parse on their sole attempt and settle
inside the release terms. Each change set must commit at least one actual
record edit and drop at most one third of its proposed operations
(`3 × dropped ≤ proposed`). The result records every verdict, its
dependency IDs and the committed revisions. A selection failure leaves
that period's change set unsent. There are no retries or fallbacks.

The original four requests would reserve CNY 0.575967 at the off-peak
tariff and 8,000 output tokens per attempt. With the owner's approval, the
probe uses the existing guard's omission order to drop only optional context
from the two real frozen periods. Each selection has a 36,000 counted input
limit. The dependent change set uses the surviving frozen context, with up
to 50,000 counted inputs for its expanded schema and selected records.
The complete index, mandatory record revisions and personality remain
protected where required. The preflight records every omitted reference;
the paid audit records the final omissions after each fresh selection.

| Frozen period | Selection preflight | Change-set preflight using the recorded selection |
| --- | --- | --- |
| `p:ella:1` at 270 | 35,811 sent, 8,039 protected floor. Omitted day entries `d:p:ella:1:1`–`d:p:ella:1:430`. | 49,412 sent, 20,916 protected floor on the reused context. Omitted the same day entries and selected record `m:ella:183`. |
| `p:ella:2` at 385 | 35,731 sent, 10,904 protected floor. Omitted day entries `d:p:ella:2:1`–`d:p:ella:2:81`. | 49,324 sent, 23,781 protected floor on the reused context. Omitted the same day entries and selected record `m:ella:247`. |

DeepSeek V4.1 Flash 1017 is pinned through the DL-06 Responses settings and
counter. Each attempt reserves 8,000 output tokens and assumes zero cache
hits. CNY 0.068 per selection and CNY 0.082 per change set reserve exactly
**CNY 0.30** at **0.02 / 1 / 4** CNY per million cache-hit, cache-miss and
output tokens. The same bounds would reserve CNY 0.60 at peak rates.
The reconciled prior phase ledger records **CNY 4.13287158 settled** and
the original **CNY 0.133982 hold** (CNY 15.73314642 remaining). The new
tariff applies only to the probe slice. Before each audit claim the runner
checks the window and counted bound, plus settled probe spend, any open
holds and the candidate charge against the probe and phase caps. It checks
the window again immediately before HTTPS.
[DL-06 pricing and wire evidence](M14-provider-check.md#owner-release-on-2026-11-24)

| Input in `runs/m14-ev06-consolidation-probe-inputs/` | SHA-256 or commit |
| --- | --- |
| Implementation | `9918ae9a7e21621cbed7da20e27c596d548aa123` |
| `probe.py` | `1f6a497639830b81710b3faa66c888aa5a7f4b49727f6c24f2e6184e4fe40a10` |
| `preflight.json` | `586be762b7160bbfe0d9fecdb0e32e208cdb52493cdc88d8873e4c584fa2c0a9` |
| `ledger.json` | `6454d21ecbe0f340ee8c2aad4bf8b7b855fc1b1d202601874cea9ceb1f56cb08` |
| `release.json` | `cbfaada894986c529c9fc1018c9b05a46a5c9a568578b2b5134e5146fcafdc92` |

The released inputs passed the offline fake-transport run with four
claims and four terminals. Its one proposed operation per period
committed scratch record `m:ella:185` and `m:ella:249`, respectively,
with zero drops. The offline result in
`C:/Temp/li-ev06-mf-probe-403b7769fa83/result.json` has SHA-256
`964c0811a019cea1acdc858e4b7e5ee491ace88e7e7d42babaaca6c769f83385`.

#### Owner command

Run from the EV-06 worktree during the window. The exclusive output directory
`runs/m14-ev06-consolidation-probe/` will contain the durable provider audit,
probe-only ledger and `result.json`.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06' -ErrorAction Stop
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06'
$ev06Start = [DateTimeOffset]::Parse('2026-11-25T18:10:00+08:00')
$ev06End = [DateTimeOffset]::Parse('2026-11-25T23:50:00+08:00')
$ev06Now = [DateTimeOffset]::UtcNow
if ($ev06Now -lt $ev06Start -or $ev06Now -ge $ev06End) {
    throw 'Outside the signed EV-06 consolidation probe window.'
}
$ev06Inputs = 'runs/m14-ev06-consolidation-probe-inputs'
$ev06ScriptHash = (Get-FileHash -LiteralPath "$ev06Inputs/probe.py" -ErrorAction Stop).Hash
$ev06ReleaseHash = (Get-FileHash -LiteralPath "$ev06Inputs/release.json" -ErrorAction Stop).Hash
if ($ev06ScriptHash -ine '1f6a497639830b81710b3faa66c888aa5a7f4b49727f6c24f2e6184e4fe40a10' -or
    $ev06ReleaseHash -ine 'cbfaada894986c529c9fc1018c9b05a46a5c9a568578b2b5134e5146fcafdc92') {
    throw 'EV-06 consolidation probe script or release differs from the verified input.'
}
try {
    $ev06Pattern = '^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(?:"(?<key>[^"]+)"|''(?<key>[^'']+)''|(?<key>[^#\s]+))(?:\s*#.*)?\s*$'
    $ev06KeyLine = Select-String -LiteralPath 'E:\桌面\Living_World\.env' `
        -Pattern $ev06Pattern -ErrorAction Stop | Select-Object -Last 1
    if ($null -eq $ev06KeyLine) { throw 'DEEPSEEK_API_KEY is missing or invalid.' }
    $env:DEEPSEEK_API_KEY = $ev06KeyLine.Matches[0].Groups['key'].Value

    uv run --offline --locked --no-env-file --no-sync --directory backend `
        python "../$ev06Inputs/probe.py" --live `
        --release "../$ev06Inputs/release.json" `
        --ledger "../$ev06Inputs/ledger.json"
    if ($LASTEXITCODE -ne 0) { throw "EV-06 consolidation probe exited with code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
    Remove-Variable -Name ev06KeyLine -ErrorAction SilentlyContinue
}
```

### First consolidation probe result

The owner's off-peak probe dispatched four calls with four metered
terminals. It settled **CNY 0.05631456**. Period `p:ella:1` committed
one gather skill, `m:ella:185`, with content SHA-256
`e199a79ff52da95665fcce26604a3b540087d4c4ad5c8f7391ee52d59ee1e3e9`.
It dropped five of six proposed operations. Period `p:ella:2` dropped
all ten operations and committed no edit. The probe failed its pass rule.
The phase now settles CNY 4.18918614 with the original CNY 0.133982 hold
and CNY 15.67683186 headroom. [Phase ledger](P3.5-spend-ledger.md#opening-ledger)

Offline staging reproduced all 16 verdicts and the skill write from the
parsed responses, frozen stores and sent allowlists. The decisive reasons
below use the validator's recorded precedence.

| Period | Operation | Verdict | Exact check |
| --- | --- | --- | --- |
| `p:ella:1` | `op1`, `op2`, `op4`, `op6` | `format` | Episodic additions omitted `about_tick`. |
| `p:ella:1` | `op3` | `depends_on` | Its inferred source referenced `new:1` and `new:2` from dropped `op1` and `op2`. |
| `p:ella:1` | `op5` | Committed | `d:p:ella:1:446` and `d:p:ella:1:503` both witnessed `verb:gather`. The write created `m:ella:185`. |
| `p:ella:2` | `add_1`–`add_4` | `format` | Episodic additions omitted `about_tick`. |
| `p:ella:2` | `add_5` | `provenance` | `d:p:ella:2:116` witnessed `verb:drink` and `phenomenon:drinks`. The belief's subject key was `place:38,30`. |
| `p:ella:2` | `add_6` | `provenance` | The general belief had no subject keys. Its observed citations `d:p:ella:2:150` and `d:p:ella:2:116` could match none. |
| `p:ella:2` | `add_7` | `depends_on` | Its inferred source referenced `new:3` from dropped `add_3`. |
| `p:ella:2` | `add_8` | `provenance` | `d:p:ella:2:155` and `d:p:ella:2:151` carry `need:stamina`. The sleep skill's only key was `verb:sleep`. |
| `p:ella:2` | `update_1` | `authority` | The update to Mia's social record `m:ella:2` supplied `add_sources`, a field social updates cannot write. |
| `p:ella:2` | `update_2` | `authority` | The update to Ryan's social record `m:ella:3` supplied `add_sources`, a field social updates cannot write. |

The missing dates masked other evidence errors. In the first period,
`op1`, `op4` and `op6` used sleep, drink, rest or need entries
without the claimed place key. `op2` used a gather failure keyed only
to `verb:gather` and an own-response entry ineligible as an observed
source. In the second period, `add_1` had a matching move entry and also
cited an unkeyed sleep entry. `add_2` used own utterance feedback.
The gather entries in `add_3` and the drink/rest entries in `add_4`
also lacked the proposed places. Those are existing evidence rules.

| Artifact under `runs/m14-ev06-consolidation-probe/` | SHA-256 |
| --- | --- |
| `result.json` | `3de442ea994981798de47731f458b9db8fef130ec704096b84bddab347de79de` |
| `provider-probe.sqlite` | `9e2db87b273f23845efc6e171d83aecdf941409362a0f20fa77022d538caaf63` |
| `ledger-evidence.json` | `4144d64962bac308f03ab179bb46b249731e0ca93860e958bb52d9ec79cf09ac` |
| Period 1 parsed change set | `3af75a7cbfbd16c39dc7c9da65b325419b4fde6b91f1cb01e445548470323173` |
| Period 2 parsed change set | `8fd17a44b600f9254363640e55b083cd489f4c8b6448aba29ed26738afac05eb` |

### Consolidation schema repair

The `consolidation_selection/0.5` and `consolidation_change_set/0.5`
requests show the existing observed witness keys alongside the original
day-log lines. Keys come from the resident's delivered entries and stay
with each line when the guard trims it. The change-set instruction
explains subject overlap, evidence for general beliefs and the social and
skill update field limits. It includes one complete episodic add example.

The sent add schema discriminates the three creatable kinds. Episodic and
dated belief branches require a non-null tick range. Stable beliefs may
omit the tick or use null. Skills exclude the field and code-owned
evidence. The content object is typed for each kind. Merge offers the
episodic and belief branches. The receiver still sends each returned
operation to the existing validator, which assigns individual verdicts.
This repair uses the existing source and authority rules and needs no
spec amendment. [Memory formation §§3.3–3.5](../../spec/memory-formation-v0.1.md#33-call-2-change-set)
· [Memory model §§2–3](../../spec/memory-model-v0.1.md#2-the-record-envelope)

### Second consolidation probe release

**Wednesday 2026-11-25, 22:30 inclusive to 23:50 exclusive Beijing (+08:00).**
The offline preflight was prepared at 22:19 Beijing before the 23:20 cutoff. It uses the
same frozen periods at checkpoints 271 and 386, the same DeepSeek V4.1
Flash 1017 pin and the same one-attempt policy. Each period starts from
its historical base and commits edits to an isolated store. The earlier
probe and the tick-442 capture remain retained evidence.

**Pass rule.** All four calls must parse on their only attempts and
settle within the release. Each change set must commit at least one
actual record edit and drop at most one third of the operations proposed
in that period. The report records each verdict and its dependency IDs.
A failed selection leaves that period's change set unsent.

The same two per-stage bounds apply. Each selection reserves 36,000
counted input tokens and each change set 50,000. Each call allows 8,000
output tokens. At CNY 0.02 / 1 / 4 per million cache-hit, cache-miss and
output tokens with zero assumed hits, the four-attempt reserve is
**CNY 0.30**. The same bounds price at CNY 0.60 peak. The runner verifies
the date, window and tariff before using the release and gates every
claim against both the remaining probe budget and the phase headroom.
The ledger wrapper preserves the historical and first-probe bundles
byte for byte, so each UTC day's calls retain their billed tariff.
[DL-06 dated tariff](M14-provider-check.md#owner-release-on-2026-11-24)

The preflight and the paid report list omitted references. The following
change-set columns use each original capture's recorded selection to
check fit offline. The live change set follows its own new selection.

| Period | Selection sent / floor | Change set sent / floor | Optional context omitted in the preflight |
| --- | ---: | ---: | --- |
| `p:ella:1` at 270 | 35,886 / 8,063 | 49,367 / 28,019 | Selection omits day entries 1–442. The change-set sample omits day entries 1–458 and selected records `m:ella:183` and `m:ella:184`. |
| `p:ella:2` at 385 | 35,801 / 10,928 | 49,984 / 30,884 | Selection omits day entries 1–86. The change-set sample omits day entries 1–102 and selected records `m:ella:247` and `m:ella:248`. |

| Input in `runs/m14-ev06-consolidation-probe2-inputs/` | SHA-256 or commit |
| --- | --- |
| Implementation | `c7454fc130f1eea731ce464e6c6a0f0e64d022a4` |
| `probe.py` | `9682f2bc69fbe81a7a2711d4335c10565114fddc30dc3a53ae13df6e6e3a8900` |
| `preflight.json` | `4d831502ae6ba4895ee83a2555d2cd5f3beffffa8c5046133c3f2c87e2abb979` |
| `ledger.json` | `b9ab9c7aa472febf367f43f493a465b786aa31a543512938da989e45c640f6d2` |
| `release.json` | `3bc0acfa1b078510b8136669058f01c7c19544b2e190d812c5ba8fe08441e233` |

The fake run sent all four requests and committed one episode per
period with zero drops. It used sent witness `d:p:ella:1:517` and
tick range 262–262 for scratch record `m:ella:185`, then
`d:p:ella:2:150` and tick range 384–384 for scratch record `m:ella:249`.
The fresh C:/Temp result has SHA-256
`4b0a8fd4414c7198df81f884b51ed742846cb8b83f9f82a2127c5ef33204046d`.

#### Second probe owner command

Use the block during the released window. Output goes to the exclusive
directory `runs/m14-ev06-consolidation-probe2/`. The probe will record
the observed results and settle any attempted call before reporting
success or failure.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06' -ErrorAction Stop
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06'
$ev06Start = [DateTimeOffset]::Parse('2026-11-25T22:30:00+08:00')
$ev06End = [DateTimeOffset]::Parse('2026-11-25T23:50:00+08:00')
$ev06Now = [DateTimeOffset]::UtcNow
if ($ev06Now -lt $ev06Start -or $ev06Now -ge $ev06End) {
    throw 'Outside the signed second EV-06 consolidation probe window.'
}
$ev06Inputs = 'runs/m14-ev06-consolidation-probe2-inputs'
$ev06ScriptHash = (Get-FileHash -LiteralPath "$ev06Inputs/probe.py" -ErrorAction Stop).Hash
$ev06ReleaseHash = (Get-FileHash -LiteralPath "$ev06Inputs/release.json" -ErrorAction Stop).Hash
if ($ev06ScriptHash -ine '9682f2bc69fbe81a7a2711d4335c10565114fddc30dc3a53ae13df6e6e3a8900' -or
    $ev06ReleaseHash -ine '3bc0acfa1b078510b8136669058f01c7c19544b2e190d812c5ba8fe08441e233') {
    throw 'EV-06 second probe script or release differs from the verified input.'
}
try {
    $ev06Pattern = '^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(?:"(?<key>[^"]+)"|''(?<key>[^'']+)''|(?<key>[^#\s]+))(?:\s*#.*)?\s*$'
    $ev06KeyLine = Select-String -LiteralPath 'E:\桌面\Living_World\.env' `
        -Pattern $ev06Pattern -ErrorAction Stop | Select-Object -Last 1
    if ($null -eq $ev06KeyLine) { throw 'DEEPSEEK_API_KEY is missing or invalid.' }
    $env:DEEPSEEK_API_KEY = $ev06KeyLine.Matches[0].Groups['key'].Value

    uv run --offline --locked --no-env-file --no-sync --directory backend `
        python "../$ev06Inputs/probe.py" --live `
        --release "../$ev06Inputs/release.json" `
        --ledger "../$ev06Inputs/ledger.json"
    if ($LASTEXITCODE -ne 0) { throw "EV-06 second consolidation probe exited with code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
    Remove-Variable -Name ev06KeyLine -ErrorAction SilentlyContinue
}
```

### Second consolidation probe result and owner ruling

The first probe settled CNY 0.05631456 and committed one gather skill.
The second settled **CNY 0.04855008** across four first attempts, each with
a metered terminal. It committed one episode and recorded three
`provenance` drops and zero `format` drops. Period `p:ella:1` committed
zero of one proposed operation. Period `p:ella:2` committed one of
three, so the overall probe failed its original pass rule.
[First consolidation probe result](#first-consolidation-probe-result)

| Period and operation | Verdict | Sent evidence |
| --- | --- | --- |
| `p:ella:1` · `remember_woke_after_sleep` | `provenance` | `d:p:ella:1:528` reads “You fall asleep.” `d:p:ella:1:529` carries `need:stamina`. Neither matches `resident:ella` or `place:38,31`. |
| `p:ella:2` · `remember_ryan_fill` | Committed | `d:p:ella:2:108` and `d:p:ella:2:109` both carry `resident:ryan` and show the start and result of filling his canteen. That participant key binds both citations. |
| `p:ella:2` · `remember_failed_gathers` | `provenance` | `d:p:ella:2:124`, `d:p:ella:2:134`, and `d:p:ella:2:136` each carry `verb:gather`. The episode named no participant or place. |
| `p:ella:2` · `remember_sleep_tired` | `provenance` | `d:p:ella:2:151` carries `need:stamina`. `d:p:ella:2:153` reads “You fall asleep.” Neither supplies the episode's `place:22,13`. |

The second probe's scratch write at tick 420 created `m:ella:249` for
ticks 356–357 with gist “I saw Ryan filling his canteen at the spring
while I was nearby.” Its content hash is
`a3a860405ca12135859184e5f38b8fc158686100aa812df808eb0663236390ce`.
The owner ruled on 2026-11-25 that the provenance rule is working as
specified and closed wording iterations. The second probe remains a
separate evidence capture.

| Artifact under `runs/m14-ev06-consolidation-probe2/` | SHA-256 |
| --- | --- |
| `result.json` | `e06624fbbf3004dbf16afaacce567f5e00d3a60e68fb2d60b028dbeb13c70148` |
| `provider-probe.sqlite` | `ea03876877a8f522b76726c0e8c8c7fb452bb4b777164e3bf42f6f5211cf8bd6` |
| `ledger-evidence.json` | `0afea33aec49a27fa272a19d9efec05724f40db61e562a23bb9d1fd5e8bd6f49` |
| Period 1 parsed change set | `03906f5d37ce2b71e7529839d442cfd412ef14a73072fb7fb57acf973a7aeaad` |
| Period 2 parsed change set | `d5fdec5772640177d0aa69779f998f64caab06bd8f24da4331ee0992f614782d` |

### Fresh 576-tick live release

The owner authorized one fresh 576-tick run after reviewing both probes.
The detached checkout `F:/p35-w1/ev06r3` pins executable
`c7454fc130f1eea731ce464e6c6a0f0e64d022a4` with both consolidation
requests at `0.5`. The pack, vocabulary, setup, seed `20261108`,
resident profiles and rehearsal match the prior four-day preflight. Ella
uses the explorer profile with memory on in `compat-v1`. Ryan and Mia
remain rule-controlled. The run uses the pinned DeepSeek V4.1 Flash 1017
Responses transport and counter.

The release is **Thursday 2026-11-26, 09:10 inclusive to 12:00 exclusive
Beijing (+08:00)**, with the 2026-11-26 UTC peak tariff of **CNY 0.04 /
2 / 8** per million cache-hit input, cache-miss input and output tokens.
The normal preflight and authority loader accepted the release offline at
**23:32:16 Beijing on 2026-11-25**.
[Peak tariff evidence](M14-provider-check.md#owner-release-on-2026-11-24)

| Game day | Rehearsed attempts | Counted input tokens | Output tokens held | Reserve CNY |
| --- | ---: | ---: | ---: | ---: |
| 1 | 47 | 551,104 | 376,000 | 4.110208 |
| 2 | 33 | 375,923 | 264,000 | 2.863846 |
| 3 | 29 | 363,856 | 232,000 | 2.583712 |
| 4 | 36 | 423,035 | 288,000 | 3.150070 |
| **Total** | **145** | **1,713,918** | **1,160,000** | **12.707836** |

The archived EV-05 audit matches every pinned attempt slot and input bound.
Reserve assumes zero cache hits and 8,000 output tokens per attempt.
CNY 4.23773622 is settled and the original unmatched claim still holds
CNY 0.133982. **All four rehearsed days fit** the CNY 15.62828178 headroom,
leaving **CNY 2.92044578** outside the reservation. The runtime guard
prices each proposed attempt, including retries, against the signed
window, the phase cap and the remaining rehearsal reserve before a
dispatch claim. Its published refusal ends the run at the next safe stop.
[Rehearsal artifact](#rehearsed-waking-period-continuity)
· [Reconciled spend](P3.5-spend-ledger.md#opening-ledger)

The new authorization ledger carries both off-peak consolidation probe
settlements as CNY 0.10486464 in its opening reconciliation, with the two
receipt hashes. The prior tick-442 run keeps its itemized facts under
`m14-ev06-ella-tick-442` in this ledger only, so the fresh live run can
claim `m14-ev06-ella`. All earlier captures remain in place.

| Input in `F:/p35-w1/ev06r3/runs/` | SHA-256 |
| --- | --- |
| `m14-ev06-ella-preflight.json` | `7ccf91cdd0f233cd3879aa8bd2a4c64e7865d3a829fbcf3c84f7cf1460bd728a` |
| `m14-ev06-ella-ledger.json` | `119770ac2a4e996d6a527595dcf85dad99770f6d517822fe5113bc1f63ef8610` |
| `m14-ev06-ella-release.json` | `0b6bf568dad1985d82f5616cce5a42f64cb6561cd1b9890470ff7c06212c6ef5` |

#### Fresh live owner command

Run this block in the released window. The one-time output is
`F:/p35-w1/ev06r3/runs/m14-ev06-ella/`.

```powershell
Set-Location -LiteralPath 'F:\p35-w1\ev06r3' -ErrorAction Stop
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'F:/p35-w1/ev06r3'
$ev06Start = [DateTimeOffset]::Parse('2026-11-26T09:10:00+08:00')
$ev06End = [DateTimeOffset]::Parse('2026-11-26T12:00:00+08:00')
$ev06Now = [DateTimeOffset]::UtcNow
if ($ev06Now -lt $ev06Start -or $ev06Now -ge $ev06End) {
    throw 'Outside the signed EV-06 window on 2026-11-26, 09:10–12:00 Beijing.'
}
$ev06ReleaseHash = (Get-FileHash -LiteralPath 'runs/m14-ev06-ella-release.json' -ErrorAction Stop).Hash
if ($ev06ReleaseHash -ine '0b6bf568dad1985d82f5616cce5a42f64cb6561cd1b9890470ff7c06212c6ef5') {
    throw 'EV-06 release differs from the verified authorization.'
}
try {
    $ev06Pattern = '^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=\s*(?:"(?<key>[^"]+)"|''(?<key>[^'']+)''|(?<key>[^#\s]+))(?:\s*#.*)?\s*$'
    $ev06KeyLine = Select-String -LiteralPath 'E:\桌面\Living_World\.env' `
        -Pattern $ev06Pattern -ErrorAction Stop | Select-Object -Last 1
    if ($null -eq $ev06KeyLine) { throw 'DEEPSEEK_API_KEY is missing or invalid.' }
    $env:DEEPSEEK_API_KEY = $ev06KeyLine.Matches[0].Groups['key'].Value

    uv run --offline --locked --no-env-file --no-sync --no-dev --directory backend `
        python -m living_island.sim.v2.harness.live_resident run --live --through 576 `
        --implementation c7454fc130f1eea731ce464e6c6a0f0e64d022a4 `
        --release ../runs/m14-ev06-ella-release.json `
        --ledger ../runs/m14-ev06-ella-ledger.json --out ../runs/m14-ev06-ella
    if ($LASTEXITCODE -ne 0) { throw "EV-06 exited with code $LASTEXITCODE." }
}
finally {
    Remove-Item -LiteralPath 'Env:\DEEPSEEK_API_KEY' -ErrorAction SilentlyContinue
    Remove-Variable -Name ev06KeyLine -ErrorAction SilentlyContinue
}
```
