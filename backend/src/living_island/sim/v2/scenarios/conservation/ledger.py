"""Reconcile a point-in-time census against committed rule transactions."""

from collections.abc import Collection, Iterable, Iterator
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from living_island.persistence.v2.journal import store_once
from living_island.sim.v2.scenarios.runtime import Boundary
from living_island.world.v2.engine.state import Entity
from living_island.world.v2.protocol import ProtocolModel
from living_island.world.v2.rules import Pack
from living_island.world.v2.rules.schema import canonical_json_bytes

type Units = dict[str, int]
type Matter = dict[str, Units]


def inventory(entities: Iterable[Entity], matter: Matter, classes: Iterable[str]) -> Units:
    # All entities (including contents at any depth) have exactly one physical ID.
    # Stock in a store is the one quantity without its own entity.
    totals = dict.fromkeys(classes, 0)
    for entity in entities:
        if entity.archetype_id is not None:
            for kind, units in matter[entity.archetype_id].items():
                totals[kind] += units * entity.quantity
        store = entity.components.get("store")
        if store is not None:
            for kind, units in matter[store["archetype"]].items():
                totals[kind] += units * store["count"]
    return totals


class _Payload(BaseModel):
    """Project the matter-bearing fields of the engine's JSON event payload."""

    model_config = ConfigDict(strict=True)
    archetype_id: str
    rule_id: str


class _Consumed(_Payload):
    quantity: int


class _Created(_Consumed):
    source: str | None


class _Store(_Payload):
    source: str | None
    before: int
    after: int


class Entry(ProtocolModel):
    event_id: str
    intent_id: str | None
    rule_id: str
    branch: str
    operation: Literal["source", "consume", "output"]
    source: str | None
    archetype: str
    quantity: int
    units: Units


def transactions(boundary: Boundary, matter: Matter) -> Iterator[Entry]:
    branches = {
        action.intent_id: action.settlement.kind if action.settlement else "interrupt"
        for action in boundary.result.actions
    }
    for event in boundary.result.events:
        operation: Literal["source", "consume", "output"]
        source = None
        record: _Payload
        match event.type:
            case "entity_consumed":
                consumed = _Consumed.model_validate(event.payload)
                record, quantity, operation = consumed, consumed.quantity, "consume"
            case "entity_created":
                created = _Created.model_validate(event.payload)
                record, quantity, source = created, created.quantity, created.source
                operation = "source" if source is not None else "output"
            case "store_count_changed":
                store = _Store.model_validate(event.payload)
                # Starter stock withdrawals also emit matter_moved. Only regrowth
                # creates stock in the validated starter library.
                if store.source is None:
                    continue
                record, quantity, source = store, store.after - store.before, store.source
                operation = "source"
            case _:
                continue
        yield Entry(
            event_id=event.event_id,
            intent_id=event.intent_id,
            rule_id=record.rule_id,
            branch="applied" if event.intent_id is None else branches[event.intent_id],
            operation=operation,
            source=source,
            archetype=record.archetype_id,
            quantity=quantity,
            units={k: v * quantity for k, v in matter[record.archetype_id].items()},
        )


class Difference(ProtocolModel):
    tick: int
    matter_class: str
    expected: int
    observed: int
    entries: list[Entry]


class Balance(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    initial: Units
    expected: Units
    observed: Units
    sources: dict[str, Units] = Field(default_factory=dict)
    # Each value is input debits minus unsourced output credits for one rule.
    net_sinks: dict[str, Units] = Field(default_factory=dict)
    outputs: dict[str, Units] = Field(default_factory=dict)
    sample: Entry | None = None
    transfers: int = 0
    first_difference: Difference | None = None
    tick: int = 0
    prefix: str

    @classmethod
    def opening(cls, initial: Units) -> "Balance":
        return cls(
            initial=initial,
            expected=initial.copy(),
            observed=initial.copy(),
            prefix=sha256(canonical_json_bytes(initial)).hexdigest(),
        )

    def reconcile(self, tick: int, rows: list[Entry], live: Units) -> None:
        for row in rows:
            if row.source is not None:
                bucket = self.sources.setdefault(row.source, {})
            else:
                bucket = self.net_sinks.setdefault(row.rule_id, {})
            for kind, units in row.units.items():
                delta = -units if row.operation == "consume" else units
                self.expected[kind] += delta
                bucket[kind] = bucket.get(kind, 0) + (delta if row.source is not None else -delta)
                if row.operation == "output":
                    credits = self.outputs.setdefault(row.rule_id, {})
                    credits[kind] = credits.get(kind, 0) + units
                    if self.sample is None and units:
                        self.sample = row
        self.tick, self.observed = tick, live
        if self.first_difference is None:
            for kind in sorted(live):
                if live[kind] != self.expected[kind]:
                    self.first_difference = Difference(
                        tick=tick,
                        matter_class=kind,
                        expected=self.expected[kind],
                        observed=live[kind],
                        entries=[r for r in rows if kind in r.units],
                    )
                    break


def extend(prefix: str, data: bytes) -> str:
    return sha256(bytes.fromhex(prefix) + data).hexdigest()


def ledger_bytes(directory: Path, balance: Balance) -> bytes:
    """Verify retained rows against the checkpoint before extending or publishing them."""
    prefix = Balance.opening(balance.initial).prefix
    lines = []
    for tick in range(1, balance.tick + 1):
        data = (directory / f"ledger/{tick}.json").read_bytes()
        lines.append(data)
        prefix = extend(prefix, data)
    if prefix != balance.prefix:
        raise ValueError(f"ledger prefix differs at committed tick {balance.tick}")
    return b"".join(line + b"\n" for line in lines)


class Ledger:
    def __init__(self, directory: Path, pack: Pack, entities: Iterable[Entity]):
        self.directory = directory
        self.matter: Matter = {k: row["matter"] for k, row in pack.data["archetype"].items()}
        self.classes = tuple(sorted(pack.vocabulary.matter_classes))
        self.balance = Balance.opening(inventory(entities, self.matter, self.classes))

    def observe(self, boundary: Boundary, entities: Collection[Entity]) -> None:
        rows = list(transactions(boundary, self.matter))
        balance = self.balance
        live = inventory(entities, self.matter, self.classes)
        balance.reconcile(boundary.tick + 1, rows, live)
        moves = [
            (e.type, e.event_id)
            for e in boundary.result.events
            if e.type in ("stack_split", "stack_merged", "item_transferred", "matter_moved")
        ]
        balance.transfers += sum(name in ("item_transferred", "matter_moved") for name, _ in moves)
        data = canonical_json_bytes(
            {
                "tick": balance.tick,
                "turn_record": f"turns/{boundary.tick}.json",
                "expected": balance.expected,
                "observed": live,
                "entity_count": len(entities),
                "entries": [r.model_dump(mode="json") for r in rows],
                "movements": moves,
            }
        )
        store_once(self.directory / f"ledger/{balance.tick}.json", data)
        balance.prefix = extend(balance.prefix, data)
