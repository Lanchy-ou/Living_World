"""Phase hooks owned by P3.5-EN-04."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tick import TickContext


def apply_physiology(ctx: TickContext) -> None:
    """Apply phase 5 physiology, death and drops in resident order."""


def hard_stops_and_waking(ctx: TickContext) -> None:
    """Run phase 6 hard stops and wake transitions before perception."""
