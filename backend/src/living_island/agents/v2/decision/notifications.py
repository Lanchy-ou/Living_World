"""Select notification classes from resident-visible reports."""

from collections.abc import Iterable

from living_island.agents.v2.context.state import NotificationClass
from living_island.world.v2.protocol import WorldReport


def notifications(
    reports: Iterable[WorldReport], muted: tuple[NotificationClass, ...]
) -> frozenset[NotificationClass]:
    selected: set[NotificationClass] = set()
    for report in reports:
        klass: NotificationClass
        match report.kind:
            case "need_band_changed" | "need_threshold_crossed":
                klass = "body"
            case "utterance_heard":
                klass = "direct_speech" if report.addressed else "nearby_speech"
            case "entity_first_seen":
                klass = "discovery"
            case "progress_step":
                klass = "progress"
            case _:
                continue
        critical = report.subject_id in ("hydration", "satiety") and report.band == "critical"
        if klass not in muted or critical:
            selected.add(klass)
    return frozenset(selected)
