"""Explicit offline V-04 tape creation and committed-tape proof (outside default CI).

Generate once from the approved pure request/response DTO builders. A changed tape
requires explanation/review; this script never overwrites an existing tape/output.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from scripts.p3_experiments import recorded_proof  # noqa: E402
from scripts.p3_trials import (  # noqa: E402
    FakeStep,
    FakeTape,
    TapeProvider,
    build_case_inputs,
    build_registration,
    git,
)

from living_island.agents.llm.fallback import FrozenRuleFallbackAdapter  # noqa: E402
from living_island.agents.p3.types import ProviderResult, WireRequest  # noqa: E402
from living_island.contract.p3_save import InputPin, TrialRegistration  # noqa: E402
from living_island.memory.p3_types import canonical_bytes, canonical_sha256  # noqa: E402
from living_island.persistence.p3_allocation import AllocationStore, initialize_fake  # noqa: E402
from living_island.persistence.p3_inspection import (  # noqa: E402
    GitSourceReader,
    export_inspection,
    verify_inspection_source,
)
from living_island.sim.p3 import export_p3_replay, run_p3  # noqa: E402

SELF = "backend/tests/fixtures/p3/evaluation/build_fixture.py"
TAPE = "backend/tests/fixtures/p3/evaluation/v04-tape.json.gz"
CAPS = {"attempts": 6048, "input_tokens": 198180864, "output_tokens": 12386304, "micro_cny": 0}


class TapeBuilder:
    """Pure scripted adapter: records exact builder inputs; never uses transport."""

    def __init__(self):
        self.steps = []
        self.ordinals = {}
        self.attempt = {}

    def prepare(self, request):
        return WireRequest(
            wire_schema_version="0.1",
            method="POST",
            origin="https://api.deepseek.com",
            path="/responses",
            content_type="application/json",
            body_base64=base64.b64encode(canonical_bytes(request)).decode("ascii"),
        )

    def count_input_tokens(self, request, wire):
        if wire != self.prepare(request):
            raise ValueError("fake counter must count its exact prepared wire")
        return 100

    def complete(self, request, wire, timeout_ms):
        data = json.loads(request.messages[1].content)
        actor = data["request"]["actor_id"]
        ordinal = data["request"]["decision_ordinal"]
        attempt = self.attempt.get((actor, ordinal), 0)
        self.attempt[(actor, ordinal)] = attempt + 1
        if actor == "ella" and ordinal == 1:
            result = ProviderResult(
                provider_result_version="0.1",
                outcome="timeout",
                raw_response=None,
                raw_body_base64=None,
                observed_body_bytes=0,
                response_complete=False,
                response_text=None,
                provider_request_id=None,
                token_input=None,
                token_output=None,
                latency_ms=30000,
                provider_error_code=None,
            )
        else:
            current = data["context"]["goals"]["current"]
            proposal = {
                "proposal_schema_version": "0.1",
                "actions": [
                    {"action_type": "wait", "target": None, "parameters": {}, "reason": None}
                ],
                "cognitive_delta": {
                    "delta_schema_version": "0.1",
                    "goal_change": {
                        "operation": "continue",
                        "expected_goal_id": None if current is None else current["goal_id"],
                        "proposal": None,
                    },
                },
            }
            raw = canonical_bytes(proposal)
            result = ProviderResult(
                provider_result_version="0.1",
                outcome="response",
                raw_response=raw.decode(),
                raw_body_base64=base64.b64encode(raw).decode(),
                observed_body_bytes=len(raw),
                response_complete=True,
                response_text=raw.decode(),
                provider_request_id=None,
                token_input=100,
                token_output=20,
                latency_ms=1,
                provider_error_code=None,
            )
        self.steps.append(
            FakeStep(
                actor_id=actor,
                decision_ordinal=ordinal,
                attempt_index=attempt,
                expected_request=request,
                expected_wire=wire,
                expected_input_tokens=100,
                result=result,
            )
        )
        return result


def inputs(*, include_tape: bool):
    commit = git(ROOT, "rev-parse", "HEAD").decode().strip()
    reader = GitSourceReader(ROOT)
    base = build_registration(ROOT, commit, purpose="fake", registration_id="p3-v04-offline-r1")
    value = base.model_dump(mode="json")
    case = value["cases"][0]
    case["ticks"] = 1008
    case["caps"] = CAPS
    case["llm_actor_ids"] = [item["actor_id"] for item in case["policy_templates"]]
    for item in case["policy_templates"]:
        item["config"]["policy_id"] = "llm-v0"
    value["aggregate_caps"] = CAPS
    value["fake_fixture_id"] = "v04"
    pins = {p["path"]: p for p in value["input_pins"]}
    for path in [SELF, *([TAPE] if include_tape else [])]:
        source = reader(commit, path)
        if source != (ROOT / path).read_bytes():
            raise ValueError("fixture helper/tape must be committed before execution")
        pins[path] = InputPin(path=path, sha256=sha256(source).hexdigest()).model_dump()
    value["input_pins"] = [pins[p] for p in sorted(pins)]
    registration = TrialRegistration.model_validate(value)
    content, files = build_case_inputs(ROOT, registration, registration.cases[0].case_id)
    implementation = json.loads(files["implementation.json"])
    for module in implementation["modules"]:
        if module["role"] in ("adapter", "counter"):
            module["files"].append(pins[SELF])
            module["files"].sort(key=lambda p: p["path"])
    files["implementation.json"] = canonical_bytes(implementation)
    return content, files, registration, reader


def run(output, *, provider, include_tape):
    content, files, registration, reader = inputs(include_tape=include_tape)
    output.mkdir(parents=True, exist_ok=False)
    authority = output / "isolated-fake-authority"
    initialize_fake(authority)
    store = AllocationStore(authority, mode="fake")
    case = registration.cases[0]
    store.enroll_fake(canonical_sha256(registration), case.case_id, case.caps)
    config = json.loads(files["p3-policy-configs.json"])[0]["config"]["fallback_config"]
    from living_island.agents.types import PolicyConfig

    fallback = FrozenRuleFallbackAdapter(PolicyConfig.model_validate(config))
    result = run_p3(
        content,
        files,
        case.case_id,
        output / "source",
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
    )
    return result, registration, reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["generate-tape", "prove"])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    tape_path = ROOT / TAPE
    if args.mode == "generate-tape":
        if tape_path.exists():
            raise ValueError(
                "the frozen tape already exists; regeneration requires reviewed explanation"
            )
        provider = TapeBuilder()
        result, registration, _ = run(args.out, provider=provider, include_tape=False)
        tape = FakeTape(fake_schema_version="0.1", fixture_id="v04", steps=provider.steps)
        with tape_path.open("xb") as stream:
            stream.write(gzip.compress(canonical_bytes(tape), mtime=0))
        provenance = {
            "fixture_id": "v04",
            "implementation_commit": registration.implementation_commit,
            "generator_sha256": sha256((ROOT / SELF).read_bytes()).hexdigest(),
            "tape_sha256": sha256(tape_path.read_bytes()).hexdigest(),
            "steps": len(tape.steps),
            "horizon": 1008,
            "seed": 1292387875,
            "llm_actor_ids": ["ella", "mia", "ryan"],
            "caps": CAPS,
            "real_provider_calls": 0,
            "timeout_steps": [
                {"actor_id": s.actor_id, "ordinal": s.decision_ordinal, "attempt": s.attempt_index}
                for s in tape.steps
                if s.result.outcome == "timeout"
            ],
            "final_world_sha256": result.trace.final_world_sha256,
            "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        }
        with (tape_path.parent / "v04-tape-provenance.json").open("xb") as stream:
            stream.write(canonical_bytes(provenance))
        print(json.dumps(provenance), flush=True)
        return 0
    tape = FakeTape.model_validate_json(gzip.decompress(tape_path.read_bytes()))
    provider = TapeProvider(tape)
    result, registration, reader = run(args.out, provider=provider, include_tape=True)
    provider.assert_consumed()
    replay_path = args.out / "source/replay.json"
    export_p3_replay(result.output, replay_path, source_reader=reader)
    verified = verify_inspection_source(
        result.output, replay_path, repository=ROOT, source_reader=reader
    )
    index = export_inspection(verified, args.out / "inspection")
    proof = recorded_proof(
        verified, result.output, args.out / "recorded", repository=ROOT, ancestors=(), reader=reader
    )
    report = {
        "fixture_id": "v04",
        "status": "PASS",
        "registration_sha256": canonical_sha256(registration),
        "tape_sha256": sha256(tape_path.read_bytes()).hexdigest(),
        "steps": len(tape.steps),
        "samples": len(index.samples),
        "decisions": len(index.decisions),
        "index_sha256": canonical_sha256(index),
        "recorded_proof": proof,
        "alive_at_1008": [r.id for r in verified.replay.frames[-1].residents if r.alive],
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    }
    (args.out / "proof.json").write_bytes(canonical_bytes(report))
    print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
