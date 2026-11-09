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
from living_island.contract.replay import ReplayBundle

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "frontend"
OUT_DIR = FRONTEND / "src" / "api" / "generated"
SCHEMA_PATH = OUT_DIR / "contract.schema.json"
REPLAY_SCHEMA_PATH = OUT_DIR / "replay.schema.json"
JSON_SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"


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


def build_replay_schema() -> dict[str, object]:
    """Standalone JSON Schema 2020-12 rooted at ``ReplayBundle`` (replay-frontend §2.3).

    Not wrapped in the legacy ``Contract`` object: a raw bundle validates directly and a
    Contract-shaped input is refused.
    """
    schema = ReplayBundle.model_json_schema(mode="validation")
    return {"$schema": JSON_SCHEMA_2020_12, **schema}


def render_schema(schema: dict[str, object], *, sort_keys: bool = False) -> str:
    return json.dumps(schema, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"


def write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Legacy combined output: same bytes as before.
    write_text(SCHEMA_PATH, render_schema(build_schema(), sort_keys=True))
    # The replay schema keeps pydantic's field order so the generated TS follows the spec order.
    write_text(REPLAY_SCHEMA_PATH, render_schema(build_replay_schema()))

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        print("pnpm not found on PATH", file=sys.stderr)
        return 1
    subprocess.run([pnpm, "--dir", str(FRONTEND), "run", "gen:types"], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
