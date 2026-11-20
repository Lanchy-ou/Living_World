"""Vocabulary loading and descriptor validation."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import (
    Table,
    array,
    boolean,
    content_hash,
    fields,
    identifier,
    indexed,
    integer,
    interval,
    require,
    string,
    term,
)

COMPONENTS = {
    "portable": ("slots_per_unit", ""),
    "store": ("archetype capacity", "count"),
    "container": ("capacity accepts", ""),
    "durability": ("max_wear", "wear"),
    "fuel": ("", "ticks_left"),
    "shelter": ("", ""),
    "footprint": ("blocks_movement opaque", ""),
    "process": ("work_required", "work_done"),
}


@dataclass(frozen=True)
class Vocabulary:
    version: str
    vocabulary_hash: str
    needs: dict[str, Table]
    properties: dict[str, Table]
    matter_classes: dict[str, Table]
    verbs: dict[str, Table]
    phenomena: dict[str, Table]


def property_value(value: object, domain: str, path: str) -> None:
    if domain == "bool":
        boolean(value, path)
    else:
        integer(value, path, 0, 5 if domain == "scale" else None)


def descriptor(prop: Table, value: Any) -> str:
    rows = prop["descriptors"]
    if prop["domain"] == "bool":
        return str(next(row["word"] for row in rows if row["value"] == value))
    return str(next((row["word"] for row in rows if value <= row["upto"]), rows[-1]["word"]))


def parse_vocabulary(data: Table) -> Vocabulary:
    fields(data, "vocabulary", "vocabulary_version need property matter_class verb phenomenon")
    version = string(data["vocabulary_version"], "vocabulary_version")
    needs, props, matter, verbs, phenomena = (
        indexed(data[key], key)
        for key in ("need", "property", "matter_class", "verb", "phenomenon")
    )
    for key, row in needs.items():
        fields(row, key, "id polarity")
        term(row["polarity"], ("higher_is_better", "higher_is_worse"), key)
    for key, row in matter.items():
        fields(row, key, "id")
    for key, row in props.items():
        fields(row, key, "id domain observability", "default descriptors")
        require(key != "progress", "DUPLICATE_ID", key, "reserved engine property")
        domain = term(row["domain"], ("scale", "count", "bool"), key)
        visibility = term(row["observability"], ("visible", "on_inspect", "on_use"), key)
        entries = array(row.get("descriptors", []), key)
        require(
            bool(entries) == (visibility != "on_use"),
            "BAD_SHAPE",
            key,
            "descriptor table disagrees with observability",
        )
        require(
            ("default" in row) == (domain != "count"),
            "BAD_SHAPE",
            key,
            "only scale and bool properties have defaults",
        )
        if "default" in row:
            property_value(row["default"], domain, key)
        words: set[str] = set()
        values: list[int] = []
        bound = "value" if domain == "bool" else "upto"
        for entry in entries:
            fields(entry, key, f"{bound} word")
            property_value(entry[bound], domain, key)
            word = string(entry["word"], key)
            require(word and word not in words, "BAD_SHAPE", key, "invalid descriptor word")
            words.add(word)
            values.append(entry[bound])
        if entries:
            valid = (
                sorted(values) == [False, True]
                if domain == "bool"
                else (values == sorted(set(values)))
            )
            require(valid, "BAD_SHAPE", key, "invalid descriptor bounds")
    for key, row in verbs.items():
        fields(row, key, "id description target reach params", "awareness_during duration_param")
        string(row["description"], key)
        target = fields(row["target"], key, "kinds", "class must_be_held")
        kinds = array(target["kinds"], key)
        for kind in kinds:
            term(kind, ("tile", "entity", "resident"), key)
        require(len(kinds) == len(set(kinds)), "BAD_SHAPE", key, "duplicate target kind")
        if "class" in target:
            term(target["class"], COMPONENTS, key)
        if "must_be_held" in target:
            boolean(target["must_be_held"], key)
        if "class" in target or target.get("must_be_held", False):
            require(kinds == ["entity"], "BAD_SHAPE", key, "expected an entity target")
        interval(row["reach"], key)
        params = {}
        for param in array(row["params"], key):
            fields(param, key, "name type min max")
            name = identifier(param["name"], key)
            require(name not in params, "DUPLICATE_ID", key, name)
            params[name] = param
            term(param["type"], ("integer",), key)
            lower = integer(param["min"], key)
            integer(param["max"], key, lower)
        if "duration_param" in row:
            name = term(row["duration_param"], params, key)
            integer(params[name]["min"], key, 1)
        if "awareness_during" in row:
            term(row["awareness_during"], ("asleep",), key)
    for key, row in phenomena.items():
        fields(row, key, "id text watcher_visible")
        string(row["text"], key)
        boolean(row["watcher_visible"], key)
    return Vocabulary(version, content_hash(data), needs, props, matter, verbs, phenomena)


def load_vocabulary(path: Path) -> Vocabulary:
    with path.open("rb") as stream:
        return parse_vocabulary(tomllib.load(stream))
