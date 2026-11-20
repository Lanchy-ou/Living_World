import ast
import re
import tomllib
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[3]
REAL_PACKS = BACKEND.parent / "content/packs"
ENGINE_TEST = BACKEND / "tests/fixtures/v2/packs/engine-test"
WORLD_V2 = BACKEND / "src/living_island/world/v2"
RECIPE_SECTIONS = ("archetype", "material", "rule")
CONTENT_SECTIONS = (*RECIPE_SECTIONS, "instance")
EXCLUDED_FILES = {"pack.toml", "compat-codes.toml"}


def authored_ids(directory: Path, sections: tuple[str, ...]) -> set[str]:
    ids: set[str] = set()
    for path in directory.rglob("*.toml"):
        if path.name in EXCLUDED_FILES:
            continue
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        for section in sections:
            entries = data.get(section, [])
            # Whole-section placeholders are bound by the pack's loader.
            if isinstance(entries, str):
                continue
            rows = [entries] if isinstance(entries, dict) else entries
            ids.update(row["id"] for row in rows)
    return ids


def real_pack_ids(root: Path, sections: tuple[str, ...]) -> set[str]:
    return {
        member
        for manifest in root.glob("*/pack.toml")
        for member in authored_ids(manifest.parent, sections)
    }


def terrain_literal_lines(module: str, source: str) -> Counter[int]:
    """Identify the protocol and validator declarations of the shared terrain term."""
    match module:
        case "protocol.py":
            declaration_name = "Terrain"
        case "rules/schema.py":
            declaration_name = "TERRAINS"
        case _:
            return Counter()

    lines: Counter[int] = Counter()
    for statement in ast.parse(source).body:
        if not isinstance(statement, ast.Assign):
            continue
        target, *extra = statement.targets
        if extra or not isinstance(target, ast.Name) or target.id != declaration_name:
            continue
        match statement.value:
            case ast.Subscript(value=ast.Name(id="Literal"), slice=ast.Tuple(elts=members)):
                pass
            case ast.Call(func=ast.Name(id="frozenset"), args=[ast.Set(elts=members)], keywords=[]):
                pass
            case _:
                continue
        lines.update(
            node.lineno
            for node in members
            if isinstance(node, ast.Constant)
            and ast.get_source_segment(source, node) in {'"fruit_tree"', "'fruit_tree'"}
        )
    return lines


def recipe_id_locations(source: Path, ids: set[str]) -> list[str]:
    locations = []
    for path in sorted(source.rglob("*.py")):
        module = path.relative_to(source).as_posix()
        text = path.read_text(encoding="utf-8")
        terrain_lines = terrain_literal_lines(module, text)
        for number, line in enumerate(text.splitlines(), start=1):
            tokens = Counter(re.findall(r"\w+", line))
            tokens["fruit_tree"] -= terrain_lines[number]
            for member in sorted(ids.intersection(+tokens)):
                locations.append(f"{module}:{number}: {member}")
    return locations


def test_ct14_synthetic_ids_are_disjoint_from_real_ids() -> None:
    shared = authored_ids(ENGINE_TEST, CONTENT_SECTIONS) & real_pack_ids(
        REAL_PACKS, CONTENT_SECTIONS
    )
    assert not shared, sorted(shared)


def test_en22_world_v2_is_recipe_free() -> None:
    assert not recipe_id_locations(WORLD_V2, real_pack_ids(REAL_PACKS, RECIPE_SECTIONS))


@pytest.mark.parametrize("section", RECIPE_SECTIONS)
def test_en22_scan_detects_planted_id(tmp_path: Path, section: str) -> None:
    root = tmp_path / "packs"
    pack = root / "planted"
    pack.mkdir(parents=True)
    (pack / "pack.toml").write_text('pack_id = "planted"\n', encoding="utf-8")
    (pack / f"{section}s.toml").write_text(f'[[{section}]]\nid = "planted_id"\n', encoding="utf-8")

    source = tmp_path / "world/v2"
    nested = source / "engine"
    nested.mkdir(parents=True)
    module = nested / "example.py"
    module.write_text('value = "other_planted_id"\nplanted_id_suffix = 1\n', encoding="utf-8")
    ids = real_pack_ids(root, RECIPE_SECTIONS)
    assert recipe_id_locations(source, ids) == []

    with module.open("a", encoding="utf-8") as stream:
        stream.write('value = "planted_id"\n')
    assert recipe_id_locations(source, ids) == ["engine/example.py:3: planted_id"]


def test_recipe_scan_skips_bound_sections_and_excluded_files(tmp_path: Path) -> None:
    pack = tmp_path / "planted"
    pack.mkdir()
    (pack / "pack.toml").write_text('[rule]\nid = "manifest_value"\n', encoding="utf-8")
    (pack / "compat-codes.toml").write_text('[rule]\nid = "code_value"\n', encoding="utf-8")
    (pack / "rules.toml").write_text(
        'rule = "${rules}"\ninstance = "${instances}"\n[archetype]\nid = "planted_arch"\n',
        encoding="utf-8",
    )
    assert real_pack_ids(tmp_path, CONTENT_SECTIONS) == {"planted_arch"}


def test_en22_scan_detects_rules_from_a_second_file(tmp_path: Path) -> None:
    root = tmp_path / "packs"
    pack = root / "planted"
    pack.mkdir(parents=True)
    (pack / "pack.toml").write_text('pack_id = "planted"\n', encoding="utf-8")
    (pack / "rules.toml").write_text('[[rule]]\nid = "first_rule"\n', encoding="utf-8")
    (pack / "rule-templates.toml").write_text(
        '[rule]\nid = "second_rule"\n[instance]\nid = "planted_instance"\n', encoding="utf-8"
    )
    assert real_pack_ids(root, CONTENT_SECTIONS) == {
        "first_rule",
        "second_rule",
        "planted_instance",
    }

    source = tmp_path / "world/v2"
    source.mkdir(parents=True)
    (source / "example.py").write_text('value = "second_rule"\n', encoding="utf-8")
    assert recipe_id_locations(source, real_pack_ids(root, RECIPE_SECTIONS)) == [
        "example.py:1: second_rule"
    ]


@pytest.mark.parametrize(
    ("module", "declaration"),
    [
        ("protocol.py", 'Terrain = Literal["fruit_tree", "grass"]'),
        ("rules/schema.py", 'TERRAINS = frozenset({"fruit_tree", "grass"})'),
    ],
)
def test_en22_distinguishes_terrain_declarations_from_recipe_ids(
    tmp_path: Path, module: str, declaration: str
) -> None:
    path = tmp_path / module
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{declaration}\nrecipe = "fruit_tree"\n', encoding="utf-8")
    assert recipe_id_locations(tmp_path, {"fruit_tree", "grass"}) == [
        f"{module}:1: grass",
        f"{module}:2: fruit_tree",
    ]

    path.write_text(f'{declaration}; recipe = "fruit_tree"\n', encoding="utf-8")
    assert recipe_id_locations(tmp_path, {"fruit_tree"}) == [f"{module}:1: fruit_tree"]
