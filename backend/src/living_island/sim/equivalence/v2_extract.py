"""Project committed compatibility-engine boundaries into projection/0.1."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from living_island.agents.rule_based import RuleBasedPolicy
from living_island.agents.types import DecisionRecord, OwnProfile, PolicyConfig
from living_island.sim.v2.compat.adapters import legacy_speech
from living_island.sim.v2.compat.bridge import LegacyBridge
from living_island.sim.v2.compat.policy_host import (
    PolicyCheckpoint,
    PolicyFactory,
    PolicyHost,
    _Proposal,
)
from living_island.world import protocol as legacy
from living_island.world.v2 import protocol as v2
from living_island.world.v2.engine import TickResult, World
from living_island.world.v2.engine.items import entities_at, tile_of
from living_island.world.v2.engine.kernel import distance, exhausted, exposed
from living_island.world.v2.engine.state import Held, Inside, OnTile, WorldState
from living_island.world.v2.engine.validate import EnginePack

from .compare import utterance_key
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
)


def _position(point: v2.Coord) -> Position:
    return Position(x=point.x, y=point.y)


def _decision(record: DecisionRecord, speech_ids: dict[str, str]) -> Decision:
    intents: list[Intent] = []
    for intent in record.plan.intents:
        parameters = intent.parameters.model_dump(mode="json")
        if isinstance(intent.parameters, legacy.TalkParameters):
            reply = intent.parameters.in_reply_to
            if reply is not None and reply in speech_ids:
                parameters["in_reply_to"] = speech_ids[reply]
        intents.append(
            Intent(
                action_type=intent.action_type,
                target=intent.target.model_dump(mode="json") if intent.target else None,
                parameters=parameters,
            )
        )
    return Decision(
        actor_id=record.actor_id,
        triggers=list(record.triggers),
        intents=intents,
    )


def _outcome(result: legacy.ActionResult) -> Outcome:
    return Outcome(
        actor_id=result.actor_id,
        intent_id=result.intent_id,
        tick_started=result.tick_started,
        tick_finished=result.tick_finished,
        status=result.status,
        code=result.failure_code or result.interruption_reason,
    )


def _spoken(event: v2.WorldEvent) -> Utterance:
    payload = event.payload
    speech = v2.Utterance.model_construct(
        addressee_id=cast(str, payload["addressee_id"]),
        speech_act=cast(v2.SpeechAct, payload["speech_act"]),
        text=cast(str, payload["text"]),
        terms=(v2.Terms.model_validate(payload["terms"]) if payload["terms"] is not None else None),
        in_reply_to=cast(str | None, payload["in_reply_to"]),
    )
    speaker = cast(str, event.actor_id)
    act, item, quantity = legacy_speech(speaker, speech)
    terms = (
        RequestTerms(
            item_type=cast(Literal["fruit", "canteen"], item), quantity=cast(int, quantity)
        )
        if act == "request"
        else None
    )
    return Utterance(
        tick=event.tick,
        speaker=speaker,
        addressee=cast(str, speech.addressee_id),
        act=act,
        text=speech.text,
        request=terms,
    )


def snapshot(world: World, canteen_id: str) -> Frame:
    """Read physical state before the decisions at this boundary settle."""
    state = world.state
    canteen = state.entities[canteen_id]
    place = canteen.place
    held: Counter[str] = Counter()
    ground: Counter[tuple[int, int]] = Counter()
    trees: list[Tree] = []
    corpses: list[Corpse] = []
    servings = 0
    for item in state.entities.values():
        match item.archetype_id:
            case "fruit_tree":
                trees.append(Tree(id=item.entity_id, stock=item.components["store"]["count"]))
            case "fruit":
                if isinstance(item.place, Held):
                    held[item.place.holder_id] += item.quantity
                elif isinstance(item.place, OnTile):
                    ground[item.place.position.y, item.place.position.x] += item.quantity
            case "water":
                if item.place == Inside(canteen_id):
                    servings += item.quantity
        if item.corpse_resident_id is not None:
            corpses.append(
                Corpse(
                    id=item.entity_id,
                    resident_id=item.corpse_resident_id,
                    position=_position(cast(OnTile, item.place).position),
                    death_tick=cast(int, item.death_tick),
                )
            )
    holder = place.holder_id if isinstance(place, Held) else None
    return Frame(
        tick=state.tick,
        residents=[
            Resident(
                id=actor,
                position=_position(resident.position),
                alive=resident.alive,
                satiety=state.needs[actor]["satiety"],
                hydration=state.needs[actor]["hydration"],
                stamina=state.needs[actor]["stamina"],
                health=state.needs[actor]["health"],
                fruit_count=held[actor],
                canteen_id=canteen_id if actor == holder else None,
                canteen_servings=servings if actor == holder else None,
            )
            for actor, resident in sorted(state.residents.items())
        ],
        trees=sorted(trees, key=lambda item: item.id),
        ground_fruit=[
            GroundFruit(position=Position(x=x, y=y), quantity=count)
            for (y, x), count in sorted(ground.items())
        ],
        canteen=Canteen(
            id=canteen_id,
            holder_id=holder,
            ground_position=_position(cast(OnTile, place).position) if holder is None else None,
            servings=servings,
        ),
        corpses=sorted(corpses, key=lambda item: item.id),
        utterances=[],
        outcomes=[],
        decisions=[],
    )


EXCEPTION_NAMES = (
    "gather-exhausted-unreachable",
    "gather-exhausted-receipted-missing",
    "drink-full-without-canteen",
    "reply-after-accept",
    "reply-after-refuse",
)


@dataclass(frozen=True)
class DeclaredException:
    name: str
    tick: int
    actor_id: str


def declared_exceptions(
    opening: WorldState, pack: EnginePack, submissions: Sequence[v2.TurnSubmission]
) -> list[DeclaredException]:
    """Inspect actual submitted inputs against their opening state for WAP-26."""
    hits = []
    for submission in submissions:
        actor = submission.actor_id
        if isinstance(submission.action, v2.IntentAction):
            intent = submission.action.intent
            if intent.verb == "gather" and exhausted(opening, pack, actor):
                target = cast(v2.EntityTarget, intent.target)
                if exposed(opening, actor, target.id):
                    tree = opening.entities.get(target.id)
                    if tree is None:
                        hits.append(DeclaredException(EXCEPTION_NAMES[1], opening.tick, actor))
                    else:
                        verb = pack.verbs["gather"]
                        reach = distance(
                            opening.residents[actor].position, tile_of(opening, tree.place)
                        )
                        if not verb.min_reach <= reach <= verb.max_reach:
                            hits.append(DeclaredException(EXCEPTION_NAMES[0], opening.tick, actor))
            if (
                intent.verb == "drink"
                and intent.instruments
                and opening.needs[actor]["hydration"] == pack.needs["hydration"].maximum
                and all(
                    item.archetype_id != "canteen" for item in entities_at(opening, Held(actor))
                )
            ):
                hits.append(DeclaredException(EXCEPTION_NAMES[2], opening.tick, actor))
        speech = submission.utterance
        if speech is not None and speech.in_reply_to is not None:
            proposal = opening.proposals.get(speech.in_reply_to)
            if (
                proposal is not None
                and (proposal.speaker_id, proposal.addressee_id) == (speech.addressee_id, actor)
                and proposal.answer is not None
            ):
                hits.append(
                    DeclaredException(f"reply-after-{proposal.answer}", opening.tick, actor)
                )
    return hits


class V2Extractor:
    """Observe real committed intent bindings, speech and authoritative results."""

    def __init__(self, bridge: LegacyBridge) -> None:
        self.bridge = bridge
        self.frames: list[Frame] = []
        self._issued: dict[str, legacy.ActionIntent] = {}
        self._stops: dict[str, legacy.ActionResult] = {}
        self._decisions: list[DecisionRecord] = []
        self._speech_ids: dict[str, str] = {}

    def committed(self, proposal: _Proposal) -> None:
        if proposal.decision is not None:
            self._decisions.append(proposal.decision.trace.record)
        if proposal.intent is not None:
            choice = cast(v2.IntentAction, proposal.submission.action)
            self._issued[choice.intent.intent_id] = proposal.intent
        if proposal.legacy_stop is not None:
            self._stops[cast(str, proposal.replaces)] = proposal.legacy_stop

    def append(self, frame: Frame, result: TickResult) -> None:
        """Enter decisions and actor stops at the opening boundary, then close it."""
        opened = self.frames[-1]
        opened.decisions.extend(_decision(record, self._speech_ids) for record in self._decisions)
        self._decisions.clear()
        for action in result.actions:
            intent = self._issued.pop(action.intent_id)
            if isinstance(action.stop, v2.ActorStop):
                opened.outcomes.append(_outcome(self._stops.pop(action.intent_id)))
            else:
                translated = self.bridge.translate(
                    intent, action, result.utterances.get(action.actor_id)
                )
                if translated is None:
                    raise ValueError(f"no compatibility outcome for {action!r}")
                frame.outcomes.append(_outcome(translated))
        for event in result.events:
            if event.type == "utterance_spoken":
                utterance = _spoken(event)
                frame.utterances.append(utterance)
                self._speech_ids[event.event_id] = utterance_key(
                    utterance.tick, utterance.speaker, utterance.addressee
                )
        self.frames.append(frame)

    def finish(self) -> list[Frame]:
        next_tick: dict[str, int] = {}
        for frame in reversed(self.frames):
            for decision in frame.decisions:
                next_tick[decision.actor_id] = frame.tick
            for outcome in frame.outcomes:
                outcome.next_decision_tick = next_tick.get(outcome.actor_id)
        return self.frames


class ProjectionHost(PolicyHost):
    """Record the same proposals the compatibility coordinator commits."""

    def __init__(
        self,
        config: PolicyConfig,
        profile: OwnProfile,
        sleep_ticks: int,
        *,
        extractor: V2Extractor,
        restored: PolicyCheckpoint | None = None,
        policy_factory: PolicyFactory = RuleBasedPolicy,
    ) -> None:
        super().__init__(
            config,
            profile,
            sleep_ticks,
            bridge=extractor.bridge,
            restored=restored,
            policy_factory=policy_factory,
        )
        self._extractor = extractor

    def commit(self, proposal: _Proposal) -> None:
        super().commit(proposal)
        self._extractor.committed(proposal)
