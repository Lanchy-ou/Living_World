"""Principal action failures, including authorization before live state lookup."""

import pytest
from test_engine_actions import CANTEEN, RYAN, TREE, content_with, failures, intent
from test_engine_movement import movement, tick

from living_island.world.ports import create_engine
from living_island.world.protocol import ActionIntent, Coord
from living_island.world.state import GroundFruitPile, ReceiptEntity, UniqueCanteenState

PICKUP = {"kind": "tile", "position": {"x": 2, "y": 2}}


@pytest.mark.parametrize(
    "action",
    [
        movement(3, 2),
        intent("gather", target=TREE),
        intent("eat"),
        intent("drink", source="spring"),
        intent("fill_canteen", target=CANTEEN),
        intent("rest"),
        intent("sleep"),
        intent("wait"),
        intent("talk", target=RYAN, speech_act="statement", text="Hello"),
        intent("give", target=RYAN, item_type="fruit", quantity=1),
        intent("pick_up", target=PICKUP, item_type="fruit", quantity=1),
    ],
    ids=lambda action: action.action_type,
)
def test_dead_submission_is_a_bounded_rejection_without_physical_effect(
    action: ActionIntent,
) -> None:
    content = content_with({"ella": (2, 2)})
    initial = create_engine(content, None).initial_commit()
    state = initial.snapshot
    state.residents[0].satiety = state.residents[0].health = 0
    engine = create_engine(content, state, initial.events)
    dead = tick(engine)
    rejected = tick(engine, action)
    assert failures(rejected) == ["DEAD"]
    assert rejected.snapshot.residents == dead.snapshot.residents
    assert rejected.snapshot.unique_canteen == dead.snapshot.unique_canteen
    assert not rejected.pending_deliveries


@pytest.mark.parametrize(
    ("action", "setup", "code"),
    [
        (movement(3, 2), "exhausted", "EXHAUSTED"),
        (movement(8, 2), "disconnected", "NO_PATH"),
        (movement(12, 2), "out-of-bounds", "INVALID_TARGET"),
        (movement(2, 0), "explored-sea", "PATH_BLOCKED"),
        (intent("gather", target=TREE), "exhausted", "EXHAUSTED"),
        (intent("gather", target=TREE), "full", "INVENTORY_FULL"),
        (intent("gather", target=TREE), "far", "OUT_OF_REACH"),
        (intent("gather", target=TREE), "hidden", "INVALID_TARGET"),
        (intent("gather", target=TREE), "empty-tree", "RESOURCE_TAKEN"),
        (intent("eat"), "sated", "NO_NEED"),
        (intent("eat"), "no-fruit", "NO_ITEM"),
        (intent("drink", source="canteen"), "hydrated", "NO_NEED"),
        (intent("drink", source="canteen"), "missing", "NO_ITEM"),
        (intent("drink", source="canteen"), "empty", "NO_WATER"),
        (intent("drink", source="spring"), "ordinary", "OUT_OF_REACH"),
        (intent("drink", source="spring"), "spring-sated", "NO_NEED"),
        (intent("fill_canteen", target=CANTEEN), "missing", "NO_ITEM"),
        (intent("fill_canteen", target=CANTEEN), "ordinary", "OUT_OF_REACH"),
        (intent("fill_canteen", target=CANTEEN), "by-spring", "ALREADY_FULL"),
        (intent("give", target=RYAN, item_type="fruit", quantity=2), "one-fruit", "NO_ITEM"),
        (
            intent("give", target=RYAN, item_type="canteen", quantity=1),
            "receiver-full",
            "INVENTORY_FULL",
        ),
        (
            intent("give", target=RYAN, item_type="canteen", quantity=1),
            "far-recipient",
            "OUT_OF_REACH",
        ),
        (intent("give", target=RYAN, item_type="canteen", quantity=1), "hidden", "INVALID_TARGET"),
        (
            intent(
                "give", target={"kind": "resident", "id": "ella"}, item_type="canteen", quantity=1
            ),
            "self-recipient",
            "INVALID_TARGET",
        ),
        (
            intent("give", target=RYAN, item_type="canteen", quantity=1),
            "dead-recipient",
            "INVALID_TARGET",
        ),
        (
            intent("pick_up", target=PICKUP, item_type="fruit", quantity=2),
            "ground-one",
            "ITEM_TAKEN",
        ),
        (
            intent("pick_up", target=PICKUP, item_type="fruit", quantity=1),
            "ground-full",
            "INVENTORY_FULL",
        ),
        (
            intent("pick_up", target=PICKUP, item_type="fruit", quantity=1),
            "ground-far",
            "OUT_OF_REACH",
        ),
        (
            intent("pick_up", target=PICKUP, item_type="fruit", quantity=1),
            "ground-hidden",
            "INVALID_TARGET",
        ),
        (
            intent("pick_up", target=PICKUP, item_type="canteen", quantity=1),
            "stale-canteen",
            "ITEM_TAKEN",
        ),
    ],
    ids=lambda value: value.action_type if isinstance(value, ActionIntent) else str(value),
)
def test_action_failure_codes(action: ActionIntent, setup: str, code: str) -> None:
    pos = (2, 2)
    if setup in {"by-spring", "spring-sated"}:
        pos = (9, 1)
    elif setup in {"far", "ground-far"}:
        pos = (1, 3)
    ryan = (2, 4) if setup == "far-recipient" else (2, 1)
    content = content_with({"ella": pos, "ryan": ryan})
    initial = create_engine(content, None).initial_commit()
    state = initial.snapshot
    actor, recipient = state.residents
    needs = content.config.needs
    if setup == "exhausted":
        actor.stamina = needs.min_value
    elif setup == "disconnected":
        state.explored_tiles_by_resident[0].tile_indices = [
            2 * content.config.map.width + x for x in (2, 8)
        ]
    elif setup == "sated":
        actor.satiety = needs.max_value
        actor.fruit_count = 1
    elif setup == "hydrated":
        actor.hydration = needs.max_value
    elif setup == "spring-sated":
        actor.hydration = needs.max_value
    elif setup in {"missing", "stale-canteen"}:
        state.unique_canteen = UniqueCanteenState(
            id="canteen_01",
            holder_id="ryan",
            ground_position=None,
            servings=1,
        )
    elif setup == "empty":
        state.unique_canteen.servings = 0
    elif setup == "one-fruit":
        actor.fruit_count = 1
    elif setup == "receiver-full":
        recipient.fruit_count = content.config.inventory.slot_capacity
    elif setup == "hidden":
        state.exposure_receipts_by_resident[0].entities = []
    elif setup == "empty-tree":
        state.fruit_nodes[0].stock = 0
    elif setup == "dead-recipient":
        assert any(
            e.entity_id == recipient.id for e in state.exposure_receipts_by_resident[0].entities
        )
        recipient.satiety = recipient.health = 0
    elif setup == "explored-sea":
        assert 2 in state.explored_tiles_by_resident[0].tile_indices
    if setup in {"full", "ground-full"}:
        actor.fruit_count = content.config.inventory.slot_capacity - 1
    if setup.startswith("ground-"):
        position = Coord(x=2, y=2)
        state.ground_fruit = [GroundFruitPile(position=position, quantity=1)]
        if setup != "ground-hidden":
            group = state.exposure_receipts_by_resident[0]
            group.entities = sorted(
                [
                    *group.entities,
                    ReceiptEntity(
                        entity_id="ground_fruit@2,2",
                        entity_type="ground_fruit",
                        position=position,
                    ),
                ],
                key=lambda e: (e.entity_id, e.position.y, e.position.x),
            )
    engine = create_engine(content, state, initial.events)
    if setup == "dead-recipient":
        assert not tick(engine).snapshot.residents[1].alive
    result = tick(engine, action)
    assert failures(result) == [code]
    assert result.snapshot.unique_canteen == state.unique_canteen
    assert [r.fruit_count for r in result.snapshot.residents] == [
        actor.fruit_count,
        recipient.fruit_count,
    ]
