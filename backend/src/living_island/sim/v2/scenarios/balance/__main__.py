"""Run a CT-13 round or rebuild its report from verified case receipts."""

import argparse
import os
import platform
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .campaign import campaign


@contextmanager
def heavy_lock(path: Path) -> Iterator[None]:
    with path.open("x", encoding="utf-8") as lock:
        try:
            lock.write(
                f"P3.5-CT-06 {datetime.now(UTC).isoformat()} "
                f"pid={os.getpid()} host={platform.node()}\n"
            )
            lock.flush()
            yield
        finally:
            lock.close()
            path.unlink()


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
    lock = Path("C:/Temp") if os.name == "nt" else Path(tempfile.gettempdir())
    with heavy_lock(lock / "li-heavy.lock"):
        result = campaign(
            args.stage,
            args.calibration,
            args.receipt_sha256,
            args.out,
            args.jobs,
            inspect=args.report_only,
            reuse=tuple(args.reuse),
        )
    print(f"{result['verdict']} {args.out / 'report.json'}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
