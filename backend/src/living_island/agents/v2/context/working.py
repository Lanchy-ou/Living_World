"""Assemble a decision and retain the exact resident-visible parts for consolidation."""

from dataclasses import dataclass, field, replace
from typing import Literal

from living_island.agents.v2.calls.contracts import INSTRUCTIONS, Contract, prompt_version_for
from living_island.agents.v2.calls.guard import Assembly, Call, Part, Prepared, Ref, prepare
from living_island.agents.v2.calls.journal import Journal
from living_island.memory.v2.projections import ResidentView

from .day_log import DayLog
from .entries import DayEntry
from .prefix import FrozenPrefix
from .state import CurrentState


@dataclass(frozen=True)
class FrozenPeriod:
    """MF takes this snapshot after logging the confirming sleep or faint packet."""

    prefix: FrozenPrefix
    entries: tuple[DayEntry, ...]
    current_state: tuple[Part, ...]

    def visible_to(self, view: ResidentView) -> "FrozenPeriod":
        """Project prompt parts without rewriting the saved prefix or append-only log."""
        ids = {revision.ref.id for revision in view.records}
        if view.current_intention is not None:
            ids.add(view.current_intention.ref.id)
        return FrozenPeriod(
            replace(
                self.prefix,
                memories=tuple(m for m in self.prefix.memories if m.revision.id in ids),
            ),
            tuple(e for e in self.entries if e.retrieved is None or e.retrieved.id in ids),
            tuple(p for p in self.current_state if p.source.kind != "memory" or p.source.id in ids),
        )

    @property
    def parts(self) -> tuple[Part, ...]:
        # Consolidation has its own system message. Retain the resident's decision
        # instructions here as part of the waking context it actually had.
        instructions = Part(
            "prefix",
            Ref(kind="template", id="decision", version=prompt_version_for("decision")),
            INSTRUCTIONS["decision"],
        )
        return (
            instructions,
            *self.prefix.parts,
            *(entry.part for entry in self.entries),
            *self.current_state,
        )


@dataclass
class WorkingContext:
    """An opened prefix and its period's log, including any pre-waking deliveries."""

    prefix: FrozenPrefix
    log: DayLog
    _last_state: tuple[Part, ...] = field(default=(), init=False)

    def prepare_decision(
        self,
        call: Call,
        state: CurrentState,
        journal: Journal,
        *,
        view: ResidentView,
        stage: Literal["decision", "decision_after_recall"] = "decision",
        protected_recall_ids: frozenset[str] = frozenset(),
    ) -> Prepared:
        # Current state was rendered from this turn's view. Only carried parts
        # can outlive their store records and need a reachability projection.
        visible = FrozenPeriod(self.prefix, self.log.entries, ()).visible_to(view)
        prefix = visible.prefix.parts
        entries = visible.entries
        state_start = len(prefix) + len(entries)
        assembly = Assembly.decision(
            (*prefix, *(entry.part for entry in entries), *state.parts),
            prefix_memories=visible.prefix.memory_positions,
            day_log=tuple(range(len(prefix), state_start)),
            pressure_at=state_start + state.pressure_at,
            recall_entries=frozenset(
                i
                for i, entry in enumerate(entries, start=len(prefix))
                if entry.id in protected_recall_ids
            ),
        )
        prepared = prepare(call, Contract(stage, self.prefix.enabled_verbs), assembly, journal)
        (cue,) = prepared.record.candidates[0].manifest.derived
        pressure_line = Part(
            "current_state",
            Ref(kind="pressure", id="pressure", version=cue.wording_version),
            cue.text,
        )
        self._last_state = (
            *state.parts[: state.pressure_at],
            pressure_line,
            *state.parts[state.pressure_at :],
        )
        return prepared

    def freeze(self) -> FrozenPeriod:
        return FrozenPeriod(self.prefix, self.log.entries, self._last_state)
