import json
from hashlib import sha256

import pytest


def test_inspection_reader_refuses_misaddressed_or_invalid_artifacts(
    capture, tmp_path, monkeypatch
):
    from living_island.analysis.v2 import shards
    from living_island.analysis.v2.export import export
    from living_island.contract.inspection_v2 import FilePart, RevisionRef

    directory = tmp_path / "read"
    index = export(*capture, directory)
    archive = shards.InspectionArchive.open(directory)
    assert archive.revision("absent", RevisionRef("m:absent:1", 7, "0" * 64)) is None
    metrics = index.metrics
    part = metrics.parts[0]
    with pytest.raises(ValueError, match="numbered part filename"):
        archive.read(metrics.model_copy(update={"id": "different"}))
    with pytest.raises(ValueError, match="size mismatch"):
        archive.read(metrics.model_copy(update={"parts": [part.model_copy(update={"size": 1})]}))
    with pytest.raises(ValueError, match="assembled hash mismatch"):
        archive.read(metrics.model_copy(update={"sha256": "0" * 64}))
    path = directory / part.name
    for body, reason in [
        (shards.encoded({"family": "cost", "attempts": []}), "wrong shard family"),
        (shards.encoded({"family": "metrics", "extra": True}), "Extra inputs"),
    ]:
        path.write_bytes(body)
        digest = sha256(body).hexdigest()
        ref = metrics.model_copy(
            update={
                "sha256": digest,
                "parts": [FilePart(name=part.name, size=len(body), sha256=digest)],
            }
        )
        with pytest.raises(ValueError, match=reason):
            archive.read(ref)
    index_path = directory / "index.json"
    index_path.write_bytes(index_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="canonical inspection index"):
        shards.read_index(directory)
    monkeypatch.setattr(shards, "INDEX_LIMIT", 3)
    with pytest.raises(ValueError, match="exceeds 32 MiB"):
        shards.read_index(directory)


def test_ev01_fresh_deterministic_complete_export(capture, tmp_path, monkeypatch):
    from living_island.analysis.v2 import shards
    from living_island.analysis.v2.export import export, fingerprint

    source, manifest, replay = capture
    originals = {p: fingerprint(p) for p in source.rglob("*") if p.is_file()}
    # Force multipart files in a short routine run. The logical records are unchanged.
    monkeypatch.setattr(shards, "SHARD_LIMIT", 4096)
    first = tmp_path / "first"
    second = tmp_path / "second"
    index = export(*capture, first)
    assert index == export(*capture, second)
    assert {f.name: fingerprint(f) for f in first.iterdir()} == {
        f.name: fingerprint(f) for f in second.iterdir()
    }
    assert all(fingerprint(p) == digest for p, digest in originals.items())
    assert index.inspection_schema_version == "ia/0.1"
    assert index.final_tick == 1 and len(index.deliveries) == 3
    assert index.replay_sha256 == fingerprint(replay)
    assert index.manifest_sha256 == fingerprint(manifest)
    assert shards.read_index(first) == index
    refs = [
        *[v.shard for v in (*index.decisions, *index.stores, *index.calls)],
        *index.deliveries,
        *index.revisions,
        *index.evidence_writes,
        index.cost,
        index.attempts,
        index.metrics,
        index.time_use,
    ]
    assert any(len(ref.parts) > 1 for ref in refs)
    for ref in refs:
        assert all(p.size <= 4096 for p in ref.parts)
        assert shards.read_shard(first, ref).family == ref.family
    with pytest.raises(ValueError, match="fresh destination"):
        export(*capture, first)
    part = first / index.metrics.parts[0].name
    raw = part.read_bytes()
    part.write_bytes(b"!" + raw[1:])
    with pytest.raises(ValueError, match="hash mismatch"):
        shards.read_shard(first, index.metrics)


def test_dl29_immutable_call_parts_and_use(capture, tmp_path):
    from living_island.analysis.v2.export import export
    from living_island.analysis.v2.shards import read_shard

    dest = tmp_path / "with-calls"
    index = export(*capture, dest)
    decision = read_shard(dest, index.decisions[0].shard)
    assert [c.call_kind for c in decision.calls] == ["decision", "recall", "decision_after_recall"]
    for c in decision.calls:
        by_hash = {part.sha256: part.text for part in c.parts}
        assert c.prepared.candidates[c.prepared.floor_candidate]
        for request, candidate in zip(c.requests, c.prepared.candidates, strict=True):
            ordered = [by_hash[entry.sha256] for entry in candidate.manifest.entries]
            wire = json.loads(request.text)
            assert wire["input"][1]["content"] == "\n".join(ordered[1:-1])
            assert wire["text"]["format"]["schema"] == json.loads(ordered[-1])
        assert (
            c.attempts[0].dispatch.request_sha256
            == c.requests[c.prepared.admitted_candidate].sha256
        )
        assert c.full_manifest == c.prepared.candidates[0].manifest
        assert c.sent_manifest == c.attempts[0].dispatch.sent.manifest
    assert decision.record.origin == "model"
    assert decision.record.use_updates
    assert decision.outcome_event_ids
    assert all(a.missing_usage_reason for a in read_shard(dest, index.cost).attempts)
