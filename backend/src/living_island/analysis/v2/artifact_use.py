"""Round 3 artifact-use metrics from the objective journal of one verified run."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from living_island.analysis.v2.joins import instance
from living_island.analysis.v2.shards import encoded
from living_island.contract import inspection_v2 as ia


@dataclass(frozen=True)
class Portion:
    origin: str
    order: tuple[int, int]
    day: int
    makers: frozenset[str]
    quantity: int
    trace: frozenset[str]


@dataclass(frozen=True)
class Missing:
    reason: str
    trace: frozenset[str]


type Stock = tuple[Portion, ...] | Missing


def joined(left: Stock, right: Stock) -> Stock:
    if isinstance(left, Missing):
        return left
    if isinstance(right, Missing):
        return right
    return tuple(sorted((*left, *right), key=lambda p: p.order))


def marked(stock: Stock, *refs: str) -> Stock:
    if isinstance(stock, Missing):
        return replace(stock, trace=stock.trace.union(refs))
    return tuple(replace(p, trace=p.trace.union(refs)) for p in stock)


def split(stock: Stock, quantity: int, physical: str) -> tuple[Stock, Stock]:
    """Take the oldest constituents without mutating a previously recorded binding."""
    if isinstance(stock, Missing):
        return stock, stock
    taken, remainder = [], []
    for p in stock:
        n = min(p.quantity, quantity)
        if n:
            taken.append(replace(p, quantity=n))
        if n < p.quantity:
            remainder.append(replace(p, quantity=p.quantity - n))
        quantity -= n
    if quantity:
        gap = Missing(f"missing physical quantity for {physical}", frozenset({physical}))
        return gap, gap
    return tuple(taken), tuple(remainder)


def lookup(stocks: dict[str, Stock], physical: str) -> Stock:
    return stocks.get(
        physical, Missing(f"missing physical history for {physical}", frozenset({physical}))
    )


class Inventory:
    def __init__(self) -> None:
        self.live: dict[str, Stock] = {}
        self.debits: dict[str, Stock] = {}
        self.debit_scope: tuple[int, str | None] | None = None
        self.contributors: defaultdict[str, dict[str, str]] = defaultdict(dict)

    def apply(
        self,
        e: ia.WorldEvent,
        day: int,
        following: ia.WorldEvent | None,
        binding_event: ia.WorldEvent | None,
    ) -> None:
        # WorldEvent has a generic JSON payload. The verified engine event type
        # selects the corresponding engine section 11 payload.
        p: dict[str, Any] = e.payload
        if e.type in {"entity_created", "entity_consumed"}:
            scope = e.tick, e.intent_id
            if scope != self.debit_scope:
                self.debits.clear()
                self.debit_scope = scope
        match e.type:
            case "process_progressed":
                self.contributors[p["process_id"]].setdefault(p["contributor_id"], e.event_id)
            case "world_rule_applied" | "act_settled" | "action_stopped":
                self.debits.clear()
            case "entity_created":
                key = p["entity_id"]
                refs = {key, e.event_id}
                if e.intent_id:
                    refs.add(e.intent_id)
                if p["recreated_from"]:
                    returned: Stock = ()
                    for part in p["recreated_from"]:
                        source = part["physical_id"]
                        debit = self.debits.get(
                            source,
                            Missing(
                                f"missing entity_consumed for returned source {source}",
                                frozenset({source}),
                            ),
                        )
                        used, self.debits[source] = split(debit, part["quantity"], source)
                        returned = joined(returned, used)
                    if binding_event:
                        refs.add(binding_event.event_id)
                    self.live[key] = marked(returned, *refs)
                    return
                makers: set[str] = set()
                if (process := p["process_id"]) is not None:
                    makers.update(self.contributors[process])
                    refs.update(self.contributors[process].values())
                    refs.add(process)
                    if not makers:
                        self.live[key] = Missing(
                            f"missing process contributions for {process}", frozenset(refs)
                        )
                        return
                elif e.actor_id is not None and p["source"] is None:
                    makers.add(e.actor_id)
                self.live[key] = (
                    Portion(
                        key,
                        (e.tick, e.seq_in_tick),
                        day,
                        frozenset(makers),
                        p["quantity"],
                        frozenset(refs),
                    ),
                )
            case "stack_split":
                source, dest = p["from_id"], p["new_id"]
                taken, left = split(lookup(self.live, source), p["quantity"], source)
                self.live[dest] = marked(taken, e.event_id, source, dest)
                self.live[source] = marked(left, e.event_id, source)
            case "stack_merged":
                source, dest = p["from_id"], p["into_id"]
                moving = lookup(self.live, source)
                # Store withdrawals materialize without entity_created. The move
                # immediately after their merge names the surviving stack.
                if source not in self.live and following and following.type == "matter_moved":
                    move: dict[str, Any] = following.payload
                    if move["from"]["kind"] == "store" and move["entity_id"] == dest:
                        moving = self.raw(source, p["quantity"], day, following)
                self.live[dest] = marked(joined(lookup(self.live, dest), moving), e.event_id, dest)
                self.live.pop(source, None)
            case "matter_moved":
                key = p["entity_id"]
                if key is not None and p["from"]["kind"] == "store" and key not in self.live:
                    self.live[key] = self.raw(key, p["quantity"], day, e)
            case "entity_consumed":
                key = p["entity_id"]
                used, self.live[key] = split(lookup(self.live, key), p["quantity"], key)
                self.debits[key] = joined(self.debits.get(key, ()), marked(used, e.event_id, key))

    @staticmethod
    def raw(key: str, quantity: int, day: int, event: ia.WorldEvent) -> Stock:
        return (
            Portion(
                key,
                (event.tick, event.seq_in_tick),
                day,
                frozenset(),
                quantity,
                frozenset({event.event_id, key}),
            ),
        )


@dataclass(frozen=True)
class Binding:
    physical: str
    quantity: int
    stock: Stock
    role: str
    event: ia.WorldEvent


@dataclass
class Act:
    items: ia.WorldEvent | None = None
    settled: ia.WorldEvent | None = None
    slots: list[Binding] = field(default_factory=list)
    missing_roles: set[str] = field(default_factory=set)
    benefits: list[Binding] = field(default_factory=list)
    missing_witnesses: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    trace: set[str] = field(default_factory=set)
    reasons: set[str] = field(default_factory=set)
    later: bool = False

    def add(self, part: Binding, actor: str, day: int) -> None:
        stock = part.stock
        makers: set[str] = set()
        if isinstance(stock, Missing):
            used: Stock = stock
        else:
            makers.update(maker for p in stock for maker in p.makers)
            if part.role != "target" and actor in makers:
                return
            used, _ = split(stock, part.quantity, part.physical)
        if isinstance(used, Missing):
            self.reasons.add(used.reason)
            self.trace.update(used.trace)
        else:
            crafted = [p for p in used if p.makers or part.role == "target"]
            if not crafted:
                return
            for p in crafted:
                self.trace.add(
                    encoded(
                        dict(
                            role=part.role,
                            physical_id=part.physical,
                            origin_id=p.origin,
                            quantity=p.quantity,
                            makers=sorted(p.makers),
                            stack_makers=sorted(makers),
                            creation_day=p.day,
                            use_day=day,
                            binding_event=part.event.event_id,
                        )
                    ).decode()
                )
                self.later |= p.day < day
                self.trace.update(p.trace)
        self.trace.update((part.physical, part.event.event_id))


def artifact_use_metrics(
    run_id: str,
    events: Sequence[ia.WorldEvent],
    decisions: Sequence[ia.DecisionRecord],
    *,
    tick_minutes: int,
) -> list[ia.Metric]:
    """Evaluate one run using its recorded replay clock and verified EV-01 inputs."""

    def day(tick: int) -> int:
        return 1 + tick * tick_minutes // 1440

    turns = {
        (r.resident_id, r.submission.action.intent.intent_id): (r, r.submission.action.intent.verb)
        for r in decisions
        if r.submission and r.submission.action.kind == "intent"
    }
    acts: defaultdict[tuple[str, str], Act] = defaultdict(Act)
    inventory = Inventory()
    ordered = sorted(events, key=lambda e: (e.tick, e.seq_in_tick))
    # A completion witness is emitted even when a capped need gained nothing.
    # Only a positive completion effect on this intent establishes a benefit.
    gains: dict[tuple[str | None, int], set[str]] = defaultdict(set)
    for e in ordered:
        payload: dict[str, Any] = e.payload
        if e.type == "needs_changed" and any(c["after"] > c["before"] for c in payload["changes"]):
            gains[e.intent_id, e.tick].add(e.event_id)

    sleeping: dict[str, tuple[str, str]] = {}
    witness_ticks: set[tuple[str, int, str]] = set()
    for i, e in enumerate(ordered):
        p: dict[str, Any] = e.payload
        actor, intent = e.actor_id, e.intent_id
        act = acts.get((actor, intent)) if actor is not None and intent is not None else None
        inventory.apply(
            e,
            day(e.tick),
            ordered[i + 1] if i + 1 < len(ordered) else None,
            act.items if act else None,
        )
        if actor is not None and e.type == "needs_changed" and "sleep_in_shelter" in p["causes"]:
            if (
                actor in sleeping
                and (sleeping[actor][1], e.tick, "completion" if intent else "per_tick")
                not in witness_ticks
                and (intent is None or e.event_id in gains.get((intent, e.tick), ()))
            ):
                acts[sleeping[actor]].missing_witnesses.append(e.event_id)
        if actor is None or intent is None:
            continue
        key = actor, intent
        if e.type == "act_items":
            act = acts[key]
            act.items = e
            for slot in p["slots"]:
                for part in slot["parts"]:
                    physical = part.get("physical_id")
                    if physical is None:
                        act.missing_roles.add(slot["role"])
                        continue
                    act.slots.append(
                        Binding(
                            physical,
                            part["quantity"],
                            lookup(inventory.live, physical),
                            slot["role"],
                            e,
                        )
                    )
        elif e.type == "act_settled":
            acts[key].settled = e
        elif e.type == "resident_fell_asleep":
            sleeping[actor] = key
        elif e.type == "condition_witness" and p["condition_id"] == "shelter":
            witness_ticks.add((intent, e.tick, p["timing"]))
            witness_turn = turns.get(key)
            # An absent decision is handled below as unknown, never as model origin.
            if witness_turn and witness_turn[1] != "sleep":
                continue
            physical = p["entity_id"]
            if physical is not None and (p["timing"] == "per_tick" or gains.get((intent, e.tick))):
                acts[key].benefits.append(
                    Binding(physical, 1, lookup(inventory.live, physical), "shelter", e)
                )

    rows = []
    uses = []
    later_ids: set[str] = set()
    for (actor, intent), act in acts.items():
        entry = turns.get((actor, intent))
        turn = entry[0] if entry else None
        refs = {run_id, actor, intent}
        if turn:
            refs.add(turn.turn_id)
        used, target = Evidence(), Evidence()
        settled = act.settled
        if settled:
            refs.add(settled.event_id)
        if act.items:
            refs.add(act.items.event_id)
        applied = settled is not None and settled.payload["kind"] == "applied"
        tools = {p.physical for p in act.slots if p.role != "target"}
        for binding in act.slots:
            if binding.role == "target":
                if binding.physical not in tools:
                    target.add(binding, actor, day(binding.event.tick))
            elif applied and settled:
                used.add(binding, actor, day(settled.tick))
        if "target" in act.missing_roles:
            target.reasons.add("missing act_items physical_id for target")
        if target.trace or target.reasons:
            rows.append(
                instance(
                    "artifact_target_only",
                    list(refs | target.trace),
                    None if target.reasons else 0,
                    "; ".join(sorted(target.reasons)) or None,
                )
            )
        if turn and turn.origin == "fallback":
            continue
        for binding in act.benefits:
            used.add(binding, actor, day(binding.event.tick))
            if (
                binding.event.payload["timing"] == "completion"
                and binding.event.event_id in used.trace
            ):
                used.trace.update(gains[intent, binding.event.tick])
        if applied and not act.items:
            used.reasons.add("missing act_items for applied act")
        if applied:
            used.reasons.update(
                f"missing act_items physical_id for {role}"
                for role in act.missing_roles - {"target"}
            )
        if act.missing_witnesses:
            used.reasons.add("missing shelter condition_witness for delivered benefit")
            used.trace.update(act.missing_witnesses)
        if not (used.trace or used.reasons):
            continue
        if turn is None or turn.origin is None:
            used.reasons.add("missing decision origin")
        reason = "; ".join(sorted(used.reasons)) or None
        row = instance("artifact_use", list(refs | used.trace), None if reason else 1, reason)
        uses.append(row)
        if used.later:
            later_ids.add(row.instance_id)
    rows.extend(uses)
    reason = "missing artifact-use evidence" if any(r.value is None for r in uses) else None
    trace = [run_id, *(r.instance_id for r in uses)]
    rows.extend(
        [
            instance("artifact_use_count", trace, None if reason else len(uses), reason),
            instance(
                "artifact_later_day_count",
                [
                    run_id,
                    *(r.instance_id for r in uses if r.instance_id in later_ids or r.value is None),
                ],
                None if reason else len(later_ids),
                reason,
            ),
            instance(
                "artifact_ev12",
                trace,
                None if reason else int(len(uses) >= 3 and bool(later_ids)),
                reason,
            ),
        ]
    )
    return sorted(rows, key=lambda r: r.instance_id)
