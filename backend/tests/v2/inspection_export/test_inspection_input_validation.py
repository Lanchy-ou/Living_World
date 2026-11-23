import json
import shutil
import sqlite3
from hashlib import sha256

import pytest


@pytest.mark.parametrize(
    ("slot", "keys", "replacement", "reason"),
    [
        ("0.boundary", ["tick"], 17, "boundary does not belong"),
        ("0.boundary", ["committed"], False, "finished range"),
        ("0.boundary", ["store_version"], 91, "missing store revision"),
        ("decision", ["tick"], 17, "decision does not match"),
        ("v1.revision", ["before"], 17, "broken revision chain"),
        ("v1.revision", ["edits", 0, "id"], "m:other:1", "wrong memory identity"),
        ("v1.revision", ["store_hash"], "0" * 64, "recorded store hash differs"),
        ("0.dispatch", ["request_sha256"], "0" * 64, "dispatch differs"),
        ("prepared", ["candidates", 0, "manifest", "tokens_total"], 0, "rebuilt request differs"),
        (
            "prepared",
            ["candidates", 0, "manifest", "sections", 0, "unexpected"],
            True,
            "Extra inputs",
        ),
    ],
)
def test_inspection_rejects_inconsistent_audit(capture, tmp_path, slot, keys, replacement, reason):
    from living_island.analysis.v2.export import export, fingerprint

    source, original, replay = capture
    copy = tmp_path / "run"
    shutil.copytree(source, copy)
    database = copy / "resident.sqlite"
    with sqlite3.connect(database) as db:
        name, body = db.execute(
            "SELECT name, body FROM facts WHERE name LIKE ? ORDER BY seq LIMIT 1",
            ("%." + slot + ".json",),
        ).fetchone()
        row = json.loads(body)
        target = row
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = replacement
        raw = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        db.execute(
            "UPDATE facts SET body=?, hash=? WHERE name=?", (raw, sha256(raw).hexdigest(), name)
        )
    seal = {**json.loads(original.read_bytes()), "audit_sha256": fingerprint(database)}
    manifest = tmp_path / "seal.json"
    manifest.write_text(json.dumps(seal), encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        export(copy, manifest, replay, tmp_path / "refused")


def test_inspection_rejects_foreign_packet_or_replay(capture, tmp_path):
    from living_island.analysis.v2.export import export, fingerprint

    source, original, replay = capture
    copy = tmp_path / "run"
    shutil.copytree(source, copy)
    packet = copy / "packets" / "0.json"
    batch = json.loads(packet.read_bytes())
    manifest = tmp_path / "seal.json"
    seal = json.loads(original.read_bytes())
    seal["arm"] = "on"
    for key, reason in [("batch", "packet batch outside"), ("packet", "packet identity differs")]:
        changed = json.loads(json.dumps(batch))
        if key == "batch":
            changed["run_id"] = "different"
        else:
            changed["packets"][0]["delivery_id"] += "-different"
        packet.write_text(json.dumps(changed), encoding="utf-8")
        seal["packet_sha256"][0] = fingerprint(packet)
        manifest.write_text(json.dumps(seal), encoding="utf-8")
        with pytest.raises(ValueError, match=reason):
            export(copy, manifest, replay, tmp_path / key)
    seal["run_id"] = "different"
    manifest.write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="replay does not match"):
        export(copy, manifest, replay, tmp_path / "foreign")


def test_inspection_audit_distinguishes_day_entries_from_provider_bytes(tmp_path):
    from living_island.analysis.v2.joins import Audit
    from living_island.persistence.v2.audit import AuditWriter

    database = tmp_path / "resident.sqlite"
    raw = b'{"about":"provider metadata"}'
    key = sha256(raw).hexdigest()
    AuditWriter(database).keep(key, raw)
    audit = Audit(database)
    assert audit.facts[key] == raw and not audit.entries


def test_inspection_rejects_modified_source(capture, tmp_path):
    from living_island.analysis.v2.export import export

    source, manifest, replay = capture
    changed = tmp_path / "replay.json"
    changed.write_bytes(replay.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="source hash differs"):
        export(source, manifest, changed, tmp_path / "new")


def test_inspection_rejects_unknown_source_schema(capture, tmp_path):
    from living_island.analysis.v2.export import export

    source, manifest, replay = capture
    changed = tmp_path / "manifest.json"
    changed.write_text(json.dumps({**json.loads(manifest.read_bytes()), "unknown": True}))
    with pytest.raises(ValueError, match="Extra inputs"):
        export(source, changed, replay, tmp_path / "new")


def test_inspection_rejects_unfit_index(capture, tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("living_island.analysis.v2.export")
    monkeypatch.setattr(module, "INDEX_LIMIT", 20)
    dest = tmp_path / "too-small"
    with pytest.raises(ValueError, match="index exceeds"):
        module.export(*capture, dest)
    assert not (dest / "index.json").exists()


def test_inspection_rejects_dangling_flagged_revision(formation, tmp_path):
    from living_island.analysis.v2.export import export, fingerprint

    (source, manifest, replay), _, _, _ = formation
    path = source / "resident.sqlite"
    with sqlite3.connect(path) as db:
        key, raw = db.execute(
            "SELECT name,body FROM facts WHERE name LIKE '%.consolidation.json'"
        ).fetchone()
        row = json.loads(raw)
        row["relabel_flags"][0]["flagged"]["content_hash"] = "0" * 64
        raw = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        db.execute(
            "UPDATE facts SET body=?, hash=? WHERE name=?", (raw, sha256(raw).hexdigest(), key)
        )
    seal = json.loads(manifest.read_bytes())
    seal["audit_sha256"] = fingerprint(path)
    manifest.write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="absent memory revision"):
        export(source, manifest, replay, tmp_path / "invalid")


def test_inspection_missing_hypothesis_is_unknown(formation, tmp_path):
    from living_island.analysis.v2.export import export, fingerprint
    from living_island.analysis.v2.shards import read_shard

    (source, manifest, replay), _, _, _ = formation
    path = source / "resident.sqlite"
    with sqlite3.connect(path) as db:
        for key, raw in db.execute(
            "SELECT name,body FROM facts WHERE name LIKE '%.period_members.json'"
        ):
            receipt = json.loads(raw)
            skill = next((w["skill"] for w in receipt["writes"] if w["skill"]), None)
            if skill:
                skill["hypothesis"]["content_hash"] = "0" * 64
                changed = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
                db.execute(
                    "UPDATE facts SET body=?, hash=? WHERE name=?",
                    (changed, sha256(changed).hexdigest(), key),
                )
                break
    seal = json.loads(manifest.read_bytes())
    manifest.write_text(json.dumps({**seal, "audit_sha256": fingerprint(path)}))
    directory = tmp_path / "missing"
    index = export(source, manifest, replay, directory)
    (row,) = (
        r for r in read_shard(directory, index.metrics).instances if r.metric == "hypothesis_source"
    )
    assert row.value is None and row.reason == "missing hypothesis revision"
