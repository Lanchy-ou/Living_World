"""Builders for the P2 experiment-spec oracles (§8 worked example and §8.1 vectors).

A ``Toy`` assembles parsed frames, events and decision records and returns a ``RunData``. The
metrics only read parsed objects, so no engine run is needed. Conventions follow the spec:
map ``6x3``, spring at (5,1) (index 11), tree ``t1`` at (2,2), residents ``a``, ``b``, ``c``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from living_island.agents.types import DecisionRecord
from living_island.analysis.data import RunData, RunLimits
from living_island.contract.replay import (
    DisplayFrame,
    EventRange,
    FruitTreeFrame,
    GroundCanteenFrame,
    ResidentFrame,
)
from living_island.events import WorldEvent
from living_island.world.protocol import Coord

ROWS = ("......", ".....S", "..F...")
GAIN = 6000
LIMITS = RunLimits(
    min_value=0,
    hydration_gain_per_serving=GAIN,
    canteen_capacity=2,
    max_stock_per_tree=6,
    slot_capacity=3,
    tick_minutes=10,
)
SHA = "0" * 64


def ticks_of(spec: int | range | Iterable[int]) -> list[int]:
    return [spec] if isinstance(spec, int) else list(spec)


class Toy:
    def __init__(
        self,
        T: int = 8,
        *,
        residents: tuple[str, ...] = ("a", "b", "c"),
        rows: tuple[str, ...] = ROWS,
        limits: RunLimits = LIMITS,
        run_id: str = "toy",
    ) -> None:
        self.T, self.rows, self.limits, self.run_id = T, rows, limits, run_id
        self.residents = residents
        self.base: dict[str, Any] = dict(
            x=0,
            y=0,
            alive=True,
            satiety=5000,
            hydration=5000,
            stamina=5000,
            health=10000,
            fruit_count=0,
            canteen_servings=None,
        )
        self.cells: dict[tuple[str, int], dict[str, Any]] = {}
        self.stock: dict[int, int] = {}
        self.stock_default = 1
        self.ground_canteen: tuple[int, int, int] | None = (0, 2, 1)
        self.ground_fruit: dict[int, list[tuple[int, int, int]]] = {}
        self.events: list[WorldEvent] = []
        self.records: list[DecisionRecord] = []
        self._seq: dict[int, int] = {}

    # -- frames -------------------------------------------------------------

    def put(self, resident: str, ticks: int | range | Iterable[int], **fields: Any) -> Toy:
        """Override fields of a resident's frames at the given ticks."""
        for tick in ticks_of(ticks):
            self.cells.setdefault((resident, tick), {}).update(fields)
        return self

    def alive_until(self, resident: str, last_alive_tick: int, **dead: Any) -> Toy:
        """The resident is alive through ``last_alive_tick`` and dead after it."""
        return self.put(
            resident,
            range(last_alive_tick + 1, self.T + 1),
            alive=False,
            fruit_count=0,
            canteen_servings=None,
            **dead,
        )

    def trees(self, ticks: int | range | Iterable[int], stock: int) -> Toy:
        for tick in ticks_of(ticks):
            self.stock[tick] = stock
        return self

    def frame(self, tick: int) -> DisplayFrame:
        residents = []
        for rid in sorted(self.residents):
            v = {**self.base, **self.cells.get((rid, tick), {})}
            residents.append(
                ResidentFrame(
                    id=rid,
                    position=Coord(x=v["x"], y=v["y"]),
                    alive=v["alive"],
                    satiety=v["satiety"],
                    hydration=v["hydration"],
                    stamina=v["stamina"],
                    health=v["health"],
                    fruit_count=v["fruit_count"],
                    canteen_servings=v["canteen_servings"],
                    active_action=None,
                )
            )
        held = any(r.alive and r.canteen_servings is not None for r in residents)
        ground = None
        if self.ground_canteen is not None and not held:
            x, y, servings = self.ground_canteen
            ground = GroundCanteenFrame(position=Coord(x=x, y=y), servings=servings)
        return DisplayFrame(
            tick=tick,
            residents=residents,
            fruit_trees=[
                FruitTreeFrame(
                    id="t1",
                    position=Coord(x=2, y=2),
                    stock=self.stock.get(tick, self.stock_default),
                )
            ],
            ground_fruit=[],
            ground_canteen=ground,
            corpses=[],
            event_range=EventRange(first_index=0, count=0),
        )

    # -- events -------------------------------------------------------------

    def event(
        self,
        event_type: str,
        tick: int,
        payload: dict[str, Any],
        *,
        actor: str | None = None,
        target: str | None = None,
        intent: str | None = None,
        seq: int | None = None,
    ) -> WorldEvent:
        if seq is None:
            seq = self._seq.get(tick, 0)
        self._seq[tick] = seq + 1
        built = WorldEvent.model_validate(
            {
                "schema_version": "0.1",
                "run_id": self.run_id,
                "event_id": f"{self.run_id}:{tick:010d}:{seq:06d}",
                "tick": tick,
                "seq_in_tick": seq,
                "type": event_type,
                "actor_id": actor,
                "target_id": target,
                "intent_id": intent,
                "llm_call_id": None,
                "caused_by_event_ids": [],
                "payload": payload,
            }
        )
        self.events.append(built)
        return built

    def explored(self, tick: int, resident: str, indices: list[int]) -> WorldEvent:
        return self.event(
            "exploration_updated",
            tick,
            {"resident_id": resident, "newly_seen_tile_indices": indices},
            actor=resident,
        )

    def succeeded(self, tick: int, actor: str, action_type: str, **kw: Any) -> WorldEvent:
        return self.event(
            "action_succeeded",
            tick,
            {"action_type": action_type, "result_code": "OK"},
            actor=actor,
            **kw,
        )

    def failed(self, tick: int, actor: str, action_type: str, code: str, **kw: Any) -> WorldEvent:
        return self.event(
            "action_failed",
            tick,
            {"action_type": action_type, "failure_code": code},
            actor=actor,
            **kw,
        )

    def gathered(
        self, tick: int, actor: str, tree: str = "t1", before: int = 1, after: int = 0, **kw: Any
    ) -> WorldEvent:
        return self.event(
            "fruit_gathered",
            tick,
            {"tree_id": tree, "quantity": 1, "stock_before": before, "stock_after": after},
            actor=actor,
            **kw,
        )

    def drank(
        self,
        tick: int,
        actor: str,
        source: str,
        before: int,
        after: int,
        servings_after: int | None = None,
    ) -> WorldEvent:
        return self.event(
            "water_drank",
            tick,
            {
                "source": source,
                "servings": 1,
                "hydration_before": before,
                "hydration_after": after,
                "canteen_servings_after": servings_after,
            },
            actor=actor,
        )

    def died(self, tick: int, resident: str) -> WorldEvent:
        return self.event(
            "resident_died",
            tick,
            {"resident_id": resident, "position": {"x": 0, "y": 0}, "cause": "DEPRIVATION"},
            actor=resident,
        )

    def given(
        self, tick: int, giver: str, to: str, item_type: str = "canteen", quantity: int = 1
    ) -> WorldEvent:
        return self.event(
            "item_given",
            tick,
            {
                "from_id": giver,
                "to_id": to,
                "item_type": item_type,
                "quantity": quantity,
                "canteen_id": "canteen_01" if item_type == "canteen" else None,
            },
            actor=giver,
            target=to,
        )

    # -- decisions ----------------------------------------------------------

    def decision(
        self,
        actor: str,
        ordinal: int,
        tick: int,
        intents: list[dict[str, Any]],
        triggers: tuple[str, ...] = ("PLAN_FINISHED",),
    ) -> DecisionRecord:
        plan_id = f"{actor}:p{ordinal:06d}"
        record = DecisionRecord.model_validate(
            {
                "record_schema_version": "0.1",
                "run_id": self.run_id,
                "tick": tick,
                "actor_id": actor,
                "decision_ordinal": ordinal,
                "policy_id": "scripted-v0",
                "effective_policy_id": "scripted-v0",
                "triggers": list(triggers),
                "request_sha256": SHA,
                "status": "ok",
                "error_kind": None,
                "plan": {
                    "plan_id": plan_id,
                    "actor_id": actor,
                    "created_at_tick": tick,
                    "intents": [
                        {
                            "intent_id": f"{plan_id}:i{index}",
                            "plan_id": plan_id,
                            "actor_id": actor,
                            "reason": None,
                            **intent,
                        }
                        for index, intent in enumerate(intents)
                    ],
                },
                "substituted": False,
                "llm_call_id": None,
            }
        )
        self.records.append(record)
        return record

    def run(self) -> RunData:
        return RunData(
            self.run_id,
            [self.frame(k) for k in range(self.T + 1)],
            self.events,
            self.records,
            self.rows,
            self.limits,
        )


def gather_intent(tree: str = "t1") -> dict[str, Any]:
    return {
        "action_type": "gather",
        "target": {"kind": "entity", "id": tree},
        "parameters": {},
    }


def move_intent(x: int, y: int) -> dict[str, Any]:
    return {
        "action_type": "move_to",
        "target": {"kind": "tile", "position": {"x": x, "y": y}},
        "parameters": {},
    }


def give_intent(to: str, item_type: str = "canteen", quantity: int = 1) -> dict[str, Any]:
    return {
        "action_type": "give",
        "target": {"kind": "resident", "id": to},
        "parameters": {"item_type": item_type, "quantity": quantity},
    }


def pick_up_intent(x: int, y: int, item_type: str = "fruit", quantity: int = 1) -> dict[str, Any]:
    return {
        "action_type": "pick_up",
        "target": {"kind": "tile", "position": {"x": x, "y": y}},
        "parameters": {"item_type": item_type, "quantity": quantity},
    }


def talk_refuse_intent(to: str, in_reply_to: str) -> dict[str, Any]:
    return {
        "action_type": "talk",
        "target": {"kind": "resident", "id": to},
        "parameters": {"speech_act": "refuse", "text": "no", "in_reply_to": in_reply_to},
    }


def talk_accept_intent(to: str, in_reply_to: str) -> dict[str, Any]:
    return {
        "action_type": "talk",
        "target": {"kind": "resident", "id": to},
        "parameters": {"speech_act": "accept", "text": "yes", "in_reply_to": in_reply_to},
    }


def drink_intent(source: str = "spring") -> dict[str, Any]:
    return {"action_type": "drink", "target": None, "parameters": {"source": source}}


def worked_example() -> Toy:
    """The §8 worked example."""
    toy = Toy(T=8)
    positions = {
        "a": [(0, 1), (2, 1), (4, 1), (4, 1), (2, 1), (2, 1), (4, 1), (4, 1), (4, 1)],
        "c": [(1, 2)] * 9,
        "b": [(0, 0)] * 9,
    }
    for rid, path in positions.items():
        for tick, (x, y) in enumerate(path):
            toy.put(rid, tick, x=x, y=y)
    for tick, hydration in enumerate([150, 50, 0, 0, 0, 0, 0, 0, 0]):
        toy.put("b", tick, hydration=hydration)
    toy.alive_until("b", 2)
    toy.trees(range(0, 5), 1).trees(range(5, 9), 0)
    # Tick 0: b already sees the spring tile (index 11); a and c do not.
    toy.explored(0, "a", [3])
    toy.explored(0, "b", [3, 11])
    toy.explored(0, "c", [3])
    toy.explored(2, "a", [11])
    toy.succeeded(2, "a", "move_to")
    toy.drank(3, "a", "spring", 2000, 8000)
    toy.succeeded(3, "a", "drink")
    toy.died(3, "b")
    toy.gathered(5, "a")  # toy:0000000005:000000
    toy.succeeded(5, "a", "gather")
    toy.failed(5, "c", "gather", "RESOURCE_TAKEN", intent="c:p000001:i0")  # seq 2
    toy.drank(7, "a", "spring", 7000, 10000)
    toy.succeeded(7, "a", "drink")
    toy.decision("c", 1, 3, [gather_intent()])
    toy.decision("c", 2, 5, [move_intent(0, 2)], triggers=("ACTION_FAILED",))
    return toy
