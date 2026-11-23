"""CT-04, CT-12 and CT-18 on the registered island and the authored starter rules."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from shutil import copytree
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.sim.v2.scenarios.starter import StarterScenario
    from living_island.world.v2.engine import WorldSetup
    from living_island.world.v2.protocol import Coord

ROOT = Path(__file__).resolve().parents[5]
CONTENT = ROOT / "content"
ISLAND = CONTENT / "worlds/default-island.map"
DEFAULT = CONTENT / "worlds/default.toml"
PROBES = Path(__file__).with_name("probes.toml")

# Starter §5.8. Tile, terrain, material, store archetype, opening stock/capacity.
DEPOSITS = {
    "clay_bank_01": ((37, 31), "grass", "clay", "clay_lump", 16),
    "grass_patch_01": ((30, 34), "grass", "grass", "grass_tuft", 12),
    "stone_outcrop_01": ((37, 28), "grass", "stone", "stone", 20),
    "grass_patch_02": ((40, 36), "grass", "grass", "grass_tuft", 12),
    "flint_scatter_01": ((28, 25), "grass", "flint", "flint_nodule", 12),
    "deadwood_02": ((31, 22), "woods", "wood", "branch", 8),
    "deadwood_01": ((47, 31), "woods", "wood", "branch", 8),
    "vine_tangle_02": ((36, 44), "woods", "vine", "vine", 10),
    "flint_scatter_02": ((27, 41), "grass", "flint", "flint_nodule", 12),
    "vine_tangle_01": ((48, 26), "woods", "vine", "vine", 10),
}

VERBS = {
    "gather_deposit",
    "knap_flake",
    "twist_cord",
    "make_stone_axe",
    "bind_snaps",
    "cut_wood_with_axe",
    "light_fire",
    "feed_fire",
    "shape_pot",
    "fill_pot",
    "drink_from_pot",
    "mark_shelter_site",
    "sleep_in_shelter",
}
WORLD_RULES = {
    "regrow_deadwood",
    "regrow_grass",
    "bake_pot",
    "fire_burns",
    "fire_goes_out",
    "fruit_rots",
    "rotten_fruit_crumbles",
    "axe_breaks",
    "finish_shelter",
}


def edit(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(before) == 1, (path, before)
    path.write_text(text.replace(before, after), encoding="utf-8")


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write("\n" + text + "\n")


@dataclass(frozen=True)
class Case:
    config: Path
    leaf: Path

    def load(self, *, map_path: Path = ISLAND, seed: int | None = None) -> StarterScenario:
        from living_island.sim.v2.scenarios.starter import load_starter_pack
        from living_island.world.v2.rules import load_vocabulary

        vocabulary = load_vocabulary(CONTENT / "vocabulary/vocab-0.1.toml")
        return load_starter_pack(self.config, self.leaf, vocabulary, map_path=map_path, seed=seed)

    def copy(self, root: Path) -> Case:
        copytree(self.leaf.parent / "compat-v1", root / "compat-v1")
        return replace(self, leaf=copytree(self.leaf, root / self.leaf.name))


@pytest.fixture(scope="module")
def case() -> Case:
    return Case(DEFAULT, CONTENT / "packs/starter-v1")


def test_ct04_composition(case: Case, tmp_path: Path) -> None:
    from living_island.sim.v2.compat.registry import REGISTRY
    from living_island.world.v2.rules import ContentError

    scenario = case.load()
    pack = scenario.pack
    data = pack.data
    assert pack.pack_ids == ("compat-v1", "starter-v1") == scenario.setup.pack_ids
    assert pack.pack_version == "0.1"
    assert "compat_codes" not in data
    assert (
        pack.vocabulary_hash == "57554435492d6f3db83006a4510b292f8b0d1ebc70c3393663fd1a9ad94cf286"
    )
    assert scenario.manifest.config_blob_sha256 == REGISTRY["production"].digest
    assert data["timing"]["give_ticks"] == 1
    assert set(data["timing"]["attempt_ticks"].values()) == {1}
    assert data["sight_while_asleep"] is False
    assert data["physiology"]["satiety_asleep_decay_per_tick"] == 15
    assert data["physiology"]["hydration_asleep_decay_per_tick"] == 60
    assert data["material"]["vine"]["apparent"] == {"strength": 4}
    assert data["material"]["grass"]["apparent"] == {"strength": 1}
    assert data["unmatched"]["gather"] == {"entries": [], "default": ["finds_nothing"]}
    assert pack.report.slot_coverage.keys() == pack.rules.keys()

    # Compare parsed operands (including array order) to the literal TOML in the frozen spec.
    spec = (ROOT / "docs/spec/starter-content-v0.1.md").read_text(encoding="utf-8")
    section = spec.split("### 5.10 Exact encodings", 1)[1]
    expected_rules = tomllib.loads(section.split("```toml", 1)[1].split("```", 1)[0])["rule"]
    assert {row["id"] for row in expected_rules} == {
        "bind_snaps",
        "knap_flake",
        "light_fire",
        "fill_pot",
        "fruit_rots",
        "compat_regrow_fruit",
    }
    for expected in expected_rules:
        rule = pack.rules[expected["id"]].data
        layer = "compat-v1" if expected["id"] == "compat_regrow_fruit" else pack.pack_id
        assert rule["provenance"] == {"kind": "authored", "pack_id": layer}
        for key, value in expected["phenomena"].items():
            assert rule["phenomena"][key] == value
        assert {k: rule[k] for k in expected if k != "phenomena"} == {
            k: v for k, v in expected.items() if k != "phenomena"
        }

    seeded = case.load(seed=1007489817)
    assert seeded.setup.seed == seeded.manifest.seed == 1007489817
    assert seeded.manifest.effective_config_sha256 != scenario.manifest.effective_config_sha256
    assert seeded.pack.pack_hash == pack.pack_hash

    altered = case.copy(tmp_path / "altered")
    parent = altered.leaf.parent / "compat-v1/materials.toml"
    edit(parent, "edible = true", "edible = true, dry = true")
    changed = altered.load().pack
    assert changed.ancestors[0].pack_hash != pack.ancestors[0].pack_hash
    assert changed.pack_hash != pack.pack_hash
    assert changed.data["material"]["fruit"]["properties"]["dry"]

    duplicate = case.copy(tmp_path / "duplicate")
    append(duplicate.leaf / "materials.toml", '[[material]]\nid = "wood"')
    with pytest.raises(ContentError, match="DUPLICATE_ID at material: wood"):
        duplicate.load()
    unbounded = case.copy(tmp_path / "unbounded")
    rules_file = unbounded.leaf / "rules.toml"
    condition = next(
        s for s in rules_file.read_text(encoding="utf-8").splitlines() if 'id = "nodule"' in s
    )
    edit(rules_file, condition, "conditions = []")
    with pytest.raises(ContentError, match="CONSERVATION at knap_flake: unproven joint debit"):
        unbounded.load()
    for path, message in (
        (case.config, "unregistered v1 config blob"),
        (ISLAND, "map blob SHA-256"),
    ):
        wrong = tmp_path / path.name
        wrong.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(ValueError, match=message):
            if path == ISLAND:
                case.load(map_path=wrong)
            else:
                replace(case, config=wrong).load()


def move_resident(setup: WorldSetup, actor: str, position: Coord) -> WorldSetup:
    residents = tuple(
        row.model_copy(update={"position": position}) if row.id == actor else row
        for row in setup.residents
    )
    return setup.model_copy(update={"residents": residents})


def test_ct12_deposits_and_adjacent_perceptions(case: Case) -> None:
    from living_island.sim.v2.compat.registry import ISLAND_MAP
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.kernel import neighbors
    from living_island.world.v2.protocol import Coord

    scenario = case.load()
    pack, setup = scenario.pack, scenario.setup
    rows = pack.data["instance"]
    assert scenario.manifest.map_blob_sha256 == setup.map_hash == ISLAND_MAP
    assert {k for k, row in rows.items() if row["archetype"] == "deposit"} == DEPOSITS.keys()
    assert {k for k, row in rows.items() if row["archetype"] == "canteen"} == {"canteen_01"}
    assert rows["canteen_01"]["at"] == {"holder": "ryan"}
    assert rows["canteen_01"]["owner_id"] == "ryan"
    assert rows["canteen_01"]["contents"] == ["canteen_01_water"]
    trees = {k for k, row in rows.items() if row["archetype"] == "fruit_tree"}
    assert trees == {f"fruit_{i:02}" for i in range(1, 7)}
    cfg = tomllib.loads(case.config.read_text(encoding="utf-8"))["world"]
    occupied = {tuple(cfg["initial_cave"]), tuple(cfg["spring"])}
    occupied.update((row.position.x, row.position.y) for row in (*setup.residents, *setup.cues))
    occupied.update(tuple(rows[k]["at"]["tile"]) for k in trees)
    terrain = setup.static_map()
    for key, (tile, land, material, item, stock) in DEPOSITS.items():
        x, y = tile
        point = Coord(x=x, y=y)
        assert tile not in occupied
        occupied.add(tile)
        assert rows[key]["at"] == {"tile": [x, y]}
        assert terrain.terrain(point) == land and terrain.cost(point) is not None
        assert rows[key]["material"] == material
        assert rows[key]["state"]["store"] == {"archetype": item, "capacity": stock, "count": stock}
        adjacent = next(p for p in neighbors(point) if terrain.cost(p) is not None)
        world = initialize(pack, move_resident(setup, "ella", adjacent))
        packet = next(p.perception for p in world.pending_packets() if p.actor_id == "ella")
        assert packet.awareness == "awake" and packet.own_position == adjacent
        look = next(v for v in packet.visible_entities if v.entity_id == key)
        assert (look.kind, look.archetype_id, look.material_id, look.position) == (
            "feature",
            "deposit",
            material,
            point,
        )
        assert ("stock_amount", "plenty") in [(d.property_id, d.value) for d in look.descriptors]


def opening_turn(actor: str, action: str, target: str, *, verb=None, instruments=()) -> dict:
    turn_id = f"{actor}:t000000"
    return {
        "schema_version": "wap/0.1",
        "turn_id": turn_id,
        "actor_id": actor,
        "observed_tick": 0,
        "utterance": None,
        "action": {
            "kind": "intent",
            "intent": {
                "intent_id": f"{turn_id}:a",
                "turn_id": turn_id,
                "actor_id": actor,
                "action": action,
                "verb": verb,
                "target": {"kind": "entity", "id": target},
                "instruments": [{"kind": "item", "id": item} for item in instruments],
                "inputs": [],
                "params": {},
                "reason": None,
            },
        },
    }


def test_ct18_normalization_and_corpse_reserve(case: Case, tmp_path: Path) -> None:
    from living_island.world.v2.engine import initialize
    from living_island.world.v2.engine.snapshot import encode_snapshot
    from living_island.world.v2.protocol import Coord
    from living_island.world.v2.rules import ContentError

    scenario = case.load()
    repeated = case.load()
    assert repeated == scenario
    world = initialize(scenario.pack, scenario.setup)
    assert encode_snapshot(initialize(repeated.pack, repeated.setup)) == encode_snapshot(world)
    pack = scenario.pack
    assert world.state.library.ancestor_pack_hashes == tuple(
        layer.pack_hash for layer in pack.ancestors
    )
    assert world.state.library.pack_hash == pack.pack_hash
    assert world.state.library.rule_library_hash == pack.rule_library_hash
    assert world.state.library.vocabulary_hash == pack.vocabulary_hash
    inherited = {
        key for key, rule in pack.rules.items() if rule.data["provenance"]["pack_id"] == "compat-v1"
    }
    assert len(inherited) == 9
    assert set(pack.rules) == inherited | VERBS | WORLD_RULES
    for key, rule in pack.rules.items():
        row = rule.data
        assert all(
            isinstance(row[field], list)
            for field in ("conditions", "instruments", "inputs", "outputs", "effects")
        )
        if row["trigger"].startswith("verb:"):
            assert key in inherited | VERBS
            assert row["on_interrupt"] == "lose"
            assert row["phenomena"]["unmet"] == ["nothing_happens"]
        else:
            assert key in inherited | WORLD_RULES
            assert "work_ticks" not in row and row["instruments"] == []

    # The witness worlds start with actual zero-wear and zero-work entities.
    implicit = case.copy(tmp_path / "implicit")
    append(implicit.leaf / "instances.toml", PROBES.read_text(encoding="utf-8"))
    explicit = implicit.copy(tmp_path / "explicit")
    arches = explicit.leaf / "archetypes.toml"
    edit(arches, "max_wear = 20", "max_wear = 20, wear = 0")
    edit(arches, "work_required = 24", "work_required = 24, work_done = 0")
    edit(
        explicit.leaf / "rules.toml",
        'id = "twist_cord"',
        'id = "twist_cord"\neffects = []\nconditions = []\ninstruments = []',
    )
    edit(
        explicit.leaf / "rules.toml",
        'id = "fire_burns"',
        'id = "fire_burns"\ninputs = []\noutputs = []',
    )
    pair = [c.load() for c in (implicit, explicit)]
    assert pair[0].pack.rules == pair[1].pack.rules
    worlds = [initialize(s.pack, move_resident(s.setup, "ryan", Coord(x=31, y=22))) for s in pair]
    assert encode_snapshot(worlds[0]) == encode_snapshot(worlds[1])
    assert worlds[0].state.entities["probe_axe"].components["durability"]["wear"] == 0
    assert worlds[0].state.entities["probe_site"].components["process"]["work_done"] == 0
    turns = [
        opening_turn("ryan", "act", "deadwood_02", verb="cut", instruments=("probe_axe",)),
        opening_turn("ella", "contribute", "probe_site"),
    ]
    for submissions in (turns, []):
        results = [
            w.step(
                submissions, acknowledged={p.actor_id: p.delivery_id for p in w.pending_packets()}
            )
            for w in worlds
        ]
        assert results[0] == results[1]
        assert encode_snapshot(worlds[0]) == encode_snapshot(worlds[1])
    assert worlds[0].state.entities["probe_axe"].components["durability"]["wear"] == 1
    assert worlds[0].state.entities["probe_site"].components["process"]["work_done"] > 0

    invalid = case.copy(tmp_path / "world-work")
    edit(invalid.leaf / "rules.toml", 'id = "fire_burns"', 'id = "fire_burns"\nwork_ticks = 1')
    with pytest.raises(ContentError, match="BAD_SHAPE at fire_burns:.*work_ticks"):
        invalid.load()

    units = sum(e.quantity for e in world.state.entities.values())
    living = sum(r.alive for r in world.state.residents.values())
    exact = units + living
    limited = case.copy(tmp_path / "reserve")
    limits = limited.leaf / "pack.toml"
    append(
        limits,
        f"[limits]\nreplace = true\nmax_entities_per_tile = 16\nmax_entity_units_world = {exact}",
    )
    admitted = limited.load()
    initialize(admitted.pack, admitted.setup)
    edit(limits, f"max_entity_units_world = {exact}", f"max_entity_units_world = {exact - 1}")
    refused = limited.load()
    with pytest.raises(ValueError, match="initial placements exceed entity limits"):
        initialize(refused.pack, refused.setup)
