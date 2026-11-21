"""In-memory records of committed boundaries and a terminal harness stop."""

from dataclasses import dataclass, field

from pydantic import JsonValue

from living_island.world.v2.protocol import SCHEMA_VERSION, TurnSubmission


@dataclass(frozen=True)
class FallbackTurn:
    submission: TurnSubmission
    reason: str
    policy_id: str


@dataclass(frozen=True)
class TerminalStop:
    reason: str
    witness: JsonValue


@dataclass(frozen=True)
class BoundaryRecord:
    tick: int
    submissions: tuple[TurnSubmission, ...]
    fallback_turns: tuple[FallbackTurn, ...]


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
    stop: StopRecord | None = field(default=None, init=False)
