"""Route party-specific agreement facts and join a resident's filtered delivery to its log."""

from collections.abc import Iterable, Mapping, Sequence
from operator import attrgetter
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_island.agents.v2.context.delivery import FilteredDelivery
from living_island.agents.v2.context.entries import DayEntry, HeardRef, UtteranceFeedbackRef
from living_island.memory.v2.mechanical import (
    AgreementFact,
    MechanicalDelivery,
    Member,
    OwnResult,
    Sight,
    Speech,
    Watch,
)
from living_island.memory.v2.records import Observed, Told
from living_island.world.v2.protocol import (
    BoundaryDelivery,
    Intent,
    ResidentTarget,
    Terms,
    WorldEvent,
)


class _Accepted(BaseModel):
    """The four fields consumed from the otherwise open WorldEvent payload."""

    model_config = ConfigDict(strict=True, extra="ignore")

    agreement_id: str
    proposal_id: str
    acceptance_id: str
    terms: Terms


def project_agreement_facts(
    events: Iterable[WorldEvent], resident_id: str
) -> tuple[AgreementFact, ...]:
    """Project in settlement order. The coordinator retains the objective event IDs."""
    facts = []
    accepted = (event for event in events if event.type == "agreement_accepted")
    for event in sorted(accepted, key=attrgetter("tick", "seq_in_tick")):
        payload = _Accepted.model_validate(event.payload)
        terms = payload.terms
        role: Literal["promisor", "promisee"]
        if resident_id == terms.promisor_id:
            role, counterpart = "promisor", terms.promisee_id
        elif resident_id == terms.promisee_id:
            role, counterpart = "promisee", terms.promisor_id
        else:
            continue
        facts.append(
            AgreementFact(
                agreement_id=payload.agreement_id,
                role=role,
                counterpart_id=counterpart,
                terms=terms,
                due_tick=terms.due_tick,
                accepted_tick=event.tick,
                proposal_id=payload.proposal_id,
                acceptance_id=payload.acceptance_id,
            )
        )
    return tuple(facts)


def actor_feedback_members(packets: Iterable[BoundaryDelivery]) -> dict[str, Member]:
    """Inspection joins an intent to its actor's original result, even for a fallback."""
    return {
        result.intent_id: Member(packet.delivery_id, f"perception.action_feedback[{i}]")
        for packet in packets
        for i, result in enumerate(packet.perception.action_feedback)
    }


def mechanical_delivery(
    delivery: FilteredDelivery,
    entries: Sequence[DayEntry],
    intents: Mapping[str, Intent] = MappingProxyType({}),
) -> MechanicalDelivery:
    """Join the newly appended day entries to this packet and the resident's own submissions."""
    packet = delivery.packet
    view = packet.perception
    pending_speech = {
        heard.utterance_id
        for heard in view.heard_utterances
        if heard.addressee_id == view.actor_id and heard.speech_act in ("accept", "propose")
    }
    own = delivery.own_speech
    members = {}
    speech = []
    for entry in entries:
        if entry.delivery_id != packet.delivery_id:
            raise ValueError("day entry belongs to a different delivery")
        path, *related = entry.member_paths
        member = Member(packet.delivery_id, path, entry.id, entry.revision, tuple(related))
        members[path] = member
        ref = entry.ref
        if isinstance(ref, HeardRef):
            speech.append(
                Speech(
                    ref.utterance_id,
                    Told(utterance_id=ref.utterance_id, speaker_id=ref.speaker_id),
                    member,
                    entry.tick,
                    ref.utterance_id in pending_speech,
                )
            )
        elif (
            isinstance(ref, UtteranceFeedbackRef)
            and ref.utterance_id is not None
            and own is not None
            and own.utterance.speech_act in ("accept", "propose")
        ):
            speech.append(
                Speech(ref.utterance_id, Observed(entry_id=entry.id), member, entry.tick, True)
            )

    sights = []
    for field, residents in (
        ("visible_entities", view.visible_entities),
        ("transient_sightings", view.transient_sightings),
    ):
        for i, entity in enumerate(residents):
            if entity.kind == "resident":
                path = f"perception.{field}[{i}]"
                # An unchanged visible resident has no new day entry but is still seen.
                sights.append(
                    Sight(entity.entity_id, members.get(path, Member(packet.delivery_id, path)))
                )

    watches = tuple(
        Watch(action, members[f"perception.observed_actions[{i}]"])
        for i, action in enumerate(view.observed_actions)
    )
    results = []
    for result in view.action_feedback:
        if result.status != "done":
            continue
        slot = delivery.feedback_sources[result.intent_id]
        intent = intents[result.intent_id]
        if intent.intent_id != result.intent_id or intent.actor_id != packet.actor_id:
            raise ValueError("submitted intent differs from the delivered feedback")
        target = intent.target
        results.append(
            OwnResult(
                result,
                intent.action,
                intent.verb,
                target is None,
                target.id
                if intent.action == "give" and isinstance(target, ResidentTarget)
                else None,
                members[f"perception.action_feedback[{slot.position}]"],
            )
        )
    return MechanicalDelivery(
        packet.actor_id, packet.observed_tick, tuple(sights), tuple(speech), watches, tuple(results)
    )
