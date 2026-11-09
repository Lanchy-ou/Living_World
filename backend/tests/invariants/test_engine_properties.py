"""World invariants and deterministic re-execution through the real engine."""

from hypothesis import given, settings
from hypothesis import strategies as st
from test_engine_actions import TREE, content_with, intent
from test_engine_movement import tick

from living_island.world.canteen import check_canteen
from living_island.world.content import canonical_json_bytes
from living_island.world.facts import ResidentMovedPayload
from living_island.world.ports import create_engine
from living_island.world.protocol import ActionIntent, Coord
from living_island.world.resources import check_fruit_conservation
from living_island.world.space import StaticMap
from living_island.world.state import ResidentPhysicalState, WorldState

KINDS = ("move_to", "gather", "eat", "drink", "give", "pick_up", "rest", "sleep", "wait")


def select_intent(state: WorldState, actor: ResidentPhysicalState, kind: str) -> ActionIntent:
    args = {"actor": actor.id, "id": f"{state.tick}:{actor.id}"}
    position = actor.position
    if kind == "move_to":
        target = Coord(x=position.x, y=2 if position.y == 3 else 3)
        return intent("move_to", target={"kind": "tile", "position": target}, **args)
    if kind == "gather":
        return intent("gather", target=TREE, **args)
    if kind == "eat":
        return intent("eat", **args)
    if kind == "drink":
        return intent("drink", source="canteen", **args)
    if kind == "give":
        other = "ryan" if actor.id == "ella" else "ella"
        return intent(
            "give", target={"kind": "resident", "id": other}, item_type="fruit", quantity=1, **args
        )
    if kind == "pick_up":
        return intent(
            "pick_up",
            target={"kind": "tile", "position": position},
            item_type="canteen",
            quantity=1,
            **args,
        )
    if kind == "rest":
        return intent("rest", **args)
    if kind == "sleep":
        return intent("sleep", **args)
    return intent("wait", **args)


@given(
    seed=st.integers(min_value=1, max_value=0xFFFFFFFF),
    commands=st.lists(
        st.tuples(st.sampled_from(KINDS), st.sampled_from(KINDS)), min_size=4, max_size=14
    ),
    harsh=st.booleans(),
)
@settings(max_examples=30, deadline=None)
def test_engine_invariants_and_reexecution(seed, commands, harsh) -> None:
    needs = (
        {"initial_hydration": 300, "hydration_decay_per_tick": 80, "initial_health": 600}
        if harsh
        else {}
    )
    content = content_with(
        {"ella": (2, 2), "ryan": (4, 2)},
        meta={"seed": seed},
        needs=needs,
        fruit={"regrow_ticks": 3},
        actions={"rest_ticks": 2, "sleep_ticks": 2},
    )
    smap = StaticMap.from_content(content)
    engine = create_engine(content, None)
    twin = create_engine(content, None)
    previous = engine.initial_commit()
    assert previous == twin.initial_commit()
    known_ids = {e.event_id for e in previous.events}
    grown = consumed = 0
    for index, pair in enumerate(commands):
        if index == len(commands) // 2:
            saved = WorldState.model_validate_json(previous.snapshot.model_dump_json())
            twin = create_engine(content, saved)
        active = {a.intent.actor_id for a in previous.snapshot.active_actions}
        inputs = [
            select_intent(previous.snapshot, actor, kind)
            for actor, kind in zip(previous.snapshot.residents, pair, strict=True)
            if actor.alive and actor.id not in active
        ]
        commit = tick(engine, *inputs)
        repeated = tick(twin, *reversed(inputs))
        assert canonical_json_bytes(commit.model_dump(mode="json")) == canonical_json_bytes(
            repeated.model_dump(mode="json")
        )
        state = commit.snapshot
        assert state.tick == previous.snapshot.tick + 1
        check_fruit_conservation(content.config, state)
        check_canteen(content.config, state)
        positions = {r.id: r.position for r in previous.snapshot.residents}
        costs = {r.id: 0 for r in previous.snapshot.residents}
        for sequence, event in enumerate(commit.events):
            assert (event.tick, event.seq_in_tick) == (state.tick, sequence)
            assert all(cause in known_ids for cause in event.caused_by_event_ids)
            assert event.event_id not in known_ids
            known_ids.add(event.event_id)
            payload = event.payload
            if isinstance(payload, ResidentMovedPayload):
                actor_id = event.actor_id
                assert payload.from_ == positions[actor_id]
                assert (
                    abs(payload.from_.x - payload.to.x) + abs(payload.from_.y - payload.to.y) == 1
                )
                assert payload.step_cost_units == smap.step_cost(payload.to.x, payload.to.y)
                costs[actor_id] += payload.step_cost_units
                positions[actor_id] = payload.to
            elif event.type == "fruit_regrew":
                grown += payload.quantity
            elif event.type == "fruit_consumed":
                consumed += payload.quantity
        assert state.event_log_cursor == len(known_ids)
        assert (state.lifetime_fruit_regrown, state.lifetime_fruit_consumed) == (grown, consumed)
        assert [d.actor_id for d in commit.pending_deliveries] == [
            r.id for r in state.residents if r.alive
        ]
        for actor in state.residents:
            assert actor.position == positions[actor.id]
            assert costs[actor.id] <= content.config.map.walk_cost_budget_per_tick
            for field in (actor.satiety, actor.hydration, actor.stamina, actor.health):
                assert type(field) is int
                assert content.config.needs.min_value <= field <= content.config.needs.max_value
            if not actor.alive:
                assert actor.fruit_count == 0
                assert all(a.intent.actor_id != actor.id for a in state.active_actions)
        previous = commit
