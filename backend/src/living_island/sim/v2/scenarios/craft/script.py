"""Run each resident's own itinerary against its delivered packet only."""

from collections.abc import Iterable

from pydantic import JsonValue, TypeAdapter

from living_island.sim.v2.scenarios.receipts import State
from living_island.sim.v2.turns import TurnRequest
from living_island.world.v2 import protocol as p

from .route import BENCH, ELLA, ROUTES, SITE, Step

_WAIT = p.ModelTurn.model_validate(
    {
        "utterance": None,
        "action": {
            "kind": "intent",
            "intent": {
                "action": "wait",
                "verb": None,
                "target": None,
                "instruments": [],
                "inputs": [],
                "params": {},
                "reason": None,
            },
        },
    }
)


def find(looks: Iterable[p.InspectView], key: str) -> str | None:
    archetype, _, material = key.partition(":")
    return next(
        (
            v.entity_id
            for v in looks
            if v.entity_id == key
            or (v.archetype_id == archetype and (not material or v.material_id == material))
        ),
        None,
    )


def choice(view: p.Perception, key: str) -> p.NamedItem:
    item = find(view.inventory, key)
    if item is None:
        raise ValueError(f"{view.actor_id} tick {view.tick}: missing held {key}")
    return p.NamedItem(kind="item", id=item)


def turn(step: Step, view: p.Perception) -> p.ModelTurn | None:
    target: p.Target | None = None
    params: dict[str, JsonValue] = {}
    match step.target:
        case (x, y):
            target = p.TileTarget(kind="tile", position=p.Coord(x=x, y=y))
        case str(key):
            if step.action == "pick_up" or key == "woodpile":
                tile = (
                    SITE
                    if key == "cord:vine"
                    else (38, 32)
                    if key in {"woodpile", "clay_pot"}
                    else BENCH
                )
                looks = (
                    v
                    for v in view.visible_entities
                    if (v.position.x, v.position.y) == tile
                    and v.quantity is not None
                    and v.quantity >= step.quantity
                )
                item = find(looks, "branch" if key == "woodpile" else key)
            else:
                item = find((*view.inventory, *view.visible_entities), key)
            if item is None:
                return None
            target = p.EntityTarget(kind="entity", id=item)

    inputs = []
    if step.action == "drop":
        key, quantity = step.items[0]
        params = {"item": choice(view, key).model_dump(mode="json"), "quantity": quantity}
    elif step.action == "pick_up":
        params = {"quantity": step.quantity}
    elif step.verb == "sleep":
        params = {"duration_ticks": 6}
    else:
        inputs = [p.ActionInput(item=choice(view, key), quantity=n) for key, n in step.items]

    shape = p.IntentShape(
        action=step.action,
        verb=step.verb,
        target=target,
        instruments=[choice(view, key) for key in step.tools],
        inputs=inputs,
        params=params,
        reason=step.label,
    )
    return p.ModelTurn(utterance=None, action=p.ModelIntentAction(kind="intent", intent=shape))


class CraftScript:
    def __init__(self, state: State | None):
        self.positions = (
            dict.fromkeys(ROUTES, 0)
            if state is None
            else TypeAdapter(dict[str, int]).validate_python(state["positions"])
        )

    def checkpoint(self) -> State:
        return {"positions": dict(self.positions)}

    def deliver(self, packet: p.BoundaryDelivery) -> bool:
        # Ella interrupts her first contribution after exactly one blocked work tick.
        action = packet.perception.running_action
        return (
            packet.actor_id == "ella"
            and action is not None
            and action.action == "contribute"
            and ELLA[self.positions["ella"]].action == "pick_up"
        )

    def choose(self, request: TurnRequest) -> p.ModelTurn:
        view = request.delivery.perception
        actor = view.actor_id
        route = ROUTES[actor]
        index = self.positions[actor]
        if index == len(route):
            return _WAIT
        step = route[index]
        # Light just before the six-tick bake cycle. Shaping (four ticks) and
        # inserting (one) then fit even the shortest qualified fire lifetime.
        if step.verb == "light" and view.tick % 6 != 5:
            return _WAIT
        # Wait for vine delivery at the site before either helper starts continuous work.
        if (
            step.action == "contribute"
            and actor != "ella"
            and not any(
                (v.position.x, v.position.y) == SITE and v.archetype_id == "cord"
                for v in view.visible_entities
            )
        ):
            return _WAIT
        result = turn(step, view)
        if result is None:
            return _WAIT
        self.positions[actor] = index + 1
        return result
