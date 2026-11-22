"""Load, compose and validate v2 packs without consulting simulation state."""

import re
import tomllib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import Catalog, build_catalog, closure, phase_offsets, validate_containers
from .conservation import validate_branches
from .report import build_report
from .rule import comparison_tables, covered_roles, normalize_rule, specificity
from .schema import (
    ContentError,
    Table,
    ValidationReport,
    array,
    boolean,
    content_hash,
    fields,
    identifier,
    indexed,
    integer,
    require,
    string,
    table,
    term,
)
from .vocabulary import Vocabulary

PACK_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}")
PLACEHOLDER = re.compile(r"\$\{([a-zA-Z0-9_.-]+)\}")
SECTIONS = {
    "materials.toml": "material",
    "archetypes.toml": "archetype",
    "rules.toml": "rule",
    "instances.toml": "instance",
    "unmatched.toml": "unmatched",
}
VALUE_TABLES = ("needs", "physiology", "timing", "inventory_slots", "limits", "sight_while_asleep")


@dataclass(frozen=True)
class Rule:
    data: Table
    content_hash: str
    specificity: int

    @property
    def id(self) -> str:
        return str(self.data["id"])


@dataclass(frozen=True)
class PackLayer:
    pack_id: str
    pack_hash: str


@dataclass(frozen=True)
class Pack:
    pack_id: str
    pack_version: str
    pack_hash: str
    vocabulary: Vocabulary
    rule_library_hash: str
    rules: dict[str, Rule]
    report: ValidationReport
    data: Table
    ancestors: tuple[PackLayer, ...]

    @property
    def vocabulary_hash(self) -> str:
        return self.vocabulary.vocabulary_hash

    @property
    def pack_ids(self) -> tuple[str, ...]:
        return (*(layer.pack_id for layer in self.ancestors), self.pack_id)


def read_toml(path: Path) -> Table:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, ValueError) as exc:
        raise ContentError("BAD_SHAPE", path.name, str(exc)) from exc


def bind(value: Any, bindings: Table, path: str) -> Any:
    if isinstance(value, str):
        match = PLACEHOLDER.fullmatch(value)
        if match:
            name = term(match[1], bindings, path)
            replacement = deepcopy(bindings[name])
            ensure_canonical(replacement, path)
            return replacement
        require("${" not in value, "BAD_SHAPE", path, "placeholder must occupy a whole value")
    elif isinstance(value, list):
        return [bind(item, bindings, path) for item in value]
    elif isinstance(value, dict):
        return {key: bind(item, bindings, path) for key, item in value.items()}
    ensure_canonical(value, path)
    return value


def ensure_canonical(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            string(key, path)
            ensure_canonical(item, path)
    elif isinstance(value, list):
        for item in value:
            ensure_canonical(item, path)
    else:
        require(
            type(value) in (int, str, bool),
            "BAD_SHAPE",
            path,
            "content must be strings, integers, booleans, arrays or tables",
        )


def pack_id(value: object) -> str:
    key = string(value, "pack_id")
    require(PACK_ID.fullmatch(key), "DUPLICATE_ID", "pack_id", "invalid pack ID")
    return key


def merge_entries(base: Table, local: Table, path: str, *, replaceable: bool) -> Table:
    result = dict(base)
    for key, value in sorted(local.items()):
        row = dict(table(value, path))
        replace = boolean(row.pop("replace", False), path)
        if key in base:
            require(replace and replaceable, "DUPLICATE_ID", path, key)
        else:
            require(not replace, "UNKNOWN_TERM", path, f"no inherited {key} to replace")
        result[key] = row
    return dict(sorted(result.items()))


def merge_settings(base: Table, local: Table, path: str) -> Table:
    for key in VALUE_TABLES:
        if key not in local:
            continue
        value = local[key]
        if key in ("inventory_slots", "sight_while_asleep"):
            replace = False
            if isinstance(value, dict):
                fields(value, path, "value replace")
                replace = boolean(value["replace"], key)
                value = value["value"]
            require(
                replace == (key in base),
                "DUPLICATE_ID" if key in base else "UNKNOWN_TERM",
                path,
                f"replacement marker disagrees with inherited {key}",
            )
        else:
            value = dict(table(value, key))
            replace = boolean(value.pop("replace", False), key)
            if key in base and not replace:
                if key == "needs":
                    value = merge_entries(base[key], value, key, replaceable=True)
                else:
                    require(False, "DUPLICATE_ID", path, f"{key} requires replace = true")
            elif replace:
                require(key in base, "UNKNOWN_TERM", path, f"no inherited {key}")
            elif key == "needs":
                value = merge_entries({}, value, key, replaceable=True)
        base[key] = value
    return base


def compose(
    directory: Path, vocab: Vocabulary, bindings: Table, ancestry: tuple[str, ...] = ()
) -> tuple[Table, tuple[PackLayer, ...]]:
    raw = bind(read_toml(directory / "pack.toml"), bindings, "pack.toml")
    fields(
        raw,
        "pack.toml",
        "pack_id pack_version vocabulary_version vocabulary_hash",
        "extends enabled_verbs enabled_needs disable sources " + " ".join(VALUE_TABLES),
    )
    key = pack_id(raw["pack_id"])
    require(key not in ancestry, "BAD_SHAPE", key, "pack extension cycle")
    string(raw["pack_version"], key)
    require(
        raw["vocabulary_version"] == vocab.version
        and raw["vocabulary_hash"] == vocab.vocabulary_hash,
        "UNKNOWN_TERM",
        key,
        "vocabulary pin mismatch",
    )
    base: Table = {}
    layers: tuple[PackLayer, ...] = ()
    if "extends" in raw:
        parent = pack_id(raw["extends"])
        base, layers = compose(directory.parent / parent, vocab, bindings, (*ancestry, key))
        require(base["pack_id"] == parent, "UNKNOWN_TERM", key, "base pack ID mismatch")
        # Pin the bound composition before this overlay can replace its content.
        # A prefix is not required to pass leaf validation on its own.
        layers = (*layers, PackLayer(parent, content_hash(base)))

    result = {
        name: raw[name]
        for name in ("pack_id", "pack_version", "vocabulary_version", "vocabulary_hash", "extends")
        if name in raw
    }
    for name, allowed in (("enabled_verbs", vocab.verbs), ("enabled_needs", vocab.needs)):
        terms = [term(item, allowed, key) for item in array(raw.get(name, []), name)]
        require(len(terms) == len(set(terms)), "DUPLICATE_ID", key, f"duplicate {name}")
        result[name] = sorted(set(base.get(name, [])) | set(terms))
    result.update(
        merge_settings({name: base[name] for name in VALUE_TABLES if name in base}, raw, key)
    )
    sources = raw.get("sources", {})
    if isinstance(sources, list):
        sources = indexed(sources, "source")
    result["source"] = merge_entries(
        base.get("source", {}), table(sources, "sources"), "sources", replaceable=False
    )

    disabled = set()
    for rule_id in array(raw.get("disable", []), "disable"):
        name = term(rule_id, base.get("rule", {}), key)
        require(name not in disabled, "DUPLICATE_ID", key, name)
        disabled.add(name)
    for filename, name in SECTIONS.items():
        path = directory / filename
        data = bind(read_toml(path), bindings, filename) if path.exists() else {}
        fields(data, filename, optional=name)
        if name == "unmatched":
            local = table(data.get(name, {}), filename)
        else:
            local = indexed(data.get(name, []), filename)
        if name == "rule":
            for rule_id, rule in local.items():
                require(
                    rule_id not in disabled, "DUPLICATE_ID", key, "same rule disabled and declared"
                )
                authored = {"kind": "authored", "pack_id": key}
                require(
                    rule.get("provenance", authored) == authored,
                    "BAD_SHAPE",
                    rule_id,
                    "file rule must be authored by its pack",
                )
                rule["provenance"] = authored
        result[name] = merge_entries(
            base.get(name, {}), local, name, replaceable=name != "instance"
        )
        if name == "rule":
            result[name] = {
                rule_id: row for rule_id, row in result[name].items() if rule_id not in disabled
            }
    if disabled:
        for key, row in result["instance"].items():
            offsets = table(row.get("phase_offset", {}), key)
            row["phase_offset"] = {
                rule: phase for rule, phase in offsets.items() if rule not in disabled
            }
    codes = directory / "compat-codes.toml"
    if codes.exists():
        result["compat_codes"] = bind(read_toml(codes), bindings, codes.name)
    return result, layers


def validate_settings(pack: Table, catalog: Catalog) -> None:
    needs = table(pack.setdefault("needs", {}), "needs")
    for name in sorted(needs.keys() | set(pack["enabled_needs"])):
        term(name, pack["enabled_needs"], "needs")
        row = fields(
            needs.get(name),
            name,
            "min max initial band_cutoffs max_gain_per_tick max_loss_per_tick",
            "thresholds",
        )
        minimum = integer(row["min"], name)
        maximum = integer(row["max"], name, minimum)
        integer(row["initial"], name, minimum, maximum)
        for key in ("max_gain_per_tick", "max_loss_per_tick"):
            integer(row[key], name, 0)
        cutoffs = array(row["band_cutoffs"], name)
        for cutoff in cutoffs:
            integer(cutoff, name, 0, maximum - minimum)
        require(
            len(cutoffs) == 4 and cutoffs == sorted(set(cutoffs)),
            "BAD_SHAPE",
            name,
            "expected four increasing band cutoffs",
        )
        for threshold in indexed(row.setdefault("thresholds", []), name).values():
            fields(threshold, name, "id at", "wakes")
            integer(threshold["at"], name, 0, maximum - minimum)
            boolean(threshold.setdefault("wakes", False), name)

    for key, source in pack["source"].items():
        identifier(key, "source")
        fields(source, key, "archetype", "id max_per_application")
        require(source.setdefault("id", key) == key, "BAD_SHAPE", key, "source ID mismatch")
        term(source["archetype"], catalog.archetypes, key)
        maximum = source.get("max_per_application")
        require(
            type(maximum) is int and maximum > 0,
            "UNDECLARED_SOURCE",
            key,
            "source needs a positive per-application bound",
        )
    boolean(pack.setdefault("sight_while_asleep", False), "sight_while_asleep")
    if "inventory_slots" in pack:
        integer(pack["inventory_slots"], "inventory_slots", 1)
    for name in ("timing", "limits", "physiology"):
        table(pack.setdefault(name, {}), name)
    for key in ("max_entities_per_tile", "max_entity_units_world"):
        if key in pack["limits"]:
            integer(pack["limits"][key], key, 1)
    timing = pack["timing"]
    for key in timing:
        if key.endswith("_ticks") and key != "attempt_ticks":
            integer(timing[key], key, 1)
    if pack["enabled_verbs"] or "attempt_ticks" in timing:
        attempts = table(timing.get("attempt_ticks", {}), "attempt_ticks")
        for verb in sorted(attempts.keys() | set(pack["enabled_verbs"])):
            term(verb, pack["enabled_verbs"], "attempt_ticks")
            integer(attempts.get(verb), f"attempt_ticks.{verb}", 1)


def validate_interruption(catalog: Catalog, rule: Table, rules: list[Table]) -> None:
    mode = rule.get("on_interrupt")
    if not isinstance(mode, dict) or "keep_progress" not in mode:
        return
    arch = mode["keep_progress"]
    path = rule["id"]
    settings = catalog.archetypes[arch]["components"]
    require(
        "process" in settings
        and "work_required" in settings["process"]
        and "container" in settings
        and "accepts" in settings["container"]
        and "capacity" in settings["container"],
        "INTERRUPT_MODE",
        path,
        "keep_progress requires a constructible process",
    )
    from .catalog import matches
    from .report import compatible, signature

    original = signature(catalog, rule)
    inputs = covered_roles(catalog, rule)
    capacity = 0
    for slot in rule["inputs"]:
        choices = inputs["slot:" + slot["slot"]]
        require(
            bool(choices) and all(matches(settings["container"]["accepts"], v) for v in choices),
            "INTERRUPT_MODE",
            path,
            "process cannot hold every interrupted input",
        )
        capacity += slot["qty"] * max(v.components["portable"]["slots_per_unit"] for v in choices)
    require(
        capacity <= settings["container"]["capacity"],
        "INTERRUPT_MODE",
        path,
        "interrupted inputs cannot fit the process",
    )
    for candidate in rules:
        kind, _, trigger = candidate["trigger"].partition(":")
        if kind != "when" or candidate["subject"].get("archetype") != arch:
            continue
        if not any(
            c["id"] == trigger and c["kind"] == "work_complete" for c in candidate["conditions"]
        ):
            continue
        finish = signature(catalog, candidate)
        left = {"target": None, "subject": None, "instruments": [], "inputs": original["inputs"]}
        right = {**left, "inputs": finish["inputs"]}
        if compatible(left, right, subset=True):
            return
    require(False, "INTERRUPT_MODE", path, "no process rule covers interrupted inputs")


def wrap_rule(rule: Table) -> Rule:
    return Rule(
        rule,
        content_hash({key: value for key, value in rule.items() if key != "provenance"}),
        specificity(rule),
    )


def library_hash(rules: dict[str, Table]) -> str:
    return content_hash([rules[key] for key in sorted(rules)])


def load_pack(directory: Path, vocabulary: Vocabulary, *, bindings: Table | None = None) -> Pack:
    """Read a pack directory and its sibling ancestors, then validate the composed pack."""
    parsed, ancestors = compose(directory, vocabulary, bindings or {})
    catalog = build_catalog(vocabulary, parsed)
    validate_settings(parsed, catalog)
    comparison_tables(catalog, parsed["enabled_verbs"], parsed["unmatched"])
    rules = {
        key: normalize_rule(raw, catalog, parsed, pack_id=raw["provenance"]["pack_id"])
        for key, raw in parsed["rule"].items()
    }
    active = list(rules.values())
    closure(catalog, active)
    validate_containers(catalog)
    phase_offsets(catalog, rules)
    for rule in active:
        validate_branches(catalog, rule, parsed["source"])
        validate_interruption(catalog, rule, active)
    parsed["rule"] = rules
    return Pack(
        parsed["pack_id"],
        parsed["pack_version"],
        content_hash(parsed),
        vocabulary,
        library_hash(rules),
        {key: wrap_rule(rule) for key, rule in rules.items()},
        build_report(catalog, parsed, rules),
        parsed,
        ancestors,
    )


def validate_proposal(pack: Pack, raw: Table, *, canonical: bool = False) -> Rule:
    """Validate a proposed addition in context and leave the active library untouched."""
    ensure_canonical(raw, "proposal")
    data = deepcopy(pack.data)
    catalog = build_catalog(pack.vocabulary, data)
    rule = normalize_rule(raw, catalog, data, pack_id=None, canonical=canonical)
    key = rule["id"]
    require(key not in pack.rules, "DUPLICATE_ID", key, "rule ID is already active")
    combined = dict(sorted({**data["rule"], key: rule}.items()))
    active = list(combined.values())
    closure(catalog, active)
    validate_containers(catalog)
    for candidate in active:
        validate_branches(catalog, candidate, data["source"])
        validate_interruption(catalog, candidate, active)
    return wrap_rule(rule)
