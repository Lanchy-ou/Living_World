"""Replay capture and publication through the frozen boundary observer."""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_engine_actions import content_with

from living_island.contract.replay import ReplayBundle
from living_island.persistence._codec import PersistenceError
from living_island.persistence.content import load_world_content
from living_island.persistence.replay import FrameSpool, export_replay
from living_island.persistence.scripts import load_script
from living_island.sim.cli import main
from living_island.sim.runner import run
from living_island.world.content import canonical_json_bytes
from living_island.world.facts import ActionFailedPayload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "replay"


def _run_args(directory, ticks):
    return [
        "run",
        "--config",
        str(FIXTURES / "mechanics.toml"),
        "--ticks",
        str(ticks),
        "--policy",
        "scripted",
        "--script",
        str(FIXTURES / "mechanics.script.json"),
        "--out",
        str(directory),
        "--export-replay",
    ]


@pytest.mark.parametrize("ticks", [0, 6])
def test_cli_export_captures_all_boundaries_and_reexecution_matches(tmp_path, ticks):
    original = tmp_path / "original"
    recorded = tmp_path / "recorded"
    assert main(_run_args(original, ticks)) == 0
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
    raw = (original / "replay.json").read_bytes()
    assert (recorded / "replay.json").read_bytes() == raw
    bundle = ReplayBundle.model_validate_json(raw)
    assert [frame.tick for frame in bundle.frames] == list(range(ticks + 1))
    lines = [canonical_json_bytes(frame.model_dump(mode="json")) + b"\n" for frame in bundle.frames]
    for directory in (original, recorded):
        assert (directory / "frames.jsonl").read_bytes() == b"".join(lines)
    if ticks == 0:
        assert bundle.events[0].type == "world_initialized"
        assert all(event.tick == 0 for event in bundle.events)
        assert bundle.frames[0].event_range.count == len(bundle.events)
        assert not (original / "decisions.jsonl").read_bytes()
        return

    assert raw == (FIXTURES / "mechanics.replay.json").read_bytes()
    failures = [
        (event.tick, event.actor_id, event.payload.failure_code)
        for event in bundle.events
        if isinstance(event.payload, ActionFailedPayload)
    ]
    assert failures == [(2, "mia", "RESOURCE_TAKEN")]
    assert {(event.tick, event.type, event.actor_id) for event in bundle.events} >= {
        (1, "water_drank", "ryan"),
        (2, "resident_moved", "ryan"),
        (2, "fruit_gathered", "ella"),
        (4, "resident_died", "ella"),
        (4, "item_dropped", "ella"),
        (5, "item_picked_up", "ryan"),
    }
    assert bundle.frames[4].ground_fruit[0].quantity == 1
    assert not bundle.frames[5].ground_fruit
    assert not bundle.frames[-1].residents[0].alive
    assert bundle.frames[-1].residents[2].fruit_count == 1


@given(seed=st.integers(min_value=1, max_value=2**32 - 1), ticks=st.integers(0, 12))
@settings(max_examples=15, deadline=None)
def test_every_spooled_frame_matches_its_committed_snapshot(tmp_path_factory, seed, ticks):
    content = content_with(
        {"ryan": (4, 2), "ella": (2, 2)},
        meta={"seed": seed},
        needs={"initial_hydration": 300, "initial_health": 70},
    )
    directory = tmp_path_factory.mktemp("projection") / "run"
    spool = FrameSpool(directory)
    snapshots = []
    events_by_tick = []

    def capture(snapshot, events):
        snapshots.append(snapshot.model_dump(mode="json"))
        events_by_tick.append(events)
        spool(snapshot, events)
        assert snapshot.model_dump(mode="json") == snapshots[-1]

    run(content, ticks, directory, on_boundary_committed=capture)
    export_replay(directory)
    doc = json.loads((directory / "replay.json").read_bytes())
    assert doc.keys() == {
        "replay_schema_version",
        "run_id",
        "world_id",
        "config_hash",
        "map_hash",
        "clock",
        "condition_bounds",
        "map",
        "residents",
        "frames",
        "events",
    }
    assert [row["id"] for row in doc["residents"]] == ["ella", "ryan"]
    assert all(row.keys() == {"id", "display_name"} for row in doc["residents"])
    assert doc["map"]["rows"] == list(content.map_rows)
    assert doc["condition_bounds"] == {
        "min_value": 0,
        "max_value": content.config.needs.max_value,
    }
    first = 0
    for frame, state, events in zip(doc["frames"], snapshots, events_by_tick, strict=True):
        canteen = state["unique_canteen"]
        actions = {
            action["intent"]["actor_id"]: {
                "intent_id": action["intent"]["intent_id"],
                "action_type": action["intent"]["action_type"],
                "tick_started": action["tick_started"],
                "remaining_ticks": action["remaining_ticks"],
            }
            for action in state["active_actions"]
        }
        end = first + len(events)
        assert end == state["event_log_cursor"]
        assert doc["events"][first:end] == [event.model_dump(mode="json") for event in events]
        assert frame == {
            "tick": state["tick"],
            "residents": [
                {
                    **resident,
                    "canteen_servings": (
                        canteen["servings"] if resident["id"] == canteen["holder_id"] else None
                    ),
                    "active_action": actions.get(resident["id"]),
                }
                for resident in state["residents"]
            ],
            "fruit_trees": [
                {key: tree[key] for key in ("id", "position", "stock")}
                for tree in state["fruit_nodes"]
            ],
            "ground_fruit": state["ground_fruit"],
            "ground_canteen": (
                {"position": canteen["ground_position"], "servings": canteen["servings"]}
                if canteen["ground_position"] is not None
                else None
            ),
            "corpses": [
                {key: corpse[key] for key in ("id", "resident_id", "position")}
                for corpse in state["corpses"]
            ],
            "event_range": {"first_index": first, "count": len(events)},
        }
        first = end


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("missing_tail", "expected 4 frames"),
        ("wrong_tick", "frame_ticks"),
        ("wrong_range", "event_range"),
        ("torn_line", "missing final LF"),
        ("changed_events", "events_sha256"),
    ],
)
def test_failed_export_refuses_damaged_inputs_without_publishing(tmp_path, damage, message):
    # Everyone dies at tick 1, so the last two frames have empty event slices. The
    # manifest's final tick is needed to detect a dropped final frame in this case.
    content = content_with({"ella": (2, 2)}, needs={"initial_hydration": 0, "initial_health": 70})
    directory = tmp_path / "run"
    spool = FrameSpool(directory)
    run(content, 3, directory, on_boundary_committed=spool)
    lines = spool.path.read_bytes().splitlines(keepends=True)
    assert json.loads(lines[-1])["event_range"]["count"] == 0
    if damage == "missing_tail":
        lines.pop()
    elif damage in ("wrong_tick", "wrong_range"):
        frame = json.loads(lines[2])
        if damage == "wrong_tick":
            frame["tick"] = 1
        else:
            frame["event_range"]["count"] = 1
        lines[2] = canonical_json_bytes(frame) + b"\n"
    elif damage == "torn_line":
        lines[-1] = lines[-1][:-1]
    else:
        event_log = directory / "events.jsonl"
        event_log.write_bytes(event_log.read_bytes() + b"\n")
    damaged_spool = b"".join(lines)
    spool.path.write_bytes(damaged_spool)
    with pytest.raises(ValueError, match=message):
        export_replay(directory)
    assert not (directory / "replay.json").exists()
    assert spool.path.read_bytes() == damaged_spool


def test_frame_write_error_stops_run_and_refuses_publication(tmp_path, capsys, monkeypatch):
    directory = tmp_path / "run"
    open_path = Path.open

    def fail_frame_append(path, mode="r", *args, **kwargs):
        if path.name == "frames.jsonl" and mode == "r+b":
            raise OSError("injected frame spool write failure")
        return open_path(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_frame_append)
    assert main(_run_args(directory, 3)) == 1
    error = capsys.readouterr().err
    assert "frames.jsonl:2" in error
    assert "injected frame spool write failure" in error
    assert (directory / "checkpoint-0000000000.json").is_file()
    assert len((directory / "frames.jsonl").read_bytes().splitlines()) == 1
    assert (
        max(
            json.loads(line)["tick"]
            for line in (directory / "events.jsonl").read_bytes().splitlines()
        )
        == 1
    )
    assert not (directory / "decision-trace.json").exists()
    assert not (directory / "replay.json").exists()


@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        ("frames.jsonl", "final_frame.*does not match the final checkpoint"),
        ("checkpoint-0000000006.json", "final_world_sha256"),
    ],
)
def test_export_refuses_altered_final_health(tmp_path, artifact, message):
    directory = tmp_path / "run"
    content = load_world_content(FIXTURES / "mechanics.toml")
    script = load_script(FIXTURES / "mechanics.script.json", content.config)
    run(content, 6, directory, script=script, on_boundary_committed=FrameSpool(directory))
    target = directory / artifact
    lines = target.read_bytes().splitlines(keepends=True)
    final = json.loads(lines[-1])
    world = final if artifact == "frames.jsonl" else final["world"]
    assert world["residents"][2]["health"] == 70
    world["residents"][2]["health"] = 71
    lines[-1] = canonical_json_bytes(final) + (b"\n" if artifact == "frames.jsonl" else b"")
    target.write_bytes(b"".join(lines))

    with pytest.raises(PersistenceError, match=message):
        export_replay(directory)
    assert not (directory / "replay.json").exists()
