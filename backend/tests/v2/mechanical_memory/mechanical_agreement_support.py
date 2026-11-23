"""Shared accepted agreement and delivered speech for the mechanical writer tests."""

PROPOSAL = "island:0000000001:000003"
ACCEPTANCE = "island:0000000002:000001"
AGREEMENT = "island:0000000002:000002"
TERMS = {
    "promisor_id": "mia",
    "promisee_id": "ella",
    "what": {"kind": "give_item", "item": {"archetype_id": "fruit", "quantity": 2}},
    "due_tick": 300,
}


def accepted_event():
    from living_island.world.v2.protocol import WorldEvent

    return WorldEvent(
        schema_version="wap/0.1",
        run_id="island",
        event_id=AGREEMENT,
        tick=2,
        seq_in_tick=2,
        type="agreement_accepted",
        actor_id="mia",
        target_id="ella",
        intent_id="mia:t000001:a",
        llm_call_id="private-call",
        caused_by_event_ids=[PROPOSAL, ACCEPTANCE],
        payload={
            "proposal_id": PROPOSAL,
            "acceptance_id": ACCEPTANCE,
            "agreement_id": AGREEMENT,
            "terms": TERMS,
        },
    )


def agreement_exchange(resident, packet, audit):
    from living_island.agents.v2.context.day_log import DayLog
    from living_island.agents.v2.context.delivery import FilteredDelivery, OwnSpeech
    from living_island.memory.v2.mechanical import MechanicalWriter
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.agreement_facts import (
        mechanical_delivery,
        project_agreement_facts,
    )
    from living_island.world.v2.protocol import Utterance

    store = MemoryStore(resident)
    writer = MechanicalWriter(store)
    log = DayLog(f"p:{resident}:1", audit, phenomena={})
    proposal = Utterance.model_validate(
        dict(
            addressee_id="mia",
            speech_act="propose",
            text="Bring fruit?",
            terms=TERMS,
            in_reply_to=None,
        )
    )
    stages = []
    if resident == "ella":
        # The proposer saw Mia and received feedback for her own proposal, then slept.
        sight = dict(
            kind="resident",
            entity_id="mia",
            archetype_id=None,
            material_id=None,
            descriptors=[],
            position={"x": 1, "y": 0},
            observable_signs=[],
            quantity=None,
        )
        first = packet(
            tick=1,
            actor=resident,
            visible_entities=[sight],
            last_utterance_feedback={"utterance_id": PROPOSAL, "failure_code": None},
        )
        stages.append(
            FilteredDelivery(
                first, own_speech=OwnSpeech(first.perception.last_utterance_feedback, proposal)
            )
        )
        fruit = dict(
            entity_id="stack",
            archetype_id="fruit",
            material_id=None,
            descriptors=[],
            quantity=2,
        )
        stages.append(
            FilteredDelivery(
                packet(
                    tick=2,
                    actor=resident,
                    awareness="asleep",
                    inventory=[fruit],
                )
            )
        )
    elif resident == "mia":
        heard = dict(
            **proposal.model_dump(), utterance_id=PROPOSAL, speaker_id="ella", heard_at_tick=1
        )
        report = dict(
            kind="utterance_heard",
            subject_id=PROPOSAL,
            band=None,
            threshold_id=None,
            addressed=True,
        )
        stages.append(
            FilteredDelivery(
                packet(
                    tick=1,
                    actor=resident,
                    heard_utterances=[heard],
                    reports=[report],
                )
            )
        )
        reply = Utterance(
            addressee_id="ella", speech_act="accept", text="Yes.", terms=None, in_reply_to=PROPOSAL
        )
        second = packet(
            tick=2,
            actor=resident,
            last_utterance_feedback={"utterance_id": ACCEPTANCE, "failure_code": None},
        )
        stages.append(
            FilteredDelivery(
                second, own_speech=OwnSpeech(second.perception.last_utterance_feedback, reply)
            )
        )
    else:
        stages.append(FilteredDelivery(packet(tick=2, actor=resident)))

    for stage in stages:
        events = (accepted_event(),) if stage.packet.observed_tick == 2 else ()
        writer.deliver(
            mechanical_delivery(stage, log.deliver(stage)),
            agreements=project_agreement_facts(events, resident),
        )
    return store.snapshot, log
