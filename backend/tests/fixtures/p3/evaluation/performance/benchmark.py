"""Explicit offline cache measurements; outputs are fresh, never accepted golden data."""

from __future__ import annotations

import argparse
import ast
import json
import runpy
import sys
import time
import tracemalloc
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT))

from scripts.p3_experiments import RaisingSentinel  # noqa: E402
from scripts.p3_trials import build_case_inputs  # noqa: E402

from living_island.agents.llm.fallback import FrozenRuleFallbackAdapter  # noqa: E402
from living_island.agents.types import PolicyConfig  # noqa: E402
from living_island.contract.p3_save import TrialRegistration  # noqa: E402
from living_island.memory.p3_types import canonical_bytes, canonical_sha256  # noqa: E402
from living_island.persistence import p3 as persistence  # noqa: E402
from living_island.persistence.p3 import (  # noqa: E402
    _VerificationSession,
    read_checkpoint_p3,
)
from living_island.persistence.p3_allocation import AllocationStore, initialize_fake  # noqa: E402
from living_island.persistence.p3_inspection import GitSourceReader  # noqa: E402
from living_island.sim import p3 as sim  # noqa: E402


def stats(session):
    return {
        name: getattr(session, name)
        for name in (
            "max_raw_bytes",
            "raw_bytes",
            "peak_raw_bytes",
            "retained_rows",
            "hits",
            "misses",
            "evictions",
        )
    }


def files(directory):
    return {
        p.name: sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.iterdir())
        if p.is_file()
    }


def measure_prefix(checkpoint):
    reader = GitSourceReader(ROOT)
    before = files(checkpoint.parent)
    start = time.perf_counter()
    expected = read_checkpoint_p3(checkpoint, source_reader=reader)
    source_warmup = time.perf_counter() - start
    cache = _VerificationSession()
    measurements = []
    for name, session in (("disabled", _VerificationSession(0)), ("cold", cache), ("warm", cache)):
        start = time.perf_counter()
        actual = read_checkpoint_p3(checkpoint, source_reader=reader, verification=session)
        elapsed = time.perf_counter() - start
        assert actual == expected
        measurements.append({"mode": name, "seconds": elapsed, **stats(session)})
    # Separate instrumented allocation measurement, excluded from the timings above.
    tracemalloc.start()
    measured = _VerificationSession()
    read_checkpoint_p3(checkpoint, source_reader=reader, verification=measured)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert before == files(checkpoint.parent)
    sizes = [len(row) for raw in expected.logs.values() for row in raw.splitlines()]
    return {
        "checkpoint": str(checkpoint.resolve()),
        "checkpoint_sha256": sha256(expected.raw).hexdigest(),
        "source_git_warmup_seconds": source_warmup,
        "measurements": measurements,
        "all_log_rows": len(sizes),
        "all_row_raw_bytes": sum(sizes),
        "largest_row_bytes": max(sizes),
        "instrumented_current_bytes": current,
        "instrumented_peak_bytes": peak,
        "source_preserved": True,
        "provider_accesses": 0,
        "authority_accesses": 0,
    }


def short_inputs():
    helper_path = ROOT / "backend/tests/fixtures/p3/evaluation/build_fixture.py"
    helper = runpy.run_path(str(helper_path))
    _, original_files, original, reader = helper["inputs"](include_tape=False)
    value = original.model_dump(mode="json")
    value["registration_id"] = "p3-perf-u1-short-m6"
    value["fake_fixture_id"] = "perf-short"
    value["cases"][0]["case_id"] = f"{value['registration_id']}.s{value['cases'][0]['seed']}"
    value["cases"][0]["ticks"] = 4
    path = Path(__file__).resolve().relative_to(ROOT).as_posix()
    raw = reader(original.implementation_commit, path)
    if raw != Path(__file__).read_bytes():
        raise ValueError("benchmark helper must be committed before evidence generation")
    pin = {"path": path, "sha256": sha256(raw).hexdigest()}
    value["input_pins"].append(pin)
    value["input_pins"].sort(key=lambda item: item["path"])
    registration = TrialRegistration.model_validate(value)
    content, inputs = build_case_inputs(ROOT, registration, registration.cases[0].case_id)
    implementation = json.loads(original_files["implementation.json"])
    for module in implementation["modules"]:
        if module["role"] in ("adapter", "counter"):
            module["files"].append(pin)
            module["files"].sort(key=lambda item: item["path"])
    inputs["implementation.json"] = canonical_bytes(implementation)
    return helper, content, inputs, registration, reader


BASELINE_COMMIT = "ec531c112fd45199f591fd5095f5b6ac4b8e6247"


def baseline_session_type():
    """Execute only the pinned prior cache class for a same-input comparison.

    All surrounding verifier/runtime code stays current. The only production
    behavior changed by this follow-up is this class's internal representation.
    The trusted Git source is never unpickled or accepted from an input artifact.
    """
    path = "backend/src/living_island/persistence/p3.py"
    raw = GitSourceReader(ROOT)(BASELINE_COMMIT, path)
    tree = ast.parse(raw, filename=f"{BASELINE_COMMIT}:{path}")
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == "_VerificationSession"
    )
    namespace = vars(persistence).copy()
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), namespace)
    return namespace["_VerificationSession"], sha256(raw).hexdigest()


def measure_short(output, *, compare_baseline=False):
    helper, content, inputs, registration, reader = short_inputs()
    case = registration.cases[0]
    summaries = []
    expected = None
    baseline, baseline_sha256 = baseline_session_type() if compare_baseline else (None, None)
    capacity = 128 * 1024 * 1024
    modes = [("disabled", _VerificationSession, 0), ("enabled", _VerificationSession, capacity)]
    if compare_baseline:
        modes = [
            ("disabled", _VerificationSession, 0),
            ("baseline", baseline, capacity),
            ("enabled", _VerificationSession, capacity),
            ("enabled-repeat", _VerificationSession, capacity),
            ("baseline-repeat", baseline, capacity),
        ]
    for mode, factory, capacity in modes:
        root = output / mode
        root.mkdir()
        authority = root / "isolated-fake-authority"
        initialize_fake(authority)
        store = AllocationStore(authority, mode="fake")
        store.enroll_fake(canonical_sha256(registration), case.case_id, case.caps)
        provider = helper["TapeBuilder"]()
        config = json.loads(inputs["p3-policy-configs.json"])[0]["config"]["fallback_config"]
        fallback = FrozenRuleFallbackAdapter(PolicyConfig.model_validate(config))
        session = factory(capacity)
        with patch.object(sim, "_VerificationSession", return_value=session):
            start = time.perf_counter()
            result = sim.run_p3(
                content,
                inputs,
                case.case_id,
                root / "source",
                allocation_store=store,
                provider=provider,
                fallback=fallback,
                source_reader=reader,
            )
            elapsed = time.perf_counter() - start
        current = files(result.output)
        request_hash = canonical_sha256([step.model_dump(mode="json") for step in provider.steps])
        if expected is None:
            expected = (current, request_hash)
        else:
            assert expected == (current, request_hash)
        provider_sentinel, authority_sentinel = RaisingSentinel(), RaisingSentinel()
        replay = sim.reexecute_p3(
            result.output,
            root / "recorded",
            provider=provider_sentinel,
            allocation_store=authority_sentinel,
            fallback=fallback,
            source_reader=reader,
        )
        assert replay.trace == result.trace and files(replay.output) == current
        sim.export_p3_replay(result.output, root / "replay.json", source_reader=reader)
        assert files(result.output) == current
        summaries.append(
            {
                "mode": mode,
                "seconds": elapsed,
                **stats(session),
                "steps": len(provider.steps),
                "step_sequence_sha256": request_hash,
                "source_files": current,
                "trace_sha256": canonical_sha256(result.trace),
                "replay_sha256": sha256((root / "replay.json").read_bytes()).hexdigest(),
                "provider_accesses_in_reexecution": provider_sentinel.accesses,
                "authority_accesses_in_reexecution": authority_sentinel.accesses,
            }
        )
    assert len({summary["replay_sha256"] for summary in summaries}) == 1
    return {
        "baseline_commit": BASELINE_COMMIT if compare_baseline else None,
        "baseline_persistence_sha256": baseline_sha256,
        "baseline_method": "exact prior cache class with current surrounding verifier",
        "horizon": 4,
        "seed": case.seed,
        "llm_actor_ids": case.llm_actor_ids,
        "implementation_commit": registration.implementation_commit,
        "registration_sha256": canonical_sha256(registration),
        "measurements": summaries,
        "all_source_bytes_identical": True,
        "reexecution_bytes_identical": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prefix", "short", "clone-short"])
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    if args.mode == "prefix":
        if args.checkpoint is None:
            raise ValueError("prefix mode requires a retained checkpoint")
        result = measure_prefix(args.checkpoint)
    else:
        result = measure_short(args.out, compare_baseline=args.mode == "clone-short")
    result["argv"] = [sys.executable, *sys.argv]
    result["benchmark_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    (args.out / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
