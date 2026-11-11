# P2-04 development experiments for M6

## Inputs and timing

The baseline is local `main` at `22345ca814a3caafd2ef7b13c2abd7f957c9978f` with MF
accepted. The experiment code commit is `6412dc9b60b88809f33f845a96fc19dc87d1bed4`,
which adds the immutable S4 fixture. P2-03 checked each scenario's content against its
pin and applied all eight [technical checks](../../spec/p2-experiments-v0.1.md#4-pass-lines).

| Case label | Scenario and variant | Pin | Single factor relative to S2/base |
|---|---|---|---|
| S1 | `s1-spring-visible:orig:base` | `d533cd7` | Spawns move from Ella (12,32), Ryan (13,32), Mia (14,32) to (33,32), (34,32), (35,32). |
| S2 | `s2-default:orig:base` | `04fde8b` | Original map and settings. Decay 100, fruit regrowth 144, canteen and cue enabled. |
| S2-R | `s2-default:orig:canteen-restricted` | `04fde8b` | `canteen_use=restricted`. |
| S2-I | `s2-default:orig:cue-ignored` | `04fde8b` | `cue_use=ignored`. |
| S3 | `s3-regrow288:orig:base` | `b5f512f` | Fruit regrowth 144 → 288 ticks. |
| S4 | `s4-decay120:orig:base` | `6412dc9` | Hydration decay 100 → 120 per tick. |
| S4-R | `s4-decay120:orig:canteen-restricted` | `6412dc9` | Relative to S4, only `canteen_use=restricted`. |

All fixtures name the same map bytes. The SHA-256 of the retained map is
`007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c`. The two arms
of each canteen or cue comparison use the same effective world config and distinct
tick-zero policy config hashes. The spawns, regrowth and decay comparisons hold
`RuleParams` fixed.

Before launching the matrix, `p2-04-pilot` ran S2/base at seed `2195683955` through
P2-03, including replay export and analysis. It exited 0 in **70.7 s** and passed all
eight checks. This timing samples an early-death S2 run. P2-02 measured **342 s** for
a solo S1 run whose three residents remained alive. [P2-02 timing](P2-02.md#handoff)

Under OQ-060 the owner approved the first six registered development seeds and all
seven cases per seed. The [task card](P2-04.md#oq-060-disposition-for-this-round)
records their registration order and batch IDs. The matrix comprises **42 runs of
1,008 ticks** in six concurrent batches. The other 14 registered development seeds
account for 98 cases outside this round. They are
`2507182619`, `3698676642`, `2144999532`, `1263016932`, `2344699806`,
`1011827743`, `2104929825`, `2520148199`, `201486072`, `1021125776`,
`1334592829`, `3695162045`, `3976177611` and `404876745`.
The 20 acceptance seeds remain reserved for P2-05.

## Comparison conditions

- Canteen restriction includes loss of access to the two initial servings. Both arms
  start with a slot occupied. A transfer can move that slot to another resident in
  the enabled arm. The restricted policy leaves a dropped canteen in place.
- The first changed action can alter later contention and resolution order. Differences
  use treatment minus control on each seed's run totals. Rates divide by living exposure
  from the prior boundary, including the interval that ends in death. Deaths are
  counted separately by whether the resident held the canteen at the preceding frame.
  Nonholder deaths provide no evidence of canteen benefit.
- The cue comparison covers directions captured at decisions. S1 moves spawns as a
  group, which changes initial visibility and travel geometry. S1 versus S2 is the
  discovery and survival diagnosis. S2 versus S2-I isolates cue use.
- The paired tool keeps its registered 20-seed gate. The reduced-scope summary applies
  the same case checks and pairs the six selected seeds. It preserves both the full
  gate and the selected-set disposition in the aggregate.

## Results

### Batch and case dispositions

The six batches took **2589.8 s** wall time.
**42/42** cases passed all eight checks. **0** selected cases failed or lack completed artifacts.

| Seed | Batch seconds | Exit | Valid | Failed or incomplete |
| --- | --- | --- | --- | --- |
| 2195683955 | 1509.8 | 0 | 7 | — |
| 937154673 | 1627.1 | 0 | 7 | — |
| 1452436788 | 2142.8 | 0 | 7 | — |
| 1883209505 | 1890.1 | 0 | 7 | — |
| 497199041 | 2139.9 | 0 | 7 | — |
| 3459030352 | 2589.8 | 0 | 7 | — |

| Round | Pairs used | Selected verdict | Selected seeds dropped | Full tool verdict | Full gate missing arms |
| --- | --- | --- | --- | --- | --- |
| S4 decay 100 | 6 | PASS | — | FAIL | 28 |
| S4 decay 120 | 6 | PASS | — | FAIL | 28 |
| S5 cue | 6 | PASS | — | FAIL | 28 |

The full verdict applies the tool's 20-seed requirement to the joined results. Its
28 missing arms per round are the two arms for each of the 14 excluded seeds. Each
raw one-seed batch summary applies the same 20-seed requirement to its own seed.

### Survival and water access

Water access is spring drank / found without a spring drink / never found. Timing cells give median [min, max], then the number of observed residents. Censored residents are counted in the access split and excluded from the observed medians. Any drink includes the canteen.

| Arm | Valid seeds | All 3 alive | Residents alive | Spring access | Discovery tick | Any first drink tick | First spring drink tick |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 6 | 6 | 18 | 18 / 0 / 0 | 0 [0, 0], 18 | 46 [42, 50], 18 | 49 [45, 178], 18 |
| S2 | 6 | 1 | 9 | 9 / 1 / 8 | 82 [44, 230], 10 | 48 [42, 84], 10 | 175 [76, 232], 9 |
| S2-R | 6 | 0 | 4 | 4 / 1 / 13 | 78 [73, 82], 5 | 80 [76, 84], 4 | 80 [76, 84], 4 |
| S2-I | 6 | 0 | 8 | 8 / 0 / 10 | 81.5 [35, 152], 8 | 46 [42, 85], 10 | 130.5 [60, 179], 8 |
| S3 | 6 | 1 | 9 | 9 / 1 / 8 | 82 [44, 230], 10 | 48 [42, 84], 10 | 175 [76, 232], 9 |
| S4 | 6 | 0 | 5 | 5 / 1 / 12 | 112 [86, 144], 6 | 35 [35, 88], 7 | 140 [88, 147], 5 |
| S4-R | 6 | 0 | 4 | 4 / 0 / 14 | 78 [70, 86], 4 | 80.5 [72, 88], 4 | 80.5 [72, 88], 4 |

### Deprivation and travel costs

Exposure and action columns are totals across valid runs. Water and food deprivation can overlap.

| Arm | Exposure ticks | Deprived ticks | Water | Food | Dedicated trips | Water-only visits | Move ticks | Gathers | Spring drinks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 18144 | 0 | 0 | 0 | 27 | 95 | 7432 | 252 | 246 |
| S2 | 11190 | 1335 | 1335 | 0 | 7 | 33 | 3789 | 135 | 104 |
| S2-R | 7140 | 2007 | 2007 | 0 | 6 | 20 | 2437 | 63 | 72 |
| S2-I | 10524 | 1437 | 1437 | 0 | 5 | 33 | 3530 | 122 | 95 |
| S3 | 11190 | 1447 | 1335 | 112 | 26 | 53 | 4983 | 122 | 101 |
| S4 | 7957 | 1880 | 1880 | 0 | 7 | 29 | 2903 | 84 | 62 |
| S4-R | 6958 | 2055 | 2055 | 0 | 10 | 24 | 2595 | 68 | 86 |

| Arm | Canteen drinks | Fills | Canteens given | Canteens received | Transfer then drink | Cap waste | Slot-full holding | Slot-full without |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 66 | 30 | 0 | 0 | 0 | 66400 | 0 | 0 |
| S2 | 55 | 23 | 0 | 0 | 0 | 42600 | 0 | 0 |
| S2-R | 0 | 0 | 0 | 0 | 0 | 28000 | 0 | 0 |
| S2-I | 48 | 20 | 0 | 0 | 0 | 34000 | 0 | 0 |
| S3 | 55 | 23 | 0 | 0 | 0 | 28200 | 0 | 0 |
| S4 | 45 | 18 | 2 | 2 | 0 | 22320 | 0 | 0 |
| S4-R | 0 | 0 | 0 | 0 | 0 | 39320 | 0 | 0 |

### Death diagnoses

| Arm | Never found | Found, no spring drink | Post-access dehydration | Food access | Food supply | Holder deaths | Nonholder deaths |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| S2 | 8 | 1 | 0 | 0 | 0 | 1 | 8 |
| S2-R | 13 | 1 | 0 | 0 | 0 | 6 | 8 |
| S2-I | 10 | 0 | 0 | 0 | 0 | 2 | 8 |
| S3 | 8 | 1 | 0 | 0 | 0 | 1 | 8 |
| S4 | 12 | 1 | 0 | 0 | 0 | 3 | 10 |
| S4-R | 14 | 0 | 0 | 0 | 0 | 3 | 11 |

### Per-seed outcomes

Triples list Ella / Mia / Ryan. A dash means the event is unobserved. Case IDs are the scenario, revision and variant from the input table followed by `.s<seed>`.

| Seed | Case | §4 | Alive | Discovery ticks | Any first drink ticks | First spring drink ticks | Water / food deprived ticks | Dedicated trips | Move ticks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2195683955 | S1 | PASS | 3 | 0 / 0 / 0 | 47 / 45 / 42 | 47 / 45 / 176 | 0 / 0 | 7 | 1278 |
| 2195683955 | S2 | PASS | 0 | – / 82 / – | – / – / 44 | – / – / – | 429 / 0 | 0 | 322 |
| 2195683955 | S2-R | PASS | 0 | – / 82 / – | – / – / – | – / – / – | 429 / 0 | 0 | 247 |
| 2195683955 | S2-I | PASS | 0 | – / – / – | – / – / 42 | – / – / – | 429 / 0 | 0 | 323 |
| 2195683955 | S3 | PASS | 0 | – / 82 / – | – / – / 44 | – / – / – | 429 / 0 | 0 | 322 |
| 2195683955 | S4 | PASS | 1 | – / – / 144 | – / – / 35 | – / – / 147 | 286 / 0 | 0 | 461 |
| 2195683955 | S4-R | PASS | 1 | – / – / 83 | – / – / 86 | – / – / 86 | 305 / 0 | 2 | 506 |
| 937154673 | S1 | PASS | 3 | 0 / 0 / 0 | 49 / 50 / 42 | 49 / 50 / 175 | 0 / 0 | 3 | 1305 |
| 937154673 | S2 | PASS | 1 | – / – / 44 | – / – / 42 | – / – / 179 | 286 / 0 | 0 | 456 |
| 937154673 | S2-R | PASS | 0 | – / – / – | – / – / – | – / – / – | 429 / 0 | 0 | 246 |
| 937154673 | S2-I | PASS | 1 | – / 57 / – | – / 60 / 42 | – / 60 / – | 286 / 0 | 1 | 574 |
| 937154673 | S3 | PASS | 1 | – / – / 44 | – / – / 42 | – / – / 179 | 286 / 0 | 0 | 463 |
| 937154673 | S4 | PASS | 0 | – / – / – | – / – / 35 | – / – / – | 429 / 0 | 0 | 309 |
| 937154673 | S4-R | PASS | 0 | – / – / – | – / – / – | – / – / – | 429 / 0 | 0 | 246 |
| 1452436788 | S1 | PASS | 3 | 0 / 0 / 0 | 46 / 45 / 42 | 46 / 45 / 175 | 0 / 0 | 7 | 1166 |
| 1452436788 | S2 | PASS | 2 | 82 / – / 230 | 84 / – / 45 | 84 / – / 232 | 179 / 0 | 1 | 685 |
| 1452436788 | S2-R | PASS | 1 | 82 / – / – | 84 / – / – | 84 / – / – | 290 / 0 | 1 | 466 |
| 1452436788 | S2-I | PASS | 1 | – / – / 119 | – / – / 44 | – / – / 177 | 286 / 0 | 0 | 487 |
| 1452436788 | S3 | PASS | 2 | 82 / – / 230 | 84 / – / 45 | 84 / – / 232 | 179 / 0 | 6 | 1083 |
| 1452436788 | S4 | PASS | 1 | – / – / 101 | – / – / 35 | – / – / 147 | 286 / 0 | 3 | 520 |
| 1452436788 | S4-R | PASS | 0 | – / – / – | – / – / – | – / – / – | 429 / 0 | 0 | 246 |
| 1883209505 | S1 | PASS | 3 | 0 / 0 / 0 | 49 / 48 / 42 | 49 / 48 / 175 | 0 / 0 | 3 | 1229 |
| 1883209505 | S2 | PASS | 1 | – / – / 132 | – / – / 48 | – / – / 175 | 286 / 0 | 0 | 455 |
| 1883209505 | S2-R | PASS | 0 | – / – / – | – / – / – | – / – / – | 429 / 0 | 0 | 247 |
| 1883209505 | S2-I | PASS | 2 | – / 80 / 35 | – / 82 / 45 | – / 82 / 179 | 145 / 0 | 1 | 732 |
| 1883209505 | S3 | PASS | 1 | – / – / 132 | – / – / 48 | – / – / 176 | 286 / 0 | 1 | 509 |
| 1883209505 | S4 | PASS | 0 | – / – / – | – / – / 35 | – / – / – | 429 / 0 | 0 | 299 |
| 1883209505 | S4-R | PASS | 1 | – / – / 70 | – / – / 72 | – / – / 72 | 291 / 0 | 3 | 524 |
| 497199041 | S1 | PASS | 3 | 0 / 0 / 0 | 46 / 48 / 42 | 46 / 48 / 175 | 0 / 0 | 4 | 1218 |
| 497199041 | S2 | PASS | 2 | 73 / – / 209 | 76 / – / 48 | 76 / – / 211 | 154 / 0 | 2 | 709 |
| 497199041 | S2-R | PASS | 1 | 73 / – / – | 76 / – / – | 76 / – / – | 286 / 0 | 1 | 475 |
| 497199041 | S2-I | PASS | 2 | – / 77 / 152 | – / 79 / 43 | – / 79 / 176 | 143 / 0 | 1 | 721 |
| 497199041 | S3 | PASS | 2 | 73 / – / 209 | 76 / – / 48 | 76 / – / 211 | 154 / 0 | 5 | 924 |
| 497199041 | S4 | PASS | 1 | – / 88 / 123 | – / – / 35 | – / – / 139 | 286 / 0 | 0 | 465 |
| 497199041 | S4-R | PASS | 0 | – / – / – | – / – / – | – / – / – | 429 / 0 | 0 | 247 |
| 3459030352 | S1 | PASS | 3 | 0 / 0 / 0 | 49 / 46 / 42 | 49 / 46 / 178 | 0 / 0 | 3 | 1236 |
| 3459030352 | S2 | PASS | 3 | 77 / 78 / 151 | 79 / 81 / 46 | 79 / 81 / 175 | 1 / 0 | 4 | 1162 |
| 3459030352 | S2-R | PASS | 2 | 77 / 78 / – | 79 / 81 / – | 79 / 81 / – | 144 / 0 | 4 | 756 |
| 3459030352 | S2-I | PASS | 2 | 83 / – / 129 | 85 / – / 47 | 85 / – / 176 | 148 / 0 | 2 | 693 |
| 3459030352 | S3 | PASS | 3 | 77 / 78 / 151 | 79 / 81 / 46 | 79 / 81 / 175 | 1 / 112 | 14 | 1682 |
| 3459030352 | S4 | PASS | 2 | 86 / – / 123 | 88 / – / 35 | 88 / – / 140 | 164 / 0 | 4 | 849 |
| 3459030352 | S4-R | PASS | 2 | 86 / – / 73 | 88 / – / 75 | 88 / – / 75 | 172 / 0 | 5 | 826 |

### S3 contention and adaptation

| Seed | C1 | A1 | A2 | Repeat | Unresolved | First evidence of each kind |
| --- | --- | --- | --- | --- | --- | --- |
| 2195683955 | 2 | 15 | 4 | 0 | 0 | C1 `s3_regrow288:0000000003:000002` matched `s3_regrow288:0000000003:000000`, `ella:p000001`<br>A1 `s3_regrow288:0000000003:000002`, `ella:p000001` → `ella:p000002`<br>A2 `fruit_01`, `s3_regrow288:0000000003:000000`, `mia:p000002` |
| 937154673 | 2 | 12 | 7 | 0 | 0 | C1 `s3_regrow288:0000000003:000002` matched `s3_regrow288:0000000003:000000`, `mia:p000001`<br>A1 `s3_regrow288:0000000003:000002`, `mia:p000001` → `mia:p000002`<br>A2 `fruit_05`, `s3_regrow288:0000000035:000006`, `ella:p000026` |
| 1452436788 | 2 | 28 | 25 | 0 | 0 | C1 `s3_regrow288:0000000003:000002` matched `s3_regrow288:0000000003:000000`, `ryan:p000001`<br>A1 `s3_regrow288:0000000003:000002`, `ryan:p000001` → `ryan:p000002`<br>A2 `fruit_05`, `s3_regrow288:0000000030:000007`, `ella:p000026` |
| 1883209505 | 2 | 19 | 11 | 0 | 0 | C1 `s3_regrow288:0000000003:000002` matched `s3_regrow288:0000000003:000000`, `ryan:p000001`<br>A1 `s3_regrow288:0000000003:000002`, `ryan:p000001` → `ryan:p000002`<br>A2 `fruit_01`, `s3_regrow288:0000000003:000000`, `mia:p000002` |
| 497199041 | 2 | 13 | 22 | 0 | 0 | C1 `s3_regrow288:0000000003:000002` matched `s3_regrow288:0000000003:000000`, `mia:p000001`<br>A1 `s3_regrow288:0000000003:000002`, `mia:p000001` → `mia:p000002`<br>A2 `fruit_01`, `s3_regrow288:0000000003:000000`, `ella:p000002` |
| 3459030352 | 2 | 22 | 25 | 0 | 0 | C1 `s3_regrow288:0000000003:000002` matched `s3_regrow288:0000000003:000000`, `ella:p000001`<br>A1 `s3_regrow288:0000000003:000002`, `ella:p000001` → `ella:p000002`<br>A2 `fruit_02`, `s3_regrow288:0000000194:000005`, `ella:p000099` |

### Paired results

Each cell reports treatment minus base as median [min, max]. A parenthesis reports counts favoring base / treatment / tied for directional metrics.

| Scalar | S4 decay 100 | S4 decay 120 | S5 cue |
| --- | --- | --- | --- |
| `deaths` | 1 [0, 1] (5/0/1) | 0 [-1, 1] (2/1/3) | 0 [-1, 1] (2/1/3) |
| `all_alive` | 0 [-1, 0] (1/0/5) | 0 [0, 0] (0/0/6) | — |
| `ticks_deprived` | 137.500000 [0, 143] (5/0/1) | 13.500000 [-138, 143] (4/1/1) | — |
| `ticks_deprived_water` | 137.500000 [0, 143] (5/0/1) | 13.500000 [-138, 143] (4/1/1) | 0 [-141, 147] (2/2/2) |
| `dedicated_water_trips` | 0 [-1, 0] (0/1/5) | 0.500000 [-3, 3] (3/1/2) | — |
| `water_only_visits` | -2.500000 [-5, 0] (0/4/2) | -1 [-10, 8] (2/3/1) | — |
| `gathers_completed` | -14 [-14, -3] (6/0/0) | 0 [-14, 12] (2/1/3) | — |
| `discovered` | -1 [-1, 0] (5/0/1) | 0 [-2, 1] (2/1/3) | -0.500000 [-1, 1] (3/1/2) |
| `access_drank` | -1 [-1, 0] (5/0/1) | 0 [-1, 1] (2/1/3) | 0 [-1, 1] (2/1/3) |
| `discovery_time_capped` | 829 [0, 965] (5/0/1) | -25 [-939, 1807] (2/3/1) | 414.500000 [-1026, 927] (4/2/0) |
| `spring_drink_time_capped` | 814 [0, 834] (5/0/1) | -30.500000 [-937, 870] (2/3/1) | — |
| `movement_ticks` | -214.500000 [-406, -75] | -43 [-274, 225] | — |
| `given_count` | 0 [0, 0] | 0 [-1, 0] | — |
| `given_qty` | 0 [0, 0] | 0 [-1, 0] | — |
| `received_count` | 0 [0, 0] | 0 [-1, 0] | — |
| `received_qty` | 0 [0, 0] | 0 [-1, 0] | — |
| `canteen_drinks` | -10.500000 [-11, -2] | -7.500000 [-13, -2] | — |
| `canteen_fills` | -4.500000 [-5, 0] | -3 [-6, 0] | — |
| `transfer_then_drink` | 0 [0, 0] | 0 [0, 0] | — |
| `hydration_cap_waste` | -1900 [-5900, 0] | 3820 [-9280, 11200] | — |
| `slot_full_incidents` | 0 [0, 0] | 0 [0, 0] | — |
| `access_found_not_drunk` | 0 [0, 0] | 0 [-1, 0] | 0 [-1, 0] |
| `access_not_found` | 1 [0, 1] | 0 [-1, 2] | 0.500000 [-1, 1] |

| Round | Base category | Drank | Found, no drink | Never found |
| --- | --- | --- | --- | --- |
| S4 decay 100 | drank | 4 | 0 | 5 |
| S4 decay 100 | found_not_drunk | 0 | 1 | 0 |
| S4 decay 100 | not_found | 0 | 0 | 8 |
| S4 decay 120 | drank | 3 | 0 | 2 |
| S4 decay 120 | found_not_drunk | 0 | 0 | 1 |
| S4 decay 120 | not_found | 1 | 0 | 11 |
| S5 cue | drank | 5 | 0 | 4 |
| S5 cue | found_not_drunk | 0 | 0 | 1 |
| S5 cue | not_found | 3 | 0 | 5 |

| Round | Seed | Deaths | Discovered | Drank from spring | Water-deprived ticks | Dedicated trips | Move ticks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S4 decay 100 | 2195683955 | 3 → 3 | 1 → 1 | 0 → 0 | 429 → 429 | 0 → 0 | 322 → 247 |
| S4 decay 100 | 937154673 | 2 → 3 | 1 → 0 | 1 → 0 | 286 → 429 | 0 → 0 | 456 → 246 |
| S4 decay 100 | 1452436788 | 1 → 2 | 2 → 1 | 2 → 1 | 179 → 290 | 1 → 1 | 685 → 466 |
| S4 decay 100 | 1883209505 | 2 → 3 | 1 → 0 | 1 → 0 | 286 → 429 | 0 → 0 | 455 → 247 |
| S4 decay 100 | 497199041 | 1 → 2 | 2 → 1 | 2 → 1 | 154 → 286 | 2 → 1 | 709 → 475 |
| S4 decay 100 | 3459030352 | 0 → 1 | 3 → 2 | 3 → 2 | 1 → 144 | 4 → 4 | 1162 → 756 |
| S4 decay 120 | 2195683955 | 2 → 2 | 1 → 1 | 1 → 1 | 286 → 305 | 0 → 2 | 461 → 506 |
| S4 decay 120 | 937154673 | 3 → 3 | 0 → 0 | 0 → 0 | 429 → 429 | 0 → 0 | 309 → 246 |
| S4 decay 120 | 1452436788 | 2 → 3 | 1 → 0 | 1 → 0 | 286 → 429 | 3 → 0 | 520 → 246 |
| S4 decay 120 | 1883209505 | 3 → 2 | 0 → 1 | 0 → 1 | 429 → 291 | 0 → 3 | 299 → 524 |
| S4 decay 120 | 497199041 | 2 → 3 | 2 → 0 | 1 → 0 | 286 → 429 | 0 → 0 | 465 → 247 |
| S4 decay 120 | 3459030352 | 1 → 1 | 2 → 2 | 2 → 2 | 164 → 172 | 4 → 5 | 849 → 826 |
| S5 cue | 2195683955 | 3 → 3 | 1 → 0 | 0 → 0 | 429 → 429 | 0 → 0 | 322 → 323 |
| S5 cue | 937154673 | 2 → 2 | 1 → 1 | 1 → 1 | 286 → 286 | 0 → 1 | 456 → 574 |
| S5 cue | 1452436788 | 1 → 2 | 2 → 1 | 2 → 1 | 179 → 286 | 1 → 0 | 685 → 487 |
| S5 cue | 1883209505 | 2 → 1 | 1 → 2 | 1 → 2 | 286 → 145 | 0 → 1 | 455 → 732 |
| S5 cue | 497199041 | 1 → 1 | 2 → 2 | 2 → 2 | 154 → 143 | 2 → 1 | 709 → 721 |
| S5 cue | 3459030352 | 0 → 1 | 3 → 2 | 3 → 2 | 1 → 148 | 4 → 2 | 1162 → 693 |

### Resident exposure and rates

Rates are counts per 1,000 exposure ticks, rounded to one decimal for the table. The aggregate JSON holds the tool's six-decimal rates per tick and arm totals. The last column reports raw slot-full counts while holding / without the canteen.

| Arm | Resident | Exposure | Water deprived | Food deprived | Dedicated trips | Move ticks | Gathers | Canteen drinks | Fills | Slot-full counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | ella | 6048 | 0.0 | 0.0 | 2.5 | 436.7 | 13.9 | 0.0 | 0.0 | 0 / 0 |
| S1 | mia | 6048 | 0.0 | 0.0 | 2.0 | 419.0 | 13.9 | 0.0 | 0.0 | 0 / 0 |
| S1 | ryan | 6048 | 0.0 | 0.0 | 0.0 | 373.2 | 13.9 | 10.9 | 5.0 | 0 / 0 |
| S2 | ella | 3690 | 117.3 | 0.0 | 1.6 | 340.7 | 11.7 | 0.0 | 0.0 | 0 / 0 |
| S2 | mia | 2118 | 338.1 | 0.0 | 0.5 | 376.8 | 9.0 | 0.0 | 0.0 | 0 / 0 |
| S2 | ryan | 5382 | 34.6 | 0.0 | 0.0 | 322.2 | 13.6 | 10.2 | 4.3 | 0 / 0 |
| S2-R | ella | 3690 | 117.3 | 0.0 | 1.4 | 321.4 | 11.7 | 0.0 | 0.0 | 0 / 0 |
| S2-R | mia | 2118 | 338.1 | 0.0 | 0.5 | 351.7 | 9.0 | 0.0 | 0.0 | 0 / 0 |
| S2-R | ryan | 1332 | 644.1 | 0.0 | 0.0 | 379.9 | 0.8 | 0.0 | 0.0 | 0 / 0 |
| S2-I | ella | 2118 | 339.9 | 0.0 | 0.9 | 343.7 | 7.6 | 0.0 | 0.0 | 0 / 0 |
| S2-I | mia | 3690 | 116.8 | 0.0 | 0.8 | 331.2 | 12.2 | 0.0 | 0.0 | 0 / 0 |
| S2-I | ryan | 4716 | 60.6 | 0.0 | 0.0 | 335.0 | 12.9 | 10.2 | 4.2 | 0 / 0 |
| S3 | ella | 3690 | 117.3 | 0.0 | 4.6 | 467.8 | 10.8 | 0.0 | 0.0 | 0 / 0 |
| S3 | mia | 2118 | 338.1 | 0.0 | 2.8 | 452.3 | 6.6 | 0.0 | 0.0 | 0 / 0 |
| S3 | ryan | 5382 | 34.6 | 20.8 | 0.6 | 427.2 | 12.6 | 10.2 | 4.3 | 0 / 0 |
| S4 | ella | 2053 | 358.5 | 0.0 | 1.5 | 398.0 | 8.8 | 0.0 | 0.0 | 0 / 0 |
| S4 | mia | 1254 | 684.2 | 0.0 | 0.0 | 383.6 | 5.6 | 0.0 | 0.0 | 0 / 0 |
| S4 | ryan | 4650 | 61.5 | 0.0 | 0.9 | 345.2 | 12.7 | 9.7 | 3.9 | 0 / 0 |
| S4-R | ella | 2053 | 358.5 | 0.0 | 1.0 | 384.8 | 8.8 | 0.0 | 0.0 | 0 / 0 |
| S4-R | mia | 1254 | 684.2 | 0.0 | 0.0 | 384.4 | 5.6 | 0.0 | 0.0 | 0 / 0 |
| S4-R | ryan | 3651 | 126.3 | 0.0 | 2.2 | 362.4 | 11.8 | 0.0 | 0.0 | 0 / 0 |

### Recorded re-execution and repeatability

| First-seed case | Exit | Events bytes | Decisions bytes | Final world SHA-256 |
| --- | --- | --- | --- | --- |
| `s2-default.orig.base.s2195683955` | 0 | equal | equal | `c19677e825b2e0bd88a8e8014e391711b4ecd3a0f44f5ddf4549b1ab03673f53` (equal) |
| `s2-default.orig.canteen-restricted.s2195683955` | 0 | equal | equal | `0735cdb73f73c45bfc263cc3361074683336338cf574bdcd610f4692febaf760` (equal) |
| `s4-decay120.orig.base.s2195683955` | 0 | equal | equal | `f1625346a1aaa2afccf6de4c821ce44ff121cfe4b79ba5808a71887baa271127` (equal) |
| `s4-decay120.orig.canteen-restricted.s2195683955` | 0 | equal | equal | `9f3996208ae91a0e45d705a8d7278417ab9e5fad38fb4bbfe794d87249d4cd57` (equal) |

The pilot and its S2/base matrix repeat use the same code, pin, map, world and policy identities. They match on all three result hashes and every P2-03 metric.

### Trace example from the original baseline

For seed `2195683955`, Ella and Ryan died without discovering the spring, at ticks
222 and 342. Ryan drank from his initial canteen at tick 44. Mia first observed the
spring at tick 82. Her `exploration_updated` event
`default_island_seed20261108_run01:0000000082:000018` records tile index `1958`, the
spring at (38,30). Decision `mia:p000072` targeted (38,31), adjacent to the spring.
The move failed with `EXHAUSTED` at
`default_island_seed20261108_run01:0000000083:000006`. Mia had zero spring-adjacent
frames and died at tick 222. This run shows both a discovery failure and a failure
to reach and drink after discovery. The latter includes a directly observed movement
failure. The inexhaustible spring rules out a water stock shortfall.

### Interpretation

- **S1 and S2.** The original baseline is technically valid in six of six cases and
  reproducible on the pilot repeat. S2 had one all-alive seed and nine deaths.
  Eight deaths followed no discovery and one followed discovery without a spring
  drink. All 18 S1 residents saw the spring at tick 0, drank from it and survived.
  S2 discovery, early frontier routes and survival produced six distinct behavioral
  signatures. Five of six differed from the modal signature, with a descriptive
  95% Wilson interval of 43.65%–96.99% under the registered-seed sampling assumption.
- **Scarcity and supply.** All six S3 seeds had C1, A1 and A2 evidence. Regrowth at
  288 instead of 144 increased food-deprived exposure by 112 resident-ticks and
  lowered completed gathers from 135 to 122. S3 had the same survival and
  spring-access counts as S2. A food-supply death requires a food-only terminal
  deprived run with a zero fruit ledger at every frame. The ledger includes tree
  stock, ground fruit and fruit carried by residents. No death in this matrix met
  that definition. The S3 evidence table records local depletion and competition.
- **Canteen at decay 100.** Ryan was the initial holder and stayed with the canteen.
  He survived five enabled runs and died at tick 342 in the remaining one after
  drinking the two initial servings. He died at tick 222 in all six restricted
  runs. Both arms had eight nonholder deaths. The enabled runs show 55 canteen
  drinks and 23 fills. Restriction added a median 137.5 water-deprived resident-ticks
  per seed. The dedicated-trip median difference was zero. The shorter exposure in
  the restricted arm limits interpretation of its lower total movement.
- **Canteen at decay 120.** Five residents survived with access enabled and four
  with restriction. The paired median difference in deaths was zero and restriction
  added a median 13.5 water-deprived resident-ticks. Dedicated-trip differences
  ranged from −3 to +3. The enabled arm recorded 45 drinks and 18 fills. Two
  transfers completed, from Ryan to Mia at seed `937154673`
  (`s4_decay120:0000000103:000004`) and from Ryan to Ella at seed `1452436788`
  (`s4_decay120:0000000125:000004`). Neither recipient completed a canteen drink
  inside the specified transfer window, so the experiment leaves delivery benefit
  unmeasured. The scenario tests exercise giving, filling and drinking.
  [Canteen scenario tests](../../../backend/tests/unit/test_rule_policy_scenarios.py#L349)
- **Cue use.** Ignoring the cue reduced the number discovering the spring from 10
  to 8. The paired median change in water deprivation was zero, with two seeds
  favoring each arm and two tied. Ignoring the cue increased deaths in two seeds,
  decreased deaths in one and tied in three. Keep the tested base cue setting in
  the M6 candidate.

## M6 recommendation

Submit the exact S1 spawn-only configuration for M6 consideration. Use the base
rule policy, hydration decay 100, fruit regrowth 144 ticks and the original island
tiles. The candidate's spawn coordinates come from the pinned S1 fixture.
[S1 fixture](../../../content/scenarios/s1-spring-visible/orig.toml)

| Proposed default field or paired outcome | S2 original | Tested S1 candidate |
| --- | --- | --- |
| Ella spawn | (12,32) | (33,32) |
| Ryan spawn | (13,32) | (34,32) |
| Mia spawn | (14,32) | (35,32) |
| §4-valid seeds | 6/6 | 6/6 |
| Seeds with all three alive at tick 1,008 | 1/6 | 6/6 |
| Residents alive at tick 1,008 | 9/18 | 18/18 |
| Discovered the spring / drank from it | 10 / 9 | 18 / 18 |
| Median first discovery / first spring drink, observed ticks | 82 / 175 | 0 / 49 |
| Water-deprived / food-deprived resident-ticks | 1,335 / 0 | 0 / 0 |

All six same-seed pairs use the same map and base policy. Five seeds gained
survivors under S1 and one tied. The all-alive fractions have descriptive 95% Wilson
intervals of 3.01%–56.35% for S2 and 60.97%–100% for S1. PD-05 is assessed separately
in P2-05 with the held-out seeds.

| Other single-factor test | Before → after | Recommendation |
| --- | --- | --- |
| S2 → S3, regrowth 144 → 288 | 9 → 9 alive, 0 → 112 food-deprived ticks, 7 → 26 dedicated water trips | Use 144 in the candidate. |
| S2 → S4, decay 100 → 120 | 9 → 5 alive, 1,335 → 1,880 water-deprived ticks | Use 100 in the candidate. |
| S2 → S2-R, restrict canteen | 9 → 4 alive, 1,335 → 2,007 water-deprived ticks | Use the enabled policy. |
| S2 → S2-I, ignore cue | 9 → 8 alive, 10 → 8 discoveries | Use the enabled policy. |

The proposed placement moves all three spawns 21 tiles east and makes the spring
visible at the start. This changes the opening travel route as well as discovery.
The owner must approve the configuration at M6 and separately approve these three
coordinates under PD-04. The tested S1 file supplies the pre-approval candidate.

## Reproduction

Use a checkout of the experiment commit `6412dc9b60b88809f33f845a96fc19dc87d1bed4`.
From the root, install the locked dependencies with `uv sync --directory backend --locked`.
Use fresh batch IDs when reproducing into an existing worktree. The batch tool records
exact simulation arguments, code and fixture commits, policy config, world and map hashes,
and all artifact hashes in `runs/p2/<batch-id>/manifests/<case-id>.json`.

```text
uv run --directory backend python ../scripts/p2_experiments.py batch --batch-id p2-04-pilot --seeds 2195683955 --case s2-default:orig:base
uv run --directory backend python ../scripts/p2_experiments.py batch --batch-id p2-04-dev-2195683955 --seeds 2195683955 --case s1-spring-visible:orig:base --case s2-default:orig:base --case s2-default:orig:canteen-restricted --case s2-default:orig:cue-ignored --case s3-regrow288:orig:base --case s4-decay120:orig:base --case s4-decay120:orig:canteen-restricted
```

Run the second command concurrently for the six seeds, replacing both the seed and
the numeric suffix of the batch ID each time. The batch command fixes the run length
at 1,008. Each batch writes `summary/cases.csv`, `summary/metrics/<case-id>.json`,
`summary/comparisons.json` and case logs. To regenerate a batch summary from the
retained artifacts, run
`uv run --directory backend python ../scripts/p2_experiments.py report --batch-id <batch-id>`.

To rebuild the six-seed paired summaries from the original runs, save the following
as `runs/rebuild-p2-04-pairs.py` and run
`uv run --directory backend python ../runs/rebuild-p2-04-pairs.py`. It uses P2-03's
artifact reader and comparison functions. If a case cannot be loaded, inspect the
batch's logs and validity report before computing a pair.

```python
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from p2_experiments import DEVELOPMENT_SEEDS, ROUNDS, load_case, metric_record
from p2_experiments import read_manifests, summarize_run_of
from living_island.analysis.compare import paired_report

seeds = DEVELOPMENT_SEEDS[:6]
arms = {}
for seed in seeds:
    batch = root / "runs/p2" / f"p2-04-dev-{seed}"
    for manifest in read_manifests(batch):
        assert manifest.seed == seed
        loaded = load_case(
            batch / manifest.run_dir,
            cli_exit_code=0,
            expected_policy_config_sha256=manifest.policy_config_sha256,
        )
        metric = metric_record(loaded)
        key = (manifest.scenario_id, manifest.policy_variant_id)
        arms.setdefault(key, {})[seed] = summarize_run_of(
            loaded, manifest.case_id, seed, metric["valid"], metric["death_categories"]
        )
for treatment, (scalars, scenarios) in ROUNDS.items():
    for scenario in sorted(scenarios):
        result = paired_report(
            arms.get((scenario, "base"), {}),
            arms.get((scenario, treatment), {}),
            scalars,
            expected_seeds=seeds,
        )
        print(json.dumps({"scenario": scenario, "treatment": treatment, **result}))
```

For the first seed, recorded re-execution uses the CLI command below. Repeat for
`s2-default.orig.canteen-restricted`, `s4-decay120.orig.base` and
`s4-decay120.orig.canteen-restricted`, preserving the seed suffix. Compare
`events.jsonl` and `decisions.jsonl` in binary mode and compare the
`final_world_sha256` field in both `decision-trace.json` manifests.

```text
uv run --directory backend python -m living_island reexecute --source-run ../runs/p2/p2-04-dev-2195683955/cases/s2-default.orig.base.s2195683955 --out ../runs/p2-04-execution/reexecutions/s2-default.orig.base.s2195683955
```
