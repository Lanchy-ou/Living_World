"""Frozen WAP shapes, canonical ordering, and model-schema drift checks."""

import json
from copy import deepcopy
from hashlib import sha256
from typing import get_args

import pytest
from pydantic import ValidationError

from living_island.world.v2 import protocol as wap

ACTOR = "résident"
TURN_ID = f"{ACTOR}:t000004"
INTENT_ID = f"{TURN_ID}:a"
COORD = {"x": 4, "y": 2}
TILE = {"kind": "tile", "position": COORD}
ENTITY = {"kind": "entity", "id": "e1"}
RESIDENT = {"kind": "resident", "id": "r2"}
NAMED = {"kind": "item", "id": "e1"}
HELD = {"kind": "held", "archetype_id": "fruit"}
WAIT = {"action": "wait", "verb": None, "target": None, "params": {}}
SLEEP = {"action": "act", "verb": "sleep", "target": None, "params": {"duration_ticks": 6}}
VERBS = (
    wap.EnabledVerb(
        id="sleep",
        target_kinds=(),
        params=(wap.VerbParameter(name="duration_ticks", min=6, max=54),),
    ),
    wap.EnabledVerb(id="gather", target_kinds=("entity", "tile"), params=()),
)


def turn(fields=WAIT, **overrides):
    return {
        "schema_version": wap.SCHEMA_VERSION,
        "turn_id": TURN_ID,
        "actor_id": ACTOR,
        "observed_tick": 14,
        "action": {
            "kind": "intent",
            "intent": {
                "intent_id": INTENT_ID,
                "turn_id": TURN_ID,
                "actor_id": ACTOR,
                "reason": None,
                "instruments": [],
                "inputs": [],
                **fields,
            },
        },
        "utterance": None,
        **overrides,
    }


def validated(data, *, running=False, model=wap.TurnSubmission):
    return wap.validate_turn_shape(model, data, enabled_verbs=VERBS, has_running_action=running)


def assert_roundtrip(value):
    encoded = wap.canonical_bytes(value)
    assert wap.canonical_bytes(wap.decode(type(value), encoded)) == encoded
    return json.loads(encoded)


@pytest.mark.parametrize(
    ("action", "target", "params"),
    [
        ("move_to", TILE, {}),
        ("give", RESIDENT, {"item": NAMED, "quantity": 1}),
        ("pick_up", ENTITY, {"quantity": 2}),
        ("pick_up", TILE, {"archetype_id": "fruit", "quantity": 3}),
        ("drop", TILE, {"item": HELD, "quantity": 1}),
        ("drop", ENTITY, {"item": NAMED, "quantity": 1}),
        ("wait", None, {}),
        ("inspect", ENTITY, {}),
        ("contribute", ENTITY, {}),
    ],
)
def test_kernel_roundtrip(action, target, params):
    parsed = validated(turn({"action": action, "target": target, "params": params, "verb": None}))
    assert_roundtrip(parsed)


@pytest.mark.parametrize(
    "fields",
    [
        {"action": "unknown"},
        {"target": ENTITY},
        {"verb": "sleep"},
        {"instruments": [NAMED]},
        {"params": {"unknown": 1}},
        {"action": "give", "target": RESIDENT, "params": {"item": HELD, "quantity": 0}},
        {"action": "give", "target": RESIDENT, "params": {"item": NAMED, "quantity": True}},
        {"action": "give", "target": RESIDENT, "params": {"item": NAMED, "quantity": 1.0}},
        {"action": "give", "target": ENTITY, "params": {"item": NAMED, "quantity": 1}},
        {"action": "pick_up", "target": ENTITY, "params": {"archetype_id": "fruit", "quantity": 1}},
        {"action": "pick_up", "target": TILE, "params": {"quantity": 1}},
        {"action": "act", "verb": None},
        {"action": "act", "verb": "unknown"},
        {"action": "act", "verb": "gather", "target": RESIDENT},
        {"action": "act", "verb": "gather", "target": None},
        {"action": "act", "verb": "gather", "target": TILE, "params": {"extra": 1}},
        {"action": "act", "verb": "gather", "target": TILE, "instruments": [NAMED, NAMED]},
        {
            "action": "act",
            "verb": "gather",
            "target": TILE,
            "instruments": [NAMED],
            "inputs": [{"item": NAMED, "quantity": 2}],
        },
        {"intent_id": f"{ACTOR}:t000004"},
        {"turn_id": f"{ACTOR}:t00004"},
        {"turn_id": f"{ACTOR}:t０００００４"},
    ],
)
def test_invalid_action_shape_classifies_entire_turn(fields):
    with pytest.raises(wap.InvalidTurn) as error:
        validated(turn({**WAIT, **fields}))
    assert error.value.code == "INVALID_TURN"


@pytest.mark.parametrize("duration", [5, 55, 6.0, True, "6", None])
def test_sleep_refuses_wrong_type_and_out_of_range(duration):
    with pytest.raises(wap.InvalidTurn):
        validated(turn({**SLEEP, "params": {"duration_ticks": duration}}))


@pytest.mark.parametrize("duration", [6, 54])
def test_sleep_accepts_inclusive_bounds(duration):
    assert_roundtrip(validated(turn({**SLEEP, "params": {"duration_ticks": duration}})))


def test_continue_requires_running_action_and_turn_ids_allow_large_ordinals():
    continued = turn(turn_id=f"{ACTOR}:t1000000", action={"kind": "continue"})
    assert_roundtrip(validated(continued, running=True))
    with pytest.raises(wap.InvalidTurn, match="running action"):
        validated(continued)
    with pytest.raises(wap.InvalidTurn):
        validated({"action": continued["action"], "utterance": None}, model=wap.ModelTurn)


def test_item_resolution_order_stays_authored_and_held_choices_are_not_named_ids():
    fields = {
        "action": "act",
        "verb": "gather",
        "target": TILE,
        "params": {},
        "instruments": [HELD, NAMED],
        "inputs": [{"item": HELD, "quantity": 2}, {"item": HELD, "quantity": 1}],
    }
    assert (
        assert_roundtrip(validated(turn(fields)))["action"]["intent"]["inputs"] == fields["inputs"]
    )
    assert assert_roundtrip(validated(turn(fields)))["action"]["intent"]["instruments"] == [
        HELD,
        NAMED,
    ]


def utterance(**fields):
    return {
        "speech_act": "statement",
        "addressee_id": None,
        "text": "À demain",
        "terms": None,
        "in_reply_to": None,
        **fields,
    }


def terms(what, due_tick=None):
    return {"promisor_id": ACTOR, "promisee_id": "r2", "what": what, "due_tick": due_tick}


@pytest.mark.parametrize(
    "proposal",
    [
        terms({"kind": "give_item", "item": {"item_id": "e1"}}),
        terms({"kind": "give_item", "item": {"archetype_id": "fruit", "quantity": 1}}),
        terms({"kind": "return_item", "item_id": "e1"}),
        terms({"kind": "be_at", "position": COORD}, 15),
        terms({"kind": "contribute", "process_id": "e3", "work_ticks": 2}, 16),
    ],
)
def test_proposal_terms_roundtrip(proposal):
    speech = utterance(speech_act="propose", addressee_id="r2", terms=proposal)
    assert_roundtrip(validated(turn(utterance=speech)))


@pytest.mark.parametrize("act", ["accept", "refuse"])
def test_reply_roundtrip(act):
    assert_roundtrip(
        validated(
            turn(utterance=utterance(speech_act=act, addressee_id="r2", in_reply_to="proposal"))
        )
    )


@pytest.mark.parametrize(
    "speech",
    [
        utterance(speech_act="unknown"),
        utterance(speech_act="propose", addressee_id="r2"),
        utterance(speech_act="propose", addressee_id="r2", terms=terms({"kind": "be_at"})),
        utterance(
            speech_act="propose",
            addressee_id="r2",
            terms=terms({"kind": "be_at", "position": COORD}),
        ),
        utterance(
            speech_act="propose",
            addressee_id="r2",
            terms=terms({"kind": "give_item", "item": {"quantity": 1}}),
        ),
        utterance(
            speech_act="propose",
            addressee_id="r2",
            terms=terms({"kind": "give_item", "item": {"archetype_id": "fruit", "quantity": -1}}),
        ),
        utterance(
            speech_act="propose",
            addressee_id="r2",
            terms=terms({"kind": "contribute", "process_id": "e3", "work_ticks": 0}),
        ),
        utterance(speech_act="propose", addressee_id="r2", terms=terms({"kind": "unknown"})),
        utterance(speech_act="accept", addressee_id="r2"),
        utterance(speech_act="refuse", in_reply_to="e1"),
        utterance(in_reply_to="e1"),
    ],
)
def test_bad_utterance_invalidates_whole_turn(speech):
    with pytest.raises(wap.InvalidTurn):
        validated(turn(utterance=speech))


def item_use(entity_id, role):
    return wap.ItemUse(
        entity_id=entity_id,
        role=role,
        archetype_id="fruit",
        material_id=None,
        quantity=1,
        descriptors=[
            wap.Descriptor(property_id="quality", value="ripe"),
            wap.Descriptor(property_id="colour", value="rouge"),
        ],
    )


def feedback(index=4, **fields):
    return wap.ActionFeedback(
        **{
            "intent_id": f"{ACTOR}:t{index:06d}:a",
            "status": "done",
            "failure_code": None,
            "stop_reason": None,
            "phenomena": ["z", "a", "z"],
            "inspected": None,
            "start_target": None,
            "items_used": [],
            **fields,
        }
    )


@pytest.mark.parametrize(
    "outcome_fields",
    [
        {"outcome": "success"},
        {
            "outcome": "failure",
            "failure_code": "NO_ITEM",
            "visible_feedback": feedback(status="failed", failure_code="NO_ITEM"),
        },
        {
            "outcome": "stopped",
            "stop": wap.ActorStop(by="actor"),
            "visible_feedback": feedback(status="stopped", stop_reason="own_choice"),
        },
        {
            "outcome": "stopped",
            "stop": wap.WorldStop(by="world", reason="WOKEN"),
            "visible_feedback": feedback(status="stopped", stop_reason="WOKEN"),
        },
        *[
            {
                "outcome": "settled",
                "settlement": wap.Settlement(
                    rule_id=None if kind == "unmatched" else "rule1",
                    kind=kind,
                    at="completion",
                    failed_check="slot" if kind == "unmet" else None,
                ),
            }
            for kind in ("applied", "unmatched", "unmet", "chance_failed")
        ],
    ],
)
def test_result_roundtrip(outcome_fields):
    result = wap.ActionResult(
        **{
            "intent_id": INTENT_ID,
            "actor_id": ACTOR,
            "tick_started": 14,
            "tick_finished": 15,
            "failure_code": None,
            "stop": None,
            "settlement": None,
            "state_delta": [wap.StateDelta(path="x", before=wap.Coord(**COORD), after=True)],
            "visible_feedback": feedback(),
            "event_ids": ["event2", "event1"],
            **outcome_fields,
        }
    )
    encoded = assert_roundtrip(result)
    assert encoded["event_ids"] == ["event1", "event2"]
    assert encoded["state_delta"][0]["after"] is True


def observed(phase, **fields):
    return wap.ObservedAction(
        **{
            "actor_id": ACTOR,
            "intent_id": INTENT_ID,
            "tick": 14,
            "phase": phase,
            "action": "give",
            "verb": None,
            "target": RESIDENT,
            "start_target": None,
            "received_items": [],
            "visible_items": [item_use("z", "input"), item_use("y", "instrument")],
            "phenomena": ["z", "a"],
            **fields,
        }
    )


@pytest.fixture
def perception():
    view = {
        "entity_id": "fruit",
        "archetype_id": "fruit",
        "material_id": None,
        "kind": "item",
        "position": COORD,
        "quantity": 1,
        "descriptors": [],
        "observable_signs": [],
    }
    return wap.Perception(
        schema_version=wap.SCHEMA_VERSION,
        actor_id="r2",
        tick=14,
        awareness="awake",
        own_position=wap.Coord(**COORD),
        needs=[
            wap.NeedView(need_id="thirst", band="critical"),
            wap.NeedView(need_id="hunger", band="good"),
        ],
        inventory=[
            wap.ItemView(
                entity_id=eid, archetype_id="fruit", material_id=None, quantity=1, descriptors=[]
            )
            for eid in ("z", "a")
        ],
        visible_tiles=[
            wap.TileView(position=wap.Coord(x=0, y=1), terrain="grass"),
            wap.TileView(position=wap.Coord(x=2, y=0), terrain="cave"),
        ],
        explored_static_tiles=[],
        visible_entities=[
            wap.EntityView(**view),
            wap.EntityView(**{**view, "entity_id": "a"}),
        ],
        transient_sightings=[wap.TransientSighting(**view, seen_at_step=0)],
        environmental_cues=[
            wap.EnvironmentalCue(
                cue_id="cue",
                position=wap.Coord(**COORD),
                detail_level="near",
                physical_description="stony",
                direction=None,
            ),
        ],
        running_action=wap.RunningAction(
            intent_id=INTENT_ID,
            action="act",
            verb="gather",
            tick_started=13,
            progress="nearly",
            start_target=wap.TileStartTarget(
                kind="tile", position=wap.Coord(**COORD), terrain="grass"
            ),
            items=[item_use("z", "target"), item_use("a", "target"), item_use("b", "input")],
        ),
        heard_utterances=[
            wap.HeardUtterance(
                **utterance(), utterance_id="spoken", speaker_id=ACTOR, heard_at_tick=14
            ),
        ],
        observed_actions=[
            observed("settle", received_items=[item_use("z", "item"), item_use("a", "item")]),
            observed("stop"),
            observed(
                "start",
                start_target=wap.SubjectStartTarget(
                    kind="resident", id="r2", archetype_id=None, material_id=None, descriptors=[]
                ),
            ),
            observed("settle", tick=13),
        ],
        action_feedback=[
            feedback(9),
            feedback(
                8,
                inspected=wap.InspectView(
                    entity_id="item", archetype_id=None, material_id=None, descriptors=[]
                ),
            ),
        ],
        last_utterance_feedback=wap.UtteranceFeedback(utterance_id="spoken", failure_code=None),
    )


def test_delivery_roundtrip_and_canonical_nested_array_order(perception):
    report_kinds = get_args(wap.ReportKind)
    reports = [
        wap.WorldReport(
            kind=kind,
            subject_id=None if kind == "woke" else "subject",
            addressed=False if kind == "utterance_heard" else None,
            band="good" if kind == "need_band_changed" else None,
            threshold_id="z" if kind == "need_threshold_crossed" else None,
        )
        for kind in reversed(report_kinds)
    ]
    reports.extend(
        [
            wap.WorldReport(
                kind="need_threshold_crossed",
                subject_id=subject,
                addressed=None,
                band=None,
                threshold_id=threshold,
            )
            for subject, threshold in [("subject", "a"), ("a", "z")]
        ]
    )
    delivery = wap.BoundaryDelivery(
        delivery_id="delivery",
        actor_id="r2",
        observed_tick=14,
        perception=perception,
        reports=reports,
    )
    encoded = assert_roundtrip(delivery)
    assert list(dict.fromkeys(report["kind"] for report in encoded["reports"])) == list(
        report_kinds
    )
    thresholds = [report for report in encoded["reports"] if report["threshold_id"] is not None]
    assert [(report["subject_id"], report["threshold_id"]) for report in thresholds] == [
        ("a", "z"),
        ("subject", "a"),
        ("subject", "z"),
    ]

    view = encoded["perception"]
    assert [need["need_id"] for need in view["needs"]] == ["hunger", "thirst"]
    assert [item["entity_id"] for item in view["inventory"]] == ["a", "z"]
    assert [tile["position"]["y"] for tile in view["visible_tiles"]] == [0, 1]
    assert [entity["entity_id"] for entity in view["visible_entities"]] == ["a", "fruit"]
    assert [item["entity_id"] for item in view["running_action"]["items"]] == ["a", "z", "b"]
    observations = view["observed_actions"]
    assert [obs["phase"] for obs in observations] == ["settle", "start", "stop", "settle"]
    assert [item["entity_id"] for item in observations[-1]["received_items"]] == ["z", "a"]
    assert [item["role"] for item in observations[0]["visible_items"]] == ["instrument", "input"]
    assert [entry["intent_id"] for entry in view["action_feedback"]] == [
        f"{ACTOR}:t000009:a",
        f"{ACTOR}:t000008:a",
    ]
    assert view["action_feedback"][0]["phenomena"] == ["a", "z"]


def event_data(payload):
    return {
        "schema_version": wap.SCHEMA_VERSION,
        "run_id": "run",
        "event_id": "run:0000000014:000002",
        "tick": 14,
        "seq_in_tick": 2,
        "type": "agreement_accepted",
        "actor_id": ACTOR,
        "target_id": "r2",
        "intent_id": INTENT_ID,
        "llm_call_id": None,
        "caused_by_event_ids": ["run:0000000013:000000", "run:0000000014:000000"],
        "payload": payload,
    }


def test_objective_event_jsonl_canonical_bytes_and_open_payload():
    data = event_data({"nested": [True, None, {"b": "café", "a": 2}], "x": -1})
    event = wap.WorldEvent.model_validate(data)
    expected = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert wap.encode_event_line(event) == (expected + "\n").encode("utf-8")
    assert wap.decode(wap.WorldEvent, wap.encode_event_line(event)) == event
    assert_roundtrip(event)


@pytest.mark.parametrize("number", [1.0, 0.125, float("nan"), float("inf"), -float("inf")])
def test_nested_floats_refused_by_event_constructor_and_decoder(number):
    data = event_data({"nested": [None, {"value": number}]})
    with pytest.raises(ValidationError):
        wap.WorldEvent.model_validate(data)
    with pytest.raises(ValueError, match="non-integer"):
        wap.decode(wap.WorldEvent, json.dumps(data).encode("utf-8"))


def test_decode_refuses_duplicate_members_and_float_literal_even_if_integral():
    raw = wap.canonical_bytes(validated(turn()))
    with pytest.raises(wap.InvalidTurn, match="duplicate JSON field"):
        wap.decode(
            wap.TurnSubmission,
            raw.replace(b'"observed_tick":14', b'"observed_tick":14,"observed_tick":15'),
        )
    with pytest.raises(wap.InvalidTurn, match="non-integer"):
        wap.decode(wap.TurnSubmission, raw.replace(b'"observed_tick":14', b'"observed_tick":14e0'))


@pytest.mark.parametrize("bad", ["wap/0.2", "wap/1.0", 1, None])
def test_wap_13_unknown_schema_version_refused(bad, perception):
    values = [
        validated(turn()),
        perception,
        wap.WorldEvent.model_validate(event_data({})),
    ]
    for value in values:
        data = value.model_dump()
        data["schema_version"] = bad
        with pytest.raises(ValueError):
            wap.decode(type(value), json.dumps(data).encode("utf-8"))
    delivery = {
        "delivery_id": "delivery",
        "actor_id": "r2",
        "observed_tick": 14,
        "reports": [],
        "perception": {**perception.model_dump(), "schema_version": bad},
    }
    with pytest.raises(ValidationError):
        wap.decode(wap.BoundaryDelivery, json.dumps(delivery).encode("utf-8"))


@pytest.mark.parametrize(
    "field",
    [
        "intention",
        "intention_update",
        "mute_list",
        "citations",
        "context_pressure",
        "schema_version",
        "actor_id",
        "turn_id",
        "observed_tick",
    ],
)
def test_wap_12_model_turn_has_no_agent_private_fields_or_harness_identity(field):
    data = {"action": {"kind": "continue"}, "utterance": None}
    assert_roundtrip(validated(data, running=True, model=wap.ModelTurn))
    with pytest.raises(wap.InvalidTurn):
        validated({**data, field: None}, running=True, model=wap.ModelTurn)
    with pytest.raises(wap.InvalidTurn):
        validated(turn(**{field: None}), running=True)


def test_wap_11_schema_uses_only_enabled_verb_shapes_and_has_canonical_hash():
    schema = wap.model_turn_schema(VERBS)
    assert wap.model_turn_schema(reversed(VERBS)) == schema
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"action", "utterance"}
    definitions = schema["$defs"]
    variants = [variant["properties"] for variant in definitions["IntentShape"]["oneOf"]]
    assert all(set(variant) == set(wap.IntentShape.model_fields) for variant in variants)
    sleep = next(variant for variant in variants if variant["verb"] == {"const": "sleep"})
    assert sleep["target"] == {"type": "null"}
    assert sleep["params"]["properties"] == {
        "duration_ticks": {"type": "integer", "minimum": 6, "maximum": 54}
    }
    pickup = [variant for variant in variants if variant["action"] == {"const": "pick_up"}]
    assert {variant["params"]["$ref"] for variant in pickup} == {
        "#/$defs/PickupParams",
        "#/$defs/TilePickupParams",
    }
    expected = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    original_hash = wap.action_schema_sha256(VERBS)
    assert sha256(expected.encode("utf-8")).hexdigest() == original_hash
    assert (
        wap.action_schema_sha256([*VERBS, wap.EnabledVerb(id="rest", target_kinds=(), params=())])
        != original_hash
    )

    # Two library revisions for the same vocabulary produce the same projection.
    pack = {"enabled_verbs": VERBS, "rules": [{"id": "gather-fruit"}]}
    extended_pack = {**pack, "rules": [{"id": "gather-fruit"}, {"id": "gather-nuts"}]}
    assert wap.action_schema_sha256(pack["enabled_verbs"]) == wap.action_schema_sha256(
        extended_pack["enabled_verbs"]
    )


def test_model_intent_roundtrip_and_requires_harness_to_supply_identity():
    data = deepcopy(turn(SLEEP))
    intent = data["action"]["intent"]
    for field in ("intent_id", "turn_id", "actor_id"):
        intent.pop(field)
    model_turn = {"action": data["action"], "utterance": utterance()}
    assert_roundtrip(validated(model_turn, model=wap.ModelTurn))
    with pytest.raises(wap.InvalidTurn):
        validated(data)
