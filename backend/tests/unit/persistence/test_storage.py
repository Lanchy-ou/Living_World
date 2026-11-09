"""Persistence acceptance tests using canonical DTOs and hand-built events."""

import json
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from living_island.agents.types import DecisionRecord, build_intent_id, build_plan_id
from living_island.contract.save import SavePackage
from living_island.events import WorldEvent, format_event_id
from living_island.persistence import _files
from living_island.persistence._codec import PersistenceError
from living_island.persistence.checkpoints import read_checkpoint, write_checkpoint
from living_island.persistence.content import (
    load_run_content,
    load_world_content,
    retain_run_content,
)
from living_island.persistence.logs import (
    DecisionLogWriter,
    EventLogWriter,
    read_decisions,
    read_events,
)
from living_island.persistence.resume import open_resume_output
from living_island.persistence.scripts import load_script
from living_island.persistence.trace import load_trace, write_trace
from living_island.world.content import (
    WorldContent,
    build_world_content,
    canonical_json_bytes,
    map_bytes_from_rows,
)
from living_island.world.protocol import format_delivery_id

RUN_ID = "run"
ACTOR = "ella"


@pytest.fixture
def content() -> WorldContent:
    path = Path(__file__).resolve().parents[4] / "content" / "worlds" / "default.toml"
    config = load_world_content(path).config.model_dump()
    config["meta"]["run_id"] = RUN_ID
    config["map"].update(width=5, height=4)
    config["world"].update(
        spring=[1, 1],
        initial_cave=[2, 1],
        fruit_trees=[{"id": "fruit_01", "position": [2, 2], "regrow_phase_offset_ticks": 0}],
    )
    config["world"]["cues"][0]["position"] = [3, 1]
    config["residents"] = [r for r in config["residents"] if r["id"] == ACTOR]
    config["residents"][0]["position"] = [1, 2]
    config["canteen"]["initial_owner_id"] = ACTOR
    return build_world_content(config, map_bytes_from_rows(["~~~~~", "~SCM~", "~.F.~", "~~~~~"]))


def checkpoint_data(
    content: WorldContent, tick: int = 0, ordinal: int = 0, death: int | None = None
) -> dict[str, Any]:
    config = content.config
    position = {"x": 1, "y": 2}
    cursor = tick - 1 if death is None else death - 1
    pending = (
        []
        if death is not None
        else [
            {
                "delivery_id": format_delivery_id(RUN_ID, tick, ACTOR),
                "actor_id": ACTOR,
                "observed_tick": tick,
                "decision_triggers": [],
                "perception": {
                    "schema_version": "0.1",
                    "actor_id": ACTOR,
                    "tick": tick,
                    "own_condition": dict.fromkeys(
                        ("satiety", "hydration", "stamina", "health"), "strong"
                    ),
                    "own_position": position,
                    "own_inventory": {
                        "fruit_count": 0,
                        "canteen_id": config.canteen.unique_item_id,
                        "canteen_servings": config.canteen.initial_servings,
                    },
                    "visible_tiles": [{"position": position, "terrain": "grass"}],
                    "visible_entities": [],
                    "transient_sightings": [],
                    "explored_static_tiles": [],
                    "environmental_cues": [],
                    "heard_utterances": [],
                    "last_action_feedback": None,
                },
            }
        ]
    )
    return {
        "save_schema_version": "0.1",
        "world": {
            "schema_version": "0.1",
            "world_id": config.meta.world_id,
            "run_id": RUN_ID,
            "tick": tick,
            "config_hash": content.config_hash,
            "map_hash": content.map_hash,
            "static_map_ref": config.map.layout_file,
            "residents": [
                {
                    "id": ACTOR,
                    "position": position,
                    "alive": death is None,
                    "satiety": 7500,
                    "hydration": 8000,
                    "stamina": 8500,
                    "health": 10000 if death is None else 0,
                    "fruit_count": 0,
                }
            ],
            "fruit_nodes": [
                {
                    "id": "fruit_01",
                    "position": {"x": 2, "y": 2},
                    "stock": 1,
                    "regrow_phase_offset_ticks": 0,
                }
            ],
            "cave": {"x": 2, "y": 1},
            "spring": {"x": 1, "y": 1},
            "cues": [
                {
                    "id": "moss_east_01",
                    "kind": "damp_moss",
                    "position": {"x": 3, "y": 1},
                }
            ],
            "ground_fruit": [],
            "lifetime_fruit_regrown": 0,
            "lifetime_fruit_consumed": 0,
            "unique_canteen": {
                "id": config.canteen.unique_item_id,
                "holder_id": ACTOR if death is None else None,
                "ground_position": None if death is None else position,
                "servings": config.canteen.initial_servings,
            },
            "corpses": []
            if death is None
            else [
                {
                    "id": "corpse@ella",
                    "resident_id": ACTOR,
                    "position": position,
                    "death_tick": death,
                }
            ],
            "dialogue_sessions": [],
            "active_actions": [],
            "explored_tiles_by_resident": [],
            "exposure_receipts_by_resident": [],
            "resolution_rng_state_uint32": config.meta.seed,
            "event_log_cursor": 1,
            "next_event_seq_in_tick": int(tick == 0),
            "rule_overrides": {},
        },
        "agent_state": {
            "profiles": [],
            "goal_states": [],
            "personal_memories": [],
            "relationships": [],
            "queued_plans": [],
            "deferred_decision_triggers": [],
            "delivered_perception_ticks": [{"actor_id": ACTOR, "last_observed_tick": cursor}],
            "runtime_states": [
                {
                    "actor_id": ACTOR,
                    "next_decision_ordinal": ordinal,
                    "policy_state": {},
                    "latest_perception_tick": cursor,
                    "policy_config": {
                        "policy_id": "random-v0",
                        "seed": config.meta.seed,
                        "max_plan_actions": config.agents.max_plan_actions,
                        "map_width": config.map.width,
                        "map_height": config.map.height,
                        "script_sha256": None,
                        "source_trace_sha256": None,
                    },
                }
            ],
        },
        "event_cursor": 1,
        "llm_record_cursor": 0,
        "decision_record_cursor": ordinal,
        "pending_perception_deliveries": pending,
        "canonical_config_hash": content.config_hash,
        "canonical_map_hash": content.map_hash,
    }


def fact(content: WorldContent, tick: int = 0, *, causes: list[str] | None = None) -> WorldEvent:
    return WorldEvent.model_validate(
        {
            "schema_version": "0.1",
            "run_id": RUN_ID,
            "event_id": format_event_id(RUN_ID, tick, 0),
            "tick": tick,
            "seq_in_tick": 0,
            "type": "world_initialized" if tick == 0 else "fruit_regrew",
            "actor_id": None,
            "target_id": None,
            "intent_id": None,
            "llm_call_id": None,
            "caused_by_event_ids": causes or [],
            "payload": (
                {
                    "config_hash": content.config_hash,
                    "map_hash": content.map_hash,
                    "initial_snapshot_hash": "a" * 64,
                }
                if tick == 0
                else {"tree_id": "果樹", "quantity": 1, "stock_before": 0, "stock_after": 1}
            ),
        }
    )


def decision(tick: int = 0, ordinal: int = 0, actor: str = ACTOR) -> DecisionRecord:
    plan_id = build_plan_id(actor, ordinal)
    return DecisionRecord.model_validate(
        {
            "record_schema_version": "0.1",
            "run_id": RUN_ID,
            "tick": tick,
            "actor_id": actor,
            "decision_ordinal": ordinal,
            "policy_id": "random-v0",
            "effective_policy_id": "random-v0",
            "triggers": ["PLAN_FINISHED"] if tick else [],
            "request_sha256": "a" * 64,
            "status": "ok",
            "error_kind": None,
            "substituted": False,
            "llm_call_id": None,
            "plan": {
                "plan_id": plan_id,
                "actor_id": actor,
                "created_at_tick": tick,
                "intents": [
                    {
                        "plan_id": plan_id,
                        "actor_id": actor,
                        "intent_id": build_intent_id(plan_id, 0),
                        "action_type": "wait",
                        "target": None,
                        "parameters": {},
                        "reason": None,
                    }
                ],
            },
        }
    )


def canonical(model: Any) -> bytes:
    return canonical_json_bytes(model.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda raw: b"\xef\xbb\xbf" + raw, "JSON"),
        (lambda raw: raw[:-1] + b"\r\n", "JSON"),
        (lambda raw: raw[:-1], "JSONL"),
        (lambda raw: raw + b"\n", "JSON"),
        (lambda raw: raw.replace(b'"tick":0', b'"tick": 0'), "JSON"),
        (lambda raw: raw.replace(b'"tick":0', b'"tick":0.0'), "$.tick"),
        (lambda raw: raw.replace(b'"tick":0', b'"tick":NaN'), "$.tick"),
        (lambda raw: raw.replace(b'"tick":0', b'"tick":Infinity'), "$.tick"),
        (lambda raw: raw.replace(b'"tick":0', b'"tick":0,"tick":0'), "JSON"),
        (lambda raw: raw.replace(b'"0.1"', b'"0.2"'), "schema_version"),
        (
            lambda raw: raw.replace(b'"run_id":"run"', b'"run_id":"other"').replace(
                b'"run:0000000000:', b'"other:0000000000:'
            ),
            "run_id",
        ),
    ],
)
def test_bad_event_bytes(tmp_path: Path, content: WorldContent, mutation: Any, field: str) -> None:
    path = tmp_path / "events.jsonl"
    raw = mutation(canonical(fact(content)) + b"\n")
    path.write_bytes(raw)
    with pytest.raises(PersistenceError) as error:
        read_events(path, RUN_ID)
    assert (error.value.path, error.value.field) == (path, field)
    assert error.value.line == (2 if raw.endswith(b"\n\n") else 1)


def test_decision_ordinals_are_actor_local(tmp_path: Path) -> None:
    path = tmp_path / "decisions.jsonl"
    writer = DecisionLogWriter(path, RUN_ID)
    initial = [decision(), decision(actor="mia")]
    writer.append(initial)
    with pytest.raises(PersistenceError, match="decision_ordinal"):
        writer.append([decision(1, 2)])
    assert read_decisions(path, RUN_ID) == tuple(initial)
    writer.append([decision(1, 1)])
    expected = [*initial, decision(1, 1)]
    assert read_decisions(path, RUN_ID) == tuple(expected)
    assert path.read_bytes() == b"".join(canonical(item) + b"\n" for item in expected)
    path.write_bytes(path.read_bytes() + canonical(decision(2, 3)) + b"\n")
    with pytest.raises(PersistenceError, match="decisions.jsonl:4: decision_ordinal"):
        read_decisions(path, RUN_ID)
    path.write_bytes(canonical(decision()).replace(b'"0.1"', b'"1.0"') + b"\n")
    with pytest.raises(PersistenceError, match="record_schema_version"):
        read_decisions(path, RUN_ID)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], max_examples=25)
@given(label=st.text(), tick=st.integers(min_value=1, max_value=100), data=st.data())
def test_round_trip_is_byte_identical(
    tmp_path: Path, content: WorldContent, label: str, tick: int, data: st.DataObject
) -> None:
    # A fresh directory for each example, including during shrinking.
    from tempfile import mkdtemp

    directory = mkdtemp(dir=tmp_path)
    first = Path(directory) / "first"
    second = Path(directory) / "second"
    first.mkdir()
    second.mkdir()
    ordinal = data.draw(st.integers(min_value=0, max_value=tick))
    payload = checkpoint_data(content, tick=tick, ordinal=ordinal)
    payload["agent_state"]["profiles"] = [{"name": label}]
    checkpoint = SavePackage.model_validate(payload)
    write_checkpoint(first / "save.json", checkpoint)
    write_checkpoint(second / "save.json", read_checkpoint(first / "save.json", content))
    for path in (first, second):
        retain_run_content(path, content)
    event_records = (fact(content), fact(content, tick))
    decisions = tuple(decision(i, i) for i in range(ordinal))
    EventLogWriter(first / "events.jsonl", RUN_ID).append(event_records)
    DecisionLogWriter(first / "decisions.jsonl", RUN_ID).append(decisions)
    EventLogWriter(second / "events.jsonl", RUN_ID).append(
        read_events(first / "events.jsonl", RUN_ID)
    )
    DecisionLogWriter(second / "decisions.jsonl", RUN_ID).append(
        read_decisions(first / "decisions.jsonl", RUN_ID)
    )
    final = checkpoint.world.model_copy(update={"event_log_cursor": len(event_records)})
    write_trace(first, final)
    write_trace(second, final)
    for file in ("save.json", "events.jsonl", "decisions.jsonl", "decision-trace.json"):
        assert (first / file).read_bytes() == (second / file).read_bytes()
    assert "果樹".encode() in (first / "events.jsonl").read_bytes()


@pytest.mark.parametrize(
    "case", ["ordinal", "death_at", "death_behind", "death_ordinal", "no_death"]
)
def test_impossible_checkpoint_histories_on_disk(
    tmp_path: Path, content: WorldContent, case: str
) -> None:
    path = tmp_path / "save.json"
    if case == "ordinal":
        data = checkpoint_data(content, tick=4, ordinal=5)
        field = "next_decision_ordinal"
    else:
        data = checkpoint_data(content, tick=4, ordinal=1, death=2)
        field = "latest_perception_tick"
        if case == "no_death":
            data["world"]["corpses"].clear()
            field = "death_tick"
        elif case == "death_ordinal":
            data["agent_state"]["runtime_states"][0]["next_decision_ordinal"] = 3
            data["decision_record_cursor"] = 3
            field = "next_decision_ordinal"
        else:
            cursor = 2 if case == "death_at" else 0
            data["agent_state"]["runtime_states"][0]["latest_perception_tick"] = cursor
            data["agent_state"]["delivered_perception_ticks"][0]["last_observed_tick"] = cursor
    SavePackage.model_validate(data)  # DTO alone accepts these histories.
    path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(PersistenceError, match=field):
        read_checkpoint(path, content)


def test_death_on_saved_boundary_is_valid(tmp_path: Path, content: WorldContent) -> None:
    path = tmp_path / "save.json"
    data = checkpoint_data(content, tick=1, ordinal=1, death=1)
    save_package = SavePackage.model_validate(data)
    write_checkpoint(path, save_package)
    assert read_checkpoint(path, content) == save_package


def test_atomic_checkpoint_refuses_existing_and_interrupted_write(
    tmp_path: Path, content: WorldContent, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "save.json"
    save_package = SavePackage.model_validate(checkpoint_data(content))
    write_checkpoint(path, save_package)
    with pytest.raises(PersistenceError, match="exists"):
        write_checkpoint(path, save_package)
    assert path.read_bytes() == canonical(save_package)

    def fail_replace(source: Path, target: Path) -> None:
        assert source.parent == target.parent
        assert source.read_bytes() == canonical(save_package)
        raise OSError("simulated publication interruption")

    monkeypatch.setattr(_files.os, "replace", fail_replace)
    with pytest.raises(PersistenceError, match="interruption"):
        write_checkpoint(tmp_path / "interrupted.json", save_package)
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_checkpoint_publishers_do_not_clobber(
    tmp_path: Path, content: WorldContent
) -> None:
    path = tmp_path / "save.json"
    checkpoints = [
        SavePackage.model_validate(checkpoint_data(content, tick=1, ordinal=ordinal))
        for ordinal in (0, 1)
    ]

    def attempt(checkpoint: SavePackage) -> bytes | None:
        try:
            write_checkpoint(path, checkpoint)
        except PersistenceError:
            return None
        return canonical(checkpoint)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [result for result in pool.map(attempt, checkpoints) if result is not None]
    assert results == [path.read_bytes()]


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("save_schema_version", "9.0"),
        ("canonical_config_hash", "b" * 64),
    ],
)
def test_checkpoint_version_and_content_hash(
    tmp_path: Path, content: WorldContent, field: str, replacement: str
) -> None:
    data = checkpoint_data(content)
    data[field] = replacement
    if field == "canonical_config_hash":
        data["world"]["config_hash"] = replacement
    path = tmp_path / "save.json"
    path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(PersistenceError, match=field):
        read_checkpoint(path, content)


def source_run(directory: Path, content: WorldContent) -> Path:
    directory.mkdir()
    retain_run_content(directory, content)
    EventLogWriter(directory / "events.jsonl", RUN_ID).append([fact(content)])
    DecisionLogWriter(directory / "decisions.jsonl", RUN_ID).append([decision()])
    path = directory / "checkpoint.json"
    write_checkpoint(path, SavePackage.model_validate(checkpoint_data(content, tick=1, ordinal=1)))
    return path


def test_resume_writes_only_continuation_and_preserves_source(
    tmp_path: Path, content: WorldContent
) -> None:
    source = tmp_path / "source"
    output = tmp_path / "output"
    checkpoint = source_run(source, content)
    # A damaged later tail is outside this checkpoint and must never be consumed.
    with (source / "events.jsonl").open("ab") as stream:
        stream.write(b"partial future record")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()}
    directory_mtime = source.stat().st_mtime_ns
    resumed = open_resume_output(source, output, checkpoint)
    initial = fact(content)
    event = fact(content, 2, causes=[initial.event_id])
    with pytest.raises(PersistenceError, match="post-checkpoint event"):
        resumed.events.append([fact(content, 1)])
    resumed.events.append([event])
    with pytest.raises(PersistenceError):
        resumed.decisions.append([decision()])
    resumed.decisions.append([decision(1, 1)])
    assert (output / "events.jsonl").read_bytes() == canonical(event) + b"\n"
    assert (output / "decisions.jsonl").read_bytes() == canonical(decision(1, 1)) + b"\n"
    assert read_events(output / "events.jsonl", RUN_ID, prior=[initial], after_tick=1) == (event,)
    assert read_decisions(output / "decisions.jsonl", RUN_ID, ordinals={ACTOR: 1}, from_tick=1) == (
        decision(1, 1),
    )
    assert (output / "resume-origin.json").read_bytes() == canonical_json_bytes(
        {
            "source_run_id": RUN_ID,
            "checkpoint_tick": 1,
            "event_cursor": 1,
            "decision_record_cursor": 1,
            "checkpoint_sha256": sha256(checkpoint.read_bytes()).hexdigest(),
        }
    )
    for forbidden in (source / ".." / "source", source / "child", output):
        with pytest.raises(PersistenceError, match="output"):
            open_resume_output(source, forbidden, checkpoint)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()}
    assert source.stat().st_mtime_ns == directory_mtime


@pytest.mark.parametrize("artifact", ["config.json", "map.txt"])
def test_retained_content_is_verified(tmp_path: Path, content: WorldContent, artifact: str) -> None:
    retain_run_content(tmp_path, content)
    hashes = {"expected_config_hash": content.config_hash, "expected_map_hash": content.map_hash}
    assert load_run_content(tmp_path, **hashes) == content
    path = tmp_path / artifact
    if artifact == "config.json":
        data = json.loads(path.read_bytes())
        data["meta"]["seed"] += 1
        path.write_bytes(canonical_json_bytes(data))
        expected = "config_hash"
    else:
        path.write_bytes(path.read_bytes().replace(b"~.F.~", b"~.F,~"))
        expected = "map_hash"
    with pytest.raises(PersistenceError, match=expected):
        load_run_content(tmp_path, **hashes)


def script_data() -> dict[str, Any]:
    return {
        "script_schema_version": "0.1",
        "actors": [
            {
                "actor_id": ACTOR,
                "on_exhausted": "wait",
                "plans": [
                    [{"action_type": "wait", "target": None, "parameters": {}, "reason": "休息"}]
                ],
            }
        ],
    }


def test_script_identity_actor_slice_and_resume(tmp_path: Path, content: WorldContent) -> None:
    source = tmp_path / "source"
    source_run(source, content)
    path = source / "script.json"
    data = script_data()
    path.write_bytes(json.dumps(data, indent=2).encode())
    script = load_script(path, content.config)
    assert script.sha256 == sha256(canonical_json_bytes(data)).hexdigest()
    script.for_actor(ACTOR).plans.clear()
    assert len(script.for_actor(ACTOR).plans) == 1

    payload = checkpoint_data(content, tick=1, ordinal=1)
    saved_runtime = payload["agent_state"]["runtime_states"][0]
    saved_runtime["policy_config"].update(policy_id="scripted-v0", script_sha256=script.sha256)
    saved_runtime["policy_state"] = {"cursor": 1}
    checkpoint = source / "scripted-checkpoint.json"
    write_checkpoint(checkpoint, SavePackage.model_validate(payload))
    output = tmp_path / "out"
    assert open_resume_output(source, output, checkpoint).script is not None
    assert (output / "script.json").read_bytes() == canonical_json_bytes(data)
    data["actors"][0]["on_exhausted"] = "error"
    path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(PersistenceError, match="script_sha256"):
        open_resume_output(source, tmp_path / "changed", checkpoint)


@pytest.mark.parametrize("case", ["version", "missing_actor", "plan_limit", "unknown_field"])
def test_invalid_script(tmp_path: Path, content: WorldContent, case: str) -> None:
    path = tmp_path / "script.json"
    data = script_data()
    if case == "version":
        data["script_schema_version"] = "2.0"
    elif case == "missing_actor":
        data["actors"].clear()
    elif case == "plan_limit":
        plan_list = data["actors"][0]["plans"]
        plan_list[0] *= content.config.agents.max_plan_actions + 1
    else:
        data["actors"][0]["unused"] = None
    path.write_bytes(canonical_json_bytes(data))
    with pytest.raises(PersistenceError, match="script_schema_version|actors"):
        load_script(path, content.config)


@pytest.mark.parametrize(
    "mutation",
    [
        "identity",
        "record_count",
        "event_count",
        "decisions_sha256",
        "events_sha256",
        "trace_schema_version",
        "final_world_sha256",
        "run_id",
    ],
)
def test_verified_trace_and_tampering(tmp_path: Path, content: WorldContent, mutation: str) -> None:
    source = tmp_path / "source"
    checkpoint = source_run(source, content)
    world = read_checkpoint(checkpoint, content).world
    manifest = write_trace(source, world)
    assert manifest.final_world_sha256 == sha256(canonical(world)).hexdigest()
    trace = load_trace(source)
    assert trace.events == (fact(content),)
    assert trace.for_actor(ACTOR) == (decision(),)
    trace.for_actor(ACTOR)[0].plan.intents.clear()
    assert trace.for_actor(ACTOR) == (decision(),)
    path = source / "decision-trace.json"
    data = manifest.model_dump()
    if mutation == "identity":
        data["final_world_sha256"] = "b" * 64
        path.write_bytes(canonical_json_bytes(data))
        with pytest.raises(PersistenceError, match="source_trace_sha256"):
            load_trace(source, expected_sha256=trace.sha256)
    else:
        data[mutation] = 0 if mutation.endswith("count") else "bad"
        if mutation in {"decisions_sha256", "events_sha256"}:
            data[mutation] = "0" * 64
        path.write_bytes(canonical_json_bytes(data))
        with pytest.raises(PersistenceError, match=mutation):
            load_trace(source)


def test_recorded_resume_requires_the_saved_trace_identity(
    tmp_path: Path, content: WorldContent
) -> None:
    source = tmp_path / "source"
    path = source_run(source, content)
    manifest = write_trace(source, read_checkpoint(path, content).world)
    trace_path = source / "decision-trace.json"
    payload = checkpoint_data(content, tick=1, ordinal=1)
    payload["agent_state"]["runtime_states"][0]["policy_config"].update(
        policy_id="recorded-v0", source_trace_sha256=sha256(trace_path.read_bytes()).hexdigest()
    )
    checkpoint = source / "recorded-checkpoint.json"
    write_checkpoint(checkpoint, SavePackage.model_validate(payload))
    output = tmp_path / "out"
    with pytest.raises(PersistenceError, match="requires a trace directory"):
        open_resume_output(source, output, checkpoint)
    assert not output.exists()
    resumed = open_resume_output(source, output, checkpoint, trace_directory=source)
    assert resumed.trace is not None
    assert resumed.trace.for_actor(ACTOR) == (decision(),)

    trace_path.write_bytes(canonical(manifest.model_copy(update={"final_world_sha256": "b" * 64})))
    with pytest.raises(PersistenceError, match="source_trace_sha256"):
        open_resume_output(source, tmp_path / "changed", checkpoint, trace_directory=source)


def test_resume_continuation_uses_ancestor_prefix(tmp_path: Path, content: WorldContent) -> None:
    source = tmp_path / "source"
    middle = tmp_path / "middle"
    checkpoint = source_run(source, content)
    resumed = open_resume_output(source, middle, checkpoint)
    initial = fact(content)
    event = fact(content, 2, causes=[initial.event_id])
    resumed.events.append([event])
    resumed.decisions.append([decision(1, 1)])
    data = checkpoint_data(content, tick=2, ordinal=2)
    data["world"].update(event_log_cursor=2, next_event_seq_in_tick=1)
    data["event_cursor"] = 2
    later_checkpoint = middle / "checkpoint.json"
    write_checkpoint(later_checkpoint, SavePackage.model_validate(data))

    output = tmp_path / "output"
    later = open_resume_output(middle, output, later_checkpoint, prior_events=(initial,))
    final_event = fact(content, 3, causes=[initial.event_id, event.event_id])
    later.events.append([final_event])
    later.decisions.append([decision(2, 2)])
    assert (output / "events.jsonl").read_bytes() == canonical(final_event) + b"\n"
    assert (output / "decisions.jsonl").read_bytes() == canonical(decision(2, 2)) + b"\n"
