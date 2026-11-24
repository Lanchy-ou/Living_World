"""Pair a short fake recording with a separately pinned display fixture."""

import json
from pathlib import Path


def seal_capture(work, source, recording, kwargs, arm):
    from living_island.analysis.v2.export import FinishedRun, fingerprint
    from living_island.contract import inspection_v2 as ia

    tick = recording.session.world.tick
    replay = work / "replay.json"
    fixture = Path(__file__).resolve().parents[2] / "fixtures/replay/mechanics.replay.json"
    display = json.loads(fixture.read_bytes())
    display["frames"] = display["frames"][: tick + 1]
    display["events"] = [e for e in display["events"] if e["tick"] <= tick]
    replay.write_text(json.dumps(display), encoding="utf-8")
    pack = kwargs["compat"].pack
    seal = FinishedRun(
        status="finished",
        run_id=recording.session.world.run_id,
        arm=arm,
        pack_ids=[ia.PackPin(pack_id=pack.pack_id, sha256=pack.pack_hash)],
        residents=[
            ia.Resident(resident_id=actor, profile_id=row.profile_id)
            for actor, row in kwargs["profiles"].items()
        ],
        replay_sha256=fingerprint(replay),
        final_tick=tick,
        audit_sha256=fingerprint(source / "resident.sqlite"),
        packet_sha256=[
            fingerprint(source / "packets" / f"{n}.json")
            for n in range(len(list((source / "packets").glob("*.json"))))
        ],
        content_checks_sha256=None,
    )
    manifest = work / "manifest.json"
    manifest.write_text(seal.model_dump_json(), encoding="utf-8")
    return source, manifest, replay
