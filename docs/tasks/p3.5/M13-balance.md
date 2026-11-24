# M13 starter balance qualification

## Qualification status

| Stage | Registered pairs | Result | Evidence |
|---|---:|---|---|
| Development | 20 | Technical PASS, verdict FAIL | 112 treatment faints in 60 resident-weeks. See [development evidence](#development-evidence). |
| Tuned development | 20 | Technical PASS, verdict PASS | All five thresholds passed. See [measured results and frozen candidate](#tuned-development-result-and-candidate-freeze). |
| Held-out acceptance | 20 | Technical PASS, verdict PASS | All five thresholds passed. See [held-out evidence and receipts](#held-out-acceptance-evidence). |
| D1 and CT-D9 | — | Within budget, above 30% | D1 took 356.951 s. Treatment spent 22,571 of 42,391 awake ticks on non-survival actions (53.24%). |

D2 selects the S2 m6 production geometry, the P2 base policy in stand-alone visible-feedback mode, three residents and 1,008 advances. Both arms journal ordinary packet batches and committed turns and checkpoint every 24 ticks. The comparison changes the loaded pack from `compat-v1` to `starter-v1`. CT-03's initial starter source tree at dispatch is `d7ef990e5ab85992aa342bd27f64bc70d5a217a9`. Its bound pack and rule library hashes are captured separately in each case. Each balance invocation takes the accepted equivalence commit via `--equivalence-revision`. `require_calibration` checks that revision, the CT-05 receipt digest, the executable pins and full case coverage. EN-10 added `action_observed`. The owner selected its accepted 20/20 evidence at `3d729bcfe3bd3e2fb3207100f2075830100c3999` for fresh calibration. D1 preselects treatment seed 2600456787 with a 30-minute cumulative active-time budget. [Decisions D1–D6](M13-plan.md) · [CT-03 content pins](P3.5-CT-03.md) · [P2 S2 reference evidence](../p2/P2-05.md)

## Running a round

From the repository root, set `$ct05Dir` to the absolute directory containing the EN-10 calibration receipt, `$ct05Sha` to its SHA-256 and `$equivalenceRevision` to the accepted equivalence commit above. On Windows the entry point takes `C:\Temp\li-heavy.lock` exclusively and exits immediately if the host is occupied. One parent owns the lock through completion of all workers and report publication. Each worker owns a separate case directory.

The recovery wrapper uses two workers for both stages and writes `runs/m13/calibration-en10/receipt.json`. The detached calibration checkout at `90caa0a` matches the original CT-04 arm scopes. An equal receipt with zero missing cases authorizes development. The wrapper owns one lock across both steps. The owner reviews both reports before any held-out work.

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance.development --jobs 2 --calibration-checkout F:/p35-w1/ct06-pin --en08 F:/p35-w1/en10/runs/m13/en10/acceptance-3d729bcfe3bd3e2fb3207100f2075830100c3999
```

To resume development separately with the same verified calibration:

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage development --calibration $ct05Dir --receipt-sha256 $ct05Sha --equivalence-revision $equivalenceRevision --jobs 2 --out ../runs/m13/balance-dev
```

Record the development report digest, reviewed candidate tree and pack version here before starting held-out acceptance on that candidate. If development needs tuning, retain the round, obtain a CT-03 allocation and repeat development in a fresh directory. Pass `--reuse <absolute-prior-round-directory>` to admit verified cases with identical inputs. A changed starter pin requires fresh treatment cases. If any held-out result informs tuning, retain its report and arrange registration and admission of a disjoint replacement list before further acceptance work.

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage acceptance --calibration $ct05Dir --receipt-sha256 $ct05Sha --equivalence-revision $equivalenceRevision --jobs 2 --out ../runs/m13/balance-accept
```

For a restart, use the original command and directory. For a receipt-only rebuild, append `--report-only` to that command. For example, after the initial held-out round:

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage acceptance --calibration $ct05Dir --receipt-sha256 $ct05Sha --equivalence-revision $equivalenceRevision --jobs 2 --out ../runs/m13/balance-accept --report-only
```

The initial 40-case development round took 109 minutes at two workers from round registration to report publication. The rerun estimates below use its recorded case times.

## Reading the report

- `round.json` and `scope.json` record the registration, calibration digest, candidate, executable pins and host settings. `report.json` joins the complete seed list. `reports/` retains published summaries and `failures/` retains failed case inspections or attempts. Interrupted runs also retain per-attempt timing in SQLite.
- `cases["<seed>/<arm>"]` identifies the verified CT-04 evidence, receipt digest, content ancestry, checkpoint schedule, complete timing history and P2 resident and run metrics. `days` gives each resident's seven rows, using opening-tick day membership. Sleep and unconsciousness have separate totals. An awake interval has one paid attempt, including failed starts. A move inherits survival only from its immediate next start with matching destination and reach. Zero living awake intervals yield a null fraction.
- `arms` gives the valid case and resident counts, spring drinkers and never-drinkers, deaths, water trips, mean deprivation, median spring-drink tick and faints. Counts of deprivation include the closing needs of the final interval if the resident was alive at its opening. Each never-drinker contributes 1009 to the 60-resident median. `paired` and `access_by_resident` supply paired differences and the control-to-treatment access transitions.
- `technical` requires 40 matched valid cases. `thresholds` applies starter §9.2 with inclusive limits. `verdict` records the result for the named list. Qualification uses the frozen candidate's held-out result. The separate `ct_d9_at_least_30_percent` field compares pooled treatment non-survival ticks to living awake ticks for owner review. M15 owns the live-resident measurement.
- For CT-10, follow `d1_case` to the preselected held-out treatment row, then open its case receipt, evidence and timing database. `timing.active_ns` sums measured attempts through durable evidence publication. Timing also records downtime, unclassified gaps, throughput and the D1 budget verdict.

## Development evidence

The two-worker wrapper finished at 14:47 SGT on 2026-11-24. EN-10 recalibration returned `equal` with zero missing cases. The paired development round completed all 40 cases on reviewed head `9d781e051b0ca7bee792a826fb79cb00d076d42e`, using the initial CT-03 starter candidate above (bound pack SHA-256 `666a67f3bbd8dae11d7d8c671598d614ba61b99a9e49f73dd62809bb9d5a109e`).

| Retained artifact | SHA-256 |
|---|---|
| [Calibration receipt](../../../runs/m13/calibration-en10/receipt.json) | `82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5` |
| [Development report](../../../runs/m13/balance-dev/report.json) | `4d0fd86835fc945ed984c425d473f36de1094658b128f46baa569fd5dbaa77dc` |

| §9.2 metric | compat-v1 | starter-v1 | Development result |
|---|---:|---:|---|
| All-alive cases | 20/20 | 20/20 | PASS, at least 19 required |
| Mean deprived ticks per resident | 0 | 0 | PASS, at most 24 |
| Median first spring drink, ticks | 48 | 48 | PASS, within 12 ticks. All 60 residents drank in each arm. |
| Faints per resident-week | 0/60 | 112/60 = 1.87 | FAIL, at most 1.00 |
| New death causes | 0 deaths | 0 deaths | PASS |

The treatment counted 3,623 unconscious resident-ticks, the control zero. The separate CT-D9 non-survival fractions were 53.86% for treatment and 54.94% for control.

### Who fainted and when

All 20 starter seeds had faints. Each entry below is the day of one faint in that resident's seven-day case (144 ticks per day). Across 60 residents, 58 fainted. Days 1–4 had zero events, day 5 had seven (all Ryan), day 6 had 49 and day 7 had 56.

| Seed | Ella | Mia | Ryan |
|---:|---|---|---|
| 201486072 | 6, 7 | 7 | 5, 6, 7 |
| 404876745 | 7 | 6, 7 | 6, 7 |
| 497199041 | 6, 7 | 7 | 5, 6, 7 |
| 937154673 | 7 | 6 | 6, 7 |
| 1011827743 | 6, 7 | 6, 7 | 6, 7 |
| 1021125776 | 7 | 6, 7 | 5, 6, 7 |
| 1263016932 | 6, 7 | 6, 7 | 6, 7 |
| 1334592829 | 6, 7 | 6, 7 | 5, 6, 7 |
| 1452436788 | 6, 7 | 6, 7 | 6, 7 |
| 1883209505 | 6, 7 | 6, 7 | 5, 6, 7 |
| 2104929825 | 6 | 6, 7 | 6, 7 |
| 2144999532 | 6, 7 | 7 | 6, 7 |
| 2195683955 | None | 6, 7 | 6, 7 |
| 2344699806 | 6, 7 | None | 6, 7 |
| 2507182619 | 6, 7 | 7 | 5, 6, 7 |
| 2520148199 | 6, 7 | 6, 7 | 6, 7 |
| 3459030352 | 6, 7 | 6, 7 | 5, 6, 7 |
| 3695162045 | 6, 7 | 6, 7 | 7 |
| 3698676642 | 6, 7 | 6, 7 | 6, 7 |
| 3976177611 | 6, 7 | 7 | 6, 7 |
| **Faints** | **34** | **32** | **46** |
| **Seeds with a faint** | **19/20** | **19/20** | **20/20** |

### Why faints accumulated

The visible-feedback rule policy selects sleep at low physical stamina. Its fallback selects rest or wait, and its projected perception omits mental fatigue. Rest restores stamina while mental fatigue keeps increasing. Voluntary sleep starts by day were 60, 120, 60, 59, 48, 2 and 2. On days 6 and 7, residents spent 4,612 and 4,427 awake ticks respectively resting or waiting. Of the 112 faints, 59 occurred during rest and 32 during wait. Ryan accumulated the least voluntary sleep over the 20 weeks, with 4,790 ticks against Ella's 5,904 and Mia's 6,083. [Rule policy R7 and R12](../../../backend/src/living_island/agents/rule_based/policy.py) · [Perception projection](../../../backend/src/living_island/sim/v2/compat/adapters.py)

Of 351 voluntary sleeps, 345 completed all 48 ticks. The six early wakes occurred after 35–40 ticks as hydration crossed the critical threshold of 1,999. Of the 112 uninterrupted waking spells ending in a faint, 53 followed a full sleep, five an early wake and 54 an earlier faint. The spells lasted 107–200 awake ticks (median 198). Across their 17,379 awake ticks, the packets contributed zero heard utterances and 130 first sightings. Before clamping, the base awake rate accounted for 868,950 fatigue points and first sightings for 3,900. A complete 36-tick faint clears 5,400 points, leaving 4,600. Another 108 quiet awake ticks can therefore trigger a second faint.

| Resident and event | Evidence from the waking spell |
|---|---|
| Ryan, seed 1021125776, day 5, tick 615. `default_island_seed20261108_run01:0000000615:000007` | Sleep ended at tick 416 with zero fatigue. Over the next 199 awake ticks, Ryan spent 90 resting and 30 waiting. Two first sightings and zero heard utterances brought the total to 10,010 before clamping. The final wait took fatigue from 9,960 to 10,000 with stamina at 8,220. [Observation 614](../../../runs/m13/balance-dev/1021125776/starter-v1/observations/614.json) |
| Ella, seed 1011827743, day 7, tick 983. `default_island_seed20261108_run01:0000000983:000006` | Ella fainted at tick 839 and recovered to 4,600 at tick 875. The next 108 awake ticks included 54 resting and 33 waiting, with zero sightings or heard utterances. The last wait took fatigue from 9,950 to 10,000 with stamina at 8,120. [Observation 982](../../../runs/m13/balance-dev/1011827743/starter-v1/observations/982.json) |

### Tuning proposal for owner decision

**Change only `awake_per_tick` from 50 to 34 (−32%).** Applying the fatigue arithmetic to the recorded schedules gives **55 faints in 60 resident-weeks (0.92)**, five below the §9.2 ceiling. This is the smallest integer reduction of this coefficient that crosses the threshold on these traces. A value of 35 yields 69 faints and all settings from 35 through 50 exceed 60. At 34, a silent resident starting from zero takes 295 awake ticks to faint, compared with 200 today. This directly addresses the long waking spells and preserves both stimulus costs, ordinary sleep recovery and the 36-tick unconscious period.

The estimate used the retained treatment observations and acknowledged opening packet inputs for all 60,480 resident intervals. Starting at zero, add the base gain and the two stimulus costs while awake, subtract recovery during recorded voluntary sleep or projected unconsciousness, and clamp to 0–10,000. At the cap, count one faint and impose the next 36 unconscious ticks. With the original values this reproduces every observed faint tick. For the estimate, keep recorded voluntary sleep times and stimulus inputs fixed, including zero observed stimuli in formerly unconscious intervals. Actual choices, encounters and later sleep timing can change after a prevented faint.

The four passing thresholds have limited direct exposure. All 60 treatment residents took their first spring drink by tick 211, well before the earliest faint at 613, and this policy does not read fatigue. Food, water, spring access and death rules keep their original values. The main indirect risk for survival and deprivation is that additional awake ticks consume needs faster and change subsequent actions. The 20/20 all-alive cases and zero deprivation are the measured baseline. Only a new paired development result can verify the five-event margin and the other thresholds.

**Alternative:** use `awake_per_tick = 36` (−28%) and `recovery_per_tick_asleep = 175` (+16.7%). The same calculation gives **56/60 (0.93)**. This keeps silent waking tolerance closer to the original at 278 ticks and clears 8,400 points in a full sleep. It changes two coefficients, including the recovery gained during a faint. Even the maximum permitted recovery of 225 by itself still gives 81 faints on these traces.

Both proposals fit the §9.3 coefficient range. The recommended change would move the CT-09 typical-day vector from 6,400 to 4,864 while preserving the 7,200-point night recovery. The owner decides OQ-P3.5-M13-1 before any fixed-vector expectation changes. The initial pack, measured round and both sets of proposed values are recorded here for that decision. Pack edits require a separate CT-03 allocation. Held-out acceptance and D1 remain pending. [Starter spec §§5.2 and 9](../../spec/starter-content-v0.1.md) · [M13 decision D5](M13-plan.md)

### Shortest rerun plan

The owner subsequently selected the full 20-seed development option. The launch command is in the [owner decision](#owner-selected-development-check).

Use two workers, a fresh output directory per stage and the recorded `require_calibration` gate at each start. The owner chooses the tuning before the quick check. Freeze the candidate after reviewing that check, then open the acceptance list once. Estimates assume sole use of the host after EV-05. [Campaign and case admission](../../../backend/src/living_island/sim/v2/scenarios/balance/campaign.py) · [Byte comparison and evidence verification](../../../backend/src/living_island/sim/v2/scenarios/calibration/reuse.py)

| Step | Fresh simulations | Reused balance controls | Estimated wall time at two workers |
|---|---:|---:|---|
| Preferred development diagnostic, with a prefix selector added | 6 starter | 6 | 17–22 min |
| Development fallback supported by the current CLI | 20 starter | 20 | 55–65 min |
| Acceptance supported by the current CLI | 20 starter + 20 compat | 0 | 105–120 min |

**Development.** The owner-approved six-seed prefix in registration order is `2195683955, 937154673, 1452436788, 1883209505, 497199041, 3459030352`. The baseline had 34 faints in 18 resident-weeks on this prefix. Both proposals project 18/18 here, exactly the inclusive limit. All six saved compat input archives match the inputs in the balance report, and their case receipt and evidence digests match. Starter-pack-only tuning preserves their compat inputs. Their original control case indices are 18, 38, 8, 10, 36 and 26. [Registered order](../../spec/p2-experiments-v0.1.md) · [OQ-060](../../spec/open-questions.md)

The CLI currently enumerates all 20 seeds in case-name sort order, schedules both arms, and reports technical PASS only for 20 pairs. A six-seed slice would also change the plan's full-list setup hash and renumber cases, invalidating control reuse. For the short diagnostic, add a development-only selector for the six registered IDs, retain the full development list hash and each original case index, and record the selected IDs separately. Require each selected control to pass existing receipt verification before submitting the six starter cases. Report six pairs and 18 resident-weeks distinctly from qualification. This is a tooling change to make before execution. With the current CLI, the fastest supported development comparison is the full list in a fresh directory with `--reuse ../runs/m13/balance-dev`. All 20 matching controls can be admitted and only the 20 changed starter cases need simulation. [CLI](../../../backend/src/living_island/sim/v2/scenarios/balance/__main__.py) · [List and verdict checks](../../../backend/src/living_island/sim/v2/scenarios/balance/report.py)

**Acceptance.** None of the 20 calibration visible-arm inputs is byte-identical to its expected balance control. All 20 share the required 1,008-tick horizon and 24-tick cadence, but their archived plan says arm `visible`, observer `CT-20/1` and case index 1. Balance requires arm `compat-v1`, a pinned balance measurement observer and the seed's even control index. Controller, setup and recording revision pins differ as well. The calibration directories contain CT-20 comparison traces, while balance measurement consumes hash-bound opening and per-tick `observations/` absent from all 20. Moving or renaming the directories cannot satisfy these checks. Use the ordinary 40-case acceptance round once, including D1 timing on starter seed 2600456787. [Calibration recorder](../../../backend/src/living_island/sim/v2/scenarios/calibration/campaign.py) · [Balance observer](../../../backend/src/living_island/sim/v2/scenarios/balance/observations.py)

The six corresponding starter receipts total 31.7 worker-minutes, and all 20 starter receipts total 103.7. Control verification, measurement, scheduling and report publication add overhead. The 40-case acceptance estimate uses the measured 109-minute paired development round. The preferred sequence is **46 fresh cases, about 2 h 02 min–2 h 22 min** of campaign time. With today's CLI the fallback is **60 fresh cases, about 2 h 40 min–3 h 05 min**. These estimates exclude implementation and owner review time.

### Owner-selected development check

On 2026-11-24 the owner allocated the single `awake_per_tick` setting in the starter pack and selected the 20-seed development check, followed by acceptance once after candidate review. The fixed-schedule calculation reproduced all 112 observed baseline faint ticks before projecting the five candidate values.

| Awake gain per tick | Projected faints / 60 resident-weeks | Faints per resident-week |
|---:|---:|---:|
| **30 (selected)** | **49/60** | **0.8167** |
| 31 | 49/60 | 0.8167 |
| 32 | 49/60 | 0.8167 |
| 33 | 50/60 | 0.8333 |
| 34 | 55/60 | 0.9167 |

The owner's 0.80 selection target allows 48 faints. The lowest projection is 49, so the owner's fallback sets `awake_per_tick` from 50 to 30 (−40%). It projects 11 fewer faints than the §9.2 ceiling of 60.

For D5/CT-09, the published typical day (96 awake ticks, 50 heard utterances and 20 first sightings) moves from 6,400 fatigue to **4,480** (`96 × 30 + 50 × 20 + 20 × 30`). From zero fatigue, a silent resident first reaches 10,000 at **334 ticks**, previously 200. The 48-tick night still clears up to 7,200 points and a faint lasts 36 ticks. The owner will disposition the two changed vectors at Gate 3. [Published CT-09 vectors](../../spec/starter-content-v0.1.md)

**Calibration and reuse preflight.** The current admission function accepted receipt `82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5` as equal for all 59 cases with zero missing. Its 20 executable pins cover `content/packs/compat-v1` and `content/vocabulary` and exclude the starter pack. All 20 match this branch. Comparing `fbdc069` with fetched `origin/main` at `b5fb161624ef421fbc6f98a78fc3e7ebd8a8768b` showed identical objects at every pinned path. Rebasing this branch onto that tip preserves the receipt, including this branch's calibration implementation. Rebuilding the 20 development control inputs at tick zero matched the retained CT-04 archives byte for byte. Their receipt and evidence digests matched the development report, and every new starter pack hash differed from its baseline. [Calibration pins](../../../backend/src/living_island/sim/v2/scenarios/calibration/pins.py)

**Prepared command from the worktree root** (55–65 minutes at two workers, based on 103.7 measured starter worker-minutes plus control verification and reporting).

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage development --jobs 2 --calibration ../runs/m13/calibration-en10 --receipt-sha256 82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5 --equivalence-revision 3d729bcfe3bd3e2fb3207100f2075830100c3999 --reuse ../runs/m13/balance-dev --out ../runs/m13/balance-dev-awake30
```

The balance CLI takes the exclusive host lock, calls `require_calibration` before scheduling cases, and releases the lock in `finally`.

### Tuned development result and candidate freeze

On 2026-11-24 the tuned development check passed technically and on all five §9.2 thresholds. The 20 fresh starter cases were paired with their 20 verified controls from `runs/m13/balance-dev`. Each arm contributed 60 resident-weeks. The report SHA-256 is `189a58d11d6d186b0cf39d05070fe830d351063d650448deb3237e0ca5bbe3f0`. [Tuned development report](../../../runs/m13/balance-dev-awake30/report.json)

| §9.2 metric | compat-v1 | starter-v1 |
|---|---:|---:|
| All-alive cases | 20/20 | 20/20 |
| Mean deprived ticks per resident | 0 | 0 |
| Median first spring drink (ticks) | 48 | 48 |
| Faints per resident-week | 0/60 | 50/60 (0.83) |
| Deaths and new death causes | 0 | 0 |

The owner froze `starter-v1` version `0.1` at `awake_per_tick = 30` on reviewed commit `27ab740282934d8cb8dddd4d631583f2a60f299e`. Its pack tree is `8991da96e1dbac05fd8284e4c8ccd20b0917714e` and its bound pack SHA-256 is `c193d071e7593185f7641513c7a14e42d9b30eba3ceaf96e1fc563bf85f51fc0`. The single authorized acceptance round uses both arms fresh on all 20 registered acceptance seeds, the reviewed EN-10 calibration receipt, two workers and `runs/m13/balance-accept`. D1 uses the preselected starter case on seed 2600456787.

## Held-out acceptance evidence

**CT-13 PASS.** The frozen candidate passed all five §9.2 thresholds on its single held-out round. The report records execution head `bacb78e48139be9d9922df4da9d1817badbf7dc5` and calibration SHA-256 `82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5`. All 40 cases were fresh and formed 20 valid pairs, with zero failures. Each case covered three residents for 1,008 ticks. At two workers the wall time from round registration (21:11:15 SGT) to report publication (23:14:14 SGT) was **2 h 02 min 59 s** on 2026-11-24. The owner reported wrapper completion and lock release by 23:15 SGT. Report SHA-256 is `37131a9bcec492e2824d77383e740383bce6f5357c3edf562e6b840a1744f7f3`. [Acceptance report](../../../runs/m13/balance-accept/report.json) · [Round registration](../../../runs/m13/balance-accept/round.json)

| Held-out measurement | compat-v1 | starter-v1 |
|---|---:|---:|
| All-alive cases / valid cases | 20/20 | 20/20 |
| Deprived ticks / residents (mean) | 69/60 (1.15) | 0/60 (0) |
| Median first spring drink over all 60 residents (ticks) | 48 | 48 |
| Spring drinkers / never-drinkers | 60 / 0 | 60 / 0 |
| Faints / resident-weeks (mean) | 0/60 (0) | 51/60 (0.85) |
| Deaths / distinct death causes | 0 / 0 | 0 / 0 |
| Dedicated water trips | 122 | 83 |
| Awake / asleep / unconscious resident-ticks | 45,145 / 15,335 / 0 | 42,391 / 16,268 / 1,821 |
| Non-survival / living awake ticks (CT-D9) | 24,650/45,145 (54.60%) | 22,571/42,391 (53.24%) |

Each arm contributes 420 resident-days and 60,480 living resident-ticks. The water threshold uses the recorded first spring drink. The separate discovery-based access labels read `not_found` for all 60 residents in each arm despite recorded spring drinks for all 60.

**CT-10 / D1.** Preselected seed 2600456787, starter arm, completed tick 1,008 in one attempt with standard journaling and 24-tick checkpoints. Cumulative active time was 356,950,809,400 ns (5 min 56.951 s) against the 30-minute budget, with zero downtime or unclassified gap. The receipt SHA-256 is `66f735dec5f1b22a973711518c960b491d04f868d2a2b8a3bda7c667dc3f7b0c`. [Case receipt](../../../runs/m13/balance-accept/2600456787/starter-v1/cases/1.json) · [Evidence](../../../runs/m13/balance-accept/2600456787/starter-v1/evidence.json) · [Timing database](../../../runs/m13/balance-accept/2600456787/starter-v1/progress.sqlite)

**D5 / CT-09 for Gate 3.** The published awake gain is 50 and the qualified pack uses 30. For 96 awake ticks, 50 heard utterances and 20 first sightings, published day fatigue is 6,400 and pack fatigue is 4,480. From zero fatigue, the published silent faint occurs at tick 200 and the pack faint at tick 334. Both use a 36-tick faint and recover up to 7,200 fatigue in 48 ticks of sleep. The owner retains disposition of the two changed vectors. [Starter specification §5.2](../../spec/starter-content-v0.1.md)

### Acceptance case receipts

Each link displays the first 12 hex digits of the receipt SHA-256. The acceptance report records the full receipt and evidence digests under `cases["<seed>/<arm>"]`. All 40 receipt files and all 40 evidence files matched those digests.

| Seed | compat-v1 receipt | starter-v1 receipt |
|---:|---|---|
| 2600456787 | [43bba39d3a75](../../../runs/m13/balance-accept/2600456787/compat-v1/cases/0.json) | [66f735dec5f1](../../../runs/m13/balance-accept/2600456787/starter-v1/cases/1.json) |
| 1007489817 | [3b352493df73](../../../runs/m13/balance-accept/1007489817/compat-v1/cases/2.json) | [9f0c3ecc84e5](../../../runs/m13/balance-accept/1007489817/starter-v1/cases/3.json) |
| 1557484054 | [6bb18a16415d](../../../runs/m13/balance-accept/1557484054/compat-v1/cases/4.json) | [da9f30060def](../../../runs/m13/balance-accept/1557484054/starter-v1/cases/5.json) |
| 1569596598 | [44a8d77c5842](../../../runs/m13/balance-accept/1569596598/compat-v1/cases/6.json) | [4f036eebd1a8](../../../runs/m13/balance-accept/1569596598/starter-v1/cases/7.json) |
| 1802799976 | [641544d771a8](../../../runs/m13/balance-accept/1802799976/compat-v1/cases/8.json) | [f9dda9fe8e2d](../../../runs/m13/balance-accept/1802799976/starter-v1/cases/9.json) |
| 2122883013 | [e51f06eb3fb9](../../../runs/m13/balance-accept/2122883013/compat-v1/cases/10.json) | [e889b3efa89c](../../../runs/m13/balance-accept/2122883013/starter-v1/cases/11.json) |
| 2170312666 | [6b8802cfc412](../../../runs/m13/balance-accept/2170312666/compat-v1/cases/12.json) | [9493ce0ee5d7](../../../runs/m13/balance-accept/2170312666/starter-v1/cases/13.json) |
| 2560155364 | [f51a08b19272](../../../runs/m13/balance-accept/2560155364/compat-v1/cases/14.json) | [063687a24d9e](../../../runs/m13/balance-accept/2560155364/starter-v1/cases/15.json) |
| 2733016023 | [7abb911c7bb3](../../../runs/m13/balance-accept/2733016023/compat-v1/cases/16.json) | [e892c69d4c39](../../../runs/m13/balance-accept/2733016023/starter-v1/cases/17.json) |
| 3178109895 | [4b321bdd91c9](../../../runs/m13/balance-accept/3178109895/compat-v1/cases/18.json) | [a8c721123a7f](../../../runs/m13/balance-accept/3178109895/starter-v1/cases/19.json) |
| 330361958 | [657d04e58962](../../../runs/m13/balance-accept/330361958/compat-v1/cases/20.json) | [10c9de32f40e](../../../runs/m13/balance-accept/330361958/starter-v1/cases/21.json) |
| 3335059634 | [f0329d010b6f](../../../runs/m13/balance-accept/3335059634/compat-v1/cases/22.json) | [53d113445934](../../../runs/m13/balance-accept/3335059634/starter-v1/cases/23.json) |
| 3486741106 | [68650c22f710](../../../runs/m13/balance-accept/3486741106/compat-v1/cases/24.json) | [84d9c676248e](../../../runs/m13/balance-accept/3486741106/starter-v1/cases/25.json) |
| 3501343423 | [9a4e9d535f59](../../../runs/m13/balance-accept/3501343423/compat-v1/cases/26.json) | [f843748a8f74](../../../runs/m13/balance-accept/3501343423/starter-v1/cases/27.json) |
| 4155892942 | [30816b9c179c](../../../runs/m13/balance-accept/4155892942/compat-v1/cases/28.json) | [47112eb4bded](../../../runs/m13/balance-accept/4155892942/starter-v1/cases/29.json) |
| 598561891 | [6c60132c13a3](../../../runs/m13/balance-accept/598561891/compat-v1/cases/30.json) | [76214c60e54b](../../../runs/m13/balance-accept/598561891/starter-v1/cases/31.json) |
| 646834264 | [878eacf124fa](../../../runs/m13/balance-accept/646834264/compat-v1/cases/32.json) | [12ad43b6c443](../../../runs/m13/balance-accept/646834264/starter-v1/cases/33.json) |
| 857949281 | [d43305d8baad](../../../runs/m13/balance-accept/857949281/compat-v1/cases/34.json) | [159598af55c8](../../../runs/m13/balance-accept/857949281/starter-v1/cases/35.json) |
| 958049702 | [5ae2b243daa6](../../../runs/m13/balance-accept/958049702/compat-v1/cases/36.json) | [0c7f3f8d36e8](../../../runs/m13/balance-accept/958049702/starter-v1/cases/37.json) |
| 969717619 | [02a8c023a279](../../../runs/m13/balance-accept/969717619/compat-v1/cases/38.json) | [6b89480813e9](../../../runs/m13/balance-accept/969717619/starter-v1/cases/39.json) |
