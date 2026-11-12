"""Pure exactly-once capture and bounded retention of resident-local experience."""

from __future__ import annotations

from living_island.memory.p3_types import (
    MAX_EXPERIENCE_BYTES,
    MAX_EXPERIENCE_RECORDS,
    AcceptedDecisionData,
    DecisionSourceRef,
    DeliverySourceRef,
    ExperienceData,
    ExperienceKind,
    ExperiencePayload,
    ExperienceRecord,
    ExperienceState,
    FeedbackData,
    OwnedIntentRef,
    OwnStateData,
    build_decision_id,
    build_experience_id,
    canonical_bytes,
    validate_goal_reference,
)
from living_island.world.protocol import ActionPlan, BoundaryPerceptionDelivery, format_delivery_id


def initial_experience(owner_id: str) -> ExperienceState:
    """Construct the only valid pre-ingestion state."""
    return ExperienceState(
        experience_schema_version="0.1",
        owner_id=owner_id,
        last_ingested_tick=-1,
        next_sequence=0,
        records=[],
        intent_refs=[],
    )


def _validated_state(state: ExperienceState, run_id: str) -> ExperienceState:
    # Round-trip validation also rejects mutated nested lists and model_construct bypasses.
    checked = ExperienceState.model_validate_json(canonical_bytes(state))
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a nonempty string")
    canonical_bytes(run_id)
    if any(record.source.run_id != run_id for record in checked.records):
        raise ValueError("experience source run differs from the trusted runtime run")
    for ref in checked.intent_refs:
        if ref.decision_id != build_decision_id(run_id, checked.owner_id, ref.decision_ordinal):
            raise ValueError("intent reference belongs to another run")
    return checked


def _retained(records: list[ExperienceRecord]) -> list[ExperienceRecord]:
    sizes = [len(canonical_bytes(record)) for record in records]
    total = 2 + sum(sizes) + max(0, len(records) - 1)
    start = 0
    while len(records) - start > MAX_EXPERIENCE_RECORDS or total > MAX_EXPERIENCE_BYTES:
        total -= sizes[start]
        if len(records) - start > 1:
            total -= 1
        start += 1
    return records[start:]


def ingest_experience(
    state: ExperienceState, delivery: BoundaryPerceptionDelivery, *, run_id: str
) -> ExperienceState:
    """Capture only the exact next own packet; return a new store, preserving intent refs."""
    current = _validated_state(state, run_id)
    packet = BoundaryPerceptionDelivery.model_validate_json(canonical_bytes(delivery))
    if packet.actor_id != current.owner_id:
        raise ValueError("delivery must belong to the memory owner")
    if packet.observed_tick != current.last_ingested_tick + 1:
        raise ValueError("delivery must advance the ingestion cursor exactly once")
    if packet.delivery_id != format_delivery_id(run_id, packet.observed_tick, current.owner_id):
        raise ValueError("delivery must belong to the trusted run")
    records = list(current.records)
    next_sequence = current.next_sequence

    def append(kind: ExperienceKind, field: str, index: int | None, data: ExperienceData) -> None:
        nonlocal next_sequence
        source = DeliverySourceRef.model_validate(
            {
                "source_kind": "delivery",
                "run_id": run_id,
                "delivery_id": packet.delivery_id,
                "field": field,
                "index": index,
            }
        )
        records.append(
            ExperienceRecord(
                experience_id=build_experience_id(current.owner_id, next_sequence),
                owner_id=current.owner_id,
                sequence=next_sequence,
                observed_tick=packet.observed_tick,
                kind=kind,
                source=source,
                payload=ExperiencePayload(information_kind="delivered", confidence=None, data=data),
            )
        )
        next_sequence += 1

    perception = packet.perception
    append(
        "own_state",
        "own_state",
        None,
        OwnStateData(
            condition=perception.own_condition,
            position=perception.own_position,
            inventory=perception.own_inventory,
        ),
    )
    for index, entity in enumerate(perception.visible_entities):
        append("entity_seen", "visible_entities", index, entity)
    for index, sighting in enumerate(perception.transient_sightings):
        append("transient_seen", "transient_sightings", index, sighting)
    for index, cue in enumerate(perception.environmental_cues):
        append("cue_seen", "environmental_cues", index, cue)
    for index, utterance in enumerate(perception.heard_utterances):
        append("heard_speech", "heard_utterances", index, utterance)
    feedback = perception.last_action_feedback
    if feedback is not None:
        owned = next(
            (ref for ref in current.intent_refs if ref.intent.intent_id == feedback.intent_id), None
        )
        append(
            "action_feedback",
            "last_action_feedback",
            None,
            FeedbackData(
                feedback=feedback,
                owned_intent=owned,
            ),
        )
    return ExperienceState(
        experience_schema_version="0.1",
        owner_id=current.owner_id,
        last_ingested_tick=packet.observed_tick,
        next_sequence=next_sequence,
        records=_retained(records),
        intent_refs=current.intent_refs,
    )


def capture_accepted_decision(
    state: ExperienceState,
    run_id: str,
    decision_id: str,
    decision_ordinal: int,
    plan: ActionPlan,
    attached_goal_id: str | None,
    *,
    max_plan_actions: int,
) -> ExperienceState:
    """Capture an already accepted effective plan; the runtime owns transaction admission."""
    current = _validated_state(state, run_id)
    accepted = ActionPlan.model_validate_json(canonical_bytes(plan))
    if type(max_plan_actions) is not int or max_plan_actions < 1:
        raise ValueError("max_plan_actions must be a positive integer")
    if len(accepted.intents) > max_plan_actions:
        raise ValueError("accepted plan exceeds the configured action bound")
    if (
        accepted.actor_id != current.owner_id
        or accepted.created_at_tick != current.last_ingested_tick
    ):
        raise ValueError("accepted plan must match the ingested owner and tick")
    if decision_id != build_decision_id(run_id, current.owner_id, decision_ordinal):
        raise ValueError("decision ID must match the trusted run, owner and ordinal")
    if current.intent_refs and decision_ordinal <= current.intent_refs[0].decision_ordinal:
        raise ValueError("accepted decision ordinal must advance beyond retained current refs")
    validate_goal_reference(attached_goal_id, current.owner_id)
    source = DecisionSourceRef(
        source_kind="decision",
        run_id=run_id,
        decision_id=decision_id,
        decision_ordinal=decision_ordinal,
    )
    record = ExperienceRecord(
        experience_id=build_experience_id(current.owner_id, current.next_sequence),
        owner_id=current.owner_id,
        sequence=current.next_sequence,
        observed_tick=current.last_ingested_tick,
        kind="accepted_decision",
        source=source,
        payload=ExperiencePayload(
            information_kind="interpretation",
            confidence="unassessed",
            data=AcceptedDecisionData(plan=accepted, goal_id=attached_goal_id),
        ),
    )
    refs = [
        OwnedIntentRef(
            intent=intent,
            decision_id=decision_id,
            decision_ordinal=decision_ordinal,
            committed_tick=accepted.created_at_tick,
            goal_id=attached_goal_id,
        )
        for intent in accepted.intents
    ]
    return ExperienceState(
        experience_schema_version="0.1",
        owner_id=current.owner_id,
        last_ingested_tick=current.last_ingested_tick,
        next_sequence=current.next_sequence + 1,
        records=_retained([*current.records, record]),
        intent_refs=refs,
    )
