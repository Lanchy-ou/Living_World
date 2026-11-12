"""Pure resident-local context, explicit bounded projection and complete manifest."""

from __future__ import annotations

from typing import Literal

from living_island.agents.p3.types import (
    MANDATORY_FIELDS,
    MAX_PROJECTION_BYTES,
    MAX_STATIC_TILE_CANDIDATES,
    ContextAssembly,
    ContextProfile,
    DecisionContextP3,
    ExperienceInclusion,
    InclusionManifest,
    OwnActionSuccessPredicate,
    ProviderPerception,
    ProviderProjection,
    ResidentCognitiveState,
    TileInclusion,
)
from living_island.memory.p3_types import (
    RetrievalQuery,
    RetrievalSelector,
    canonical_bytes,
    canonical_sha256,
)
from living_island.memory.retrieval import retrieve
from living_island.world.protocol import (
    Coord,
    Perception,
    TileTarget,
    TileView,
    TransientSighting,
    VisibleEntity,
)


def _query(perception: Perception, state: ResidentCognitiveState) -> RetrievalQuery:
    ids: set[str] = set()
    positions = {(perception.own_position.y, perception.own_position.x)}
    entities: list[VisibleEntity | TransientSighting] = [
        *perception.visible_entities,
        *perception.transient_sightings,
    ]
    for entity in entities:
        ids.add(entity.entity_id)
        positions.add((entity.position.y, entity.position.x))
    for cue in perception.environmental_cues:
        ids.add(cue.cue_id)
        positions.add((cue.position.y, cue.position.x))
    if perception.own_inventory.canteen_id is not None:
        ids.add(perception.own_inventory.canteen_id)
    goal = state.goals.current
    if goal is not None and isinstance(goal.completion, OwnActionSuccessPredicate):
        target = goal.completion.target
        if isinstance(target, TileTarget):
            positions.add((target.position.y, target.position.x))
        elif target is not None:
            ids.add(target.id)
    return RetrievalQuery(
        query_schema_version="0.1",
        owner_id=state.actor_id,
        entity_ids=sorted(ids, key=lambda value: value.encode("utf-8")),
        positions=[Coord(x=x, y=y) for y, x in sorted(positions)],
    )


def _tile_rank(tile: TileView, origin: Coord) -> tuple[int, int, int, int]:
    rank = {"spring": 0, "cave": 1, "fruit_tree": 2, "damp_moss": 3}
    p = tile.position
    return rank.get(tile.terrain, 4), abs(p.x - origin.x) + abs(p.y - origin.y), p.y, p.x


def assemble_context(
    perception: Perception,
    cognitive_state: ResidentCognitiveState,
    profile: ContextProfile,
    *,
    purpose: Literal["live", "fake", "recorded-fake"] = "live",
    selector: RetrievalSelector | None = None,
    selector_sha256: str | None = None,
) -> ContextAssembly:
    """Assemble from an already-ingested boundary and trusted, pinned selector binding.

    Enrollment, file pin verification and replay comparison are coordinator duties.
    This pure seam validates declared identities, full ranks and exact record copies.
    """
    # Validate serialized copies: callers cannot smuggle mutated nested lists/model_copy
    # updates through Pydantic's trusted-instance shortcut, or retain mutable aliases.
    p = Perception.model_validate(perception.model_dump(mode="json"))
    state = ResidentCognitiveState.model_validate(cognitive_state.model_dump(mode="json"))
    profile = ContextProfile.model_validate(profile.model_dump(mode="json"))
    if purpose not in ("live", "fake", "recorded-fake"):
        raise ValueError("unknown execution purpose")
    if profile.retrieval_profile != "recent-relevant-v0" and purpose == "live":
        raise ValueError("fixture selector is forbidden in live context")
    if p.actor_id != state.actor_id or p.tick != state.experience.last_ingested_tick:
        raise ValueError("context requires the latest ingested own boundary")
    positions = [(t.position.y, t.position.x) for t in p.explored_static_tiles]
    if len(set(positions)) != len(positions):
        raise ValueError("explored tiles must have unique positions")
    result = retrieve(
        state.experience,
        _query(p, state),
        profile.retrieval_profile,
        selector=selector,
        expected_implementation_sha256=selector_sha256,
    )
    context = DecisionContextP3(
        context_schema_version="0.2",
        perception=p,
        identity=state.identity,
        goals=state.goals,
        recalled_experience=result.selected_records,
        owned_intents=state.experience.intent_refs,
    )
    projection_data = dict(
        projection_schema_version="0.1",
        perception={**p.model_dump(mode="json"), "explored_static_tiles": []},
        identity=state.identity.model_dump(mode="json"),
        goals=state.goals.model_dump(mode="json"),
        recalled_experience=[],
        owned_intents=[r.model_dump(mode="json") for r in state.experience.intent_refs],
    )
    projection = ProviderProjection.model_validate(projection_data)
    mandatory_bytes = len(canonical_bytes(projection))
    overflow = mandatory_bytes > MAX_PROJECTION_BYTES
    retrieved_ids = {r.experience_id for r in result.selected_records}
    projected_ids: set[str] = set()
    tiles = sorted(p.explored_static_tiles, key=lambda tile: _tile_rank(tile, p.own_position))
    tile_manifest: list[TileInclusion] = []
    if not overflow:
        for record in result.selected_records:
            candidate = projection.model_copy(
                update={"recalled_experience": [*projection.recalled_experience, record]}
            )
            if len(canonical_bytes(candidate)) <= MAX_PROJECTION_BYTES:
                projection = candidate
                projected_ids.add(record.experience_id)
    for index, tile in enumerate(tiles):
        omission: Literal["mandatory_oversize", "tile_limit", "projection_bytes"] | None
        if overflow:
            omission = "mandatory_oversize"
        elif index >= MAX_STATIC_TILE_CANDIDATES:
            omission = "tile_limit"
        else:
            candidate_tiles = sorted(
                [*projection.perception.explored_static_tiles, tile],
                key=lambda item: (item.position.y, item.position.x),
            )
            candidate = projection.model_copy(
                update={
                    "perception": ProviderPerception.model_validate(
                        {
                            **projection.perception.model_dump(mode="json"),
                            "explored_static_tiles": [
                                t.model_dump(mode="json") for t in candidate_tiles
                            ],
                        }
                    )
                }
            )
            if len(canonical_bytes(candidate)) <= MAX_PROJECTION_BYTES:
                projection = candidate
                omission = None
            else:
                omission = "projection_bytes"
        tile_manifest.append(
            TileInclusion(
                position=tile.position,
                projected=omission is None,
                omission=omission,
            )
        )
    manifest = InclusionManifest(
        manifest_schema_version="0.1",
        context_profile_id=profile.context_profile_id,
        retrieval_profile=profile.retrieval_profile,
        projection_profile=profile.projection_profile,
        store_next_sequence=state.experience.next_sequence,
        retained_record_count=len(state.experience.records),
        evicted_record_count=state.experience.next_sequence - len(state.experience.records),
        mandatory_fields=list(MANDATORY_FIELDS),
        mandatory_bytes=mandatory_bytes,
        projection_bytes=None if overflow else len(canonical_bytes(projection)),
        experiences=[
            ExperienceInclusion(
                experience_id=rid,
                retrieved=rid in retrieved_ids,
                projected=rid in projected_ids,
                omission=(
                    None
                    if rid in projected_ids
                    else "retrieval_limit"
                    if rid not in retrieved_ids
                    else "mandatory_oversize"
                    if overflow
                    else "projection_bytes"
                ),
            )
            for rid in result.ranked_experience_ids
        ],
        static_tiles=tile_manifest,
    )
    return ContextAssembly.model_validate(
        {
            "assembly_schema_version": "0.1",
            "context": context.model_dump(mode="json"),
            "context_sha256": canonical_sha256(context),
            "provider_projection": None if overflow else projection.model_dump(mode="json"),
            "projection_sha256": None if overflow else canonical_sha256(projection),
            "manifest": manifest.model_dump(mode="json"),
            "error": "MANDATORY_OVERSIZE" if overflow else None,
        }
    )
