"""Compare real v2 trajectories and committed v1 case witnesses."""

import importlib
from functools import partial
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTED = (
    "ct15-ct17-regrowth-0",
    "ct15-ct17-regrowth-2",
    "ct17-canteen-0-servings",
    "ct17-canteen-1-servings",
    "ct17-canteen-2-servings",
    "ct17-one-tick-gather",
    "wap23-gather-last-fruit-contested",
    "wap23-pickup-contested-last-fruit",
    "wap23-reply-first-reply",
    "wap23-wap29-two-talks-last-slot-with-wait",
    "wap23-wap32-daylight-footprint",
    "wap23-wap32-early-wake-no-speech",
    "wap23-wap32-natural-wake-no-speech",
    "wap23-wap32-wap35-corpse-restore-before-wake",
    "wap23-wap33-en23-gather-exhaustion",
    "wap23-wap33-en23-move-exhaustion",
    "wap27-completion-away",
    "wap27-completion-returned",
    "wap33-exhaustion-and-death",
)
COMPLETION_CASES = {
    "wap23-gather-last-fruit-contested",
    "wap23-pickup-contested-last-fruit",
    "wap23-wap29-two-talks-last-slot-with-wait",
}


@pytest.fixture(scope="module")
def scripted_setup():
    from living_island.sim.equivalence.v1_extract import scripted_projections
    from living_island.world.v2.rules import load_vocabulary

    # Reuse PR-06's immutable test input construction. Its loader and setup
    # create the v2 World and its fixture starting conditions independently.
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(ROOT / "scripts"))
        patch.syspath_prepend(str(ROOT / "backend/tests/v2/compat_policy"))
        tests = importlib.import_module("test_scripted")
        generator = importlib.import_module("gen_v1_projections")
        registry = generator.load_registry(ROOT)
        mechanics, _ = generator.effective("mechanics", *registry["mechanics"], 20261108)
        cases = {name: run.__self__ for name, _, _, run in scripted_projections(mechanics)}
        vocabulary = load_vocabulary(ROOT / "content/vocabulary/vocab-0.1.toml")
        yield tests, (generator, registry, cases, vocabulary)


@pytest.mark.parametrize("name", SCRIPTED)
def test_scripted_oracle(scripted_setup, tmp_path, name):
    from living_island.agents.types import OwnProfile
    from living_island.persistence.v2.checkpoint import load_checkpoint, save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.equivalence.compare import first_difference, legacy_replies
    from living_island.sim.equivalence.v1_extract import FixturePolicy, script_policy_config
    from living_island.sim.equivalence.v2_extract import ProjectionHost, V2Extractor, snapshot
    from living_island.sim.v2.compat.adapters import project_perception
    from living_island.sim.v2.compat.bridge import LegacyBridge
    from living_island.sim.v2.compat.policy_host import (
        PolicyCheckpoint,
        PolicySession,
        restore_policies,
    )

    helpers, archive = scripted_setup
    bound, content, case, oracle = helpers.load_case(archive, tmp_path, name)
    oracle = legacy_replies(oracle)
    assert oracle.scripted_evidence is not None
    world = helpers.seeded_world(bound, content, case)
    config = content.config
    extractor = V2Extractor(LegacyBridge(bound))
    canteen = config.canteen.unique_item_id
    journal = PacketJournal(tmp_path / "journal", world.run_id)
    overrides = {(actor, case.start + tick): plan for (actor, tick), plan in case.plans.items()}

    def create_session(current_world, checkpoints):
        hosts = {
            row.id: ProjectionHost(
                script_policy_config(config),
                OwnProfile(profile_id=row.profile_id, initial_goal=row.initial_goal),
                config.actions.sleep_ticks,
                extractor=extractor,
                restored=checkpoints.get(row.id),
                policy_factory=partial(FixturePolicy, overrides=overrides, observed=case.observed),
            )
            for row in config.residents
        }
        return PolicySession(current_world, hosts, journal)

    initial = {}
    if case.start:
        # The PR-06 setup uses ordinary waits to request a turn at this
        # artificial starting boundary. PR-03 opened it without completions.
        world.state.resolution_rng_state_uint32 = config.meta.seed
        for packet in world.pending_packets():
            start = PolicyCheckpoint()
            receipts, _ = start.receipts.ingest(project_perception(packet.perception))
            initial[packet.actor_id] = PolicyCheckpoint(
                cursor=case.start - 1, receipts=receipts, deferred=("PLAN_FINISHED",)
            )
    session = create_session(world, initial)
    extractor.frames.append(snapshot(world, canteen))
    for frame, evidence in zip(oracle.frames, oracle.scripted_evidence, strict=True):
        assert frame.tick == world.tick
        if frame.tick == case.restore_after:
            path = tmp_path / "restored.json"
            save_checkpoint(
                path, world, journal, session.checkpoint(), first_journal_tick=case.start
            )
            saved = load_checkpoint(path, bound.pack, journal)
            world = saved.world
            session = create_session(world, restore_policies(saved.sim_checkpoint))
        assert world.state.resolution_rng_state_uint32 == evidence["rng"], frame.tick
        if name.startswith("wap23-wap32"):
            footprint = {r["resident_id"]: set(r["tile_indices"]) for r in evidence["explored"]}
            assert world.state.explored_tiles_by_resident == footprint, frame.tick
            for expected in evidence["deliveries"]:
                if expected["actor_id"] == "ella":
                    packet = world.state.pending_deliveries["ella"]
                    perception = project_perception(packet.perception)
                    assert bool(perception.heard_utterances) == bool(
                        expected["perception"]["heard_utterances"]
                    )
            if name.endswith("corpse-restore-before-wake") and frame.tick >= 1:
                ella = world.state.pending_deliveries["ella"]
                corpse = "corpse@ryan"
                assert corpse in world.state.exposure_receipts_by_resident["ella"].entities
                sightings = [
                    r
                    for r in ella.reports
                    if r.subject_id == corpse and r.kind == "entity_first_seen"
                ]
                assert bool(sightings) == (frame.tick == 1)
                if frame.tick == 1:
                    assert ella.perception.awareness == "asleep"
                    assert corpse in {e.entity_id for e in ella.perception.visible_entities}
        result = session.advance()
        assert result is not None
        extractor.append(snapshot(world, canteen), result)
    extractor.frames.pop()  # Scripted v1 fixtures retain decisions at their last boundary.
    for expected, actual in zip(oracle.frames, extractor.finish(), strict=True):
        if name in COMPLETION_CASES:
            assert expected.outcomes == actual.outcomes, expected.tick
        assert first_difference(expected, actual) is None


def test_matrix_registration_agrees_with_archive():
    from living_island.sim.v2.cli import FIXTURES, matrix_names

    registered = matrix_names()
    assert len(registered) == 160
    assert len([name for name in registered if name.startswith("acceptance-")]) == 20
    assert registered == sorted(
        file.name.removesuffix(".json.gz") for file in (FIXTURES / "matrix").glob("*.json.gz")
    )


def test_acceptance_prefix_and_repeatable_receipt(tmp_path):
    from living_island.sim.v2.cli import FIXTURES, run_case

    path = FIXTURES / "matrix/acceptance-production-base-2600456787.json.gz"
    first = run_case(path, tmp_path / "first", 2)
    second = run_case(path, tmp_path / "second", 2)
    assert first == second
    assert first["difference"] is None
    assert first["matched_boundaries"] == 3


def test_comparator_locates_the_first_unequal_need():
    from living_island.sim.equivalence.compare import first_difference
    from living_island.sim.equivalence.projection import read_projection
    from living_island.sim.v2.cli import FIXTURES

    frame = read_projection(FIXTURES / "scripted/ct17-canteen-2-servings.json.gz").frames[1]
    altered = frame.model_copy(deep=True)
    expected = frame.residents[0].stamina
    altered.residents[0].stamina += 1
    altered.residents[0].health -= 1
    assert first_difference(frame, altered) == {
        "tick": 1,
        "field": "residents[0].health",
        "expected": frame.residents[0].health,
        "actual": frame.residents[0].health - 1,
    }
    altered.residents[0].health = frame.residents[0].health
    assert first_difference(frame, altered) == {
        "tick": 1,
        "field": "residents[0].stamina",
        "expected": expected,
        "actual": expected + 1,
    }


def test_wap33_path_blocking_precedes_death(scripted_setup, tmp_path):
    from living_island.sim.equivalence.v2_extract import snapshot
    from living_island.sim.v2.compat.adapters import adapt_intent
    from living_island.sim.v2.compat.bridge import LegacyBridge
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world import protocol as v1
    from living_island.world.v2 import protocol as v2
    from living_island.world.v2.engine.state import ActiveAction, Move, Route

    helpers, archive = scripted_setup
    name = "wap33-path-blocked-then-death"
    bound, content, case, oracle = helpers.load_case(archive, tmp_path, name)
    world = helpers.seeded_world(bound, content, case)
    position = v2.Coord(x=2, y=0)
    legacy = v1.ActionIntent(
        actor_id="ella",
        intent_id="fixture-blocked-route",
        plan_id="fixture",
        action_type="move_to",
        target=v1.TileTarget(kind="tile", position=v1.Coord(x=2, y=0)),
        parameters=v1.EmptyParameters(),
        reason=None,
    )
    ella = world.state.pending_deliveries["ella"]
    turn = TurnRequest(ella, 0, ("start",)).bind(adapt_intent(legacy, 48))
    state = world.state
    assert isinstance(turn.action, v2.IntentAction)
    assert state.static_map.cost(position) is None
    state.active_actions["ella"] = ActiveAction(
        turn.action.intent, Move(position), 0, route=Route((position,))
    )
    result = world.step(
        acknowledged={packet.actor_id: packet.delivery_id for packet in world.pending_packets()}
    )
    [outcome] = result.actions
    translated = LegacyBridge(bound).translate(legacy, outcome, None)
    assert translated is not None
    expected = next(item for item in oracle.frames[1].outcomes if item.actor_id == "ella")
    assert (
        (translated.status, translated.failure_code, translated.tick_finished)
        == (expected.status, expected.code, expected.tick_finished)
        == ("failure", "PATH_BLOCKED", 1)
    )
    actual = snapshot(world, "canteen_01")
    assert actual.residents[0] == oracle.frames[1].residents[0]
    assert actual.corpses == oracle.frames[1].corpses
