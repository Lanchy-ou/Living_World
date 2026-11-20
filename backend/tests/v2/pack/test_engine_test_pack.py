from __future__ import annotations

import tomllib
from pathlib import Path
from shutil import copytree
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.rules import Pack, Vocabulary

BACKEND = Path(__file__).resolve().parents[3]
FIXTURES = BACKEND / "tests/fixtures/v2/packs"
ENGINE_TEST = FIXTURES / "engine-test"
VARIANTS = tomllib.loads(
    (FIXTURES / "engine-test-negative/variants.toml").read_text(encoding="utf-8")
)["variant"]


@pytest.fixture(scope="module")
def vocabulary() -> Vocabulary:
    # v1 trial registration fingerprints the modules imported during collection.
    from living_island.world.v2.rules import load_vocabulary

    return load_vocabulary(BACKEND.parent / "content/vocabulary/vocab-0.1.toml")


@pytest.fixture(scope="module")
def engine_test(vocabulary: Vocabulary) -> Pack:
    from living_island.world.v2.rules import load_pack

    return load_pack(ENGINE_TEST, vocabulary)


def test_ct14_closed_term_coverage(engine_test: Pack) -> None:
    from living_island.world.v2.rules.rule import CONDITIONS, EFFECTS, PLACES
    from living_island.world.v2.rules.vocabulary import COMPONENTS

    archetypes = engine_test.data["archetype"].values()
    components = {component for arch in archetypes for component in arch["components"]}
    predicates = [
        arch["components"]["container"]["accepts"]
        for arch in archetypes
        if "container" in arch["components"]
    ]
    triggers = set()
    conditions = set()
    operations = set()
    places = set()
    interruptions = set()
    for rule in engine_test.rules.values():
        data = rule.data
        trigger, _, _ = data["trigger"].partition(":")
        triggers.add(trigger)
        if "subject" in data:
            predicates.append(data["subject"])
        if "where" in data.get("target", {}):
            predicates.append(data["target"]["where"])
        predicates.extend(slot["where"] for slot in data["inputs"] + data.get("instruments", []))
        for condition in data["conditions"]:
            conditions.add(condition["kind"])
            if condition["kind"] == "entity_near":
                predicates.append(condition["where"])

        outputs = list(data["outputs"])
        if trigger == "verb":
            mode = data["on_interrupt"]
            if mode == "lose":
                interruptions.add(mode)
            else:
                interruptions.update(mode)
                outputs.extend(mode.get("partial", []))
        if outputs:
            operations.add("create")
            places.update(output["at"] for output in outputs)
        for effect in data["effects"] + data.get("chance_failed_effects", []):
            operations.add(effect["op"])
            if effect["op"] == "move":
                places.add(effect["to"])

    predicate_keys = {"archetype", "material", "has_component"}
    for name, prop in engine_test.vocabulary.properties.items():
        if prop["domain"] == "bool":
            predicate_keys.add(name)
        elif prop["domain"] == "scale":
            predicate_keys.update({f"{name}_min", f"{name}_max"})

    assert components == set(COMPONENTS)
    assert {key for predicate in predicates for key in predicate} == predicate_keys
    assert conditions == set(CONDITIONS)
    assert operations == {"create", *EFFECTS}
    assert triggers == {"verb", "every", "when"}
    assert places == PLACES
    assert interruptions == {"lose", "partial", "keep_progress"}


def test_ct14_world_setup(engine_test: Pack) -> None:
    world = tomllib.loads((ENGINE_TEST / "world.toml").read_text(encoding="utf-8"))
    rows = (ENGINE_TEST / world["map"]["layout_file"]).read_text(encoding="utf-8").splitlines()
    assert rows
    assert {len(row) for row in rows} == {len(rows[0])}
    assert len(world["residents"]) == len({resident["id"] for resident in world["residents"]}) == 2
    positions = [tuple(resident["position"]) for resident in world["residents"]]
    positions.extend(tuple(item["at"]["tile"]) for item in engine_test.data["instance"].values())
    assert len(positions) == len(set(positions))
    for x, y in positions:
        assert 0 <= x < len(rows[0]) and 0 <= y < len(rows)
        assert rows[y][x] in ".,WC"


def test_ct14_load_is_deterministic(engine_test: Pack, vocabulary: Vocabulary) -> None:
    from living_island.world.v2.rules import load_pack

    assert engine_test.pack_id == "engine-test"
    assert engine_test == load_pack(ENGINE_TEST, vocabulary)
    assert engine_test.report.slot_coverage["rule_d"]["slot_a"] == (("arch_a", "mat_a"),)


def test_ct14_negative_variants_cover_validator_codes() -> None:
    # Rule representation section 7.
    codes = [variant["code"] for variant in VARIANTS]
    assert sorted(codes) == [
        "BAD_SHAPE",
        "CONSERVATION",
        "DUPLICATE_ID",
        "INTERRUPT_MODE",
        "NEED_RATE",
        "OUT_OF_RANGE",
        "TELL_MISSING",
        "UNDECLARED_SOURCE",
        "UNKNOWN_TERM",
    ]


@pytest.mark.parametrize("variant", VARIANTS, ids=[variant["code"] for variant in VARIANTS])
def test_ct14_negative_variant(
    engine_test: Pack, vocabulary: Vocabulary, tmp_path: Path, variant: dict[str, str]
) -> None:
    from living_island.world.v2.rules import ContentError, load_pack

    directory = tmp_path / engine_test.pack_id
    copytree(ENGINE_TEST, directory)
    file = directory / variant["file"]
    original = file.read_text(encoding="utf-8")
    assert original.count(variant["old"]) == 1
    file.write_text(original.replace(variant["old"], variant["new"]), encoding="utf-8")
    with pytest.raises(ContentError) as error:
        load_pack(directory, vocabulary)
    assert (error.value.issue.code, error.value.issue.path) == (variant["code"], variant["path"])
