"""Immutable resident blobs and named facts in publication order, scoped to one run."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class AuditReader:
    path: Path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)

    def cursor(self) -> int:
        with closing(self._connect()) as db:
            return int(db.execute("SELECT coalesce(max(seq), 0) FROM facts").fetchone()[0])

    def keys(self, after: int, through: int) -> tuple[str, ...]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT name FROM facts WHERE seq > ? AND seq <= ? ORDER BY seq",
                (after, through),
            )
            return tuple(row[0] for row in rows)

    def read(self, key: str, through: int | None = None) -> bytes:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT hash, body FROM facts WHERE name = ? AND (? IS NULL OR seq <= ?)",
                (key, through, through),
            ).fetchone()
        if row is None:
            raise KeyError(key)
        expected, body = row
        actual = sha256(body).hexdigest()
        if actual != expected or ("." not in key and actual != key):
            raise ValueError(f"audit hash differs for {key}: stored {expected}, computed {actual}")
        return bytes(body)


@dataclass(frozen=True)
class AuditWriter:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS facts (seq INTEGER PRIMARY KEY, name TEXT UNIQUE, "
                "hash TEXT NOT NULL, body BLOB NOT NULL)"
            )

    def keep(self, key: str, body: bytes) -> None:
        self._insert(key, body, False)

    def create(self, key: str, body: bytes) -> None:
        self._insert(key, body, True)

    def _insert(self, key: str, body: bytes, exclusive: bool) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute(
                "INSERT INTO facts(name, hash, body) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO NOTHING RETURNING seq",
                (key, sha256(body).hexdigest(), body),
            ).fetchone()
            if row is None:
                if exclusive:
                    raise FileExistsError(key)
                if (
                    db.execute("SELECT body FROM facts WHERE name = ?", (key,)).fetchone()[0]
                    != body
                ):
                    raise ValueError(f"immutable audit fact differs: {key}")
