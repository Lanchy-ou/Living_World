"""Phase hooks owned by P3.5-EN-05."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocol import Coord
    from .tick import TickContext


def observe_step(ctx: TickContext, actor_id: str, position: Coord, step: int) -> None:
    """Capture intermediate sight at an entered movement tile."""


def build_deliveries(ctx: TickContext) -> None:
    """Build phase 6 perception, update exposure and queue pending packets."""
