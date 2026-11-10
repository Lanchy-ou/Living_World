"""rule-based-v0: the deterministic rule policy (Rule Policy Spec v0.1, R0-R12).

Imports only ``world.protocol``, ``agents.types``, the shared plan builders and the standard
library. ``decide`` reads the perception, the committed state and the frozen config; it uses
no clock, randomness, IO or global state, and chooses only through the §2.1 seeded tie-break.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal, TypeVar, cast

from living_island.agents.policies._plans import make_plan
from living_island.agents.rule_based.keys import (
    BACKOFF,
    LOCAL_CODES,
    LOCAL_ENTRY_LIMIT,
    SELF,
    Key,
    entity_key,
    key_of_target,
    resident_key,
    target_of_key,
    tile_key,
)
from living_island.agents.types import (
    CueImpression,
    DecisionRequest,
    FailedTarget,
    IntentTemplate,
    IssuedIntent,
    OkOutcome,
    PolicyConfig,
    RuleCommitment,
    RuleParams,
    RuleStateV0_1,
    TargetKey,
)
from living_island.world.protocol import (
    ActionType,
    DrinkParameters,
    DrinkSource,
    EmptyParameters,
    EntityTarget,
    ItemRequest,
    ItemTransferParameters,
    ItemType,
    NeedBand,
    Perception,
    ResidentTarget,
    SpeechAct,
    TalkParameters,
    TileTarget,
    TransientSighting,
    VisibleEntity,
)
from living_island.world.protocol import Coord as ProtoCoord

_BAND: dict[str, int] = {"critical": 0, "low": 1, "moderate": 2, "good": 3, "strong": 4}
_PASSABLE = frozenset({"beach", "grass", "woods", "cave", "fruit_tree", "damp_moss"})
_DIRECTIONS = frozenset({"north", "east", "south", "west"})

Goal = Literal["water", "tree", "canteen", "explore"]
Pos = tuple[int, int]  # (x, y)
_T = TypeVar("_T", bound=Hashable)


def _at_most(band: NeedBand, limit: str) -> bool:
    return _BAND[band] <= _BAND[limit]


def _at_least(band: NeedBand, limit: str) -> bool:
    return _BAND[band] >= _BAND[limit]


def _manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _yx(pos: Pos) -> tuple[int, int]:
    return pos[1], pos[0]


@dataclass(frozen=True)
class _Item:
    """One planned intent with the key §2 matching and §7.1 references use."""

    template: IntentTemplate
    action: ActionType
    key: Key | None
    is_request: bool = False
    ref_target: TargetKey | None = None


def _simple(action: ActionType) -> _Item:
    template = IntentTemplate(
        action_type=action, target=None, parameters=EmptyParameters(), reason=None
    )
    return _Item(template, action, None)


def _item_move(pos: Pos) -> _Item:
    target = TileTarget(kind="tile", position=ProtoCoord(x=pos[0], y=pos[1]))
    template = IntentTemplate(
        action_type="move_to", target=target, parameters=EmptyParameters(), reason=None
    )
    return _Item(template, "move_to", tile_key(*pos), ref_target=target)


def _item_gather(entity_id: str, pos: Pos) -> _Item:
    template = IntentTemplate(
        action_type="gather",
        target=EntityTarget(kind="entity", id=entity_id),
        parameters=EmptyParameters(),
        reason=None,
    )
    ref = TileTarget(kind="tile", position=ProtoCoord(x=pos[0], y=pos[1]))
    return _Item(template, "gather", tile_key(*pos), ref_target=ref)


def _item_drink(source: str) -> _Item:
    template = IntentTemplate(
        action_type="drink",
        target=None,
        parameters=DrinkParameters(source=cast(DrinkSource, source)),
        reason=None,
    )
    return _Item(template, "drink", None)


def _item_fill(canteen_id: str) -> _Item:
    target = EntityTarget(kind="entity", id=canteen_id)
    template = IntentTemplate(
        action_type="fill_canteen", target=target, parameters=EmptyParameters(), reason=None
    )
    return _Item(template, "fill_canteen", entity_key(canteen_id), ref_target=target)


def _item_pick_up(pos: Pos) -> _Item:
    target = TileTarget(kind="tile", position=ProtoCoord(x=pos[0], y=pos[1]))
    template = IntentTemplate(
        action_type="pick_up",
        target=target,
        parameters=ItemTransferParameters(item_type="canteen", quantity=1),
        reason=None,
    )
    return _Item(template, "pick_up", tile_key(*pos), ref_target=target)


def _item_give(resident_id: str, item_type: str, quantity: int) -> _Item:
    target = ResidentTarget(kind="resident", id=resident_id)
    template = IntentTemplate(
        action_type="give",
        target=target,
        parameters=ItemTransferParameters(item_type=cast(ItemType, item_type), quantity=quantity),
        reason=None,
    )
    return _Item(template, "give", resident_key(resident_id), ref_target=target)


def _item_talk(
    resident_id: str,
    act: str,
    *,
    request: ItemRequest | None = None,
    in_reply_to: str | None = None,
) -> _Item:
    target = ResidentTarget(kind="resident", id=resident_id)
    extra: dict[str, ItemRequest | str] = {}
    if request is not None:
        extra["request"] = request
    if in_reply_to is not None:
        extra["in_reply_to"] = in_reply_to
    template = IntentTemplate(
        action_type="talk",
        target=target,
        parameters=TalkParameters.model_validate(
            {"speech_act": cast(SpeechAct, act), "text": "", **extra}
        ),
        reason=None,
    )
    return _Item(
        template, "talk", resident_key(resident_id), is_request=act == "request", ref_target=target
    )


@dataclass
class _Commit:
    goal: str
    target: Pos
    set_at_tick: int


class _Decision:
    """One decision: R0 on a working copy, then R1-R12 in order."""

    def __init__(self, config: PolicyConfig, request: DecisionRequest, state: RuleStateV0_1):
        params = config.rule_params
        if params is None:
            raise ValueError("rule-based-v0 requires rule_params")
        self.config = config
        self.params: RuleParams = params
        self.request = request
        self.p: Perception = request.context.perception
        self.tick = request.tick
        self.own: Pos = (self.p.own_position.x, self.p.own_position.y)
        self.enabled = params.canteen_use == "enabled"
        self.cue_enabled = params.cue_use == "enabled"
        self.state = state
        # (action, key) -> (code, retry_after_tick)
        self.entries: dict[tuple[str, Key], tuple[str, int]] = {
            (e.action, cast(Key, key_of_target(e.target))): (e.code, e.retry_after_tick)
            for e in state.failed_targets
        }
        self.commit: _Commit | None = (
            _Commit(
                state.commitment.goal,
                (state.commitment.target.x, state.commitment.target.y),
                state.commitment.set_at_tick,
            )
            if state.commitment is not None
            else None
        )
        self.capacity = state.canteen_capacity
        self.cue: CueImpression | None = state.cue_impressions[0] if state.cue_impressions else None
        self._geo: tuple[dict[Pos, str], set[Pos], dict[Pos, int]] | None = None

    # -- geometry (§2) ------------------------------------------------------------------

    def _geometry(self) -> tuple[dict[Pos, str], set[Pos], dict[Pos, int]]:
        if self._geo is None:
            terrain: dict[Pos, str] = {
                (t.position.x, t.position.y): t.terrain for t in self.p.explored_static_tiles
            }
            passable = {pos for pos, name in terrain.items() if name in _PASSABLE}
            dist: dict[Pos, int] = {self.own: 0}
            queue = deque([self.own])
            while queue:
                x, y = queue.popleft()
                for nxt in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
                    if nxt in passable and nxt not in dist:
                        dist[nxt] = dist[(x, y)] + 1
                        queue.append(nxt)
            self._geo = (terrain, passable, dist)
        return self._geo

    @property
    def explored(self) -> dict[Pos, str]:
        return self._geometry()[0]

    @property
    def dist(self) -> dict[Pos, int]:
        return self._geometry()[2]

    @staticmethod
    def _neighbors(pos: Pos) -> tuple[Pos, Pos, Pos, Pos]:
        x, y = pos
        return (x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)

    # -- back-off bookkeeping (§5) -------------------------------------------------------

    def _failed(self, action: str, key: Key) -> bool:
        return (action, key) in self.entries

    def _blocked(self, items: Iterable[_Item]) -> bool:
        for item in items:
            for action, key in self.entries:
                if action == "request":
                    if item.is_request and item.key == key:
                        return True
                elif item.action == action and (key == SELF or item.key == key):
                    return True
        return False

    def _write_failure(self, action: str, key: Key, code: str) -> None:
        self.entries[(action, key)] = (code, self.tick + self.params.failed_target_retry_ticks)

    def _write_local(self, action: str, key: Key, code: str) -> None:
        existing = self.entries.get((action, key))
        if existing is not None and existing[0] not in LOCAL_CODES:
            return
        if existing is None:
            local = [(v[1], k) for k, v in self.entries.items() if v[0] in LOCAL_CODES]
            if len(local) >= LOCAL_ENTRY_LIMIT:
                victim = min(local, key=lambda rk: (rk[0], rk[1][0], rk[1][1]))
                del self.entries[victim[1]]
        self.entries[(action, key)] = (code, self.tick + self.params.failed_target_retry_ticks)

    # -- R0 -------------------------------------------------------------------------------

    def _r0(self) -> None:
        p = self.p
        # 1. expiry
        self.entries = {k: v for k, v in self.entries.items() if v[1] > self.tick}
        # 2. feedback
        fb = p.last_action_feedback
        if fb is not None:
            ref = next((r for r in self.state.issued_intents if r.intent_id == fb.intent_id), None)
            if ref is not None:
                servings = p.own_inventory.canteen_servings
                if ref.action_type == "fill_canteen" and servings is not None:
                    if fb.status == "success" or (
                        fb.status == "failure" and fb.failure_code == "ALREADY_FULL"
                    ):
                        self.capacity = servings
                if fb.status == "failure" and fb.failure_code is not None:
                    source = BACKOFF.get(ref.action_type, {}).get(fb.failure_code)
                    key = SELF if source == "self" else key_of_target(ref.target)
                    if source is not None and key is not None:
                        self._write_failure(ref.action_type, key, fb.failure_code)
        # 3. refusals
        for u in p.heard_utterances:
            if u.speech_act == "refuse" and u.addressee_id == self.request.actor_id:
                self._write_local("request", resident_key(u.speaker_id), "REFUSED")
        # 4. observed tree stock
        for tree in self._current_trees():
            key = tile_key(tree.position.x, tree.position.y)
            if tree.fruit_band == "empty":
                self._write_local("gather", key, "OBSERVED_EMPTY")
            else:
                entry = self.entries.get(("gather", key))
                if entry is not None and entry[0] == "OBSERVED_EMPTY":
                    del self.entries[("gather", key)]
        # 5. cue impressions
        self._merge_cues()
        # 6. commitment invalidation
        c = self.commit
        if c is not None and (
            self.own == c.target
            or self._failed("move_to", tile_key(*c.target))
            or (c.goal == "explore" and c.target in self.explored)
        ):
            self.commit = None

    def _current_trees(self) -> list[VisibleEntity | TransientSighting]:
        trees: list[VisibleEntity | TransientSighting] = [
            e for e in self.p.visible_entities if e.entity_type == "fruit_tree"
        ]
        trees.extend(s for s in self.p.transient_sightings if s.entity_type == "fruit_tree")
        return trees

    def _merge_cues(self) -> None:
        for cue in self.p.environmental_cues:
            cur = self.cue
            if cur is not None and cur.cue_id != cue.cue_id:
                continue
            near_seen = cue.detail_level == "near"
            if cur is None:
                self.cue = CueImpression(
                    cue_id=cue.cue_id,
                    position=cue.position,
                    detail_level=cue.detail_level,
                    direction=cue.direction if near_seen else None,
                )
                continue
            detail: Literal["distant", "near"] = (
                "near" if near_seen or cur.detail_level == "near" else "distant"
            )
            direction = cur.direction
            if near_seen and cue.direction is not None:
                direction = cue.direction
            self.cue = CueImpression(
                cue_id=cur.cue_id,
                position=cur.position,
                detail_level=detail,
                direction=direction if detail == "near" else None,
            )

    # -- selection (§2.1) and movement branches (§4.1) ------------------------------------

    def _select(self, scored: dict[_T, int], order: Callable[[_T], object], domain: str) -> _T:
        best = min(scored.values())
        tied = sorted((k for k, s in scored.items() if s == best), key=order)  # type: ignore[arg-type]
        if len(tied) == 1:
            return tied[0]
        text = f"{self.config.seed}|{self.request.actor_id}|{self.request.decision_ordinal}"
        digest = sha256(f"{text}|rule-v0:{domain}".encode()).digest()
        return tied[int.from_bytes(digest[:8], "big") % len(tied)]

    def _movement(self, goal: str, cands: dict[Pos, int], domain: str) -> list[_Item] | None:
        cands = {
            pos: score
            for pos, score in cands.items()
            if pos != self.own and not self._blocked([_item_move(pos)])
        }
        if not cands:
            return None
        return [_item_move(self._choose_target(goal, cands, domain))]

    def _choose_target(self, goal: str, cands: dict[Pos, int], domain: str) -> Pos:
        c = self.commit
        if c is not None and c.goal == goal and c.target in cands:
            return c.target
        target = self._select(cands, _yx, domain)
        self.commit = _Commit(goal, target, self.tick)
        return target

    def _stands(self, targets: set[Pos]) -> dict[Pos, int]:
        """Reachable passable tiles at Manhattan distance exactly 1 from a target tile."""
        return {
            pos: d
            for pos, d in self.dist.items()
            if pos in self._geometry()[1] and any(n in targets for n in self._neighbors(pos))
        }

    def _frontier(self) -> dict[Pos, int]:
        cfg = self.config
        out: dict[Pos, int] = {}
        for pos, d in self.dist.items():
            for n in self._neighbors(pos):
                if (
                    0 <= n[0] < cfg.map_width
                    and 0 <= n[1] < cfg.map_height
                    and n not in self.explored
                ):
                    out[n] = min(out.get(n, d + 1), d + 1)
        return out

    def _explore(self, domain: str) -> list[_Item] | None:
        cands = {
            pos: score
            for pos, score in self._frontier().items()
            if pos != self.own and not self._blocked([_item_move(pos)])
        }
        if (
            self.cue_enabled
            and self.cue is not None
            and not any(t == "spring" for t in self.explored.values())
        ):
            cue = self.cue
            if cue.detail_level == "near" and cue.direction in _DIRECTIONS:
                cx, cy = cue.position.x, cue.position.y
                tests: dict[str, Callable[[Pos], bool]] = {
                    "east": lambda q: q[0] > cx,
                    "west": lambda q: q[0] < cx,
                    "north": lambda q: q[1] < cy,
                    "south": lambda q: q[1] > cy,
                }
                keep = {q: s for q, s in cands.items() if tests[cue.direction](q)}
                if keep:
                    cands = keep
        if not cands:
            return None
        return [_item_move(self._choose_target("explore", cands, domain))]

    # -- helpers --------------------------------------------------------------------------

    def _at_spring(self) -> bool:
        return any(
            t.terrain == "spring" and _manhattan((t.position.x, t.position.y), self.own) == 1
            for t in self.p.visible_tiles
        )

    def _neighbor_residents(self) -> list[VisibleEntity]:
        return [
            e
            for e in self.p.visible_entities
            if e.entity_type == "resident"
            and _manhattan((e.position.x, e.position.y), self.own) == 1
        ]

    # -- rules ----------------------------------------------------------------------------

    def _r1(self) -> list[_Item] | None:
        p = self.p
        requests = sorted(
            (
                u
                for u in p.heard_utterances
                if u.speech_act == "request" and u.addressee_id == self.request.actor_id
            ),
            key=lambda u: u.utterance_id,
        )
        if not requests:
            return None
        u = requests[0]
        x = u.speaker_id
        inv, cond = p.own_inventory, p.own_condition
        accept: list[_Item] | None = None
        if self.config.max_plan_actions >= 2 and any(
            e.entity_id == x for e in self._neighbor_residents()
        ):
            talk = _item_talk(x, "accept", in_reply_to=u.utterance_id)
            if u.request_item_type == "canteen":
                if (
                    self.enabled
                    and inv.canteen_id is not None
                    and _at_least(cond.hydration, "moderate")
                ):
                    accept = [talk, _item_give(x, "canteen", 1)]
            elif u.request_item_type == "fruit" and u.request_quantity is not None:
                q = u.request_quantity
                if inv.fruit_count - q >= 1 and _at_least(cond.satiety, "moderate"):
                    accept = [talk, _item_give(x, "fruit", q)]
        if accept is not None and not self._blocked(accept):
            return accept
        refuse = [_item_talk(x, "refuse", in_reply_to=u.utterance_id)]
        if self._blocked(refuse):
            return None
        return refuse

    def _r2(self) -> list[_Item] | None:
        inv = self.p.own_inventory
        if (
            _at_most(self.p.own_condition.hydration, "low")
            and inv.canteen_id is not None
            and inv.canteen_servings is not None
            and inv.canteen_servings > 0
            and self.enabled
            and not self._at_spring()
        ):
            return [_item_drink("canteen")]
        return None

    def _r3(self) -> list[_Item] | None:
        if self._at_spring() and _at_most(self.p.own_condition.hydration, "moderate"):
            return [_item_drink("spring")]
        return None

    def _r4(self) -> list[_Item] | None:
        inv = self.p.own_inventory
        if not (self._at_spring() and inv.canteen_id is not None and self.enabled):
            return None
        servings = inv.canteen_servings
        if self.capacity is not None and servings is not None and servings >= self.capacity:
            return None
        fill = [_item_fill(inv.canteen_id)]
        return None if self._blocked(fill) else fill

    def _r5(self) -> list[_Item] | None:
        if self.p.own_inventory.fruit_count > 0 and _at_most(
            self.p.own_condition.satiety, "moderate"
        ):
            return [_simple("eat")]
        return None

    def _r6(self) -> list[_Item] | None:
        if not _at_most(self.p.own_condition.hydration, "low"):
            return None
        springs = {pos for pos, name in self.explored.items() if name == "spring"}
        plan = self._movement("water", self._stands(springs), "water")
        if plan is not None:
            return plan
        if (
            self.p.own_condition.hydration == "critical"
            and self.enabled
            and (self.p.own_inventory.canteen_id is None)
        ):
            cands: dict[str, int] = {}
            for e in self._neighbor_residents():
                request = _item_talk(
                    e.entity_id, "request", request=ItemRequest(item_type="canteen", quantity=1)
                )
                if not self._blocked([request]):
                    cands[e.entity_id] = 0
            if cands:
                rid = self._select(cands, lambda s: s, "request")
                self._write_local("request", resident_key(rid), "REQUESTED")
                return [
                    _item_talk(rid, "request", request=ItemRequest(item_type="canteen", quantity=1))
                ]
        return self._explore("water")

    def _r7(self) -> list[_Item] | None:
        if _at_most(self.p.own_condition.stamina, "low"):
            return [_simple("sleep")]
        return None

    def _r8(self) -> list[_Item] | None:
        inv = self.p.own_inventory
        if inv.fruit_count >= self.params.fruit_carry_target or self._failed("gather", SELF):
            return None
        near: dict[Pos, int] = {}
        entity: dict[Pos, str] = {}
        for tree in self._current_trees():
            pos = (tree.position.x, tree.position.y)
            if _manhattan(pos, self.own) != 1 or tree.fruit_band not in ("few", "many"):
                continue
            if self._blocked([_item_gather(tree.entity_id, pos)]):
                continue
            near[pos] = 0 if tree.fruit_band == "many" else 1
            entity[pos] = tree.entity_id
        if near:
            pos = self._select(near, _yx, "gather")
            tree_band_few = near[pos] == 1
            k = (
                1
                if tree_band_few
                else min(
                    self.params.fruit_carry_target - inv.fruit_count, self.config.max_plan_actions
                )
            )
            return [_item_gather(entity[pos], pos) for _ in range(k)]
        trees = {
            pos
            for pos, name in self.explored.items()
            if name == "fruit_tree" and not self._failed("gather", tile_key(*pos))
        }
        return self._movement("tree", self._stands(trees), "tree")

    def _r9(self) -> list[_Item] | None:
        inv = self.p.own_inventory
        if not self.enabled or inv.canteen_id is not None or self._failed("pick_up", SELF):
            return None
        for e in self.p.visible_entities:
            if e.entity_type != "canteen":
                continue
            pos = (e.position.x, e.position.y)
            if self._failed("pick_up", tile_key(*pos)):
                continue
            if _manhattan(pos, self.own) <= 1:
                return [_item_pick_up(pos)]
            if pos in self.dist and pos in self._geometry()[1]:
                return self._movement("canteen", {pos: self.dist[pos]}, "canteen")
            return None
        return None

    def _r10(self) -> list[_Item] | None:
        inv = self.p.own_inventory
        if not (
            self.enabled
            and inv.canteen_id is not None
            and inv.canteen_servings is not None
            and inv.canteen_servings > 0
            and _at_least(self.p.own_condition.hydration, "good")
        ):
            return None
        cands = {
            e.entity_id: 0
            for e in self._neighbor_residents()
            if "dehydrated" in e.observable_signs
            and not self._blocked([_item_give(e.entity_id, "canteen", 1)])
        }
        if not cands:
            return None
        return [_item_give(self._select(cands, lambda s: s, "deliver"), "canteen", 1)]

    def _r11(self) -> list[_Item] | None:
        return self._explore("explore")

    def _r12(self) -> list[_Item]:
        return [_simple("rest" if _at_most(self.p.own_condition.stamina, "good") else "wait")]

    def run(self) -> tuple[list[_Item], RuleStateV0_1]:
        self._r0()
        rules: list[Callable[[], list[_Item] | None]] = [
            self._r1, self._r2, self._r3, self._r4, self._r5, self._r6,
            self._r7, self._r8, self._r9, self._r10, self._r11,
        ]  # fmt: skip
        items: list[_Item] | None = None
        for rule in rules:
            items = rule()
            if items is not None:
                break
        if items is None:
            items = self._r12()
        return items, self._next_state(items)

    def _next_state(self, items: list[_Item]) -> RuleStateV0_1:
        plan_id = f"{self.request.actor_id}:p{self.request.decision_ordinal:06d}"
        refs = [
            IssuedIntent(
                intent_id=f"{plan_id}:i{i}", action_type=item.action, target=item.ref_target
            )
            for i, item in enumerate(items)
        ]
        failed = sorted(
            (
                FailedTarget(
                    action=cast(ActionType, action),
                    target=target_of_key(key),
                    code=code,
                    retry_after_tick=retry,
                )
                for (action, key), (code, retry) in self.entries.items()
            ),
            key=lambda f: f.sort_key(),
        )
        commitment = (
            RuleCommitment(
                goal=cast(Goal, self.commit.goal),
                target=ProtoCoord(x=self.commit.target[0], y=self.commit.target[1]),
                set_at_tick=self.commit.set_at_tick,
            )
            if self.commit is not None
            else None
        )
        return RuleStateV0_1(
            rule_state_version="0.1",
            commitment=commitment,
            issued_intents=refs,
            failed_targets=failed,
            cue_impressions=[self.cue] if self.cue is not None else [],
            canteen_capacity=self.capacity,
        )


class RuleBasedPolicy:
    policy_id = "rule-based-v0"

    def __init__(self, config: PolicyConfig, state: RuleStateV0_1 | None = None) -> None:
        if config.rule_params is None:
            raise ValueError("rule-based-v0 requires rule_params")
        self._config = config
        self._state = (
            state
            if state is not None
            else RuleStateV0_1(
                rule_state_version="0.1",
                commitment=None,
                issued_intents=[],
                failed_targets=[],
                cue_impressions=[],
                canteen_capacity=None,
            )
        )
        self._pending: RuleStateV0_1 | None = None

    def decide(self, request: DecisionRequest) -> OkOutcome:
        if self._pending is not None:
            raise ValueError("rule policy decision still awaiting commitment")
        items, next_state = _Decision(self._config, request, self._state).run()
        plan = make_plan(request, [item.template for item in items])
        self._pending = next_state
        return OkOutcome(status="ok", policy_id=self.policy_id, plan=plan)

    def finish_decision(self, accepted: bool) -> None:
        if accepted:
            if self._pending is None:
                raise ValueError("rule policy has no pending state to commit")
            self._state = self._pending
        self._pending = None

    def export_state(self) -> dict[str, Any]:
        if self._pending is not None:
            raise ValueError("cannot save an uncommitted rule policy decision")
        return self._state.model_dump(mode="json")
