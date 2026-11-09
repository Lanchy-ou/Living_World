"""Read-only replay DTOs: ``ReplayBundle`` and ``DisplayFrame`` (amendment A2).

Replay-frontend spec §2.2-§2.3. The bundle is a display projection for the offline viewer.
It is separate from ``SavePackage`` and never reuses ``WorldState`` or ``Perception``.

This module is the single source for the replay schema: ``scripts/gen_types.py`` exports
``frontend/src/api/generated/replay.schema.json`` and the TypeScript types from it. The
cross-field validators below are the backend half of the shared validation contract; the
browser re-implements the same rules in P1-08 against the same fixtures.

Every cross-field validator raises ``ValueError`` whose message starts with a stable rule slug
(``frame_ticks:``, ``event_range:`` ...) so tests and tools can assert the reason.

Depends only on the canonical event model and public vocabularies; no ``sim`` dependency and
no ``world.state`` import.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from living_island.world.facts import (
    UtteranceHeardPayload,
    UtteranceSpokenPayload,
    WorldEvent,
    format_event_id,
)
from living_island.world.protocol import (
    TERRAIN_BY_SYMBOL,
    Coord,
    NonNegInt,
    PosInt,
    ProtocolModel,
    Sha256Hex,
    Terrain,
)

REPLAY_SCHEMA_VERSION = "0.1"

# Grammar symbols of World Rules §1.2: one printable ASCII character per legend entry.
LegendSymbol = Annotated[str, StringConstraints(min_length=1, max_length=1, pattern=r"^[ -~]$")]
# A map row only ever holds the nine grammar symbols ``~ . , W ^ S C F M``.
MapRow = Annotated[str, StringConstraints(min_length=1, pattern=r"^[~.,W^SCFM]+$")]

# Payload fields that reference a resident (replay-frontend §4.4, plus ``recipient_id``,
# see OQ-009) and payload fields that hold a coordinate.
RESIDENT_REF_FIELDS = (
    "resident_id",
    "from_id",
    "to_id",
    "listener_id",
    "addressee_id",
    "recipient_id",
)
PAYLOAD_COORD_FIELDS = ("from_", "to", "position")


# ---------------------------------------------------------------------------
# Header pieces
# ---------------------------------------------------------------------------


class ReplayClock(ProtocolModel):
    tick_minutes: PosInt
    start_hour: Annotated[int, Field(ge=0, le=23)]
    day_start_hour: Annotated[int, Field(ge=0, le=24)]
    day_end_hour: Annotated[int, Field(ge=0, le=24)]

    @model_validator(mode="after")
    def _world_rules_1_1(self) -> ReplayClock:
        if 1440 % self.tick_minutes != 0:
            raise ValueError("clock: tick_minutes must divide 1440")
        if not self.day_start_hour < self.day_end_hour:
            raise ValueError("clock: day_start_hour must be below day_end_hour")
        return self


class ConditionBounds(ProtocolModel):
    """Effective needs bounds; the minimum is always 0 and below the maximum."""

    min_value: Literal[0]
    max_value: PosInt


class LegendEntry(ProtocolModel):
    symbol: LegendSymbol
    terrain: Terrain


class ReplayMap(ProtocolModel):
    width: PosInt
    height: PosInt
    rows: list[MapRow]
    terrain_legend: list[LegendEntry]

    @model_validator(mode="after")
    def _grid_and_legend(self) -> ReplayMap:
        if len(self.rows) != self.height:
            raise ValueError(f"map: expected {self.height} rows, got {len(self.rows)}")
        for y, row in enumerate(self.rows):
            if len(row) != self.width:
                raise ValueError(f"map: row {y} has length {len(row)}, expected {self.width}")
        expected = list(TERRAIN_BY_SYMBOL.items())
        actual = [(e.symbol, e.terrain) for e in self.terrain_legend]
        if actual != expected:
            raise ValueError(
                "legend: terrain_legend must be exactly the nine World Rules §1.2 pairs "
                "in order ~ . , W ^ S C F M"
            )
        return self


class ReplayResident(ProtocolModel):
    """Label only; carries no state."""

    id: str
    display_name: str


# ---------------------------------------------------------------------------
# Display frame
# ---------------------------------------------------------------------------


class ActiveActionDisplay(ProtocolModel):
    intent_id: str
    action_type: str
    tick_started: NonNegInt
    remaining_ticks: NonNegInt | None


class ResidentFrame(ProtocolModel):
    id: str
    position: Coord
    alive: bool
    satiety: NonNegInt
    hydration: NonNegInt
    stamina: NonNegInt
    health: NonNegInt
    fruit_count: NonNegInt
    canteen_servings: NonNegInt | None  # null = not holding the canteen
    active_action: ActiveActionDisplay | None


class FruitTreeFrame(ProtocolModel):
    id: str
    position: Coord
    stock: NonNegInt


class GroundFruitFrame(ProtocolModel):
    position: Coord
    quantity: NonNegInt


class GroundCanteenFrame(ProtocolModel):
    position: Coord
    servings: NonNegInt


class CorpseFrame(ProtocolModel):
    id: str
    resident_id: str
    position: Coord


class EventRange(ProtocolModel):
    first_index: NonNegInt
    count: NonNegInt


def _require_strictly_ascending[T: (str, tuple[int, int])](
    keys: list[T], rule: str, what: str
) -> None:
    for a, b in zip(keys, keys[1:], strict=False):
        if a == b:
            raise ValueError(f"{rule}: duplicate {what} {a!r}")
    for a, b in zip(keys, keys[1:], strict=False):
        if a > b:
            raise ValueError(f"{rule}: {what} must be sorted ascending")


class DisplayFrame(ProtocolModel):
    tick: NonNegInt
    residents: list[ResidentFrame]
    fruit_trees: list[FruitTreeFrame]
    ground_fruit: list[GroundFruitFrame]
    ground_canteen: GroundCanteenFrame | None
    corpses: list[CorpseFrame]
    event_range: EventRange

    @model_validator(mode="after")
    def _unique_and_sorted(self) -> DisplayFrame:
        # IC §6.2: entries by ID, ground fruit by (y, x).
        resident_ids = [r.id for r in self.residents]
        _require_strictly_ascending(resident_ids, "frame_sort", "resident id")
        tree_ids = [t.id for t in self.fruit_trees]
        _require_strictly_ascending(tree_ids, "frame_sort", "fruit tree id")
        corpse_ids = [c.id for c in self.corpses]
        _require_strictly_ascending(corpse_ids, "frame_sort", "corpse id")
        pile_keys = [(g.position.y, g.position.x) for g in self.ground_fruit]
        _require_strictly_ascending(pile_keys, "frame_sort", "ground fruit (y, x)")
        return self


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------


def map_hash_of(rows: list[str]) -> str:
    """SHA-256 of the rows joined with LF plus a final LF (replay-frontend §2.3)."""
    return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


def _in_map(c: Coord, width: int, height: int) -> bool:
    return c.x < width and c.y < height


class ReplayBundle(ProtocolModel):
    replay_schema_version: Literal["0.1"]
    run_id: str
    world_id: str
    config_hash: Sha256Hex  # identity only; the viewer cannot verify it
    map_hash: Sha256Hex
    clock: ReplayClock
    condition_bounds: ConditionBounds
    map: ReplayMap
    residents: list[ReplayResident]
    frames: Annotated[list[DisplayFrame], Field(min_length=1)]
    events: list[WorldEvent]

    @model_validator(mode="after")
    def _cross_field(self) -> ReplayBundle:
        self._check_map_hash()
        self._check_declared_residents()
        self._check_frame_ticks()
        self._check_events()
        self._check_event_ranges()
        self._check_event_references()
        self._check_frames()
        self._check_namespaces()
        return self

    # -- header ------------------------------------------------------------

    def _check_map_hash(self) -> None:
        if self.map_hash != map_hash_of(self.map.rows):
            raise ValueError("map_hash: does not match rows joined with LF plus a final LF")

    def _check_declared_residents(self) -> None:
        _require_strictly_ascending(
            [r.id for r in self.residents], "residents", "declared resident id"
        )

    # -- frames ------------------------------------------------------------

    def _check_frame_ticks(self) -> None:
        for index, frame in enumerate(self.frames):
            if frame.tick != index:
                raise ValueError(
                    f"frame_ticks: frame at index {index} has tick {frame.tick}; "
                    "ticks must be contiguous from 0"
                )

    # -- events ------------------------------------------------------------

    def _check_events(self) -> None:
        seen: set[str] = set()
        for event in self.events:
            if event.run_id != self.run_id:
                raise ValueError(f"run_id: event {event.event_id} has run_id {event.run_id!r}")
            expected = format_event_id(event.run_id, event.tick, event.seq_in_tick)
            if event.event_id != expected:
                raise ValueError(f"event_id: {event.event_id} does not match {expected}")
            if event.event_id in seen:
                raise ValueError(f"event_id: duplicate event id {event.event_id}")
            seen.add(event.event_id)
        previous: WorldEvent | None = None
        for event in self.events:
            if previous is None or event.tick > previous.tick:
                if event.seq_in_tick != 0:
                    raise ValueError(
                        f"event_seq: first event of tick {event.tick} has seq_in_tick "
                        f"{event.seq_in_tick}, expected 0"
                    )
            elif event.tick < previous.tick or event.seq_in_tick <= previous.seq_in_tick:
                raise ValueError(
                    f"event_order: {event.event_id} follows {previous.event_id}; "
                    "events must be strictly ordered by (tick, seq_in_tick)"
                )
            elif event.seq_in_tick != previous.seq_in_tick + 1:
                raise ValueError(
                    f"event_seq: {event.event_id} follows {previous.event_id}; "
                    "seq_in_tick must be contiguous"
                )
            previous = event

    def _check_event_ranges(self) -> None:
        per_tick = Counter(e.tick for e in self.events)
        cursor = 0
        for frame in self.frames:
            rng = frame.event_range
            if rng.first_index != cursor:
                raise ValueError(
                    f"event_range: frame {frame.tick} first_index {rng.first_index}, "
                    f"expected cumulative prior count {cursor}"
                )
            end = rng.first_index + rng.count
            if end > len(self.events):
                raise ValueError(f"event_range: frame {frame.tick} slice ends past the events")
            for event in self.events[rng.first_index : end]:
                if event.tick != frame.tick:
                    raise ValueError(
                        f"event_range: frame {frame.tick} slice holds {event.event_id} "
                        f"of tick {event.tick}"
                    )
            if rng.count != per_tick.get(frame.tick, 0):
                raise ValueError(
                    f"event_range: frame {frame.tick} count {rng.count} but the bundle has "
                    f"{per_tick.get(frame.tick, 0)} events at that tick"
                )
            cursor = end
        if cursor != len(self.events):
            raise ValueError(
                f"event_range: slices cover {cursor} of {len(self.events)} events; "
                "every event must belong to exactly one frame"
            )

    def _check_event_references(self) -> None:
        index_of = {e.event_id: i for i, e in enumerate(self.events)}
        spoken: dict[str, str] = {}  # utterance event id -> speech_act, earlier events only
        residents = {r.id for r in self.residents}
        tree_ids = {t.id for t in self.frames[0].fruit_trees}
        for i, event in enumerate(self.events):
            for ref in event.caused_by_event_ids:
                if ref not in index_of:
                    raise ValueError(f"causal_refs: {event.event_id} cites unknown event {ref}")
                if index_of[ref] >= i:
                    raise ValueError(
                        f"causal_refs: {event.event_id} cites {ref}, which is not earlier"
                    )
            payload = event.payload
            if isinstance(payload, UtteranceSpokenPayload):
                if payload.utterance_id != event.event_id:
                    raise ValueError(
                        f"utterance_refs: utterance_id of {event.event_id} must equal its event id"
                    )
                if payload.in_reply_to is not None and spoken.get(payload.in_reply_to) != "request":
                    raise ValueError(
                        f"utterance_refs: in_reply_to of {event.event_id} must cite an earlier "
                        "utterance_spoken request"
                    )
                spoken[event.event_id] = payload.speech_act
            elif isinstance(payload, UtteranceHeardPayload) and payload.utterance_id not in spoken:
                raise ValueError(
                    f"utterance_refs: utterance_heard {event.event_id} cites no earlier "
                    "utterance_spoken"
                )
            if event.actor_id is not None and event.actor_id not in residents:
                raise ValueError(
                    f"entity_refs: actor_id {event.actor_id!r} of {event.event_id} "
                    "is not a declared resident"
                )
            for name in RESIDENT_REF_FIELDS:
                value = getattr(payload, name, None)
                if value is not None and value not in residents:
                    raise ValueError(
                        f"entity_refs: {name} {value!r} of {event.event_id} "
                        "is not a declared resident"
                    )
            tree_id = getattr(payload, "tree_id", None)
            if tree_id is not None and tree_id not in tree_ids:
                raise ValueError(
                    f"entity_refs: tree_id {tree_id!r} of {event.event_id} is not a fruit tree"
                )
            for name in PAYLOAD_COORD_FIELDS:
                coord = getattr(payload, name, None)
                if isinstance(coord, Coord) and not _in_map(coord, self.map.width, self.map.height):
                    raise ValueError(f"coords: {name} of {event.event_id} is outside the map")

    # -- frame contents ----------------------------------------------------

    def _check_frames(self) -> None:
        w, h = self.map.width, self.map.height
        declared = [r.id for r in self.residents]
        declared_set = set(declared)
        f_tiles = {
            (x, y) for y, row in enumerate(self.map.rows) for x, ch in enumerate(row) if ch == "F"
        }
        first = self.frames[0]
        base_trees = [(t.id, t.position.x, t.position.y) for t in first.fruit_trees]
        if len({(x, y) for _, x, y in base_trees}) != len(base_trees):
            raise ValueError("trees: two fruit trees share a position")
        if {(x, y) for _, x, y in base_trees} != f_tiles:
            raise ValueError("trees: fruit trees must correspond one-to-one to F tiles")
        max_value = self.condition_bounds.max_value
        for frame in self.frames:
            ids = {r.id for r in frame.residents}
            if ids != declared_set:
                missing = sorted(declared_set - ids)
                extra = sorted(ids - declared_set)
                raise ValueError(
                    f"frame_residents: frame {frame.tick} resident ids differ from declared "
                    f"(missing {missing}, undeclared {extra})"
                )
            for r in frame.residents:
                if not _in_map(r.position, w, h):
                    raise ValueError(f"coords: resident {r.id} outside the map at {frame.tick}")
                for name in ("satiety", "hydration", "stamina", "health"):
                    if getattr(r, name) > max_value:
                        raise ValueError(
                            f"conditions: {name} of {r.id} exceeds {max_value} at {frame.tick}"
                        )
            if [(t.id, t.position.x, t.position.y) for t in frame.fruit_trees] != base_trees:
                raise ValueError(
                    f"trees: frame {frame.tick} fruit tree ids or positions differ from tick 0"
                )
            for g in frame.ground_fruit:
                if not _in_map(g.position, w, h):
                    raise ValueError(f"coords: ground fruit outside the map at {frame.tick}")
            if frame.ground_canteen and not _in_map(frame.ground_canteen.position, w, h):
                raise ValueError(f"coords: ground canteen outside the map at {frame.tick}")
            for c in frame.corpses:
                if c.resident_id not in declared_set:
                    raise ValueError(
                        f"entity_refs: corpse {c.id} cites undeclared resident {c.resident_id!r}"
                    )
                if not _in_map(c.position, w, h):
                    raise ValueError(f"coords: corpse {c.id} outside the map at {frame.tick}")

    def _check_namespaces(self) -> None:
        residents = {r.id for r in self.residents}
        trees = {t.id for t in self.frames[0].fruit_trees}
        corpses = {c.id for f in self.frames for c in f.corpses}
        for a, b, label in (
            (residents, trees, "resident/fruit tree"),
            (residents, corpses, "resident/corpse"),
            (trees, corpses, "fruit tree/corpse"),
        ):
            clash = sorted(a & b)
            if clash:
                raise ValueError(f"namespaces: {label} ids collide: {clash}")
