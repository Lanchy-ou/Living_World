"""Run a CT-13 round or rebuild its report from verified case receipts."""

import argparse
from pathlib import Path

from .campaign import campaign, heavy_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("development", "acceptance"), required=True)
    parser.add_argument(
        "--calibration",
        type=Path,
        required=True,
        help="directory containing the reviewed receipt.json",
    )
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument(
        "--equivalence-revision", required=True, help="accepted equivalence commit SHA"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=1)
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument(
        "--reuse",
        action="append",
        type=Path,
        default=[],
        help="prior round with unchanged case inputs",
    )
    args = parser.parse_args()
    with heavy_lock():
        result = campaign(
            args.stage,
            args.calibration,
            args.receipt_sha256,
            args.out,
            args.jobs,
            equivalence_revision=args.equivalence_revision,
            inspect=args.report_only,
            reuse=tuple(args.reuse),
        )
    print(f"{result['verdict']} {args.out / 'report.json'}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
