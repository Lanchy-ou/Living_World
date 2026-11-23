"""DeepSeek Responses framing and the offline Flash-1017 upper bound."""

import json
from dataclasses import dataclass

from living_island.agents.llm import provider as p3

from .contracts import json_bytes

MODEL_WINDOW = 1_000_000
RESERVE = 8_000
WINDOW = MODEL_WINDOW - RESERVE
FRAMING_VERSION = "deepseek-responses-v2/0.1"
WORDING_VERSION = "pressure/0.1"
NOTICE = "You cannot clearly recall earlier parts of the day."


def part_tokens(text: str) -> int:
    """Standalone upper bound for inspection, not an additive share of the total."""
    return p3._plain_token_bound(text)


@dataclass(frozen=True)
class Wire:
    body: bytes
    counted: int


def frame(kind: str, instructions: str, schema: bytes, user: str) -> Wire:
    # schema is already canonical, so its key order also matches the provider's
    # spaced expansion of the object parsed from the serialized wire.
    shape = json.loads(schema)
    body = json_bytes(
        {
            "model": p3.MODEL_ID,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user},
            ],
            "reasoning": {"effort": "none"},
            "max_output_tokens": RESERVE,
            "stream": False,
            "tools": [],
            "tool_choice": "none",
            "text": {"format": {"type": "json_schema", "name": kind, "schema": shape}},
        }
    )
    # Same two text spans and five structural tokens as the certified P3
    # renderer. A part boundary within either span is not a tokenizer boundary.
    expanded = json.dumps(shape, ensure_ascii=False, separators=(", ", ": "))
    counted = 5 + part_tokens(instructions + p3._SCHEMA_PREFIX + expanded) + part_tokens(user)
    return Wire(body, counted)
