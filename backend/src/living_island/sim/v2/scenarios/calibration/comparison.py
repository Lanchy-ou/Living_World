"""Compare the private stand-alone policy traces and their archived PR-07 trajectory."""

from collections.abc import Iterable, Sequence
from hashlib import sha256
from typing import Literal

from pydantic import JsonValue

from living_island.agents.types import DecisionRecord
from living_island.sim.equivalence.compare import (
    _first,
    first_difference,
    legacy_replies,
    utterance_key,
)
from living_island.sim.equivalence.projection import (
    Decision,
    Frame,
    Outcome,
    Projection,
    ProjectionModel,
    Utterance,
    Values,
    canonical_bytes,
)
from living_island.sim.equivalence.v2_extract import _decision, _spoken
from living_island.sim.v2.compat.policy_host import PolicyCheckpoint
from living_island.world.v2.protocol import (
    ActionResult,
    TurnSubmission,
    UtteranceFeedback,
    WorldEvent,
)


class ActorTrace(PolicyCheckpoint):
    decision: DecisionRecord | None

    @property
    def decision_key(self) -> int:
        """The chosen ordinal, or the next decision ordinal while a queue runs."""
        return self.ordinal if self.decision is None else self.decision.decision_ordinal


class PolicyBoundary(ProjectionModel):
    tick: int
    actors: dict[str, ActorTrace]
    submissions: list[TurnSubmission]


class PhysicalFrame(Frame):
    # PR-07 reads physical state before attaching transitions to its boundaries.
    utterances: list[Utterance] = []
    outcomes: list[Outcome] = []
    decisions: list[Decision] = []


class Trajectory(ProjectionModel):
    opening: PhysicalFrame | None = None
    closing: PhysicalFrame
    actions: list[ActionResult]
    utterances: dict[str, UtteranceFeedback]
    spoken: list[WorldEvent]
    final_boundary: PolicyBoundary | None = None


class TraceBoundary(PolicyBoundary):
    seed: int
    trajectory: Trajectory
    # Only the bridge records translated objective results for the separate v1 archive check.
    projected_outcomes: list[Outcome] = []


class Difference(ProjectionModel):
    seed: int
    tick: int
    actor: str | None = None
    ordinal: int | None = None
    field: str
    expected: JsonValue
    actual: JsonValue


class TraceComparison(ProjectionModel):
    status: Literal["equal", "different", "incomplete"]
    compared_boundaries: int
    difference: Difference | None = None
    projection_sha256: str | None = None


def _difference(
    left: JsonValue,
    right: JsonValue,
    field: str,
    seed: int,
    tick: int,
    actor: str | None = None,
    ordinal: int | None = None,
) -> Difference | None:
    first = _first(left, right, field)
    if first is None:
        return None
    path, expected, actual = first
    return Difference(
        seed=seed,
        tick=tick,
        actor=actor,
        ordinal=ordinal,
        field=path,
        expected=expected,
        actual=actual,
    )


def _policy_difference(
    seed: int,
    left: PolicyBoundary,
    right: PolicyBoundary,
    prefix: str = "",
) -> Difference | None:
    for actor, row in sorted(left.actors.items()):
        other = right.actors[actor]
        if row != other:
            return _difference(
                row.model_dump(mode="json"),
                other.model_dump(mode="json"),
                f"{prefix}actors.{actor}",
                seed,
                left.tick,
                actor,
                row.decision_key,
            )
    return _difference(
        [turn.model_dump(mode="json") for turn in left.submissions],
        [turn.model_dump(mode="json") for turn in right.submissions],
        f"{prefix}submissions",
        seed,
        left.tick,
    )


def _mode_difference(left: TraceBoundary, right: TraceBoundary) -> Difference | None:
    if difference := _policy_difference(left.seed, left, right):
        return difference
    if left.trajectory != right.trajectory:
        ending = left.trajectory.closing.tick
        if difference := _difference(
            left.trajectory.model_dump(mode="json", exclude={"final_boundary"}),
            right.trajectory.model_dump(mode="json", exclude={"final_boundary"}),
            "trajectory",
            left.seed,
            ending,
        ):
            if difference.field.startswith("trajectory.opening"):
                difference.tick = left.tick
            return difference
        final, other = left.trajectory.final_boundary, right.trajectory.final_boundary
        if final is not None and other is not None:
            return _policy_difference(left.seed, final, other, "trajectory.final_boundary.")
        return _difference(
            final is not None,
            other is not None,
            "trajectory.final_boundary.present",
            left.seed,
            ending,
        )
    return None


def _decisions(boundary: PolicyBoundary, speech_ids: dict[str, str]) -> list[Decision]:
    return [
        _decision(row.decision, speech_ids)
        for _, row in sorted(boundary.actors.items())
        if row.decision is not None
    ]


class _Archive:
    """Build actual PR-07 frames in commit order using the comparator's own records."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self.speech_ids: dict[str, str] = {}

    def append(self, row: TraceBoundary) -> None:
        trajectory = row.trajectory
        if trajectory.opening is not None:
            self.frames.append(trajectory.opening.model_copy(deep=True))
        opening = self.frames[-1]
        opening.decisions = _decisions(row, self.speech_ids)
        closing = trajectory.closing.model_copy(deep=True)
        for event in trajectory.spoken:
            spoken = _spoken(event)
            closing.utterances.append(spoken)
            self.speech_ids[event.event_id] = utterance_key(
                spoken.tick, spoken.speaker, spoken.addressee
            )
        for outcome in row.projected_outcomes:
            frame = opening if outcome.tick_finished == opening.tick else closing
            frame.outcomes.append(outcome.model_copy())
        if trajectory.final_boundary is not None:
            closing.decisions = _decisions(trajectory.final_boundary, self.speech_ids)
        self.frames.append(closing)

    def projection(self, oracle: Projection) -> Projection:
        next_decision: dict[str, int] = {}
        for frame in reversed(self.frames):
            for decision in frame.decisions:
                next_decision[decision.actor_id] = frame.tick
            for outcome in frame.outcomes:
                outcome.next_decision_tick = next_decision.get(outcome.actor_id)
        # PR-07's week digest binds actual frames under the archived source/config/policy.
        return oracle.model_copy(update={"frames": self.frames})


def _coverage(values: list[str], seed: int, tick: int) -> Values:
    return {"actors": [*values], "seed": seed, "tick": tick}


def compare_traces(
    seed: int,
    opening_tick: int,
    horizon: int,
    actors: Sequence[str],
    bridge: Iterable[TraceBoundary],
    visible: Iterable[TraceBoundary],
    *,
    oracle: Projection | None = None,
    en08_sha256: str | None = None,
) -> TraceComparison:
    """Check the planned interval and roster, including boundaries with no new choice."""
    left_rows, right_rows = iter(bridge), iter(visible)
    roster = sorted(actors)
    archive = _Archive() if oracle is not None else None
    if oracle is not None:
        if difference := _difference(
            [opening_tick, opening_tick + horizon],
            [oracle.frames[0].tick, oracle.frames[-1].tick],
            "coverage.archive.interval",
            seed,
            opening_tick,
        ):
            return TraceComparison(
                status="incomplete", compared_boundaries=0, difference=difference
            )
    for offset in range(horizon):
        tick = opening_tick + offset
        left, right = next(left_rows, None), next(right_rows, None)
        if left is None or right is None:
            return TraceComparison(
                status="incomplete",
                compared_boundaries=offset,
                difference=Difference(
                    seed=seed,
                    tick=tick,
                    field="coverage.boundary",
                    expected=["bridge", "visible"],
                    actual=[
                        arm
                        for arm, row in (("bridge", left), ("visible", right))
                        if row is not None
                    ],
                ),
            )
        for arm, row in (("bridge", left), ("visible", right)):
            planned = _coverage(roster, seed, tick)
            recorded = _coverage(sorted(row.actors), row.seed, row.tick)
            planned.update(opening=opening_tick if offset == 0 else None, closing=tick + 1)
            physical = row.trajectory.opening
            recorded.update(
                opening=None if physical is None else physical.tick,
                closing=row.trajectory.closing.tick,
            )
            final = row.trajectory.final_boundary
            if oracle is not None or final is not None:
                has_final = (
                    final is not None
                    if oracle is None
                    else oracle.scripted_evidence is not None and offset + 1 == horizon
                )
                planned["final"] = {"tick": tick + 1, "actors": [*roster]} if has_final else None
                recorded["final"] = (
                    {"tick": final.tick, "actors": [*sorted(final.actors)]}
                    if final is not None
                    else None
                )
            if difference := _difference(planned, recorded, f"coverage.{arm}", seed, tick):
                return TraceComparison(
                    status="incomplete",
                    compared_boundaries=offset,
                    difference=difference,
                )
        if difference := _mode_difference(left, right):
            return TraceComparison(
                status="different",
                compared_boundaries=offset,
                difference=difference,
            )
        if archive is not None:
            archive.append(left)
    for arm, rows in (("bridge", left_rows), ("visible", right_rows)):
        if (extra := next(rows, None)) is not None:
            return TraceComparison(
                status="incomplete",
                compared_boundaries=horizon,
                difference=Difference(
                    seed=seed,
                    tick=opening_tick + horizon,
                    field=f"coverage.{arm}.tick",
                    expected=None,
                    actual=extra.tick,
                ),
            )
    if archive is not None and oracle is not None:
        actual = archive.projection(oracle)
        for baseline, frame in zip(legacy_replies(oracle).frames, actual.frames, strict=True):
            first = first_difference(baseline, frame)
            if first is not None:
                return TraceComparison(
                    status="different",
                    compared_boundaries=horizon,
                    difference=Difference(
                        seed=seed,
                        tick=baseline.tick,
                        field=f"archive.{first['field']}",
                        expected=first["expected"],
                        actual=first["actual"],
                    ),
                )
        digest = sha256(canonical_bytes(actual)).hexdigest()
        if en08_sha256 is not None and digest != en08_sha256:
            return TraceComparison(
                status="different",
                compared_boundaries=horizon,
                projection_sha256=digest,
                difference=Difference(
                    seed=seed,
                    tick=opening_tick + horizon,
                    field="en08.v2_projection_sha256",
                    expected=en08_sha256,
                    actual=digest,
                ),
            )
        return TraceComparison(
            status="equal", compared_boundaries=horizon, projection_sha256=digest
        )
    return TraceComparison(status="equal", compared_boundaries=horizon)
