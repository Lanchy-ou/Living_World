"""Offline launcher registration, shared authority and invocation-lineage checks."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from types import ModuleType

import pytest
from living_island.agents.llm.provider import DeepSeekResponsesAdapter, TransportResponse
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.persistence.p3_allocation import (
    AllocationError,
    initialize_fake,
)

REPOSITORY = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY / "scripts/p3_trials.py"
SPEC = importlib.util.spec_from_file_location("p305_launcher_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = launcher
SPEC.loader.exec_module(launcher)


def commit(repository: Path, *paths: str) -> str:
    launcher.git(repository, "add", "--", *paths)
    launcher.git(
        repository,
        "-c",
        "user.name=P3 fixture",
        "-c",
        "user.email=p3-fixture@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "Retain immutable offline fixture inputs",
    )
    return launcher.git(repository, "rev-parse", "HEAD").decode().strip()


def clone_repository(directory: Path) -> Path:
    """Create a disposable Git fixture, never a task branch or a live authority."""
    result = subprocess.run(
        ["git", "clone", "--shared", "--quiet", str(REPOSITORY), str(directory)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    # Tests also work before the executor commits a reversible launcher correction.
    (directory / "scripts/p3_trials.py").write_bytes(SCRIPT.read_bytes())
    commit(directory, "scripts/p3_trials.py")
    return directory


@pytest.fixture
def repository(tmp_path):
    return clone_repository(tmp_path / "repository")


def register(repository, *, purpose="fake", name="launcher-fixture", committed=True):
    head = launcher.git(repository, "rev-parse", "HEAD").decode().strip()
    registration = launcher.build_registration(
        repository, head, purpose=purpose, registration_id=name
    )
    path = repository / f"content/experiments/p3/development/{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(registration))
    if committed:
        commit(repository, path.relative_to(repository).as_posix())
    return registration, path


@pytest.fixture(scope="module")
def registered(tmp_path_factory):
    repository = clone_repository(tmp_path_factory.mktemp("p305-registration") / "repository")
    registration, path = register(repository)
    return repository, registration, path


def fake_enrollment(repository, tmp_path):
    registration, path = register(repository)
    authority = tmp_path / "isolated-fake-authority"
    initialize_fake(authority)
    keys = launcher.enroll_registration(repository, path, fake_authority=authority)
    return registration, path, authority, keys[0]


class WaitTransport:
    """Real P3-04 wire mapping with a local byte response; no socket or key."""

    def __init__(self):
        self.bodies = []

    def exchange(self, body, timeout_ms):
        self.bodies.append(body)
        payload = json.loads(body)
        user = json.loads(payload["input"][1]["content"])
        current = user["context"]["goals"]["current"]
        proposal = {
            "proposal_schema_version": "0.1",
            "actions": [{"action_type": "wait", "target": None, "parameters": {}, "reason": None}],
            "cognitive_delta": {
                "delta_schema_version": "0.1",
                "goal_change": {
                    "operation": "continue",
                    "expected_goal_id": None if current is None else current["goal_id"],
                    "proposal": None,
                },
            },
        }
        response = {
            "id": "offline-launcher-response",
            "object": "response",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": canonical_bytes(proposal).decode()}
                    ],
                }
            ],
            "usage": {"input_tokens": 80, "output_tokens": 10},
        }
        return TransportResponse(200, canonical_bytes(response), True)


class FixtureAdapter(DeepSeekResponsesAdapter):
    """Explicit fake count units; never used as a production token-count proof."""

    def count_input_tokens(self, request, wire):
        assert request.settings.input_counter_id == "p3-tape-count"
        return 100


def fake_provider():
    transport = WaitTransport()
    return FixtureAdapter(transport), transport


def public_documents(*, model=None, input_price="2", schema=True):
    version = launcher.COUNTER_MODEL_VERSION if model is None else model
    pricing = f"""<table><tr><th>Model</th><th>deepseek-flash</th></tr>
    <tr><td>模型版本</td><td>{version}</td></tr>
    <tr><td>Responses API</td><td>支持</td></tr>
    <tr><td>思考模式</td><td>思考与非思考模式</td></tr>
    <tr><td>高峰时段 百万tokens输入 缓存未命中</td><td>{input_price}元</td></tr>
    <tr><td>高峰时段 百万tokens输出</td><td>8元</td></tr></table>"""
    guide = """<table><tr><th>Parameter</th><th>Support Status</th></tr>
    <tr><td>text</td><td>Partially supported. format fully supported</td></tr>
    <tr><td>reasoning</td><td>Partially supported. effort supported</td></tr></table>
    <table><tr><th>Input item</th><th>Support</th></tr>
    <tr><td>reasoning</td><td>Supported</td></tr></table>"""
    return {
        launcher.PRICE_URL: pricing.encode(),
        launcher.GUIDE_URL: guide.encode(),
        launcher.API_URL: b"json_schema none" if schema else b"none",
    }


def evidence():
    return launcher.LiveEvidence.model_validate_json(
        (REPOSITORY / launcher.PREFLIGHT_PATH).read_bytes()
    )


def test_registration_freezes_approved_world_real_inputs_and_actor_policies(registered):
    repository, registration, path = registered
    assert launcher.validate_registration(repository, path) == registration
    case = registration.cases[0]
    assert (registration.world_pin_commit, case.seed, case.ticks, case.llm_actor_ids) == (
        launcher.WORLD_COMMIT,
        1292387875,
        24,
        ["ella"],
    )
    assert case.caps.micro_cny == 0
    assert registration.aggregate_caps == case.caps
    _, files = launcher.build_case_inputs(repository, registration, case.case_id)
    policies = json.loads(files["p3-policy-configs.json"])
    assert {p["actor_id"]: p["config"]["policy_id"] for p in policies} == {
        "ella": "llm-v0",
        "mia": "rule-based-v0",
        "ryan": "rule-based-v0",
    }
    assert all(
        p["config"]["trial_registration_sha256"] == canonical_sha256(registration) for p in policies
    )
    modules = json.loads(files["implementation.json"])["modules"]
    for role in ("adapter", "counter"):
        assert "scripts/p3_trials.py" in [
            pin["path"] for module in modules if module["role"] == role for pin in module["files"]
        ]
    assert registration.world_config_sha256 != "0" * 64


@pytest.mark.parametrize("mutation", ["cap", "actor", "inventory", "world", "unknown"])
def test_registration_mutations_refused_before_any_dispatch(registered, tmp_path, mutation):
    repository, registration, _ = registered
    raw = registration.model_dump(mode="json")
    if mutation == "cap":
        raw["cases"][0]["caps"]["micro_cny"] = 1
    elif mutation == "actor":
        raw["cases"][0]["llm_actor_ids"] = ["mia"]
    elif mutation == "inventory":
        raw["implementation_pins"] = raw["implementation_pins"][1:]
    elif mutation == "world":
        raw["world_pin_commit"] = "0" * 40
    else:
        raw["credentials"] = "forbidden"
    path = tmp_path / "changed.json"
    path.write_bytes(canonical_bytes(raw))
    with pytest.raises(ValueError):
        launcher.validate_registration(repository, path)


def test_dirty_or_untracked_source_is_not_hidden_by_git_blob_cache(repository):
    _, path = register(repository)
    launcher.validate_registration(repository, path)
    source = repository / "scripts/p3_trials.py"
    original = source.read_bytes()
    source.write_bytes(original + b"\n# mutable drift\n")
    with pytest.raises(ValueError, match="PINNED_SOURCE_DRIFT"):
        launcher.validate_registration(repository, path)
    source.write_bytes(original)
    new_source = repository / "backend/src/living_island/launcher_untracked.py"
    new_source.write_text("# unauthorized source\n")
    with pytest.raises(ValueError, match="UNTRACKED_IMPLEMENTATION_SOURCE"):
        launcher.validate_registration(repository, path)


def test_active_import_from_unpinned_source_is_refused(registered, tmp_path, monkeypatch):
    repository, _, path = registered
    source = tmp_path / "foreign.py"
    source.write_text("# not part of the pinned package\n")
    module = ModuleType("living_island.foreign")
    module.__file__ = str(source)
    monkeypatch.setitem(sys.modules, "living_island.foreign", module)
    with pytest.raises(ValueError, match="ACTIVE_IMPLEMENTATION_SOURCE_DRIFT"):
        launcher.validate_registration(repository, path)


def test_validate_cli_does_not_touch_credentials_provider_or_authority(
    registered, monkeypatch, capsys
):
    repository, _, path = registered

    def fail(*args, **kwargs):
        raise AssertionError("validation touched external seam")

    for name in ("_credential", "_live_store", "current_preflight", "DeepSeekResponsesAdapter"):
        monkeypatch.setattr(launcher, name, fail)
    assert (
        launcher.main(["--repository", str(repository), "validate", "--registration", str(path)])
        == 0
    )
    assert "no dispatch" in capsys.readouterr().out


def test_public_preflight_checks_fresh_documents_and_accepts_unchanged_later_date():
    expected = evidence().model_copy(update={"checked_on": "2026-11-01"})
    documents = public_documents()
    observed = launcher.current_preflight(expected, fetch=documents.__getitem__)
    assert observed["model_version"] == expected.model_version
    assert len(observed["documents"]) == 3
    assert observed["documents"][0]["sha256"] == sha256(documents[launcher.PRICE_URL]).hexdigest()


@pytest.mark.parametrize("changes", [{"model": "drift"}, {"input_price": "3"}, {"schema": False}])
def test_public_model_price_or_schema_drift_refuses(changes):
    with pytest.raises(ValueError, match="PUBLIC_PREFLIGHT_"):
        launcher.current_preflight(evidence(), fetch=public_documents(**changes).__getitem__)


def test_unavailable_public_documents_refuse():
    def unavailable(url):
        raise OSError("fixture unavailable")

    with pytest.raises(OSError):
        launcher.current_preflight(evidence(), fetch=unavailable)


def test_credentials_are_explicit_dotenv_only_and_never_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-must-not-be-used")
    path = tmp_path / ".env"
    with pytest.raises(ValueError, match="DOTENV_CREDENTIAL_UNAVAILABLE"):
        launcher._credential(path)
    path.write_text("OTHER=value\nDEEPSEEK_API_KEY='fixture-secret-only'\n")
    assert launcher._credential(path) == "fixture-secret-only"
    path.write_text("DEEPSEEK_API_KEY=one\nDEEPSEEK_API_KEY=two\n")
    with pytest.raises(ValueError, match="DOTENV_CREDENTIAL_INVALID"):
        launcher._credential(path)
    wrong = tmp_path / "key.txt"
    wrong.write_text("DEEPSEEK_API_KEY=fixture-secret-only")
    with pytest.raises(ValueError):
        launcher._credential(wrong)


def test_uncommitted_registration_and_missing_authority_cannot_enroll(repository, tmp_path):
    _, path = register(repository, purpose="smoke", committed=False)
    with pytest.raises(ValueError, match="REGISTRATION_MUST_BE_COMMITTED"):
        launcher.enroll_registration(repository, path)
    commit(repository, path.relative_to(repository).as_posix())
    with pytest.raises((ValueError, OSError)):
        launcher.enroll_registration(repository, path)
    assert not launcher.live_locations(repository)[0].exists()


def test_canonical_authority_six_slots_duplicate_registration_and_no_reinitialization(repository):
    registration, path = register(repository, purpose="smoke")
    launcher.initialize_authority(repository)
    root, approval = launcher.live_locations(repository)
    assert root.is_relative_to(launcher.common_directory(repository))
    pilot = json.loads(approval.read_bytes())
    assert len(pilot["slots"]) == 6
    assert sum(s["caps"]["micro_cny"] for s in pilot["slots"]) == 150000000
    first = launcher.enroll_registration(repository, path)
    before = approval.read_bytes()
    assert launcher.enroll_registration(repository, path) == first
    assert approval.read_bytes() == before
    _, alternate = register(repository, purpose="smoke", name="launcher-other")
    with pytest.raises(AllocationError, match="ALLOCATION_ALREADY_ENROLLED"):
        launcher.enroll_registration(repository, alternate)
    with pytest.raises(ValueError, match="PILOT_ALREADY_INITIALIZED_OR_REQUIRES_REPAIR"):
        launcher.initialize_authority(repository)
    assert sum(s["binding"] is not None for s in json.loads(approval.read_bytes())["slots"]) == 1
    receipt = launcher.CaseReceipt.model_validate_json(
        (
            launcher._receipt_directory(repository, registration)
            / f"{registration.cases[0].case_id}.json"
        ).read_bytes()
    )
    assert receipt.status == "not_started" and receipt.allocation_key == first[0]


def test_enrollment_crash_after_binding_recovers_same_slot_once(repository, monkeypatch):
    _, path = register(repository, purpose="smoke")
    launcher.initialize_authority(repository)
    real_store = launcher._live_store(repository)

    def crash(stage):
        if stage == "slot_bind:after_replace":
            raise RuntimeError("fixture enrollment crash")

    real_store.fault = crash
    with monkeypatch.context() as patch:
        patch.setattr(launcher, "_live_store", lambda repository: real_store)
        with pytest.raises(RuntimeError, match="fixture enrollment crash"):
            launcher.enroll_registration(repository, path)
    key = launcher.enroll_registration(repository, path)[0]
    root, approval = launcher.live_locations(repository)
    pilot = json.loads(approval.read_bytes())
    bound = [slot["binding"] for slot in pilot["slots"] if slot["binding"] is not None]
    assert len(bound) == 1 and bound[0]["allocation_key"] == key
    assert bound[0]["state"] == "issued"
    assert len(list((root / "allocations").glob("*.json"))) == 1


def test_real_second_process_cannot_take_receipt_lock(tmp_path):
    path = tmp_path / "receipt.lock"
    code = """import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('launcher_lock_child',sys.argv[1])
m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
try:
    with m._persistent_lock(Path(sys.argv[2])): pass
except ValueError as exc:
    print(type(exc).__name__);sys.exit(0)
sys.exit(3)
"""
    with launcher._persistent_lock(path):
        child = subprocess.run(
            [sys.executable, "-c", code, str(SCRIPT), str(path)],
            env={**os.environ, "PYTHONPATH": str(REPOSITORY / "backend/src")},
            capture_output=True,
            timeout=15,
        )
    assert child.returncode == 0, child.stderr.decode(errors="replace")
    assert b"AllocationError" in child.stdout
    with launcher._persistent_lock(path):
        pass


def test_closed_tape_requires_exact_request_wire_and_attempt_order():
    from test_provider import COMPLETED, request

    provider = DeepSeekResponsesAdapter()
    prepared = request(json.dumps({"request": {"actor_id": "ella", "decision_ordinal": 0}}))
    wire = provider.prepare(prepared)
    from living_island.agents.llm.provider import map_response

    result = map_response(TransportResponse(200, COMPLETED, True), latency_ms=1)
    step = {
        "actor_id": "ella",
        "decision_ordinal": 0,
        "attempt_index": 0,
        "expected_request": prepared.model_dump(mode="json"),
        "expected_wire": wire.model_dump(mode="json"),
        "expected_input_tokens": 100,
        "result": result.model_dump(mode="json"),
    }
    raw = {"fake_schema_version": "0.1", "fixture_id": "launcher-tape", "steps": [step]}
    tape = launcher.FakeTape.model_validate(raw)
    adapter = launcher.TapeProvider(tape)
    assert adapter.prepare(prepared) == wire
    assert adapter.count_input_tokens(prepared, wire) == 100
    with pytest.raises(ValueError, match="FAKE_TAPE_REQUEST_MISMATCH"):
        adapter.prepare(prepared.model_copy(update={"model_id": "changed"}))
    with pytest.raises(ValueError, match="FAKE_TAPE_REQUEST_MISMATCH"):
        adapter.count_input_tokens(prepared, wire.model_copy(update={"path": "/changed"}))
    assert adapter.complete(prepared, wire, 1000) == result
    adapter.assert_consumed()
    with pytest.raises(ValueError, match="FAKE_TAPE_EXHAUSTED"):
        adapter.complete(prepared, wire, 1000)
    with pytest.raises(ValueError, match="FAKE_TAPE_ATTEMPT_SEQUENCE"):
        launcher.FakeTape.model_validate({**raw, "steps": [{**step, "attempt_index": 1}]})
    with pytest.raises(ValueError):
        launcher.FakeTape.model_validate({**raw, "not_declared": True})


def test_fake_run_and_resume_preserve_one_allocation_refuse_repeat_and_stale(repository, tmp_path):
    registration, path, authority, key = fake_enrollment(repository, tmp_path)
    provider, transport = fake_provider()
    case = registration.cases[0].case_id
    directory = repository / "runs/p3" / registration.registration_id
    first = launcher.run_registration(
        repository,
        path,
        case,
        directory / "first",
        fake_authority=authority,
        provider=provider,
        ticks=1,
    )
    assert transport.bodies and first.world.tick == 1
    first_checkpoint = first.output / "checkpoint-0000000001.json"
    with pytest.raises(ValueError, match="CASE_ALREADY_STARTED"):
        launcher.run_registration(
            repository,
            path,
            case,
            directory / "duplicate",
            fake_authority=authority,
            provider=provider,
            ticks=1,
        )
    second = launcher.run_registration(
        repository,
        path,
        case,
        directory / "second",
        fake_authority=authority,
        provider=provider,
        checkpoint=first_checkpoint,
        ticks=1,
    )
    assert second.world.tick == 2
    receipt_path = launcher._receipt_directory(repository, registration) / f"{case}.json"
    receipt_before = receipt_path.read_bytes()
    with pytest.raises(ValueError, match="CHECKPOINT_AUTHORITY_HEAD_MISMATCH"):
        launcher.run_registration(
            repository,
            path,
            case,
            directory / "stale",
            fake_authority=authority,
            provider=provider,
            checkpoint=first_checkpoint,
            ticks=1,
        )
    assert receipt_path.read_bytes() == receipt_before
    state = launcher.CaseAllocationP3.model_validate_json(
        (authority / "allocations" / f"{key}.json").read_bytes()
    )
    assert state.head.checkpoint_tick == 2
    assert len(list((authority / "allocations").glob("*.json"))) == 1
    assert second.checkpoint.run_budget.money_charged == 0


def test_live_preflight_refusal_precedes_credential_and_transport(repository, monkeypatch):
    registration, path = register(repository, purpose="smoke")
    launcher.initialize_authority(repository)
    launcher.enroll_registration(repository, path)
    touched = []

    def credential(path):
        touched.append("credential")
        raise AssertionError("must not read credential")

    monkeypatch.setattr(launcher, "_credential", credential)
    directory = repository / "runs/p3" / registration.registration_id
    with pytest.raises(ValueError, match="PUBLIC_PREFLIGHT_MODEL_DRIFT"):
        launcher.run_registration(
            repository,
            path,
            registration.cases[0].case_id,
            directory / "drift",
            live=True,
            dotenv=repository / ".env",
            fetch=public_documents(model="different-model").__getitem__,
        )

    def oversized(content, files):
        raise ValueError("INITIAL_CONTEXT_INPUT_LIMIT")

    monkeypatch.setattr(launcher, "initial_request_preflight", oversized)
    with pytest.raises(ValueError, match="INITIAL_CONTEXT_INPUT_LIMIT"):
        launcher.run_registration(
            repository,
            path,
            registration.cases[0].case_id,
            directory / "oversize",
            live=True,
            dotenv=repository / ".env",
            fetch=public_documents().__getitem__,
        )
    assert touched == []
    assert not (directory / "drift").exists() and not (directory / "oversize").exists()
    monkeypatch.setattr(launcher, "initial_request_preflight", lambda content, files: [])
    with pytest.raises(ValueError, match="DOTENV_CREDENTIAL_UNAVAILABLE"):
        launcher.run_registration(
            repository,
            path,
            registration.cases[0].case_id,
            directory / "missing-key",
            live=True,
            fetch=public_documents().__getitem__,
        )
    assert touched == [] and not (directory / "missing-key").exists()


def test_cli_exception_output_never_contains_credential_or_exception_message(monkeypatch, capsys):
    def failure(*args, **kwargs):
        raise RuntimeError("fixture-secret-value-that-must-not-appear")

    monkeypatch.setattr(launcher, "run_registration", failure)
    result = launcher.main(["run", "--registration", "missing", "--case", "case", "--out", "out"])
    captured = capsys.readouterr()
    assert result == 1
    assert "RuntimeError" in captured.err
    assert "fixture-secret" not in captured.err + captured.out


def test_live_and_offline_resume_modes_are_mutually_exclusive(capsys):
    with pytest.raises(SystemExit) as stopped:
        launcher.main(
            [
                "resume",
                "--registration",
                "registration.json",
                "--case",
                "case",
                "--out",
                "out",
                "--checkpoint",
                "checkpoint.json",
                "--live",
                "--offline-recovery",
            ]
        )
    assert stopped.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
