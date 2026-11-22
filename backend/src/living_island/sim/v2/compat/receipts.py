"""Legacy exposure identities and ordered decision triggers."""

from living_island.world import protocol as v1
from living_island.world.v2 import protocol as v2


class LegacyReceipt(v2.ProtocolModel):
    entity_id: str
    entity_type: v1.EntityType
    x: int
    y: int


class LegacyReceipts(v2.ProtocolModel):
    entities: list[LegacyReceipt] = []
    explored: list[v2.Coord] = []
    cue_detail: dict[str, v1.CueDetailLevel] = {}

    def ingest(self, view: v1.Perception) -> tuple["LegacyReceipts", bool]:
        def receipt(entity_id: str, kind: v1.EntityType, pos: v1.Coord) -> LegacyReceipt:
            return LegacyReceipt(entity_id=entity_id, entity_type=kind, x=pos.x, y=pos.y)

        entities: tuple[v1.VisibleEntity | v1.TransientSighting, ...] = (
            *view.visible_entities,
            *view.transient_sightings,
        )
        seen = {
            receipt(entity.entity_id, entity.entity_type, entity.position) for entity in entities
        }
        seen.update(receipt(cue.cue_id, "cue", cue.position) for cue in view.environmental_cues)
        canteen = view.own_inventory.canteen_id
        if canteen is not None:
            seen.add(receipt(canteen, "canteen", view.own_position))
        prior_ids = {entity.entity_id for entity in self.entities}
        novel = any(entity.entity_id not in prior_ids for entity in seen)
        detail = dict(self.cue_detail)
        for cue in view.environmental_cues:
            prior = self.cue_detail.get(cue.cue_id)
            if cue.detail_level == "near" and prior != "near":
                novel = True
            if prior is None or cue.detail_level == "near":
                detail[cue.cue_id] = cue.detail_level
        seen.add(receipt(view.actor_id, "resident", view.own_position))
        explored = set(self.explored)
        explored.update(
            v2.Coord(x=tile.position.x, y=tile.position.y) for tile in view.explored_static_tiles
        )
        return LegacyReceipts(
            entities=sorted(
                seen.union(self.entities), key=lambda entry: (entry.entity_id, entry.y, entry.x)
            ),
            explored=sorted(explored, key=lambda point: (point.y, point.x)),
            cue_detail=detail,
        ), novel and view.tick != 0


def observed_triggers(
    packet: v2.BoundaryDelivery,
    view: v1.Perception,
    novelty: bool,
) -> set[v1.DecisionTrigger]:
    triggers: set[v1.DecisionTrigger] = set()
    if novelty:
        triggers.add("NEW_SIGHT")
    for report in packet.reports:
        if report.kind == "need_threshold_crossed" and report.threshold_id == "urgent":
            triggers.add("URGENT_NEED")
        elif report.kind == "utterance_heard":
            triggers.add("UTTERANCE_HEARD")
            if report.addressed:
                triggers.add("DIRECT_SPEECH")
        elif report.kind == "woke":
            triggers.add("WOKE")
    if any(
        utterance.speech_act == "request" and utterance.addressee_id == packet.actor_id
        for utterance in view.heard_utterances
    ):
        triggers.add("REPLY_REQUIRED")
    return triggers


def interrupt_reason(
    action: v1.ActionType,
    triggers: set[v1.DecisionTrigger],
) -> v1.InterruptionReason | None:
    if action in ("move_to", "gather", "rest"):
        if "URGENT_NEED" in triggers:
            return "URGENT_NEED"
        if "DIRECT_SPEECH" in triggers:
            return "DIRECT_SPEECH"
    if action == "move_to" and "NEW_SIGHT" in triggers:
        return "NEW_SIGHT"
    return None
