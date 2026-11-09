"""SavePackage envelope, frozen ports and one import example per consumer (M1)."""

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_contract_models import delivery, perception
from test_contract_models import world_state as world_state_dict

from living_island.agents.types import PolicyConfig, ResidentRuntimeState
from living_island.contract.save import SavePackage
from living_island.world import ports
from living_island.world.protocol import format_delivery_id

SRC = Path(__file__).resolve().parents[2] / "src" / "living_island"


def runtime(ordinal: int, latest: int, actor_id: str = "ella") -> dict[str, Any]:
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
        actor_id=actor_id,
        policy_config=cfg,
        next_decision_ordinal=ordinal,
        policy_state={},
        latest_perception_tick=latest,
    ).model_dump()


def packet(tick: int, actor_id: str = "ella", delivery_id: str | None = None) -> dict[str, Any]:
    return delivery(
        delivery_id=delivery_id or format_delivery_id("run", tick, actor_id),
        actor_id=actor_id,
        observed_tick=tick,
        perception=perception(tick=tick, actor_id=actor_id),
    )


def save(
    tick: int = 0,
    cursor: int = -1,
    latest: int | None = None,
    ordinal: int = 0,
    alive: bool = True,
    packets: list[dict[str, Any]] | None = None,
    cursors: list[dict[str, Any]] | None = None,
    **kw: Any,
) -> dict[str, Any]:
    """Pre-ingest checkpoint for Ella at ``tick`` (defaults: zero-decision initialization)."""
    world = world_state_dict(tick=tick)
    world["residents"][0]["alive"] = alive
    if cursors is None:
        cursors = [{"actor_id": "ella", "last_observed_tick": cursor}]
    if packets is None:
        packets = [packet(tick)] if alive else []
    d: dict[str, Any] = {
        "save_schema_version": "0.1",
        "world": world,
        "agent_state": {
            "profiles": [],
            "goal_states": [],
            "personal_memories": [],
            "relationships": [],
            "queued_plans": [],
            "deferred_decision_triggers": [],
            "delivered_perception_ticks": cursors,
            "runtime_states": [runtime(ordinal, cursor if latest is None else latest)],
        },
        "event_cursor": 0,
        "llm_record_cursor": 0,
        "decision_record_cursor": ordinal,
        "pending_perception_deliveries": packets,
        "canonical_config_hash": "a" * 64,
        "canonical_map_hash": "a" * 64,
    }
    d.update(kw)
    return d


# Valid later checkpoint: tick 4, ticks 0..3 ingested, two committed decisions.
LATER: dict[str, Any] = {"tick": 4, "cursor": 3, "ordinal": 2}
PREFIX_ONLY_ID = "run:perception:other:perception:0000000000:ella"


def test_save_package_initialization_valid() -> None:
    pkg = SavePackage.model_validate(save())
    assert pkg.decision_record_cursor == 0
    assert pkg.agent_state.delivered_perception_ticks[0].last_observed_tick == -1


def test_save_package_later_checkpoint_valid() -> None:
    SavePackage.model_validate(save(**LATER))


def test_save_package_dead_actor_without_packet_valid() -> None:
    SavePackage.model_validate(save(tick=4, cursor=2, ordinal=1, alive=False))


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"event_cursor": 1}, id="S1-event-cursor"),
        pytest.param({"canonical_map_hash": "b" * 64}, id="S2-hash"),
        pytest.param({"decision_record_cursor": 1}, id="S4-ordinal-sum"),
        pytest.param({"llm_record_cursor": -1}, id="negative-llm-cursor"),
        pytest.param({"extra": 1}, id="extra-field"),
        pytest.param({"ordinal": 3}, id="S5-decisions-before-first-ingest"),
        pytest.param({"cursors": []}, id="S6-missing-cursor"),
        pytest.param(
            {"cursors": [{"actor_id": "zed", "last_observed_tick": -1}]}, id="S6-foreign-cursor"
        ),
        pytest.param(
            {
                "cursors": [
                    {"actor_id": "ella", "last_observed_tick": -1},
                    {"actor_id": "zed", "last_observed_tick": -1},
                ]
            },
            id="S6-extra-foreign-cursor",
        ),
        pytest.param({"latest": 5}, id="S7-runtime-cursor-future"),
        pytest.param({**LATER, "latest": 2}, id="S7-runtime-cursor-behind"),
        pytest.param({"cursor": 0}, id="S8-tick-zero-already-acknowledged"),
        pytest.param({**LATER, "cursor": 4}, id="S8-later-already-acknowledged"),
        pytest.param({**LATER, "cursor": -1}, id="S8-tick-four-cursor-minus-one"),
        pytest.param({**LATER, "cursor": 2}, id="S8-gap"),
        pytest.param({"cursor": 7}, id="S8-future-cursor"),
        pytest.param(
            {"tick": 4, "cursor": 4, "ordinal": 1, "alive": False}, id="S8-dead-future-cursor"
        ),
        pytest.param({"packets": [packet(0), packet(0)]}, id="S9-duplicate-packet"),
        pytest.param({"packets": []}, id="S10-missing-packet"),
        pytest.param({"packets": [packet(0), packet(0, "zed")]}, id="S10-extra-actor-packet"),
        pytest.param({"alive": False, "packets": [packet(0)]}, id="S10-dead-actor-packet"),
        pytest.param({"packets": [packet(1)]}, id="S11-wrong-tick-packet"),
        pytest.param(
            {"packets": [packet(0, delivery_id=format_delivery_id("other", 0, "ella"))]},
            id="S11-wrong-run-packet",
        ),
        pytest.param(
            {"packets": [packet(0, delivery_id=PREFIX_ONLY_ID)]}, id="S11-prefix-only-delivery-id"
        ),
    ],
)
def test_save_package_invalid(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SavePackage.model_validate(save(**mutation))


def test_save_package_missing_runtime_state() -> None:  # S3
    data = save()
    data["agent_state"]["runtime_states"] = []
    with pytest.raises(ValidationError):
        SavePackage.model_validate(data)


def test_receipt_baseline_is_immutable() -> None:
    from living_island.world.state import ExposureReceipts

    receipts = ExposureReceipts.model_validate(
        world_state_dict()["exposure_receipts_by_resident"][0]
    )
    acc = ports.ObservationAccumulator(0, (receipts,))
    view = acc.receipt_baseline[0]
    view.resident_id = "altered"
    view.entities.clear()
    receipts.resident_id = "caller-altered"
    again = acc.receipt_baseline[0]
    assert again.resident_id == "ella"
    assert len(again.entities) == 1
    assert acc.receipt_baseline[0] is not again


def test_port_signatures_frozen() -> None:
    def params(fn: Any) -> list[str]:
        return list(inspect.signature(fn).parameters)

    assert params(ports.create_engine) == ["content", "restored_world"]
    assert params(ports.begin_observation_tick) == ["state", "completed_tick", "content"]
    assert params(ports.observe_step) == ["acc", "state", "actor_id", "position", "step_index"]
    assert params(ports.finish_observation_tick) == ["acc", "state"]
    hints = inspect.get_annotations(ports.WorldEngine.append_fact)
    assert hints["caused_by_event_ids"] == "list[str]"
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
