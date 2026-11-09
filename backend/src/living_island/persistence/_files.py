"""File creation primitives for the single-owner persistence writers."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from ._codec import PersistenceError


def create_file(path: Path, data: bytes = b"") -> None:
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except OSError as exc:
        raise PersistenceError(path, "file", str(exc)) from exc


def atomic_create(path: Path, data: bytes) -> None:
    """Serialize publishers to a target, then atomically publish the flushed temp file."""
    lock = path.with_name(f".{path.name}.lock")
    temporary: Path | None = None
    locked = False
    try:
        try:
            with lock.open("xb"):
                locked = True
        except FileExistsError as exc:
            raise PersistenceError(
                path,
                "lock",
                f"writer lock exists at {lock}. Remove it manually "
                "after confirming no writer is active",
            ) from exc
        if os.path.lexists(path):
            raise FileExistsError(f"target already exists: {path}")
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if os.path.lexists(path):
            raise FileExistsError(f"target already exists: {path}")
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise PersistenceError(path, "file", str(exc)) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if locked:
            lock.unlink()
