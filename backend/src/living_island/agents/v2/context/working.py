"""Assemble a decision and retain the exact resident-visible parts for consolidation."""

from dataclasses import dataclass, field
from typing import Literal

from living_island.agents.v2.calls.contracts import INSTRUCTIONS, Contract, prompt_version_for
from living_island.agents.v2.calls.guard import Assembly, Call, Part, Prepared, Ref, prepare
from living_island.agents.v2.calls.journal import Journal

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
        stage: Literal["decision", "decision_after_recall"] = "decision",
        protected_recall_ids: frozenset[str] = frozenset(),
    ) -> Prepared:
        prefix = self.prefix.parts
        entries = self.log.entries
        state_start = len(prefix) + len(entries)
        assembly = Assembly.decision(
            (*prefix, *(entry.part for entry in entries), *state.parts),
            prefix_memories=self.prefix.memory_positions,
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
