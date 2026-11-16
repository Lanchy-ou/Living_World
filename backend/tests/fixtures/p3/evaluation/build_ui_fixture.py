"""Build the small inspection UI fixture from a committed closed offline tape."""

from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import sys
import tarfile
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
for path in (ROOT, ROOT / "backend/tests/p3", ROOT / "backend/tests/unit"):
    sys.path.insert(0, str(path))

from scripts.p3_trials import FakeStep, FakeTape, TapeProvider  # noqa: E402
from test_extension_ports import committed_head, committed_source, pinned_inputs  # noqa: E402
from test_reexecution import LocalFallback  # noqa: E402
from world_builders import tiny_content  # noqa: E402

from living_island.agents.p3.types import ProviderResult, WireRequest  # noqa: E402
from living_island.contract.p3_save import ActorPolicyConfig, TrialRegistration  # noqa: E402
from living_island.memory.p3_types import canonical_bytes, canonical_sha256  # noqa: E402
from living_island.persistence.p3_allocation import AllocationStore, initialize_fake  # noqa: E402
from living_island.persistence.p3_inspection import (  # noqa: E402
    export_inspection,
    verify_inspection_source,
)
from living_island.sim.p3 import export_p3_replay, run_p3  # noqa: E402
from living_island.world.content import build_world_content, map_bytes_from_rows  # noqa: E402

SELF = "backend/tests/fixtures/p3/evaluation/build_ui_fixture.py"
TAPE = "backend/tests/fixtures/p3/evaluation/ui-tape.json.gz"
FIXTURES = ROOT / "backend/tests/fixtures/p3/evaluation"


class Builder:
    def __init__(self):
        self.steps = []

    def prepare(self, request):
        return WireRequest(
            wire_schema_version="0.1",
            method="POST",
            origin="https://api.deepseek.com",
            path="/responses",
            content_type="application/json",
            body_base64=base64.b64encode(canonical_bytes(request)).decode(),
        )

    def count_input_tokens(self, request, wire):
        assert self.prepare(request) == wire
        return 100

    def complete(self, request, wire, timeout_ms):
        user = json.loads(request.messages[1].content)
        actor, ordinal = user["request"]["actor_id"], user["request"]["decision_ordinal"]
        current = user["context"]["goals"]["current"]
        change = {
            "operation": "continue",
            "expected_goal_id": None if current is None else current["goal_id"],
            "proposal": None,
        }
        action = {"action_type": "wait", "target": None, "parameters": {}, "reason": None}
        if actor == "ella":
            if ordinal == 0:
                change.update(
                    operation="revise",
                    proposal={
                        "text": "Wait for one observed result",
                        "completion": {
                            "kind": "own_action_success",
                            "action_type": "wait",
                            "target": None,
                            "parameters": {},
                        },
                    },
                )
            elif ordinal == 1:
                change.update(
                    operation="revise",
                    proposal={
                        "text": "Consider the heard request",
                        "completion": {"kind": "unverifiable"},
                    },
                )
            elif ordinal == 2:
                change.update(operation="abandon")
        if actor == "mia" and ordinal == 0:
            action = {
                "action_type": "talk",
                "target": {"kind": "resident", "id": "ella"},
                "parameters": {
                    "speech_act": "statement",
                    "text": "<img src=x onerror=alert('fixture')> & quoted speech",
                },
                "reason": None,
            }
        if actor == "ryan":
            action = {"action_type": "sleep", "target": None, "parameters": {}, "reason": None}
        raw = canonical_bytes(
            {
                "proposal_schema_version": "0.1",
                "actions": [action],
                "cognitive_delta": {"delta_schema_version": "0.1", "goal_change": change},
            }
        )
        unknown = actor == "mia" and ordinal == 0
        result = ProviderResult(
            provider_result_version="0.1",
            outcome="response",
            raw_response=raw.decode(),
            raw_body_base64=base64.b64encode(raw).decode(),
            observed_body_bytes=len(raw),
            response_complete=True,
            response_text=raw.decode(),
            provider_request_id=None,
            token_input=None if unknown else 100,
            token_output=20,
            latency_ms=None if unknown else 1,
            provider_error_code=None,
        )
        self.steps.append(
            FakeStep(
                actor_id=actor,
                decision_ordinal=ordinal,
                attempt_index=0,
                expected_request=request,
                expected_wire=wire,
                expected_input_tokens=100,
                result=result,
            )
        )
        return result


def source_inputs(include_tape, *, edge=False):
    content = tiny_content(
        [
            "~~~~~~~~~~~",
            "~.SC......~",
            "~.MF......~",
            "~.........~",
            "~.........~",
            "~.........~",
            "~~~~~~~~~~~",
        ],
        {"ella": (2, 3), "mia": (3, 3), "ryan": (8, 4)},
        day_radius_tiles=10,
    )
    if edge:
        effective = content.config.model_dump(mode="json")
        effective["needs"].update(initial_satiety=0, initial_hydration=0, initial_health=1)
        content = build_world_content(effective, map_bytes_from_rows(content.map_rows))
    files, reader = pinned_inputs(content, fixture=False)
    registration = json.loads(files["trial-registration.json"])
    name = "p307-ui-edge" if edge else "p307-ui"
    registration["registration_id"] = name
    registration["fake_fixture_id"] = name
    case = registration["cases"][0]
    case["case_id"] = f"{name}.s{case['seed']}"
    case["ticks"] = 4
    if edge:
        case["caps"] = dict.fromkeys(("attempts", "input_tokens", "output_tokens", "micro_cny"), 0)
        registration["aggregate_caps"] = case["caps"]
    commit = committed_head()
    pins = {p["path"]: p for p in registration["input_pins"]}
    for path in [SELF, *([TAPE] if include_tape else [])]:
        raw = committed_source(commit, path)
        if raw != (ROOT / path).read_bytes():
            raise ValueError("UI helper/tape must be committed")
        pins[path] = {"path": path, "sha256": sha256(raw).hexdigest()}
    registration["input_pins"] = [pins[p] for p in sorted(pins)]
    for item in case["policy_templates"]:
        item["config"]["adapter_id"] = "p307-ui-closed-tape"
    typed = TrialRegistration.model_validate(registration)
    files["trial-registration.json"] = canonical_bytes(typed)
    policies = [
        {
            "actor_id": t["actor_id"],
            "config": {**t["config"], "trial_registration_sha256": canonical_sha256(typed)},
        }
        for t in case["policy_templates"]
    ]
    files["p3-policy-configs.json"] = canonical_bytes(policies)
    implementation = json.loads(files["implementation.json"])
    for module in implementation["modules"]:
        if module["role"] in ("adapter", "counter"):
            module["files"] = [
                pins[SELF],
                {
                    "path": "scripts/p3_trials.py",
                    "sha256": sha256(reader(commit, "scripts/p3_trials.py")).hexdigest(),
                },
            ]
            module["files"].sort(key=lambda p: p["path"])
    files["implementation.json"] = canonical_bytes(implementation)
    fallback = LocalFallback(
        {p["actor_id"]: ActorPolicyConfig.model_validate(p).config for p in policies}
    )
    return content, files, typed, reader, fallback


def main():
    global TAPE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["generate-tape", "publish"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--edge", action="store_true")
    args = parser.parse_args()
    name = "ui-edge" if args.edge else "ui"
    if args.edge:
        TAPE = "backend/tests/fixtures/p3/evaluation/ui-edge-tape.json.gz"
    if args.out.exists():
        raise ValueError("fresh fixture source output required")
    include_tape = args.mode == "publish"
    if not include_tape and (ROOT / TAPE).exists():
        raise ValueError("closed UI tape already exists")
    content, files, registration, reader, fallback = source_inputs(include_tape, edge=args.edge)
    provider = (
        TapeProvider(FakeTape.model_validate_json(gzip.decompress((ROOT / TAPE).read_bytes())))
        if include_tape
        else Builder()
    )
    args.out.mkdir(parents=True)
    authority = args.out / "isolated-fake-authority"
    initialize_fake(authority)
    store = AllocationStore(authority, mode="fake")
    case = registration.cases[0]
    store.enroll_fake(canonical_sha256(registration), case.case_id, case.caps)
    source = args.out / "source"
    run_p3(
        content,
        files,
        case.case_id,
        source,
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
    )
    if not include_tape:
        tape = FakeTape(
            fake_schema_version="0.1", fixture_id=registration.fake_fixture_id, steps=provider.steps
        )
        with (ROOT / TAPE).open("xb") as stream:
            stream.write(gzip.compress(canonical_bytes(tape), mtime=0))
        print(
            json.dumps(
                {"steps": len(tape.steps), "sha256": sha256((ROOT / TAPE).read_bytes()).hexdigest()}
            )
        )
        return 0
    provider.assert_consumed()
    replay = source / "replay.json"
    export_p3_replay(source, replay, source_reader=reader)
    verified = verify_inspection_source(source, replay, repository=ROOT, source_reader=reader)
    destination = FIXTURES / name
    index = export_inspection(verified, destination)
    (destination / "replay.json").write_bytes(replay.read_bytes())
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for path in sorted(source.iterdir()):
            raw = path.read_bytes()
            info = tarfile.TarInfo(path.name)
            info.size = len(raw)
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(raw))
    compressed = gzip.compress(archive.getvalue(), mtime=0)
    (FIXTURES / f"{name}-source.tar.gz").write_bytes(compressed)
    manifest = {
        "fixture_id": registration.fake_fixture_id,
        "implementation_commit": registration.implementation_commit,
        "index_sha256": canonical_sha256(index),
        "source_archive_sha256": sha256(compressed).hexdigest(),
        "registration_sha256": canonical_sha256(registration),
        "tape_sha256": sha256((ROOT / TAPE).read_bytes()).hexdigest(),
        "replay": f"{name}/replay.json",
        "inspection_files": [
            f"{name}/{p.name}" for p in sorted(destination.iterdir()) if p.name != "replay.json"
        ],
        "files": {
            f"{name}/{p.name}": sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.iterdir())
        },
        "features": [
            "three actors",
            "same-boundary completion/revise",
            "abandon",
            "nondecision boundary",
            "unknown usage",
            "HTML-looking speech",
        ],
        "live_provider_calls": 0,
        "live_authority_accesses": 0,
    }
    if args.edge:
        manifest["features"] = ["death", "stale cognitive cursor", "zero-call budget fallback"]
    (FIXTURES / f"{name}-manifest.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps(manifest), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
