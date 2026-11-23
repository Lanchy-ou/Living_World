"""Shared resident packet and fake provider fixtures for sleep boundaries."""

from v2.working_context.conftest import audit as audit
from v2.working_context.conftest import fake_exchange as fake_exchange
from v2.working_context.conftest import packet as packet


def journal(files):
    from living_island.agents.v2.calls.journal import Journal

    def keep(key, data):
        assert files.setdefault(key, data) == data

    def create(key, data):
        assert key not in files
        files[key] = data

    return Journal(keep, create)


def resident(journal, *, memory_on=True, store=None):
    from living_island.agents.v2.context.prefix import FrozenPrefix
    from living_island.memory.v2.store import MemoryStore
    from living_island.sim.v2.harness.consolidation import PeriodCoordinator

    return PeriodCoordinator(
        store or MemoryStore("ella"),
        journal,
        FrozenPrefix("p:ella:1", (), (), (), None),
        memory_on=memory_on,
    )


def sleeping(packet, tick=101, start=100, duration=36, **perception):
    from living_island.agents.v2.context.delivery import FilteredDelivery
    from living_island.world.v2.protocol import Intent

    turn = f"ella:t{start:06d}"
    intent = Intent(
        actor_id="ella",
        turn_id=turn,
        intent_id=turn + ":a",
        action="act",
        verb="sleep",
        target=None,
        instruments=[],
        inputs=[],
        params={"duration_ticks": duration},
        reason=None,
    )
    physical = packet(
        tick=tick,
        awareness="asleep",
        running_action=dict(
            intent_id=intent.intent_id,
            action="act",
            verb="sleep",
            tick_started=start,
            progress=None,
            start_target=None,
            items=[],
        ),
        **perception,
    )
    return FilteredDelivery(physical), {intent.intent_id: intent}
