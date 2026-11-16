"""P3 inspection schema, lineage and offline export integration tests."""

from __future__ import annotations

import json
from hashlib import sha256

import pytest
from test_extension_ports import ROOT, _three_actor_case, fixture_provider, fixture_selector

from living_island.contract.p3_inspection import (
    DecisionInspection,
    P3InspectionIndex,
    ResidentInspection,
    canonical_bytes,
)
from living_island.persistence.p3_inspection import export_inspection, verify_inspection_source
from living_island.sim.p3 import export_p3_replay, run_p3


@pytest.fixture(scope="module")
def inspected(tmp_path_factory):
    root = tmp_path_factory.mktemp("inspection")
    content, files, case, store, reader, fallback = _three_actor_case(root, fixture=True, horizon=2)
    source = root / "source"
    run_p3(
        content,
        files,
        case,
        source,
        allocation_store=store,
        provider=fixture_provider("recent-only", 1, horizon=2),
        fallback=fallback,
        source_reader=reader,
        selector=fixture_selector(),
        selector_sha256=fixture_selector().implementation_sha256,
    )
    replay = root / "replay.json"
    export_p3_replay(source, replay, source_reader=reader)
    verified = verify_inspection_source(source, replay, repository=ROOT, source_reader=reader)
    return root, source, replay, reader, verified


def test_export_exact_deterministic_shards_and_complete_samples(inspected):
    root, source, replay, reader, verified = inspected
    before = {
        p.relative_to(source): sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*")
        if p.is_file()
    }
    first, second = root / "export-a", root / "export-b"
    index = export_inspection(verified, first)
    assert export_inspection(verified, second) == index
    assert len(index.samples) == 9
    assert len(index.decisions) == len(verified.decisions)
    assert (first / "trace.json").read_bytes() == (source / "decision-trace-p3.json").read_bytes()
    assert index.replay_sha256 == sha256(replay.read_bytes()).hexdigest()
    for file in first.iterdir():
        assert file.read_bytes() == (second / file.name).read_bytes()
        if file.name != "trace.json":
            assert not file.read_bytes().endswith(b"\n")
    for ref in index.decisions:
        raw = (first / ref.shard.file).read_bytes()
        assert sha256(raw).hexdigest() == ref.shard.sha256
        shard = DecisionInspection.model_validate_json(raw)
        assert shard.context.assembly.manifest.retrieval_profile == "recent-only-fixture-v0"
    for ref in index.samples:
        sample = ResidentInspection.model_validate_json((first / ref.shard.file).read_bytes())
        assert sample.latest_perception_tick < sample.tick
        if ref.tick == 0:
            assert sample.latest_decision_id is None
            assert sample.recent_experience == []
        else:
            assert len(sample.recent_experience) == min(8, sample.retained_record_count)
    assert before == {
        p.relative_to(source): sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*")
        if p.is_file()
    }
    with pytest.raises(ValueError, match="fresh"):
        export_inspection(verified, first)


@pytest.mark.parametrize(
    "mutation", ["version", "missing", "duplicate", "foreign", "filename", "ordinal"]
)
def test_index_refuses_corrupt_membership(inspected, mutation):
    root, _, _, _, verified = inspected
    index = export_inspection(verified, root / f"mutation-{mutation}").model_dump(mode="json")
    if mutation == "version":
        index["inspection_schema_version"] = "9"
    elif mutation == "missing":
        index["samples"].pop()
    elif mutation == "duplicate":
        index["samples"].append(index["samples"][0])
    elif mutation == "foreign":
        index["decisions"][0]["actor_id"] = "other"
    elif mutation == "filename":
        index["samples"][0]["shard"]["file"] = "../bad.json"
    else:
        index["decisions"][0]["ordinal"] = True
    with pytest.raises(ValueError):
        P3InspectionIndex.model_validate(index)


def test_unrelated_replay_refuses(inspected):
    root, source, replay, reader, _ = inspected
    data = json.loads(replay.read_bytes())
    data["config_hash"] = "f" * 64
    wrong = root / "wrong-replay.json"
    wrong.write_bytes(canonical_bytes(data))
    with pytest.raises(ValueError, match="config_hash|run/config/map"):
        verify_inspection_source(source, wrong, repository=ROOT, source_reader=reader)


def test_exact_shard_limit(monkeypatch, inspected):
    import living_island.persistence.p3_inspection as exporter

    shard = inspected[-1].decisions[0]
    size = len(canonical_bytes(shard))
    monkeypatch.setattr(exporter, "SHARD_LIMIT", size)
    assert len(exporter.checked_shard_bytes(shard)) == size
    monkeypatch.setattr(exporter, "SHARD_LIMIT", size - 1)
    with pytest.raises(ValueError, match="V-06"):
        exporter.checked_shard_bytes(shard)
