"""Deliver packets and settle one frozen v2 boundary at a time."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field

from living_island.persistence.v2.journal import PacketJournal
from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.protocol import (
    BoundaryDelivery,
    InvalidTurn,
    TurnSubmission,
    encode_event_line,
)

from .manifest import (
    BoundaryRecord,
    FallbackTurn,
    RefusedBoundary,
    RunManifest,
    StopRecord,
    TerminalStop,
)
from .turns import TurnRequest, turn_reasons

type DeliverPacket = Callable[[BoundaryDelivery], bool]
type DecideTurn = Callable[[TurnRequest], TurnSubmission | FallbackTurn | TerminalStop]


@dataclass
class _Delivery:
    packets: tuple[BoundaryDelivery, ...]
    acknowledged: dict[str, str]
    notifications: list[bool] = field(default_factory=list)


class Runner:
    def __init__(
        self,
        world: World,
        decide: DecideTurn,
        *,
        deliver: DeliverPacket,
        journal: PacketJournal,
    ) -> None:
        """Use the harness's packet receiver and decision callback at each boundary.

        The receiver consumes every packet and returns whether the harness
        promotes its reports to a notification for the resident.
        """
        self._world = world
        self._decide = decide
        self._deliver = deliver
        self._journal = journal
        self._delivery: _Delivery | None = None
        self.manifest = RunManifest(
            vocabulary_hash=world.state.library.vocabulary_hash,
            rule_library_hash=world.state.library.rule_library_hash,
        )

    def advance(self) -> TickResult | None:
        """Settle a boundary, or return None with its terminal witness recorded."""
        if self.manifest.stop is not None:
            return None

        world = self._world
        boundary_tick = world.tick
        if self._delivery is None:
            acknowledged = self._journal.ingest(world)
            self._delivery = _Delivery(world.pending_packets(), acknowledged)
        delivery = self._delivery
        for packet in delivery.packets[len(delivery.notifications) :]:
            delivery.notifications.append(self._deliver(packet.model_copy(deep=True)))

        submissions: list[TurnSubmission] = []
        fallback_turns: list[FallbackTurn] = []
        try:
            for packet, notification in zip(delivery.packets, delivery.notifications, strict=True):
                reasons = turn_reasons(packet, notification)
                if not reasons:
                    continue
                ordinal = world.state.turn_ordinals[packet.actor_id]
                request = TurnRequest(packet, ordinal, reasons)
                decision = self._decide(TurnRequest(packet.model_copy(deep=True), ordinal, reasons))
                match decision:
                    case TerminalStop():
                        self.manifest.stop = StopRecord(
                            boundary_tick, packet.actor_id, request.turn_id, deepcopy(decision)
                        )
                        return None
                    case FallbackTurn():
                        submission = decision.submission.model_copy(deep=True)
                        fallback_turns.append(
                            FallbackTurn(submission, decision.reason, decision.policy_id)
                        )
                    case TurnSubmission():
                        submission = decision.model_copy(deep=True)
                submissions.append(submission)
                request.check_binding(submission)

            ordered = tuple(submissions)
            result = world.step(
                ordered,
                acknowledged=delivery.acknowledged,
                fallbacks=tuple(turn.fact() for turn in fallback_turns),
            )
        except InvalidTurn as error:
            self.manifest.refusals.append(
                RefusedBoundary(boundary_tick, tuple(submissions), str(error))
            )
            raise

        self.manifest.boundaries.append(
            BoundaryRecord(
                boundary_tick,
                ordered,
                tuple(fallback_turns),
                b"".join(map(encode_event_line, result.events)),
            )
        )
        self._delivery = None
        return result
