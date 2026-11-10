"""Command-line entry points for simulation, continuation and re-execution."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from living_island.agents.types import RuleParams
from living_island.persistence._codec import decode_model
from living_island.persistence.content import load_world_content
from living_island.persistence.replay import FrameSpool, export_replay
from living_island.persistence.scripts import load_script
from living_island.sim.runner import reexecute, resume, run
from living_island.world.content import build_world_content, map_bytes_from_rows

_POLICY_FLAGS = {"--policy", "--script", "--rule-canteen", "--rule-cue", "--rule-params"}


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
    parser = argparse.ArgumentParser(prog="python -m living_island", exit_on_error=False)
    commands = parser.add_subparsers(dest="command", required=True)
    fresh = commands.add_parser("run", allow_abbrev=False, exit_on_error=False)
    fresh.add_argument("--config", type=Path, required=True)
    fresh.add_argument("--ticks", type=_nonnegative, required=True)
    fresh.add_argument("--seed", type=_positive)
    fresh.add_argument("--policy", choices=("random", "scripted", "rule-based"), action="append")
    fresh.add_argument("--script", type=Path, action="append")
    fresh.add_argument("--rule-canteen", choices=("enabled", "restricted"), action="append")
    fresh.add_argument("--rule-cue", choices=("enabled", "ignored"), action="append")
    fresh.add_argument("--rule-params", type=Path, action="append")
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


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _parser()
    try:
        args, extra = parser.parse_known_args(argv)
    except argparse.ArgumentError as exc:
        if exc.argument_name in _POLICY_FLAGS:
            raise ValueError(str(exc)) from exc
        parser.error(str(exc))
    if extra:
        if any(
            token.split("=", 1)[0] in _POLICY_FLAGS or token.startswith("--rule-")
            for token in extra
        ):
            raise ValueError(f"invalid policy arguments for {args.command}: {' '.join(extra)}")
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    return args


def _run_policy(args: argparse.Namespace) -> tuple[Path | None, RuleParams | None]:
    for flag in sorted(_POLICY_FLAGS):
        values = getattr(args, flag[2:].replace("-", "_"))
        if values and len(values) > 1:
            raise ValueError(f"{flag} may be supplied only once")
    if args.policy is None:
        raise ValueError("--policy is required")
    policy = args.policy[0]
    script = args.script[0] if args.script else None
    if (policy == "scripted") != (script is not None):
        raise ValueError("--script is required for scripted and forbidden for other policies")

    switches = args.rule_canteen or args.rule_cue
    if policy != "rule-based":
        if args.rule_params or switches:
            raise ValueError("rule flags require --policy rule-based")
        return script, None
    if args.rule_params:
        if switches:
            raise ValueError("--rule-params cannot be combined with rule switches")
        path = args.rule_params[0]
        return None, decode_model(path.read_bytes(), RuleParams, path, canonical=False)
    return None, RuleParams(
        rule_params_version="0.1",
        canteen_use=args.rule_canteen[0] if args.rule_canteen else "enabled",
        cue_use=args.rule_cue[0] if args.rule_cue else "enabled",
        fruit_carry_target=2,
        failed_target_retry_ticks=36,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.export_replay and args.command == "resume":
            raise ValueError("resume cannot export a full replay; use reexecute --export-replay")
        observer = FrameSpool(args.out) if args.export_replay else None
        match args.command:
            case "run":
                script_path, rule_params = _run_policy(args)
                content = load_world_content(args.config)
                if args.seed is not None:
                    config = content.config.model_dump()
                    config["meta"]["seed"] = args.seed
                    content = build_world_content(config, map_bytes_from_rows(content.map_rows))
                script = (
                    load_script(script_path, content.config) if script_path is not None else None
                )
                result = run(
                    content,
                    args.ticks,
                    args.out,
                    script=script,
                    rule_params=rule_params,
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
