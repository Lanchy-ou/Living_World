"""Generate or resume the approved scripted week."""

import argparse
import json
from pathlib import Path

from living_island.sim.v2.scenarios.receipts import file_digest

from . import run, starter
from .script import schedules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    case = starter()
    path = run(args.out, case, schedules(case.pack))
    status = json.loads(path.read_bytes())["status"]
    print(f"{status} {path} sha256={file_digest(path)}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
