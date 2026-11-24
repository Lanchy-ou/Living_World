"""Calibrate the two stand-alone compat-v1 policies using the accepted EN-08 evidence."""

import argparse
from pathlib import Path

from ..receipts import file_digest
from .campaign import run
from .pins import find_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="1..4",
        help="number of independent case workers (default 1)",
    )
    parser.add_argument("--en08", type=Path, help="EN-08 acceptance-<revision> evidence directory")
    parser.add_argument(
        "--reuse",
        type=Path,
        action="append",
        default=[],
        help="previous calibration directory with verified arm recordings (repeatable)",
    )
    args = parser.parse_args()
    try:
        en08 = args.en08 or find_evidence(args.out.parent / "en08")
        receipt = run(args.out, en08, reuse=tuple(args.reuse), jobs=args.jobs)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    path = args.out / "receipt.json"
    print(f"{receipt.status}  {file_digest(path)}  {path}")
    if receipt.status != "equal":
        print(receipt.cases[-1].comparison.model_dump_json(indent=2))
        print(f"Missing cases: {list(receipt.missing_cases)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
