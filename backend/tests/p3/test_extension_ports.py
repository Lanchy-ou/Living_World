"""VF-20 offline adapter/selector interchange and EX-11/12 exact assemblies."""

from __future__ import annotations

import gzip
import importlib.util
import json
import subprocess
import sys
from functools import cache
from hashlib import sha256
from pathlib import Path

import pytest
from test_context import cognitive, profile
from test_experience import entity, packet
from test_persistence import retained_fixture
from test_reexecution import LocalFallback, Sentinel
from world_builders import tiny_content

from living_island.agents.p3.context import assemble_context
from living_island.agents.p3.prompts import render_provider_request
from living_island.agents.p3.types import DecisionRequestP3
from living_island.agents.policies.recorded import ReplayDiverged
from living_island.contract.p3_save import ActorPolicyConfig, TrialRegistration
from living_island.memory.experience import ingest_experience, initial_experience
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.memory.retrieval import retrieve
from living_island.persistence.p3_allocation import AllocationStore, initialize_fake
from living_island.sim.p3 import reexecute_p3, run_p3
from living_island.world.protocol import Coord, VisibleEntity

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.p3_trials import FakeTape  # noqa: E402

SELECTOR_PATH = "backend/tests/fixtures/p3/extensions/recent_only.py"
ADAPTER_PATH = "backend/tests/fixtures/p3/extensions/adapters.py"
PRODUCTION_SELECTOR = "backend/src/living_island/memory/retrieval.py"
SAFE = f"safe.directory={ROOT.as_posix()}"


@cache
def committed_source(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-c", SAFE, "show", f"{commit}:{path}"], cwd=ROOT)


def committed_head() -> str:
    return subprocess.check_output(
        ["git", "-c", SAFE, "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def fixture_selector():
    source = (ROOT / SELECTOR_PATH).read_bytes()
    commit = committed_head()
    assert committed_source(commit, SELECTOR_PATH) == source, "selector helper must be committed"
    spec = importlib.util.spec_from_file_location("p3_vf20_recent_only", ROOT / SELECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RecentOnlySelector(sha256(source).hexdigest())


def fixture_provider(profile_name: str, latency_ms: int, *, horizon: int = 1):
    source = (ROOT / ADAPTER_PATH).read_bytes()
    assert committed_source(committed_head(), ADAPTER_PATH) == source
    spec = importlib.util.spec_from_file_location("p3_vf20_adapters", ROOT / ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    label = "a" if latency_ms == 1 else "b"
    suffix = "" if horizon == 1 else f"-h{horizon}"
    path = ROOT / "backend/tests/fixtures/p3/extensions" / f"{profile_name}-{label}{suffix}.json.gz"
    tape_bytes = path.read_bytes()
    assert committed_source(committed_head(), path.relative_to(ROOT).as_posix()) == tape_bytes
    tape = FakeTape.model_validate_json(gzip.decompress(tape_bytes))
    adapter = module.FixtureAdapterA if latency_ms == 1 else module.FixtureAdapterB
    return adapter(tape)


def _pin(path: str, commit: str) -> dict[str, str]:
    return {"path": path, "sha256": sha256(committed_source(commit, path)).hexdigest()}


def pinned_inputs(content, *, fixture: bool, latency_ms: int = 1, horizon: int = 1):
    """Retain an actual committed source inventory, including the test-only selector."""
    files, _ = retained_fixture(content, horizon=horizon, fixture_profile=fixture)
    commit = committed_head()
    label = "a" if latency_ms == 1 else "b"
    profile_name = "recent-only" if fixture else "recent-relevant"
    suffix = "" if horizon == 1 else f"-h{horizon}"
    tape_path = f"backend/tests/fixtures/p3/extensions/{profile_name}-{label}{suffix}.json.gz"
    profile_path = (
        "backend/tests/fixtures/p3/extensions/context-profile.json"
        if fixture
        else "content/prompts/p3-v0.1/context-profile.json"
    )
    roles = {
        "adapter": [ADAPTER_PATH, "scripts/p3_trials.py"],
        "counter": ["scripts/p3_trials.py"],
        "goal": ["backend/src/living_island/agents/p3/cognition.py"],
        "runtime": ["backend/src/living_island/sim/p3.py"],
        "schema": ["backend/src/living_island/contract/p3_save.py"],
        "selector": [
            "backend/src/living_island/memory/p3_types.py",
            PRODUCTION_SELECTOR,
            *([SELECTOR_PATH] if fixture else []),
        ],
    }
    inventory = subprocess.check_output(
        [
            "git",
            "-c",
            SAFE,
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "--",
            "backend/src",
            "scripts",
            "backend/pyproject.toml",
            "backend/uv.lock",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    required_inputs = {
        SELECTOR_PATH,
        ADAPTER_PATH,
        PRODUCTION_SELECTOR,
        "backend/src/living_island/memory/p3_types.py",
        "scripts/p3_trials.py",
        "backend/src/living_island/agents/p3/prompts.py",
        profile_path,
        "content/prompts/p3-v0.1/resident.txt",
        tape_path,
    }
    pinned = {
        path: _pin(path, commit)
        for path in set(inventory)
        | required_inputs
        | {path for paths in roles.values() for path in paths}
    }
    registration = json.loads(files["trial-registration.json"])
    for item in registration["cases"][0]["policy_templates"]:
        item["config"]["adapter_id"] = f"vf-20-adapter-{label}"
    registration.update(
        implementation_commit=commit,
        world_pin_commit=commit,
        fake_fixture_id="vf-20",
        implementation_pins=[pinned[path] for path in sorted(inventory)],
        input_pins=[pinned[path] for path in sorted(required_inputs)],
    )
    files["trial-registration.json"] = canonical_bytes(registration)
    policies = json.loads(files["p3-policy-configs.json"])
    for item in policies:
        item["config"]["adapter_id"] = f"vf-20-adapter-{label}"
        item["config"]["trial_registration_sha256"] = canonical_sha256(registration)
    files["p3-policy-configs.json"] = canonical_bytes(policies)
    files["context-profile.json"] = canonical_bytes(
        json.loads(committed_source(commit, profile_path))
    )
    files["prompt.txt"] = committed_source(commit, "content/prompts/p3-v0.1/resident.txt")
    files["implementation.json"] = canonical_bytes(
        {
            "implementation_pin_version": "0.1",
            "code_commit": commit,
            "modules": [
                {"role": role, "files": [pinned[path] for path in sorted(paths)]}
                for role, paths in roles.items()
            ],
        }
    )
    return files, committed_source


def _delivery(tick: int, own_x: int, seen: VisibleEntity):
    base = packet(tick, entities=[seen])
    perception = base.perception.model_copy(update={"own_position": Coord(x=own_x, y=0)})
    return base.model_copy(update={"perception": perception})


def _entity(identifier: str, x: int):
    return entity(identifier).model_copy(update={"position": Coord(x=x, y=0)})


def _six_records():
    deliveries = [
        _delivery(0, 0, _entity("ryan", 1)),
        _delivery(1, 2, _entity("mia", 3)),
        _delivery(2, 4, _entity("ryan", 5)),
    ]
    store = initial_experience("ella")
    for delivery in deliveries:
        store = ingest_experience(store, delivery, run_id="r")
    return deliveries[-1].perception, store


def _assembly_sequences(assembly):
    manifest = assembly.manifest
    return (
        [record.sequence for record in assembly.context.recalled_experience],
        [record.sequence for record in assembly.provider_projection.recalled_experience],
        [item.experience_id for item in manifest.experiences],
    )


def test_ex11_actual_selectors_preserve_distinct_complete_assemblies():
    perception, store = _six_records()
    state = cognitive(perception, store=store)
    selector = fixture_selector()
    recent = assemble_context(perception, state, profile(), purpose="fake")
    alternate = assemble_context(
        perception,
        state,
        profile(True),
        purpose="fake",
        selector=selector,
        selector_sha256=selector.implementation_sha256,
    )
    for assembly, expected in ((recent, [5, 4, 1, 3, 2, 0]), (alternate, [5, 4, 3, 2, 1, 0])):
        recall, projection, manifest_ids = _assembly_sequences(assembly)
        assert recall == projection == expected
        assert manifest_ids == [store.records[sequence].experience_id for sequence in expected]
        assert [item.omission for item in assembly.manifest.experiences] == [None] * 6
        assert assembly.manifest.static_tiles == []
        assert assembly.manifest.store_next_sequence == 6
        assert assembly.manifest.evicted_record_count == 0
        assert assembly.context_sha256 == canonical_sha256(assembly.context)
        assert assembly.projection_sha256 == canonical_sha256(assembly.provider_projection)
    assert alternate.manifest.retrieval_profile == "recent-only-fixture-v0"
    assert alternate.manifest.context_profile_id == "p3-context-recent-only-fixture-v0"
    assert alternate.manifest.projection_profile == "p3-context-v0"
    assert recent.context_sha256 != alternate.context_sha256
    assert store.next_sequence == 6


def test_ex12_empty_and_limit_keep_actual_fixture_identity():
    selector = fixture_selector()
    empty_p = packet().perception
    empty_store = initial_experience("ella").model_copy(update={"last_ingested_tick": 0})
    empty = assemble_context(
        empty_p,
        cognitive(empty_p, store=empty_store),
        profile(True),
        purpose="fake",
        selector=selector,
        selector_sha256=selector.implementation_sha256,
    )
    assert empty.context.recalled_experience == []
    assert empty.manifest.experiences == []
    assert empty.manifest.retrieval_profile == selector.retrieval_profile
    assert empty.manifest.context_profile_id == profile(True).context_profile_id
    store = initial_experience("ella")
    for tick in range(17):
        delivery = packet(tick)
        store = ingest_experience(store, delivery, run_id="r")
    full = assemble_context(
        delivery.perception,
        cognitive(delivery.perception, store=store),
        profile(True),
        purpose="fake",
        selector=selector,
        selector_sha256=selector.implementation_sha256,
    )
    assert [record.sequence for record in full.context.recalled_experience] == list(
        range(16, 0, -1)
    )
    assert [record.sequence for record in full.provider_projection.recalled_experience] == list(
        range(16, 0, -1)
    )
    assert [item.experience_id for item in full.manifest.experiences] == [
        store.records[sequence].experience_id for sequence in range(16, -1, -1)
    ]
    assert [item.omission for item in full.manifest.experiences] == [None] * 16 + [
        "retrieval_limit"
    ]


@pytest.mark.parametrize(
    "invalid", ["missing", "wrong_hash", "wrong_profile", "unknown_strategy", "live"]
)
def test_ex12_invalid_pure_bindings_refuse_before_selector_call(invalid):
    perception, store = _six_records()
    state = cognitive(perception, store=store)

    class ProbedSelector:
        retrieval_profile = "recent-only-fixture-v0"
        implementation_sha256 = "f" * 64
        calls = 0

        def retrieve(self, state, query):
            self.calls += 1
            raise AssertionError("selector was called")

    selector = ProbedSelector()
    selected = profile(True)
    purpose = "fake"
    pin = selector.implementation_sha256
    if invalid == "missing":
        pin = None
    elif invalid == "wrong_hash":
        pin = "e" * 64
    elif invalid == "wrong_profile":
        selected = profile()
    elif invalid == "unknown_strategy":
        selected = selected.model_copy(update={"retrieval_profile": "unregistered-strategy"})
    else:
        purpose = "live"
    with pytest.raises(ValueError):
        assemble_context(
            perception,
            state,
            selected,
            purpose=purpose,
            selector=selector,
            selector_sha256=pin,
        )
    assert selector.calls == 0


def test_ex12_empty_manifest_identity_mismatch_refuses_before_provider(tmp_path):
    perception = packet().perception
    store = initial_experience("ella").model_copy(update={"last_ingested_tick": 0})
    state = cognitive(perception, store=store)
    selector = fixture_selector()
    fixture_assembly = assemble_context(
        perception,
        state,
        profile(True),
        purpose="fake",
        selector=selector,
        selector_sha256=selector.implementation_sha256,
    )
    production_assembly = assemble_context(perception, state, profile(), purpose="fake")
    assert fixture_assembly.context.recalled_experience == []
    assert production_assembly.context.recalled_experience == []
    assert fixture_assembly.context_sha256 == production_assembly.context_sha256
    assert fixture_assembly.projection_sha256 == production_assembly.projection_sha256
    request = DecisionRequestP3(
        request_schema_version="0.2",
        actor_id="ella",
        tick=0,
        decision_ordinal=0,
        triggers=[],
        context=fixture_assembly.context,
    )
    content = tiny_content(["~~~~~~~", "~.SC..~", "~.MF..~", "~~~~~~~"], {"ella": (1, 1)})
    files, _ = pinned_inputs(content, fixture=True)
    configured = ActorPolicyConfig.model_validate(json.loads(files["p3-policy-configs.json"])[0])
    config = configured.config.model_copy(
        update={"identity_sha256": canonical_sha256(state.identity)}
    )
    assert render_provider_request(fixture_assembly, request, config, files["prompt.txt"])
    wrong_manifest = fixture_assembly.model_copy(
        update={
            "manifest": fixture_assembly.manifest.model_copy(
                update={
                    "context_profile_id": "p3-context-v0",
                    "retrieval_profile": "recent-relevant-v0",
                }
            )
        }
    )
    with pytest.raises(ValueError, match="context profile does not match the policy"):
        render_provider_request(wrong_manifest, request, config, files["prompt.txt"])


def _three_actor_case(tmp_path: Path, *, fixture: bool, latency_ms: int = 1, horizon: int = 1):
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
        {"ella": (2, 3), "mia": (5, 4), "ryan": (8, 4)},
        day_radius_tiles=10,
    )
    files, reader = pinned_inputs(content, fixture=fixture, latency_ms=latency_ms, horizon=horizon)
    registration = TrialRegistration.model_validate_json(files["trial-registration.json"])
    case = registration.cases[0]
    authority = tmp_path / "authority"
    initialize_fake(authority)
    store = AllocationStore(authority, mode="fake")
    store.enroll_fake(sha256(files["trial-registration.json"]).hexdigest(), case.case_id, case.caps)
    policies = {
        item["actor_id"]: ActorPolicyConfig.model_validate(item).config
        for item in json.loads(files["p3-policy-configs.json"])
    }
    return content, files, case.case_id, store, reader, LocalFallback(policies)


def _read_jsonl(path: Path):
    return [json.loads(row) for row in path.read_bytes().splitlines()]


@pytest.mark.parametrize("fixture", [False, True], ids=["recent-relevant", "recent-only"])
@pytest.mark.parametrize("latency_ms", [1, 2], ids=["adapter-a", "adapter-b"])
def test_vf20_three_actor_offline_ports_and_exact_replay(tmp_path, fixture, latency_ms):
    content, files, case, store, reader, fallback = _three_actor_case(
        tmp_path, fixture=fixture, latency_ms=latency_ms
    )
    selector = fixture_selector() if fixture else None
    provider = fixture_provider("recent-only" if fixture else "recent-relevant", latency_ms)
    original = run_p3(
        content,
        files,
        case,
        tmp_path / "original",
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
        selector=selector,
        selector_sha256=None if selector is None else selector.implementation_sha256,
        clock_ms=lambda: 0,
    )
    provider.assert_consumed()
    decisions = _read_jsonl(original.output / "decisions-p3.jsonl")
    assert [row["actor_id"] for row in decisions] == ["ella", "mia", "ryan"]
    calls = _read_jsonl(original.output / "llm-calls.jsonl")
    assert len(calls) == 3
    assert [row["result"]["latency_ms"] for row in calls] == [latency_ms] * 3
    contexts = _read_jsonl(original.output / "contexts-p3.jsonl")
    expected_profile = "recent-only-fixture-v0" if fixture else "recent-relevant-v0"
    assert len(contexts) == 3
    for row in contexts:
        assembly = row["assembly"]
        manifest = assembly["manifest"]
        assert manifest["retrieval_profile"] == expected_profile
        assert manifest["context_profile_id"] == (
            "p3-context-recent-only-fixture-v0" if fixture else "p3-context-v0"
        )
        assert manifest["projection_profile"] == "p3-context-v0"
        assert assembly["context_sha256"] == canonical_sha256(assembly["context"])
        assert assembly["projection_sha256"] == canonical_sha256(assembly["provider_projection"])
        recalled_ids = [
            record["experience_id"] for record in assembly["context"]["recalled_experience"]
        ]
        projected_ids = [
            record["experience_id"]
            for record in assembly["provider_projection"]["recalled_experience"]
        ]
        assert (
            recalled_ids
            == projected_ids
            == [item["experience_id"] for item in manifest["experiences"] if item["retrieved"]]
        )
        assert len(manifest["experiences"]) == manifest["retained_record_count"]
    replay = reexecute_p3(
        original.output,
        tmp_path / "replay",
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        source_reader=reader,
        selector=fixture_selector() if fixture else None,
        selector_sha256=None if selector is None else selector.implementation_sha256,
    )
    assert replay.checkpoint == original.checkpoint
    for name in (
        "contexts-p3.jsonl",
        "decisions-p3.jsonl",
        "llm-calls.jsonl",
        "events.jsonl",
    ):
        assert (replay.output / name).read_bytes() == (original.output / name).read_bytes()


@pytest.mark.parametrize("fixture", [False, True], ids=["recent-relevant", "recent-only"])
def test_vf20_adapter_latency_changes_only_diagnostic_audit(tmp_path, fixture):
    results = []
    for latency_ms in (1, 2):
        work = tmp_path / f"adapter-{latency_ms}"
        content, files, case, store, reader, fallback = _three_actor_case(
            work, fixture=fixture, latency_ms=latency_ms
        )
        selector = fixture_selector() if fixture else None
        provider = fixture_provider("recent-only" if fixture else "recent-relevant", latency_ms)
        result = run_p3(
            content,
            files,
            case,
            work / "run",
            allocation_store=store,
            provider=provider,
            fallback=fallback,
            source_reader=reader,
            selector=selector,
            selector_sha256=None if selector is None else selector.implementation_sha256,
            clock_ms=lambda: 0,
        )
        provider.assert_consumed()
        results.append(result)
    a, b = results
    assert a.checkpoint.world == b.checkpoint.world
    assert [state.cognitive_state for state in a.checkpoint.agent_state.runtime_states] == [
        state.cognitive_state for state in b.checkpoint.agent_state.runtime_states
    ]
    assert (a.output / "contexts-p3.jsonl").read_bytes() == (
        b.output / "contexts-p3.jsonl"
    ).read_bytes()
    assert (a.output / "llm-calls.jsonl").read_bytes() != (
        b.output / "llm-calls.jsonl"
    ).read_bytes()


def test_vf20_closed_tapes_refuse_missing_and_extra_calls():
    for profile_name in ("recent-relevant", "recent-only"):
        for latency_ms in (1, 2):
            provider = fixture_provider(profile_name, latency_ms)
            with pytest.raises(ValueError, match="FAKE_TAPE_CALLS_MISSING"):
                provider.assert_consumed()
            provider.cursor = len(provider.tape.steps)
            with pytest.raises(ValueError, match="FAKE_TAPE_EXHAUSTED"):
                provider.prepare(provider.tape.steps[0].expected_request)


def test_vf20_divergent_selector_replay_recomputes_all_three_states(tmp_path):
    content, files, case, store, reader, fallback = _three_actor_case(
        tmp_path, fixture=True, horizon=2
    )
    selector = fixture_selector()
    provider = fixture_provider("recent-only", 1, horizon=2)
    original = run_p3(
        content,
        files,
        case,
        tmp_path / "original",
        allocation_store=store,
        provider=provider,
        fallback=fallback,
        source_reader=reader,
        selector=selector,
        selector_sha256=selector.implementation_sha256,
        clock_ms=lambda: 0,
    )
    provider.assert_consumed()
    contexts = _read_jsonl(original.output / "contexts-p3.jsonl")
    assert len(contexts) == 6
    tick_one = [row for row in contexts if row["request"]["tick"] == 1]
    assert [row["request"]["actor_id"] for row in tick_one] == ["ella", "mia", "ryan"]
    for row in tick_one:
        sequences = [
            record["sequence"] for record in row["assembly"]["context"]["recalled_experience"]
        ]
        assert sequences == sorted(sequences, reverse=True)
    replay = reexecute_p3(
        original.output,
        tmp_path / "replay",
        provider=Sentinel(),
        fallback=Sentinel(),
        allocation_store=Sentinel(),
        source_reader=reader,
        selector=fixture_selector(),
        selector_sha256=selector.implementation_sha256,
    )
    assert replay.checkpoint == original.checkpoint
    assert (replay.output / "contexts-p3.jsonl").read_bytes() == (
        original.output / "contexts-p3.jsonl"
    ).read_bytes()

    class WrongAlgorithm:
        """Adversarial identity claim: use default ranking under the fixture ID."""

        retrieval_profile = "recent-only-fixture-v0"
        implementation_sha256 = selector.implementation_sha256

        def retrieve(self, state, query):
            return retrieve(state, query, "recent-relevant-v0")

    with pytest.raises(ReplayDiverged):
        reexecute_p3(
            original.output,
            tmp_path / "wrong-algorithm",
            provider=Sentinel(),
            fallback=Sentinel(),
            allocation_store=Sentinel(),
            source_reader=reader,
            selector=WrongAlgorithm(),
            selector_sha256=selector.implementation_sha256,
        )


@pytest.mark.parametrize(
    "defect",
    ["missing_selector", "wrong_selector", "source", "profile", "config", "manifest", "live"],
)
def test_vf20_registration_binding_refuses_before_provider(tmp_path, defect):
    content, files, case, store, reader, fallback = _three_actor_case(tmp_path, fixture=True)
    selector = fixture_selector()
    sha = selector.implementation_sha256
    if defect == "missing_selector":
        selector = None
        sha = None
    elif defect == "wrong_selector":
        sha = "e" * 64
    elif defect == "source":
        original_reader = reader

        def reader(commit, path):
            raw = original_reader(commit, path)
            return raw + b"altered" if path == SELECTOR_PATH else raw

    elif defect == "profile":
        files["context-profile.json"] = canonical_bytes(profile())
    elif defect == "config":
        registration = json.loads(files["trial-registration.json"])
        for item in registration["cases"][0]["policy_templates"]:
            item["config"]["context_profile_id"] = "p3-context-v0"
        files["trial-registration.json"] = canonical_bytes(registration)
        policies = json.loads(files["p3-policy-configs.json"])
        for item in policies:
            item["config"]["context_profile_id"] = "p3-context-v0"
            item["config"]["trial_registration_sha256"] = canonical_sha256(registration)
        files["p3-policy-configs.json"] = canonical_bytes(policies)
    elif defect == "manifest":
        implementation = json.loads(files["implementation.json"])
        implementation["modules"][-1]["files"] = [
            item for item in implementation["modules"][-1]["files"] if item["path"] != SELECTOR_PATH
        ]
        files["implementation.json"] = canonical_bytes(implementation)
    else:
        registration = json.loads(files["trial-registration.json"])
        registration["purpose"] = "development"
        registration["fake_fixture_id"] = None
        files["trial-registration.json"] = canonical_bytes(registration)
        policies = json.loads(files["p3-policy-configs.json"])
        for item in policies:
            item["config"]["trial_registration_sha256"] = canonical_sha256(registration)
        files["p3-policy-configs.json"] = canonical_bytes(policies)
    provider = fixture_provider("recent-only", 1)
    expected = (
        "fixture retrieval strategies require a fake registration" if defect == "live" else None
    )
    with pytest.raises(ValueError, match=expected):
        run_p3(
            content,
            files,
            case,
            tmp_path / "refused",
            allocation_store=store,
            provider=provider,
            fallback=fallback,
            source_reader=reader,
            selector=selector,
            selector_sha256=sha,
            clock_ms=lambda: 0,
        )
    assert provider.cursor == 0
