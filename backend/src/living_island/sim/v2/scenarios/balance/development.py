"""Recalibrate and run the approved development round under one host lock."""

import argparse
import subprocess
from hashlib import sha256
from pathlib import Path

from living_island.sim.v2 import cli

from ..calibration.campaign import CalibrationReceipt
from .campaign import campaign, heavy_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en08", required=True, type=Path, help="accepted equivalence directory")
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=2)
    parser.add_argument(
        "--calibration-checkout",
        type=Path,
        default=cli.ROOT,
        help="source checkout pinned by existing calibration case receipts",
    )
    args = parser.parse_args()
    equivalence = args.en08.resolve()
    runs = cli.ROOT / "runs" / "m13"
    calibration = runs / "calibration-en10"
    development = runs / "balance-dev"
    with heavy_lock():
        print(f"Starting calibration against {equivalence}", flush=True)
        subprocess.run(
            [
                "uv",
                "run",
                "--directory",
                "backend",
                "python",
                "-m",
                "living_island.sim.v2.scenarios.calibration",
                "--out",
                str(calibration),
                "--en08",
                str(equivalence),
                "--jobs",
                str(args.jobs),
            ],
            cwd=args.calibration_checkout.resolve(),
            check=True,
        )
        raw = (calibration / "receipt.json").read_bytes()
        receipt = CalibrationReceipt.model_validate_json(raw)
        if receipt.status != "equal" or receipt.missing_cases:
            raise ValueError(f"calibration {receipt.status}, missing cases {receipt.missing_cases}")
        digest = sha256(raw).hexdigest()
        print(f"Starting development with calibration SHA-256 {digest}", flush=True)
        result = campaign(
            "development",
            calibration,
            digest,
            development,
            args.jobs,
            equivalence_revision=equivalence.name.removeprefix("acceptance-"),
            inspect=False,
            reuse=(),
        )
        print(f"{result['verdict']} {development / 'report.json'}", flush=True)
        return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
