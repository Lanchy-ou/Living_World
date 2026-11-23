"""Open the fixed, resident-visible part of one confirmed waking period."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from living_island.agents.v2.calls.contracts import Contract, MorningIDs, digest, json_bytes
from living_island.agents.v2.calls.guard import Assembly, Call, Part, Prepared, Ref, prepare
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.memory.v2.profiles import SelectedProfile, TraitValues
from living_island.memory.v2.projections import ProjectedRevision, ResidentView, RevisionRef
from living_island.world.v2.protocol import EnabledVerb

if TYPE_CHECKING:
    from .state import CurrentState


@dataclass(frozen=True)
class ResidentIdentity:
    name: str
    profile: SelectedProfile


@dataclass(frozen=True)
class VerbDescription:
    """Sim projects an enabled verb and its neutral resident-facing description."""

    verb: EnabledVerb
    description: str


def memory_ref(ref: RevisionRef) -> Ref:
    return Ref(kind="memory", id=ref.id, version=f"{ref.store_version}:{ref.content_hash}")


@dataclass(frozen=True)
class MemoryFragment:
    revision: RevisionRef
    part: Part

    @property
    def sha256(self) -> str:
        return digest(self.part.text.encode())


def render_memory(revision: ProjectedRevision) -> MemoryFragment:
    """Pin the MM-01 resident projection as it was when this record was selected."""
    text = json_bytes(revision.record.model_dump(mode="json")).decode()
    return MemoryFragment(revision.ref, Part("prefix", memory_ref(revision.ref), text))


class MorningReceipt(Fact):
    call_id: str
    prepared_cursor: str
    outcome: Literal["adopted", "failed", "stopped_unfit"]
    selected_ids: tuple[str, ...]
    ignored_ids: tuple[str, ...]


@dataclass(frozen=True)
class MorningStop:
    prepared: Prepared
    morning: MorningReceipt


@dataclass(frozen=True)
class FrozenPrefix:
    period_id: str
    enabled_verbs: tuple[EnabledVerb, ...]
    fixed: tuple[Part, ...]
    memories: tuple[MemoryFragment, ...]
    morning: MorningReceipt | None

    @property
    def parts(self) -> tuple[Part, ...]:
        # DL-01 supplies this call kind's pinned instruction as the first (system) part.
        return self.fixed + tuple(memory.part for memory in self.memories)

    @property
    def memory_positions(self) -> tuple[int, ...]:
        return tuple(range(len(self.fixed), len(self.fixed) + len(self.memories)))


def _fixed_part(key: str, text: str, version: str = "prefix/0.1") -> Part:
    return Part("prefix", Ref(kind="template", id=key, version=version), text)


def _trait_words(traits: TraitValues) -> str:
    levels = ("hardly ", "slightly ", "moderately ", "", "very ")
    adjectives = (
        (traits.curiosity, "curious"),
        (traits.caution, "cautious"),
        (traits.sociability, "sociable"),
        (traits.trustfulness, "trusting"),
        (traits.diligence, "diligent"),
    )
    words = (levels[value] + adjective for value, adjective in adjectives)
    return "You are " + ", ".join(words) + "."


def open_prefix(
    *,
    call: Call,
    identity: ResidentIdentity,
    verbs: tuple[VerbDescription, ...],
    traits: TraitValues,
    view: ResidentView,
    store_version: int,
    memory_on: bool,
    waking: CurrentState,
    journal: Journal,
    select: Callable[[Prepared], MorningIDs | None],
    previous: FrozenPrefix | None = None,
) -> FrozenPrefix | MorningStop:
    """Sim supplies the period ID and a retrying caller. None means its retries failed."""
    if previous is not None and previous.period_id == call.period_id:
        return previous

    profile = identity.profile
    identity_part = _fixed_part(
        "identity",
        f"Your name is {identity.name}. Your values: " + ", ".join(profile.document.values) + ".",
        profile.sha256,
    )
    fixed = (
        _fixed_part("verbs", "\n".join(f"{v.verb.id}: {v.description}" for v in verbs)),
        identity_part,
        _fixed_part("traits", _trait_words(traits if memory_on else profile.document.traits)),
    )
    enabled = tuple(v.verb for v in verbs)
    if call.tick == 0 or not memory_on:
        return FrozenPrefix(call.period_id, enabled, fixed, (), None)

    index_head = Part(
        "index",
        Ref(kind="index", id=call.resident_id, version=str(store_version)),
        "Memory index:",
    )
    index = tuple(
        Part("index", Ref(kind="index", id=r.ref.id, version=str(store_version)), r.index_line)
        for r in view.records
    )
    parts = (identity_part, *waking.parts, index_head, *index)
    assembly = Assembly(parts, (), frozenset(range(len(parts))), 1 + waking.pressure_at)
    prepared = prepare(call, Contract("morning"), assembly, journal)
    outcome: Literal["adopted", "failed", "stopped_unfit"]
    chosen: dict[str, MemoryFragment] = {}
    ignored: list[str] = []
    if prepared.admitted is None:
        outcome = "stopped_unfit"
    elif (answer := select(prepared)) is None:
        outcome = "failed"
    else:
        outcome = "adopted"
        indexed = {r.ref.id: r for r in view.records}
        for record_id in answer.ids:
            if record_id in indexed and record_id not in chosen:
                chosen[record_id] = render_memory(indexed[record_id])
            else:
                ignored.append(record_id)

    receipt = MorningReceipt(
        call_id=call.call_id,
        prepared_cursor=prepared.cursor,
        outcome=outcome,
        selected_ids=tuple(chosen),
        ignored_ids=tuple(ignored),
    )
    journal.fact(call.call_id, "morning", receipt)
    if outcome == "stopped_unfit":
        return MorningStop(prepared, receipt)
    return FrozenPrefix(call.period_id, enabled, fixed, tuple(chosen.values()), receipt)
