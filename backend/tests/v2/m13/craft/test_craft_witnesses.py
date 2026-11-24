"""CT-05/06/16 and §5.9 share one short itinerary and a mid-twist checkpoint."""

from functools import partial

import pytest


@pytest.fixture(scope="module")
def trace(tmp_path_factory):
    from living_island.persistence.v2.checkpoint import save_checkpoint
    from living_island.persistence.v2.journal import PacketJournal
    from living_island.sim.v2.scenarios.craft import opening
    from living_island.sim.v2.scenarios.craft.__main__ import FINAL_TICK
    from living_island.sim.v2.scenarios.craft.index import Story
    from living_island.sim.v2.scenarios.craft.observer import Frame, observe
    from living_island.sim.v2.scenarios.craft.script import CraftScript
    from living_island.sim.v2.scenarios.runtime import Boundary, scripted
    from living_island.world.v2.engine.snapshot import encode_snapshot

    world, _, _ = opening()
    folder = tmp_path_factory.mktemp("craft")
    journal = PacketJournal(folder / "packets", world.run_id)
    session = scripted(CraftScript)(world, journal, None)
    observer = {}
    suffix = []
    point = folder / "mid-twist.json"
    for tick in range(FINAL_TICK):
        result = session.advance()
        record = session.runner.manifest.boundaries.pop().for_replay()
        observe(
            observer,
            Boundary(
                tick, record, result, partial(journal.read, tick), partial(encode_snapshot, world)
            ),
        )
        if world.tick == 110:
            assert world.state.active_actions["ella"].intent.verb == "combine"
            save_checkpoint(point, world, journal, session.checkpoint())
        elif world.tick > 110:
            suffix.append(record)
    story = Story((Frame.model_validate(f) for f in observer.values()), world.pack.source)
    return story, point, journal, suffix, encode_snapshot(world)


def test_ct05_flake_to_shelter(trace):
    story, *_ = trace
    chain = story.craft()
    assert chain["knap_flake"]["settled"] < chain["sleep_in_shelter"]["opening"]
    assert story.frames[126].tick == chain["sleep_in_shelter"]["settled"]


def test_ct06_deceptive_binding_and_cooperation(trace):
    story, *_ = trace
    vine = story.binding("bind_snaps", "strong")
    grass = story.binding("make_stone_axe", "weak")
    assert vine["watcher_settle"] != grass["watcher_settle"]
    assert story.cooperation()["units"] == 24


def test_ct16_pot_and_checkpoint_trace(trace):
    from living_island.persistence.v2.checkpoint import load_checkpoint
    from living_island.sim.v2.scenarios.craft.script import CraftScript
    from living_island.sim.v2.scenarios.runtime import scripted
    from living_island.world.v2.engine.snapshot import encode_snapshot

    story, point, journal, suffix, final_snapshot = trace
    assert story.pot()["servings"] == [0, 1, 1, 0]
    restored = load_checkpoint(point, story.pack, journal)
    session = scripted(CraftScript)(restored.world, journal, restored.sim_checkpoint)
    for expected in suffix:
        session.advance()  # The journal verifies identical packets on each re-ingestion.
        assert session.runner.manifest.boundaries.pop().for_replay() == expected
    assert encode_snapshot(restored.world) == final_snapshot


def test_section59_six_perceived_benefits(trace):
    story, *_ = trace
    benefits = story.benefits()
    assert set(benefits) == {"sharp_flake", "cord", "stone_axe", "campfire", "clay_pot", "shelter"}


def test_craft_reports_missing_held_input(trace):
    from living_island.sim.v2.scenarios.craft.script import choice

    _, _, journal, *_ = trace
    ella = next(p.perception for p in journal.read(0) if p.actor_id == "ella")
    with pytest.raises(ValueError, match="ella tick 0: missing held sharp_flake"):
        choice(ella, "sharp_flake")


def test_craft_refuses_incomplete_burn_evidence(trace):
    from living_island.sim.v2.scenarios.craft.index import Story

    story, *_ = trace
    last_burn = story.matching("world_rule_applied", "fire_burns")[-1]
    frame = story.frames[last_burn.tick]
    changed = dict(story.frames)
    changed[frame.tick] = frame.model_copy(
        update={"events": [e for e in frame.events if e != last_burn]}
    )
    with pytest.raises(ValueError, match="fire lifetime"):
        Story(changed.values(), story.pack).benefits()
