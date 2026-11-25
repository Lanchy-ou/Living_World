"""DL-07 exercises the actual morning and decision wires with two private histories."""

import json
from functools import partial
from pathlib import Path


def report(kind, subject_id=None, *, addressed=None, band=None):
    return {
        "kind": kind,
        "subject_id": subject_id,
        "addressed": addressed,
        "band": band,
        "threshold_id": None,
    }


def objective_result(secret):
    from living_island.world.v2.protocol import ActionResult

    intent = "ella:t000002:a"
    return ActionResult.model_validate(
        {
            "intent_id": intent,
            "actor_id": "ella",
            "tick_started": 5,
            "tick_finished": 6,
            "outcome": "settled",
            "failure_code": None,
            "stop": None,
            "settlement": {
                "rule_id": f"hidden_recipe_{secret}",
                "kind": "unmet",
                "at": "completion",
                "failed_check": f"private_bridge_check_{secret}",
            },
            "state_delta": [{"path": "true_material", "before": None, "after": f"true_{secret}"}],
            "visible_feedback": {
                "intent_id": intent,
                "status": "done",
                "failure_code": None,
                "stop_reason": None,
                "phenomena": ["bends"],
                "inspected": None,
                "start_target": None,
                "items_used": [],
            },
            "event_ids": [f"private_event_{secret}"],
        }
    )


def store_with_commitment(profile, secret):
    from living_island.memory.v2.records import Observed
    from living_island.memory.v2.store import MemoryStore

    store = MemoryStore("ella")
    profile.initialize(store)
    record = store.registry.parse(
        {
            "id": store.snapshot.next_id(),
            "owner_id": "ella",
            "kind": "commitment",
            "created_tick": 3,
            "updated_tick": 3,
            "about_tick": None,
            "sources": [],
            "confidence": 4,
            "speech_derived": False,
            "last_used_tick": None,
            "use_count": 0,
            "supersedes": None,
            "superseded_by": None,
            "needs_review": False,
            "gist": "",
            "text": None,
            "content": {
                "agreement_id": f"agreement:acceptance_{secret}",
                "role": "promisee",
                "counterpart_id": "mia",
                "terms": {
                    "promisor_id": "mia",
                    "promisee_id": "ella",
                    "what": {"kind": "return_item", "item_id": "the-cup"},
                    "due_tick": None,
                },
                "due_tick": None,
                "heard_counterpart": False,
                "status": "open",
                "status_note": None,
            },
        }
    )
    store.apply(store.snapshot.version, "mechanical", [record])
    store.set_intention(
        turn_id="ella:t000001",
        tick=4,
        text="Meet Mia.",
        source=Observed(entry_id="d:p:ella:1:1"),
    )
    return store.snapshot


def select_morning(prepared, *, audit, transport, clock):
    from living_island.agents.v2.calls.contracts import MorningIDs
    from living_island.agents.v2.calls.provider import attempt

    response = attempt(
        prepared, n=1, has_running_action=False, journal=audit, transport=transport, clock=clock
    )
    assert isinstance(response.parsed, MorningIDs)
    return response.parsed


def test_dl_07_only_resident_projections_reach_the_request(packet, audit, fake_exchange):
    from living_island.agents.v2.calls.guard import Call
    from living_island.agents.v2.calls.provider import attempt
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FeedbackSource, FilteredDelivery
    from living_island.agents.v2.context.dialogue import DialogueState
    from living_island.agents.v2.context.prefix import FrozenPrefix, ResidentIdentity, open_prefix
    from living_island.agents.v2.context.state import render_current_state
    from living_island.agents.v2.context.working import WorkingContext
    from living_island.memory.v2.profiles import SelectedProfile

    profile = SelectedProfile.load(
        Path(__file__).parents[1] / "memory_store" / "fixtures" / "synthetic_min.json"
    )
    period = "p:ella:2"
    wires = []
    for secret in ("A", "B"):
        snapshot = store_with_commitment(profile, secret)
        visible = snapshot.resident(memory_on=True)
        result = objective_result(secret)
        waking = packet(tick=5, needs=[{"need_id": "mental_fatigue", "band": "moderate"}])
        state = render_current_state(
            waking, reasons=("woke",), time_of_day="dawn", intention=visible.current_intention
        )
        clock, transport = fake_exchange(
            ['{"ids":["m:ella:2"]}', '{"step":"recall","query":"Mia"}']
        )

        prefix = open_prefix(
            call=Call(call_id=f"morning-{secret}", resident_id="ella", tick=5, period_id=period),
            identity=ResidentIdentity("Ella", profile),
            verbs=(),
            traits=profile.document.traits,
            view=visible,
            store_version=snapshot.version,
            memory_on=True,
            waking=state,
            journal=audit,
            select=partial(select_morning, audit=audit, transport=transport, clock=clock),
        )
        assert isinstance(prefix, FrozenPrefix)
        log = DayLog(period, audit, phenomena={"bends": "It bends."})
        dialogue = DialogueState("ella", gap_ticks=3)
        cup = {
            "entity_id": "the-cup",
            "archetype_id": "cup",
            "material_id": "clay",
            "descriptors": [{"property_id": "surface", "value": "pale"}],
            "quantity": 1,
        }
        fallback = result.visible_feedback.model_copy(
            update={"intent_id": "ella:t000001:a", "phenomena": [f"fallback_only_{secret}"]}
        )
        physical = packet(
            tick=6,
            needs=[{"need_id": "mental_fatigue", "band": "moderate"}],
            inventory=[cup],
            action_feedback=[fallback, result.visible_feedback],
            reports=[
                report("action_ended", fallback.intent_id),
                report("action_ended", result.intent_id),
                report("utterance_heard", "overheard-acceptance", addressed=False),
            ],
            running_action={
                "intent_id": "ella:t000003:a",
                "action": "move_to",
                "verb": None,
                "tick_started": 6,
                "progress": "partway",
                "start_target": None,
                "items": [],
            },
            visible_tiles=[{"position": {"x": 0, "y": 0}, "terrain": "grass"}],
            explored_static_tiles=[
                {"position": {"x": 0, "y": 0}, "terrain": "grass"},
                {"position": {"x": 2, "y": 0}, "terrain": "cave"},
            ],
            heard_utterances=[
                {
                    "utterance_id": "overheard-acceptance",
                    "speaker_id": "jules",
                    "heard_at_tick": 6,
                    "addressee_id": "mia",
                    "speech_act": "accept",
                    "text": "At the old tree.",
                    "terms": None,
                    "in_reply_to": "delivered-proposal-id",
                }
            ],
        )
        # Sim joins durable intent origins. Keep both neutral action-ended
        # reports, and only the model-owned result at its original packet slot.
        retained = [
            f for f in physical.perception.action_feedback if f.intent_id == result.intent_id
        ]
        public = physical.model_copy(
            update={
                "perception": physical.perception.model_copy(update={"action_feedback": retained})
            }
        )
        delivery = FilteredDelivery(public, {result.intent_id: FeedbackSource("bend", 1)})
        log.deliver(delivery)
        dialogue.receive(delivery)
        state = render_current_state(
            public,
            reasons=("action_ended", "notification"),
            time_of_day="morning",
            mute=("discovery",),
            intention=visible.current_intention,
            dialogue=dialogue.sessions,
        )
        context = WorkingContext(prefix, log)
        prepared = context.prepare_decision(
            Call(
                call_id=f"decision-{secret}",
                resident_id="ella",
                period_id=period,
                tick=6,
                turn_id="ella:t000004",
            ),
            state,
            audit,
            view=visible,
        )
        returned = attempt(
            prepared, n=1, has_running_action=True, journal=audit, transport=transport, clock=clock
        )
        assert returned.terminal.error_class is None
        morning, decision = [
            json.loads(body)["input"][1]["content"] for body in transport.dispatches
        ]
        for private in (
            "hidden_recipe_",
            "true_material",
            f"true_{secret}",
            "private_bridge_check_",
            "unmet",
            "private_event_",
            "agreement_id",
            "fallback_only_",
            f"acceptance_{secret}",
        ):
            assert private not in morning and private not in decision
        assert "overheard-acceptance" not in morning
        section_order = (
            "Turn reasons:",
            "mentally tired",
            "Your thoughts feel clear.",
            "You are at",
            "Carrying:",
            "Continue or replace",
            "Current intention",
            "In sight:",
            "Explored map",
        )
        positions = [decision.index(label) for label in section_order]
        assert positions == sorted(positions)
        for public_text in (
            "It bends.",
            "overheard-acceptance",
            "delivered-proposal-id",
            "At the old tree.",
            "m:ella:2",
            "the-cup",
            "m:ella:3",
            "Meet Mia.",
            "discovery",
            "partway",
            "pale",
            "@?C",
        ):
            assert public_text in decision
        # Only current state is replaced. The confirmation snapshot retains its
        # exact pressure words and entries as later sleeping deliveries arrive.
        log.deliver(
            FilteredDelivery(
                packet(
                    tick=7,
                    awareness="unconscious",
                    reports=[report("need_band_changed", "mental_fatigue", band="critical")],
                )
            )
        )
        frozen = context.freeze()
        assert decision.endswith("\n".join(p.text for p in frozen.current_state))
        assert "Your thoughts feel clear." in [p.text for p in frozen.current_state]
        log.deliver(
            FilteredDelivery(
                packet(
                    tick=8,
                    awareness="unconscious",
                    reports=[report("need_band_changed", "satiety", band="low")],
                )
            )
        )
        assert len(log.entries) > len(frozen.entries)
        assert len(frozen.parts) == 1 + len(prefix.parts) + len(frozen.entries) + len(
            frozen.current_state
        )
        wires.append(transport.dispatches)
    assert wires[0] == wires[1]
