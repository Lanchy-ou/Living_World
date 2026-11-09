"""Canonical JSON and file diagnostics shared by the persistence formats."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticSerializationError

from living_island.world.content import canonical_json_bytes


class PersistenceError(ValueError):
    """A storage failure or invalid persisted field, with its file and optional line."""

    def __init__(self, path: Path, field: str, message: str, *, line: int | None = None):
        self.path = path
        self.field = field
        self.line = line
        location = str(path) if line is None else f"{path}:{line}"
        super().__init__(f"{location}: {field}: {message}")


def _check_numbers(value: object, field: str, path: Path, line: int | None) -> None:
    if isinstance(value, float):
        raise PersistenceError(path, field, "only integral JSON numbers are allowed", line=line)
    if isinstance(value, dict):
        for key, child in value.items():
            _check_numbers(child, f"{field}.{key}", path, line)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_numbers(child, f"{field}[{index}]", path, line)


def encode(value: BaseModel, path: Path, *, line: int | None = None) -> bytes:
    """Encode a DTO via the world-owned encoder."""
    try:
        data = value.model_dump(mode="json", warnings="error")
        _check_numbers(data, "$", path, line)
        return canonical_json_bytes(data)
    except PersistenceError:
        raise
    except (ValueError, TypeError, RecursionError, PydanticSerializationError) as exc:
        raise PersistenceError(path, "JSON", str(exc), line=line) from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate field {key!r}")
        result[key] = value
    return result


def decode_model[T: BaseModel](
    raw: bytes,
    model: type[T],
    path: Path,
    *,
    line: int | None = None,
    canonical: bool = True,
    version_field: str | None = None,
) -> T:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        _check_numbers(value, "$", path, line)
    except PersistenceError:
        raise
    except (ValueError, RecursionError) as exc:
        raise PersistenceError(path, "JSON", str(exc), line=line) from exc
    if not isinstance(value, dict):
        raise PersistenceError(path, "JSON", "expected an object", line=line)
    if version_field is not None:
        require_version(path, version_field, value.get(version_field), line=line)
    try:
        parsed = model.model_validate(value)
    except ValidationError as exc:
        error = exc.errors()[0]
        field = ".".join(map(str, error["loc"])) or "record"
        raise PersistenceError(path, field, error["msg"], line=line) from exc
    if canonical and encode(parsed, path, line=line) != raw:
        raise PersistenceError(path, "JSON", "expected canonical UTF-8 JSON bytes", line=line)
    return parsed


def require_version(path: Path, field: str, value: object, *, line: int | None = None) -> None:
    if value != "0.1":
        raise PersistenceError(path, field, f"unsupported version {value!r}", line=line)


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PersistenceError(path, "file", str(exc)) from exc


def verify_identity(path: Path, field: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise PersistenceError(path, field, f"expected {expected}, got {actual}")


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()
