"""Deterministic, perception-only test traffic (Agent Interface §4.1)."""

from hashlib import sha256

from pydantic import JsonValue

from living_island.agents.policies._plans import WAIT, make_plan
from living_island.agents.types import DecisionRequest, IntentTemplate, OkOutcome, PolicyConfig
from living_island.world.protocol import (
    ActionType,
    Coord,
    DrinkParameters,
    EmptyParameters,
    EntityTarget,
    ItemTransferParameters,
    Perception,
    TileTarget,
)

_PASSABLE = {"beach", "grass", "woods", "cave", "fruit_tree", "damp_moss"}


def _distance(a: Coord, b: Coord) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


def _simple(action: ActionType) -> IntentTemplate:
    return IntentTemplate(
        action_type=action, target=None, parameters=EmptyParameters(), reason=None
    )


class RandomPolicy:
    policy_id = "random-v0"

    def __init__(self, config: PolicyConfig) -> None:
        self._config = config

    def _move_targets(self, perception: Perception) -> list[IntentTemplate]:
        explored = {(tile.position.x, tile.position.y) for tile in perception.explored_static_tiles}
        passable = {
            (tile.position.x, tile.position.y)
            for tile in perception.explored_static_tiles
            if tile.terrain in _PASSABLE
        }
        frontier = {
            neighbor
            for x, y in passable
            for neighbor in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            if neighbor not in explored
        }
        origin = perception.own_position
        return [
            IntentTemplate(
                action_type="move_to",
                target=TileTarget(kind="tile", position=Coord(x=x, y=y)),
                parameters=EmptyParameters(),
                reason=None,
            )
            for x, y in sorted(passable | frontier, key=lambda xy: (xy[1], xy[0]))
            if 0 <= x < self._config.map_width
            and 0 <= y < self._config.map_height
            and 1 <= abs(x - origin.x) + abs(y - origin.y) <= 10
        ]

    def _categories(self, perception: Perception) -> list[list[IntentTemplate]]:
        needs, inventory = perception.own_condition, perception.own_inventory
        spring = any(
            tile.terrain == "spring" and _distance(tile.position, perception.own_position) <= 1
            for tile in perception.visible_tiles
        )
        nearby = [
            entity
            for entity in sorted(perception.visible_entities, key=lambda e: e.entity_id)
            if _distance(entity.position, perception.own_position) <= 1
        ]
        categories = [[WAIT]]
        if needs.stamina in ("critical", "low"):
            categories.append([_simple("rest")])
        if needs.stamina == "critical":
            categories.append([_simple("sleep")])
        if inventory.fruit_count > 0 and needs.satiety != "strong":
            categories.append([_simple("eat")])
        if spring and needs.hydration != "strong":
            categories.append(
                [
                    IntentTemplate(
                        action_type="drink",
                        target=None,
                        parameters=DrinkParameters(source="spring"),
                        reason=None,
                    )
                ]
            )
        if inventory.canteen_servings and needs.hydration != "strong":
            categories.append(
                [
                    IntentTemplate(
                        action_type="drink",
                        target=None,
                        parameters=DrinkParameters(source="canteen"),
                        reason=None,
                    )
                ]
            )
        if inventory.canteen_id is not None and spring:
            categories.append(
                [
                    IntentTemplate(
                        action_type="fill_canteen",
                        target=EntityTarget(kind="entity", id=inventory.canteen_id),
                        parameters=EmptyParameters(),
                        reason=None,
                    )
                ]
            )
        categories.extend(
            [
                [
                    IntentTemplate(
                        action_type="gather",
                        target=EntityTarget(kind="entity", id=e.entity_id),
                        parameters=EmptyParameters(),
                        reason=None,
                    )
                    for e in nearby
                    if e.entity_type == "fruit_tree" and e.fruit_band != "empty"
                ],
                [
                    IntentTemplate(
                        action_type="pick_up",
                        target=TileTarget(kind="tile", position=e.position),
                        parameters=ItemTransferParameters(
                            item_type="fruit" if e.entity_type == "ground_fruit" else "canteen",
                            quantity=1,
                        ),
                        reason=None,
                    )
                    for e in nearby
                    if e.entity_type in ("ground_fruit", "canteen")
                ],
                self._move_targets(perception),
            ]
        )
        return [category for category in categories if category]

    def decide(self, request: DecisionRequest) -> OkOutcome:
        def pick(stage: int, size: int) -> int:
            value = f"{self._config.seed}|{request.actor_id}|{request.decision_ordinal}|{stage}"
            return int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big") % size

        categories = self._categories(request.context.perception)
        category = categories[pick(0, len(categories))]
        plan = make_plan(request, [category[pick(1, len(category))]])
        return OkOutcome(status="ok", policy_id=self.policy_id, plan=plan)

    def export_state(self) -> dict[str, JsonValue]:
        return {}
