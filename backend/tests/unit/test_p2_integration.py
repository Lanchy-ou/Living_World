"""Short CI coverage for the M6 default and the rule-policy replay lifecycle."""

import json

from world_builders import WORLDS

from living_island.contract.replay import ReplayBundle
from living_island.persistence.checkpoints import read_checkpoint
from living_island.persistence.content import load_world_content
from living_island.sim.cli import main
from living_island.sim.runner import checkpoint_filename


def test_m6_rule_run_resume_reexecute_and_replay(tmp_path):
    config_path = WORLDS / "default.toml"
    content = load_world_content(config_path)
    original, continuation, recorded = (tmp_path / n for n in ("run", "resume", "recorded"))
    assert (
        main(
            [
                "run",
                "--config",
                str(config_path),
                "--ticks",
                "16",
                "--policy",
                "rule-based",
                "--checkpoint-every",
                "8",
                "--out",
                str(original),
                "--export-replay",
            ]
        )
        == 0
    )
    checkpoint = original / checkpoint_filename(8)
    save = read_checkpoint(checkpoint, content)
    living = {resident.id for resident in save.world.residents if resident.alive}
    assert living == {"ella", "mia", "ryan"}
    assert (
        main(
            [
                "resume",
                "--source-run",
                str(original),
                "--checkpoint",
                str(checkpoint),
                "--ticks",
                "8",
                "--out",
                str(continuation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "reexecute",
                "--source-run",
                str(original),
                "--out",
                str(recorded),
                "--export-replay",
            ]
        )
        == 0
    )

    for stream, cursor in (
        ("events.jsonl", save.event_cursor),
        ("decisions.jsonl", save.decision_record_cursor),
    ):
        full = (original / stream).read_bytes()
        prefix = b"".join(full.splitlines(keepends=True)[:cursor])
        assert prefix + (continuation / stream).read_bytes() == full
        assert (recorded / stream).read_bytes() == full
    assert any(
        json.loads(line)["actor_id"] in living
        for line in (continuation / "decisions.jsonl").read_bytes().splitlines()
    )
    final = checkpoint_filename(16)
    worlds = [
        read_checkpoint(path / final, content).world for path in (original, continuation, recorded)
    ]
    assert worlds[0] == worlds[1] == worlds[2]

    replay = (original / "replay.json").read_bytes()
    assert (recorded / "replay.json").read_bytes() == replay
    bundle = ReplayBundle.model_validate_json(replay)
    assert [frame.tick for frame in bundle.frames] == list(range(17))
    assert {
        resident.id: (resident.position.x, resident.position.y)
        for resident in bundle.frames[0].residents
    } == {
        "ella": (33, 32),
        "ryan": (34, 32),
        "mia": (35, 32),
    }
