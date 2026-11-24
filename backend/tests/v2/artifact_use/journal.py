"""Small, deterministic objective journals and their model/fallback decision records."""

from collections import Counter

from living_island.analysis.v2.artifact_use import artifact_use_metrics
from living_island.contract import inspection_v2 as ia


class Journal:
    def __init__(self, run_id="fake-artifacts", tick_minutes=10):
        self.run_id = run_id
        self.tick_minutes = tick_minutes
        self.events = []
        self.decisions = []
        self.sequence = Counter()

    def event(self, at_tick, typ, *, actor=None, intent=None, **payload):
        seq = self.sequence[at_tick]
        self.sequence[at_tick] += 1
        event = ia.WorldEvent(
            schema_version="wap/0.1",
            run_id=self.run_id,
            tick=at_tick,
            seq_in_tick=seq,
            event_id=f"{self.run_id}:{at_tick:010}:{seq:06}",
            type=typ,
            actor_id=actor,
            intent_id=intent,
            target_id=None,
            llm_call_id=None,
            caused_by_event_ids=[],
            payload=payload,
        )
        self.events.append(event)
        return event

    def create(
        self, tick, key, maker, qty=1, *, process=None, intent=None, made_from=(), recreated_from=()
    ):
        return self.event(
            tick,
            "entity_created",
            actor=maker,
            intent=intent,
            entity_id=key,
            quantity=qty,
            archetype_id=key,
            material_id=None,
            place={"kind": "tile", "position": {"x": 1, "y": 1}},
            owner_id=None,
            rule_id="craft" if maker else process,
            source=None,
            process_id=process,
            made_from=list(made_from),
            recreated_from=list(recreated_from),
        )

    def turn(self, tick, actor, verb, origin="model", slots=()):
        tid = f"{actor}:t{len(self.decisions) + 1:06}"
        intent = tid + ":a"
        action = dict(
            action="act",
            verb=verb,
            target=None,
            instruments=[],
            inputs=[],
            params={},
            reason=None,
            actor_id=actor,
            intent_id=intent,
            turn_id=tid,
        )
        for role, parts in slots:
            public = parts[0][1]
            if role == "target":
                action["target"] = dict(kind="entity", id=public)
            elif role == "instrument":
                action["instruments"].append(dict(kind="item", id=public))
            else:
                action["inputs"].append(
                    dict(
                        item=dict(kind="held", archetype_id=public),
                        quantity=sum(qty for _, _, qty in parts),
                    )
                )
        submission = ia.TurnSubmission.model_validate(
            dict(
                schema_version="wap/0.1",
                actor_id=actor,
                turn_id=tid,
                observed_tick=tick,
                utterance=None,
                action=dict(kind="intent", intent=action),
            )
        )
        self.decisions.append(
            ia.DecisionRecord(
                record_schema="dr/0.1",
                turn_id=tid,
                resident_id=actor,
                tick=tick,
                period_id=f"{actor}:p1",
                reasons=[],
                call_ids=[],
                prepared_cursors=[],
                new_entries=[],
                output=None,
                valid_cites=[],
                invalid_cites=[],
                cited_parts=[],
                telemetry=ia.Telemetry(
                    delivery_id=tid, awake_ticks=tick, fatigue_band=None, stages=[]
                ),
                use_updates=[],
                origin=origin,
                fallback=ia.Fallback(used=origin == "fallback", reason=None, policy_id=None),
                submission=submission,
                used_memories=[],
            )
        )
        return intent

    def start(self, tick, actor, verb, slots, origin="model"):
        intent = self.turn(tick - 1, actor, verb, origin, slots)
        items = self.event(
            tick,
            "act_items",
            actor=actor,
            intent=intent,
            target=None,
            rule_id=verb,
            slots=[
                dict(
                    slot=role,
                    role=role,
                    parts=[
                        dict(
                            physical_id=key,
                            entity_id=public,
                            archetype_id=public,
                            material_id=None,
                            quantity=qty,
                        )
                        for key, public, qty in parts
                    ],
                )
                for role, parts in slots
            ],
        )
        return intent, items

    def settle(self, tick, actor, verb, intent, kind="applied"):
        return self.event(
            tick,
            "act_settled",
            actor=actor,
            intent=intent,
            verb=verb,
            kind=kind,
            rule_id=verb,
            at="completion",
            failed_check=None,
            phenomena=[],
        )

    def act(self, tick, actor, verb, slots=(), *, origin="model", kind="applied"):
        intent, items = self.start(tick, actor, verb, slots, origin)
        return intent, items, self.settle(tick, actor, verb, intent, kind)

    def metrics(self):
        return artifact_use_metrics(
            self.run_id, self.events, self.decisions, tick_minutes=self.tick_minutes
        )


def one_part(role, key, qty=1):
    return [(role, [(key, key, qty)])]


def family(rows, metric):
    return [r for r in rows if r.metric == metric]


def totals(rows):
    return tuple(
        family(rows, name)[0].value
        for name in ("artifact_use_count", "artifact_later_day_count", "artifact_ev12")
    )


def portions(row):
    import json

    return [json.loads(s) for s in row.trace if s.startswith("{")]
