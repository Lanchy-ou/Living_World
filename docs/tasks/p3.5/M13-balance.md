# M13 starter balance qualification

## Status before qualification

| Stage | Registered pairs | Result | Evidence |
|---|---:|---|---|
| Development | 20 | NOT_RUN | Gated by EN-10 recalibration |
| Held-out acceptance | 20 | NOT_RUN | Awaiting development and candidate freeze |
| D1 and CT-D9 | — | NOT_RUN | Read the held-out treatment receipts below |

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
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage acceptance --calibration $ct05Dir --receipt-sha256 $ct05Sha --equivalence-revision $equivalenceRevision --jobs 4 --out ../runs/m13/balance-accept
```

For a restart, use the original command and directory. For a receipt-only rebuild, append `--report-only` to that command. For example, after the initial held-out round:

```powershell
uv run --directory backend python -m living_island.sim.v2.scenarios.balance --stage acceptance --calibration $ct05Dir --receipt-sha256 $ct05Sha --equivalence-revision $equivalenceRevision --jobs 4 --out ../runs/m13/balance-accept --report-only
```

Budget about five hours per round at 30 minutes per case and four workers (ten waves). EN-08's lighter compatibility projection took 3,201 seconds for 20 serial weeks. CT-04 writes the full packet journal, turn log, observation files and checkpoints. Actual four-worker wall time and disk contention remain unmeasured. [EN-08 timing](P3.5-EN-08.md)

## Reading the report

- `round.json` and `scope.json` record the registration, calibration digest, candidate, executable pins and host settings. `report.json` joins the complete seed list. `reports/` retains published summaries and `failures/` retains failed case inspections or attempts. Interrupted runs also retain per-attempt timing in SQLite.
- `cases["<seed>/<arm>"]` identifies the verified CT-04 evidence, receipt digest, content ancestry, checkpoint schedule, complete timing history and P2 resident and run metrics. `days` gives each resident's seven rows, using opening-tick day membership. Sleep and unconsciousness have separate totals. An awake interval has one paid attempt, including failed starts. A move inherits survival only from its immediate next start with matching destination and reach. Zero living awake intervals yield a null fraction.
- `arms` gives the valid case and resident counts, spring drinkers and never-drinkers, deaths, water trips, mean deprivation, median spring-drink tick and faints. Counts of deprivation include the closing needs of the final interval if the resident was alive at its opening. Each never-drinker contributes 1009 to the 60-resident median. `paired` and `access_by_resident` supply paired differences and the control-to-treatment access transitions.
- `technical` requires 40 matched valid cases. `thresholds` applies starter §9.2 with inclusive limits. `verdict` records the result for the named list. Qualification uses the frozen candidate's held-out result. The separate `ct_d9_at_least_30_percent` field compares pooled treatment non-survival ticks to living awake ticks for owner review. M15 owns the live-resident measurement.
- For CT-10, follow `d1_case` to the preselected held-out treatment row, then open its case receipt, evidence and timing database. `timing.active_ns` sums measured attempts through durable evidence publication. Timing also records downtime, unclassified gaps, throughput and the D1 budget verdict.

## Round history

Development candidate freeze, report paths and SHA-256 digests, held-out verdict, D1 timing, CT-D9 signal and any tuning history are pending phase 2. No pack tuning was performed in phase 1.
