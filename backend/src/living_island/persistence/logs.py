"""Canonical append-only event and decision logs."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from io import BytesIO
from itertools import islice
from pathlib import Path

from pydantic import BaseModel

from living_island.agents.types import DecisionRecord
from living_island.events import WorldEvent
from living_island.events.validation import EventSequence, EventValidationError

from ._codec import PersistenceError, decode_model, encode, read_bytes
from ._files import create_file

EVENTS_FILENAME = "events.jsonl"
DECISIONS_FILENAME = "decisions.jsonl"


def _decode_lines[T: BaseModel](
    lines: Iterable[bytes], path: Path, model: type[T], version_field: str
) -> tuple[T, ...]:
    records = []
    for line, raw in enumerate(lines, 1):
        if not raw.endswith(b"\n"):
            raise PersistenceError(path, "JSONL", "missing final LF", line=line)
        records.append(decode_model(raw[:-1], model, path, line=line, version_field=version_field))
    return tuple(records)


def _check_events(
    path: Path,
    sequence: EventSequence,
    events: Iterable[WorldEvent],
    offset: int,
    after_tick: int | None,
) -> None:
    def post_checkpoint() -> Iterable[WorldEvent]:
        for index, event in enumerate(events):
            if after_tick is not None and event.tick <= after_tick:
                raise EventValidationError(index, "tick", "expected a post-checkpoint event")
            yield event

    try:
        sequence.validate(post_checkpoint())
    except EventValidationError as exc:
        raise PersistenceError(path, exc.field, str(exc), line=offset + exc.index + 1) from exc


class _DecisionSequence:
    def __init__(self, run_id: str, ordinals: Mapping[str, int], from_tick: int | None) -> None:
        self._run_id = run_id
        self._ordinals = dict(ordinals)
        self._from_tick = from_tick
        self._last: tuple[int, str] | None = None

    def validate(self, path: Path, records: Iterable[DecisionRecord], offset: int) -> None:
        ordinals, last = self._ordinals.copy(), self._last
        for line, record in enumerate(records, offset + 1):
            if record.run_id != self._run_id:
                raise PersistenceError(path, "run_id", f"expected {self._run_id!r}", line=line)
            expected = ordinals.get(record.actor_id, 0)
            if record.decision_ordinal != expected:
                raise PersistenceError(path, "decision_ordinal", f"expected {expected}", line=line)
            if self._from_tick is not None and record.tick < self._from_tick:
                raise PersistenceError(
                    path, "tick", "expected a post-checkpoint decision", line=line
                )
            key = (record.tick, record.actor_id)
            if last is not None and key <= last:
                raise PersistenceError(
                    path, "tick/actor_id", "expected boundary actor order", line=line
                )
            ordinals[record.actor_id] = expected + 1
            last = key
        self._ordinals, self._last = ordinals, last


def _events_from_bytes(
    path: Path, raw: bytes, run_id: str, prior: Iterable[WorldEvent], after_tick: int | None
) -> tuple[WorldEvent, ...]:
    sequence = EventSequence(run_id)
    _check_events(path, sequence, prior, 0, None)
    events = _decode_lines(BytesIO(raw), path, WorldEvent, "schema_version")
    _check_events(path, sequence, events, 0, after_tick)
    return events


def read_events(
    path: Path,
    run_id: str,
    *,
    prior: Iterable[WorldEvent] = (),
    after_tick: int | None = None,
) -> tuple[WorldEvent, ...]:
    """Read a full event log or a continuation seeded with its causal prefix."""
    return _events_from_bytes(path, read_bytes(path), run_id, prior, after_tick)


def read_event_prefix(
    path: Path, run_id: str, count: int, *, prior: tuple[WorldEvent, ...] = ()
) -> tuple[WorldEvent, ...]:
    """Read precisely the committed prefix, ignoring later source-run bytes."""
    remaining = count - len(prior)
    if remaining < 0:
        raise PersistenceError(path, "event_cursor", "earlier history exceeds checkpoint cursor")
    try:
        with path.open("rb") as stream:
            records = _decode_lines(islice(stream, remaining), path, WorldEvent, "schema_version")
    except OSError as exc:
        raise PersistenceError(path, "file", str(exc)) from exc
    if len(records) != remaining:
        raise PersistenceError(path, "event_cursor", f"expected {remaining} records in this file")
    sequence = EventSequence(run_id)
    _check_events(path, sequence, prior, 0, None)
    _check_events(path, sequence, records, 0, None)
    return prior + records


def _decisions_from_bytes(
    path: Path, raw: bytes, run_id: str, ordinals: Mapping[str, int], from_tick: int | None
) -> tuple[DecisionRecord, ...]:
    records = _decode_lines(BytesIO(raw), path, DecisionRecord, "record_schema_version")
    _DecisionSequence(run_id, ordinals, from_tick).validate(path, records, 0)
    return records


def read_decisions(
    path: Path,
    run_id: str,
    *,
    ordinals: Mapping[str, int] | None = None,
    from_tick: int | None = None,
) -> tuple[DecisionRecord, ...]:
    """Read decisions in recorded order, with optional starting continuation ordinals."""
    return _decisions_from_bytes(path, read_bytes(path), run_id, ordinals or {}, from_tick)


class _LogWriter[T: BaseModel]:
    """Own a newly created log and append validated batches without rereading it."""

    def __init__(
        self,
        path: Path,
        model: type[T],
        version_field: str,
        validate: Callable[[tuple[T, ...], int], None],
    ) -> None:
        create_file(path)
        self._path = path
        self._model = model
        self._version_field = version_field
        self._validate = validate
        self._count = 0
        self._failed = False

    def append(self, records: Iterable[T]) -> None:
        if self._failed:
            raise PersistenceError(self._path, "file", "an earlier append failed")
        raw = b"".join(
            encode(record, self._path, line=line) + b"\n"
            for line, record in enumerate(records, self._count + 1)
        )
        if not raw:
            return
        parsed = tuple(
            decode_model(
                record[:-1], self._model, self._path, line=line, version_field=self._version_field
            )
            for line, record in enumerate(BytesIO(raw), self._count + 1)
        )
        self._validate(parsed, self._count)
        try:
            with self._path.open("ab") as stream:
                stream.write(raw)
        except OSError as exc:
            self._failed = True
            raise PersistenceError(self._path, "file", str(exc)) from exc
        self._count += len(parsed)


class EventLogWriter(_LogWriter[WorldEvent]):
    def __init__(
        self,
        path: Path,
        run_id: str,
        *,
        prior: Iterable[WorldEvent] = (),
        after_tick: int | None = None,
    ) -> None:
        sequence = EventSequence(run_id)
        _check_events(path, sequence, prior, 0, None)

        def validate(events: tuple[WorldEvent, ...], offset: int) -> None:
            _check_events(path, sequence, events, offset, after_tick)

        super().__init__(path, WorldEvent, "schema_version", validate)


class DecisionLogWriter(_LogWriter[DecisionRecord]):
    def __init__(
        self,
        path: Path,
        run_id: str,
        *,
        ordinals: Mapping[str, int] | None = None,
        from_tick: int | None = None,
    ) -> None:
        sequence = _DecisionSequence(run_id, ordinals or {}, from_tick)

        def validate(records: tuple[DecisionRecord, ...], offset: int) -> None:
            sequence.validate(path, records, offset)

        super().__init__(path, DecisionRecord, "record_schema_version", validate)
