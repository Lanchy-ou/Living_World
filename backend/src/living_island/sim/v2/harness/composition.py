"""Start the M14 model resident alongside standalone rule-controlled companions."""

from collections.abc import Mapping
from pathlib import Path

from living_island.agents.types import OwnProfile, PolicyConfig
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.context.dialogue import DialogueState
from living_island.agents.v2.context.prefix import ResidentIdentity, VerbDescription
from living_island.agents.v2.decision.caller import Caller
from living_island.persistence.v2.journal import PacketJournal
from living_island.sim.v2.compat.bridge import LegacyBridge
from living_island.sim.v2.compat.config import BoundCompatPack
from living_island.sim.v2.compat.policy_host import PolicyCheckpoint, PolicyHost
from living_island.sim.v2.harness.consolidation.coordinator import K, PeriodCoordinator
from living_island.sim.v2.harness.loop import ResidentLoop
from living_island.sim.v2.harness.session import (
    ResidentContinuation,
    ResidentPolicyHost,
    ResidentSession,
)
from living_island.world.v2.engine import World


def compose(
    world: World,
    *,
    actor: str,
    identity: ResidentIdentity,
    profiles: Mapping[str, OwnProfile],
    config: PolicyConfig,
    sleep_ticks: int,
    caller: Caller,
    packets: PacketJournal,
    journal: Journal,
    memory_on: bool,
    compat: BoundCompatPack | None = None,
    stop_file: Path | None = None,
    restored: tuple[Mapping[str, PolicyCheckpoint], ResidentContinuation] | None = None,
) -> ResidentSession:
    pack = world.pack
    fatigue = pack.physiology.mental_fatigue
    if fatigue is not None and fatigue.faint_ticks < K:
        raise ValueError(f"faint_ticks {fatigue.faint_ticks} is shorter than K {K}")
    if pack.source.pack_id == "compat-v1" and compat is None:
        raise ValueError("compat-v1 requires the registered fallback bridge")
    bridge = LegacyBridge(compat) if compat else None
    policies = restored[0] if restored else {}
    model_host = ResidentPolicyHost(
        config,
        profiles[actor],
        sleep_ticks,
        bridge=bridge,
        restored=policies[actor] if restored else None,
    )
    companions = {
        key: PolicyHost(
            config,
            profile,
            sleep_ticks,
            bridge=bridge,
            restored=policies[key] if restored else None,
        )
        for key, profile in profiles.items()
        if key != actor
    }
    vocabulary = pack.source.vocabulary
    verbs = tuple(
        VerbDescription(spec.shape, vocabulary.verbs[key]["description"])
        for key, spec in pack.verbs.items()
    )
    phenomena = {key: row["text"] for key, row in vocabulary.phenomena.items()}
    gap = world.state.dialogue_limits.gap_ticks
    if restored is None:
        resident = ResidentLoop.start(
            resident_id=actor,
            identity=identity,
            verbs=verbs,
            journal=journal,
            memory_on=memory_on,
            gap_ticks=gap,
            phenomena=phenomena,
            caller=caller,
        )
        return ResidentSession(
            world, companions, packets, resident, model_host, stop_file=stop_file
        )
    state = restored[1]
    period = PeriodCoordinator.restore(state.period, journal, phenomena=phenomena)
    dialogue = DialogueState.restore(actor, gap, state.dialogue)
    resident = ResidentLoop(
        identity, verbs, period, dialogue, caller, muted=state.muted, awake_ticks=state.awake_ticks
    )
    session = ResidentSession(world, companions, packets, resident, model_host, stop_file=stop_file)
    session.intents, session.spoken, session.agreements = (
        dict(state.intents),
        state.spoken,
        state.agreements,
    )
    session.incomplete = state.incomplete
    return session
