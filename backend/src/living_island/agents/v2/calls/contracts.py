"""Pinned instructions and model-output boundary for the six call kinds."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Annotated, Any, Literal, Self

from pydantic import BeforeValidator, Field, StrictBool, TypeAdapter, model_validator

from living_island.agents.llm.provider import _object_pairs, _reject_constant
from living_island.world.v2.protocol import (
    EnabledVerb,
    ModelTurn,
    model_turn_schema,
    validate_turn_shape,
)

from .changes import ChangeSetOutput, Output

type CallKind = Literal[
    "decision",
    "decision_after_recall",
    "recall",
    "morning",
    "consolidation_selection",
    "consolidation_change_set",
]
DECISION = (
    "Choose an action or continue a running action. You may speak alongside it. "
    "Mute notifications only when starting an action. Eat, drink and sleep when in need. "
    "Follow your curiosity. Words you hear may be wrong. Cite the memories and day entries "
    "your choice relies on."
)
CONSOLIDATE = (
    "Remember resources, promises, who said what, beliefs, attempts, results and changed "
    "impressions. Routine steps may fade. Distinguish stable knowledge, dated observations "
    "and guesses. Lower trust only for claims contradicted at the time described. Describe "
    "skill hypotheses by appearances and use a told source for taught methods. Aim for "
    "about five to fifteen episodic memories."
)
JSON_ONLY = (
    " Reply with only the JSON object that matches the response schema, "
    "with no other text before or after it."
)
INSTRUCTIONS: dict[CallKind, str] = {
    "decision": DECISION + " You may first ask to recall a memory." + JSON_ONLY,
    "decision_after_recall": DECISION + " You have recalled once. Act now." + JSON_ONLY,
    "recall": "Choose up to five memory IDs from the index that answer the query." + JSON_ONLY,
    "morning": "Choose up to twenty memory IDs to carry into this waking period." + JSON_ONLY,
    "consolidation_selection": CONSOLIDATE + " Choose up to sixty records to read." + JSON_ONLY,
    "consolidation_change_set": CONSOLIDATE
    + " Propose memory changes in application order."
    + JSON_ONLY,
}


def prompt_version_for(kind: CallKind) -> str:
    return f"{kind}/0.2"


def json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def read_json(raw: bytes | str) -> Any:
    # Ambiguous duplicate fields or non-scalar Unicode cannot be recorded canonically.
    value = json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    json_bytes(value)
    return value


class RecallStep(Output):
    step: Literal["recall"]
    query: Annotated[str, Field(max_length=200)]


class SetIntention(Output):
    set: Annotated[str, Field(max_length=500)]


class ClearIntention(Output):
    clear: Annotated[Literal[True], BeforeValidator(TypeAdapter(StrictBool).validate_python)]


class ActStep(ModelTurn):
    step: Literal["act"]
    intention: SetIntention | ClearIntention | None
    mute: list[Literal["body", "direct_speech", "nearby_speech", "discovery", "progress"]]
    cite: Annotated[list[str], Field(max_length=10)]

    @model_validator(mode="after")
    def check_agent_fields(self) -> Self:
        if self.action.kind == "continue" and self.mute:
            raise ValueError("only a new intent may mute notifications")
        if self.utterance is not None and len(self.utterance.text) > 500:
            raise ValueError("utterance exceeds 500 characters")
        if self.action.kind == "intent" and len(self.action.intent.reason or "") > 300:
            raise ValueError("intent reason exceeds 300 characters")
        return self


class MemoryIDs(Output):
    ids: list[str]


class MorningIDs(MemoryIDs):
    ids: Annotated[list[str], Field(max_length=20)]


class Selection(Output):
    read: list[str]


type Parsed = RecallStep | ActStep | MemoryIDs | Selection | ChangeSetOutput


def _decision_schema(kind: CallKind, verbs: tuple[EnabledVerb, ...]) -> dict[str, Any]:
    act = ActStep.model_json_schema()
    world = model_turn_schema(verbs)
    # Keep the world generator's reachable definitions. Only intention is a
    # harness-owned nested object; generic JsonValue from IntentShape is unused.
    extras = act.pop("$defs")
    defs = {
        **world["$defs"],
        "SetIntention": extras["SetIntention"],
        "ClearIntention": extras["ClearIntention"],
    }
    act["properties"].update(world["properties"])
    for variant in defs["Utterance"]["oneOf"]:
        variant["properties"]["text"]["maxLength"] = 500
    for variant in defs["IntentShape"]["oneOf"]:
        variant["properties"]["reason"]["maxLength"] = 300
    if kind == "decision_after_recall":
        return {"$defs": defs, **act}
    return {"$defs": defs, "type": "object", "oneOf": [act, RecallStep.model_json_schema()]}


def check_schema(schema: dict[str, Any]) -> None:
    """Offline regex preflight, including M9's retained DeepSeek HTTP 400 vector."""

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "pattern" in value and isinstance(value["pattern"], str):
                pattern = value["pattern"]
                re.compile(pattern)
                # The provider compiles scalar-value regexes. Python alone accepts
                # the surrogate range in the historical rejected schema.
                if re.search(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}|[\ud800-\udfff]", pattern):
                    raise ValueError("provider schema regex contains a surrogate")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)


@dataclass(frozen=True)
class Contract:
    kind: CallKind
    verbs: tuple[EnabledVerb, ...] = ()
    schema: bytes = field(init=False)

    @property
    def instructions(self) -> str:
        return INSTRUCTIONS[self.kind]

    @property
    def prompt_version(self) -> str:
        return prompt_version_for(self.kind)

    def __post_init__(self) -> None:
        kind = self.kind
        if kind in ("decision", "decision_after_recall"):
            schema = _decision_schema(kind, self.verbs)
        elif kind == "consolidation_change_set":
            schema = ChangeSetOutput.model_json_schema()
        elif kind == "consolidation_selection":
            schema = Selection.model_json_schema()
            schema["properties"]["read"]["maxItems"] = 60
        elif kind == "morning":
            schema = MorningIDs.model_json_schema()
        else:
            schema = MemoryIDs.model_json_schema()
            schema["properties"]["ids"]["maxItems"] = 5
        check_schema(schema)
        object.__setattr__(self, "schema", json_bytes(schema))

    def parse(self, raw: str, *, has_running_action: bool) -> Parsed:
        value = read_json(raw)
        if self.kind in ("decision", "decision_after_recall"):
            if isinstance(value, dict):
                for key in ("turn_id", "actor_id", "observed_tick", "schema_version"):
                    value.pop(key, None)
                if self.kind == "decision" and value.get("step") == "recall":
                    return RecallStep.model_validate(value)
                action = value.get("action")
                if isinstance(action, dict) and isinstance(intent := action.get("intent"), dict):
                    for key in ("actor_id", "turn_id", "intent_id"):
                        intent.pop(key, None)
            # The protocol constructs exactly the model class passed here. Its
            # constrained type variable widens subclasses to ModelTurn in mypy.
            return validate_turn_shape(  # type: ignore[return-value]
                ActStep, value, enabled_verbs=self.verbs, has_running_action=has_running_action
            )
        if self.kind == "consolidation_change_set":
            return ChangeSetOutput.model_validate(value)
        if self.kind == "consolidation_selection":
            return Selection.model_validate(value)
        if self.kind == "morning":
            return MorningIDs.model_validate(value)
        # Return all typed IDs to the assembler. It records and ignores surplus
        # or ineligible choices against the immutable sent index (MF §3.2, DL §6.3).
        return MemoryIDs.model_validate(value)
