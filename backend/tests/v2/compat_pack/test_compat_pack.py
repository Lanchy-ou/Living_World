"""Load the compatibility content against the independently committed v1 pins."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import tomllib
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.sim.v2.compat import BoundCompatPack

ROOT = Path(__file__).resolve().parents[4]
CONTENT = ROOT / "content"
PACK = CONTENT / "packs/compat-v1"
VOCAB = CONTENT / "vocabulary/vocab-0.1.toml"
DEFAULT = CONTENT / "worlds/default.toml"
ISLAND = CONTENT / "worlds/default-island.map"
FIXTURES = ROOT / "backend/tests/fixtures/v1_projection"


def load(
    config: Path = DEFAULT,
    pack: Path = PACK,
    *,
    map_path: Path | None = None,
    seed: int | None = None,
) -> BoundCompatPack:
    from living_island.sim.v2.compat import load_compat_pack
    from living_island.world.v2.rules import load_vocabulary

    return load_compat_pack(config, pack, load_vocabulary(VOCAB), map_path=map_path, seed=seed)


def test_ct01_default_values_and_determinism() -> None:
    raw = tomllib.loads(DEFAULT.read_text(encoding="utf-8"))
    result = load()
    pack = result.pack
    assert result.config == raw
    assert pack.pack_id == "compat-v1"
    assert pack.data["inventory_slots"] == raw["inventory"]["slot_capacity"]
    assert pack.data["sight_while_asleep"] is True
    assert pack.data["limits"] == {"max_entities_per_tile": 16, "max_entity_units_world": 4000}
    assert {key: pack.data["timing"][key] for key in ("give_ticks", "sleep_ticks")} == {
        key: raw["actions"][key] for key in ("give_ticks", "sleep_ticks")
    }
    assert set(pack.data["timing"]["attempt_ticks"].values()) == {
        raw["actions"]["invalid_attempt_ticks"]
    }
    for need, gain, loss in (
        ("satiety", 2000, 0),
        ("hydration", 6000, 0),
        ("stamina", 220, 150),
        ("health", 0, 0),
    ):
        row = pack.data["needs"][need]
        assert row["initial"] == raw["needs"][f"initial_{need}"]
        assert row["min"] == raw["needs"]["min_value"]
        assert row["max"] == raw["needs"]["max_value"]
        assert row["band_cutoffs"] == raw["perception"]["need_band_cutoffs"]
        assert (row["max_gain_per_tick"], row["max_loss_per_tick"]) == (gain, loss)
        expected = (
            []
            if need == "health"
            else [{"id": "urgent", "at": raw["agents"][f"urgent_{need}_below"], "wakes": True}]
        )
        assert row["thresholds"] == expected
    physiology = pack.data["physiology"]
    for need in ("satiety", "hydration"):
        assert physiology[f"{need}_awake_decay_per_tick"] == raw["needs"][f"{need}_decay_per_tick"]
        assert physiology[f"{need}_asleep_decay_per_tick"] == raw["needs"][f"{need}_decay_per_tick"]
    plants = pack.data["instance"]
    for tree in raw["world"]["fruit_trees"]:
        item = plants[tree["id"]]
        assert item["at"] == {"tile": tree["position"]}
        assert item["state"]["store"]["count"] == raw["fruit"]["initial_stock_per_tree"]
        assert (
            item["phase_offset"].get("compat_regrow_fruit", 0) == tree["regrow_phase_offset_ticks"]
        )
    assert plants["canteen_01"]["at"] == {"holder": "ryan"}
    assert plants["canteen_01"]["owner_id"] == "ryan"
    assert plants["canteen_01"]["contents"] == ["canteen_01_water"]
    assert plants["canteen_01_water"]["at"] == {"holder": "canteen_01"}
    assert plants["canteen_01_water"]["quantity"] == raw["canteen"]["initial_servings"]
    gather = pack.rules["compat_gather_fruit"].data
    assert [check["id"] for check in gather["conditions"]] == ["stamina", "room", "stock"]
    assert gather["phenomena"]["unmet_by_check"] == {
        "stamina": ["too_tired"],
        "room": ["hands_full"],
        "stock": ["finds_nothing"],
    }
    assert gather["effects"][0]["from"] == "target.store"
    assert gather["exhaustion_stops"]
    assert pack.rules["compat_sleep_cave"].specificity > pack.rules["compat_sleep"].specificity
    assert load() == result


def test_wap34_all_registered_source_and_map_hashes(tmp_path: Path) -> None:
    from living_island.sim.v2.compat.registry import REGISTRY, materialize_fixture

    assert set(REGISTRY) == {
        "production",
        "s2-orig",
        "s1-orig",
        "s3-orig",
        "s4-orig",
        "p1-default",
        "mechanics",
        "give-3",
        "regrowth-2",
        "regrowth-0",
        "gather-1",
    }
    for name, entry in REGISTRY.items():
        if entry.substitution is not None:
            config = FIXTURES / "configs" / f"{name}.toml"
            assert materialize_fixture(DEFAULT.read_bytes(), name) == config.read_bytes()
        elif name == "s2-orig":
            config = tmp_path / "s2-orig.toml"
            config.write_bytes(
                subprocess.check_output(["git", "show", f"{entry.ref}:{entry.path}"], cwd=ROOT)
            )
        else:
            config = ROOT / entry.path
        map_path = config.parent / "mechanics.map" if name == "mechanics" else ISLAND
        result = load(config, map_path=map_path)
        assert sha256(config.read_bytes()).hexdigest() == result.manifest.config_blob_sha256
        assert result.manifest.config_blob_sha256 == entry.digest
        assert sha256(map_path.read_bytes()).hexdigest() == entry.map_digest
        assert result.manifest.map_blob_sha256 == result.manifest.map_sha256 == entry.map_digest
        assert result.map_rows == tuple(map_path.read_text(encoding="utf-8").splitlines())


def test_ct15_and_ct17_substitutions() -> None:
    def fixture(name: str) -> BoundCompatPack:
        return load(FIXTURES / "configs" / f"{name}.toml", map_path=ISLAND)

    give = fixture("give-3")
    assert give.pack.data["timing"]["give_ticks"] == 3
    regrow = fixture("regrowth-2").pack
    assert regrow.data["source"]["fruit_regrowth"]["max_per_application"] == 2
    assert regrow.rules["compat_regrow_fruit"].data["outputs"][0]["quantity"] == {
        "upto": 2,
        "of": "fit:subject.store",
    }
    zero = fixture("regrowth-0").pack
    assert "compat_regrow_fruit" not in zero.rules
    assert "fruit_regrowth" not in zero.data["source"]
    assert not any(row["phase_offset"] for row in zero.data["instance"].values())
    gather = fixture("gather-1")
    assert gather.pack.rules["compat_gather_fruit"].data["work_ticks"] == 1
    assert gather.pack.data["needs"]["stamina"]["max_loss_per_tick"] == 300
    for name, result in (
        ("ct15-ct17-regrowth-2", fixture("regrowth-2")),
        ("ct15-ct17-regrowth-0", fixture("regrowth-0")),
        ("ct17-one-tick-gather", gather),
    ):
        assert_fixture_manifest(result, FIXTURES / "scripted" / f"{name}.json.gz")


def assert_fixture_manifest(result: BoundCompatPack, fixture: Path) -> None:
    with gzip.open(fixture, "rt", encoding="utf-8") as stream:
        source = json.load(stream)["source"]
    assert asdict(result.manifest) == {field: source[field] for field in asdict(result.manifest)}


@pytest.mark.parametrize(
    ("config", "prefix"),
    [
        (DEFAULT, "acceptance-production-base-"),
        (CONTENT / "scenarios/s1-spring-visible/orig.toml", "development-s1-orig-base-"),
    ],
)
def test_wap34_canonical_seed_binding(config: Path, prefix: str) -> None:
    fixtures = sorted((FIXTURES / "matrix").glob(prefix + "*.json.gz"))
    assert len(fixtures) == 20
    baseline = load(config)
    for path in fixtures:
        seed = int(path.name.removeprefix(prefix).removesuffix(".json.gz"))
        result = load(config, seed=seed)
        assert result.config["meta"]["seed"] == seed
        assert result.pack.pack_hash == baseline.pack.pack_hash
        assert result.manifest.effective_config_sha256 != baseline.manifest.effective_config_sha256
        assert_fixture_manifest(result, path)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (b"talk_ticks = 1", b"talk_ticks = 2"),
        (b"sleep_ticks = 48", b"sleep_ticks = 60"),
        (b"fruit_few_max = 2", b"fruit_few_max = 3"),
        (b"capacity_servings = 2", b"capacity_servings = 3"),
        (b"capacity_servings = 2", b"capacity_servings = 3999"),
        (b"[2000, 4000, 6000, 8000]", b"[2001, 4000, 6000, 8000]"),
    ],
)
def test_unknown_config_refused_before_opening_map(
    tmp_path: Path, before: bytes, after: bytes
) -> None:
    path = tmp_path / "default.toml"
    raw = DEFAULT.read_bytes()
    assert raw.count(before) == 1
    path.write_bytes(raw.replace(before, after))
    with pytest.raises(ValueError, match="unregistered v1 config blob"):
        load(path)


def test_wap34_wrong_map_and_seed_refused(tmp_path: Path) -> None:
    wrong_map = tmp_path / "default-island.map"
    wrong_map.write_bytes(ISLAND.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="map blob SHA-256"):
        load(map_path=wrong_map)
    with pytest.raises(ValueError, match="unregistered P2 seed"):
        load(seed=1)


def test_wap34_production_manifest_and_registered_p2_seeds() -> None:
    from living_island.sim.v2.compat.config import P2_SEEDS

    matrix = FIXTURES / "matrix"
    seed = 1007489817
    assert_fixture_manifest(load(seed=seed), matrix / f"acceptance-production-base-{seed}.json.gz")
    fixture_seeds = {
        int(path.name.removesuffix(".json.gz").rsplit("-", 1)[1])
        for path in matrix.glob("*.json.gz")
    }
    assert P2_SEEDS == fixture_seeds


def test_wap34_materialization_requires_production_pin() -> None:
    from living_island.sim.v2.compat.registry import materialize_fixture

    with pytest.raises(ValueError, match="production config blob SHA-256"):
        materialize_fixture(DEFAULT.read_bytes() + b"\n", "give-3")
    with pytest.raises(ValueError, match="unregistered v1 fixture"):
        materialize_fixture(DEFAULT.read_bytes(), "production")


def test_ct03_unreachable_and_physical_dispositions() -> None:
    result = load()
    assert result.pack.report.unreachable_checks == (("compat_sleep_cave", "cave"),)
    assert result.codes["compat_sleep_cave"] == {"cave": "unreachable"}
    assert result.codes["compat_gather_fruit"]["world_limit"] == "defect"
    assert "compat_sleep" not in result.codes
    assert "compat_rest" not in result.codes
    assert "world_limit" not in result.codes["compat_drink_spring"]


@pytest.mark.parametrize(
    ("before", "after", "diagnostic"),
    [
        ('stock = "RESOURCE_TAKEN"\n', "", "missing.*stock"),
        ('stamina = "EXHAUSTED"', 'stamina = "unreachable"', "stamina.*invalid disposition"),
        ('food = "NO_ITEM"\n', "", "missing.*food"),
        ('world_limit = "defect"\n', "", "missing.*world_limit"),
        ('stock = "RESOURCE_TAKEN"', 'stock = "defect"', "stock.*invalid disposition"),
        ('stock = "RESOURCE_TAKEN"', "stock = true", "stock.*invalid disposition"),
        ('stock = "RESOURCE_TAKEN"', 'stock = "WRONG"', "stock.*invalid disposition"),
        ('stock = "RESOURCE_TAKEN"', 'stock = "RESOURCE_TAKEN"\nextra = "NO_ITEM"', "extra"),
        ("[compat_sleep_cave]", "[compat_sleep]", "missing.*cave"),
    ],
)
def test_ct03_reject_bad_code_table(
    tmp_path: Path, before: str, after: str, diagnostic: str
) -> None:
    from living_island.world.v2.rules import ContentError

    copy = shutil.copytree(PACK, tmp_path / PACK.name)
    path = copy / "compat-codes.toml"
    original = path.read_text(encoding="utf-8")
    assert before in original
    path.write_text(original.replace(before, after, 1), encoding="utf-8")
    with pytest.raises(ContentError, match=diagnostic):
        load(pack=copy)


@pytest.mark.parametrize("filename", ["rule-templates.toml", "rule-regrowth.toml"])
def test_template_rule_array_is_validated_at_load(tmp_path: Path, filename: str) -> None:
    from living_island.world.v2.rules import ContentError

    copy = shutil.copytree(PACK, tmp_path / PACK.name)
    (copy / filename).write_text("rule = false\n", encoding="utf-8")
    with pytest.raises(ContentError, match=rf"{filename}:rule.*expected an array"):
        load(pack=copy)


def test_ct03_reject_missing_code_file(tmp_path: Path) -> None:
    from living_island.world.v2.rules import ContentError

    copy = shutil.copytree(PACK, tmp_path / PACK.name)
    (copy / "compat-codes.toml").unlink()
    with pytest.raises(ContentError, match="missing compatibility code table"):
        load(pack=copy)
