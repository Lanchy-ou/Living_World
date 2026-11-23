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


def declaration_uses(module: str, source: str) -> Counter[tuple[int, str]]:
    """Identify individual keys in the closed terrain and component declarations."""
    uses: Counter[tuple[int, str]] = Counter()
    if module not in ("protocol.py", "rules/schema.py", "rules/vocabulary.py", "engine/state.py"):
        return uses
    for stmt in ast.parse(source).body:
        match module, stmt:
            case "protocol.py", ast.Assign(
                targets=[ast.Name(id="Terrain")],
                value=ast.Subscript(value=ast.Name(id="Literal"), slice=ast.Tuple(elts=members)),
            ):
                allowed = {"fruit_tree", "grass"}
            case "rules/schema.py", ast.Assign(
                targets=[ast.Name(id="TERRAINS")],
                value=ast.Call(func=ast.Name(id="frozenset"), args=[ast.Set(elts=members)]),
            ):
                allowed = {"fruit_tree", "grass"}
            case "rules/vocabulary.py", ast.Assign(
                targets=[ast.Name(id="COMPONENTS")], value=ast.Dict(keys=members)
            ):
                allowed = {"shelter"}
            case "engine/state.py", ast.ClassDef(name="Components", body=body):
                uses.update(
                    (field.lineno, "shelter")
                    for field in body
                    if isinstance(field, ast.AnnAssign)
                    and isinstance(field.target, ast.Name)
                    and field.target.id == "shelter"
                )
                continue
            case _:
                continue
        for member in members:
            if isinstance(member, ast.Constant) and member.value in allowed:
                # Only subtract an actual lexical occurrence (escapes can spell the same value).
                if ast.get_source_segment(source, member) in (
                    f'"{member.value}"',
                    f"'{member.value}'",
                ):
                    uses[member.lineno, member.value] += 1
    return uses


# These English phrases describe settlement or terrain in diagnostics, docs and comments.
GENERIC_PROSE = {
    "engine/validate.py": ("movement budget must cover all step costs, including grass",),
    "engine/effects.py": ("simulate a verb branch", "# A partial branch can refer"),
    "engine/limits.py": ("initialization and branch preflight",),
    "engine/processes.py": ("transfer its inputs as one branch",),
    "rules/conservation.py": ("each settlement branch", "branch credits exceed debits"),
    "engine/settle.py": ("admit only its selected branch",),
}


def operation_uses(module: str, source: str) -> Counter[tuple[int, str]]:
    uses: Counter[tuple[int, str]] = Counter()
    if module == "engine/settle.py":
        # The bound settlement local is an AppliedBranch. Literal IDs and
        # attributes (e.g. archetypes.branch) are different AST nodes.
        for fn in ast.parse(source).body:
            if not isinstance(fn, ast.FunctionDef) or fn.name not in (
                "phase_location",
                "complete_act",
                "interrupt",
            ):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Name) and node.id == "branch":
                    uses[node.lineno, "branch"] += 1
                elif isinstance(node, ast.arg) and node.arg == "branch":
                    uses[node.lineno, "branch"] += 1
    elif module in ("engine/kernel.py", "engine/validate.py"):
        for node in ast.walk(ast.parse(source)):
            match node:
                case ast.Subscript(
                    value=ast.Attribute(value=ast.Name(id="smap"), attr="step_costs"),
                    slice=ast.Constant(value="grass") as member,
                ) if module == "engine/kernel.py":
                    pass
                case ast.Compare(
                    left=ast.Constant(value="grass") as member,
                    ops=[ast.NotIn()],
                    comparators=[ast.Attribute(value=ast.Name(id="self"), attr="step_costs")],
                ) if module == "engine/validate.py":
                    pass
                case _:
                    continue
            if ast.get_source_segment(source, member) in ('"grass"', "'grass'"):
                uses[member.lineno, "grass"] += 1
    return uses


def recipe_id_locations(source: Path, ids: set[str]) -> list[str]:
    locations = []
    for path in sorted(source.rglob("*.py")):
        module = path.relative_to(source).as_posix()
        text = path.read_text(encoding="utf-8")
        uses = declaration_uses(module, text)
        uses.update(operation_uses(module, text))
        for number, line in enumerate(text.splitlines(), start=1):
            tokens = Counter(re.findall(r"\w+", line))
            for phrase in GENERIC_PROSE.get(module, ()):
                # Discount only the shared word, even if other IDs occur in the phrase.
                shared = "grass" if module == "engine/validate.py" else "branch"
                uses[number, shared] += len(re.findall(rf"(?<!\w){re.escape(phrase)}(?!\w)", line))
            for member in sorted(ids.intersection(tokens)):
                if tokens[member] > uses[number, member]:
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


def test_en22_distinguishes_generic_uses_from_same_line_recipes(tmp_path: Path) -> None:
    for module, context, member in (
        ("protocol.py", 'Terrain = Literal["fruit_tree", "grass"]', "fruit_tree"),
        ("rules/schema.py", 'TERRAINS = frozenset({"fruit_tree", "grass"})', "grass"),
        ("engine/kernel.py", 'cost = smap.step_costs["grass"]', "grass"),
        ("engine/validate.py", 'missing = "grass" not in self.step_costs', "grass"),
        ("rules/vocabulary.py", 'COMPONENTS = {"shelter": ("", "")}', "shelter"),
        ("engine/state.py", "class Components(TypedDict): shelter: NotRequired[dict]", "shelter"),
        ("engine/settle.py", "def interrupt(): branch = None", "branch"),
    ):
        path = tmp_path / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{context}; recipe = archetypes["{member}"]\n', encoding="utf-8")
        assert recipe_id_locations(tmp_path, {member}).count(f"{module}:1: {member}") == 1
        path.write_text(context + "\n", encoding="utf-8")
        assert f"{module}:1: {member}" not in recipe_id_locations(tmp_path, {member})
