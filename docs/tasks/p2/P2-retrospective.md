# P2 retrospective

## Delivery

| Stage | Evidence |
| --- | --- |
| M5 and CR-004 | Rule-policy inputs, state, experiment parameters and restore provenance were frozen. [P2-00](P2-00.md) |
| Runtime wiring | The CLI and runtime gained `rule-based-v0` with the same world-owned action boundary. P1 serialization and recorded execution were checked against their historical artifacts. [P2-01](P2-01.md) |
| Survival policy | The rule policy implements survival, exploration and canteen actions from resident-local perception. The development suite exercised S1 on 20 seeds. [P2-02](P2-02.md) |
| Experiment tooling | The P2-03 CLI records pinned inputs, verifies eight technical checks and derives metrics from run artifacts. [P2-03](P2-03.md) |
| MF | The owner accepted the pixel-art viewer on the existing replay contract. [P2-F1](P2-F1.md) |
| M6 | The owner approved the S1 spawn positions after the six-seed comparison. The P2-04 branch recorded the config and kept the frozen P1 inputs for regression. [P2-04](P2-04.md) |
| M7 | The owner viewed the seven-day replay through tick 1,008 and signed off on 2026-11-11. [P2-05](P2-05.md) |

All 20 held-out cases passed the technical and survival lines with 60 survivors.
The sample's 95% Wilson lower limit is 83.8875%. The first seed reproduced its
events, decisions and final world from both a living tick-144 checkpoint and
recorded re-execution. The owner's M7 sign-off completes P2.

## What the experiments resolved

- In the six selected development pairs, S2 finished with nine survivors and S1 with
  eighteen. The original blind start produced eight deaths before discovery and one
  after discovery without a spring drink. The S1 spawn change altered both visibility
  and travel. S5 held the spawns fixed for the cue comparison.
- S3 recorded contention and adaptation in every selected seed. Regrowth at 288 ticks
  produced 112 food-deprived resident-ticks and no death that met the food-ledger
  supply-shortfall definition. The owner approved regrowth at 144 for M6.
- The decay-100 canteen comparison favored enabled for survival and water deprivation
  in the measured development sample. The decay-120 result was smaller. Both rounds
  account for living exposure and holder status. Two transfers completed at decay 120
  with zero transfers followed by a recipient drink in the specified window.
- The early-death S2 pilot took 70.7 seconds. The six parallel seven-case batches took
  2,589.8 seconds wall time. The different resident exposure and action volumes make
  a single pilot a weak estimate for a mixed matrix. [Detailed experiment results](P2-04-report.md)
- M6 changed assumptions in nine tests about where residents start or what they can
  see. The frozen P1 input fixture preserves the original blind-map comparisons
  and reproduced the M4 hashes. The M6 integration test covers the new default
  explicitly. [M6 closeout](P2-04.md#m6-closeout-handoff)

## Carry forward to P3

- Use `rule-based-v0` with `base` parameters and M6 content pin `7c13d78` as the
  control and fallback. Record the code revision, canonical policy configuration
  hash, seed and content pin for every case. [Baseline identity](P2-05.md)
- Keep objective event and decision records as the evidence boundary for later
  comparisons. The P2 analysis uses resident exposure, access timing and the fruit
  ledger to explain outcomes that final survival alone cannot distinguish.
- Keep the 1,008-tick acceptance matrix in explicit experiment runs. Default CI
  exercises the M6 replay lifecycle with the 16-tick integration test and uses the
  frozen P1 fixture for the historical artifact regression.
