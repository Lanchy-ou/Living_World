# M13 Gate 3 — The new island

**CT-10 executor status as of 2026-11-25.** The qualified starter pack passed
the held-out balance round. Claude Code published the D1 PASS receipt and
recorded the D4 search. D5 awaits the owner's disposition. CT-10 independent
review, integrated acceptance, and owner signature are pending. [M13 plan](M13-plan.md)

The integration base is `7e8902acac7ef924acf0b8fd5dda5b36fcac213e`.
M12 was signed on 2026-11-23. Its compatibility, synthetic-pack and
extension evidence carries forward, including CT-01–03, CT-14, CT-15, the
compatibility portion of CT-10/11, the canteen portion of CT-16 and CT-17.
[Signed M12 report](M12-equivalence-report.md#owner-review-at-m12-gate-3) ·
[PR-07 #40](https://github.com/Lanchy-ou/Living_World/pull/40) ·
[PR-07 CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45111978749) ·
[M12 sign-off #48](https://github.com/Lanchy-ou/Living_World/pull/48) ·
[Sign-off CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45131868672)

## Qualified candidate and retained artifacts

The owner froze `starter-v1` version 0.1 with `awake_per_tick = 30` at
`27ab740282934d8cb8dddd4d631583f2a60f299e`. Its source tree is
`8991da96e1dbac05fd8284e4c8ccd20b0917714e`. The effective starter hash is
`c193d071e7593185f7641513c7a14e42d9b30eba3ceaf96e1fc563bf85f51fc0`
with base `compat-v1` hash
`2fdf1322b47802166538dc00995b83dcfb9cef0cee692b156bd569f24687eb93`.
The bound rule library is
`1861e489ebb2bf8187533777bb3759898210f5a0669d6ffc8b6327d2ec138f28`.
[Freeze and qualification](M13-balance.md#tuned-development-result-and-candidate-freeze)

Evidence paths below are relative to `F:/p35-w1`. Each locator opens a retained
artifact. The producer handoffs give their reproduction commands and per-case
hashes. Use the listed execution revision to reproduce historical output.

| Producer | Retained locator | SHA-256 |
| --- | --- | --- |
| CT-03 single-seed PR-07 recheck, 1,009 matched boundaries | [`ct03/runs/m13/ct03-pr07-3920f37/cases/acceptance-production-base-2600456787.json`](../../../../ct03/runs/m13/ct03-pr07-3920f37/cases/acceptance-production-base-2600456787.json) | `87e4bc44d7bf409fc2695fee0ba4acbd5f555cc03f748002c81a9555c53feb62` |
| CT-04 interrupted and restored policy case | [`ct04/runs/m13/ct04/a5f1cfd-campaign/cases/1.json`](../../../../ct04/runs/m13/ct04/a5f1cfd-campaign/cases/1.json) | `f2e56dbff29938f3c263236ce163c4313e0b228713ac2f9c4d66050241a0d545` |
| EN-08 20-seed PR-07 rerun | [`en08/runs/m13/en08/acceptance-f8142919376de0ea2125fe3e443629c82dce8166/report.json`](../../../../en08/runs/m13/en08/acceptance-f8142919376de0ea2125fe3e443629c82dce8166/report.json) | `1160bed7a9ee429e22a5c8275c9289e9ebd3a34c832c982d9b9526d9a4d5bb79` |
| EN-10 20-seed PR-07 rerun used by calibration | [`en10/runs/m13/en10/acceptance-3d729bcfe3bd3e2fb3207100f2075830100c3999/report.json`](../../../../en10/runs/m13/en10/acceptance-3d729bcfe3bd3e2fb3207100f2075830100c3999/report.json) | `1160bed7a9ee429e22a5c8275c9289e9ebd3a34c832c982d9b9526d9a4d5bb79` |
| CT-05 refreshed calibration, 59 equal pairs and zero missing | [`ct06/runs/m13/calibration-en10/receipt.json`](../../../../ct06/runs/m13/calibration-en10/receipt.json) | `82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5` |
| CT-06 original development, faint tolerance failed | [`ct06/runs/m13/balance-dev/report.json`](../../../../ct06/runs/m13/balance-dev/report.json) | `4d0fd86835fc945ed984c425d473f36de1094658b128f46baa569fd5dbaa77dc` |
| CT-06 tuned development, all thresholds passed | [`ct06/runs/m13/balance-dev-awake30/report.json`](../../../../ct06/runs/m13/balance-dev-awake30/report.json) | `189a58d11d6d186b0cf39d05070fe830d351063d650448deb3237e0ca5bbe3f0` |
| CT-06 held-out qualification and case index | [`ct06/runs/m13/balance-accept/report.json`](../../../../ct06/runs/m13/balance-accept/report.json) | `37131a9bcec492e2824d77383e740383bce6f5357c3edf562e6b840a1744f7f3` |
| CT-07 continuous crafting and cooperation | [`ct07/runs/m13/craft/index.json`](../../../../ct07/runs/m13/craft/index.json) | `dd4794058c2652248706a5c983dcb6e416303aa8354ec6ad993f56381db92901` |
| CT-08 dynamics, 20 complete receipts | [`ct08/runs/m13/dynamics/report.json`](../../../../ct08/runs/m13/dynamics/report.json) | `03d87e7f2d903fb1c3b5f1c908a409cff11ecfae8223e4f351715ee8d12f18ba` |
| CT-09 scripted conservation | [`ct09/runs/m13/conservation/receipt.json`](../../../../ct09/runs/m13/conservation/receipt.json) | `64d527c1872340e9b71a00bc37cb067f57f2e5aec03b5b69334a56207770e6bf` |
| CT-10 original D1 case receipt | [`ct06/runs/m13/balance-accept/2600456787/starter-v1/cases/1.json`](../../../../ct06/runs/m13/balance-accept/2600456787/starter-v1/cases/1.json) | `66f735dec5f1b22a973711518c960b491d04f868d2a2b8a3bda7c667dc3f7b0c` |
| CT-10 final D1 PASS receipt | [`ct10/runs/m13/long-run/receipt.json`](../../../runs/m13/long-run/receipt.json) | `d4d9e3736dafbce01605f59f13a9ae5a843e9151cc0a0dc144b9b4275d4cf35d` |
| CT-10 final command log | [`ct10/runs/CT-10-evidence.log`](../../../runs/CT-10-evidence.log) | `df6f6bf434a1ba87b1976397926b3e995d716099cadc34d276e3a2c4d54fa734` |

## Mechanics and acceptance map

CT labels in the first column are [starter spec §10 tests](../../spec/starter-content-v0.1.md#10-acceptance-tests).
For craft events, prefix the displayed `tick:ordinal` with
`craft-201486072:`. For dynamics events, prefix it with
`m13-dynamics-<vector>-2600456787:`. The dynamics index maps each vector to
its `evidence.json` where `observer.<excerpt>` gives full event IDs, intent
IDs, actor and watcher deliveries, and relative opening `packets/` and
`turns/` paths.

| Test / mechanic | Card | Witness and locator |
| --- | --- | --- |
| CT-04 composition and admission | CT-03 | Both ancestry hashes above. All §5.10 rows normalize. Inherited wood without replacement, an unbounded flint debit, altered config/map bytes and world `work_ticks` are refused. [Pack tests and refusals](P3.5-CT-03.md#what-changed) |
| CT-05 continuous recipes and work | CT-07 | `index.json:story` links Ella's flake at 12, cord at 40, axe at 57, cut at 61, fire at 79, pot shape at 83, bake at 84, fill and drink at 86–88 and shelter sleep at 120–126. The six benefit rows below give action and event locators. |
| CT-06 deception and action visibility | CT-07 | `vine_comparison`: Ella's `ella:t000025:a` starts visibly at 41 and snaps at 46. Mia's start and settle deliveries carry the apparently strong vine and `snaps`. Events `0000000046:000007`–`000010` consume the cord and record the new head and handle and settlement. Grass shows weak and holds at 57. |
| CT-06 persistent shelter and cooperation | CT-07 | `benefits.cord.shelter`: site `e:8e1883bf552b43ca` has zero work with vine at 104 in Ella's packet. After grass binding, Ella, Mia and Ryan contribute eight units each at 113–120. Event `0000000120:000008` closes the site and `0000000120:000013` produces the shelter. |
| CT-07 conservation | CT-09 | Scripted seed `2195683955`, run `ct09-scripted`, through 1,008. Tick 14 ledger and `turns/13.json` link Mia's pot-shaping output event `ct09-scripted:0000000014:000003`. See ledger totals below. |
| CT-08 deadwood regrowth | CT-08 | `regrowth/regrowth-at-capacity`, tick 72, world events `0000000072:000000`–`000001`. One branch regrows at the 72-tick boundary, capped by stock. |
| CT-08 fire, failed tinder and bake on final fuel | CT-08 | `light-failure/light-failure`, Ada `ada:t000002:a`, tick 4 event `0000000004:000002` consumes only tinder. `light-success/last-fuel-bake`, tick 30 events `0000000030:000004`–`000010` show bake and fire exhaustion. `bake-insert-5/bake` verifies the next check at tick 6. |
| CT-08 fire spill | CT-08 | `spill-admitted/admitted-spill` shows contents released on fuel exhaustion. See CT-19 for the blocked spill and subsequent release. |
| CT-08 fruit age and decay | CT-08 | `fruit-rot/fruit-rot`, Ada's inventory retains four units at 432, world events `0000000432:000002`–`000004`. `fruit-crumble/fruit-crumble` shows an already aged rotten stack removed at tick 2. |
| CT-08 wear and break | CT-08 | `axe-wear/cut-20`, Ada `ada:t000039:a`, tick 60. Events `0000000060:000003` and `0000000060:000007`–`000009` show final wear, break and branch. `failed-cut-no-wear` shows the tick 1 control. |
| CT-09 tiredness, faint and recovery | CT-08 | `fatigue-day/day-end`, Ada reaches 4,480 at tick 96 after 50 utterances and 20 first sightings. `fatigue-faint/fainted-action-stop` stops `ada:t000333:a` at 340, events `0000000340:000002`–`000003`. Ada wakes at 376, event `0000000376:000001`. `fatigue-sleep/night-recovery-and-wake` records 7,200 recovered by tick 48. D5 governs the two changed fixed vectors. |
| CT-10 hunger and thirst wake | CT-08 | The four `wake-{satiety,hydration}-{urgent,critical}` vectors retain Ada's sleep choice `ada:t000000:a`. At the tick 2 critical crossings, events `0000000002:000002`–`000003` stop sleep and wake her. Urgent controls continue sleeping. |
| CT-11 sleep need rates | CT-08 | `asleep-awake-rates/first-sleep-and-awake-control`: Ada sleeps from tick 1 (`ada:t000000:a`, event `0000000001:000002`), losing 15 satiety and 60 hydration per asleep tick. Bea and the first awake interval supply the 25/100 control. |
| CT-12 unchanged geometry and ten deposits | CT-03 | Ella's adjacent looks identify all ten deposits with stock and coordinates. [Placement trace and tests](P3.5-CT-03.md#what-changed) |
| CT-13 qualification | CT-06 | Held-out technical PASS and all five tolerances PASS; see §9 below. |
| CT-16 clay pot fill | CT-07 | `benefits.clay_pot`: Ella fills once at 86, event `0000000086:000004`. `ella:t000049:a` gives `already_full` at 87 in Ella's packet. The pot carries one serving and uses three slots. |
| CT-18 normalized effects and reserve | CT-03 | Explicit and default zero/empty fields give byte-identical opening and identical cut/contribute outputs. Initial reserve admits the exact capacity and refuses one fewer unit. [Normalization and refusal checks](P3.5-CT-03.md#what-changed) |
| CT-19 bake order, spill retry and split age | CT-08 | `bake-insert-6/phase-3-insertion-and-phase-4-bake`: Ada `ada:t000005:a`, insertion `0000000006:000002`, bake output `0000000006:000007`. Tick 7 insertion bakes at 12. `spill-blocked/spill-after-pickups`: Ada and Bea's tick 4 pickups free capacity after ticks 2–3 block; `0000000004:000007` moves the pot once. `fruit-split/fruit-split`: Ada drops before decay; both splits rot at age 432 with independent creation events `0000000002:000006` and `0000000002:000009`. |
| CT-20 calibrated visible feedback | CT-05 | WAP-23 death and stopped-gather fixtures, DL-25/WAP-35 generic rejection, 20 registered production pairs, and restored mid-queue choice. 39 fixtures plus 20 seeds matched. Refresh bound to EN-10 `3d729bcfe3bd3e2fb3207100f2075830100c3999`. [Calibration handoff](P3.5-CT-05.md#what-changed) · [EN-10 checks](https://github.com/Lanchy-ou/Living_World/pull/53/checks) |
| Durable driver and restore | CT-04 | Script restored Ella's rest at tick 1 and continued `ella:t000001`. Policy restored Ryan's gather at tick 3 and next chose `ryan:t000003` at tick 4. CT-04 links the pending packets, journal prefixes, final snapshots and changed-pin refusals. [Restore commands and hashes](P3.5-CT-04.md#commands-and-results) |

### Six §5.9 benefits

All rows use the qualified craft trace `craft-201486072` at
`31be1eb39199b6e6d4becb43727b750d02bd8f8f`. Open `index.json:benefits`
for the matching actor packet, and `packets/<tick>.json` for watcher and
actor deliveries. The final pending delivery for tick 126 is in the closing
checkpoint.

| Benefit | Visible outcome and witness |
| --- | --- |
| Sharp flake | Ella knaps two flakes from one nodule at 12 (`ella:t000006:a`, `0000000012:000007`) and uses the head in the axe at 57 (`ella:t000028:a`, `0000000057:000008`). |
| Cord | Ella's vine binding snaps at 46 and grass holds at 57, with Mia's start and settle observations. The grass binding also lets the three residents finish the shelter at 120. See CT-06 above. |
| Stone axe | On `deadwood_01`, hand gathering yields one branch in three ticks (16–19, `ella:t000011:a`, `0000000019:000008`). Cutting yields two in two (59–61, `ella:t000031:a`, `0000000061:000002`). |
| Campfire | Ella lights it at 79 (`ella:t000044:a`, `0000000079:000005`). It burns through 96 and checks at six-tick intervals. Pot insertion and bake at 84 are events `0000000084:000003` and `0000000084:000007`. |
| Clay pot | Ella carries one extra serving, fills at 86, encounters full at 87 and drinks at 88 (`ella:t000050:a`, `0000000088:000005`). Ryan's canteen holds two throughout. |
| Shelter | Ella sleeps at the constructed site at ticks 120–126 (`ella:t000069:a`, `0000000126:000005`). Gain is +220 stamina per tick, matching Mia's cave control and above Ryan's +180 ordinary sleep. |

## §9 qualification and CT-D9

The original development report recorded 112 faints in 60 treatment
resident-weeks and failed the faint tolerance. The tuned development round
passed with 50/60 and the owner froze the candidate before the held-out run.
The held-out report contains all 40 fresh case receipts, 20 per arm, 420
resident-days and 60,480 living resident-ticks per arm. The per-resident
access labels all read `not_found` despite all residents recording spring
drinks. §9.2 uses first recorded spring drink. [Qualification history,
tolerances, and per-seed case hashes](M13-balance.md)

| Held-out metric | Compat | Starter |
| --- | ---: | ---: |
| All-alive cases | 20/20 | 20/20 |
| Deprived ticks / residents | 69/60 (1.15 mean) | 0/60 |
| Median first spring drink, all 60 residents | 48 ticks | 48 ticks |
| Faints / resident-weeks | 0/60 | 51/60 (0.85) |
| Deaths / distinct causes | 0 / 0 | 0 / 0 |
| Dedicated water trips | 122 | 83 |
| Awake / asleep / unconscious ticks | 45,145 / 15,335 / 0 | 42,391 / 16,268 / 1,821 |
| Non-survival / living awake ticks | 24,650/45,145 (54.60%) | 22,571/42,391 (53.24%) |

The starter result is above the 30% CT-D9 signal. Daily classifications and
denominators are in the per-case rows. M15 owns live-resident benefit and
spare-time measurement under D6. [§9.4](../../spec/starter-content-v0.1.md#94-spare-time)

## Scripted conservation

Claude Code's recorded run at `a79a93666a831697aa5d7181474157eb009fd41b`
completed with **PASS** and zero first divergence across 3,024 class/tick
balances. Ledger SHA-256
`56b9040a641252b48356576548aedd372f468dbd92ebff0959db794fcd321c34`.
[Ledger and artifact audit](P3.5-CT-09.md#final-scripted-week-evidence--2026-11-25)

| Matter | Opening | Source creation | Net destruction | Expected and observed closing |
| --- | ---: | ---: | ---: | ---: |
| Mineral | 85 | 0 | 0 | 85 |
| Plant | 66 | 27 | 3 | 90 |
| Water | 2 | 17 | 17 | 2 |

Fruit regrowth supplies 27, eating consumes 1, and crumbling removes 2.
Spring draws and drinking each account for 17 water units. Pot shaping
reclassifies 10 mineral units and rot reclassifies 2 plant units within
their classes. The ordered ledger retains all 67 matter entries and 31
transfers. [Ledger](../../../../ct09/runs/m13/conservation/ledger.jsonl) ·
[Tick 14](../../../../ct09/runs/m13/conservation/ledger/14.json)

## D1 speed and EN-08 comparison

**D1 PASS from retained CT-06 timing.** The predeclared treatment seed
`2600456787` reached **1,008 committed ticks in 356.9508094 seconds**
(2.823919 ticks/second), against 1,800 seconds. Ella, Mia and Ryan ran
`rule-based-v0/base/visible` on default S2 m6 using ordinary durable packet
and turn journaling and checkpoints every 24 ticks. Zero provider calls,
one attempt, zero excluded downtime and zero unclassified time. The run
used two round workers on LAPTOP-PN3UMDQD, Intel Core i7-12700H (CPU record
Family 6 Model 154 Stepping 3), Windows 11 build 22000, on 2026-11-24.

| D1 identity | Pin |
| --- | --- |
| Run / case / source | `default_island_seed20261108_run01`, case 1, source `bacb78e48139be9d9922df4da9d1817badbf7dc5` |
| CT-04 runtime Git blob | `79d4d643f214642f31051d8d8666903e3014d17a` |
| Registration SHA-256 | `82539ac087302405eb35e8d1c421e531d3e211a367084b2493ef0a74e23c6986` |
| Raw config SHA-256 | `15c576c98be29ac1054e1154376508b6479e4fb57ebf1f07d241905f433dc128` |
| Effective config SHA-256 | `5ff45da2198092f5041cff79a9825d675f5fe463142399721c64a194c7de5480` |
| Map SHA-256 | `007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c` |
| Vocabulary SHA-256 | `57554435492d6f3db83006a4510b292f8b0d1ebc70c3393663fd1a9ad94cf286` |
| Evidence SHA-256 | `7d24edcea48dd7ed0b5dc69c388c7936d872e2c7f614214e092b92852279cf52` |
| Closing checkpoint `checkpoints/1-1008.json` | `937d5e68d214684f0a199f2bae2c1c58148daf15c0c88204016286b348151168` |
| Packet/turn prefix SHA-256 | `3cb27f0950ff4126ca4e7b49d14a55d15ab379c3918d023c64e746a1f37d553e` |
| `progress.sqlite` SHA-256 | `d8d6b73931f46ee4b975f1cd8dbfc3902bb2ee1068f3dbdde4429b39bd796706` |

The CT-10 executor's read-only check recomputed the archived inputs,
checkpoint and packet/turn chain and confirmed the database matches the
report. It used zero extra simulations. Independent verification took 13.017
seconds in the first invocation, recorded outside the D1 stopwatch.
Claude Code ran the final command once under the host lock on
`09e305697907e1be367c3c531f0dce116d1ff69f`. It exited 0 in about 2 seconds,
reused the CT-06 timing, and published the same receipt SHA-256
`d4d9e3736dafbce01605f59f13a9ae5a843e9151cc0a0dc144b9b4275d4cf35d`.
The executor verified the final digest and the log's `D1 PASS` line.
[Final receipt](../../../runs/m13/long-run/receipt.json) ·
[Execution log](../../../runs/CT-10-evidence.log) ·
[Original timing ledger](../../../../ct06/runs/m13/balance-accept/2600456787/starter-v1/progress.sqlite)

EN-08 measured one worker and 121 identical compatibility advances on this
host. Baseline `04b9c012c89c1e05b985f85c2ffba312a695a05e` took
24.748 seconds (204.53 ms/tick). Optimized
`f8142919376de0ea2125fe3e443629c82dce8166` took 18.607 seconds
(153.78 ms/tick), a 24.8% reduction. The matching reports and packet
digests, detached-delivery assertions and retained profile
`runs/m12-pr07-prefix-profile.dat` are indexed in EN-08's handoff.
The optimized PR-07 rerun matched 20/20 acceptance trajectories through
1,009 boundaries with zero differences. The EN-10 comparison later used
for calibration matched the same 20 trajectories and aggregate digest.
[Timing and isolation](P3.5-EN-08.md#timing-and-d1-handoff) ·
[EN-08 rerun](P3.5-EN-08.md#acceptance-campaign) ·
[EN-10 handoff](P3.5-EN-10.md#handoff)

## Reopen evidence and review record

For any locator above, read the retained bytes and compare their SHA-256
with the listed digest. The following opens the CT-07 witness index. The
same commands apply to the other retained locators.

```powershell
$artifact = 'F:/p35-w1/ct07/runs/m13/craft/index.json'
Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
Get-Content -Raw -LiteralPath $artifact | ConvertFrom-Json
```

Claude Code's final D1 evidence command from the CT-10 checkout is

```powershell
uv run --directory F:/p35-w1/ct10/backend --locked --offline python -m living_island.sim.v2.scenarios.long_run --balance F:/p35-w1/ct06/runs/m13/balance-accept --out F:/p35-w1/ct10/runs/m13/long-run
```

The command published `ct10/runs/m13/long-run/receipt.json`. Add
`--verify-only` and give it a separate output directory to verify the
source with simulation disabled.

All linked CI runs completed successfully for their listed PR head, with
backend, frontend and contract jobs green.

| Card | Gate 1 and runtime evidence | Claude Code Gate 2 | PR head and CI |
| --- | --- | --- | --- |
| EN-08 | Four static checks, 459 scoped tests and 20/20 acceptance trajectories. [Handoff](P3.5-EN-08.md#required-fields) | Accepted. [#34](https://github.com/Lanchy-ou/Living_World/pull/34#issuecomment-7094223441) | `2daf2f5` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45125685422) |
| CT-03 | Four static checks, 133 focused passes and PR-07 single-seed repeat. [Handoff](P3.5-CT-03.md#required-fields) | Recheck accepted, conditional on green CI. [#35](https://github.com/Lanchy-ou/Living_World/pull/35#issuecomment-7092441987) | `0f4606b` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45117849711) |
| CT-04 | Four static checks and 12 focused passes. [Handoff](P3.5-CT-04.md#required-fields) | Accepted, conditional on green CI. [#36](https://github.com/Lanchy-ou/Living_World/pull/36#issuecomment-7092431643) | `7a766b5` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45117719192) |
| CT-05 | Four static checks, 26 focused passes and 59/59 equal pairs. [Handoff](P3.5-CT-05.md#required-fields) | Accepted. [#47](https://github.com/Lanchy-ou/Living_World/pull/47#issuecomment-7104084780) | `1fb1484` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45191778337) |
| CT-06 | Four static checks, 42 post-rebase focused passes and 40/40 intact acceptance cases. [Handoff](P3.5-CT-06.md#final-required-fields) | PASS. [#57](https://github.com/Lanchy-ou/Living_World/pull/57#issuecomment-7135912443) | `a08bf32` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45424665743) |
| CT-07 | Four static checks, six scoped passes, Claude Code's final command exit 0. [Handoff](P3.5-CT-07.md#final-qualified-evidence--2026-11-25) | Phase 1 review found no blockers. [#60](https://github.com/Lanchy-ou/Living_World/pull/60#issuecomment-7119964426) | `83e7bcf` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45506672001) |
| CT-08 | Four static checks and five scoped passes after rebase. Claude Code's final command exited 1 for the two D5 vectors. Receipt audit exited 0. [Handoff](P3.5-CT-08.md#final-evidence) | Phase 1 finding fixed in the handoff. [#59](https://github.com/Lanchy-ou/Living_World/pull/59#issuecomment-7119889117) | `d811b80` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45507155855) |
| CT-09 | Four static checks, five scoped passes, Claude Code's scripted PASS and receipt audit exit 0. [Handoff](P3.5-CT-09.md#final-required-fields) | Phase 1 review found no blockers. [#58](https://github.com/Lanchy-ou/Living_World/pull/58#issuecomment-7119869038) | `a269eec` [CI](https://github.com/Lanchy-ou/Living_World/actions/runs/45506816766) |
| CT-10 | Four static checks and five scoped passes rerun on evidence head `09e3056`. Claude Code's final D1 command exited 0 and published PASS. [Handoff](P3.5-CT-10.md#handoff) | Claude Code's independent review and integrated acceptance verdict are pending. | PR and CI pending publication. [CI workflow](../../../.github/workflows/ci.yml) |

## Owner dispositions

| Item | Status |
| --- | --- |
| D5 / OQ-P3.5-M13-1 | **Pending owner disposition.** The published awake gain 50 becomes 30. Typical CT-09 day fatigue changes **6,400 → 4,480** and silent awake ticks from zero to faint change **200 → 334**. The 36-tick faint and 7,200-point recovery in 48 asleep ticks remain recorded in both vectors. Retain both published expectations and qualified observations. [D5](M13-plan.md#1-owner-decisions) · [CT-08 comparison](P3.5-CT-08.md#phase-2-qualified-pack-and-d5) |
| D3 / P3-PERF-U1 | Dropped for P3.5. EN-07 replaced the targeted store. Preserve parked branch `task/P3-PERF-U1-validation-cache` and candidate `124e751`. [Owner decision](M13-plan.md#1-owner-decisions) |
| D4 / original M9 artifacts | **Recorded independently of M13 acceptance.** Claude Code's single read-only search confirmed receipt folders for four M9 runs, 130 files with sorted listing SHA-256 `7ffcc5e9505c0fcb02f9201e998ff671fc14e1237a005eaf5ccf13d8e136c158`. The original run trees are lost across the accessible locations. Thirteen retained folders were access-denied and remain unresolved. [Search record](M13-m9-search.md) · [PR #67, `916fdf9`](https://github.com/Lanchy-ou/Living_World/pull/67) |
| D6 / live measurements | M15 owns live benefit and time-use measurements on the starter pack. [M13 handoff](M13-plan.md#1-owner-decisions) |
| Historical P3 V-04 | Stopped at committed tick 132. [P3 closeout](../p3/P3-closeout.md#owner-disposition-and-deferred-work) |

Owner signature ____________________  Date ____________________
