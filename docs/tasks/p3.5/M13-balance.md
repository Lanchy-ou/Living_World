# M13 starter balance qualification

## Qualification status

| Stage | Registered pairs | Result | Evidence |
|---|---:|---|---|
| Development | 20 | Technical PASS, verdict FAIL | 112 treatment faints in 60 resident-weeks. See [development evidence](#development-evidence). |
| Tuned development | 20 | READY_TO_RUN | Awake gain 30. Fresh starter cases and retained controls await host release. See [owner decision](#owner-selected-development-check). |
| Held-out acceptance | 20 | NOT_RUN | One round after tuned development and candidate freeze |
| D1 and CT-D9 | — | D1 pending, development CT-D9 above 30% | 21,588 of 40,080 treatment awake ticks were non-survival. Held-out measurements are pending. |

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

The owner's 0.80 selection target allows 48 faints. The lowest projection is 49, so the owner's fallback sets `awake_per_tick` from 50 to 30 (−40%). It projects 11 fewer faints than the §9.2 ceiling of 60. The treatment pack bound to the registered production inputs has SHA-256 `c193d071e7593185f7641513c7a14e42d9b30eba3ceaf96e1fc563bf85f51fc0`. The measured result on this pack is pending.

For D5/CT-09, the published typical day (96 awake ticks, 50 heard utterances and 20 first sightings) moves from 6,400 fatigue to **4,480** (`96 × 30 + 50 × 20 + 20 × 30`). From zero fatigue, a silent resident first reaches 10,000 at **334 ticks**, previously 200. The 48-tick night still clears up to 7,200 points and a faint lasts 36 ticks. The owner will disposition the two changed vectors at Gate 3. [Published CT-09 vectors](../../spec/starter-content-v0.1.md)

**Calibration and reuse preflight.** The current admission function accepted receipt `82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5` as equal for all 59 cases with zero missing. Its 20 executable pins cover `content/packs/compat-v1` and `content/vocabulary` and exclude the starter pack. All 20 match this branch. Comparing `fbdc069` with fetched `origin/main` at `b5fb161624ef421fbc6f98a78fc3e7ebd8a8768b` showed identical objects at every pinned path. Rebasing this branch onto that tip preserves the receipt, including this branch's calibration implementation. Rebuilding the 20 development control inputs at tick zero matched the retained CT-04 archives byte for byte. Their receipt and evidence digests matched the development report, and every new starter pack hash differed from its baseline. [Calibration pins](../../../backend/src/living_island/sim/v2/scenarios/calibration/pins.py)

**Prepared command from the worktree root** (55–65 minutes at two workers, based on 103.7 measured starter worker-minutes plus control verification and reporting).

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage development --jobs 2 --calibration ../runs/m13/calibration-en10 --receipt-sha256 82aa10718fd9de52a4abae70a08cf6795ce43ddcc4a8a20fd32a95ef4d3f4fd5 --equivalence-revision 3d729bcfe3bd3e2fb3207100f2075830100c3999 --reuse ../runs/m13/balance-dev --out ../runs/m13/balance-dev-awake30
```

The current balance CLI wraps the development campaign in the same exclusive `heavy_lock()` used by the previous wrapper. It releases the lock in `finally`, including on error, and calls `require_calibration` before scheduling cases. This command selects only development and publishes into a new directory. EV-05 has the host. Launch awaits the owner's release notice.
