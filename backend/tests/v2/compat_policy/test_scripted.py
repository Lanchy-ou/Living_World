"""Exercise §11.2 with the independent PR-03 scripted v1 projections."""

from __future__ import annotations

import importlib
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "backend/tests/fixtures/v1_projection/scripted"
CASES = tuple(
    file.name.removesuffix(".json.gz")
    for file in sorted(FIXTURES.glob("wap*.json.gz"))
    if file.name.startswith(("wap23-", "wap28-", "wap30-", "wap35-"))
)


@pytest.fixture(scope="module")
def archive():
    # Keep v2 modules out of collection for the frozen v1 registration tests.
    from living_island.sim.equivalence.v1_extract import scripted_projections
    from living_island.world.v2.rules import load_vocabulary

    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(ROOT / "scripts"))
        generator = importlib.import_module("gen_v1_projections")
        registry = generator.load_registry(ROOT)
        mechanics, _ = generator.effective("mechanics", *registry["mechanics"], 20261108)
        cases = {name: run.__self__ for name, _, _, run in scripted_projections(mechanics)}
        vocabulary = load_vocabulary(ROOT / "content/vocabulary/vocab-0.1.toml")
        yield generator, registry, cases, vocabulary


def load_case(archive, tmp_path, name):
    from living_island.sim.equivalence.projection import read_projection
    from living_island.sim.v2.compat.config import load_compat_pack

    generator, registry, cases, vocabulary = archive
    projection = read_projection(FIXTURES / f"{name}.json.gz")
    case = cases[name]
    raw, map_bytes = registry[case.config]
    source, layout = tmp_path / "source.toml", tmp_path / "island.map"
    source.write_bytes(raw)
    layout.write_bytes(map_bytes)
    bound = load_compat_pack(
        source, ROOT / "content/packs/compat-v1", vocabulary, map_path=layout, seed=case.seed
    )
    content, _ = generator.effective(case.config, raw, map_bytes, case.seed)
    return bound, content, case, projection


def seeded_world(bound, content, case, *, native_pack=None):
    from living_island.world.engine import Engine
    from living_island.world.protocol import TERRAIN_BY_SYMBOL
    from living_island.world.v2 import protocol as v2
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.state import (
        DialogueSession,
        Entity,
        Held,
        Inside,
        Lineage,
        OnTile,
    )
    from living_island.world.v2.engine.tick import EventWriter, TickContext
    from living_island.world.v2.engine.validate import (
        ClockConfig,
        CueSetup,
        DialogueConfig,
        MapConfig,
        ResidentSetup,
        SensesConfig,
        WorldSetup,
    )

    def point(legacy):
        return v2.Coord(x=legacy.x, y=legacy.y)

    cfg = content.config
    original = Engine(content, None, ())._state
    if case.setup is not None:
        case.setup(original, cfg)
    spec = cfg.perception
    pack = bound.pack if native_pack is None else native_pack
    world = initialize(
        pack,
        WorldSetup(
            world_id=cfg.meta.world_id,
            run_id=cfg.meta.run_id,
            seed=cfg.meta.seed,
            config_hash=bound.manifest.effective_config_sha256,
            map_hash=bound.manifest.map_sha256,
            static_map_ref="island.map",
            pack_ids=pack.pack_ids,
            terrain=MapConfig(
                rows=tuple(
                    tuple(TERRAIN_BY_SYMBOL[symbol] for symbol in line) for line in bound.map_rows
                ),
                step_costs={
                    key: getattr(cfg.map, f"step_cost_{key}")
                    for key in ("beach", "grass", "woods", "cave", "damp_moss", "fruit_tree")
                },
                walk_budget=cfg.map.walk_cost_budget_per_tick,
                opaque_terrains=frozenset(("woods", "fruit_tree", "rock")),
            ),
            clock=ClockConfig(
                tick_minutes=cfg.time.tick_minutes,
                start_minute=cfg.time.start_hour * 60,
                day_start_minute=cfg.time.day_start_hour * 60,
                day_end_minute=cfg.time.day_end_hour * 60,
            ),
            senses=SensesConfig(
                day_radius=spec.day_radius_tiles,
                night_radius=spec.night_radius_tiles,
                hearing_radius=spec.hearing_radius_tiles,
                cue_detail_radius=spec.cue_detail_radius_tiles,
                visible_weakness_below=spec.visible_weakness_health_below,
                visible_dehydration_below=spec.visible_dehydration_hydration_below,
                visible_fatigue_below=spec.visible_fatigue_stamina_below,
            ),
            dialogue=DialogueConfig(
                max_turns=cfg.social.max_dialogue_turns,
                gap_ticks=cfg.social.dialogue_gap_ticks,
                cooldown_ticks=cfg.social.dialogue_cooldown_ticks,
            ),
            residents=tuple(
                ResidentSetup(id=r.id, position=point(r.position)) for r in original.residents
            ),
            cues=tuple(
                CueSetup(
                    id=cue.id,
                    kind=cue.kind,
                    position=v2.Coord(x=cue.position[0], y=cue.position[1]),
                    visible_description=cue.visible_description,
                    near_description=cue.near_description,
                    direction=cue.direction,
                )
                for cue in cfg.world.cues
            ),
        ),
    )
    if native_pack is not None:
        return world
    state = world.state
    for actor in original.residents:
        state.needs[actor.id] = {key: getattr(actor, key) for key in state.needs[actor.id]}
    for tree in original.fruit_nodes:
        state.entities[tree.id].components["store"]["count"] = tree.stock
    canteen = original.unique_canteen
    state.entities[canteen.id].place = Held(canteen.holder_id)
    state.entities[canteen.id].owner_id = canteen.holder_id
    water = state.entities[f"{canteen.id}_water"]
    if canteen.servings:
        water.quantity = canteen.servings
        water.lineage = (Lineage(water.entity_id, 0, water.quantity, 1),)
    else:
        del state.entities[water.entity_id]
    stacks = [(Held(actor.id), actor.id, actor.fruit_count) for actor in original.residents]
    stacks.extend(
        (OnTile(point(pile.position)), None, pile.quantity) for pile in original.ground_fruit
    )
    for n, (place, owner, count) in enumerate(stacks):
        if count:
            key = f"fixture_fruit_{n}"
            state.entities[key] = Entity(
                key,
                "fruit",
                "fruit",
                count,
                0,
                owner,
                place,
                {"portable": {"slots_per_unit": 1}},
                {},
                {},
                (),
                True,
                (Lineage(key, 0, count, n + 10),),
            )
    for row in original.dialogue_sessions:
        pair = tuple(row.pair_ids)
        state.dialogue_sessions[pair] = DialogueSession(
            pair, row.turn_count, row.last_utterance_tick, row.cooldown_until_tick
        )
    for footprint in original.explored_tiles_by_resident:
        state.explored_tiles_by_resident[footprint.resident_id].update(footprint.tile_indices)

    if case.start:
        from living_island.sim.v2.turns import TurnRequest

        # PR-03 bootstraps the opening night observation one inert tick earlier.
        state.tick = case.start - 1
        state.clock_minute = state.clock.minute_at(state.tick)
        for actor in state.residents:
            state.explored_tiles_by_resident[actor].clear()
            packet = state.pending_deliveries[actor]
            state.pending_deliveries[actor] = packet.model_copy(
                update={
                    "observed_tick": state.tick,
                    "delivery_id": v2.boundary_delivery_id(state.run_id, state.tick, actor),
                    "perception": packet.perception.model_copy(update={"tick": state.tick}),
                }
            )
        # Give the native runner an ordinary action-ended turn at the dusk bootstrap.
        opening = world.pending_packets()
        world.step(
            [TurnRequest(packet, 0, ("start",)).bind(_wait_choice()) for packet in opening],
            acknowledged={packet.actor_id: packet.delivery_id for packet in opening},
        )
    else:
        build_deliveries(TickContext(state, world.pack, EventWriter(state, 0)))
    assert all(
        isinstance(item.place, Inside)
        for item in state.entities.values()
        if item.archetype_id == "water"
    )
    return world


def hosts_for(bound, content, case, mode, restored=None):
    from living_island.agents.types import OwnProfile
    from living_island.sim.equivalence.v1_extract import FixturePolicy, script_policy_config
    from living_island.sim.v2.compat.bridge import LegacyBridge
    from living_island.sim.v2.compat.policy_host import PolicyHost

    cfg = content.config
    bridge = LegacyBridge(bound) if mode == "bridge" else None
    overrides = {(actor, tick + case.start): plan for (actor, tick), plan in case.plans.items()}
    return {
        actor.id: PolicyHost(
            script_policy_config(cfg),
            OwnProfile(profile_id=actor.profile_id, initial_goal=actor.initial_goal),
            cfg.actions.sleep_ticks,
            bridge=bridge,
            restored=None if restored is None else restored[actor.id],
            policy_factory=partial(FixturePolicy, overrides=overrides, observed=case.observed),
        )
        for actor in cfg.residents
    }


def outcome(result):
    return (
        result.intent_id,
        result.status,
        result.failure_code or result.interruption_reason,
        result.tick_started,
        result.tick_finished,
    )


def assert_plan(actual, expected, actual_heard, expected_heard):
    from living_island.world.protocol import TalkParameters

    expected_plan = type(actual).model_validate(expected).plan
    for left, right in zip(actual.plan.intents, expected_plan.intents, strict=True):
        assert (left.intent_id, left.action_type, left.target) == (
            right.intent_id,
            right.action_type,
            right.target,
        )
        params = left.parameters
        reference = right.parameters
        if isinstance(params, TalkParameters) and isinstance(reference, TalkParameters):
            if params.in_reply_to != reference.in_reply_to:
                spoken = next(u for u in actual_heard if u.utterance_id == params.in_reply_to)
                prior = next(
                    u for u in expected_heard if u["utterance_id"] == reference.in_reply_to
                )
                assert (spoken.speaker_id, spoken.addressee_id, spoken.speech_act, spoken.text) == (
                    prior["speaker_id"],
                    prior["addressee_id"],
                    prior["speech_act"],
                    prior["text"],
                )
                params = params.model_copy(update={"in_reply_to": reference.in_reply_to})
        assert params == reference


@pytest.mark.parametrize("mode", ("bridge", "visible"))
@pytest.mark.parametrize("name", CASES)
def test_scripted_migration(archive, tmp_path, name, mode):
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.compat.adapters import legacy_speech, project_perception
    from living_island.sim.v2.compat.policy_host import (
        PolicyCheckpoint,
        PolicySession,
        restore_policies,
    )
    from living_island.world.v2 import protocol as v2

    bound, content, case, projection = load_case(archive, tmp_path, name)
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    first_tick = world.tick
    initial = None
    if first_tick:
        initial = {}
        for packet in world.pending_packets():
            view = project_perception(packet.perception)
            start = PolicyCheckpoint()
            receipts, _ = start.receipts.ingest(view)
            initial[packet.actor_id] = PolicyCheckpoint(
                cursor=first_tick - 1, receipts=receipts, deferred=("PLAN_FINISHED",)
            )
    hosts = hosts_for(bound, content, case, mode, initial)
    session = PolicySession(world, hosts, journal)
    assert projection.scripted_evidence is not None
    previous = None
    for frame, expected in zip(projection.frames, projection.scripted_evidence, strict=True):
        tick = world.tick
        assert tick == frame.tick
        if tick == case.restore_after or (
            name == "wap30-interruption-long-successor" and tick == 2
        ):
            if name == "wap30-interruption-long-successor":
                assert hosts["ella"].checkpoint().handled_stops == ("ella:t000000:a",)
            path = tmp_path / "checkpoint.json"
            save_checkpoint(
                path,
                world,
                journal,
                session.checkpoint(),
                first_journal_tick=first_tick,
            )
            restored = load_checkpoint(path, bound.pack, journal)
            world = restored.world
            hosts = hosts_for(
                bound,
                content,
                case,
                mode,
                restore_policies(restored.sim_checkpoint),
            )
            session = PolicySession(world, hosts, journal)
        packets = {packet.actor_id: packet for packet in world.pending_packets()}
        inputs = {packet["actor_id"]: packet for packet in expected["deliveries"]}
        expected_receipts = {entry["resident_id"]: entry for entry in expected["receipts"]}
        assert packets.keys() == inputs.keys()
        before = {key: host.checkpoint() for key, host in hosts.items()}
        expected_queues = {plan["actor_id"]: plan["intents"] for plan in expected["queued_plans"]}
        expected_decisions = {record["actor_id"]: record for record in expected["decision_records"]}
        if previous is not None:
            spoken = []
            for event in previous.events:
                if event.type == "utterance_spoken":
                    payload = event.payload
                    speech = v2.Utterance.model_validate(
                        {
                            key: payload[key]
                            for key in (
                                "addressee_id",
                                "speech_act",
                                "text",
                                "terms",
                                "in_reply_to",
                            )
                        }
                    )
                    act, kind, quantity = legacy_speech(event.actor_id, speech)
                    spoken.append(
                        (event.actor_id, speech.addressee_id, act, speech.text, kind, quantity)
                    )
            assert spoken == [
                (
                    u.speaker,
                    u.addressee,
                    u.act,
                    u.text,
                    u.request.item_type if u.request else None,
                    u.request.quantity if u.request else None,
                )
                for u in frame.utterances
            ]
        previous = session.advance()
        assert previous is not None
        opening = session.runner.manifest.boundaries[-1]
        for actor, host in hosts.items():
            legacy_outcomes = [item for item in frame.outcomes if item.actor_id == actor]
            if actor not in packets:
                assert not host.checkpoint().queue
                assert actor not in {submission.actor_id for submission in opening.submissions}
                if mode == "bridge":
                    assert [
                        outcome(item)
                        for item in host.checkpoint().terminal_results
                        if item.tick_finished == tick
                    ] == [
                        (
                            item.intent_id,
                            item.status,
                            item.code,
                            item.tick_started,
                            item.tick_finished,
                        )
                        for item in legacy_outcomes
                    ]
                continue
            checkpoint = host.checkpoint()
            assert [
                trigger for trigger in checkpoint.boundary_triggers if trigger != "PLAN_FINISHED"
            ] == inputs[actor]["decision_triggers"]
            expected_feedback = inputs[actor]["perception"]["last_action_feedback"]
            assert [outcome(item) for item in checkpoint.boundary_results] == [
                (item.intent_id, item.status, item.code, item.tick_started, item.tick_finished)
                for item in legacy_outcomes
            ]
            if expected_feedback is not None:
                assert checkpoint.boundary_results[-1].visible_feedback.model_dump(
                    exclude={"visible_effects"}
                ) == {k: v for k, v in expected_feedback.items() if k != "visible_effects"}
            view = project_perception(packets[actor].perception)
            legacy = inputs[actor]["perception"]

            # PRE-ingest v1 discards the failed or interrupted tail at world commit.
            if not any(item.status != "success" for item in legacy_outcomes):
                assert [intent.action_type for intent in before[actor].queue] == [
                    intent["action_type"] for intent in expected_queues.get(actor, ())
                ]
            record = expected_decisions.get(actor)
            if record is None:
                assert checkpoint.last_decision_tick != tick
                assert set(checkpoint.deferred) == (
                    set(before[actor].deferred) | set(inputs[actor]["decision_triggers"])
                )
            else:
                actual = host.decision_records[-1]
                assert actual.tick == tick
                assert actual.triggers == record["triggers"]
                assert_plan(actual, record, view.heard_utterances, legacy["heard_utterances"])
                if any(item.status != "success" for item in legacy_outcomes):
                    prior_tail = {intent.intent_id for intent in before[actor].queue}
                    assert prior_tail.isdisjoint(intent.intent_id for intent in checkpoint.queue)
            failed = before[actor].policy_state
            assert (
                []
                if failed is None
                else [entry.model_dump(mode="json") for entry in failed.failed_targets]
            ) == (expected["policy_states"][actor]["failed_targets"])
            assert view.own_inventory.model_dump() == legacy["own_inventory"]
            assert view.own_condition.model_dump() == legacy["own_condition"]
            assert view.own_position.model_dump() == legacy["own_position"]
            if actor == "ella" and "wap35-" in name:
                assert [
                    entity.model_dump(mode="json")
                    for entity in view.visible_entities
                    if entity.entity_type in ("ground_fruit", "canteen", "corpse")
                ] == [
                    entity
                    for entity in legacy["visible_entities"]
                    if entity["entity_type"] in ("ground_fruit", "canteen", "corpse")
                ]
                actual_receipts = {
                    (entry.entity_id, entry.entity_type, entry.x, entry.y)
                    for entry in checkpoint.receipts.entities
                    if entry.entity_type != "resident"
                }
                assert actual_receipts == {
                    (
                        entry["entity_id"],
                        entry["entity_type"],
                        entry["position"]["x"],
                        entry["position"]["y"],
                    )
                    for entry in expected_receipts[actor]["entities"]
                    if entry["entity_type"] != "resident"
                }
            if name == "wap28-spring-unknown" and tick == 1 and actor == "ella":
                assert "spring" not in {tile.terrain for tile in view.explored_static_tiles}
                assert (10, 1) not in {(tile.x, tile.y) for tile in checkpoint.receipts.explored}
            if name in ("wap30-interruption-long-successor", "wap23-wap32-daylight-footprint"):
                assert view.model_dump()["explored_static_tiles"] == legacy["explored_static_tiles"]
            legacy_cues = {
                row["cue_id"]: row["detail_level"] for row in legacy["environmental_cues"]
            }
            for key, detail in legacy_cues.items():
                assert checkpoint.receipts.cue_detail[key] == detail or detail == "distant"


def test_ct15_rejects_unregistered_talk_length(archive, tmp_path):
    from living_island.sim.equivalence.projection import read_projection
    from living_island.sim.v2.compat.config import load_compat_pack

    _, registry, _, vocabulary = archive
    raw, _ = registry["production"]
    projection = read_projection(FIXTURES / "wap23-ct15-refused-profiles.json.gz")
    assert projection.scripted_evidence is not None
    assert any(
        "talk" in row["case"] for row in projection.scripted_evidence[0]["registry_rejections"]
    )
    source = tmp_path / "talk-2.toml"
    source.write_bytes(raw.replace(b"talk_ticks = 1", b"talk_ticks = 2"))
    with pytest.raises(ValueError, match="unregistered v1 config blob"):
        load_compat_pack(source, ROOT / "content/packs/compat-v1", vocabulary)


def test_wap25_bridge_sees_own_checks_and_visible_mode_sees_phenomena(archive, tmp_path):
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.compat.bridge import LegacyBridge, visible_result
    from living_island.sim.v2.compat.policy_host import PolicySession
    from living_island.world.v2.protocol import Settlement

    observed = {}
    for suffix, phenotype, expected_code in (
        ("empty-at-start", "finds_nothing", "RESOURCE_TAKEN"),
        ("no-stamina", "too_tired", "EXHAUSTED"),
        ("no-room", "hands_full", "INVENTORY_FULL"),
    ):
        directory = tmp_path / suffix
        directory.mkdir()
        bound, content, case, _ = load_case(archive, directory, f"wap23-gather-{suffix}")
        world = seeded_world(bound, content, case)
        hosts = hosts_for(bound, content, case, "bridge")
        session = PolicySession(world, hosts, PacketJournal(directory / "journal", world.run_id))
        result = session.advance()
        physical = next(action for action in result.actions if action.actor_id == "ella")
        intent = hosts["ella"].decision_records[0].plan.intents[0]
        packet = next(p for p in world.pending_packets() if p.actor_id == "ella")
        feedback = packet.perception.action_feedback[0]
        assert feedback == physical.visible_feedback
        assert feedback.phenomena == [phenotype]
        assert feedback.status == "done" and feedback.failure_code is None
        assert "compat_gather_fruit" not in packet.model_dump_json()
        assert "failed_check" not in packet.model_dump_json()
        assert expected_code not in packet.model_dump_json()
        translated = visible_result(intent, 0, 1, feedback, None)
        assert translated.failure_code == expected_code
        observed[expected_code] = (physical, intent, LegacyBridge(bound))
    sample, intent, bridge = observed["RESOURCE_TAKEN"]
    for check, code in (
        ("stock", "RESOURCE_TAKEN"),
        ("stamina", "EXHAUSTED"),
        ("room", "INVENTORY_FULL"),
    ):
        private_pair = sample.model_copy(
            update={
                "settlement": Settlement(
                    rule_id="compat_gather_fruit",
                    kind="unmet",
                    at="start",
                    failed_check=check,
                )
            }
        )
        assert private_pair.visible_feedback == sample.visible_feedback
        assert bridge.translate(intent, private_pair, None).failure_code == code


def test_wap25_admission_refuses_missing_check_and_foreign_pack(archive, tmp_path):
    from dataclasses import replace
    from shutil import copytree

    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.compat.bridge import LegacyBridge
    from living_island.sim.v2.compat.config import load_compat_pack
    from living_island.sim.v2.compat.policy_host import PolicySession
    from living_island.world.v2.rules import ContentError, load_pack

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-gather-no-room")
    bad = tmp_path / "compat-v1"
    copytree(ROOT / "content/packs/compat-v1", bad)
    codes = bad / "compat-codes.toml"
    codes.write_text(
        codes.read_text(encoding="utf-8").replace('room = "INVENTORY_FULL"\n', ""),
        encoding="utf-8",
    )
    _, _, _, vocabulary = archive
    with pytest.raises(ContentError, match="missing.*room"):
        load_compat_pack(
            tmp_path / "source.toml", bad, vocabulary, map_path=tmp_path / "island.map"
        )
    fixture = tmp_path / "engine-test"
    copytree(ROOT / "backend/tests/fixtures/v2/packs/engine-test", fixture)
    pack_file = fixture / "pack.toml"
    engine_settings = """
[physiology]
stamina_awake_decay_per_tick = 0
stamina_move_extra_cost_per_tick = 0
[limits]
max_entities_per_tile = 16
max_entity_units_world = 32
[timing]
invalid_attempt_ticks = 1
give_ticks = 1
pick_up_ticks = 1
drop_ticks = 1
inspect_ticks = 1
wait_ticks = 1
"""
    with pack_file.open("a", encoding="utf-8") as file:
        file.write(engine_settings)
    native = load_pack(fixture, vocabulary)
    with pytest.raises(ValueError, match="bridge requires compat-v1"):
        LegacyBridge(replace(bound, pack=native))
    world = seeded_world(bound, content, case, native_pack=native)
    journal = PacketJournal(tmp_path / "native", world.run_id)
    with pytest.raises(ValueError, match="requires its admitted compatibility pack"):
        PolicySession(world, hosts_for(bound, content, case, "bridge"), journal)
    hosts = hosts_for(bound, content, case, "visible")
    assert all(host.bridge is None for host in hosts.values())
    PolicySession(world, hosts, journal)


def _wait_choice():
    from living_island.world.v2 import protocol as v2

    return v2.ModelTurn(
        action=v2.ModelIntentAction(
            kind="intent",
            intent=v2.IntentShape(
                action="wait",
                verb=None,
                target=None,
                instruments=[],
                inputs=[],
                params={},
                reason=None,
            ),
        ),
        utterance=None,
    )


@pytest.mark.parametrize("mode", ("bridge", "visible"))
@pytest.mark.parametrize("fallback_action", ("gather", "talk"))
def test_wap25_model_fallback_model_after_restore(archive, tmp_path, mode, fallback_action):
    from dataclasses import replace

    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import give, talk
    from living_island.sim.v2.compat.policy_host import PolicySession, UseFallback, restore_policies

    bound, content, original, _ = load_case(archive, tmp_path, "wap23-gather-empty-at-start")
    script = (
        original.plans[("ella", 0)] if fallback_action == "gather" else (talk("ryan"), give("ryan"))
    )
    case = replace(original, plans={("ella", 1): script})
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    hosts = hosts_for(bound, content, case, mode)
    requests = []
    day_log = []

    def remember(packet):
        if packet.actor_id == "ella":
            day_log.append(packet)
        return False

    def choose(packet):
        if packet.actor_id == "ella":
            requests.append(packet)
            if packet.observed_tick == 1:
                return UseFallback("scripted model unavailable")
        return _wait_choice()

    session = PolicySession(world, hosts, journal, model=choose, model_delivery=remember)
    session.advance()
    fallback = session.advance()
    turn = session.runner.manifest.boundaries[-1].fallback_turns[0].submission
    assert turn.utterance is None
    fallback_id = turn.action.intent.intent_id
    assert any(event.type == "agent_fallback_used" for event in fallback.events)
    assert not any(event.type == "utterance_spoken" for event in fallback.events)
    pending = next(p for p in world.pending_packets() if p.actor_id == "ella")
    assert pending.perception.action_feedback[0].intent_id == fallback_id
    assert pending.perception.action_feedback[0].status == "done"
    path = tmp_path / "restore.json"
    save_checkpoint(
        path,
        world,
        journal,
        session.checkpoint(),
    )
    restored = load_checkpoint(path, bound.pack, journal)
    restored_states = restore_policies(restored.sim_checkpoint)
    hosts = hosts_for(bound, content, case, mode, restored_states)
    session = PolicySession(restored.world, hosts, journal, model=choose, model_delivery=remember)
    session.advance()
    state = hosts["ella"].checkpoint()
    code = "RESOURCE_TAKEN" if fallback_action == "gather" else "INVALID_SPEECH_ACT"
    assert len(state.boundary_results) == 1
    assert state.boundary_results[0].failure_code == code
    assert state.boundary_results[0].intent_id == "ella:p000000:i0"
    assert state.boundary_triggers == ("ACTION_FAILED",)
    assert not state.queue
    [backoff] = [
        entry for entry in state.policy_state.failed_targets if entry.action == fallback_action
    ]
    assert (backoff.action, backoff.code, backoff.retry_after_tick) == (fallback_action, code, 38)
    identity = backoff.target.model_dump()
    assert identity == (
        {"kind": "tile", "position": {"x": 3, "y": 2}}
        if fallback_action == "gather"
        else {"kind": "resident", "id": "ryan"}
    )
    model_packet = requests[-1]
    assert model_packet.observed_tick == 2
    assert model_packet.perception.action_feedback == []
    assert model_packet == day_log[-1]
    # The harness's day-log and recall input ports receive the same filtered packet.
    recall = [packet.perception.model_dump_json() for packet in day_log]
    for public in [model_packet.model_dump_json(), *recall, pending.model_dump_json()]:
        assert code not in public
        assert "failed_check" not in public
        assert "compat_gather_fruit" not in public
        assert "ACTION_FAILED" not in public
        assert "ella:p000000:i0" not in public
    assert fallback_id not in model_packet.model_dump_json()
    assert all(fallback_id not in memory for memory in recall)
    policy = hosts["ella"]
    assert not policy.ingest(pending)
    assert policy.checkpoint() == state
    session.advance()
    following = policy.checkpoint()
    assert following.boundary_results == ()
    assert following.policy_state.failed_targets == state.policy_state.failed_targets
    assert not policy.ingest(pending)
    assert policy.checkpoint() == following


@pytest.mark.parametrize("mode", ("bridge", "visible"))
def test_round_three_real_near_upgrade_restores_once(archive, tmp_path, mode):
    from dataclasses import replace

    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import action, move, seeded
    from living_island.sim.v2.compat.policy_host import (
        PolicyCheckpoint,
        PolicySession,
        restore_policies,
    )

    bound, content, original, _ = load_case(archive, tmp_path, "wap23-ct15-refused-profiles")
    case = replace(
        original,
        plans={("ella", 0): (move(21, 32),), ("ella", 1): (action("sleep"), action("wait"))},
        setup=seeded(positions={"ella": (12, 32)}),
    )
    world = seeded_world(bound, content, case)
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    hosts = hosts_for(bound, content, case, mode)
    session = PolicySession(world, hosts, journal)
    initial = next(p for p in world.pending_packets() if p.actor_id == "ella")
    [initial_cue] = initial.perception.environmental_cues
    assert initial_cue.detail_level == "distant"
    moved = session.advance()
    positions = [
        event.payload["to"]
        for event in moved.events
        if event.type == "resident_moved" and event.actor_id == "ella"
    ]
    assert {"x": 15, "y": 32} in positions
    assert positions[-1] == {"x": 20, "y": 32}
    pending = next(p for p in world.pending_packets() if p.actor_id == "ella")
    [upgraded] = pending.perception.environmental_cues
    assert (upgraded.cue_id, upgraded.position) == (initial_cue.cue_id, initial_cue.position)
    assert (upgraded.detail_level, upgraded.direction) == ("near", "east")
    old = hosts["ella"].checkpoint()
    assert old.receipts.cue_detail == {upgraded.cue_id: "distant"}
    path = tmp_path / "cue.json"
    save_checkpoint(
        path,
        world,
        journal,
        session.checkpoint(),
    )
    restore = load_checkpoint(path, bound.pack, journal)
    old_hosts = hosts_for(
        bound,
        content,
        case,
        mode,
        restore_policies(restore.sim_checkpoint),
    )
    pending_again = next(p for p in restore.world.pending_packets() if p.actor_id == "ella")
    assert pending_again == pending
    assert old_hosts["ella"].ingest(pending_again)
    first = old_hosts["ella"].checkpoint()
    assert first.boundary_triggers == ("ACTION_INTERRUPTED", "NEW_SIGHT")
    assert first.receipts.cue_detail == {upgraded.cue_id: "near"}
    assert [outcome(item) for item in first.boundary_results] == [
        ("ella:p000000:i0", "interrupted", "NEW_SIGHT", 0, 1)
    ]
    # Restore after taking the private receipt, with the exact same pending delivery.
    restored_hosts = hosts_for(
        bound,
        content,
        case,
        mode,
        {
            key: PolicyCheckpoint.model_validate_json(host.checkpoint().model_dump_json())
            for key, host in old_hosts.items()
        },
    )
    session = PolicySession(restore.world, restored_hosts, journal)
    session.advance()
    host = restored_hosts["ella"]
    [record] = host.decision_records
    assert record.triggers == ["ACTION_INTERRUPTED", "NEW_SIGHT"]
    assert host.checkpoint().handled_stops == ("ella:t000000:a",)
    assert host.checkpoint().policy_state.cue_impressions[0].detail_level == "near"
    unchanged = next(p for p in restore.world.pending_packets() if p.actor_id == "ella")
    assert unchanged.perception.environmental_cues[0].detail_level == "distant"
    assert [(f.intent_id, f.stop_reason) for f in unchanged.perception.action_feedback] == [
        ("ella:t000000:a", "own_choice")
    ]
    session.advance()
    state = host.checkpoint()
    assert not state.handled_stops and not state.boundary_results and not state.deferred
    assert state.receipts.cue_detail == {upgraded.cue_id: "near"}
    assert [i.action_type for i in state.queue] == ["wait"]
    assert host.decision_records == [record]


def test_transient_cue_keeps_last_sight_step_and_highest_detail(archive, tmp_path):
    from dataclasses import replace

    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.v1_extract import move, seeded
    from living_island.sim.v2.compat.adapters import project_perception
    from living_island.sim.v2.compat.policy_host import PolicySession
    from living_island.world.v2.engine.perception import build_deliveries
    from living_island.world.v2.engine.tick import EventWriter, TickContext

    bound, content, case, _ = load_case(archive, tmp_path, "wap23-ct15-refused-profiles")
    case = replace(
        case,
        plans={("ella", 0): (move(21, 32),)},
        setup=seeded(positions={"ella": (12, 32)}, known_route=True),
    )
    world = seeded_world(bound, content, case)
    state = world.state
    state.clock = replace(state.clock, start_minute=1200)
    state.clock_minute = state.clock.minute_at(0)
    build_deliveries(TickContext(state, world.pack, EventWriter(state, 0)))
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    session = PolicySession(world, hosts_for(bound, content, case, "visible"), journal)
    session.advance()
    packet = next(p for p in world.pending_packets() if p.actor_id == "ella")
    view = project_perception(packet.perception)
    [cue] = view.environmental_cues
    assert cue.detail_level == "near"
    assert all(entity.entity_id != cue.cue_id for entity in view.visible_entities)
    [sighting] = [entry for entry in view.transient_sightings if entry.entity_id == cue.cue_id]
    assert (sighting.entity_type, sighting.position, sighting.seen_at_step) == (
        "cue",
        cue.position,
        6,
    )
    assert cue.cue_id not in world.state.exposure_receipts_by_resident["ella"].entities
