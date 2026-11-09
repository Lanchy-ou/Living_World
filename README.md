# Living Island

Living Island runs a deterministic 2D island world. Residents propose actions through a
policy interface, and the world validates and resolves them. The P1 CLI runs random and
scripted policies, saves checkpoints, and re-executes recorded decisions. The offline viewer
loads exported replays for inspection. P1 is complete: milestone M4 was signed off by the
project owner on 2026-11-09.

- [Product design](docs/product/living-island-v0.1-design.md)
- [Specifications](docs/spec/)
- [Architecture decisions](docs/adr/)
- [P1 integration and acceptance](docs/tasks/p1/P1-09.md)
- [Development checks](AGENTS.md)

## Prerequisites

Use Python 3.13 with [uv](https://docs.astral.sh/uv/), Node.js 24, and pnpm 10.34.9.
Run the commands from the repository root.

```sh
uv sync --directory backend
pnpm --dir frontend install
```

## Run, resume and re-execute

Use new output directories when repeating the walkthrough. The first command runs the
default world for seven game days and saves every 144 ticks. The second resumes from
tick 144 for 864 more ticks. The third re-executes the original run from tick zero using
its recorded decisions.

```sh
uv run --directory backend python -m living_island run --config ../content/worlds/default.toml --ticks 1008 --policy random --checkpoint-every 144 --out ../runs/p1-demo/original --export-replay
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

Open [the local viewer](http://127.0.0.1:5177/) and choose
`runs/p1-demo/recorded/replay.json` in the replay file picker. Enter 1008 in the tick
field or use the last-tick button. Select a resident to inspect conditions, inventory and
current action. Use the event filters to inspect failures and select an event to jump to
its tick.

Run `uv run --directory backend python ../scripts/measure_p1.py` to repeat the backend
measurements under `runs/p1-measurements/`. Pass `--out runs/<new-name>` for another sample.
