"""Observation ports: accumulator, novelty, receipts and the frozen batch (plan §2.1, P1-02)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from world_builders import (
    default_content,
    fresh_state,
    p1_default_content,
    place,
    resident,
    tiny_content,
)

from living_island.world.content import WorldContent, canonical_json_bytes
from living_island.world.perception import ground_fruit_id
from living_island.world.ports import (
    ObservationAccumulator,
    ObservationBatch,
    begin_observation_tick,
    finish_observation_tick,
    observe_step,
)
from living_island.world.protocol import Coord, Perception
from living_island.world.receipts import (
    merge_receipts,
    merge_tile_indices,
    receipt_authorizes_entity,
    receipt_authorizes_pickup,
)
from living_island.world.state import (
    CueDetailReceipt,
    ExposureReceipts,
    GroundFruitPile,
    ReceiptEntity,
    WorldState,
)

TINY = [
    "~~~~~~~~~~~~~~~~",
    "~...M..........~",
    "~.........F....~",
    "~..............~",
    "~.C..........S.~",
    "~~~~~~~~~~~~~~~~",
]
POS = {"ella": (3, 3), "ryan": (3, 4), "mia": (12, 3)}
MOSS = Coord(x=4, y=1)


def tiny(**perception: int) -> tuple[WorldContent, WorldState]:
    content = tiny_content(TINY, POS, **perception)
    return content, fresh_state(content)


def c(x: int, y: int) -> Coord:
    return Coord(x=x, y=y)


def run_tick(
    content: WorldContent,
    state: WorldState,
    completed_tick: int,
    steps: Mapping[str, Sequence[Coord]] | None = None,
) -> ObservationBatch:
    acc = begin_observation_tick(state, completed_tick, content)
    for actor, positions in (steps or {}).items():
        for n, pos in enumerate(positions, start=1):
            observe_step(acc, state, actor, pos, n)
    return finish_observation_tick(acc, state)


def apply_batch(state: WorldState, batch: ObservationBatch) -> None:
    """What the engine does in phase 6: apply footprints and receipts exactly once."""
    for t in batch.new_static_tiles_by_actor:
        group = next(g for g in state.explored_tiles_by_resident if g.resident_id == t.actor_id)
        group.tile_indices = merge_tile_indices(group.tile_indices, t.tile_indices)
    for u in batch.exposure_receipt_updates:
        i = next(
            k
            for k, g in enumerate(state.exposure_receipts_by_resident)
            if g.resident_id == u.actor_id
        )
        state.exposure_receipts_by_resident[i] = merge_receipts(
            state.exposure_receipts_by_resident[i], u.entities, u.cue_detail_seen
        )


def sample_of(batch: ObservationBatch, actor: str) -> Any:
    return next(s for s in batch.physical_samples_by_actor if s.actor_id == actor)


def receipts_of(state: WorldState, actor: str) -> ExposureReceipts:
    return next(g for g in state.exposure_receipts_by_resident if g.resident_id == actor)


def seed_receipts(
    state: WorldState,
    actor: str,
    entities: Sequence[tuple[str, str, int, int]] = (),
    cues: Sequence[tuple[str, str]] = (),
) -> None:
    i = next(k for k, g in enumerate(state.exposure_receipts_by_resident) if g.resident_id == actor)
    state.exposure_receipts_by_resident[i] = merge_receipts(
        state.exposure_receipts_by_resident[i],
        [ReceiptEntity(entity_id=e, entity_type=t, position=c(x, y)) for e, t, x, y in entities],
        [CueDetailReceipt(cue_id=cid, detail_level=lvl) for cid, lvl in cues],
    )


# ------------------------------------------------------------------ tick zero


def test_tick_zero_scan_seeds_receipts_and_creates_no_new_sight() -> None:
    content = p1_default_content()
    state = fresh_state(content)
    batch = run_tick(content, state, 0)
    assert [s.actor_id for s in batch.physical_samples_by_actor] == ["ella", "mia", "ryan"]
    assert batch.new_sight_actor_ids == []
    updates = {u.actor_id: u for u in batch.exposure_receipt_updates}
    assert set(updates) == {"ella", "mia", "ryan"}
    for actor, update in updates.items():
        kinds = {(e.entity_id, e.entity_type) for e in update.entities}
        assert (actor, "resident") in kinds  # own identity
        assert ("moss_east_01", "cue") in kinds
        assert [c_.cue_id for c_ in update.cue_detail_seen] == ["moss_east_01"]
    owner = content.config.canteen.initial_owner_id
    assert ("canteen_01", "canteen") in {
        (e.entity_id, e.entity_type) for e in updates[owner].entities
    }
    levels = {a: u.cue_detail_seen[0].detail_level for a, u in updates.items()}
    assert levels == {"ella": "distant", "ryan": "distant", "mia": "near"}  # moss at (15,32)


def test_tick_zero_footprint_is_exactly_the_visible_tiles() -> None:
    content = default_content()
    state = fresh_state(content)
    batch = run_tick(content, state, 0)
    for sample in batch.physical_samples_by_actor:
        new = next(t for t in batch.new_static_tiles_by_actor if t.actor_id == sample.actor_id)
        width = default_content().config.map.width
        visible = [t.position.y * width + t.position.x for t in sample.visible_tiles]
        assert new.tile_indices == visible
        assert sample.explored_static_tiles == sample.visible_tiles
        assert sample.tick == 0


def test_batch_arrays_are_sorted_by_actor_id() -> None:
    content = default_content()
    state = fresh_state(content)
    batch = run_tick(content, state, 0)
    for rows in (
        batch.physical_samples_by_actor,
        batch.new_static_tiles_by_actor,
        batch.exposure_receipt_updates,
    ):
        names = [r.actor_id for r in rows]
        assert names == sorted(names)
    assert batch.new_sight_actor_ids == sorted(batch.new_sight_actor_ids)


def test_dead_residents_get_no_sample() -> None:
    content, state = tiny()
    resident(state, "ryan").alive = False
    batch = run_tick(content, state, 1)
    assert [s.actor_id for s in batch.physical_samples_by_actor] == ["ella", "mia"]


def test_sample_fits_the_perception_model() -> None:
    content, state = tiny()
    sample = run_tick(content, state, 1).physical_samples_by_actor[0]
    Perception.model_validate(
        {**sample.model_dump(), "heard_utterances": [], "last_action_feedback": None}
    )


# ------------------------------------------------------------------ accumulator isolation


def test_observe_calls_modify_only_the_accumulator() -> None:
    content, state = tiny(day_radius_tiles=3)
    before = state.model_dump_json()
    run_tick(content, state, 1, {"ella": [c(4, 2), c(5, 2)]})
    assert state.model_dump_json() == before


def test_receipt_baseline_is_an_immutable_tick_start_copy() -> None:
    content, state = tiny()
    acc = begin_observation_tick(state, 1, content)
    assert isinstance(acc, ObservationAccumulator)
    assert acc.completed_tick == 1
    seed_receipts(state, "ella", [("mia", "resident", 12, 3)])  # engine mutates state later
    assert all(not r.entities for r in acc.receipt_baseline)
    acc.receipt_baseline[0].entities.append(  # mutating a returned copy changes nothing
        ReceiptEntity(entity_id="x", entity_type="resident", position=c(1, 1))
    )
    assert all(not r.entities for r in acc.receipt_baseline)


def test_novelty_ignores_receipts_added_to_state_after_begin() -> None:
    content, state = tiny()
    acc = begin_observation_tick(state, 1, content)
    observe_step(acc, state, "ella", c(4, 3), 1)
    seed_receipts(state, "ella", [("mia", "resident", 12, 3), ("fruit_01", "fruit_tree", 10, 2)])
    batch = finish_observation_tick(acc, state)
    assert "ella" in batch.new_sight_actor_ids


# ------------------------------------------------------------------ transient sightings and cues


def test_intermediate_sign_and_near_cue_survive_in_the_batch() -> None:
    content, state = tiny(day_radius_tiles=3, cue_detail_radius_tiles=1)
    resident(state, "mia").health = 3000  # visibly weak
    place(state, "mia", 3, 1)
    acc = begin_observation_tick(state, 1, content)
    observe_step(acc, state, "ella", c(3, 2), 1)  # moss at distance 2: distant; mia adjacent
    observe_step(acc, state, "ella", c(4, 2), 2)  # moss at distance 1: near
    # The world moves on before the boundary: values must not be re-read.
    resident(state, "mia").health = 10000
    place(state, "mia", 2, 2)
    place(state, "ella", 9, 3)  # tick-end position far from both
    batch = finish_observation_tick(acc, state)

    sample = sample_of(batch, "ella")
    # ryan (3,4) and the cue were also in view at the steps; one entry per entity, by ID.
    assert [t.entity_id for t in sample.transient_sightings] == ["mia", "moss_east_01", "ryan"]
    mia = sample.transient_sightings[0]
    assert (mia.position, mia.seen_at_step) == (c(3, 1), 2)  # last intermediate sighting
    assert mia.observable_signs == ["weak"]  # captured, not refreshed
    assert "mia" not in [e.entity_id for e in sample.visible_entities]
    [cue] = sample.environmental_cues
    spec = content.config.world.cues[0]
    assert (cue.cue_id, cue.detail_level, cue.direction) == ("moss_east_01", "near", "east")
    assert cue.physical_description == spec.near_description
    assert cue.position == MOSS
    assert "ella" in batch.new_sight_actor_ids


def test_transient_keeps_last_step_and_excludes_entities_visible_at_tick_end() -> None:
    content, state = tiny(day_radius_tiles=3)
    # ryan (3,4) is in view at steps 1 and 2 but not from the tick-end tile (9,3).
    acc = begin_observation_tick(state, 1, content)
    observe_step(acc, state, "ella", c(3, 3), 1)
    observe_step(acc, state, "ella", c(4, 4), 2)
    place(state, "ella", 9, 3)
    batch = finish_observation_tick(acc, state)
    [t] = [t for t in sample_of(batch, "ella").transient_sightings if t.entity_id == "ryan"]
    assert t.seen_at_step == 2 and t.position == c(3, 4)

    # Seen at an intermediate step AND still visible at tick end: not transient.
    place(state, "ella", 3, 3)
    acc = begin_observation_tick(state, 2, content)
    observe_step(acc, state, "ella", c(3, 3), 1)
    place(state, "ella", 4, 3)
    sample = sample_of(finish_observation_tick(acc, state), "ella")
    assert "ryan" not in [t.entity_id for t in sample.transient_sightings]
    assert "ryan" in [e.entity_id for e in sample.visible_entities]


# ------------------------------------------------------------------ NEW_SIGHT


def test_first_exposure_is_new_sight_even_after_several_observe_calls() -> None:
    content, state = tiny()
    # fruit_01 (10,2) is in view at every step; naive "seen earlier this tick" logic would
    # lose it. Novelty is judged against the tick-start receipts only.
    batch = run_tick(content, state, 1, {"ella": [c(5, 2), c(6, 2), c(7, 2)]})
    assert "ella" in batch.new_sight_actor_ids


def test_previously_exposed_entities_do_not_retrigger_new_sight() -> None:
    content, state = tiny()
    seed_receipts(
        state,
        "ella",
        [
            ("fruit_01", "fruit_tree", 10, 2),
            ("mia", "resident", 12, 3),
            ("ryan", "resident", 3, 4),
            ("moss_east_01", "cue", 4, 1),
            ("canteen_01", "canteen", 3, 3),  # Ella's inventory canteen is already known
        ],
        [("moss_east_01", "distant")],
    )
    place(state, "mia", 11, 3)  # moved: a new position, not a new entity
    batch = run_tick(content, state, 1, {"ella": [c(5, 3), c(6, 3)]})
    assert "ella" not in batch.new_sight_actor_ids
    update = next(u for u in batch.exposure_receipt_updates if u.actor_id == "ella")
    assert ("mia", "resident", 11, 3) in {
        (e.entity_id, e.entity_type, e.position.x, e.position.y) for e in update.entities
    }


def test_new_sight_is_reported_once_per_actor_in_sorted_order() -> None:
    content, state = tiny()
    batch = run_tick(content, state, 1, {"ella": [c(5, 2), c(6, 2)]})
    assert batch.new_sight_actor_ids == sorted(set(batch.new_sight_actor_ids))
    assert batch.new_sight_actor_ids.count("ella") == 1


@pytest.mark.parametrize(
    ("baseline", "end_x", "expected_new_sight", "expected_cue_update"),
    [
        (None, 5, True, "near"),  # first exposure, directly near
        (None, 8, True, "distant"),  # first exposure, distant
        ("distant", 5, True, "near"),  # distant -> near upgrade
        ("distant", 8, False, None),  # distant again: nothing new
        ("near", 5, False, None),  # near again: nothing new
        ("near", 8, False, None),  # near was seen before; distance does not downgrade
    ],
)
def test_cue_novelty_and_receipt_upgrade(
    baseline: str | None, end_x: int, expected_new_sight: bool, expected_cue_update: str | None
) -> None:
    content, state = tiny(day_radius_tiles=5, cue_detail_radius_tiles=1)
    place(state, "ella", end_x, 1)
    # Keep everything else already known so only the cue can be novel for ella.
    known = [("ryan", "resident", 3, 4), ("mia", "resident", 12, 3)]
    known += [("fruit_01", "fruit_tree", 10, 2), ("canteen_01", "canteen", 3, 3)]
    if baseline:
        known.append(("moss_east_01", "cue", 4, 1))
    seed_receipts(state, "ella", known, [("moss_east_01", baseline)] if baseline else [])
    batch = run_tick(content, state, 1)
    assert ("ella" in batch.new_sight_actor_ids) is expected_new_sight
    update = next((u for u in batch.exposure_receipt_updates if u.actor_id == "ella"), None)
    levels = [c_.detail_level for c_ in update.cue_detail_seen] if update else []
    assert levels == ([expected_cue_update] if expected_cue_update else [])


# ------------------------------------------------------------------ footprints and receipts


def test_footprint_keeps_static_terrain_but_not_dynamic_stock() -> None:
    content, state = tiny(day_radius_tiles=3)
    width = content.config.map.width
    tree_tile = 2 * width + 10
    place(state, "ella", 9, 2)  # tree (10,2) adjacent
    first = run_tick(content, state, 1)
    assert "fruit_01" in [e.entity_id for e in sample_of(first, "ella").visible_entities]
    apply_batch(state, first)

    place(state, "ella", 3, 3)  # walk away; the tree is far outside sight
    state.fruit_nodes[0].stock = 5  # remote change must not leak
    second = run_tick(content, state, 2)
    sample = sample_of(second, "ella")
    explored = {(t.position.x, t.position.y): t.terrain for t in sample.explored_static_tiles}
    assert explored[(10, 2)] == "fruit_tree"  # static terrain persists
    assert tree_tile in {t.position.y * width + t.position.x for t in sample.explored_static_tiles}
    assert "fruit_01" not in [e.entity_id for e in sample.visible_entities]
    assert "fruit_01" not in [t.entity_id for t in sample.transient_sightings]
    dumped = json.dumps([t.model_dump() for t in sample.explored_static_tiles])
    assert set(json.loads(dumped)[0]) == {"position", "terrain"}  # no stock/descriptors


def test_second_identical_tick_adds_nothing_once_applied() -> None:
    content, state = tiny()
    first = run_tick(content, state, 1)
    assert first.new_static_tiles_by_actor and first.exposure_receipt_updates
    apply_batch(state, first)
    second = run_tick(content, state, 2)
    assert second.new_static_tiles_by_actor == []
    assert second.exposure_receipt_updates == []
    assert second.new_sight_actor_ids == []


def test_receipts_authorize_only_exposed_ids() -> None:
    content, state = tiny(day_radius_tiles=3)
    state.ground_fruit = [GroundFruitPile(position=c(4, 3), quantity=2)]
    place(state, "ella", 5, 3)
    apply_batch(state, run_tick(content, state, 1))
    receipts = receipts_of(state, "ella")
    assert receipt_authorizes_entity(receipts, "ryan")
    assert receipt_authorizes_entity(receipts, ground_fruit_id(c(4, 3)))
    assert not receipt_authorizes_entity(receipts, "mia")  # never in sight
    assert not receipt_authorizes_entity(receipts, "fruit_01")  # beyond radius 3
    # pick_up needs an item-type receipt at that exact tile.
    assert receipt_authorizes_pickup(receipts, "fruit", c(4, 3))
    assert not receipt_authorizes_pickup(receipts, "fruit", c(5, 3))
    assert not receipt_authorizes_pickup(receipts, "canteen", c(4, 3))
    assert not receipt_authorizes_pickup(receipts, "fruit", c(10, 2))


def test_merge_helpers_are_sorted_unique_and_upgrade_cue_detail() -> None:
    assert merge_tile_indices([5, 1, 3], [3, 2, 9]) == [1, 2, 3, 5, 9]
    base = ExposureReceipts(resident_id="ella", entities=[], cue_detail_seen=[])
    e1 = ReceiptEntity(entity_id="b", entity_type="resident", position=c(2, 1))
    e2 = ReceiptEntity(entity_id="a", entity_type="resident", position=c(9, 9))
    merged = merge_receipts(
        base,
        [e1, e2, e1],
        [
            CueDetailReceipt(cue_id="m", detail_level="distant"),
            CueDetailReceipt(cue_id="m", detail_level="near"),
        ],
    )
    assert [e.entity_id for e in merged.entities] == ["a", "b"]
    assert merged.cue_detail_seen == [CueDetailReceipt(cue_id="m", detail_level="near")]
    downgraded = merge_receipts(merged, [], [CueDetailReceipt(cue_id="m", detail_level="distant")])
    assert downgraded.cue_detail_seen[0].detail_level == "near"
    assert base.entities == []  # inputs untouched


# ------------------------------------------------------------------ leaks, determinism, errors


def test_batch_has_no_hidden_spring_exact_needs_or_remote_stock() -> None:
    content = p1_default_content()
    state = fresh_state(content)
    resident(state, "mia").satiety = 4321
    resident(state, "mia").hydration = 4322
    for node in state.fruit_nodes:
        node.stock = 4
    batch = run_tick(content, state, 0)
    text = canonical_json_bytes(batch.model_dump(mode="json")).decode()
    spring = state.spring
    assert not any(
        t["terrain"] == "spring"
        for s in batch.model_dump(mode="json")["physical_samples_by_actor"]
        for t in s["visible_tiles"] + s["explored_static_tiles"]
    )
    assert f'"x":{spring.x},"y":{spring.y}' not in text
    assert "4321" not in text and "4322" not in text
    assert '"stock"' not in text
    assert "fruit_02" not in text  # remote tree: absent entirely


def scenario_bytes() -> bytes:
    content, state = tiny(day_radius_tiles=3)
    resident(state, "mia").health = 3000
    place(state, "mia", 3, 1)
    acc = begin_observation_tick(state, 1, content)
    observe_step(acc, state, "ella", c(3, 2), 1)
    observe_step(acc, state, "ella", c(4, 2), 2)
    place(state, "ella", 9, 3)
    return canonical_json_bytes(finish_observation_tick(acc, state).model_dump(mode="json"))


def test_identical_inputs_give_byte_identical_canonical_json_with_integers_only() -> None:
    first, second = scenario_bytes(), scenario_bytes()
    assert first == second

    def has_float(value: object) -> bool:
        if isinstance(value, float):
            return True
        if isinstance(value, dict):
            return any(has_float(v) for v in value.values())
        if isinstance(value, list):
            return any(has_float(v) for v in value)
        return False

    assert not has_float(json.loads(first))


def test_step_indexes_must_be_consecutive_from_one() -> None:
    content, state = tiny()
    acc = begin_observation_tick(state, 1, content)
    with pytest.raises(ValueError, match="consecutive"):
        observe_step(acc, state, "ella", c(4, 3), 2)
    observe_step(acc, state, "ella", c(4, 3), 1)
    with pytest.raises(ValueError, match="consecutive"):
        observe_step(acc, state, "ella", c(5, 3), 1)


def test_observe_rejects_dead_unknown_and_out_of_map() -> None:
    content, state = tiny()
    acc = begin_observation_tick(state, 1, content)
    resident(state, "ryan").alive = False
    with pytest.raises(ValueError, match="dead"):
        observe_step(acc, state, "ryan", c(3, 4), 1)
    with pytest.raises(ValueError, match="unknown"):
        observe_step(acc, state, "nobody", c(3, 4), 1)
    with pytest.raises(ValueError, match="outside the map"):
        observe_step(acc, state, "ella", c(99, 99), 1)


def test_mismatched_content_and_foreign_accumulators_are_refused() -> None:
    content, state = tiny()
    state.map_hash = "0" * 64
    with pytest.raises(ValueError, match="do not match"):
        begin_observation_tick(state, 1, content)
    with pytest.raises(ValueError):
        begin_observation_tick(fresh_state(content), -1, content)
    foreign = ObservationAccumulator(1, ())
    with pytest.raises(TypeError):
        observe_step(foreign, fresh_state(content), "ella", c(3, 3), 1)
    with pytest.raises(TypeError):
        finish_observation_tick(foreign, fresh_state(content))


def test_mutating_the_supplied_content_after_begin_changes_nothing() -> None:
    """G2-02 / CR-002(a): the accumulator keeps its own deep copy of the content."""
    content, state = tiny()
    expected = run_tick(content, state, 1).model_dump(mode="json")
    acc = begin_observation_tick(state, 1, content)
    cutoffs = content.config.perception.need_band_cutoffs
    original = list(cutoffs)
    cutoffs[:] = [9000, 9100, 9200, 9300]  # ella's 8500 stamina would read "critical"
    content.map_rows[3] = "~" * len(content.map_rows[3])  # blind the map as well
    try:
        batch = finish_observation_tick(acc, state)
    finally:
        cutoffs[:] = original
        content.map_rows[3] = TINY[3]
    assert batch.model_dump(mode="json") == expected
    assert sample_of(batch, "ella").own_condition.stamina != "critical"


# ------------------------------------------------------------------ rework round 1


def test_novelty_indices_are_private_and_immutable() -> None:
    """G2-03: novelty reads only an immutable index derived from the immutable baseline."""
    content, state = tiny(day_radius_tiles=0, night_radius_tiles=0)
    seed_receipts(
        state, "ella", [("fruit_01", "fruit_tree", 10, 2), ("canteen_01", "canteen", 3, 3)]
    )
    acc = begin_observation_tick(state, 1, content)
    for name in ("known_ids", "known_triples", "known_cue_detail"):
        assert not hasattr(acc, name)  # no public mutable index
    index = acc._known
    with pytest.raises((AttributeError, TypeError)):
        index.ids["ella"].add("ryan")
    with pytest.raises((AttributeError, TypeError)):
        index.ids["ella"] = frozenset({"ryan"})
    with pytest.raises((AttributeError, TypeError)):
        index.ids = {}
    place(state, "ella", 10, 2)  # standing on the tree: it is already in the baseline
    batch = finish_observation_tick(acc, state)
    assert "ella" not in batch.new_sight_actor_ids
    # A tampered baseline copy must not leak into the accumulator either.
    acc.receipt_baseline[0].entities.clear()
    assert "fruit_01" in acc._known.ids["ella"]


def test_cues_are_ordinary_entities_and_keep_their_detail() -> None:
    """G2-04: WR §4.1 / §5.1 step 5 / IC §2.5 treat cues as one of the six entity types."""
    content, state = tiny(day_radius_tiles=3, cue_detail_radius_tiles=1)
    place(state, "ella", 5, 1)
    sample = sample_of(run_tick(content, state, 1), "ella")
    entity = next(e for e in sample.visible_entities if e.entity_id == "moss_east_01")
    assert entity.entity_type == "cue" and entity.position == MOSS
    assert (entity.observable_signs, entity.fruit_band, entity.quantity) == ([], None, None)
    [cue] = sample.environmental_cues
    assert (cue.cue_id, cue.detail_level) == ("moss_east_01", "near")


def test_step_only_cue_is_a_transient_sighting_with_its_step() -> None:
    content, state = tiny(day_radius_tiles=3, cue_detail_radius_tiles=1)
    acc = begin_observation_tick(state, 1, content)
    observe_step(acc, state, "ella", c(3, 2), 1)  # distant
    observe_step(acc, state, "ella", c(4, 2), 2)  # near
    place(state, "ella", 9, 3)  # the cue is out of sight at tick end
    sample = sample_of(finish_observation_tick(acc, state), "ella")
    [moss] = [t for t in sample.transient_sightings if t.entity_id == "moss_east_01"]
    assert (moss.entity_type, moss.seen_at_step, moss.position) == ("cue", 2, MOSS)
    assert (moss.observable_signs, moss.fruit_band, moss.quantity) == ([], None, None)
    assert "moss_east_01" not in [e.entity_id for e in sample.visible_entities]
    assert [c_.detail_level for c_ in sample.environmental_cues] == ["near"]


def test_first_exposure_of_an_inventory_canteen_is_new_sight() -> None:
    """G2-05: the canteen ID counts as exposed through inventory; self never does."""
    content, state = tiny(day_radius_tiles=0, night_radius_tiles=0)
    assert state.unique_canteen.holder_id == "ella"
    # Tick zero seeds receipts without a trigger, canteen included.
    zero = run_tick(content, state, 0)
    assert zero.new_sight_actor_ids == []
    apply_batch(state, zero)
    assert run_tick(content, state, 1).new_sight_actor_ids == []  # known canteen, known self
    # A give at a completed boundary: Mia's first canteen exposure is NEW_SIGHT; Ella's is not.
    state.unique_canteen = state.unique_canteen.model_copy(update={"holder_id": "mia"})
    given = run_tick(content, state, 2)
    assert given.new_sight_actor_ids == ["mia"]
    apply_batch(state, given)
    assert run_tick(content, state, 3).new_sight_actor_ids == []


def test_a_fresh_baseline_never_counts_self_as_a_sight() -> None:
    content, state = tiny(day_radius_tiles=0, night_radius_tiles=0)
    batch = run_tick(content, state, 1)  # empty baselines, nobody in sight
    assert batch.new_sight_actor_ids == ["ella"]  # only the canteen holder's inventory ID


# ------------------------------------------------------------------ rework round 2


def test_stale_config_is_refused_at_bind_time() -> None:
    """G2-02: canonical hashes are recomputed from the private copy before anything is built."""
    content, state = tiny()
    cutoffs = content.config.perception.need_band_cutoffs
    original = list(cutoffs)
    cutoffs[:] = [9000, 9100, 9200, 9300]  # data changed, declared hashes unchanged
    try:
        with pytest.raises(ValueError, match="config does not match"):
            begin_observation_tick(state, 1, content)
    finally:
        cutoffs[:] = original
    begin_observation_tick(state, 1, content)  # restored content binds again


def test_stale_map_is_refused_at_bind_time() -> None:
    content, state = tiny()
    original = content.map_rows[3]
    content.map_rows[3] = original.replace(".", ",", 1)  # still a legal glyph, stale hash
    try:
        with pytest.raises(ValueError, match="map does not match"):
            begin_observation_tick(state, 1, content)
    finally:
        content.map_rows[3] = original
    expected = run_tick(content, state, 1)
    assert expected.physical_samples_by_actor  # the refused bind poisoned no cache


def test_content_matching_itself_but_not_the_world_state_is_refused() -> None:
    content, state = tiny()
    state.config_hash = "1" * 64
    with pytest.raises(ValueError, match="do not match the world state"):
        begin_observation_tick(state, 1, content)
    state.config_hash = content.config_hash
    state.map_hash = "2" * 64
    with pytest.raises(ValueError, match="do not match the world state"):
        begin_observation_tick(state, 1, content)


def test_identical_state_and_valid_content_give_a_byte_identical_batch() -> None:
    first_content, first_state = tiny(day_radius_tiles=3)
    second_content, second_state = tiny(day_radius_tiles=3)
    assert first_content is not second_content
    one = run_tick(first_content, first_state, 1, {"ella": [c(4, 2), c(5, 2)]})
    two = run_tick(second_content, second_state, 1, {"ella": [c(4, 2), c(5, 2)]})
    assert canonical_json_bytes(one.model_dump(mode="json")) == canonical_json_bytes(
        two.model_dump(mode="json")
    )
