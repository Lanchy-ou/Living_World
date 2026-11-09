"""Canonical world/agent models: field shapes, strict integers, ranges, unknown fields."""

from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from living_island.agents.types import (
    DecisionOutcome,
    DecisionRecord,
    DecisionRequest,
    PolicyConfig,
    ResidentRuntimeState,
    ScriptFixture,
    build_intent_id,
    build_plan_id,
)
from living_island.world import facts, protocol, state
from living_island.world.facts import WorldEvent, format_event_id
from living_island.world.protocol import (
    ActionIntent,
    ActionPlan,
    ActionResult,
    BoundaryPerceptionDelivery,
    Perception,
    format_delivery_id,
)
from living_island.world.state import WorldState

HEX = "a" * 64


# ---------------------------------------------------------------- builders


def intent(i: int = 0, **kw: Any) -> dict[str, Any]:
    plan_id = build_plan_id("ella", 0)
    d: dict[str, Any] = {
        "intent_id": build_intent_id(plan_id, i),
        "plan_id": plan_id,
        "actor_id": "ella",
        "action_type": "wait",
        "target": None,
        "parameters": {},
        "reason": None,
    }
    d.update(kw)
    return d


def plan(intents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "plan_id": "ella:p000000",
        "actor_id": "ella",
        "created_at_tick": 0,
        "intents": intents if intents is not None else [intent()],
    }


def perception(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "schema_version": "0.1",
        "actor_id": "ella",
        "tick": 0,
        "own_condition": {
            "satiety": "good",
            "hydration": "strong",
            "stamina": "strong",
            "health": "strong",
        },
        "own_position": {"x": 12, "y": 32},
        "own_inventory": {"fruit_count": 0, "canteen_id": None, "canteen_servings": None},
        "visible_tiles": [{"position": {"x": 12, "y": 32}, "terrain": "grass"}],
        "visible_entities": [
            {
                "entity_id": "mia",
                "entity_type": "resident",
                "position": {"x": 14, "y": 32},
                "observable_signs": [],
                "fruit_band": None,
                "quantity": None,
            }
        ],
        "transient_sightings": [],
        "explored_static_tiles": [],
        "environmental_cues": [],
        "heard_utterances": [],
        "last_action_feedback": None,
    }
    d.update(kw)
    return d


def delivery(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "delivery_id": format_delivery_id("run", 0, "ella"),
        "actor_id": "ella",
        "observed_tick": 0,
        "perception": perception(),
        "decision_triggers": [],
    }
    d.update(kw)
    return d


def context() -> dict[str, Any]:
    return {
        "perception": perception(),
        "personality_profile": {"profile_id": "explorer", "values": []},
        "current_goals": [{"goal_id": "initial", "text": "explore", "priority": 0}],
        "recalled_episodes": [],
        "beliefs": [],
        "current_plan_summary": None,
    }


def record(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "record_schema_version": "0.1",
        "run_id": "run",
        "tick": 0,
        "actor_id": "ella",
        "decision_ordinal": 0,
        "policy_id": "random-v0",
        "effective_policy_id": "random-v0",
        "triggers": [],
        "request_sha256": HEX,
        "status": "ok",
        "error_kind": None,
        "plan": plan(),
        "substituted": False,
        "llm_call_id": None,
    }
    d.update(kw)
    return d


def world_state(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "schema_version": "0.1",
        "world_id": "w",
        "run_id": "run",
        "tick": 0,
        "config_hash": HEX,
        "map_hash": HEX,
        "static_map_ref": "default-island.map",
        "residents": [
            {
                "id": "ella",
                "position": {"x": 12, "y": 32},
                "alive": True,
                "satiety": 7500,
                "hydration": 8000,
                "stamina": 8500,
                "health": 10000,
                "fruit_count": 0,
            }
        ],
        "fruit_nodes": [
            {
                "id": "fruit_01",
                "position": {"x": 16, "y": 36},
                "stock": 1,
                "regrow_phase_offset_ticks": 0,
            }
        ],
        "cave": {"x": 13, "y": 32},
        "spring": {"x": 38, "y": 30},
        "cues": [{"id": "moss_east_01", "kind": "damp_moss", "position": {"x": 15, "y": 32}}],
        "ground_fruit": [],
        "lifetime_fruit_regrown": 0,
        "lifetime_fruit_consumed": 0,
        "unique_canteen": {
            "id": "canteen_01",
            "holder_id": "ella",
            "ground_position": None,
            "servings": 2,
        },
        "corpses": [],
        "dialogue_sessions": [],
        "active_actions": [
            {
                "intent": intent(),
                "tick_started": 0,
                "elapsed_ticks": 0,
                "remaining_ticks": 1,
                "route": None,
                "route_cursor": None,
                "pending_failure_code": None,
            }
        ],
        "explored_tiles_by_resident": [{"resident_id": "ella", "tile_indices": [1, 2]}],
        "exposure_receipts_by_resident": [
            {
                "resident_id": "ella",
                "entities": [
                    {"entity_id": "mia", "entity_type": "resident", "position": {"x": 1, "y": 1}}
                ],
                "cue_detail_seen": [{"cue_id": "moss_east_01", "detail_level": "distant"}],
            }
        ],
        "resolution_rng_state_uint32": 20261108,
        "next_event_seq_in_tick": 0,
        "event_log_cursor": 0,
        "rule_overrides": {},
    }
    d.update(kw)
    return d


def event(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run",
        "event_id": format_event_id("run", 3, 2),
        "tick": 3,
        "seq_in_tick": 2,
        "type": "resident_moved",
        "actor_id": "ella",
        "target_id": None,
        "intent_id": None,
        "llm_call_id": None,
        "caused_by_event_ids": [],
        "payload": {"from": {"x": 1, "y": 1}, "to": {"x": 1, "y": 2}, "step_cost_units": 1},
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------- ID builders


def test_plan_and_intent_ids() -> None:
    assert build_intent_id(build_plan_id("ella", 0), 0) == "ella:p000000:i0"
    assert build_intent_id(build_plan_id("ella", 1_000_000), 4) == "ella:p1000000:i4"
    with pytest.raises(ValueError):
        build_plan_id("ella", -1)


def test_event_and_delivery_ids() -> None:
    assert format_event_id("r", 1, 2) == "r:0000000001:000002"
    assert format_event_id("r", 10**10, 10**6) == "r:10000000000:1000000"
    assert format_delivery_id("r", 5, "mia") == "r:perception:0000000005:mia"


# ---------------------------------------------------------------- positives


def test_valid_models_parse() -> None:
    ActionPlan.model_validate(plan())
    BoundaryPerceptionDelivery.model_validate(delivery())
    DecisionRequest.model_validate(
        {"actor_id": "ella", "tick": 0, "decision_ordinal": 0, "triggers": [], "context": context()}
    )
    DecisionRecord.model_validate(record())
    WorldState.model_validate(world_state())
    ev = WorldEvent.model_validate(event())
    assert ev.model_dump(mode="json")["payload"]["from"] == {"x": 1, "y": 1}
    assert WorldEvent.model_validate_json(ev.model_dump_json()) == ev


def test_every_action_shape() -> None:
    tile = {"kind": "tile", "position": {"x": 1, "y": 1}}
    cases: list[tuple[str, Any, dict[str, Any]]] = [
        ("move_to", tile, {}),
        ("gather", {"kind": "entity", "id": "fruit_01"}, {}),
        ("eat", None, {}),
        ("drink", None, {"source": "spring"}),
        ("fill_canteen", {"kind": "entity", "id": "canteen_01"}, {}),
        ("rest", None, {}),
        ("sleep", None, {}),
        ("wait", None, {}),
        ("talk", {"kind": "resident", "id": "mia"}, {"speech_act": "statement", "text": "hi"}),
        ("give", {"kind": "resident", "id": "mia"}, {"item_type": "fruit", "quantity": 2}),
        ("pick_up", tile, {"item_type": "canteen", "quantity": 1}),
    ]
    for action, target, params in cases:
        ActionIntent.model_validate(intent(action_type=action, target=target, parameters=params))


def test_decision_outcome_union() -> None:
    adapter: TypeAdapter[Any] = TypeAdapter(DecisionOutcome)
    adapter.validate_python({"status": "ok", "policy_id": "random-v0", "plan": plan()})
    adapter.validate_python(
        {"status": "error", "policy_id": "x", "error_kind": "INVALID_PLAN", "detail": ""}
    )
    adapter.validate_python(
        {"status": "replayed", "policy_id": "recorded-v0", "source_record": record()}
    )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"status": "replayed", "policy_id": "random-v0", "source_record": record()}
        )


# ---------------------------------------------------------------- negatives


@pytest.mark.parametrize(
    ("action", "target", "params"),
    [
        ("wait", None, {"source": "spring"}),
        ("move_to", None, {}),
        ("gather", {"kind": "tile", "position": {"x": 0, "y": 0}}, {}),
        ("talk", {"kind": "resident", "id": "mia"}, {"speech_act": "request", "text": ""}),
        (
            "talk",
            {"kind": "resident", "id": "mia"},
            {"speech_act": "statement", "text": "", "in_reply_to": "e"},
        ),
        ("give", {"kind": "resident", "id": "mia"}, {"item_type": "canteen", "quantity": 2}),
        ("give", {"kind": "resident", "id": "mia"}, {"item_type": "fruit", "quantity": 0}),
        ("drink", None, {"source": "sea"}),
        ("fly", None, {}),
    ],
)
def test_bad_intent_shape(action: str, target: Any, params: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ActionIntent.model_validate(intent(action_type=action, target=target, parameters=params))


def test_plan_rules() -> None:
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(plan([]))
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(plan([intent(actor_id="mia")]))
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(plan([intent(0), intent(0)]))


@pytest.mark.parametrize(
    "status_fields",
    [
        {"status": "success", "failure_code": "DEAD", "interruption_reason": None},
        {"status": "failure", "failure_code": None, "interruption_reason": None},
        {"status": "interrupted", "failure_code": None, "interruption_reason": None},
        {"status": "failure", "failure_code": "BLOCKED", "interruption_reason": None},
    ],
)
def test_result_status_rules(status_fields: dict[str, Any]) -> None:
    feedback = {"intent_id": "i", "visible_effects": [], **status_fields}
    with pytest.raises(ValidationError):
        ActionResult.model_validate(
            {
                "intent_id": "i",
                "actor_id": "ella",
                "tick_started": 0,
                "tick_finished": 1,
                "state_delta": [],
                "visible_feedback": feedback,
                "event_ids": [],
                **status_fields,
            }
        )


@pytest.mark.parametrize(
    "mutation",
    [
        {"tick": -1},
        {"tick": 1.0},
        {"tick": "1"},
        {"tick": True},
        {"own_position": {"x": -1, "y": 0}},
        {"own_inventory": {"fruit_count": 0, "canteen_id": "c", "canteen_servings": None}},
        {"surprise": 1},
        {"visible_entities": [perception()["visible_entities"][0]] * 2},
        {
            "visible_entities": [
                {**perception()["visible_entities"][0], "entity_id": "ella"},
            ]
        },
        {
            "visible_entities": [
                {**perception()["visible_entities"][0], "fruit_band": "few"},
            ]
        },
    ],
)
def test_bad_perception(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Perception.model_validate(perception(**mutation))


@pytest.mark.parametrize(
    "mutation",
    [
        {"decision_triggers": ["NEW_SIGHT", "ACTION_FAILED"]},
        {"decision_triggers": ["WOKE", "WOKE"]},
        {"delivery_id": "run:perception:0:ella"},
        {"observed_tick": 1},
    ],
)
def test_bad_delivery(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        BoundaryPerceptionDelivery.model_validate(delivery(**mutation))


@pytest.mark.parametrize(
    "mutation",
    [
        {"resolution_rng_state_uint32": 0},
        {"resolution_rng_state_uint32": 2**32},
        {"rule_overrides": {"x": 1}},
        {"tick": 1.5},
        {"residents": world_state()["residents"] * 2},
        {
            "unique_canteen": {
                "id": "c",
                "holder_id": "ella",
                "ground_position": {"x": 0, "y": 0},
                "servings": 0,
            }
        },
        {"explored_tiles_by_resident": [{"resident_id": "ella", "tile_indices": [2, 1]}]},
        {"ground_fruit": [{"position": {"x": 0, "y": 0}, "quantity": 0}]},
    ],
)
def test_bad_world_state(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        WorldState.model_validate(world_state(**mutation))


@pytest.mark.parametrize(
    "mutation",
    [
        {"event_id": "run:3:2"},
        {"type": "fruit_gathered"},
        {"payload": {"from": {"x": 1, "y": 1}, "to": {"x": 1, "y": 2}, "step_cost_units": 1.0}},
        {"payload": {"from": {"x": 1, "y": 1}, "to": {"x": 1, "y": 2}, "extra": 1}},
        {"caused_by_event_ids": [format_event_id("run", 3, 2)]},
        {"type": "teleported"},
    ],
)
def test_bad_event(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        WorldEvent.model_validate(event(**mutation))


@pytest.mark.parametrize(
    "mutation",
    [
        {"plan": {**plan(), "plan_id": "ella:p1"}},
        {"status": "error", "error_kind": None, "substituted": True},
        {
            "status": "error",
            "error_kind": "INVALID_PLAN",
            "substituted": True,
            "effective_policy_id": "random-v0",
        },
        {"request_sha256": "ABC"},
        {"record_schema_version": "0.2"},
    ],
)
def test_bad_record(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(record(**mutation))


def test_error_record_with_wait_substitute() -> None:
    DecisionRecord.model_validate(
        record(
            status="error",
            error_kind="INVALID_PLAN",
            substituted=True,
            effective_policy_id="sim-fallback-wait",
        )
    )


def test_policy_config_and_runtime_state() -> None:
    base = {"seed": 1, "max_plan_actions": 5, "map_width": 64, "map_height": 64}
    scripted = PolicyConfig.model_validate(
        {**base, "policy_id": "scripted-v0", "script_sha256": HEX, "source_trace_sha256": None}
    )
    with pytest.raises(ValidationError):
        PolicyConfig.model_validate(
            {**base, "policy_id": "random-v0", "script_sha256": HEX, "source_trace_sha256": None}
        )
    with pytest.raises(ValidationError):
        PolicyConfig.model_validate(
            {
                **base,
                "seed": 0,
                "policy_id": "random-v0",
                "script_sha256": None,
                "source_trace_sha256": None,
            }
        )
    state_d = {
        "actor_id": "ella",
        "policy_config": scripted,
        "next_decision_ordinal": 0,
        "latest_perception_tick": -1,
    }
    ResidentRuntimeState.model_validate({**state_d, "policy_state": {"cursor": 0}})
    for bad in ({}, {"cursor": -1}, {"cursor": 0, "x": 1}, {"cursor": True}):
        with pytest.raises(ValidationError):
            ResidentRuntimeState.model_validate({**state_d, "policy_state": bad})
    with pytest.raises(ValidationError):
        ResidentRuntimeState.model_validate(
            {**state_d, "policy_state": {"cursor": 0}, "latest_perception_tick": -2}
        )


def test_script_fixture() -> None:
    tmpl = {"action_type": "wait", "target": None, "parameters": {}, "reason": None}
    actor = {"actor_id": "ella", "on_exhausted": "wait", "plans": [[tmpl]]}
    ScriptFixture.model_validate({"script_schema_version": "0.1", "actors": [actor]})
    bad_cases: list[dict[str, Any]] = [
        {"script_schema_version": "0.1", "actors": [actor, actor]},
        {"script_schema_version": "0.1", "actors": [{**actor, "plans": [[]]}]},
        {
            "script_schema_version": "0.1",
            "actors": [{**actor, "plans": [[{k: v for k, v in tmpl.items() if k != "reason"}]]}],
        },
    ]
    for bad in bad_cases:
        with pytest.raises(ValidationError):
            ScriptFixture.model_validate(bad)


# ---------------------------------------------------------------- global properties


def _models(*modules: Any) -> list[type[BaseModel]]:
    out = []
    for module in modules:
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__ == (module.__name__)
            ):
                out.append(value)
    return out


def test_every_model_forbids_extra_and_is_strict() -> None:
    from living_island.agents import types as agent_types
    from living_island.contract import save
    from living_island.world import content, ports

    models = _models(protocol, state, facts, content, ports, agent_types, save)
    assert len(models) > 60
    for model in models:
        assert model.model_config.get("extra") == "forbid", model
        assert model.model_config.get("strict") is True, model


def test_every_event_type_has_a_payload_model() -> None:
    from typing import get_args

    assert set(get_args(facts.EventType)) == set(facts.PAYLOAD_MODEL_BY_TYPE)
    assert len(facts.PAYLOAD_MODEL_BY_TYPE) == 25


def test_vocabularies_match_contract() -> None:
    from typing import get_args

    assert get_args(protocol.DecisionTrigger) == protocol.DECISION_TRIGGERS
    assert len(protocol.FAILURE_CODES) == 17
    assert get_args(protocol.FailureCode) == protocol.FAILURE_CODES
    assert len(protocol.ACTION_TYPES) == 11
    assert "".join(protocol.TERRAIN_BY_SYMBOL) == "~.,W^SCFM"


# ---------------------------------------------------------------- rework round 1

TALK_PARAMS = {
    "statement": {"speech_act": "statement", "text": "hi"},
    "request": {
        "speech_act": "request",
        "text": "fruit?",
        "request": {"item_type": "fruit", "quantity": 1},
    },
    "accept": {"speech_act": "accept", "text": "ok", "in_reply_to": "run:00000003:0002"},
    "refuse": {"speech_act": "refuse", "text": "no", "in_reply_to": "run:00000003:0002"},
}


def talk_intent(act: str) -> dict[str, Any]:
    return intent(
        action_type="talk",
        target={"kind": "resident", "id": "mia"},
        parameters=TALK_PARAMS[act],
    )


@pytest.mark.parametrize("act", list(TALK_PARAMS))
def test_talk_canonical_round_trip(act: str) -> None:
    rec = DecisionRecord.model_validate(record(plan=plan([talk_intent(act)])))
    dumped = rec.model_dump(mode="json")
    params = dumped["plan"]["intents"][0]["parameters"]
    assert params == TALK_PARAMS[act]  # absent keys omitted, never null
    assert DecisionRecord.model_validate(dumped) == rec
    assert DecisionRecord.model_validate_json(rec.model_dump_json()) == rec


@pytest.mark.parametrize(
    "params",
    [
        {"speech_act": "statement", "text": "hi", "request": None},
        {"speech_act": "statement", "text": "hi", "in_reply_to": None},
        {**TALK_PARAMS["request"], "in_reply_to": None},
        {**TALK_PARAMS["accept"], "request": None},
        {"speech_act": "statement", "text": "hi", "in_reply_to": "x"},
        {"speech_act": "refuse", "text": "no", "request": {"item_type": "fruit", "quantity": 1}},
    ],
)
def test_talk_optional_keys_only_on_their_acts(params: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        protocol.TalkParameters.model_validate(params)


def test_resident_moved_wire_name_is_from_only() -> None:
    ev = WorldEvent.model_validate(event())
    assert "from" in ev.model_dump(mode="json")["payload"]
    bad = event(payload={"from_": {"x": 1, "y": 1}, "to": {"x": 1, "y": 2}, "step_cost_units": 1})
    with pytest.raises(ValidationError):
        WorldEvent.model_validate(bad)


def test_payload_action_type_and_failure_code_are_strings() -> None:
    p = facts.ActionFailedPayload.model_validate(
        {"action_type": "future_action", "failure_code": "FUTURE_CODE"}
    )
    assert (p.action_type, p.failure_code) == ("future_action", "FUTURE_CODE")


@pytest.mark.parametrize("bad_type", [[], {}, 3, None])
def test_unhashable_event_type_is_validation_error(bad_type: Any) -> None:
    with pytest.raises(ValidationError):
        WorldEvent.model_validate(event(type=bad_type))


def request(**kw: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "actor_id": "ella",
        "tick": 0,
        "decision_ordinal": 0,
        "triggers": [],
        "context": context(),
    }
    d.update(kw)
    return d


def test_initial_request_may_have_empty_triggers() -> None:
    DecisionRequest.model_validate(request())
    DecisionRequest.model_validate(request(decision_ordinal=1, triggers=["NEW_SIGHT"]))


@pytest.mark.parametrize("mutation", [{"decision_ordinal": 1}])
def test_empty_triggers_rejected_after_initial_request(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(request(**mutation))


def test_empty_triggers_rejected_at_later_tick() -> None:
    ctx = context()
    ctx["perception"] = perception(tick=5)
    with pytest.raises(ValidationError):
        DecisionRequest.model_validate(request(tick=5, context=ctx))


def ordinal_one_plan() -> dict[str, Any]:
    pid = build_plan_id("ella", 1)
    return {**plan([intent(intent_id=build_intent_id(pid, 0), plan_id=pid)]), "plan_id": pid}


def test_record_ordinal_one_with_trigger_valid() -> None:
    DecisionRecord.model_validate(
        record(decision_ordinal=1, plan=ordinal_one_plan(), triggers=["NEW_SIGHT"])
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"decision_ordinal": 1, "plan": ordinal_one_plan()},
        {"llm_call_id": "future-call"},
    ],
)
def test_record_p1_boundary_rejected(mutation: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DecisionRecord.model_validate(record(**mutation))
