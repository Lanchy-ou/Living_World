"""Physical sampling and descriptors (World Rules §5.1-§5.2, Interface Contract §2.2, §2.5)."""

from __future__ import annotations

import json

from world_builders import default_content, fresh_state, place, resident, tiny_content

from living_island.world.content import WorldContent
from living_island.world.perception import (
    Sight,
    fruit_band,
    need_band,
    own_condition,
    own_inventory,
    sample_sight,
    visible_signs,
)
from living_island.world.protocol import Coord
from living_island.world.space import StaticMap
from living_island.world.state import GroundFruitPile, UniqueCanteenState, WorldState

TINY = [
    "~~~~~~~~~~~~~~~~",
    "~...M..........~",
    "~.........F....~",
    "~..............~",
    "~.C..........S.~",
    "~~~~~~~~~~~~~~~~",
]
POS = {"ella": (3, 3), "ryan": (3, 4), "mia": (12, 3)}


def tiny(**perception: int) -> tuple[WorldContent, WorldState, StaticMap]:
    content = tiny_content(TINY, POS, **perception)
    return content, fresh_state(content), StaticMap.from_content(content)


def sight(
    content: WorldContent, state: WorldState, smap: StaticMap, who: str, tick: int = 1
) -> Sight:
    pos = resident(state, who).position
    return sample_sight(smap, content.config, state, who, pos, tick)


def ids(s: Sight) -> list[str]:
    return [e.entity_id for e in s.entities]


# --------------------------------------------------------------------- descriptors


def test_need_bands_follow_the_cutoffs() -> None:
    cut = [2000, 4000, 6000, 8000]
    assert [
        need_band(v, cut) for v in (0, 1999, 2000, 3999, 4000, 5999, 6000, 7999, 8000, 10000)
    ] == [
        "critical",
        "critical",
        "low",
        "low",
        "moderate",
        "moderate",
        "good",
        "good",
        "strong",
        "strong",
    ]


def test_fruit_bands() -> None:
    cfg = default_content().config  # fruit_few_max = 2
    assert [fruit_band(cfg, n) for n in (0, 1, 2, 3, 5)] == ["empty", "few", "few", "many", "many"]


def test_visible_signs_are_ordered_and_threshold_based() -> None:
    content, state, _ = tiny()
    mia = resident(state, "mia")
    cfg = content.config
    assert visible_signs(cfg, mia) == ()
    mia.health = cfg.perception.visible_weakness_health_below - 1
    mia.stamina = cfg.perception.visible_fatigue_stamina_below - 1
    assert visible_signs(cfg, mia) == ("weak", "fatigued")
    mia.hydration = cfg.perception.visible_dehydration_hydration_below - 1
    assert visible_signs(cfg, mia) == ("weak", "dehydrated", "fatigued")
    mia.health = cfg.perception.visible_weakness_health_below  # not below
    assert visible_signs(cfg, mia) == ("dehydrated", "fatigued")


def test_own_condition_and_exact_inventory() -> None:
    content, state, _ = tiny()
    ella, holder = resident(state, "ella"), state.unique_canteen.holder_id
    cond = own_condition(content.config, ella)
    assert cond.satiety == "good" and cond.hydration == "strong" and cond.health == "strong"
    ella.fruit_count = 3
    inv = own_inventory(state, ella)
    assert inv.fruit_count == 3
    assert (inv.canteen_id, inv.canteen_servings) == (
        ("canteen_01", 2) if holder == "ella" else (None, None)
    )
    other = resident(state, "ryan")
    assert (own_inventory(state, other).canteen_id is None) == (holder != "ryan")


# --------------------------------------------------------------------- entities


def test_entities_exclude_self_and_sort_by_id() -> None:
    content, state, smap = tiny()
    place(state, "mia", 5, 3)
    s = sight(content, state, smap, "ella")
    assert "ella" not in ids(s)
    assert ids(s) == sorted(ids(s)) == ["fruit_01", "mia", "ryan"]


def test_visible_fruit_tree_exposes_band_not_stock() -> None:
    content, state, smap = tiny()
    state.fruit_nodes[0].stock = 4
    tree = next(
        e for e in sight(content, state, smap, "ella").entities if e.entity_id == "fruit_01"
    )
    assert (tree.entity_type, tree.fruit_band, tree.quantity) == ("fruit_tree", "many", None)


def test_ground_fruit_has_spatial_id_and_exact_quantity() -> None:
    content, state, smap = tiny()
    state.ground_fruit = [GroundFruitPile(position=Coord(x=4, y=3), quantity=7)]
    pile = next(
        e for e in sight(content, state, smap, "ella").entities if e.entity_type == "ground_fruit"
    )
    assert (pile.entity_id, pile.quantity, pile.fruit_band) == ("ground_fruit@4,3", 7, None)


def test_ground_canteen_is_an_entity_and_a_carried_one_is_not() -> None:
    content, state, smap = tiny()
    assert "canteen_01" not in ids(sight(content, state, smap, "ella"))
    state.unique_canteen = UniqueCanteenState(
        id="canteen_01", holder_id=None, ground_position=Coord(x=5, y=3), servings=2
    )
    s = sight(content, state, smap, "ella")
    canteen = next(e for e in s.entities if e.entity_type == "canteen")
    assert (canteen.entity_id, canteen.position) == ("canteen_01", Coord(x=5, y=3))


def test_dead_residents_are_not_entities_but_corpses_are() -> None:
    content, state, smap = tiny()
    from living_island.world.state import CorpseState

    ryan = resident(state, "ryan")
    ryan.alive = False
    state.corpses = [
        CorpseState(id="corpse@ryan", resident_id="ryan", position=ryan.position, death_tick=1)
    ]
    s = sight(content, state, smap, "ella")
    assert "ryan" not in ids(s)
    assert next(e for e in s.entities if e.entity_id == "corpse@ryan").entity_type == "corpse"


def test_resident_signs_are_captured_in_the_sample() -> None:
    content, state, smap = tiny()
    resident(state, "ryan").hydration = 100
    ryan = next(e for e in sight(content, state, smap, "ella").entities if e.entity_id == "ryan")
    assert ryan.observable_signs == ("dehydrated",)
    assert ryan.fruit_band is None and ryan.quantity is None


def test_nothing_outside_sight_is_exposed() -> None:
    content, state, smap = tiny(day_radius_tiles=2)
    s = sight(content, state, smap, "ella")
    assert "mia" not in ids(s) and "fruit_01" not in ids(s)  # both beyond radius 2
    assert "ryan" in ids(s)  # at distance 1


def test_blocked_sight_hides_entities() -> None:
    rows = list(TINY)
    rows[3] = "~...W..........~"  # woods between ella (3,3) and mia
    content = tiny_content(rows, {"ella": (3, 3), "ryan": (3, 4), "mia": (6, 3)})
    state = fresh_state(content)
    smap = StaticMap.from_content(content)
    assert "mia" not in ids(sight(content, state, smap, "ella"))


# --------------------------------------------------------------------- cues


def test_distant_cue_gives_generic_description_without_direction() -> None:
    content, state, smap = tiny()
    place(state, "ella", 8, 1)  # moss at (4,1): distance 4 in sight
    cue = sight(content, state, smap, "ella").cues[0]
    spec = content.config.world.cues[0]
    assert (cue.detail_level, cue.direction) == ("distant", None)
    assert cue.physical_description == spec.visible_description


def test_near_cue_needs_the_detail_radius_and_carries_direction() -> None:
    content, state, smap = tiny()
    place(state, "ella", 5, 1)  # distance 1 == cue_detail_radius_tiles
    cue = sight(content, state, smap, "ella").cues[0]
    spec = content.config.world.cues[0]
    assert (cue.detail_level, cue.direction) == ("near", "east")
    assert cue.physical_description == spec.near_description
    place(state, "ella", 6, 1)  # distance 2: still visible, no detail
    assert sight(content, state, smap, "ella").cues[0].detail_level == "distant"


def test_near_cue_requires_line_of_sight() -> None:
    content = tiny_content(TINY, POS, cue_detail_radius_tiles=3)
    state = fresh_state(content)
    smap = StaticMap.from_content(content)
    place(state, "ella", 4, 3)  # distance 2, clear
    assert sight(content, state, smap, "ella").cues[0].detail_level == "near"

    blocked = list(TINY)
    blocked[2] = "~...W.....F....~"  # woods directly between (4,3) and the moss (4,1)
    content2 = tiny_content(blocked, POS, cue_detail_radius_tiles=3)
    state2 = fresh_state(content2)
    smap2 = StaticMap.from_content(content2)
    place(state2, "ella", 4, 3)
    assert sight(content2, state2, smap2, "ella").cues == ()  # no LOS: not even distant


def test_night_radius_applies_to_the_completed_tick() -> None:
    content, state, smap = tiny(day_radius_tiles=8, night_radius_tiles=1)
    day = sight(content, state, smap, "ella", tick=1)
    night = sight(content, state, smap, "ella", tick=84)
    assert len(night.tile_indices) < len(day.tile_indices)
    assert len(night.tile_indices) <= 5  # radius 1 Manhattan ball (clipped never larger)


# --------------------------------------------------------------------- leaks (AI-02 style)


def test_sight_contains_no_hidden_spring_exact_needs_or_remote_stock() -> None:
    content = default_content()
    state = fresh_state(content)
    smap = StaticMap.from_content(content)
    # Unique, recognisable values everywhere outside the observer's reach.
    resident(state, "mia").satiety = 4321
    for node in state.fruit_nodes:
        node.stock = 3
    s = sight(content, state, smap, "ella", tick=0)
    spring = state.spring
    seen = {(i % smap.width, i // smap.width) for i in s.tile_indices}
    assert (spring.x, spring.y) not in seen
    assert not any(smap.terrain(x, y) == "spring" for x, y in seen)
    blob = json.dumps(
        [
            [e.entity_id, e.entity_type, e.fruit_band, e.quantity, list(e.observable_signs)]
            for e in s.entities
        ]
    )
    assert "4321" not in blob
    # Only the one fruit tree near the cave start is within reach of the three residents.
    assert all(e.entity_id != "fruit_02" for e in s.entities)  # remote tree: no stock exposed
    assert not any(c.direction and "spring" in c.physical_description for c in s.cues)
