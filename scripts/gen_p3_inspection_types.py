"""Generate only the optional P3 inspection schemas and TypeScript DTOs."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

from living_island.contract.p3_inspection import (
    DecisionInspection,
    P3InspectionIndex,
    ResidentInspection,
)
from living_island.contract.p3_save import DecisionTraceP3, TrialRegistration

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/src/p3/generated"
MODELS: dict[str, type[BaseModel]] = {
    "index": P3InspectionIndex,
    "decision": DecisionInspection,
    "sample": ResidentInspection,
    "trace": DecisionTraceP3,
    "registration": TrialRegistration,
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(mode="validation"),
        }
        (OUT / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("pnpm is required for the pinned TypeScript generator")
    subprocess.run([pnpm, "--dir", str(ROOT / "frontend"), "run", "gen:p3-types"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
