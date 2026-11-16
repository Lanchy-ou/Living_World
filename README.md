# Living Island

Living Island runs a deterministic 2D island world. Residents propose actions through a
policy interface, and the world validates and resolves them. The CLI runs random, scripted
and rule-based policies, saves checkpoints, and re-executes recorded decisions. The offline
viewer loads exported replays for inspection. M4 signed off P1 on 2026-11-09. The
M6 configuration passed P2's technical acceptance on all 20 held-out seeds, with all
three residents alive at tick 1,008 in every run. The owner viewed the replay
through tick 1,008 and signed off M7 on 2026-11-11. P2 is complete.

- [Product design](docs/product/living-island-v0.1-design.md)
- [Specifications](docs/spec/)
- [Architecture decisions](docs/adr/)
- [P1 integration and acceptance](docs/tasks/p1/P1-09.md)
- [P2 comparison experiments](docs/tasks/p2/P2-04-report.md)
- [P2 acceptance and M7 evidence](docs/tasks/p2/P2-05.md)
- [Development checks](AGENTS.md)

## Current phase and entry points

P3 is closed as a delivered resident-agent foundation under the owner's
2026-11-16 scope decision. P3-06 offline isolation/interaction proofs and P3-07
reporting, character inspection and decision-debug features are included.
Long-duration proof, new live multi-resident evaluation and full original M10
acceptance are deferred, not passed. See the [closeout and P3.5 handoff](docs/tasks/p3/P3-closeout.md)
for retained evidence, unmerged follow-ups and known limits.

- [P3 implementation plan](docs/plans/p3-implementation-plan-v0.1.md)
- P3 specifications for [resident experience](docs/spec/resident-experience-v0.1.md),
  [resident cognition](docs/spec/resident-cognition-v0.1.md),
  [LLM decisions and recovery](docs/spec/llm-decision-v0.1.md), and
  [evaluation and inspection](docs/spec/p3-evaluation-v0.1.md)
- [M9 acceptance and evidence](docs/tasks/p3/M9-evidence.md)

## Prerequisites

Use Python 3.13 with [uv](https://docs.astral.sh/uv/), Node.js 24, and pnpm 10.34.9.
Run the commands from the repository root.

```sh
uv sync --directory backend --locked
pnpm --dir frontend install --frozen-lockfile
```

## P1 reference walkthrough

Use new output directories when repeating the walkthrough. The first command runs the
frozen P1 world for seven game days and saves every 144 ticks. The second resumes from
tick 144 for 864 more ticks. The third re-executes the original run from tick zero using
its recorded decisions.

```sh
uv run --directory backend python -m living_island run --config tests/fixtures/p1_default/default.toml --ticks 1008 --policy random --checkpoint-every 144 --out ../runs/p1-demo/original --export-replay
uv run --directory backend python -m living_island resume --checkpoint ../runs/p1-demo/original/checkpoint-0000000144.json --source-run ../runs/p1-demo/original --ticks 864 --out ../runs/p1-demo/continuation
uv run --directory backend python -m living_island reexecute --source-run ../runs/p1-demo/original --out ../runs/p1-demo/recorded --export-replay
```

The CLI runs from the backend directory when invoked with `uv run --directory backend`.
The `../runs/` arguments therefore write to the repository's ignored `runs/` directory.
Full runs store the retained config and map, checkpoints, event and decision logs, and the
completion manifest. Resume writes the continuation logs and a final checkpoint to its own
directory. Use a full run as the source for `reexecute --export-replay`. Export writes
`frames.jsonl` and `replay.json` alongside the full run's other outputs.

## Inspect the replay

```sh
pnpm --dir frontend dev --host 127.0.0.1 --port 5177 --strictPort
```

Open [the local viewer](http://127.0.0.1:5177/), choose **Open replay…** and pick
`runs/p1-demo/recorded/replay.json`, or drop the file on the page. The viewer shows the island
as pixel art drawn from the replay (design: `docs/spec/frontend-design-v0.1.md`).

- Drag to pan; scroll, pinch or use the `−` / `+` buttons to zoom; **View entire island**
  shows the whole map again.
- Press play, or enter 1008 in the tick field (shown in windows wider than 1180 px), or use
  the last-tick button. Speeds are 1 to 16 ticks per second.
- Click a resident (on the map or in the list at the top left) to open its panel with the
  recorded action, conditions and inventory. This does not move the camera or pause playback.
- **Events**, **Resources** and **Legend** open the detail drawer. Use the event filters to
  inspect failures and select an event to jump to its tick and see its raw JSON.

For a run in which residents survive longer, export a rule-based replay and open it the same
way:

```sh
uv run --directory backend python -m living_island run --config ../content/worlds/default.toml --ticks 1008 --policy rule-based --out ../runs/rule-demo --export-replay
```

At the historical M4 commit `6d90824`, run
`uv run --directory backend python ../scripts/measure_p1.py` to repeat the original
performance measurements.

## P2 acceptance and P3 baseline

The full P2 acceptance batch is a separate experiment. The default backend suite includes
a 16-tick M6 integration check for checkpoint resume and recorded re-execution.

```sh
uv run --directory backend python ../scripts/p2_experiments.py batch --batch-id p2-05-accept-all --seed-list acceptance --case s2-default:m6:base
```

Each case writes a replay to `runs/p2/<batch-id>/cases/<case-id>/replay.json`. Open the
M7 replay listed in the task card, then use **Last tick** to inspect tick 1,008.
[M7 evidence](docs/tasks/p2/P2-05.md)

For P3 comparisons and fallback, use the frozen `rule-based-v0` baseline from
`a22360d0ef4c39f08c887d463c7576022873c605`, with the M6 content pin
`7c13d78ffd7d89006f6008c8a09f37ae97c253db`. The `base` parameters are version
`0.1`, canteen enabled, cue enabled, fruit carry target 2 and failed-target retry
36 ticks. Keep the seed, content pin and policy configuration hash in each comparison
manifest.

## P3 offline evaluation and inspection

`scripts/p3_experiments.py` reads completed, retained P3 records. It does not run
live models, load credentials or open the live allocation authority. Use fresh
output directories and supply every required ancestor checkpoint for a continued
run with repeated `--ancestor` arguments. The source run is never rewritten.

For an existing completed source run and its exact exported replay:

```sh
uv run --directory backend python ../scripts/p3_experiments.py inspect --source-run ../runs/p3/completed-case --replay ../runs/p3/completed-case/replay.json --out ../runs/p3/completed-case-inspection --recorded-out ../runs/p3/completed-case-recorded
```

Replace the example paths with retained artifacts. Inspection writes an independent
versioned index, decision/sample shards, exact trace and canonical registration.
The optional recorded proof uses raising provider and authority sentinels. A missing
boundary, wrong identity or damaged committed reference refuses export.

The `validate` and `report` commands take `--registration` and `--receipts`; `report`
also requires a fresh `--out` directory. Reports keep missing cases and invalid pairs
visible, separate technical checks from descriptive behavior, and retain exact
fractions and unknown usage. Allocation arithmetic deduplicates copied reservations;
it does not turn a supplied allocation list into proof of a spending grant. Missing
immutable issuance evidence remains an explicit failure, without consulting a live
ledger. These offline commands do not perform M10 owner acceptance.

For an explicitly supplied offline evidence archive, `validate` and `report` can
instead read a closed manifest covering multiple registered runs and archived
issuance snapshots:

```sh
uv run --directory backend python ../scripts/p3_experiments.py report --evidence-manifest ../runs/p3/archived-evidence/manifest.json --trusted-owner-evidence-sha256 OWNER_APPROVED_ARCHIVE_SHA256 --out ../runs/p3/archive-report
```

Replace `OWNER_APPROVED_ARCHIVE_SHA256` with the independently supplied,
owner-approved SHA-256 of the complete canonical manifest. Computing a digest
from an untrusted archive does not approve that archive. Every member is explicitly
located and hashed inside the archive; embedded original authority paths are
compared as identity strings and are never followed. The report verifies the
supplied historical snapshot, not today's available budget, and creates no grant.
Missing expected allocations retain an unknown total and a separate known charge
subtotal. Missing historical run files cannot be reconstructed from receipts.
The current registration 0.1 multi-seed limitation still applies; multiple archive
members are not a way to split or bypass a required development/acceptance matrix.

The P3 schemas and types are generated separately:

```sh
uv run --directory backend python ../scripts/gen_p3_inspection_types.py
```

Committed local browser examples are listed in
`backend/tests/fixtures/p3/evaluation/ui-manifest.json` and `ui-edge-manifest.json`.
Each identifies its replay, complete inspection-file set, per-file hashes and
retained source archive. They are synthetic offline fixtures, not real-model trial
results. Existing P1/P2 replay imports require no inspection files.

Load the exported replay in the viewer, choose **Open inspection…**, then select
all JSON files in the corresponding inspection directory together: `index.json`,
the trace and registration, and every decision/sample shard. After verification,
select a resident and seek to a tick to inspect identity, goals, recent experience
and linked evidence. **Decision debug** shows the committed decision's delivered
context, provider projection, retrieval manifest, attempts, errors and usage.

The panels label the resident, selected tick and last observed cognition. A tick
without a new decision keeps the last committed decision visible; stopped or
older cognition is marked explicitly. Source links navigate to the recorded
decision or event. Missing usage and cost remain **Unknown**. Imported speech and
other text display literally. Legacy replays remain usable without inspection
files.
