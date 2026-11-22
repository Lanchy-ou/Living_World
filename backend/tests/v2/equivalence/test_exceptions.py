"""Pin the WAP-26 outcomes at actual compatibility-engine boundaries."""

import pytest


@pytest.fixture
def world(tmp_path):
    from living_island.sim.v2.cli import load_inputs, setup_world

    bound, config = load_inputs("mechanics", 20261108, tmp_path)
    return setup_world(bound, config)


def _step(world, actor, template):
    from living_island.sim.v2.compat.adapters import adapt_intent
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.protocol import ActionIntent

    packets = {packet.actor_id: packet for packet in world.pending_packets()}
    request = TurnRequest(packets[actor], world.state.turn_ordinals[actor], ("start",))
    legacy = ActionIntent(
        **template.model_dump(),
        actor_id=actor,
        plan_id="wap26",
        intent_id=f"wap26-{world.tick}",
    )
    turn = request.bind(adapt_intent(legacy, 48))
    opening = world.state
    result = world.step(
        (turn,), acknowledged={key: packet.delivery_id for key, packet in packets.items()}
    )
    return turn, opening, result


def _advance(world):
    return world.step(
        acknowledged={packet.actor_id: packet.delivery_id for packet in world.pending_packets()}
    )


@pytest.mark.parametrize(
    ("target_state", "expected_name", "expected_failure"),
    [
        ("receipted-far", "gather-exhausted-unreachable", "OUT_OF_REACH"),
        ("receipted-missing", "gather-exhausted-receipted-missing", "INVALID_TARGET"),
        ("unreceipted", None, "INVALID_TARGET"),
    ],
)
def test_wap26_gather(world, target_state, expected_name, expected_failure):
    from living_island.sim.equivalence.v1_extract import action, target
    from living_island.sim.equivalence.v2_extract import DeclaredException, declared_exceptions
    from living_island.world.v2.protocol import Coord

    state = world.state
    assert "fruit_01" in state.exposure_receipts_by_resident["ella"].entities
    state.needs["ella"]["stamina"] = 0
    if target_state == "receipted-far":
        state.residents["ella"].position = Coord(x=1, y=4)
    elif target_state == "receipted-missing":
        del state.entities["fruit_01"]
    else:
        del state.exposure_receipts_by_resident["ella"].entities["fruit_01"]

    turn, opening, result = _step(world, "ella", action("gather", target("entity", "fruit_01")))
    [terminal] = result.actions
    assert (
        terminal.outcome,
        terminal.failure_code,
        terminal.tick_started,
        terminal.tick_finished,
    ) == (
        "failure",
        expected_failure,
        0,
        1,
    )
    expected_hits = [] if expected_name is None else [DeclaredException(expected_name, 0, "ella")]
    assert declared_exceptions(opening, world.pack, (turn,)) == expected_hits


def test_wap26_full_without_canteen(world):
    from living_island.sim.equivalence.v1_extract import action
    from living_island.sim.equivalence.v2_extract import DeclaredException, declared_exceptions

    world.state.needs["ella"]["hydration"] = 10000
    turn, opening, result = _step(world, "ella", action("drink", source="canteen"))
    [terminal] = result.actions
    assert (
        terminal.outcome,
        terminal.failure_code,
        terminal.tick_started,
        terminal.tick_finished,
    ) == (
        "failure",
        "NO_ITEM",
        0,
        1,
    )
    assert declared_exceptions(opening, world.pack, (turn,)) == [
        DeclaredException("drink-full-without-canteen", 0, "ella")
    ]


@pytest.mark.parametrize("first_reply", ["accept", "refuse"])
def test_wap26_second_reply(world, first_reply):
    from living_island.sim.equivalence.v1_extract import talk
    from living_island.sim.equivalence.v2_extract import DeclaredException, declared_exceptions
    from living_island.world.v2.protocol import Coord

    world.state.residents["ryan"].position = Coord(x=2, y=3)
    _, _, requested = _step(
        world, "ella", talk("ryan", "request", request={"item_type": "fruit", "quantity": 1})
    )
    request_id = requested.utterances["ella"].utterance_id
    assert request_id is not None
    turn, opening, accepted = _step(
        world, "ryan", talk("ella", first_reply, in_reply_to=request_id)
    )
    assert accepted.utterances["ryan"].failure_code is None
    assert declared_exceptions(opening, world.pack, (turn,)) == []
    turn, opening, repeated = _step(world, "ryan", talk("ella", "accept", in_reply_to=request_id))
    assert repeated.utterances["ryan"].failure_code == "INVALID_REPLY"
    assert repeated.utterances["ryan"].utterance_id is None
    assert declared_exceptions(opening, world.pack, (turn,)) == [
        DeclaredException(f"reply-after-{first_reply}", 2, "ryan")
    ]


@pytest.mark.parametrize(
    ("servings", "outcome", "failed_check"),
    [
        (1, "applied", None),
        (2, "unmet", "room"),
    ],
)
def test_ct16_canteen_fill(world, servings, outcome, failed_check):
    from living_island.sim.equivalence.v1_extract import action, target
    from living_island.sim.equivalence.v2_extract import snapshot
    from living_island.world.v2 import protocol as v2
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.state import Lineage
    from living_island.world.v2.engine.tick import EventWriter, TickContext

    state = world.state
    state.residents["ryan"].position = v2.Coord(x=9, y=1)
    water = state.entities["canteen_01_water"]
    water.quantity = servings
    water.lineage = (Lineage(water.entity_id, 0, servings, 1),)
    build_deliveries(TickContext(state, world.pack, EventWriter(state, 0)))
    _, _, result = _step(world, "ryan", action("fill_canteen", target("entity", "canteen_01")))
    [terminal] = result.actions
    assert terminal.settlement is not None
    assert terminal.settlement.kind == outcome
    assert terminal.settlement.failed_check == failed_check
    assert terminal.visible_feedback.phenomena == ["fills_up" if servings == 1 else "already_full"]
    assert snapshot(world, "canteen_01").canteen.servings == 2


def test_en01_last_fruit_settles_before_regrowth(world):
    from living_island.sim.equivalence.v1_extract import action, target
    from living_island.sim.equivalence.v2_extract import snapshot
    from living_island.world.v2.protocol import boundary_delivery_id

    state = world.state
    state.tick = 142
    state.clock_minute = state.clock.minute_at(142)
    state.entities["fruit_01"].components["store"]["count"] = 1
    for actor, packet in state.pending_deliveries.items():
        state.pending_deliveries[actor] = packet.model_copy(
            update={
                "observed_tick": state.tick,
                "delivery_id": boundary_delivery_id(state.run_id, state.tick, actor),
                "perception": packet.perception.model_copy(update={"tick": state.tick}),
            }
        )
    _, _, started = _step(world, "ella", action("gather", target("entity", "fruit_01")))
    assert not started.actions
    assert snapshot(world, "canteen_01").trees[0].stock == 1
    opening_stamina = world.state.needs["ella"]["stamina"]
    result = _advance(world)
    [terminal] = result.actions
    assert terminal.settlement is not None and terminal.settlement.kind == "applied"
    assert terminal.tick_finished == 144
    assert [
        event.type for event in result.events if event.type in ("act_settled", "world_rule_applied")
    ] == [
        "act_settled",
        "world_rule_applied",
    ]
    projection = snapshot(world, "canteen_01")
    assert projection.trees[0].stock == 1
    ella = projection.residents[0]
    assert (ella.fruit_count, ella.stamina) == (1, opening_stamina - 300 - 40)


@pytest.mark.parametrize(
    ("satiety", "hydration", "health"),
    [
        (2525, 2600, 9000),
        (2525, 2601, 9000),
        (2526, 2600, 9000),
        (2526, 2601, 9015),
        (25, 100, 8930),
    ],
)
def test_en12_compat_sleep_thresholds(world, satiety, hydration, health):
    from living_island.sim.equivalence.v1_extract import action

    world.state.needs["ella"].update(satiety=satiety, hydration=hydration, health=9000)
    _, _, result = _step(world, "ella", action("sleep"))
    assert not result.actions
    values = world.state.needs["ella"]
    assert (values["satiety"], values["hydration"], values["health"]) == (
        satiety - 25,
        hydration - 100,
        health,
    )


def test_en12_compat_final_sleep_tick_recovers(world):
    from living_island.sim.equivalence.v1_extract import action

    world.state.needs["ella"].update(satiety=9000, hydration=9000)
    _step(world, "ella", action("sleep"))
    while world.tick < 47:
        assert not _advance(world).actions
    opening = world.state.needs["ella"]
    opening.update(satiety=9000, hydration=9000, health=9000)
    [terminal] = _advance(world).actions
    assert terminal.tick_finished == 48
    assert terminal.settlement is not None and terminal.settlement.kind == "applied"
    values = world.state.needs["ella"]
    assert (values["satiety"], values["hydration"], values["health"]) == (8975, 8900, 9015)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b"talk_ticks = 1", b"talk_ticks = 2"),
        (b"sleep_ticks = 48", b"sleep_ticks = 60"),
        (b"fruit_few_max = 2", b"fruit_few_max = 3"),
        (b"capacity_servings = 2", b"capacity_servings = 3"),
        (b"capacity_servings = 2", b"capacity_servings = 3999"),
    ],
)
def test_ct15_ct17_refusals(tmp_path, before, after):
    from living_island.sim.v2.cli import PACK, VOCABULARY, load_inputs
    from living_island.sim.v2.compat.config import load_compat_pack
    from living_island.world.v2.rules import load_vocabulary

    bound, _ = load_inputs("production", 20261108, tmp_path)
    raw = (tmp_path / "production.toml").read_bytes()
    assert raw.count(before) == 1
    path = tmp_path / "changed.toml"
    path.write_bytes(raw.replace(before, after))
    with pytest.raises(ValueError, match="unregistered v1 config blob SHA-256"):
        load_compat_pack(
            path,
            PACK,
            load_vocabulary(VOCABULARY),
            map_path=tmp_path / f"{bound.manifest.map_blob_sha256}.map",
        )
