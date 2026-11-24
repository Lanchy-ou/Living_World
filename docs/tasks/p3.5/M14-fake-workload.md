# M14 fake workload rehearsal

The five-resident week and the separate three-day Ella rehearsal both passed EV-05’s offline evidence checks on 2026-11-24. Ella’s forecast for three days with rule companions was CNY 2.575288 at the scripted output size, or CNY 9.470744 with the full output reserve. Independent phase 2 review is pending.

## Evidence cases

| Case | World and controllers | Seed | Horizon |
|---|---|---|---|
| Week | One shared island. Ella/explorer, Ryan/cautious, Mia/cooperative, Noah/maker and Iris/bold each use their own memory-on decision loop and fake byte transport. | 20261108 | 1,008 ten-minute ticks |
| Cost | Production compat-v1. Ella/explorer uses memory and the fake byte transport. Ryan and Mia use the normal rule controller. | 20261108 | 432 ten-minute ticks |

The week uses the merged, hash-admitted regrowth-2 configuration, its unchanged island map and the normal setup roster extended with Noah at (36,32) and Iris at (37,32). The higher fruit regrowth supports five scripted foragers. This composition is an EV-13 fixture outside the PR-07 equivalence matrix. The cost case uses the default production seed and setup. EV-06 can use this same seed for the comparison, subject to its paid registration.

The fake actors follow scripted routes between a tree and the spring, choose from their sent text, rest, drink, gather, eat and request recall. Their first decision exercises timeout, rate limit, server error and invalid output on retries. Noah also receives a nonretryable decision error. Ella's first selection receives a nonretryable provider error. The next successful change set must consume that pending period. An observed location supports an episodic addition alongside a reference to a missing memory. Short terminal branches retain the protected-floor no-dispatch record and abandonment at authorization, preparation and dispatch, including interrupted and late-return evidence.

## Receipts and verified exports

The session finished at 15:44 SGT on 2026-11-24 at source commit `b6fba61d0868b377e8f6c253430f7b637b7f7d18`. Both cases passed with zero network dispatches and CNY 0 charged. Raw artifacts are in `runs/ev05-7e8_yjab`. Local Users have inherited read and execute access. The receipt digests and the six export index hashes below were checked against the retained files.

| Case and receipt | Ticks | Capture wall time | Through final receipt¹ | Receipt SHA-256 |
| --- | --- | --- | --- | --- |
| [Week](../../../runs/ev05-7e8_yjab/week/receipt.json) | 1008 | 38m 30.454s | 38m 45.713s | `c3e585fa3b9b362319792ca4318cf36499caefdcb9b4f359ba28b8daeac6e5fa` |
| [Ella](../../../runs/ev05-7e8_yjab/ella/receipt.json) | 432 | 4m 30.127s | 4m 30.684s | `89ed3f2f9597b735faa0d793bc013924bf00f8210ef469ca5320b5773e4bacbc` |

¹ Capture includes recording, offline replay, export and shard verification, plus Ella’s six staged fake requests. The last timing uses case-directory creation through final receipt write and also includes analysis-mode opening and the week’s bounded terminal checks.

| Case | Resident index | Index SHA-256 | Shard references checked | Revisions verified after opening |
| --- | --- | --- | --- | --- |
| Week | [ella](../../../runs/ev05-7e8_yjab/week/inspection-ella/index.json) | `2e6293cc0cc2174c2794a6c9d07a1bd9e8a6331b4edd7da91515fa5806331b96` | 12167 | 3443 |
| Week | [iris](../../../runs/ev05-7e8_yjab/week/inspection-iris/index.json) | `790b62f1fb72eb5293a2ddaf131944c7758f3b33652f21980b80383f4beb62d3` | 12228 | 3473 |
| Week | [mia](../../../runs/ev05-7e8_yjab/week/inspection-mia/index.json) | `0c20519213e281619fc747996c464d3d5e8e2c28e1ca2a600751ee95f654a6e2` | 12072 | 3389 |
| Week | [noah](../../../runs/ev05-7e8_yjab/week/inspection-noah/index.json) | `873de2a882371e924d98531a0fe7fd5a685d80eaeb72ae8852757c80bad968cd` | 12227 | 3469 |
| Week | [ryan](../../../runs/ev05-7e8_yjab/week/inspection-ryan/index.json) | `67f100e41a25e1effd90af593abe847f5d1e88d2f9c86ebbd86a1e3c5603a152` | 12275 | 3496 |
| Ella | [ella](../../../runs/ev05-7e8_yjab/ella/inspection-ella/index.json) | `8cdf3941ca277eafef6fa1e3e54b2aa4d8c0932a3d764bd0661862af963d64df` | 1712 | 147 |

All six exports opened the resident’s tick-zero decision through the shipped analysis view. Offline replay rebuilt prepared and dispatched requests, checked store revisions, submissions, packet and event bytes, and matched the final world checkpoint. All five week exports shared the same world hash. Every indexed part fit the 8 MiB limit.

| Case | Run manifest SHA-256 | Display replay SHA-256 | Final world SHA-256 |
| --- | --- | --- | --- |
| Week | `cf6d9d93885100349775682ab1691784fd9c34dd45f0a15039deb752d6253e6f` | `3067fd42ffb4bad1da3ead530b2cf8bfa365496d0fdccd0784bf9c78e32da9e0` | `c2c49d9b92fe863833486654732883939cb4b3431c9b517f4d15767ffb49b690` |
| Ella | `463544ddbb1f082fb17314cd10cd7404bf2a41b54c7110ca9b7072632d37ce4c` | `154baf11c1f02472f6533de0cfe87ccd8559ead4d4219dfdb09a5aa145631461` | `14aa4c2a25e0300a8c3cb899fbefabbf3c74cba1971e7857855f87a3d544bf9c` |

## Period outcomes and terminal counts

Each period ID has the form `p:<resident>:<number>`. In the week, Ella committed periods 2–23, and Iris, Mia, Noah and Ryan each committed periods 1–23. That gives 114 committed periods and one failed period. In the separate Ella case, periods 2–9 committed and period 1 failed. In **both** cases Ella’s first consolidation selection returned HTTP 400. Period 1 closed as failed at tick 45. The store retained `p:ella:1` as pending until the commit of `p:ella:2` included it at tick 82. All residents ended with an empty pending list. In the separate case, waking abandoned the first selection for `p:ella:8` before dispatch (closure at tick 340). The same period committed at tick 385. This accounts for day 3’s 30 logical calls and 29 attempts.

| Case | Success | Timeout | Rate limit | Server error | Invalid output | Provider error (HTTP 400) | Total terminals |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Week | 1091 | 5 | 5 | 5 | 5 | 2 | 1113 |
| Ella | 104 | 1 | 1 | 1 | 1 | 1 | 109 |

The week’s second HTTP 400 occurred on Noah’s seventh decision dispatch. His fallback turn was `noah:t000002` and control returned to the model on `noah:t000003`. The separate bounded week checks recorded a protected-floor stop with zero dispatches and death after authorization, preparation and dispatch. The week recorded 114 committed and 114 dropped memory operations. The separate Ella case recorded 7 committed and 8 dropped.

The week recorded 572 increases in day-log token count between decision requests within the same waking period. The separate Ella case recorded 63. Week inspection also found continue, intent, utterance, intention set and clear, mute and valid citation outputs.

## Daily workload and cost

Each pair gives logical calls / dispatched attempts. A week row sums all five residents. Retries count attempts after the initial dispatch.

| Case / day | Decision | Recall | Decision after recall | Morning | Consolidation selection | Consolidation change set | Total | Retries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Week 1 | 156/176 | 17/17 | 17/17 | 14/14 | 18/18 | 17/17 | 239/259 | 20 |
| Week 2 | 82/82 | 8/8 | 8/8 | 16/16 | 17/17 | 17/17 | 148/148 | 0 |
| Week 3 | 82/82 | 6/6 | 6/6 | 16/16 | 16/16 | 16/16 | 142/142 | 0 |
| Week 4 | 82/82 | 6/6 | 6/6 | 19/19 | 17/17 | 17/17 | 147/147 | 0 |
| Week 5 | 70/70 | 7/7 | 7/7 | 16/16 | 17/17 | 17/17 | 134/134 | 0 |
| Week 6 | 74/74 | 7/7 | 7/7 | 16/16 | 16/16 | 16/16 | 136/136 | 0 |
| Week 7 | 89/89 | 6/6 | 6/6 | 18/18 | 14/14 | 14/14 | 147/147 | 0 |
| Ella 1 | 27/31 | 3/3 | 3/3 | 3/3 | 4/4 | 3/3 | 43/47 | 4 |
| Ella 2 | 20/20 | 2/2 | 2/2 | 3/3 | 3/3 | 3/3 | 33/33 | 0 |
| Ella 3 | 20/20 | 1/1 | 1/1 | 3/3 | 3/2 | 2/2 | 30/29 | 0 |

Daily times cover recording only. Guarded and sent columns give the largest single request body in bytes. Token bounds and forecasts sum all dispatched attempts, including retries. The price pin is the M9 historical peak on 2026-11-14, **CNY 2 per million uncached input tokens and CNY 8 per million output tokens**, with zero cache hits. Both forecasts use the recorded input bound. The central estimate uses the scripted output bound. The conservative estimate reserves 8,000 output tokens per observed attempt. The separate six-call provider check is excluded from these totals. [M9 price evidence](../p3/M9-evidence.md)

| Case / day | Recording (s) | Guarded (B) | Sent (B) | Input bound | Scripted output bound | Output reserve | Central (CNY) | Conservative (CNY) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Week 1 | 93.377 | 35580 | 35580 | 3364562 | 22851 | 2072000 | 6.911932 | 23.305124 |
| Week 2 | 74.520 | 25511 | 25511 | 1604923 | 13542 | 1184000 | 3.318182 | 12.681846 |
| Week 3 | 72.156 | 25617 | 25617 | 1567751 | 13265 | 1136000 | 3.241622 | 12.223502 |
| Week 4 | 74.151 | 25589 | 25589 | 1582834 | 13510 | 1176000 | 3.273748 | 12.573668 |
| Week 5 | 73.240 | 25408 | 25408 | 1425961 | 12064 | 1072000 | 2.948434 | 11.427922 |
| Week 6 | 73.032 | 25622 | 25622 | 1491057 | 12418 | 1088000 | 3.081458 | 11.686114 |
| Week 7 | 79.084 | 26061 | 26061 | 1661084 | 13667 | 1176000 | 3.431504 | 12.730168 |
| Ella 1 | 23.941 | 28343 | 28343 | 532380 | 3754 | 376000 | 1.094792 | 4.072760 |
| Ella 2 | 31.609 | 25275 | 25275 | 362682 | 3259 | 264000 | 0.751436 | 2.837364 |
| Ella 3 | 37.911 | 27598 | 27598 | 352310 | 3055 | 232000 | 0.729060 | 2.560620 |

Ella’s three-day totals were **CNY 2.575288 central and CNY 9.470744 conservative**. Day 1 had four retries and 47 dispatches. Days 2 and 3 had 33 and 29 dispatches respectively.

## Daily section sizes

Bytes are UTF-8 totals for section entries across sent attempts. Week columns sum all five residents. A zero means that section contributed no sent bytes that day.

| Section | Week 1 | Week 2 | Week 3 | Week 4 | Week 5 | Week 6 | Week 7 | Ella 1 | Ella 2 | Ella 3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `current_state` | 222348 | 178533 | 174158 | 183331 | 161758 | 167364 | 182200 | 35515 | 31924 | 28552 |
| `day_log` | 851378 | 241637 | 234344 | 220838 | 198829 | 218574 | 234161 | 89598 | 57030 | 67945 |
| `index` | 22666 | 30449 | 37691 | 51722 | 60183 | 67655 | 72929 | 3049 | 4318 | 6219 |
| `index_header` | 455 | 442 | 416 | 442 | 442 | 416 | 364 | 91 | 78 | 52 |
| `pending_periods` | 14526 | 0 | 0 | 0 | 0 | 0 | 0 | 9782 | 0 | 0 |
| `prefix` | 240962 | 165550 | 160082 | 162959 | 150193 | 150852 | 162629 | 44555 | 37940 | 33526 |
| `query` | 612 | 288 | 216 | 216 | 252 | 252 | 216 | 108 | 72 | 36 |
| `required_records` | 30820 | 30902 | 29100 | 30918 | 30902 | 29100 | 25452 | 908 | 1826 | 1370 |
| `schema` | 3633116 | 1752390 | 1709772 | 1716544 | 1514984 | 1581818 | 1825528 | 640306 | 420988 | 396560 |
| `selected_records` | 11466 | 11484 | 10810 | 11486 | 11485 | 10821 | 9472 | 2026 | 2028 | 1352 |
| `system` | 75441 | 43191 | 41622 | 42651 | 39165 | 39548 | 42211 | 13670 | 9535 | 8332 |

## Three-day forecast comparison

The first three days share a seed and day length. The five-resident run uses regrowth-2 and four fake companions for Ella. The separate production case uses two rule companions. The last three columns describe the separate case. [Retained comparison.json](../../../runs/ev05-7e8_yjab/comparison.json) · SHA-256 `0d7706cc2612ebcee53480989ca453c45fd0a6cd7062a0d98860bc9590889fd8`

| Day | Five residents (CNY) | Ella with fake companions (CNY) | Ella with rule companions (CNY) | Ella calls | Ella attempts | Ella largest sent (B) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 6.911932 | 1.184210 | 1.094792 | 43 | 47 | 28343 |
| 2 | 3.318182 | 0.614138 | 0.751436 | 33 | 33 | 25275 |
| 3 | 3.241622 | 0.732014 | 0.729060 | 30 | 29 | 27598 |

## Operator command

The fake controller schedules sleep for 36 ticks when its K delivery fits within the case. Near the horizon it uses a shorter schema-valid sleep of 6–35 ticks. This leaves every authorized consolidation with a recorded disposition at export time. Its final waking period can remain open. The bounded tests exercise this same schedule.

The completed session used the following command from the repository root with locked backend and frontend dependencies. The command takes the shared lock exclusively for both cases, fails immediately if occupied, creates a fresh ignored directory and prints its path. It releases its own lock on exit.

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

The case receipts retain resident-level daily rows. Actual provider usage, cache behavior and the live tariff await DL-06. [Phase spend ledger](P3.5-spend-ledger.md)
