"""Verify the M2 demo's full replay and its continuation prefix/suffix."""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path

from living_island.world.content import canonical_json_bytes


def main(original: Path, continuation: Path, replay: Path) -> None:
    manifest = json.loads((original / "decision-trace.json").read_bytes())
    origin = json.loads((continuation / "resume-origin.json").read_bytes())
    for name, cursor in (("events", "event_cursor"), ("decisions", "decision_record_cursor")):
        raw = (original / f"{name}.jsonl").read_bytes()
        prefix = b"".join(raw.splitlines(keepends=True)[: origin[cursor]])
        tail = (continuation / f"{name}.jsonl").read_bytes()
        assert raw == prefix + tail == (replay / f"{name}.jsonl").read_bytes()
        if name == "decisions":
            assert all(json.loads(line)["status"] == "ok" for line in raw.splitlines())
        digest = sha256(raw).hexdigest()
        assert digest == manifest[f"{name}_sha256"]
        print(f"{name}: {raw.count(bytes([10]))} records sha256={digest}; both comparisons match")
    checkpoint = f"checkpoint-{manifest['final_tick']:010d}.json"
    worlds = [
        canonical_json_bytes(json.loads((run / checkpoint).read_bytes())["world"])
        for run in (original, continuation, replay)
    ]
    assert worlds[0] == worlds[1] == worlds[2]
    digest = sha256(worlds[0]).hexdigest()
    assert digest == manifest["final_world_sha256"]
    print(f"final world: tick={manifest['final_tick']} sha256={digest}; all three match")


if __name__ == "__main__":
    main(*(Path(arg) for arg in sys.argv[1:]))
