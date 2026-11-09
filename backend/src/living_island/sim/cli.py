"""Command-line entry points for simulation, continuation and re-execution."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from living_island.persistence.content import load_world_content
from living_island.persistence.replay import FrameSpool, export_replay
from living_island.persistence.scripts import load_script
from living_island.sim.runner import reexecute, resume, run
from living_island.world.content import build_world_content, map_bytes_from_rows


def _nonnegative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return number


def _positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m living_island")
    commands = parser.add_subparsers(dest="command", required=True)
    fresh = commands.add_parser("run")
    fresh.add_argument("--config", type=Path, required=True)
    fresh.add_argument("--ticks", type=_nonnegative, required=True)
    fresh.add_argument("--seed", type=_positive)
    fresh.add_argument("--policy", choices=("random", "scripted"), required=True)
    fresh.add_argument("--script", type=Path)
    fresh.add_argument("--checkpoint-every", type=_positive)
    continuation = commands.add_parser("resume")
    continuation.add_argument("--checkpoint", type=Path, required=True)
    continuation.add_argument("--source-run", type=Path, required=True)
    continuation.add_argument("--ticks", type=_nonnegative, required=True)
    replay = commands.add_parser("reexecute")
    replay.add_argument("--source-run", type=Path, required=True)
    for command in (fresh, continuation, replay):
        command.add_argument("--out", type=Path, required=True)
        command.add_argument("--export-replay", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.export_replay and args.command == "resume":
            raise ValueError("resume cannot export a full replay; use reexecute --export-replay")
        observer = FrameSpool(args.out) if args.export_replay else None
        match args.command:
            case "run":
                if (args.policy == "scripted") != (args.script is not None):
                    raise ValueError("--script is required for scripted and forbidden for random")
                content = load_world_content(args.config)
                if args.seed is not None:
                    config = content.config.model_dump()
                    config["meta"]["seed"] = args.seed
                    content = build_world_content(config, map_bytes_from_rows(content.map_rows))
                script = (
                    load_script(args.script, content.config) if args.script is not None else None
                )
                result = run(
                    content,
                    args.ticks,
                    args.out,
                    script=script,
                    checkpoint_every=args.checkpoint_every,
                    on_boundary_committed=observer,
                )
            case "resume":
                result = resume(args.checkpoint, args.source_run, args.ticks, args.out)
            case "reexecute":
                result = reexecute(args.source_run, args.out, on_boundary_committed=observer)
            case _:
                raise AssertionError(f"unexpected command {args.command}")
        if observer is not None:
            export_replay(result.output)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        for note in getattr(exc, "__notes__", ()):
            print(note, file=sys.stderr)
        return 1
    world = result.world
    print(
        f"run_id={world.run_id} tick={world.tick} events={world.event_log_cursor} "
        f"decisions={result.decision_record_cursor} world_sha256={result.world_sha256}"
    )
    return 0
