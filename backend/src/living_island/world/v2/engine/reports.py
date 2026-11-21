"""Build resident-facing reports from the boundary's physical changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..protocol import NeedBand, Perception, ReportKind, WorldReport
from .physiology import need_crossings

if TYPE_CHECKING:
    from .tick import TickContext


def report(
    kind: ReportKind,
    subject_id: str | None,
    *,
    addressed: bool | None = None,
    band: NeedBand | None = None,
    threshold_id: str | None = None,
) -> WorldReport:
    return WorldReport(
        kind=kind, subject_id=subject_id, addressed=addressed, band=band, threshold_id=threshold_id
    )


def build_reports(
    ctx: TickContext,
    view: Perception,
    first_seen: set[str],
    ended: list[WorldReport],
) -> list[WorldReport]:
    actor = view.actor_id
    if ctx.tick == 0:
        return []

    previous = ctx.previous_deliveries[actor].perception
    previous_bands = {need.need_id: need.band for need in previous.needs}
    reports = list(ended)
    reports.extend(
        report("need_band_changed", need.need_id, band=need.band)
        for need in view.needs
        if previous_bands[need.need_id] != need.band
    )
    reports.extend(
        report("need_threshold_crossed", crossing.need_id, threshold_id=crossing.threshold_id)
        for crossing in need_crossings(ctx.pack, ctx.opening_needs[actor], ctx.state.needs[actor])
    )
    reports.extend(
        report("utterance_heard", utterance.utterance_id, addressed=utterance.addressee_id == actor)
        for utterance in view.heard_utterances
    )
    reports.extend(report("entity_first_seen", key) for key in sorted(first_seen))
    reports.extend(
        report("action_observed", key)
        for key in sorted({o.intent_id for o in view.observed_actions})
    )

    steps = set(ctx.progress_reports.get(actor, ()))
    steps.update(
        key
        for key, readings in ctx.process_progress.items()
        if readings[0].before != readings[-1].after
        and any(step.actor_id == actor for step in readings)
    )
    reports.extend(report("progress_step", key) for key in sorted(steps))
    if actor in ctx.woke:
        reports.append(report("woke", None))
    return reports
