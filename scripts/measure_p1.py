"""Time the documented P1 CLI walkthrough and record its output sizes and counts."""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
TICKS = 1008
SPLIT = 144


def measure(arguments: list[str], directory: Path) -> dict[str, int | float | str]:
    command = ["uv", "run", "--directory", "backend", "python", "-m", "living_island", *arguments]
    print(" ".join(command), flush=True)
    start = perf_counter()
    subprocess.run(command, cwd=ROOT, check=True)
    seconds = perf_counter() - start
    return {
        "seconds": round(seconds, 3),
        "events": (directory / "events.jsonl").read_bytes().count(b"\n"),
        "decisions": (directory / "decisions.jsonl").read_bytes().count(b"\n"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("runs/p1-measurements"))
    args = parser.parse_args()
    runs = (ROOT / "runs").resolve()
    directory = (ROOT / args.out).resolve()
    if directory == runs or not directory.is_relative_to(runs):
        parser.error("--out must be a new directory under runs/")
    directory.mkdir(parents=True)
    relative = (Path("..") / directory.relative_to(ROOT)).as_posix()
    original, continuation, recorded = (
        directory / name for name in ("original", "continuation", "recorded")
    )
    original_path = f"{relative}/original"

    results = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "final_tick": TICKS,
        "resume_from_tick": SPLIT,
        "run": measure(
            [
                "run",
                "--config",
                "../content/worlds/default.toml",
                "--ticks",
                str(TICKS),
                "--policy",
                "random",
                "--checkpoint-every",
                str(SPLIT),
                "--out",
                original_path,
                "--export-replay",
            ],
            original,
        ),
        "resume": measure(
            [
                "resume",
                "--checkpoint",
                f"{original_path}/checkpoint-{SPLIT:010d}.json",
                "--source-run",
                original_path,
                "--ticks",
                str(TICKS - SPLIT),
                "--out",
                f"{relative}/continuation",
            ],
            continuation,
        ),
        "reexecute": measure(
            [
                "reexecute",
                "--source-run",
                original_path,
                "--out",
                f"{relative}/recorded",
                "--export-replay",
            ],
            recorded,
        ),
        "replay_bytes": (recorded / "replay.json").stat().st_size,
    }
    report = json.dumps(results, indent=2) + "\n"
    (directory / "measurements.json").write_text(report, encoding="utf-8", newline="\n")
    print(report, end="")


if __name__ == "__main__":
    main()
