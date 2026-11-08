"""Export the pydantic contract to JSON Schema and generate TypeScript types.

Run from the repo root:
    uv run --directory backend python ../scripts/gen_types.py
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from living_island import contract

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "frontend"
OUT_DIR = FRONTEND / "src" / "api" / "generated"
SCHEMA_PATH = OUT_DIR / "contract.schema.json"


def build_schema() -> dict[str, object]:
    models: list[type[BaseModel]] = [getattr(contract, name) for name in contract.__all__]
    _, defs_schema = models_json_schema([(m, "validation") for m in models], title="Contract")
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Contract",
        "type": "object",
        "additionalProperties": False,
        "properties": {m.__name__: {"$ref": f"#/$defs/{m.__name__}"} for m in models},
        "$defs": defs_schema["$defs"],
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"
    with SCHEMA_PATH.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        print("pnpm not found on PATH", file=sys.stderr)
        return 1
    subprocess.run([pnpm, "--dir", str(FRONTEND), "run", "gen:types"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
