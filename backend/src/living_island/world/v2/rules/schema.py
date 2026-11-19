"""Shared types, canonical encoding and shape checks for v2 content."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, NoReturn

type Table = dict[str, Any]
type Pair = tuple[str, str | None]

ID = re.compile(r"[a-z][a-z0-9_]{0,47}")
TERRAINS = frozenset(
    {"sea", "beach", "grass", "woods", "rock", "spring", "cave", "fruit_tree", "damp_moss"}
)
OPS = frozenset({"<", "<=", "==", "!=", ">=", ">"})


@dataclass(frozen=True, order=True)
class Issue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    slot_coverage: dict[str, dict[str, tuple[Pair, ...]]]
    overlaps: tuple[tuple[str, str], ...]
    unreachable_checks: tuple[tuple[str, str], ...]


class ContentError(ValueError):
    """A deterministic validation failure with its code and content location."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.issue = Issue(code, path, message)
        self.code = code
        super().__init__(f"{code} at {path}: {message}")


def require(ok: object, code: str, path: str, message: str) -> None:
    if not ok:
        raise ContentError(code, path, message)


def fail(code: str, path: str, message: str) -> NoReturn:
    raise ContentError(code, path, message)


def fields(value: object, path: str, required: str = "", optional: str = "") -> Table:
    require(isinstance(value, dict), "BAD_SHAPE", path, "expected a table")
    assert isinstance(value, dict)
    missing = set(required.split()) - value.keys()
    extra = value.keys() - set((required + " " + optional).split())
    require(
        not missing and not extra,
        "BAD_SHAPE",
        path,
        f"missing fields {sorted(missing)}, unexpected fields {sorted(extra)}",
    )
    return value


def table(value: object, path: str) -> Table:
    require(isinstance(value, dict), "BAD_SHAPE", path, "expected a table")
    assert isinstance(value, dict)
    return value


def array(value: object, path: str) -> list[Any]:
    require(isinstance(value, list), "BAD_SHAPE", path, "expected an array")
    assert isinstance(value, list)
    return value


def string(value: object, path: str) -> str:
    require(isinstance(value, str), "BAD_SHAPE", path, "expected a string")
    assert isinstance(value, str)
    return value


def boolean(value: object, path: str) -> bool:
    require(type(value) is bool, "BAD_SHAPE", path, "expected a boolean")
    assert isinstance(value, bool)
    return value


def integer(value: object, path: str, low: int | None = None, high: int | None = None) -> int:
    require(type(value) is int, "BAD_SHAPE", path, "expected an integer")
    assert isinstance(value, int)
    require(
        (low is None or value >= low) and (high is None or value <= high),
        "OUT_OF_RANGE",
        path,
        f"{value} outside bounds {low}..{high}",
    )
    return value


def identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or ID.fullmatch(value) is None:
        fail("DUPLICATE_ID", path, f"invalid identifier {value!r}")
    return value


def term(value: object, choices: Any, path: str, code: str = "UNKNOWN_TERM") -> str:
    if not isinstance(value, str) or value not in choices:
        fail(code, path, f"unknown or disallowed term {value!r}")
    return value


def indexed(value: object, path: str) -> dict[str, Table]:
    entries = {}
    for entry in array(value, path):
        row = table(entry, path)
        key = identifier(row.get("id"), path)
        require(key not in entries, "DUPLICATE_ID", path, key)
        entries[key] = row
    return dict(sorted(entries.items()))


def interval(value: object, path: str, cap: int | None = None) -> Table:
    bounds = fields(value, path, "min max")
    minimum = integer(bounds["min"], path, 0, cap)
    integer(bounds["max"], path, minimum, cap)
    return bounds


def canonical_json_bytes(value: object) -> bytes:
    """Encode content as compact, key-sorted UTF-8 JSON."""
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return text.encode("utf-8")


def content_hash(value: object) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()
