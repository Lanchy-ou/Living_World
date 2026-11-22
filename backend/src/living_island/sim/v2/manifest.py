"""In-memory records of boundary commits, refusals, and a terminal harness stop."""

from dataclasses import dataclass, field

from pydantic import JsonValue

from living_island.persistence.v2.replay import RecordedBoundary
from living_island.world.v2.engine.tick import FallbackFact
from living_island.world.v2.protocol import SCHEMA_VERSION, TurnSubmission


@dataclass(frozen=True)
class FallbackTurn:
    submission: TurnSubmission
    reason: str
    policy_id: str

    def fact(self) -> FallbackFact:
        return FallbackFact(
            self.submission.actor_id, self.submission.turn_id, self.reason, self.policy_id
        )


@dataclass(frozen=True)
class TerminalStop:
    reason: str
    witness: JsonValue


@dataclass(frozen=True)
class BoundaryRecord:
    tick: int
    submissions: tuple[TurnSubmission, ...]
    fallback_turns: tuple[FallbackTurn, ...]
    event_lines: bytes

    def for_replay(self) -> RecordedBoundary:
        return RecordedBoundary(
            self.submissions, self.event_lines, tuple(turn.fact() for turn in self.fallback_turns)
        )


@dataclass(frozen=True)
class RefusedBoundary:
    tick: int
    submissions: tuple[TurnSubmission, ...]
    reason: str


@dataclass(frozen=True)
class StopRecord:
    tick: int
    actor_id: str
    turn_id: str
    stop: TerminalStop


@dataclass
class RunManifest:
    vocabulary_hash: str
    rule_library_hash: str
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    boundaries: list[BoundaryRecord] = field(default_factory=list, init=False)
    refusals: list[RefusedBoundary] = field(default_factory=list, init=False)
    stop: StopRecord | None = field(default=None, init=False)
