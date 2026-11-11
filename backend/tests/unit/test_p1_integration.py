"""The seven-day P1 reference run through the CLI and its durable outputs."""

import json

from world_builders import P1_WORLD

from living_island.contract.projections import project_frame
from living_island.contract.replay import ReplayBundle
from living_island.persistence.checkpoints import read_checkpoint
from living_island.persistence.content import load_world_content
from living_island.persistence.replay import FrameSpool
from living_island.persistence.trace import load_trace
from living_island.sim import cli
from living_island.sim.runner import checkpoint_filename
from living_island.world.canteen import check_canteen
from living_island.world.content import canonical_json_bytes
from living_island.world.resources import check_fruit_conservation
from living_island.world.space import StaticMap


def test_default_1008_tick_cli_run_resume_reexecute_and_replay(tmp_path, monkeypatch):
    ticks, split = 1008, 144
    first, twin, continuation, recorded = (
        tmp_path / name for name in ("first", "twin", "continuation", "recorded")
    )
    config_path = P1_WORLD
    content = load_world_content(config_path)
    config = content.config
    static_map = StaticMap.from_content(content)
    frames = []

    def observing_spool(directory):
        spool = FrameSpool(directory)

        def capture(snapshot, events):
            if directory == first:
                frames.append(project_frame(snapshot, len(events)))
            spool(snapshot, events)

        return capture

    monkeypatch.setattr(cli, "FrameSpool", observing_spool)
    fresh = ["run", "--config", str(config_path), "--ticks", str(ticks), "--policy", "random"]
    assert (
        cli.main([*fresh, "--out", str(first), "--checkpoint-every", str(split), "--export-replay"])
        == 0
    )
    assert cli.main([*fresh, "--out", str(twin)]) == 0
    checkpoint = first / checkpoint_filename(split)
    assert (
        cli.main(
            [
                "resume",
                "--checkpoint",
                str(checkpoint),
                "--source-run",
                str(first),
                "--ticks",
                str(ticks - split),
                "--out",
                str(continuation),
            ]
        )
        == 0
    )
    assert (
        cli.main(
            ["reexecute", "--source-run", str(first), "--out", str(recorded), "--export-replay"]
        )
        == 0
    )

    trace = load_trace(first)  # Verifies identities, stream hashes, event order and causal links.
    raw = (first / "replay.json").read_bytes()
    bundle = ReplayBundle.model_validate_json(raw)
    assert bundle.frames == frames
    assert [frame.tick for frame in frames] == list(range(ticks + 1))
    assert bundle.events == list(trace.events)
    assert (recorded / "replay.json").read_bytes() == raw

    checkpoints = list(range(0, ticks + 1, split))
    assert sorted(path.name for path in first.glob("checkpoint-*.json")) == [
        checkpoint_filename(tick) for tick in checkpoints
    ]
    for tick in checkpoints:
        save = read_checkpoint(first / checkpoint_filename(tick), content)
        world = save.world
        assert world.tick == tick
        assert world.event_log_cursor == sum(event.tick <= tick for event in trace.events)
        prefix = trace.events[: world.event_log_cursor]
        assert frames[tick] == project_frame(world, frames[tick].event_range.count)
        assert world.lifetime_fruit_regrown == sum(
            event.payload.quantity for event in prefix if event.type == "fruit_regrew"
        )
        assert world.lifetime_fruit_consumed == sum(
            event.payload.quantity for event in prefix if event.type == "fruit_consumed"
        )
        check_fruit_conservation(config, world)
        check_canteen(config, world)
        dead = {resident.id for resident in world.residents if not resident.alive}
        assert dead == {corpse.resident_id for corpse in world.corpses}
        assert dead.isdisjoint(action.intent.actor_id for action in world.active_actions)
        for resident in world.residents:
            x, y = resident.position.x, resident.position.y
            assert static_map.in_bounds(x, y) and static_map.step_cost(x, y) is not None
            occupied = resident.fruit_count + (world.unique_canteen.holder_id == resident.id)
            assert 0 <= occupied <= config.inventory.slot_capacity
            assert all(
                type(value) is int and config.needs.min_value <= value <= config.needs.max_value
                for value in (
                    resident.satiety,
                    resident.hydration,
                    resident.stamina,
                    resident.health,
                )
            )
            if resident.id in dead:
                assert resident.health == resident.fruit_count == 0
        assert all(type(tree.stock) is int and tree.stock >= 0 for tree in world.fruit_nodes)
        assert all(type(pile.quantity) is int and pile.quantity > 0 for pile in world.ground_fruit)

    assert (continuation / "resume-origin.json").is_file()
    assert (continuation / "resume-parent.json").is_file()
    saved = read_checkpoint(checkpoint, content)
    living = {resident.id for resident in saved.world.residents if resident.alive}
    assert living
    for name, cursor in (
        ("events.jsonl", saved.event_cursor),
        ("decisions.jsonl", saved.decision_record_cursor),
    ):
        whole = (first / name).read_bytes()
        assert (twin / name).read_bytes() == (recorded / name).read_bytes() == whole
        lines = whole.splitlines(keepends=True)
        suffix = (continuation / name).read_bytes()
        assert suffix == b"".join(lines[cursor:])
        if name == "decisions.jsonl":
            assert any(json.loads(line)["actor_id"] in living for line in suffix.splitlines())

    final = checkpoint_filename(ticks)
    assert (first / final).read_bytes() == (twin / final).read_bytes()
    assert (first / final).read_bytes() == (continuation / final).read_bytes()
    worlds = [
        canonical_json_bytes(
            read_checkpoint(directory / final, content).world.model_dump(mode="json")
        )
        for directory in (first, twin, continuation, recorded)
    ]
    assert all(world == worlds[0] for world in worlds)
