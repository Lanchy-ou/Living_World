"""M12 static rule pack acceptance checks."""

from __future__ import annotations

import shutil
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.rules import Pack, Vocabulary


FIXTURES = Path(__file__).parent / "fixtures"
VOCABULARY = Path(__file__).resolve().parents[4] / "content/vocabulary/vocab-0.1.toml"
CASES = tomllib.loads((FIXTURES / "errors.toml").read_text(encoding="utf-8"))["case"]


@pytest.fixture
def vocab() -> Vocabulary:
    # The frozen v1 registration tests examine all loaded package modules.
    # Keep v2 out of that inventory during pytest collection.
    from living_island.world.v2.rules import load_vocabulary

    return load_vocabulary(VOCABULARY)


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    path = tmp_path / "sample"
    shutil.copytree(FIXTURES / "sample", path)
    return path


def load(path: Path, vocab: Vocabulary) -> Pack:
    from living_island.world.v2.rules import load_pack

    return load_pack(path, vocab, bindings={"vocabulary_hash": vocab.vocabulary_hash})


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def add_rule(path: Path, body: str) -> None:
    with (path / "rules.toml").open("a", encoding="utf-8") as stream:
        stream.write("\n\n[[rule]]\n" + body.strip() + "\n")


def refused(path: Path, vocab: Vocabulary, code: str) -> None:
    from living_island.world.v2.rules import ContentError

    with pytest.raises(ContentError) as error:
        load(path, vocab)
    assert error.value.code == code


def test_rr01_canonical_content_encoding() -> None:
    from living_island.world.v2.rules.schema import canonical_json_bytes

    payload = {"z": [{"y": "café", "x": 4}, 1, 0], "a": True}
    assert canonical_json_bytes(payload) == '{"a":true,"z":[{"x":4,"y":"café"},1,0]}'.encode()


def test_rr01_hashes_and_order(sample: Path, vocab: Vocabulary) -> None:
    from living_island.world.v2.rules import load_vocabulary

    one = load(sample, vocab)
    two = load(sample, load_vocabulary(VOCABULARY))
    assert one == two
    path = sample / "rules.toml"
    chunks = path.read_text(encoding="utf-8").strip().split("[[rule]]\n")
    path.write_text(
        "\n\n".join("[[rule]]\n" + chunk.strip() for chunk in reversed(chunks[1:])),
        encoding="utf-8",
    )
    assert load(sample, vocab) == one
    replace(path, "delta = 120", "delta = 121")
    changed = load(sample, vocab)
    assert changed.rule_library_hash != one.rule_library_hash
    assert changed.pack_hash != one.pack_hash
    assert changed.rules["nap"].content_hash != one.rules["nap"].content_hash
    assert changed.rules["make_axe"].content_hash == one.rules["make_axe"].content_hash


@pytest.mark.parametrize("field", ["vocabulary_version", "vocabulary_hash"])
def test_rr02_vocabulary_pin(sample: Path, vocab: Vocabulary, field: str) -> None:
    text = (sample / "pack.toml").read_text(encoding="utf-8")
    old = next(line for line in text.splitlines() if line.startswith(field))
    replace(sample / "pack.toml", old, f'{field} = "incorrect"')
    refused(sample, vocab, "UNKNOWN_TERM")


def test_placeholders_are_typed_and_missing_is_an_error(sample: Path, vocab: Vocabulary) -> None:
    from living_island.world.v2.rules import load_pack

    key = "$" + "{nap.delta}"
    replace(sample / "rules.toml", "delta = 120", f'delta = "{key}"')
    refused(sample, vocab, "UNKNOWN_TERM")
    pack = load_pack(
        sample,
        vocab,
        bindings={
            "vocabulary_hash": vocab.vocabulary_hash,
            "nap.delta": 120,
        },
    )
    assert pack.rules["nap"].data["effects"][0]["delta"] == 120


@pytest.mark.parametrize("case", CASES, ids=[case["code"] for case in CASES])
def test_rr03_each_refusal_has_a_positive_control(
    sample: Path, vocab: Vocabulary, case: dict[str, str]
) -> None:
    assert load(sample, vocab).rules
    replace(sample / case["file"], case["old"], case["new"])
    refused(sample, vocab, case["code"])


def test_rr04_axe_and_symbolic_rot(sample: Path, vocab: Vocabulary) -> None:
    pack = load(sample, vocab)
    assert pack.rules["fruit_rots"].data["outputs"][0]["quantity"] == {"of": "subject.quantity"}
    assert len(pack.rules["make_axe"].data["inputs"]) == 3
    path = sample / "rules.toml"
    replace(path, ', {slot = "handle", where = { archetype = "handle" }, qty = 1}', "")
    refused(sample, vocab, "CONSERVATION")


def test_rr04_partial_branch_has_its_own_debits(sample: Path, vocab: Vocabulary) -> None:
    add_rule(
        sample,
        """
id = "bad_partial"
trigger = "verb:combine"
work_ticks = 6
inputs = [{slot = "handle", where = { archetype = "handle" }, qty = 1}]
on_interrupt = { partial = [{ archetype = "handle", quantity = 2, at = "actor" }] }
""",
    )
    refused(sample, vocab, "CONSERVATION")


def test_rr04_when_source(sample: Path, vocab: Vocabulary) -> None:
    add_rule(
        sample,
        """
id = "bad_when"
trigger = "when:old"
subject = { archetype = "fruit" }
conditions = [{ id = "old", kind = "state", of = "subject", field = "age", op = ">", value = 0 }]
conservation = "source"
outputs = [{ archetype = "water", quantity = 1, at = "subject.tile", source = "spring" }]
""",
    )
    refused(sample, vocab, "BAD_SHAPE")


def test_rr04_no_declared_output_source(sample: Path, vocab: Vocabulary) -> None:
    add_rule(
        sample,
        """
id = "free_fruit"
trigger = "every:3"
subject = { archetype = "fruit" }
outputs = [{ archetype = "fruit", quantity = 1, at = "subject.tile" }]
""",
    )
    refused(sample, vocab, "CONSERVATION")


@pytest.mark.parametrize(
    ("ticks", "chance", "conditions", "effects", "code"),
    [
        (
            1,
            1000,
            "[]",
            '[{op="need", need="stamina", delta=300, timing="completion"}]',
            "NEED_RATE",
        ),
        (
            4,
            1000,
            "[]",
            """[
            {op="need", need="stamina", delta=220, timing="per_tick"},
            {op="need", need="stamina", delta=880, timing="completion"}]""",
            "NEED_RATE",
        ),
        (6, 500, "[]", '[{op="need", need="stamina", delta=120, timing="per_tick"}]', "BAD_SHAPE"),
        (
            6,
            1000,
            '[{id="not_full",kind="need",need="stamina",op="<",value="max"}]',
            '[{op="need", need="stamina", delta=120, timing="per_tick"}]',
            "BAD_SHAPE",
        ),
    ],
)
def test_rr05_reject_need_effects(
    sample: Path,
    vocab: Vocabulary,
    ticks: int,
    chance: int,
    conditions: str,
    effects: str,
    code: str,
) -> None:
    add_rule(
        sample,
        f"""
id = "bad_rest"
trigger = "verb:rest"
work_ticks = {ticks}
success_per_mille = {chance}
conditions = {conditions}
effects = {effects}
""",
    )
    refused(sample, vocab, code)


def test_rr05_duration_uses_parameter_minimum(sample: Path, vocab: Vocabulary) -> None:
    add_rule(
        sample,
        """
id = "bad_sleep"
trigger = "verb:sleep"
work_ticks = {param = "duration_ticks"}
effects = [{op="need", need="stamina", delta=1321, timing="completion"}]
""",
    )
    refused(sample, vocab, "NEED_RATE")


def test_rr11_specificity(sample: Path, vocab: Vocabulary) -> None:
    add_rule(
        sample,
        """
id = "strike_with_axe"
trigger = "verb:strike"
work_ticks = 1
target = {where = {archetype = "head"}}
instruments = [{slot = "tool", where = {archetype = "axe"}, qty = 1}]
conditions = [{id = "awake", kind = "awareness", value = "awake"}]
""",
    )
    pack = load(sample, vocab)
    assert pack.rules["strike_with_axe"].specificity == 3
    assert pack.rules["mark_site"].specificity == 1


def test_rr22_proposed_rule_is_validated_without_activation(
    sample: Path, vocab: Vocabulary
) -> None:
    from living_island.world.v2.rules import ContentError, validate_proposal

    pack = load(sample, vocab)
    old_hash = pack.rule_library_hash
    base = pack.rules["nap"]
    assert base.data["provenance"] == {"kind": "authored", "pack_id": "sample"}
    raw = {
        "id": "proposed_nap",
        "trigger": "verb:rest",
        "work_ticks": 6,
        "effects": deepcopy(base.data["effects"]),
        "provenance": {
            "kind": "proposed",
            "llm_call_id": "call_1",
            "approved_by": "ryan",
            "approved_at_tick": 4,
        },
    }
    proposal = validate_proposal(pack, raw)
    assert proposal.id not in pack.rules
    assert pack.rule_library_hash == old_hash
    alternate = deepcopy(raw)
    alternate["provenance"]["approved_by"] = "ella"
    assert validate_proposal(pack, alternate).content_hash == proposal.content_hash
    raw["effects"][0]["delta"] = 221
    with pytest.raises(ContentError, match="NEED_RATE"):
        validate_proposal(pack, raw)


def test_rr24_coverage_and_overlaps(sample: Path, vocab: Vocabulary) -> None:
    add_rule(
        sample,
        """
id = "alt_axe"
trigger = "verb:combine"
work_ticks = 1
inputs = [{slot = "h", where = { archetype = "head", hardness_min = 4 }, qty = 1},
          {slot = "b", where = { archetype = "binding" }, qty = 1},
          {slot = "s", where = { archetype = "handle" }, qty = 1}]
""",
    )
    add_rule(
        sample,
        """
id = "sort_stone"
trigger = "verb:combine"
work_ticks = 1
inputs = [{ slot = "stone", where = { hardness_min = 4 }, qty = 1 }]
""",
    )
    report = load(sample, vocab).report
    assert report.slot_coverage["sort_stone"]["stone"] == (("axe", "stone"), ("head", "stone"))
    assert ("alt_axe", "make_axe") in report.overlaps


@pytest.mark.parametrize(
    ("file", "old", "new"),
    [
        ("rules.toml", 'trigger = "verb:rest"', 'trigger = "always:rest"'),
        ("rules.toml", 'kind = "terrain_near"', 'kind = "new_condition"'),
        ("rules.toml", 'op = "need"', 'op = "new_effect"'),
        ("archetypes.toml", "fuel = {}", "new_component = {}"),
    ],
)
def test_rr25_closed_registries(
    sample: Path, vocab: Vocabulary, file: str, old: str, new: str
) -> None:
    replace(sample / file, old, new)
    refused(sample, vocab, "UNKNOWN_TERM")


def test_rr29_rr34_unreachable_requires_both_phases(sample: Path, vocab: Vocabulary) -> None:
    assert load(sample, vocab).report.unreachable_checks == (("compat_sleep_cave", "cave"),)
    path = sample / "rules.toml"
    replace(
        path,
        'id = "compat_sleep_plain"',
        """id = "compat_sleep_plain"
conditions = [{id = "wide", kind = "terrain_near", terrain = "cave", distance = {min=0, max=2}}]
""",
    )
    replace(
        path,
        "distance = {min = 0, max = 1}}]",
        'distance = {min = 0, max = 1}}, {id="day", kind="time_phase", value="day"}]',
    )
    assert load(sample, vocab).report.unreachable_checks == ()
    replace(
        path,
        'id = "wide", kind = "terrain_near", terrain = "cave"',
        'id = "wide", kind = "entity_near", where = {archetype = "fire"}',
    )
    replace(
        path,
        'id = "cave", kind = "terrain_near", terrain = "cave"',
        'id = "fire", kind = "entity_near", where = {archetype = "fire"}',
    )
    assert load(sample, vocab).report.unreachable_checks == ()


def test_rr30_extend_replace_disable(sample: Path, vocab: Vocabulary) -> None:
    original = load(sample, vocab)
    dest = sample.parent / "extension"
    shutil.copytree(FIXTURES / "extension", dest)
    extended = load(dest, vocab)
    assert extended.rules["nap"].data["work_ticks"] == 2
    assert extended.rules["nap"].data["provenance"]["pack_id"] == "extension"
    assert "compat_sleep_cave" not in extended.rules
    assert extended.data["unmatched"]["combine"]["default"] == ["falls_apart"]
    assert extended.data["unmatched"]["combine"]["entries"][0]["phenomena"] == ["holds_firm"]
    assert extended.rule_library_hash != original.rule_library_hash
    assert extended.pack_hash != original.pack_hash
    replace(dest / "rules.toml", "replace = true", "")
    refused(dest, vocab, "DUPLICATE_ID")


def test_rr31_descriptor_tables_and_containers(sample: Path, vocab: Vocabulary) -> None:
    from living_island.world.v2.rules import ContentError, parse_vocabulary

    raw = tomllib.loads(VOCABULARY.read_text(encoding="utf-8"))
    edible = next(prop for prop in raw["property"] if prop["id"] == "edible")
    edible.pop("descriptors")
    assert parse_vocabulary(raw).properties["edible"]["domain"] == "bool"
    edible["descriptors"] = [{"value": True, "word": "food"}]
    with pytest.raises(ContentError, match="BAD_SHAPE"):
        parse_vocabulary(raw)
    edible.pop("descriptors")
    raw["property"][0].pop("descriptors")
    with pytest.raises(ContentError, match="BAD_SHAPE"):
        parse_vocabulary(raw)
    replace(sample / "archetypes.toml", 'accepts = { archetype = "water" }', "accepts = {}")
    refused(sample, vocab, "BAD_SHAPE")


def test_rr33_tells_need_descriptor_difference(sample: Path, vocab: Vocabulary) -> None:
    path = sample / "instances.toml"
    replace(path, "properties = { dry = true }", "properties = { strength = 3 }")
    replace(path, "apparent = { strength = 5 }", "apparent = { weight = 5 }")
    replace(path, 'tell = ["dry"]', 'tell = ["strength"]')
    refused(sample, vocab, "TELL_MISSING")


def test_rr33_world_and_process_normalization(sample: Path, vocab: Vocabulary) -> None:
    original = load(sample, vocab)
    replace(
        sample / "rules.toml",
        'trigger = "when:old"',
        """trigger = "when:old"
inputs = []
success_per_mille = 1000
conservation = "inputs_to_outputs"
phenomena = { success = [], chance_failed = [], unmet = [], unmet_by_check = {} }""",
    )
    replace(
        sample / "rules.toml",
        'trigger = "when:done"',
        """trigger = "when:done"
outputs = []
inputs = []
success_per_mille = 1000""",
    )
    replace(sample / "archetypes.toml", "work_required = 6", "work_required = 6, work_done = 0")
    assert load(sample, vocab) == original
    replace(sample / "rules.toml", 'trigger = "when:old"', 'trigger = "when:old"\nwork_ticks = 1')
    refused(sample, vocab, "BAD_SHAPE")


@pytest.mark.parametrize("case", ["whole", "contents", "returns", "capacity", "summed_sources"])
def test_rr36_joint_branch_ledger(sample: Path, vocab: Vocabulary, case: str) -> None:
    path = sample / "rules.toml"
    code = "CONSERVATION"
    if case == "whole":
        consume = '{op = "consume", of = "subject"}'
        replace(path, f"effects = [{consume}]", f"effects = [{consume}, {consume}]")
    elif case == "contents":
        add_rule(
            sample,
            """
id = "drink_twice"
trigger = "verb:drink"
work_ticks = 1
instruments = [{slot = "bottle", where = {archetype = "bottle"}, qty = 1}]
conditions = [{id = "water", kind = "state", of = "slot:bottle",
               field = "container.count:water", op = ">=", value = 1}]
effects = [{op = "consume", of = "slot:bottle.contents", archetype = "water", quantity = 1},
           {op = "consume", of = "slot:bottle.contents", archetype = "water", quantity = 1}]
""".replace('of = "slot:bottle",\n               field', 'of = "slot:bottle", field'),
        )
    elif case == "returns":
        add_rule(
            sample,
            """
id = "return_twice"
trigger = "verb:combine"
work_ticks = 1
inputs = [{slot = "h", where = {archetype = "handle"}, qty = 1}]
outputs = [{archetype_from = "h", material_from = "h", quantity = 1, at = "actor"},
           {archetype_from = "h", material_from = "h", quantity = 1, at = "actor"}]
""",
        )
    elif case == "capacity":
        code = "UNDECLARED_SOURCE"
        replace(sample / "archetypes.toml", "capacity = 2, accepts", "accepts")
        with (sample / "instances.toml").open("a", encoding="utf-8") as stream:
            stream.write("""
[[instance]]
id = "big_bottle"
archetype = "bottle"
at = { tile = [1, 2] }
state = { container = { capacity = 3 } }
""")
    else:
        code = "UNDECLARED_SOURCE"
        lit = '{archetype = "water", quantity = 2, at = "target.contents", source = "spring"}'
        replace(
            path,
            'outputs = [{archetype = "water", quantity = {of = "fit:target.contents"}, '
            'at = "target.contents", source = "spring"}]',
            f"outputs = [{lit}, {lit}]",
        )
    refused(sample, vocab, code)


def test_rr38_process_must_consume_whole_subject(sample: Path, vocab: Vocabulary) -> None:
    path = sample / "rules.toml"
    replace(
        path,
        'conditions = [{id = "done", kind = "work_complete"}]\neffects = '
        '[{op = "consume", of = "subject"}]',
        'conditions = [{id = "done", kind = "work_complete"}]',
    )
    refused(sample, vocab, "BAD_SHAPE")


def test_rr34_start_proof_compares_actual_values(sample: Path, vocab: Vocabulary) -> None:
    rules = sample / "rules.toml"
    replace(
        rules,
        'id = "compat_sleep_plain"',
        """id = "compat_sleep_plain"
conditions = [{id="plain_need", kind="need", need="stamina", op="<=", value=8000}]
""",
    )
    replace(
        rules,
        'conditions = [{id = "cave"',
        '''conditions = [
{id="cave_need", kind="need", need="stamina", op=">=", value=8000},
{id = "cave"''',
    )
    replace(
        rules,
        'effects = [{op = "need", need = "stamina", delta = 220, timing = "per_tick"}]',
        "effects = []",
    )
    assert load(sample, vocab).report.unreachable_checks == ()
    replace(rules, 'op="<=", value=8000', 'op=">=", value=7000')
    assert load(sample, vocab).report.unreachable_checks == (("compat_sleep_cave", "cave"),)


def test_instance_effective_component_defaults_share_a_pack_hash(
    sample: Path, vocab: Vocabulary
) -> None:
    path = sample / "instances.toml"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("""
[[instance]]
id = "placed_site"
archetype = "site"
at = { tile = [2, 3] }
""")
    original = load(sample, vocab)
    replace(
        path,
        "at = { tile = [2, 3] }",
        """at = { tile = [2, 3] }
state = { process = { work_done = 0 } }
""",
    )
    assert load(sample, vocab) == original


def test_disabling_a_periodic_rule_drops_its_inactive_offset(
    sample: Path, vocab: Vocabulary
) -> None:
    add_rule(
        sample,
        """
id = "periodic"
trigger = "every:5"
subject = { archetype = "handle" }
""",
    )
    with (sample / "instances.toml").open("a", encoding="utf-8") as stream:
        stream.write("phase_offset = { periodic = 2 }\n")
    assert load(sample, vocab).data["instance"]["placed_handle"]["phase_offset"] == {"periodic": 2}
    dest = sample.parent / "extension"
    shutil.copytree(FIXTURES / "extension", dest)
    replace(dest / "pack.toml", '"compat_sleep_cave"', '"compat_sleep_cave", "periodic"')
    assert load(dest, vocab).data["instance"]["placed_handle"]["phase_offset"] == {}
