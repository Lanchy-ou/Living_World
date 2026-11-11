"""CR-004 CLI, provenance refusals and artifact compatibility."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from test_engine_actions import content_with
from test_rule_policy_state import PARAMS
from world_builders import P1_WORLD, WORLDS

from living_island.agents.types import PolicyConfig
from living_island.persistence._codec import PersistenceError
from living_island.persistence.checkpoints import read_checkpoint
from living_island.persistence.content import load_world_content
from living_island.sim.cli import main
from living_island.sim.runner import checkpoint_filename, reexecute, resume, run
from living_island.world.content import canonical_json_bytes

DEFAULT_WORLD = WORLDS / "default.toml"


def _checkpoint(source, tick):
    return source / checkpoint_filename(tick)


def _runtime(raw):
    return raw["agent_state"]["runtime_states"][0]


def _read(path):
    return json.loads(path.read_bytes())


def _write(path, data):
    path.write_bytes(canonical_json_bytes(data))


def _cli_run(output, *flags, ticks=0, config=DEFAULT_WORLD):
    return main(
        [
            "run",
            "--config",
            str(config),
            "--ticks",
            str(ticks),
            "--out",
            str(output),
            *flags,
        ]
    )


@pytest.mark.parametrize("canteen", [None, "enabled", "restricted"])
@pytest.mark.parametrize("cue", [None, "enabled", "ignored"])
def test_cli_switches_write_shared_tick_zero_policy_config(tmp_path, canteen, cue):
    flags = ["--policy", "rule-based"]
    if canteen:
        flags += ["--rule-canteen", canteen]
    if cue:
        flags += ["--rule-cue", cue]
    assert _cli_run(tmp_path, *flags) == 0
    states = _read(_checkpoint(tmp_path, 0))["agent_state"]["runtime_states"]
    for state in states:
        assert state["policy_config"] == {
            **states[0]["policy_config"],
            "policy_id": "rule-based-v0",
            "script_sha256": None,
            "source_trace_sha256": None,
            "rule_params": {
                "rule_params_version": "0.1",
                "canteen_use": canteen or "enabled",
                "cue_use": cue or "enabled",
                "fruit_carry_target": 2,
                "failed_target_retry_ticks": 36,
            },
        }


def test_cli_params_file_overrides_all_fields(tmp_path):
    params = {
        **PARAMS.model_dump(),
        "canteen_use": "restricted",
        "cue_use": "ignored",
        "fruit_carry_target": 7,
        "failed_target_retry_ticks": 15,
    }
    path = tmp_path / "params.json"
    path.write_text(json.dumps(params, indent=2), encoding="utf-8")
    output = tmp_path / "run"
    assert _cli_run(output, "--policy", "rule-based", "--rule-params", str(path)) == 0
    states = _read(_checkpoint(output, 0))["agent_state"]["runtime_states"]
    assert all(r["policy_config"]["rule_params"] == params for r in states)


@pytest.mark.parametrize(
    "flags",
    [
        (),
        ("--policy", "recorded"),
        ("--policy", "random", "--script", "unused"),
        ("--policy", "random", "--rule-canteen", "enabled"),
        ("--policy", "random", "--rule-cue", "ignored"),
        ("--policy", "random", "--rule-params", "unused"),
        ("--policy", "scripted"),
        ("--policy", "scripted", "--script", "unused", "--rule-canteen", "enabled"),
        ("--policy", "scripted", "--script", "unused", "--rule-cue", "ignored"),
        ("--policy", "scripted", "--script", "unused", "--rule-params", "unused"),
        ("--policy", "rule-based", "--script", "unused"),
        ("--policy", "rule-based", "--rule-canteen", "ignored"),
        ("--policy", "rule-based", "--rule-cue", "restricted"),
        ("--policy", "rule-based", "--rule-canteen"),
        ("--policy", "rule-based", "--rule-unknown", "enabled"),
        ("--policy", "rule-based", "--rule-canteen", "enabled", "--rule-canteen", "enabled"),
        ("--policy", "rule-based", "--rule-cue", "enabled", "--rule-cue", "ignored"),
        ("--policy", "rule-based", "--rule-params", "unused", "--rule-params", "unused"),
        ("--policy", "rule-based", "--rule-params", "unused", "--rule-canteen", "enabled"),
        ("--policy", "rule-based", "--rule-cue", "ignored", "--rule-params", "unused"),
        ("--policy", "random", "--policy", "rule-based"),
        ("--policy", "scripted", "--script", "unused", "--script", "unused"),
    ],
)
def test_cli_rejects_other_policy_combinations(tmp_path, capsys, flags):
    out = tmp_path / "run"
    assert _cli_run(out, *flags) == 1
    assert capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize("command", ["resume", "reexecute"])
@pytest.mark.parametrize(
    "flag",
    [
        ("--policy", "random"),
        ("--script", "unused"),
        ("--rule-params", "unused"),
        ("--rule-canteen", "enabled"),
        ("--rule-cue", "ignored"),
    ],
)
def test_cli_restore_commands_take_no_policy_flags(tmp_path, capsys, command, flag):
    output = tmp_path / "run"
    args = [command, "--source-run", "unused", "--out", str(output)]
    if command == "resume":
        args += ["--checkpoint", "unused", "--ticks", "0"]
    assert main([*args, *flag]) == 1
    assert flag[0] in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("defect", ["duplicate", "array", "wrong_type", "extra_object"])
def test_cli_params_file_is_one_strict_object(tmp_path, capsys, defect):
    path = tmp_path / "params.json"
    params = json.dumps(PARAMS.model_dump())
    broken = {
        "duplicate": params.replace('"cue_use":', '"cue_use": "ignored", "cue_use":'),
        "array": f"[{params}]",
        "wrong_type": params.replace('"fruit_carry_target": 2', '"fruit_carry_target": 2.0'),
        "extra_object": f"{params} {params}",
    }
    path.write_text(broken[defect], encoding="utf-8")
    assert _cli_run(tmp_path / "run", "--policy", "rule-based", "--rule-params", str(path)) == 1
    assert str(path) in capsys.readouterr().err


@pytest.fixture
def rule_run(tmp_path):
    content = content_with({"ella": (2, 3)})
    source = tmp_path / "source"
    result = run(content, 4, source, rule_params=PARAMS, checkpoint_every=2)
    return content, source, result


@pytest.mark.parametrize("use_default", [False, True], ids=["short-fixture", "default-island"])
def test_rule_run_resume_and_reexecute_are_byte_identical(tmp_path, use_default, rule_run):
    content, source, _ = rule_run
    if use_default:
        content = load_world_content(DEFAULT_WORLD)
        source = tmp_path / "default"
        assert _cli_run(source, "--policy", "rule-based", "--checkpoint-every", "2", ticks=4) == 0
    checkpoint = _checkpoint(source, 2)
    save = read_checkpoint(checkpoint, content)
    final = read_checkpoint(_checkpoint(source, 4), content)
    assert any(resident.alive for resident in save.world.residents)
    assert all(r.policy_state["issued_intents"] for r in save.agent_state.runtime_states)
    restored, continuation, replay = (tmp_path / n for n in ("restored", "continued", "replayed"))
    resume(checkpoint, source, 0, restored)
    assert _checkpoint(restored, 2).read_bytes() == checkpoint.read_bytes()
    # The restored zero-length run also exercises multi-hop rule lineage.
    assert resume(_checkpoint(restored, 2), restored, 2, continuation).world == final.world
    assert _checkpoint(continuation, 4).read_bytes() == _checkpoint(source, 4).read_bytes()
    assert reexecute(source, replay).world == final.world
    for name, cursor in (
        ("events.jsonl", save.event_cursor),
        ("decisions.jsonl", save.decision_record_cursor),
    ):
        full = (source / name).read_bytes()
        prefix = b"".join(full.splitlines(keepends=True)[:cursor])
        assert prefix + (continuation / name).read_bytes() == full
        assert (replay / name).read_bytes() == full
    replay_save = read_checkpoint(_checkpoint(replay, 4), content)
    assert all(
        state.policy_config.policy_id == "recorded-v0" and state.policy_config.rule_params is None
        for state in replay_save.agent_state.runtime_states
    )
    assert (
        resume(_checkpoint(replay, 4), replay, 0, tmp_path / "recorded-restored").world
        == final.world
    )


def _assert_refused(source, path, tmp_path, message):
    output = tmp_path / "refused"
    with pytest.raises(PersistenceError, match=message):
        resume(path, source, 1, output)
    assert not output.exists()


@pytest.mark.parametrize("defect", ["null", "absent", "non-rule"])
def test_rj1_rule_params_presence(rule_run, tmp_path, defect):
    _, source, _ = rule_run
    path = _checkpoint(source, 2)
    data = _read(path)
    runtime = _runtime(data)
    config = runtime["policy_config"]
    if defect == "null":
        config["rule_params"] = None
    elif defect == "absent":
        del config["rule_params"]
    else:
        config["policy_id"] = "random-v0"
        runtime["policy_state"] = {}
    _write(path, data)
    _assert_refused(source, path, tmp_path, ": Value error, rule_params")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rule_params_version", "0.2"),
        ("extra", 1),
        ("fruit_carry_target", 0),
        ("failed_target_retry_ticks", True),
        ("cue_use", None),
    ],
)
def test_rj2_rule_params_schema(rule_run, tmp_path, field, value):
    _, source, _ = rule_run
    path = _checkpoint(source, 2)
    data = _read(path)
    params = _runtime(data)["policy_config"]["rule_params"]
    if value is None:
        del params[field]
    else:
        params[field] = value
    _write(path, data)
    _assert_refused(source, path, tmp_path, rf"\.rule_params\.{field}: ")


def test_rj3_invalid_policy_state(rule_run, tmp_path):
    _, source, _ = rule_run
    path = _checkpoint(source, 2)
    data = _read(path)
    _runtime(data)["policy_state"]["issued_intents"][0]["intent_id"] = "ella:p000000:i1"
    _write(path, data)
    _assert_refused(source, path, tmp_path, "contiguous indices")


@pytest.mark.parametrize("defect", ["missing", "wrong-tick", "world-hash", "unreadable"])
def test_rj4_root_must_be_the_verified_tick_zero_checkpoint(rule_run, tmp_path, defect):
    _, source, _ = rule_run
    path, root = _checkpoint(source, 2), _checkpoint(source, 0)
    if defect == "missing":
        root.rename(tmp_path / "root-backup.json")
    elif defect == "wrong-tick":
        root.write_bytes(path.read_bytes())
    elif defect == "world-hash":
        data = _read(root)
        data["world"]["resolution_rng_state_uint32"] += 1
        _write(root, data)
    else:
        root.write_bytes(b"{}")
    message = {
        "missing": "rule_lineage: missing root tick-zero checkpoint",
        "wrong-tick": "rule_lineage: checkpoint is not the verified tick-zero root",
        "world-hash": "rule_lineage: checkpoint is not the verified tick-zero root",
        "unreadable": "save_schema_version: unsupported version",
    }[defect]
    _assert_refused(source, path, tmp_path, message)


def _change_params(path):
    data = _read(path)
    _runtime(data)["policy_config"]["rule_params"]["cue_use"] = "ignored"
    _write(path, data)


def test_rj5_saved_policy_config_must_match_root(rule_run, tmp_path):
    _, source, _ = rule_run
    path = _checkpoint(source, 2)
    _change_params(path)
    _assert_refused(source, path, tmp_path, "differs from source run policy configuration")


def test_rj6_saved_policy_config_must_match_ancestor(rule_run, tmp_path):
    _, source, _ = rule_run
    child = tmp_path / "child"
    resume(_checkpoint(source, 2), source, 1, child)
    path = _checkpoint(child, 3)
    _change_params(path)
    _assert_refused(child, path, tmp_path, "resume-origin.json: policy_config")


def test_rj7_decision_prefix_exposes_substituted_non_rule_runtime(rule_run, tmp_path):
    _, source, _ = rule_run
    path = _checkpoint(source, 2)
    for save in (_checkpoint(source, 0), path):
        data = _read(save)
        runtime = _runtime(data)
        runtime["policy_state"] = {}
        config = runtime["policy_config"]
        config["policy_id"] = "random-v0"
        del config["rule_params"]
        _write(save, data)
    _assert_refused(source, path, tmp_path, "prefix decision for ella must use random-v0")


@pytest.mark.parametrize("field", ["seed", "max_plan_actions", "map_width", "map_height"])
def test_rj8_config_must_match_retained_inputs(rule_run, tmp_path, field):
    _, source, _ = rule_run
    path = _checkpoint(source, 2)
    data = _read(path)
    _runtime(data)["policy_config"][field] += 1
    _write(path, data)
    _assert_refused(source, path, tmp_path, rf": policy_config\.{field}: ")


def test_p1_policy_config_and_checkpoint_bytes_are_unchanged(tmp_path):
    # Baseline captured from the default four-tick random run at 8b2048e.
    assert _cli_run(tmp_path, "--policy", "random", ticks=4, config=P1_WORLD) == 0
    for tick, expected in (
        (0, "8c589cf674225e1b97fbda0a4a951ecb8a7ec66b525b467525f638f94edc6372"),
        (4, "1f1993cf6215acccde72e822dbce6bd431a4273ad038b2b54578a48816e8de9b"),
    ):
        checkpoint = _checkpoint(tmp_path, tick)
        assert sha256(checkpoint.read_bytes()).hexdigest() == expected
        policy = _runtime(_read(checkpoint))["policy_config"]
        assert "rule_params" not in policy
        assert PolicyConfig.model_validate(policy).model_dump(mode="json") == policy
