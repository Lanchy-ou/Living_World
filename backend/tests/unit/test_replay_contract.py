"""Replay contract (A2): models, cross-field validators and the shared fixtures (P1-01b).

The fixtures live in ``tests/fixtures/replay`` and are shared with P1-07 and P1-08.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from living_island.contract import replay
from living_island.contract.replay import ReplayBundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "backend" / "tests" / "fixtures" / "replay"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load("replay_fixture_build", FIXTURES / "build.py")


def canonical_bytes(bundle: ReplayBundle) -> bytes:
    doc = bundle.model_dump(mode="json", by_alias=True)
    return build.canonical(doc)


# ------------------------------------------------------------------ valid bundle


def test_valid_fixture_is_accepted() -> None:
    bundle = ReplayBundle.model_validate_json((FIXTURES / "valid.json").read_bytes())
    assert len(bundle.frames) == 4
    assert bundle.replay_schema_version == "0.1"
    assert [f.tick for f in bundle.frames] == [0, 1, 2, 3]


def test_valid_fixture_round_trips_through_canonical_json_byte_identically() -> None:
    raw = (FIXTURES / "valid.json").read_bytes()
    bundle = ReplayBundle.model_validate_json(raw)
    assert canonical_bytes(bundle) == raw
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert b"\r" not in raw


def test_committed_fixtures_match_the_builder() -> None:
    expected = build.build_all()
    for path, data in expected.items():
        assert path.read_bytes() == data, f"{path.name} drifted: run build.py"
    on_disk = {p for p in (FIXTURES / "invalid").glob("*.json")}
    assert on_disk == {p for p in expected if p.parent.name == "invalid"}


def test_dead_residents_stay_in_every_frame() -> None:
    raw = json.loads((FIXTURES / "valid.json").read_bytes())
    assert all(len(f["residents"]) == 3 for f in raw["frames"])
    assert raw["frames"][3]["residents"][1]["alive"] is False


def test_bundle_with_only_frame_zero_is_valid() -> None:
    doc = build.build_valid()
    doc["frames"] = doc["frames"][:1]
    doc["events"] = doc["events"][:1]
    assert len(ReplayBundle.model_validate(doc).frames) == 1


def test_all_residents_dead_is_valid() -> None:
    doc = build.build_valid()
    for f in doc["frames"]:
        for r in f["residents"]:
            r["alive"], r["health"] = False, 0
    ReplayBundle.model_validate(doc)


def test_event_free_tick_still_has_a_frame() -> None:
    doc = build.build_valid()
    doc["events"] = [e for e in doc["events"] if e["tick"] != 1]
    for e in doc["events"]:
        e["caused_by_event_ids"] = [c for c in e["caused_by_event_ids"] if ":0000000001:" not in c]
    for tick, (first, count) in {1: (1, 0), 2: (1, 4), 3: (5, 4)}.items():
        doc["frames"][tick]["event_range"] = {"first_index": first, "count": count}
    ReplayBundle.model_validate(doc)


# ---------------------------------------------------------------- invalid bundles


@pytest.mark.parametrize("name", sorted(build.INVALID))
def test_invalid_fixture_is_rejected_for_its_intended_reason(name: str) -> None:
    expected_error = build.INVALID[name][0]
    raw = (FIXTURES / "invalid" / f"{name}.json").read_bytes()
    with pytest.raises(ValidationError) as caught:
        ReplayBundle.model_validate_json(raw)
    assert expected_error in str(caught.value), str(caught.value)


def test_every_cross_field_rule_group_has_a_fixture() -> None:
    groups = {name.split("__")[0] for name in build.INVALID}
    assert groups >= {
        "frame_ticks",
        "event_range",
        "event_order",
        "event_seq",
        "run_id",
        "event_id",
        "causal_refs",
        "utterance_refs",
        "entity_refs",
        "namespaces",
        "map",
        "legend",
        "residents",
        "frame_residents",
        "frame_sort",
        "trees",
        "ground_fruit",
        "coords",
        "condition_bounds",
        "conditions",
        "clock",
        "schema",
    }


def test_wrapper_shaped_input_is_refused() -> None:
    doc = {"ReplayBundle": build.build_valid()}
    with pytest.raises(ValidationError):
        ReplayBundle.model_validate(doc)


def test_replay_models_reject_unknown_fields_and_are_strict() -> None:
    models = [
        obj
        for obj in vars(replay).values()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == replay.__name__
    ]
    assert len(models) == 14
    for model in models:
        assert model.model_config.get("extra") == "forbid", model.__name__
        assert model.model_config.get("strict") is True, model.__name__


def test_float_and_bool_are_not_integers() -> None:
    for bad in (1.0, True):
        doc = build.build_valid()
        doc["frames"][1]["residents"][0]["satiety"] = bad
        with pytest.raises(ValidationError):
            ReplayBundle.model_validate_json(json.dumps(doc))


def test_map_hash_is_rows_joined_with_lf_plus_final_lf() -> None:
    import hashlib

    rows = build.ROWS
    assert replay.map_hash_of(rows) == hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()


# ---------------------------------------------------------------- generation


def _load_gen_types() -> Any:
    return _load("gen_types_under_test", REPO_ROOT / "scripts" / "gen_types.py")


def test_replay_schema_is_2020_12_rooted_at_replay_bundle() -> None:
    schema = _load_gen_types().build_replay_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "ReplayBundle"
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert "WorldEvent" in schema["$defs"] and "DisplayFrame" in schema["$defs"]
    assert schema["properties"]["replay_schema_version"] == {
        "const": "0.1",
        "title": "Replay Schema Version",
        "type": "string",
    }


def test_committed_replay_schema_matches_the_models() -> None:
    gen = _load_gen_types()
    committed = REPO_ROOT / "frontend" / "src" / "api" / "generated" / "replay.schema.json"
    assert committed.read_text(encoding="utf-8") == gen.render_schema(gen.build_replay_schema())


def test_replay_module_has_no_sim_or_world_state_dependency() -> None:
    code = (
        "import sys, living_island.contract.replay;"
        "bad=[m for m in sys.modules if m.startswith(('living_island.sim',"
        "'living_island.persistence','living_island.world.state','living_island.agents'))];"
        "print(bad)"
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"
