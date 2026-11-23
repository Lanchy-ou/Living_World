"""Run one resident decision, including its optional, single deliberate query."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from living_island.agents.v2.calls.contracts import Contract, MemoryIDs, RecallStep
from living_island.agents.v2.calls.guard import Assembly, Call, Part, Prepared, Ref, prepare
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.calls.provider import Returned
from living_island.agents.v2.context.entries import DayEntry, DeliberateRecall
from living_island.agents.v2.context.state import CurrentState
from living_island.agents.v2.context.working import WorkingContext
from living_island.memory.v2.projections import ProjectedRevision, ResidentView, RevisionRef

from .attribution import Credit, crediting_journal
from .recipes import RecipeCues, RecipeRegistry, strength

type StageKind = Literal["decision", "recall", "decision_after_recall"]


@dataclass(frozen=True)
class RecallStage:
    prepared: Prepared
    returned: Returned | None  # The final attempt, or None if the guard stopped the call.


@dataclass(frozen=True)
class RecallTurn:
    stages: tuple[RecallStage, ...]
    entries: tuple[DayEntry, ...]
    ignored_ids: tuple[str, ...]


class RetrievedPart(Fact):
    entry_id: str
    entry_revision: str
    retrieved: RevisionRef | None
    fragment_sha256: str


class RecallReceipt(Fact):
    entries: tuple[RetrievedPart, ...]
    ignored_ids: tuple[str, ...]


def _record(
    journal: Journal,
    producer: str,
    mode: Literal["recipe", "deliberate", "off_empty"],
    entries: tuple[DayEntry, ...],
    ignored: tuple[str, ...] = (),
) -> None:
    parts = tuple(
        RetrievedPart(
            entry_id=e.id,
            entry_revision=e.revision,
            retrieved=e.retrieved,
            fragment_sha256=e.fragment_sha256,
        )
        for e in entries
    )
    journal.fact(producer, mode, RecallReceipt(entries=parts, ignored_ids=ignored))


def _prepare_query(
    call: Call, query: str, version: int, view: ResidentView, journal: Journal
) -> tuple[Prepared, dict[str, ProjectedRevision]]:
    eligible = {r.ref.id: r for r in view.records if strength(r.record, call.tick) >= 40}
    # Keep the exact projected revisions indexed here, even if the store changes later.
    parts = (
        Part("query", Ref(kind="query", id=call.call_id, version=None), query),
        Part(
            "index", Ref(kind="index", id=call.resident_id, version=str(version)), "Memory index:"
        ),
        *(
            Part("index", Ref(kind="index", id=r.ref.id, version=str(version)), r.index_line)
            for r in eligible.values()
        ),
    )
    assembly = Assembly(parts, (), frozenset(range(len(parts))))
    return prepare(call, Contract("recall"), assembly, journal), eligible


def run_recall_turn(
    *,
    resident_id: str,
    turn_id: str,
    cues: RecipeCues,
    recipes: RecipeRegistry,
    context: WorkingContext,
    state: CurrentState,
    memory_on: bool,
    read_memory: Callable[[], tuple[int, ResidentView]],
    journal: Journal,
    dispatch: Callable[[Prepared, Journal], Returned],
    credit: Credit,
) -> RecallTurn:
    """The host supplies the resident projection, store credit and retrying DL-01 caller.

    The caller uses the supplied journal for every attempt and returns the final one.
    The host decides whether to adopt its act after binding or handle the failed stage.
    """

    def call(kind: StageKind) -> Call:
        return Call(
            call_id=f"{turn_id}:{kind}",
            resident_id=resident_id,
            tick=cues.tick,
            period_id=context.prefix.period_id,
            turn_id=turn_id,
        )

    def run(prepared: Prepared, attempt_journal: Journal) -> RecallStage:
        returned = dispatch(prepared, attempt_journal) if prepared.admitted is not None else None
        return RecallStage(prepared, returned)

    def decision(
        kind: Literal["decision", "decision_after_recall"], protected: tuple[DayEntry, ...]
    ) -> RecallStage:
        prepared = context.prepare_decision(
            call(kind),
            state,
            journal,
            stage=kind,
            protected_recall_ids=frozenset(entry.id for entry in protected),
        )
        return run(prepared, crediting_journal(journal, context.log.entries, credit))

    entries: tuple[DayEntry, ...] = ()
    if memory_on:
        _, view = read_memory()
        entries = recipes.append(view, cues, context, turn_id)
        if entries:
            _record(journal, turn_id, "recipe", entries)

    first = decision("decision", ())
    stages = [first]
    if first.returned is None or not isinstance(first.returned.parsed, RecallStep):
        return RecallTurn(tuple(stages), entries, ())

    ignored: list[str] = []
    if memory_on:
        version, view = read_memory()
        recall_call = call("recall")
        prepared, eligible = _prepare_query(
            recall_call, first.returned.parsed.query, version, view, journal
        )
        recall = run(prepared, journal)
        stages.append(recall)
        if recall.returned is None or not isinstance(recall.returned.parsed, MemoryIDs):
            return RecallTurn(tuple(stages), entries, ())
        selected: dict[str, ProjectedRevision] = {}
        for position, record_id in enumerate(recall.returned.parsed.ids):
            if position >= 5 or record_id not in eligible or record_id in selected:
                ignored.append(record_id)
            else:
                selected[record_id] = eligible[record_id]
        ref = DeliberateRecall(call_id=recall_call.call_id)
        added = tuple(
            context.log.recall(cues.tick, ref, revision) for revision in selected.values()
        )
        _record(journal, recall_call.call_id, "deliberate", added, tuple(ignored))
    else:
        added = (context.log.empty_recall(cues.tick, turn_id, 1),)
        _record(journal, turn_id, "off_empty", added)

    stages.append(decision("decision_after_recall", added))
    return RecallTurn(tuple(stages), entries + added, tuple(ignored))
