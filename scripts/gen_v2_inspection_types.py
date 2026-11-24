"""Regenerate the ia/0.1 browser schemas and TypeScript from the wire contract."""

import json
import shutil
import subprocess
from pathlib import Path

from living_island.contract.inspection_v2 import InspectionIndex, Shard
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUT = FRONTEND / "src/features/v2-inspection/generated"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("pnpm is required for the pinned TypeScript generator")
    for name, adapter in (
        ("index", TypeAdapter(InspectionIndex)),
        ("shard", TypeAdapter(Shard)),
    ):
        schema = adapter.json_schema()
        models = [schema, *schema.get("$defs", {}).values()]
        for model in models:
            # Pydantic dataclasses describe named fields without an extra policy.
            if "properties" in model:
                model["additionalProperties"] = False
                if (
                    "family" in model["properties"]
                    and "family" not in model["required"]
                ):
                    model["required"].append("family")
        schema["title"] = "InspectionIndex" if name == "index" else "InspectionShard"
        source = OUT / f"{name}.schema.json"
        source.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        subprocess.run(
            [
                pnpm,
                "--dir",
                str(FRONTEND),
                "exec",
                "json2ts",
                "--input",
                str(source),
                "--output",
                str(OUT / f"{name}.ts"),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
