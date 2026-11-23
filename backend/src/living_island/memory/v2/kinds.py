"""The schema and policy declarations used by writers, change sets and recipe lookup."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from living_island.memory.v2.records import (
    Belief,
    Commitment,
    Content,
    Episodic,
    Intention,
    MemoryRecord,
    Personality,
    Skill,
    Social,
)

type Operation = Literal[
    "add",
    "update",
    "confidence",
    "review_done",
    "supersede",
    "merge",
    "forget",
    "commitment_status",
    "trait",
]


@dataclass(frozen=True)
class Kind:
    # The schema supplies index flags via Content.flags and the resident projection hook.
    schema: type[Content]
    live_capacity: int | None
    history_capacity: int
    operations: frozenset[Operation]
    recipes: tuple[str, ...] = ()
    # When set, the live capacity applies per value of this content field.
    capacity_key: str | None = None


_REVISABLE: frozenset[Operation] = frozenset(
    {"add", "update", "confidence", "review_done", "supersede", "merge", "forget"}
)
BUILTINS = (
    Kind(Episodic, 300, 300, _REVISABLE),
    Kind(Belief, 200, 200, _REVISABLE, ("direct_speech", "nearby_speech", "body", "discovery")),
    Kind(
        Social,
        1,
        0,
        frozenset({"update", "confidence", "review_done"}),
        ("direct_speech", "nearby_speech"),
        capacity_key="about",
    ),
    Kind(Skill, 80, 80, _REVISABLE - {"merge"}, ("action_ended", "discovery")),
    Kind(
        Commitment,
        None,
        0,
        frozenset({"commitment_status", "review_done"}),
        ("direct_speech", "nearby_speech", "counterpart_in_sight", "due_soon"),
    ),
    Kind(Intention, 1, 20, frozenset()),
    Kind(Personality, 1, 0, frozenset({"trait"})),
)


class KindRegistry:
    def __init__(self, *additional: Kind) -> None:
        self._kinds: dict[str, Kind] = {}
        for definition in (*BUILTINS, *additional):
            self.register(definition)

    def register(self, definition: Kind) -> None:
        name = definition.schema.kind
        if name in self._kinds:
            raise ValueError(f"memory kind already registered: {name}")
        self._kinds[name] = definition

    def __getitem__(self, kind: str) -> Kind:
        return self._kinds[kind]

    def parse(self, fields: Mapping[str, Any]) -> MemoryRecord:
        """Decode an external envelope using exactly the selected kind's content schema."""
        schema = self[fields["kind"]].schema
        content = schema.model_validate(fields["content"])
        return MemoryRecord.model_validate({**fields, "content": content})
