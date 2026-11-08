"""SavePackage envelope, frozen ports and one import example per consumer (M1)."""

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_contract_models import world_state as world_state_dict

from living_island.agents.types import PolicyConfig, ResidentRuntimeState
from living_island.contract.save import SavePackage
from living_island.world import ports

SRC = Path(__file__).resolve().parents[2] / "src" / "living_island"


def runtime(ordinal: int) -> ResidentRuntimeState:
    cfg = PolicyConfig(
        policy_id="random-v0",
        seed=1,
        max_plan_actions=5,
        map_width=64,
        map_height=64,
        script_sha256=None,
        source_trace_sha256=None,
    )
    return ResidentRuntimeState(
        actor_id="ella",
        policy_config=cfg,
        next_decision_ordinal=ordinal,
        policy_state={},
        latest_perception_tick=-1,
    )


def save(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "save_schema_version": "0.1",
        "world": world_state_dict(),
        "agent_state": {
            "profiles": [],
            "goal_states": [],
            "personal_memories": [],
            "relationships": [],
            "queued_plans": [],
            "deferred_decision_triggers": [],
            "delivered_perception_ticks": [{"actor_id": "ella", "last_observed_tick": -1}],
            "runtime_states": [runtime(3)],
        },
        "event_cursor": 0,
        "llm_record_cursor": 0,
        "decision_record_cursor": 3,
        "pending_perception_deliveries": [],
        "canonical_config_hash": "a" * 64,
        "canonical_map_hash": "a" * 64,
    }
    d.update(kw)
    return d


def test_save_package_valid() -> None:
    SavePackage.model_validate(save())


@pytest.mark.parametrize(
    "mutation",
    [
        {"decision_record_cursor": 2},
        {"event_cursor": 1},
        {"canonical_map_hash": "b" * 64},
        {"llm_record_cursor": -1},
        {"extra": 1},
    ],
)
def test_save_package_invalid(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SavePackage.model_validate(save(**mutation))


def test_port_signatures_frozen() -> None:
    def params(fn: Any) -> list[str]:
        return list(inspect.signature(fn).parameters)

    assert params(ports.create_engine) == ["content", "restored_world"]
    assert params(ports.begin_observation_tick) == ["state", "completed_tick"]
    assert params(ports.observe_step) == ["acc", "state", "actor_id", "position", "step_index"]
    assert params(ports.finish_observation_tick) == ["acc", "state"]
    assert params(ports.WorldEngine.append_fact) == [
        "self",
        "type",
        "actor_id",
        "target_id",
        "intent_id",
        "llm_call_id",
        "caused_by_event_ids",
        "payload",
    ]
    for name in ("initial_commit", "begin_tick", "start_intent", "advance_tick"):
        assert hasattr(ports.WorldEngine, name)
    assert set(ports.ObservationBatch.model_fields) == {
        "physical_samples_by_actor",
        "new_static_tiles_by_actor",
        "exposure_receipt_updates",
        "new_sight_actor_ids",
    }
    assert set(ports.WorldTickCommit.model_fields) == {"snapshot", "events", "pending_deliveries"}


def test_observation_sample_omits_hearing_and_feedback() -> None:
    from living_island.world.protocol import Perception

    assert set(Perception.model_fields) - set(ports.ObservationSample.model_fields) == {
        "heard_utterances",
        "last_action_feedback",
    }


def test_port_bodies_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        ports.create_engine(None, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------- consumer imports


def test_consumer_import_examples() -> None:
    from living_island.agents.base import Policy, ResidentRuntime  # agents
    from living_island.contract.save import SavePackage as Save  # contract
    from living_island.events import WorldEvent  # events
    from living_island.persistence.content import load_world_content  # persistence
    from living_island.sim.ports import BoundaryObserver  # sim
    from living_island.world.facts import WorldEvent as CanonicalEvent

    assert WorldEvent is CanonicalEvent  # re-export, not a copy
    assert all((Policy, ResidentRuntime, Save, load_world_content, BoundaryObserver))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


@pytest.mark.parametrize(
    ("package", "forbidden"),
    [
        ("world", ("living_island.contract", "living_island.events", "living_island.agents")),
        (
            "agents",
            (
                "living_island.contract",
                "living_island.world.state",
                "living_island.world.facts",
                "living_island.persistence",
            ),
        ),
    ],
)
def test_no_back_imports(package: str, forbidden: tuple[str, ...]) -> None:
    for path in (SRC / package).rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith(forbidden), (path, name)


def test_save_package_not_exported_to_ts() -> None:
    import living_island.contract as contract

    assert "SavePackage" not in contract.__all__
