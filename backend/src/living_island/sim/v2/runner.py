"""Deliver packets and settle one frozen v2 boundary at a time."""

from collections.abc import Callable
from operator import attrgetter

from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.protocol import BoundaryDelivery, TurnSubmission

from .manifest import BoundaryRecord, FallbackTurn, RunManifest, StopRecord, TerminalStop
from .turns import TurnRequest, turn_reasons

type DeliverPacket = Callable[[BoundaryDelivery], bool]
type DecideTurn = Callable[[TurnRequest], TurnSubmission | FallbackTurn | TerminalStop]


class Runner:
    def __init__(
        self,
        world: World,
        decide: DecideTurn,
        *,
        deliver: DeliverPacket,
    ) -> None:
        """Use the harness's packet receiver and decision callback at each boundary.

        The receiver consumes every packet and returns whether the harness
        promotes its reports to a notification for the resident.
        """
        self._world = world
        self._decide = decide
        self._deliver = deliver
        self.manifest = RunManifest(
            vocabulary_hash=world.state.library.vocabulary_hash,
            rule_library_hash=world.state.library.rule_library_hash,
        )

    def advance(self) -> TickResult | None:
        """Settle a boundary, or return None with its terminal witness recorded."""
        if self.manifest.stop is not None:
            return None

        state = self._world.state
        boundary_tick = state.tick
        packets = sorted(state.pending_deliveries.values(), key=attrgetter("actor_id"))
        acknowledged = {packet.actor_id: packet.delivery_id for packet in packets}
        delivered = [(packet, self._deliver(packet)) for packet in packets]

        submissions: list[TurnSubmission] = []
        fallback_turns: list[FallbackTurn] = []
        for packet, notification in delivered:
            reasons = turn_reasons(packet, notification)
            if not reasons:
                continue
            request = TurnRequest(packet, state.turn_ordinals[packet.actor_id], reasons)
            decision = self._decide(request)
            match decision:
                case TerminalStop():
                    self.manifest.stop = StopRecord(
                        boundary_tick, packet.actor_id, request.turn_id, decision
                    )
                    return None
                case FallbackTurn():
                    submissions.append(decision.submission)
                    fallback_turns.append(decision)
                case TurnSubmission():
                    submissions.append(decision)

        ordered = tuple(sorted(submissions, key=attrgetter("actor_id")))
        result = self._world.step(ordered, acknowledged=acknowledged)
        self.manifest.boundaries.append(
            BoundaryRecord(boundary_tick, ordered, tuple(fallback_turns))
        )
        return result
