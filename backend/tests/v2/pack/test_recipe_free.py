import re
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]
REAL_PACKS = BACKEND.parent / "content/packs"
ENGINE_TEST = BACKEND / "tests/fixtures/v2/packs/engine-test"
WORLD_V2 = BACKEND / "src/living_island/world/v2"
RECIPE_FILES = {"archetypes.toml": "archetype", "materials.toml": "material", "rules.toml": "rule"}


def authored_ids(directory: Path, sections: dict[str, str]) -> set[str]:
    ids: set[str] = set()
    for filename, section in sections.items():
        path = directory / filename
        if path.is_file():
            # Scan the authored IDs without binding compatibility settings.
            rows = tomllib.loads(path.read_text(encoding="utf-8")).get(section, [])
            ids.update(row["id"] for row in rows)
    return ids


def real_pack_ids(root: Path, sections: dict[str, str]) -> set[str]:
    return {
        member
        for manifest in root.glob("*/pack.toml")
        for member in authored_ids(manifest.parent, sections)
    }


def recipe_id_locations(source: Path, ids: set[str]) -> list[str]:
    locations = []
    for path in sorted(source.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for member in sorted(ids.intersection(re.findall(r"\w+", line))):
                locations.append(f"{path.relative_to(source).as_posix()}:{number}: {member}")
    return locations


def test_ct14_synthetic_ids_are_disjoint_from_real_ids() -> None:
    sections = {**RECIPE_FILES, "instances.toml": "instance"}
    shared = authored_ids(ENGINE_TEST, sections) & real_pack_ids(REAL_PACKS, sections)
    assert not shared, sorted(shared)


def test_en22_world_v2_is_recipe_free() -> None:
    assert not recipe_id_locations(WORLD_V2, real_pack_ids(REAL_PACKS, RECIPE_FILES))


@pytest.mark.parametrize(("filename", "section"), RECIPE_FILES.items())
def test_en22_scan_detects_planted_id(tmp_path: Path, filename: str, section: str) -> None:
    root = tmp_path / "packs"
    pack = root / "planted"
    pack.mkdir(parents=True)
    (pack / "pack.toml").write_text('pack_id = "planted"\n', encoding="utf-8")
    for unused in RECIPE_FILES.keys() - {filename}:
        (pack / unused).touch()
    (pack / filename).write_text(f'[[{section}]]\nid = "planted_id"\n', encoding="utf-8")

    source = tmp_path / "world/v2"
    nested = source / "engine"
    nested.mkdir(parents=True)
    module = nested / "example.py"
    module.write_text('value = "other_planted_id"\nplanted_id_suffix = 1\n', encoding="utf-8")
    ids = real_pack_ids(root, RECIPE_FILES)
    assert recipe_id_locations(source, ids) == []

    with module.open("a", encoding="utf-8") as stream:
        stream.write('value = "planted_id"\n')
    assert recipe_id_locations(source, ids) == ["engine/example.py:3: planted_id"]
