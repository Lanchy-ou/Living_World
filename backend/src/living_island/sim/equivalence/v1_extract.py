"""Extract projections from the frozen v1 coordinator and engine."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from pydantic import JsonValue

from living_island.agents.policies._plans import WAIT, make_plan
from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.runtime import Runtime
from living_island.agents.types import (
    DecisionRecord,
    DecisionRequest,
    IntentTemplate,
    IssuedIntent,
    OkOutcome,
    OwnProfile,
    PolicyConfig,
    ResidentRuntimeState,
    RuleParams,
    RuleStateV0_1,
    TargetKey,
)
from living_island.contract.save import AgentStateSection, DeliveryCursor, SavePackage
from living_island.sim.boundary import BoundaryLoop
from living_island.sim.runner import _runtime_roster
from living_island.world.content import EffectiveConfig, WorldContent
from living_island.world.engine import Engine
from living_island.world.facts import (
    ActionFailedPayload,
    ActionInterruptedPayload,
    ActionStartedPayload,
    ActionSucceededPayload,
    UtteranceSpokenPayload,
)
from living_island.world.ports import WorldTickCommit, create_engine
from living_island.world.protocol import (
    ActionIntent,
    ActionType,
    Coord,
    DeferredDecisionTriggers,
    EmptyParameters,
    EntityTarget,
    ResidentTarget,
    TalkParameters,
    TileTarget,
)
from living_island.world.state import (
    ActiveAction,
    DialogueSessionState,
    GroundFruitPile,
    WorldState,
)

from .projection import (
    Canteen,
    Corpse,
    Decision,
    Frame,
    GroundFruit,
    Intent,
    Outcome,
    Position,
    RequestTerms,
    Resident,
    Tree,
    Utterance,
    Values,
)


def _position(value: object) -> Position:
    return Position.model_validate(value, from_attributes=True)


class V1Extractor:
    """Join terminal events to their starts and actual v1 decisions."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self._starts: dict[str, int] = {}

    def append(
        self, commit: WorldTickCommit, decisions: list[DecisionRecord] | None = None
    ) -> None:
        world = commit.snapshot
        canteen = world.unique_canteen
        utterances: list[Utterance] = []
        outcomes: list[Outcome] = []
        for active in world.active_actions:
            self._starts[active.intent.intent_id] = active.tick_started
        for event in commit.events:
            payload = event.payload
            if isinstance(payload, ActionStartedPayload):
                assert event.intent_id is not None
                # Events are allocated for the ending boundary of the interval.
                self._starts[event.intent_id] = event.tick - 1
            elif isinstance(payload, UtteranceSpokenPayload):
                assert event.actor_id is not None
                utterances.append(
                    Utterance(
                        tick=event.tick,
                        speaker=event.actor_id,
                        addressee=payload.addressee_id,
                        act=payload.speech_act,
                        text=payload.text,
                        request=(
                            RequestTerms.model_validate(payload.request, from_attributes=True)
                            if payload.request
                            else None
                        ),
                    )
                )
            elif isinstance(
                payload, (ActionSucceededPayload, ActionFailedPayload, ActionInterruptedPayload)
            ):
                assert event.actor_id is not None and event.intent_id is not None
                if isinstance(payload, ActionSucceededPayload):
                    status, code = "success", None
                elif isinstance(payload, ActionFailedPayload):
                    status, code = "failure", payload.failure_code
                else:
                    status, code = "interrupted", payload.reason
                outcomes.append(
                    Outcome.model_validate(
                        dict(
                            actor_id=event.actor_id,
                            intent_id=event.intent_id,
                            tick_started=self._starts.pop(event.intent_id),
                            tick_finished=event.tick,
                            status=status,
                            code=code,
                        )
                    )
                )
        self.frames.append(
            Frame(
                tick=world.tick,
                residents=[
                    Resident(
                        id=r.id,
                        position=_position(r.position),
                        alive=r.alive,
                        satiety=r.satiety,
                        hydration=r.hydration,
                        stamina=r.stamina,
                        health=r.health,
                        fruit_count=r.fruit_count,
                        canteen_id=canteen.id if r.id == canteen.holder_id else None,
                        canteen_servings=canteen.servings if r.id == canteen.holder_id else None,
                    )
                    for r in world.residents
                ],
                trees=[Tree(id=t.id, stock=t.stock) for t in world.fruit_nodes],
                ground_fruit=[
                    GroundFruit(position=_position(p.position), quantity=p.quantity)
                    for p in world.ground_fruit
                ],
                canteen=Canteen(
                    id=canteen.id,
                    holder_id=canteen.holder_id,
                    ground_position=(
                        _position(canteen.ground_position) if canteen.ground_position else None
                    ),
                    servings=canteen.servings,
                ),
                corpses=[Corpse.model_validate(c.model_dump()) for c in world.corpses],
                utterances=utterances,
                outcomes=outcomes,
                decisions=decision_projection(decisions or []),
            )
        )

    def finish(self) -> list[Frame]:
        next_tick: dict[str, int] = {}
        for frame in reversed(self.frames):
            for decision in frame.decisions:
                next_tick[decision.actor_id] = frame.tick
            for outcome in frame.outcomes:
                outcome.next_decision_tick = next_tick.get(outcome.actor_id)
        return self.frames


def decision_projection(records: list[DecisionRecord]) -> list[Decision]:
    return [
        Decision(
            actor_id=record.actor_id,
            triggers=list(record.triggers),
            intents=[
                Intent(
                    action_type=intent.action_type,
                    target=intent.target.model_dump(mode="json") if intent.target else None,
                    parameters=intent.parameters.model_dump(mode="json"),
                )
                for intent in record.plan.intents
            ],
        )
        for record in records
    ]


def run_matrix_case(content: WorldContent, ticks: int, params: RuleParams) -> list[Frame]:
    loop = BoundaryLoop(
        create_engine(content, None),
        _runtime_roster(content, "rule-based-v0", None, None, rule_params=params),
    )
    extractor = V1Extractor()
    commit = loop.boundary
    for _ in range(ticks):
        following, decisions = loop.advance()
        extractor.append(commit, decisions)
        commit = following
    extractor.append(commit)
    return extractor.finish()


# Scripted fixture driver. Setup seeds a boundary state under an admitted
# config. The v1 engine and coordinator own all subsequent transitions.


@dataclass(frozen=True)
class ScriptCase:
    name: str
    plans: Mapping[tuple[str, int], tuple[IntentTemplate, ...]]
    ticks: int = 2
    config: str = "mechanics"
    seed: int = 20261108
    setup: Callable[[WorldState, EffectiveConfig], None] | None = None
    observed: str = "ella"
    start: int = 0
    restore_after: int | None = None
    reset_footprint: bool = False

    def run(self, content: WorldContent) -> tuple[list[Frame], list[Values]]:
        engine = Engine(content, None, ())
        if self.setup:
            self.setup(engine._state, content.config)
        if self.start:
            opening = engine.initial_commit()
            history = list(opening.events)
            state = opening.snapshot
            state.tick = self.start - 1
            state.next_event_seq_in_tick = 0
            if self.reset_footprint:
                for footprint in state.explored_tiles_by_resident:
                    footprint.tile_indices = []
            engine = Engine(content, state, history)
            engine.begin_tick()
            initial = engine.advance_tick()
            history.extend(initial.events)
            saved = bootstrap_save(initial, content)
            loop = BoundaryLoop(engine, self.runtimes(content, saved), saved)
        else:
            loop = BoundaryLoop(engine, self.runtimes(content, None))
            initial = loop.boundary
            history = list(initial.events)
        extractor = V1Extractor()
        evidence: list[Values] = []
        commit = initial
        for _ in range(self.ticks + 1):
            saved = loop.checkpoint()
            if commit.snapshot.tick == self.restore_after:
                restored = SavePackage.model_validate_json(saved.model_dump_json())
                loop = BoundaryLoop(
                    create_engine(content, restored.world, history),
                    self.runtimes(content, restored),
                    restored,
                )
            following, decisions = loop.advance()
            extractor.append(commit, decisions)
            evidence.append(
                {
                    "tick": commit.snapshot.tick,
                    "restored": commit.snapshot.tick == self.restore_after,
                    "deliveries": [
                        packet.model_dump(mode="json") for packet in commit.pending_deliveries
                    ],
                    "active_actions": [
                        a.model_dump(mode="json") for a in saved.world.active_actions
                    ],
                    "queued_plans": [
                        plan.model_dump(mode="json") for plan in saved.agent_state.queued_plans
                    ],
                    "deferred": [
                        entry.model_dump(mode="json")
                        for entry in saved.agent_state.deferred_decision_triggers
                    ],
                    "receipts": [
                        entry.model_dump(mode="json")
                        for entry in saved.world.exposure_receipts_by_resident
                    ],
                    "explored": [
                        entry.model_dump(mode="json")
                        for entry in saved.world.explored_tiles_by_resident
                    ],
                    "policy_states": {
                        state.actor_id: state.policy_state
                        for state in saved.agent_state.runtime_states
                    },
                    "rng": saved.world.resolution_rng_state_uint32,
                    "events": [event.model_dump(mode="json") for event in commit.events],
                    "decision_records": [record.model_dump(mode="json") for record in decisions],
                }
            )
            history.extend(following.events)
            commit = following
        return extractor.finish(), evidence

    def runtimes(self, content: WorldContent, saved: SavePackage | None) -> list[Runtime]:
        cfg = content.config
        overrides = {(actor, tick + self.start): plan for (actor, tick), plan in self.plans.items()}
        policy_config = script_policy_config(cfg)
        states = {r.actor_id: r for r in saved.agent_state.runtime_states} if saved else {}
        result = []
        for actor in cfg.residents:
            restored = states.get(actor.id)
            policy_state = RuleStateV0_1.model_validate(restored.policy_state) if restored else None
            policy = FixturePolicy(policy_config, policy_state, overrides, self.observed)
            result.append(
                Runtime(
                    actor.id,
                    policy_config,
                    OwnProfile(profile_id=actor.profile_id, initial_goal=actor.initial_goal),
                    policy,
                    restored,
                )
            )
        return result


class FixturePolicy(RuleBasedPolicy):
    """Supply scripted plans while keeping v1 feedback and subsequent policy decisions."""

    def __init__(
        self,
        config: PolicyConfig,
        state: RuleStateV0_1 | None,
        overrides: dict[tuple[str, int], tuple[IntentTemplate, ...]],
        observed: str,
    ):
        super().__init__(config, state)
        self._overrides = overrides
        self._observed = observed

    def decide(self, request: DecisionRequest) -> OkOutcome:
        decision = super().decide(request)
        scripted = self._overrides.get((request.actor_id, request.tick))
        if scripted is None:
            if request.actor_id == self._observed:
                return decision
            scripted = (WAIT,)
        plans = []
        for template in scripted:
            params = template.parameters
            if isinstance(params, TalkParameters) and params.in_reply_to == "fixture-heard-request":
                heard = next(
                    utterance
                    for utterance in request.context.perception.heard_utterances
                    if utterance.speech_act == "request"
                    and utterance.addressee_id == request.actor_id
                )
                template = template.model_copy(
                    update={
                        "parameters": params.model_copy(update={"in_reply_to": heard.utterance_id})
                    }
                )
            plans.append(template)
        plan = make_plan(request, plans)
        assert self._pending is not None
        refs = []
        for intent in plan.intents:
            target: TargetKey | None = intent.target
            if intent.action_type == "gather":
                node = next(
                    (
                        entity
                        for entity in request.context.perception.visible_entities
                        if isinstance(target, EntityTarget) and entity.entity_id == target.id
                    ),
                    None,
                )
                target = TileTarget(kind="tile", position=node.position) if node else None
            refs.append(
                IssuedIntent(
                    intent_id=intent.intent_id, action_type=intent.action_type, target=target
                )
            )
        self._pending = self._pending.model_copy(update={"issued_intents": refs})
        return decision.model_copy(update={"plan": plan})


def script_policy_config(cfg: EffectiveConfig) -> PolicyConfig:
    return PolicyConfig(
        policy_id="rule-based-v0",
        seed=cfg.meta.seed,
        max_plan_actions=cfg.agents.max_plan_actions,
        map_width=cfg.map.width,
        map_height=cfg.map.height,
        script_sha256=None,
        source_trace_sha256=None,
        rule_params=RuleParams(
            rule_params_version="0.1",
            canteen_use="enabled",
            cue_use="enabled",
            fruit_carry_target=2,
            failed_target_retry_ticks=36,
        ),
    )


def bootstrap_save(commit: WorldTickCommit, content: WorldContent) -> SavePackage:
    """Seed a late clock boundary for daylight and regrowth cases."""
    cfg = content.config
    policy_config = script_policy_config(cfg)
    actors = sorted(actor.id for actor in cfg.residents)
    tick = commit.snapshot.tick
    return SavePackage(
        save_schema_version="0.1",
        world=commit.snapshot,
        agent_state=AgentStateSection(
            profiles=[],
            goal_states=[],
            personal_memories=[],
            relationships=[],
            queued_plans=[],
            deferred_decision_triggers=[
                DeferredDecisionTriggers(actor_id=actor, reasons=["PLAN_FINISHED"])
                for actor in actors
            ],
            delivered_perception_ticks=[
                DeliveryCursor(actor_id=actor, last_observed_tick=tick - 1) for actor in actors
            ],
            runtime_states=[
                ResidentRuntimeState(
                    actor_id=actor,
                    policy_config=policy_config,
                    next_decision_ordinal=0,
                    policy_state=RuleBasedPolicy(policy_config).export_state(),
                    latest_perception_tick=tick - 1,
                )
                for actor in actors
            ],
        ),
        event_cursor=commit.snapshot.event_log_cursor,
        llm_record_cursor=0,
        decision_record_cursor=0,
        pending_perception_deliveries=commit.pending_deliveries,
        canonical_config_hash=content.config_hash,
        canonical_map_hash=content.map_hash,
    )


def coordinate(xy: tuple[int, int]) -> Coord:
    return Coord(x=xy[0], y=xy[1])


def target(kind: str, id_or_position: str | tuple[int, int]) -> Values:
    if isinstance(id_or_position, str):
        return {"kind": kind, "id": id_or_position}
    return {"kind": "tile", "position": {"x": id_or_position[0], "y": id_or_position[1]}}


def action(
    kind: ActionType, towards: Values | None = None, **parameters: JsonValue
) -> IntentTemplate:
    return IntentTemplate.model_validate(
        {"action_type": kind, "target": towards, "parameters": parameters, "reason": None}
    )


def move(x: int, y: int) -> IntentTemplate:
    return action("move_to", target("tile", (x, y)))


def give(actor: str, kind: str = "fruit", quantity: int = 1) -> IntentTemplate:
    return action("give", target("resident", actor), item_type=kind, quantity=quantity)


def talk(actor: str, act: str = "statement", **parameters: JsonValue) -> IntentTemplate:
    return action("talk", target("resident", actor), speech_act=act, text="Fruit?", **parameters)


def seeded(
    *,
    positions: dict[str, tuple[int, int]] | None = None,
    needs: dict[str, dict[str, int]] | None = None,
    fruit: dict[str, int] | None = None,
    stock: tuple[int, ...] = (),
    ground: tuple[tuple[int, int, int], ...] = (),
    servings: int | None = None,
    holder: str = "ryan",
    turns: int = 0,
    known_route: bool = False,
) -> Callable[[WorldState, EffectiveConfig], None]:
    def apply(world: WorldState, config: EffectiveConfig) -> None:
        for actor in world.residents:
            values = (needs or {}).get(actor.id, {})
            actor.satiety = values.get("satiety", 7500)
            actor.hydration = values.get("hydration", 8000)
            actor.stamina = values.get("stamina", 8500)
            actor.health = values.get("health", 10000)
            actor.fruit_count = (fruit or {}).get(actor.id, 0)
            if positions and actor.id in positions:
                actor.position = coordinate(positions[actor.id])
        for index, count in enumerate(stock):
            world.fruit_nodes[index].stock = count
        world.ground_fruit = [
            GroundFruitPile(position=Coord(x=x, y=y), quantity=count) for x, y, count in ground
        ]
        world.unique_canteen.holder_id = holder
        if servings is not None:
            world.unique_canteen.servings = servings
        if turns:
            world.dialogue_sessions = [
                DialogueSessionState(
                    pair_ids=["ella", "ryan"],
                    turn_count=turns,
                    last_utterance_tick=0,
                    cooldown_until_tick=0,
                )
            ]
        if known_route:
            # A prior visit along the small mechanics map's open east-west route.

            world.explored_tiles_by_resident[0].tile_indices = list(
                range(config.map.width * config.map.height)
            )

    return apply


ADJACENT = {"ella": (2, 3), "ryan": (3, 3)}
ROUTE = {"ella": (1, 4), "ryan": (8, 4), "mia": (2, 4)}
TREE = target("entity", "fruit_01")
CANTEEN = target("entity", "canteen_01")


def urgent_cases(config: EffectiveConfig) -> Iterable[ScriptCase]:
    for need, cutoff in (
        ("satiety", config.agents.urgent_satiety_below),
        ("hydration", config.agents.urgent_hydration_below),
        ("stamina", config.agents.urgent_stamina_below),
    ):
        for asleep in (False, True):
            action_type: ActionType = (
                "sleep" if asleep else ("wait" if need == "stamina" else "rest")
            )
            state = "asleep" if asleep else "awake"
            suffix = "control" if need == "stamina" and asleep else "crossing"
            yield ScriptCase(
                f"wap23-{need}-{state}-{suffix}",
                {("ella", 0): (action(action_type), WAIT)},
                setup=seeded(positions=ADJACENT, needs={"ella": {need: cutoff + 1}}),
            )
    yield ScriptCase(
        "wap23-priority-urgent-speech-sight",
        {("ella", 0): (move(10, 4), WAIT), ("ryan", 0): (talk("ella"),)},
        setup=seeded(
            positions={**ROUTE, "mia": (10, 4)},
            needs={"ella": {"satiety": 3001}},
        ),
    )


def speech_cases(content: WorldContent) -> Iterable[ScriptCase]:

    request = talk("ryan", "request", request={"item_type": "fruit", "quantity": 1})
    for name in ("first-reply", "dialogue-limit", "out-of-hearing", "invalid-reply"):
        reply = talk(
            "ella",
            "accept",
            in_reply_to="absent-v1-request" if name == "invalid-reply" else "fixture-heard-request",
        )
        plans = {("ella", 0): (request,), ("ryan", 0): (WAIT,), ("ryan", 1): (reply, give("ella"))}
        if name == "out-of-hearing":
            plans = {
                ("ella", 0): (WAIT,),
                ("ryan", 0): (
                    talk("ella", "request", request={"item_type": "fruit", "quantity": 1}),
                ),
                ("ella", 1): (
                    reply.model_copy(update={"target": ResidentTarget(kind="resident", id="ryan")}),
                    give("ryan"),
                ),
                ("ryan", 1): (move(4, 3),),
            }
        yield ScriptCase(
            f"wap23-reply-{name}",
            plans,
            ticks=4,
            setup=seeded(
                positions=ADJACENT,
                fruit={"ella": 1, "ryan": 1},
                turns=content.config.social.max_dialogue_turns - 1
                if name == "dialogue-limit"
                else 0,
            ),
            observed="ella" if name == "out-of-hearing" else "ryan",
        )

    for who, mover in (("ella", "ryan"), ("ryan", "ella")):
        yield ScriptCase(
            f"wap29-{who}-speaker-enters-hearing",
            {(who, 0): (talk(mover), WAIT), (mover, 0): (move(3, 3),)},
            setup=seeded(positions={who: (2, 3), mover: (4, 3), "mia": (4, 2)}),
            observed=who,
        )
    yield ScriptCase(
        "wap29-leaves-before-emission",
        {("ella", 0): (talk("ryan"), WAIT), ("ryan", 0): (move(4, 3),)},
        setup=seeded(positions=ADJACENT),
    )
    yield ScriptCase(
        "wap29-in-hearing-at-both-checks",
        {("ella", 0): (talk("ryan"), WAIT)},
        setup=seeded(positions=ADJACENT),
    )
    yield ScriptCase(
        "wap23-wap29-two-talks-last-slot-with-wait",
        {("ella", 0): (talk("ryan"), WAIT), ("ryan", 0): (talk("ella"), WAIT)},
        setup=seeded(positions=ADJACENT, turns=content.config.social.max_dialogue_turns - 1),
    )


def transfer_cases() -> Iterable[ScriptCase]:
    long_give = {("ella", 0): (give("ryan"), WAIT), ("ryan", 0): (move(35, 32),)}
    distant = {"ella": (33, 32), "ryan": (34, 32), "mia": (33, 33)}
    for name, config, returns in (
        ("completion-away", "give-3", False),
        ("completion-returned", "give-3", True),
        ("one-tick-control", "production", False),
    ):
        plans = dict(long_give)
        if returns:
            plans[("ryan", 1)] = (move(34, 32),)
        yield ScriptCase(
            f"wap27-{name}",
            plans,
            ticks=4,
            config=config,
            setup=seeded(positions=distant, fruit={"ella": 1}),
        )
    for giver, recipient in (("ella", "ryan"), ("ryan", "ella")):
        yield ScriptCase(
            f"wap27-{recipient}-recipient-start-order",
            {(giver, 0): (give(recipient), WAIT), (recipient, 0): (move(34, 32),)},
            ticks=4,
            config="give-3",
            observed=giver,
            setup=seeded(
                positions={giver: (33, 32), recipient: (35, 32), "mia": (33, 33)},
                fruit={giver: 1},
            ),
        )
    for kind, quantity, count, positions, label in (
        ("fruit", 1, 1, {"ella": (2, 3), "ryan": (2, 3)}, "same-tile"),
        ("fruit", 2, 2, ADJACENT, "fruit-by-kind"),
        ("fruit", 2, 1, ADJACENT, "too-few-items"),
        ("canteen", 1, 0, ADJACENT, "canteen-by-kind"),
    ):
        yield ScriptCase(
            f"wap23-give-{label}",
            {("ella", 0): (give("ryan", kind, quantity), WAIT)},
            setup=seeded(positions=positions, fruit={"ella": count}, holder="ella"),
        )
    pick = action("pick_up", target("tile", (3, 3)), item_type="fruit", quantity=1)
    yield ScriptCase(
        "wap23-pickup-contested-last-fruit",
        {("ella", 0): (pick, WAIT), ("ryan", 0): (pick, WAIT)},
        setup=seeded(positions=ADJACENT, ground=((3, 3, 1),)),
    )


def physical_cases() -> Iterable[ScriptCase]:
    adjacent_tree = {"ella": (2, 2), "ryan": (3, 3), "mia": (5, 2)}
    gather = action("gather", TREE)
    for name, stock, stamina, fruit, contested in (
        ("empty-at-start", 0, 8500, 0, False),
        ("last-fruit-contested", 1, 8500, 0, True),
        ("no-stamina", 1, 0, 0, False),
        ("no-room", 1, 8500, 10, False),
    ):
        plans = {("ella", 0): (gather, WAIT)}
        if contested:
            plans[("ryan", 0)] = (gather, WAIT)
        yield ScriptCase(
            f"wap23-gather-{name}",
            plans,
            ticks=3,
            setup=seeded(
                positions=adjacent_tree,
                stock=(stock,),
                fruit={"ella": fruit},
                needs={"ella": {"stamina": stamina}},
            ),
        )
    for name, xy in (("unknown", (1, 4)), ("known-adjacent", (9, 1))):
        yield ScriptCase(
            f"wap28-spring-{name}",
            {("ella", 0): (action("drink", source="spring"), WAIT)},
            setup=seeded(positions={"ella": xy}, needs={"ella": {"hydration": 5500}}),
        )
    yield ScriptCase(
        "wap23-fill-target-tree",
        {("ella", 0): (action("fill_canteen", TREE), WAIT)},
        setup=seeded(positions={"ella": (9, 1)}, holder="ella", servings=0),
    )
    yield ScriptCase(
        "wap23-fill-target-canteen",
        {("ella", 0): (action("fill_canteen", CANTEEN), WAIT)},
        setup=seeded(positions={"ella": (9, 1)}, holder="ella", servings=0),
    )
    for name, first in (("unfinished", action("sleep")), ("after-completion", WAIT)):
        yield ScriptCase(
            f"wap23-death-{name}",
            {("ella", 0): (first, WAIT)},
            setup=seeded(needs={"ella": {"hydration": 0, "health": 1}}),
        )
    yield ScriptCase(
        "wap30-interruption-long-successor",
        {("ella", 0): (move(10, 4), WAIT), ("ella", 1): (action("sleep"), WAIT)},
        ticks=4,
        setup=seeded(positions=ROUTE, needs={"ella": {"stamina": 2501}}),
    )
    for kind, first, positions in (
        ("move", move(10, 4), ROUTE),
        ("gather", gather, adjacent_tree),
    ):
        yield ScriptCase(
            f"wap23-wap33-en23-{kind}-exhaustion",
            {
                ("ella", 0): (first, WAIT),
                ("ella", 1): (action("rest"), WAIT),
                ("mia", 0): (action("sleep"),),
                ("ryan", 0): (WAIT,),
                ("ryan", 1): (WAIT,),
            },
            setup=seeded(positions=positions, needs={"ella": {"stamina": 1}}),
        )
    yield ScriptCase(
        "wap33-exhaustion-and-death",
        {("ella", 0): (move(10, 4), WAIT)},
        setup=seeded(
            positions=ROUTE,
            needs={"ella": {"stamina": 1, "hydration": 0, "health": 1}},
        ),
    )
    yield ScriptCase("wap33-path-blocked-then-death", {}, setup=seed_blocked)


def seed_blocked(world: WorldState, cfg: EffectiveConfig) -> None:
    seeded(needs={"ella": {"hydration": 0, "health": 1}})(world, cfg)
    world.active_actions = [
        ActiveAction(
            intent=ActionIntent(
                actor_id="ella",
                intent_id="fixture-blocked-route",
                plan_id="fixture",
                action_type="move_to",
                target=TileTarget(kind="tile", position=Coord(x=2, y=0)),
                parameters=EmptyParameters(),
                reason=None,
            ),
            tick_started=0,
            elapsed_ticks=0,
            remaining_ticks=None,
            route=[Coord(x=2, y=1), Coord(x=2, y=0)],
            route_cursor=1,
            pending_failure_code=None,
        )
    ]


def sleep_and_sight_cases() -> Iterable[ScriptCase]:
    for name, duration, hydration in (("natural", 48, 8000), ("early", 1, 3001)):
        yield ScriptCase(
            f"wap23-wap32-{name}-wake-no-speech",
            {("ella", 0): (action("sleep"), WAIT), ("ryan", duration - 1): (talk("ella"),)},
            ticks=duration + 1,
            setup=seeded(positions=ADJACENT, needs={"ella": {"hydration": hydration}}),
        )
    yield ScriptCase(
        "wap23-wap32-daylight-footprint",
        {("ella", 0): (action("sleep"), WAIT)},
        start=143,
        reset_footprint=True,
        ticks=2,
        config="production",
        setup=seeded(positions={"ella": (33, 32)}),
    )
    yield ScriptCase(
        "wap23-wap32-wap35-corpse-restore-before-wake",
        {("ella", 0): (action("sleep"), WAIT), ("ella", 3): (talk("mia"), give("mia"))},
        ticks=5,
        restore_after=1,
        setup=seeded(
            positions={**ADJACENT, "mia": (5, 3)},
            needs={"ella": {"hydration": 3201}, "ryan": {"hydration": 0, "health": 1}},
        ),
    )
    for kind in ("fruit", "canteen"):
        yield ScriptCase(
            f"wap35-first-held-{kind}-during-move",
            {("ella", 0): (move(10, 4), WAIT), ("ryan", 0): (give("ella", kind),)},
            ticks=4,
            setup=seeded(positions=ROUTE, fruit={"ryan": 1}, known_route=True),
        )
    yield ScriptCase(
        "wap35-near-cue-upgrade",
        {("ella", 0): (move(3, 2), WAIT)},
        setup=seeded(positions={"ella": (1, 2)}),
    )
    pick = action("pick_up", target("tile", (3, 3)), item_type="fruit", quantity=1)
    yield ScriptCase(
        "wap35-known-ground-fruit-quantity-reduced",
        {("ella", 0): (WAIT,), ("ryan", 0): (pick,)},
        setup=seeded(positions=ADJACENT, ground=((3, 3, 2),)),
    )
    yield ScriptCase(
        "wap35-ground-fruit-merged-on-death",
        {("ella", 0): (WAIT,), ("ryan", 0): (WAIT,)},
        setup=seeded(
            positions=ADJACENT,
            ground=((3, 3, 2),),
            fruit={"ryan": 1},
            holder="mia",
            needs={"ryan": {"hydration": 0, "health": 1}},
        ),
    )
    yield ScriptCase(
        "wap35-nested-water-no-novelty",
        {("ella", 0): (action("drink", source="canteen"),)},
        setup=seeded(positions=ADJACENT, holder="ella", servings=2),
    )


def config_cases() -> Iterable[ScriptCase]:
    yield ScriptCase(
        "wap23-ct15-refused-profiles",
        {("ella", 0): (WAIT,)},
        config="production",
    )
    for config in ("regrowth-2", "regrowth-0"):
        yield ScriptCase(
            f"ct15-ct17-{config}",
            {("ella", 0): (WAIT,), ("ella", 1): (WAIT,), ("ella", 23): (WAIT,)},
            ticks=25,
            start=143,
            config=config,
            setup=seeded(stock=(3, 4)),
            observed="",
        )
    yield ScriptCase(
        "ct17-one-tick-gather",
        {("ella", 0): (action("gather", TREE), WAIT)},
        config="gather-1",
        setup=seeded(positions={"ella": (16, 35)}, stock=(1,)),
    )
    for servings in (0, 1, 2):
        yield ScriptCase(
            f"ct17-canteen-{servings}-servings",
            {("ella", 0): (WAIT,)},
            config="production",
            setup=seeded(holder="ella", servings=servings),
        )


def scripted_projections(
    mechanics: WorldContent,
) -> Iterable[tuple[str, str, int, Callable[[WorldContent], tuple[list[Frame], list[Values]]]]]:
    for case in (
        *urgent_cases(mechanics.config),
        *speech_cases(mechanics),
        *transfer_cases(),
        *physical_cases(),
        *sleep_and_sight_cases(),
        *config_cases(),
    ):
        yield case.name, case.config, case.seed, case.run
