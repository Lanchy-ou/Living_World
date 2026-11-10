"""Technical validity of one run (P2 experiments §4 checks 1-8). Pure over parsed objects.

An artifact that failed to load arrives as ``None`` with its loader error in ``load_errors``;
every check that needs it fails with that reason instead of raising.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from living_island.agents.types import DecisionRecord, DecisionTraceManifest
from living_island.contract.projections import project_frame
from living_island.contract.replay import DisplayFrame, ReplayBundle
from living_island.contract.save import SavePackage
from living_island.events import WorldEvent

from .canon import canonical_bytes, canonical_sha256, sha256_hex
from .data import RunLimits, payload_of


@dataclass(frozen=True)
class ValidityInputs:
    """Everything the eight checks read; ``None`` marks an artifact that did not load."""

    cli_exit_code: int | None
    expected_ticks: int  # the configured ``--ticks``
    limits: RunLimits | None
    trace: DecisionTraceManifest | None
    events: tuple[WorldEvent, ...] | None
    records: tuple[DecisionRecord, ...] | None
    tick0: SavePackage | None
    final: SavePackage | None
    replay: ReplayBundle | None
    # Manifest identity for check 7 (``None`` when the manifest is being built from this run).
    expected_policy_config_sha256: str | None = None
    load_errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    check: int
    name: str
    ok: bool
    problems: tuple[str, ...]


@dataclass(frozen=True)
class ValidityReport:
    valid: bool
    checks: tuple[CheckResult, ...]

    @property
    def failed(self) -> tuple[int, ...]:
        return tuple(c.check for c in self.checks if not c.ok)


def _missing(inputs: ValidityInputs, *names: str) -> list[str]:
    values = {
        "trace": inputs.trace,
        "events": inputs.events,
        "records": inputs.records,
        "tick0": inputs.tick0,
        "final": inputs.final,
        "replay": inputs.replay,
        "limits": inputs.limits,
    }
    return [
        f"{name} unavailable: {inputs.load_errors.get(name, 'not loaded')}"
        for name in names
        if values[name] is None
    ]


def _events_at(events: tuple[WorldEvent, ...], tick: int) -> int:
    return sum(1 for e in events if e.tick == tick)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def _check_1(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "trace")
    if inputs.cli_exit_code is None:
        problems.append("no case manifest: it is written only after the CLI exits 0")
    elif inputs.cli_exit_code != 0:
        problems.append(f"the CLI exited {inputs.cli_exit_code}, expected 0")
    return problems


def _check_2(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "trace")
    if inputs.trace is not None and inputs.trace.final_tick != inputs.expected_ticks:
        problems.append(
            f"manifest final tick {inputs.trace.final_tick} != --ticks {inputs.expected_ticks}"
        )
    return problems


def _check_3(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "tick0", "final", "events", "trace")
    if problems:
        return problems
    assert inputs.tick0 is not None and inputs.final is not None
    assert inputs.events is not None and inputs.trace is not None
    zero, final = inputs.tick0, inputs.final
    if zero.world.tick != 0:
        problems.append(f"tick-zero file has world.tick {zero.world.tick}")
    if zero.decision_record_cursor != 0:
        problems.append(f"tick-zero decision_record_cursor {zero.decision_record_cursor} != 0")
    count0 = _events_at(inputs.events, 0)
    if zero.event_cursor != count0:
        problems.append(f"tick-zero event_cursor {zero.event_cursor} != {count0} tick-0 events")
    initialized = next((e for e in inputs.events if e.type == "world_initialized"), None)
    if initialized is None or initialized.tick != 0:
        problems.append("no world_initialized event at tick 0")
    else:
        expected = payload_of(initialized).initial_snapshot_hash
        actual = canonical_sha256(zero.world)
        if actual != expected:
            problems.append("SHA-256(tick-zero world) != world_initialized.initial_snapshot_hash")
    if final.world.tick != inputs.trace.final_tick:
        problems.append(f"final file has world.tick {final.world.tick}")
    return problems


def _check_4(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "final", "trace")
    if problems:
        return problems
    assert inputs.final is not None and inputs.trace is not None
    final, trace = inputs.final, inputs.trace
    if canonical_sha256(final.world) != trace.final_world_sha256:
        problems.append("SHA-256(final world) != final_world_sha256")
    if final.event_cursor != trace.event_count:
        problems.append(f"final event_cursor {final.event_cursor} != event_count")
    if final.decision_record_cursor != trace.record_count:
        problems.append(
            f"final decision_record_cursor {final.decision_record_cursor} != record_count"
        )
    return problems


def _check_5(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "replay", "trace", "events", "tick0", "final")
    if problems:
        return problems
    assert inputs.replay is not None and inputs.trace is not None
    assert inputs.events is not None and inputs.tick0 is not None and inputs.final is not None
    replay, trace, events = inputs.replay, inputs.trace, inputs.events
    final_tick = trace.final_tick
    if len(replay.frames) != final_tick + 1:
        problems.append(f"{len(replay.frames)} frames, expected {final_tick + 1}")
    for name, got, want in (
        ("run_id", replay.run_id, trace.run_id),
        ("config_hash", replay.config_hash, trace.config_hash),
        ("map_hash", replay.map_hash, trace.map_hash),
    ):
        if got != want:
            problems.append(f"replay {name} differs from the trace manifest")
    if len(replay.events) != len(events):
        problems.append(f"replay has {len(replay.events)} events, events.jsonl {len(events)}")
    else:
        for index, (from_replay, from_log) in enumerate(zip(replay.events, events, strict=True)):
            if canonical_bytes(from_replay) != canonical_bytes(from_log):
                problems.append(f"replay event {index} ({from_log.event_id}) differs in bytes")
                break
    if replay.frames and len(replay.frames) == final_tick + 1:
        first = project_frame(inputs.tick0.world, _events_at(events, 0))
        last = project_frame(inputs.final.world, _events_at(events, final_tick))
        if replay.frames[0] != first:
            problems.append("F[0] differs from the tick-zero checkpoint projection")
        if replay.frames[-1] != last:
            problems.append("F[T] differs from the final checkpoint projection")
    return problems


def frame_problems(
    frames: tuple[DisplayFrame, ...], events: tuple[WorldEvent, ...], limits: RunLimits
) -> list[str]:
    """Check 6: per-frame canteen, capacity, tree, slot and fruit-conservation invariants."""
    problems: list[str] = []
    regrown: dict[int, int] = {}
    consumed: dict[int, int] = {}
    for event in events:
        if event.type == "fruit_regrew":
            regrown[event.tick] = regrown.get(event.tick, 0) + payload_of(event).quantity
        elif event.type == "fruit_consumed":
            consumed[event.tick] = consumed.get(event.tick, 0) + payload_of(event).quantity
    initial_stock = sum(t.stock for t in frames[0].fruit_trees)
    cumulative_regrown = cumulative_consumed = 0
    for frame in frames:
        tick = frame.tick
        cumulative_regrown += regrown.get(tick, 0)
        cumulative_consumed += consumed.get(tick, 0)
        holders = [r for r in frame.residents if r.alive and r.canteen_servings is not None]
        locations = len(holders) + (1 if frame.ground_canteen is not None else 0)
        if locations != 1:
            problems.append(f"F[{tick}]: the canteen has {locations} locations, expected 1")
        for resident in frame.residents:
            if not resident.alive and (
                resident.canteen_servings is not None or resident.fruit_count != 0
            ):
                problems.append(f"F[{tick}]: dead {resident.id} holds items")
            if resident.canteen_servings is not None and not (
                0 <= resident.canteen_servings <= limits.canteen_capacity
            ):
                problems.append(f"F[{tick}]: {resident.id} canteen servings out of range")
            if resident.alive:
                slots = resident.fruit_count + (1 if resident.canteen_servings is not None else 0)
                if slots > limits.slot_capacity:
                    problems.append(f"F[{tick}]: {resident.id} uses {slots} slots")
        if frame.ground_canteen is not None and not (
            0 <= frame.ground_canteen.servings <= limits.canteen_capacity
        ):
            problems.append(f"F[{tick}]: ground canteen servings out of range")
        for tree in frame.fruit_trees:
            if not 0 <= tree.stock <= limits.max_stock_per_tree:
                problems.append(f"F[{tick}]: tree {tree.id} stock {tree.stock} out of range")
        present = (
            sum(t.stock for t in frame.fruit_trees)
            + sum(r.fruit_count for r in frame.residents)
            + sum(g.quantity for g in frame.ground_fruit)
            + cumulative_consumed
        )
        expected = initial_stock + cumulative_regrown
        if expected != present:
            problems.append(f"F[{tick}]: fruit not conserved ({expected} != {present})")
        if len(problems) >= 20:
            problems.append("further frame problems omitted")
            break
    return problems


def _check_6(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "replay", "events", "limits")
    if problems:
        return problems
    assert inputs.replay is not None and inputs.events is not None and inputs.limits is not None
    return frame_problems(tuple(inputs.replay.frames), inputs.events, inputs.limits)


def _check_7(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "tick0")
    if problems:
        return problems
    assert inputs.tick0 is not None
    configs = [r.policy_config for r in inputs.tick0.agent_state.runtime_states]
    if not configs:
        return ["the tick-zero checkpoint has no runtime states"]
    digests = {canonical_sha256(config) for config in configs}
    if len(digests) != 1:
        problems.append("policy_config differs across residents at tick zero")
    expected = inputs.expected_policy_config_sha256
    if expected is not None and digests != {expected}:
        problems.append("policy_config differs from the manifest policy config")
    return problems


def _check_8(inputs: ValidityInputs) -> list[str]:
    problems = _missing(inputs, "records")
    if inputs.records is not None:
        substituted = sum(1 for r in inputs.records if r.substituted)
        if substituted:
            problems.append(f"{substituted} decision records have substituted = true")
    return problems


CHECKS: tuple[tuple[int, str, Callable[[ValidityInputs], list[str]]], ...] = (
    (1, "CLI exit 0 and trace loads", _check_1),
    (2, "final tick equals the configured run length", _check_2),
    (3, "tick-zero and final checkpoints", _check_3),
    (4, "final checkpoint matches the trace manifest", _check_4),
    (5, "replay agrees with the trace and checkpoints", _check_5),
    (6, "frame invariants", _check_6),
    (7, "policy configs at tick zero", _check_7),
    (8, "no substituted decision", _check_8),
)


def assess_validity(inputs: ValidityInputs) -> ValidityReport:
    """Run all eight checks; the run is valid iff every check passes."""
    results = tuple(
        CheckResult(number, name, not (problems := check(inputs)), tuple(problems))
        for number, name, check in CHECKS
    )
    return ValidityReport(all(r.ok for r in results), results)


def frame_digest(frame: DisplayFrame) -> str:
    """Digest of a frame (used by tests and reports to name a frame without printing it)."""
    return sha256_hex(canonical_bytes(frame))
