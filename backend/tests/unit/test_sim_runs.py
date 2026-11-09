"""Durable simulation and AI §7 acceptance through real run artifacts."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from test_engine_actions import content_with, intent
from test_sim_boundaries import scripted, template
from test_sim_policies import PROFILE
from test_sim_runtime import WaitPolicy
from world_builders import WORLDS

from living_island.agents.policies._plans import WAIT
from living_island.agents.policies.recorded import ReplayDiverged
from living_island.agents.runtime import Runtime
from living_island.agents.types import ActorScript, ScriptFixture
from living_island.contract.save import SavePackage
from living_island.persistence.checkpoints import read_checkpoint
from living_island.persistence.scripts import load_script
from living_island.sim.boundary import BoundaryLoop
from living_island.sim.cli import main
from living_island.sim.runner import checkpoint_filename, reexecute, resume, run
from living_island.world.content import canonical_json_bytes
from living_island.world.ports import create_engine
from living_island.world.protocol import Coord, TileTarget


def _checkpoint(directory, tick):
    return directory / checkpoint_filename(tick)


def _script(path, content, actors):
    fixture = ScriptFixture(script_schema_version="0.1", actors=actors)
    path.write_bytes(canonical_json_bytes(fixture.model_dump(mode="json")))
    return load_script(path, content.config)


def _actor(actor_id="ella", plans=(), on_exhausted="wait"):
    return ActorScript(actor_id=actor_id, plans=list(plans), on_exhausted=on_exhausted)


def _contents(directory):
    return (
        directory.stat().st_mtime_ns,
        {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()},
    )


def _streams(directory):
    return tuple((directory / name).read_bytes() for name in ("events.jsonl", "decisions.jsonl"))


def test_ai08_mechanics_1008_ticks_resume_mid_move_and_queued_plan(tmp_path):
    # Mechanics only. With hunger/thirst decay disabled, living residents keep exercising
    # ongoing actions and queued plans throughout this checkpoint equivalence run.
    content = content_with(
        {"ella": (6, 4), "ryan": (8, 4)},
        map={"walk_cost_budget_per_tick": 2},
        perception={"day_radius_tiles": 10},
        needs={"satiety_decay_per_tick": 0, "hydration_decay_per_tick": 0},
    )
    move = template("move_to", TileTarget(kind="tile", position=Coord(x=2, y=4)))
    sleep_plans = [[template("sleep")]] * 22
    script = _script(
        tmp_path / "mechanics.json",
        content,
        [
            _actor("ella", [[move, WAIT], *sleep_plans]),
            _actor("ryan", sleep_plans),
        ],
    )
    whole, prefix, tail = (tmp_path / name for name in ("whole", "prefix", "tail"))
    uninterrupted = run(content, 1008, whole, script=script)
    run(content, 1, prefix, script=script)
    source_before = _contents(prefix)
    checkpoint = _checkpoint(prefix, 1)
    saved = read_checkpoint(checkpoint, content)
    assert any(a.intent.action_type == "move_to" for a in saved.world.active_actions)
    [queued] = saved.agent_state.queued_plans
    assert [i.intent_id for i in queued.intents] == ["ella:p000000:i1"]
    assert [p.actor_id for p in saved.pending_perception_deliveries] == ["ella", "ryan"]
    assert [p.observed_tick for p in saved.pending_perception_deliveries] == [1, 1]
    continued = resume(checkpoint, prefix, 1007, tail)
    assert continued.world.tick == 1008
    assert all(r.alive for r in continued.world.residents)
    assert continued.world == uninterrupted.world
    assert _checkpoint(whole, 1008).read_bytes() == _checkpoint(tail, 1008).read_bytes()
    assert tuple(a + b for a, b in zip(_streams(prefix), _streams(tail), strict=True)) == (
        _streams(whole)
    )
    assert _contents(prefix) == source_before


def test_resume_of_continuation_rebuilds_verified_ancestors(tmp_path):
    content = content_with({"ella": (2, 3)})
    original, middle, final = (tmp_path / name for name in ("a", "b", "c"))
    full = run(content, 5, original, checkpoint_every=1)
    before_a = _contents(original)
    resume(_checkpoint(original, 1), original, 2, middle)
    before_b = _contents(middle)
    continued = resume(_checkpoint(middle, 3), middle, 2, final)
    assert full.world == continued.world
    save = read_checkpoint(_checkpoint(original, 1), content)
    for whole, a, b, cursor in zip(
        _streams(original),
        _streams(middle),
        _streams(final),
        (save.event_cursor, save.decision_record_cursor),
        strict=True,
    ):
        assert whole == b"".join(whole.splitlines(keepends=True)[:cursor]) + a + b
    assert _contents(original) == before_a
    assert _contents(middle) == before_b


def test_ai10_recorded_reexecution_is_byte_identical(tmp_path):
    content = content_with({"ella": (2, 3), "ryan": (4, 4)})
    source, target = tmp_path / "source", tmp_path / "target"
    result = run(content, 12, source)
    before = _contents(source)
    replay = reexecute(source, target)
    assert replay.world == result.world
    assert _streams(source) == _streams(target)
    assert (source / "decision-trace.json").read_bytes() == (
        target / "decision-trace.json"
    ).read_bytes()
    assert _contents(source) == before


@pytest.mark.parametrize(
    ("defect", "detail"),
    [
        ("request", "record mismatch"),
        ("plan", "event bytes differ"),
        ("oversize", "plan exceeds"),
        ("missing", "record mismatch"),
        ("duplicate", "decision_ordinal"),
        ("events", "events_sha256"),
        ("map", "map.txt"),
        ("config", "config_hash"),
        ("final-world", "final world hash"),
    ],
)
def test_ai10_reexecute_stops_on_tampering_without_a_fallback(tmp_path, defect, detail):
    content = content_with({"ella": (2, 3)})
    script = _script(tmp_path / "waits.json", content, [_actor()])
    source, target = tmp_path / "source", tmp_path / "target"
    run(content, 3, source, script=script)
    manifest_path = source / "decision-trace.json"
    decisions = source / "decisions.jsonl"
    manifest = json.loads(manifest_path.read_bytes())
    if defect == "events":
        with (source / "events.jsonl").open("ab") as stream:
            stream.write(b"\n")
    elif defect == "map":
        (source / "map.txt").write_bytes(b"damaged\n")
    elif defect == "config":
        path = source / "config.json"
        config = json.loads(path.read_bytes())
        config["meta"]["seed"] += 1
        path.write_bytes(canonical_json_bytes(config))
    elif defect == "final-world":
        manifest["final_world_sha256"] = "a" * 64
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    else:
        rows = [json.loads(row) for row in decisions.read_bytes().splitlines()]
        if defect == "request":
            rows[0]["request_sha256"] = "a" * 64
        elif defect == "plan":
            rows[0]["plan"]["intents"][0]["action_type"] = "eat"
        elif defect == "oversize":
            plan = rows[0]["plan"]
            plan["intents"] = [
                {**plan["intents"][0], "intent_id": f"{plan['plan_id']}:i{index}"}
                for index in range(content.config.agents.max_plan_actions + 1)
            ]
        elif defect == "missing":
            rows.pop()
        else:
            rows.insert(1, rows[0])
        raw = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
        decisions.write_bytes(raw)
        manifest["decisions_sha256"] = sha256(raw).hexdigest()
        manifest["record_count"] = len(rows)
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    before = _contents(source)
    with pytest.raises(ReplayDiverged, match=f"REPLAY_DIVERGED:.*{detail}"):
        reexecute(source, target)
    assert not (target / "decision-trace.json").exists()
    if target.exists():
        assert b"sim-fallback-wait" not in (target / "decisions.jsonl").read_bytes()
        assert b"agent_fallback_used" not in (target / "events.jsonl").read_bytes()
    assert _contents(source) == before


def test_ai12_restores_exact_transient_packet_once_and_refuses_mid_ingest_save():
    content = content_with(
        {"ella": (2, 3), "ryan": (3, 4)},
        perception={"day_radius_tiles": 1, "night_radius_tiles": 1},
    )
    move = template("move_to", TileTarget(kind="tile", position=Coord(x=4, y=3)))
    ella, ryan = scripted("ella", [[move]]), scripted("ryan", [])
    source = BoundaryLoop(create_engine(content, None), [ella, ryan])
    initial = source.boundary
    committed, _ = source.advance()
    saved = source.checkpoint()
    packet = saved.pending_perception_deliveries[0]
    assert packet.perception.transient_sightings
    assert packet == committed.pending_deliveries[0]

    class TrackingRuntime(Runtime):
        def ingest(self, delivery):
            received.append(delivery.model_copy(deep=True))
            super().ingest(delivery)

        def decide(self, request):
            with pytest.raises(ValueError, match="pre-ingest"):
                restored.checkpoint()
            return super().decide(request)

    received = []
    saved_ella, saved_ryan = saved.agent_state.runtime_states
    ella = TrackingRuntime("ella", saved_ella.policy_config, PROFILE, WaitPolicy(), saved_ella)
    ryan = Runtime("ryan", saved_ryan.policy_config, PROFILE, WaitPolicy(), saved_ryan)
    with pytest.raises(ValueError, match="no ingested perception"):
        ella.make_request(saved.world.tick, ["PLAN_FINISHED"])
    restored = BoundaryLoop(
        create_engine(content, saved.world, initial.events + committed.events),
        [ella, ryan],
        saved,
    )
    restored.advance()
    restored.advance()
    assert received[0] == packet
    assert [entry.observed_tick for entry in received] == [1, 2]

    data = saved.model_dump()
    data["pending_perception_deliveries"] = []
    with pytest.raises(ValueError, match="one pending delivery"):
        SavePackage.model_validate(data)


@pytest.mark.parametrize("identity", ["script", "seed", "plan-limit", "policy"])
def test_ai13_resume_refuses_changed_runtime_inputs(tmp_path, identity):
    content = content_with({"ella": (2, 3)})
    script = _script(tmp_path / "script.json", content, [_actor()])
    source, target = tmp_path / "source", tmp_path / "target"
    run(content, 2, source, script=script)
    checkpoint = _checkpoint(source, 2)
    if identity == "script":
        retained = source / "script.json"
        fixture = json.loads(retained.read_bytes())
        fixture["actors"][0]["on_exhausted"] = "error"
        retained.write_bytes(canonical_json_bytes(fixture))
        expected = "script_sha256"
    else:
        data = json.loads(checkpoint.read_bytes())
        state = data["agent_state"]["runtime_states"][0]
        config = state["policy_config"]
        if identity == "seed":
            config["seed"] += 1
            expected = "policy_config.seed"
        elif identity == "plan-limit":
            config["max_plan_actions"] += 1
            expected = "policy_config.max_plan_actions"
        else:
            config.update(policy_id="random-v0", script_sha256=None)
            state["policy_state"] = {}
            expected = "policy_config"
        checkpoint = tmp_path / "altered.json"
        checkpoint.write_bytes(canonical_json_bytes(data))
    with pytest.raises(ValueError, match=expected):
        resume(checkpoint, source, 1, target)
    assert not target.exists()


def test_ai14_preserves_error_record_provenance_across_resume_and_reexecute(tmp_path):
    content = content_with({"ella": (2, 3)})
    script = _script(tmp_path / "fault.json", content, [_actor(on_exhausted="error")])
    original, continued, replay = (tmp_path / name for name in ("original", "continued", "replay"))
    run(content, 3, original, script=script, checkpoint_every=1)
    before = _contents(original)
    resume(_checkpoint(original, 1), original, 2, continued)
    reexecute(original, replay)
    _, full = _streams(original)
    _, tail = _streams(continued)
    assert full.splitlines(keepends=True)[1:] == tail.splitlines(keepends=True)
    assert _streams(original) == _streams(replay)
    records = [json.loads(line) for line in full.splitlines()]
    assert [record["decision_ordinal"] for record in records] == [0, 1, 2]
    assert {
        (r["policy_id"], r["effective_policy_id"], r["error_kind"], r["substituted"])
        for r in records
    } == {("scripted-v0", "sim-fallback-wait", "SCRIPT_EXHAUSTED", True)}
    assert _contents(original) == before


def test_observer_runs_after_flush_before_checkpoint_once_per_new_boundary(tmp_path):
    content = content_with({"ella": (2, 3)})
    source, target = tmp_path / "source", tmp_path / "target"
    seen = []

    def observe(world, events):
        seen.append(world.tick)
        assert all(event.tick == world.tick for event in events)
        assert not _checkpoint(source, world.tick).exists()
        event_raw, decision_raw = _streams(source)
        assert event_raw.count(b"\n") == world.event_log_cursor
        assert not world.tick or decision_raw
        world.residents[0].health = 1  # observer only sees isolated copies

    result = run(content, 3, source, checkpoint_every=1, on_boundary_committed=observe)
    assert seen == [0, 1, 2, 3]
    assert result.world.residents[0].health != 1
    seen.clear()
    resume(
        _checkpoint(source, 1),
        source,
        2,
        target,
        on_boundary_committed=lambda world, events: seen.append(world.tick),
    )
    assert seen == [2, 3]


def test_observer_failure_stops_publication_and_leaves_resume_destination_free(tmp_path):
    content = content_with({"ella": (2, 3)})
    source, target, failed = (tmp_path / name for name in ("source", "target", "failed"))
    run(content, 1, source)
    before = _contents(source)
    seen = []

    def broken(world, events):
        seen.append(world.tick)
        raise OSError("observer unavailable")

    with pytest.raises(OSError, match="observer unavailable"):
        run(content, 3, failed, on_boundary_committed=broken)
    assert seen == [0]
    assert not _checkpoint(failed, 0).exists()
    assert not (failed / "decision-trace.json").exists()
    assert {json.loads(line)["tick"] for line in _streams(failed)[0].splitlines()} == {0}
    with pytest.raises(OSError, match="observer unavailable"):
        resume(_checkpoint(source, 1), source, 2, target, on_boundary_committed=broken)
    assert seen == [0, 2]
    assert not target.exists()
    assert resume(_checkpoint(source, 1), source, 2, target).world.tick == 3
    assert _contents(source) == before


def test_restore_rejects_reused_completed_intent_id():
    content = content_with({"ella": (2, 3)})
    engine = create_engine(content, None)
    initial = engine.initial_commit()
    original = intent("wait")
    engine.begin_tick()
    engine.start_intent(original)
    committed = engine.advance_tick()
    assert not committed.snapshot.active_actions
    restored = create_engine(content, committed.snapshot, initial.events + committed.events)
    for candidate in (engine, restored):
        candidate.begin_tick()
        with pytest.raises(ValueError, match="intent ID"):
            candidate.start_intent(original)


def test_cli_seed_zero_tick_and_incompatible_flags(tmp_path, capsys):
    output = tmp_path / "run"
    arguments = [
        "run",
        "--config",
        str(WORLDS / "default.toml"),
        "--ticks",
        "0",
        "--policy",
        "random",
        "--out",
        str(output),
    ]

    assert main([*arguments, "--script", "extra.json"]) == 1
    assert "--script is required" in capsys.readouterr().err
    with pytest.raises(SystemExit) as error:
        main([*arguments, "--checkpoint-every", "0"])
    assert error.value.code == 2
    assert main([*arguments, "--seed", "42"]) == 0
    assert "tick=0" in capsys.readouterr().out
    [checkpoint] = list(output.glob("checkpoint-*.json"))
    data = json.loads(checkpoint.read_bytes())
    assert data["world"]["resolution_rng_state_uint32"] == 42
    assert {r["policy_config"]["seed"] for r in data["agent_state"]["runtime_states"]} == {42}
    assert json.loads((output / "config.json").read_bytes())["meta"]["seed"] == 42
    assert data["world"]["static_map_ref"] == "default-island.map"
    assert main(arguments) == 1
    assert "new or empty output directory" in capsys.readouterr().err


def test_resume_rejects_per_actor_ordinals_even_if_total_matches(tmp_path):
    content = content_with({"ella": (2, 3), "ryan": (4, 4)})
    script = _script(
        tmp_path / "sleep.json",
        content,
        [
            _actor("ella", [[template("sleep")]]),
            _actor("ryan", [[template("sleep")]]),
        ],
    )
    source, target = tmp_path / "source", tmp_path / "target"
    run(content, 2, source, script=script)
    data = json.loads(_checkpoint(source, 2).read_bytes())
    first, second = data["agent_state"]["runtime_states"]
    first["next_decision_ordinal"], second["next_decision_ordinal"] = 0, 2
    assert data["decision_record_cursor"] == 2
    checkpoint = tmp_path / "ordinals.json"
    checkpoint.write_bytes(canonical_json_bytes(data))
    with pytest.raises(ValueError, match="next_decision_ordinal"):
        resume(checkpoint, source, 1, target)
    assert not target.exists()


def test_checkpoint_write_error_stops_after_observer_and_before_completion(tmp_path, monkeypatch):
    from living_island.sim import runner

    content = content_with({"ella": (2, 3)})
    output = tmp_path / "target"
    observed = []

    def fail_checkpoint(path, save):
        assert observed == [0]
        assert _streams(output)[0]
        raise OSError("checkpoint write failed")

    monkeypatch.setattr(runner, "write_checkpoint", fail_checkpoint)
    with pytest.raises(OSError, match="checkpoint write failed"):
        run(
            content,
            3,
            output,
            on_boundary_committed=lambda world, events: observed.append(world.tick),
        )
    assert not (output / "decision-trace.json").exists()


def test_cli_resume_export_refusal_does_not_create_files(tmp_path, capsys):
    output = tmp_path / "target"
    source = ["--source-run", str(tmp_path / "missing"), "--out", str(output), "--export-replay"]
    assert main(["resume", "--checkpoint", "missing", "--ticks", "1", *source]) == 1
    assert "use reexecute --export-replay" in capsys.readouterr().err

    assert not output.exists()


@pytest.mark.parametrize("command", ["run", "reexecute"])
def test_cli_names_partial_fresh_output_after_failure(command, tmp_path, monkeypatch, capsys):
    from living_island.sim import runner

    output = tmp_path / "partial"
    if command == "run":
        args = [
            "run",
            "--config",
            str(WORLDS / "default.toml"),
            "--ticks",
            "1",
            "--policy",
            "random",
        ]
    else:
        source = tmp_path / "source"
        run(content_with({"ella": (2, 3)}), 1, source)
        args = ["reexecute", "--source-run", str(source)]
    write_checkpoint = runner.write_checkpoint

    def fail_final_checkpoint(path, save):
        if save.world.tick == 1:
            raise OSError("injected checkpoint failure")
        write_checkpoint(path, save)

    monkeypatch.setattr(runner, "write_checkpoint", fail_final_checkpoint)
    assert main([*args, "--out", str(output)]) == 1
    err = capsys.readouterr().err
    assert "injected checkpoint failure" in err
    assert f"Incomplete run output at {output.resolve()}" in err
    assert "Use a new --out directory to retry." in err
    assert _checkpoint(output, 0).exists()
    assert (output / "decisions.jsonl").read_bytes()
    assert not (output / "decision-trace.json").exists()


def test_recorded_checkpoint_resume_verifies_and_consumes_the_source_trace(tmp_path):
    content = content_with({"ella": (2, 3)})
    original, replay, continuation = (tmp_path / name for name in ("a", "b", "c"))
    initial = run(content, 4, original)
    reexecute(original, replay)
    before = _contents(replay)
    checkpoint = _checkpoint(replay, 0)
    save = read_checkpoint(checkpoint, content)
    assert save.agent_state.runtime_states[0].policy_config.policy_id == "recorded-v0"
    resumed = resume(checkpoint, replay, 4, continuation)
    assert initial.world == resumed.world
    assert _streams(continuation) == (
        b"".join(_streams(original)[0].splitlines(keepends=True)[save.event_cursor :]),
        _streams(original)[1],
    )
    with pytest.raises(ReplayDiverged, match="beyond the source trace"):
        resume(checkpoint, replay, 5, tmp_path / "too-long")
    assert _contents(replay) == before
