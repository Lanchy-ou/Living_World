"""Verify the registered M13 D1 case or record its missing timing."""

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

from living_island.persistence._codec import PersistenceError

from . import publish


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true", help="never advance the simulation")
    args = parser.parse_args()
    try:
        result, path = publish(args.balance, args.out, verify_only=args.verify_only)
    except (
        KeyError,
        OSError,
        ValueError,
        PersistenceError,
        sqlite3.Error,
        subprocess.CalledProcessError,
    ) as error:
        print(f"D1 verification refused: {error}", file=sys.stderr)
        return 2
    print(f"D1 {result} {path.resolve()}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
