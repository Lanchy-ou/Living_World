"""Movement through the world ports, including captured per-step perceptions."""

from world_builders import tiny_content

from living_island.world.content import build_world_content, map_bytes_from_rows
from living_island.world.facts import ActionFailedPayload, ResidentMovedPayload
from living_island.world.ports import WorldEngine, WorldTickCommit, create_engine
from living_island.world.protocol import ActionIntent, Coord, EmptyParameters, TileTarget

ROWS = [
    "~~~~~~~~~~~~",
    "~..M......S~",
    "~..F.......~",
    "~.C........~",
    "~..........~",
    "~~~~~~~~~~~~",
]


def movement(x: int, y: int) -> ActionIntent:
    return ActionIntent(
        intent_id="move",
        plan_id="plan",
        actor_id="ella",
        action_type="move_to",
        target=TileTarget(kind="tile", position=Coord(x=x, y=y)),
        parameters=EmptyParameters(),
        reason=None,
    )


def tick(engine: WorldEngine, *intents: ActionIntent) -> WorldTickCommit:
    engine.begin_tick()
    for intent in intents:
        engine.start_intent(intent)
    return engine.advance_tick()


def test_move_uses_adjacent_steps_and_captures_transient_sighting() -> None:
    content = tiny_content(
        ROWS,
        {"ella": (2, 3), "ryan": (3, 4)},
        day_radius_tiles=1,
        night_radius_tiles=1,
    )
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    assert initial.events[0].type == "world_initialized"
    assert not initial.pending_deliveries[0].perception.transient_sightings
    result = tick(engine, movement(4, 3))
    moved = [e.payload for e in result.events if isinstance(e.payload, ResidentMovedPayload)]
    assert [(e.from_.x, e.to.x) for e in moved] == [(2, 3), (3, 4)]
    assert sum(e.step_cost_units for e in moved) <= content.config.map.walk_cost_budget_per_tick
    view = result.pending_deliveries[0].perception
    assert [(s.entity_id, s.seen_at_step) for s in view.transient_sightings] == [
        ("fruit_01", 1),
        ("ryan", 1),
    ]
    receipts = result.snapshot.exposure_receipts_by_resident[0].entities
    assert any(e.entity_id == "fruit_01" for e in receipts)
    assert initial.snapshot.residents[0].position.x == 2


def test_unexplored_non_frontier_is_invalid_and_water_frontier_blocks() -> None:
    content = tiny_content(
        ROWS,
        {"ella": (2, 4)},
        day_radius_tiles=1,
        night_radius_tiles=1,
    )
    for target, expected in [((9, 4), "INVALID_TARGET"), ((3, 5), "PATH_BLOCKED")]:
        engine = create_engine(content, None)
        engine.initial_commit()
        result = tick(engine, movement(*target))
        failures = [e.payload for e in result.events if isinstance(e.payload, ActionFailedPayload)]
        assert [p.failure_code for p in failures] == [expected]
        assert result.snapshot.residents[0].position.y == 4


def test_frontier_actual_cost_waits_for_the_next_budget() -> None:
    rows = [*ROWS]
    rows[4] = rows[4][:6] + "W" + rows[4][7:]
    base = tiny_content(
        rows,
        {"ella": (4, 4)},
        day_radius_tiles=1,
        night_radius_tiles=1,
    )
    config = base.config.model_dump()
    config["map"]["walk_cost_budget_per_tick"] = 2
    content = build_world_content(config, map_bytes_from_rows(rows))
    engine = create_engine(content, None)
    first = engine.initial_commit()
    assert not any(
        tile.position.x == 6 for tile in first.pending_deliveries[0].perception.visible_tiles
    )
    first_move = tick(engine, movement(6, 4))
    assert first_move.snapshot.residents[0].position == Coord(x=5, y=4)
    assert first_move.snapshot.active_actions[0].route_cursor == 1
    second_move = tick(engine)
    steps = [e.payload for e in second_move.events if isinstance(e.payload, ResidentMovedPayload)]
    assert [step.step_cost_units for step in steps] == [2]
    assert second_move.snapshot.residents[0].position == Coord(x=6, y=4)
    assert not second_move.snapshot.active_actions
