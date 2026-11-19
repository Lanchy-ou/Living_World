"""Portable projection/0.1 types and canonical fixture encoding."""

import gzip
import io
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonnegative = Annotated[int, Field(ge=0)]
Values = dict[str, JsonValue]


class ProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Position(ProjectionModel):
    x: Nonnegative
    y: Nonnegative


class Resident(ProjectionModel):
    id: str
    position: Position
    alive: bool
    satiety: Nonnegative
    hydration: Nonnegative
    stamina: Nonnegative
    health: Nonnegative
    fruit_count: Nonnegative
    canteen_id: str | None
    canteen_servings: Nonnegative | None


class Tree(ProjectionModel):
    id: str
    stock: Nonnegative


class GroundFruit(ProjectionModel):
    position: Position
    quantity: Annotated[int, Field(gt=0)]


class Canteen(ProjectionModel):
    id: str
    holder_id: str | None
    ground_position: Position | None
    servings: Nonnegative

    @model_validator(mode="after")
    def place(self) -> "Canteen":
        if (self.holder_id is None) == (self.ground_position is None):
            raise ValueError("canteen must have exactly one place")
        return self


class Corpse(ProjectionModel):
    id: str
    resident_id: str
    position: Position
    death_tick: Nonnegative


class RequestTerms(ProjectionModel):
    item_type: Literal["fruit", "canteen"]
    quantity: Annotated[int, Field(gt=0)]


class Utterance(ProjectionModel):
    tick: Nonnegative
    speaker: str
    addressee: str
    act: Literal["statement", "request", "accept", "refuse"]
    text: str
    request: RequestTerms | None


class Outcome(ProjectionModel):
    actor_id: str
    intent_id: str
    tick_started: Nonnegative
    tick_finished: Nonnegative
    status: Literal["success", "failure", "interrupted"]
    code: str | None
    next_decision_tick: Nonnegative | None = None

    @model_validator(mode="after")
    def timeline(self) -> "Outcome":
        if self.tick_started > self.tick_finished:
            raise ValueError("outcome ends before it starts")
        if (self.code is None) != (self.status == "success"):
            raise ValueError("only unsuccessful outcomes carry a code")
        if self.next_decision_tick is not None and self.next_decision_tick < self.tick_finished:
            raise ValueError("next decision precedes the outcome")
        return self


class Intent(ProjectionModel):
    action_type: str
    target: Values | None
    parameters: Values


class Decision(ProjectionModel):
    actor_id: str
    triggers: list[str]
    intents: Annotated[list[Intent], Field(min_length=1)]


class Frame(ProjectionModel):
    tick: Nonnegative
    residents: list[Resident]
    trees: list[Tree]
    ground_fruit: list[GroundFruit]
    canteen: Canteen
    corpses: list[Corpse]
    utterances: list[Utterance]
    outcomes: list[Outcome]
    decisions: list[Decision]


class Source(ProjectionModel):
    v1_source_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    config_blob_sha256: Digest
    effective_config_sha256: Digest
    map_blob_sha256: Digest
    map_sha256: Digest
    seed: Annotated[int, Field(ge=1, le=2**32 - 1)]
    generator_version: Literal["0.1"] = "0.1"


class Projection(ProjectionModel):
    version: Literal["projection/0.1"] = "projection/0.1"
    case: str
    config: str
    policy: str
    source: Source
    frames: Annotated[list[Frame], Field(min_length=1)]
    scripted_evidence: list[Values] | None = None

    @model_validator(mode="after")
    def timeline(self) -> "Projection":
        first = self.frames[0].tick
        next_decision: dict[str, int] = {}
        for index in reversed(range(len(self.frames))):
            frame = self.frames[index]
            tick = first + index
            if frame.tick != tick or any(item.tick != tick for item in frame.utterances):
                raise ValueError("projection frames and utterances must follow the boundary clock")
            for decision in frame.decisions:
                next_decision[decision.actor_id] = tick
            for outcome in frame.outcomes:
                if outcome.tick_finished != tick:
                    raise ValueError("outcome recorded at the wrong boundary")
                if outcome.next_decision_tick != next_decision.get(outcome.actor_id):
                    raise ValueError("outcome must link to the next recorded decision")
        if self.scripted_evidence is not None and (
            [entry.get("tick") for entry in self.scripted_evidence]
            != [frame.tick for frame in self.frames]
        ):
            raise ValueError("scripted evidence must follow the boundary clock")
        return self


def canonical_bytes(projection: Projection) -> bytes:
    # Keep this encoding independent of v1 so fixtures still load after its removal.
    return json.dumps(
        projection.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def fixture_bytes(projection: Projection) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as stream:
        stream.write(canonical_bytes(projection))
    return buffer.getvalue()


def read_projection(path: Path) -> Projection:
    raw = gzip.decompress(path.read_bytes())
    projection = Projection.model_validate_json(raw)
    if raw != canonical_bytes(projection):
        raise ValueError(f"{path}: projection JSON is not canonical")
    return projection
