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
from living_island.world.facts import PAYLOAD_MODEL_BY_TYPE

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "frontend"
OUT_DIR = FRONTEND / "src" / "api" / "generated"
SCHEMA_PATH = OUT_DIR / "contract.schema.json"
REPLAY_SCHEMA_PATH = OUT_DIR / "replay.schema.json"
REPLAY_TYPES_PATH = OUT_DIR / "replay.ts"
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


def render_discriminated_replay_types(source: str) -> str:
    """Refine the TypeScript event union using the same pairs as the Python validator."""
    event_declaration = "export interface WorldEvent {"
    if source.count(event_declaration) != 1:
        raise ValueError("Expected one json-schema-to-typescript WorldEvent declaration")

    source = source.replace(event_declaration, "interface WorldEventShape {")
    payload_mapping = "\n".join(
        f"  {json.dumps(event_type)}: {model.__name__};"
        for event_type, model in PAYLOAD_MODEL_BY_TYPE.items()
    )
    return f"""{source.rstrip()}

type EventPayloadByType = {{
{payload_mapping}
}};

export type WorldEvent = {{
  [EventType in WorldEventShape["type"]]: Omit<WorldEventShape, "type" | "payload"> & {{
    type: EventType;
    payload: EventPayloadByType[EventType];
  }};
}}[WorldEventShape["type"]];
"""


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
    source = REPLAY_TYPES_PATH.read_text(encoding="utf-8")
    write_text(REPLAY_TYPES_PATH, render_discriminated_replay_types(source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
