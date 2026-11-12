"""Pure deterministic retrieval, with an explicitly source-pinned fixture seam."""

from __future__ import annotations

import re

from living_island.memory.p3_types import (
    MAX_RECALLED_RECORDS,
    AcceptedDecisionData,
    ExperienceRecord,
    ExperienceState,
    FeedbackData,
    OwnStateData,
    RetrievalProfileId,
    RetrievalQuery,
    RetrievalResult,
    RetrievalSelector,
    canonical_bytes,
)
from living_island.world.protocol import (
    ActionTarget,
    EntityTarget,
    EnvironmentalCue,
    HeardUtterance,
    ResidentTarget,
    TileTarget,
    TransientSighting,
    VisibleEntity,
)

_KIND_RANK = {
    "action_feedback": 0,
    "heard_speech": 1,
    "accepted_decision": 2,
    "cue_seen": 3,
    "transient_seen": 4,
    "entity_seen": 5,
    "own_state": 6,
}


def _target_keys(target: ActionTarget | None) -> tuple[set[str], set[tuple[int, int]]]:
    if isinstance(target, TileTarget):
        return set(), {(target.position.x, target.position.y)}
    if isinstance(target, (EntityTarget, ResidentTarget)):
        return {target.id}, set()
    return set(), set()


def _keys(record: ExperienceRecord) -> tuple[set[str], set[tuple[int, int]]]:
    data = record.payload.data
    if isinstance(data, OwnStateData):
        ids = set() if data.inventory.canteen_id is None else {data.inventory.canteen_id}
        return ids, {(data.position.x, data.position.y)}
    if isinstance(data, (VisibleEntity, TransientSighting)):
        return {data.entity_id}, {(data.position.x, data.position.y)}
    if isinstance(data, EnvironmentalCue):
        return {data.cue_id}, {(data.position.x, data.position.y)}
    if isinstance(data, HeardUtterance):
        return {data.speaker_id, data.addressee_id}, set()
    if isinstance(data, FeedbackData):
        return _target_keys(None if data.owned_intent is None else data.owned_intent.intent.target)
    assert isinstance(data, AcceptedDecisionData)
    entity_ids: set[str] = set()
    positions: set[tuple[int, int]] = set()
    for intent in data.plan.intents:
        ids, coords = _target_keys(intent.target)
        entity_ids.update(ids)
        positions.update(coords)
    return entity_ids, positions


def retrieve(
    state: ExperienceState,
    query: RetrievalQuery,
    retrieval_profile: RetrievalProfileId,
    *,
    selector: RetrievalSelector | None = None,
    expected_implementation_sha256: str | None = None,
) -> RetrievalResult:
    """Return the complete retained rank and copied E-03 prefix, never inferred history."""
    current = ExperienceState.model_validate_json(canonical_bytes(state))
    requested = RetrievalQuery.model_validate_json(canonical_bytes(query))
    if requested.owner_id != current.owner_id:
        raise ValueError("retrieval query cannot cross the store owner boundary")
    if retrieval_profile not in {"recent-relevant-v0", "recent-only-fixture-v0"}:
        raise ValueError("unknown retrieval strategy")
    if selector is None:
        if expected_implementation_sha256 is not None:
            raise ValueError("an implementation pin requires an injected selector")
        if retrieval_profile != "recent-relevant-v0":
            raise ValueError("fixture strategy requires an explicitly pinned host selector")
        entity_ids = set(requested.entity_ids)
        positions = {(position.x, position.y) for position in requested.positions}

        def rank(record: ExperienceRecord) -> tuple[int, int, int, int]:
            ids, coords = _keys(record)
            related = bool(ids & entity_ids or coords & positions)
            return -int(related), -record.observed_tick, _KIND_RANK[record.kind], -record.sequence

        ordered = sorted(current.records, key=rank)
        result = RetrievalResult(
            ranked_experience_ids=[record.experience_id for record in ordered],
            selected_records=ordered[:MAX_RECALLED_RECORDS],
        )
    else:
        if (
            expected_implementation_sha256 is None
            or re.fullmatch(r"[0-9a-f]{64}", expected_implementation_sha256) is None
        ):
            raise ValueError("injected selector requires a canonical expected implementation hash")
        if selector.retrieval_profile != retrieval_profile:
            raise ValueError("selector identity differs from the admitted retrieval profile")
        if selector.implementation_sha256 != expected_implementation_sha256:
            raise ValueError("selector implementation differs from the admitted pin")
        before_state, before_query = canonical_bytes(current), canonical_bytes(requested)
        result = selector.retrieve(current, requested)
        if canonical_bytes(current) != before_state or canonical_bytes(requested) != before_query:
            raise ValueError("a pure selector must not mutate supplied state or query")
    checked = RetrievalResult.model_validate_json(canonical_bytes(result))
    by_id = {record.experience_id: record for record in current.records}
    if set(checked.ranked_experience_ids) != set(by_id):
        raise ValueError("selector rank must be an exact permutation of retained IDs")
    expected = [
        by_id[identifier] for identifier in checked.ranked_experience_ids[:MAX_RECALLED_RECORDS]
    ]
    if checked.selected_records != expected:
        raise ValueError("selector prefix must contain exact retained record copies")
    return checked
