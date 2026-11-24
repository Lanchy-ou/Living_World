"""Three repeatable work schedules on the registered island."""

from dataclasses import dataclass

from pydantic import JsonValue

from living_island.sim.v2.scenarios.receipts import State
from living_island.sim.v2.turns import TurnRequest
from living_island.world.v2.protocol import (
    Action,
    ActionInput,
    BoundaryDelivery,
    Coord,
    EntityTarget,
    HeldItem,
    IntentShape,
    ModelIntentAction,
    ModelTurn,
    Target,
    TileTarget,
)
from living_island.world.v2.rules import Pack

SEED = 2195683955
WEEK = 7 * 144
START = {"ryan": (39, 30), "mia": (37, 31), "ella": (42, 11)}


def tile(x: int, y: int) -> TileTarget:
    return TileTarget(kind="tile", position=Coord(x=x, y=y))


def entity(key: str) -> EntityTarget:
    return EntityTarget(kind="entity", id=key)


def held(archetype: str) -> HeldItem:
    return HeldItem(kind="held", archetype_id=archetype)


def intent(
    verb: str | None = None,
    target: Target | None = None,
    *,
    action: Action = "act",
    tools: tuple[str, ...] = (),
    inputs: tuple[tuple[str, int], ...] = (),
    params: dict[str, JsonValue] | None = None,
) -> IntentShape:
    return IntentShape(
        action=action,
        verb=verb,
        target=target,
        instruments=[held(tool) for tool in tools],
        inputs=[ActionInput(item=held(kind), quantity=n) for kind, n in inputs],
        params={} if params is None else params,
        reason=None,
    )


@dataclass
class Schedule:
    programs: dict[str, tuple[IntentShape, ...]]

    def deliver(self, packet: BoundaryDelivery) -> bool:
        return False

    def choose(self, request: TurnRequest) -> ModelTurn:
        # The coordinator checkpoints the next ordinal, including mid-action restores.
        rows = self.programs[request.delivery.actor_id]
        command = rows[request.ordinal % len(rows)]
        return ModelTurn(action=ModelIntentAction(kind="intent", intent=command), utterance=None)

    def checkpoint(self) -> State:
        return {}


def schedules(pack: Pack) -> Schedule:
    eat = intent(
        "eat", inputs=(("fruit", pack.rules["compat_eat_fruit"].data["inputs"][0]["qty"]),)
    )
    sleep = intent("sleep", params={"duration_ticks": pack.data["timing"]["sleep_ticks"]})
    clay = pack.rules["shape_pot"].data["inputs"][0]["qty"]
    potter = (
        *((intent("gather", entity("clay_bank_01")),) * (clay + 1)),
        intent(
            action="drop",
            target=tile(*START["mia"]),
            params={"item": held("clay_lump").model_dump(), "quantity": 1},
        ),
        intent("combine", inputs=(("clay_lump", clay),)),
        intent(
            action="drop",
            target=tile(*START["mia"]),
            params={"item": held("unfired_pot").model_dump(), "quantity": 1},
        ),
        sleep,
    )
    # Short waypoints keep each next destination in sight even after dark.
    # The carrier eats at two orchards and replenishes the canteen at the spring.
    spring = START["ryan"]
    orchards = (
        ("fruit_04", [(42, 30), (45, 30), (48, 30), (51, 30), (52, 28)]),
        (
            "fruit_06",
            [(39, 33), (39, 36), (42, 36), (45, 36), (48, 36), (48, 39), (48, 42), (48, 45)],
        ),
    )
    carrier = []
    for tree, path in orchards:
        carrier.extend(
            (
                intent("drink", tools=("canteen",)),
                intent("fill", entity("canteen_01")),
                *(intent(action="move_to", target=tile(*p)) for p in path),
                intent("gather", entity(tree)),
                eat,
                sleep,
                intent("drink", tools=("canteen",)),
                *(
                    intent(action="move_to", target=tile(*p))
                    for p in reversed([spring, *path[:-1]])
                ),
            )
        )
    harvest = intent("gather", entity("fruit_03"))
    leave_fruit = intent(
        action="drop",
        target=tile(*START["ella"]),
        params={"item": held("fruit").model_dump(), "quantity": 1},
    )
    return Schedule(
        {
            "ella": (harvest, leave_fruit, sleep, harvest, eat, sleep),
            "mia": potter,
            "ryan": tuple(carrier),
        }
    )
