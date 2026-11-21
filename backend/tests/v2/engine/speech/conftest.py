"""Synthetic speech audience and capture at the world delivery boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from living_island.world.v2.engine.tick import TickContext


@pytest.fixture
def audience(pack, setup, auto_acknowledge):
    from living_island.world.v2.engine import ResidentSetup, initialize
    from living_island.world.v2.engine.state import Exposure
    from living_island.world.v2.protocol import Coord

    setup = setup.model_copy(
        update={
            "residents": (*setup.residents, ResidentSetup(id="res_c", position=Coord(x=2, y=1)))
        }
    )
    world = initialize(pack, setup)
    state = world.state
    for actor_id, receipts in state.exposure_receipts_by_resident.items():
        receipts.entities.update(
            (resident.id, Exposure(resident.id, resident.position))
            for resident in state.residents.values()
            if resident.id != actor_id
        )
    return auto_acknowledge(world)


@pytest.fixture
def deliveries(monkeypatch) -> list[TickContext]:
    from living_island.world.v2.engine import perception

    boundaries: list[TickContext] = []
    build = perception.build_deliveries

    def capture(ctx):
        build(ctx)
        boundaries.append(ctx)

    monkeypatch.setattr(perception, "build_deliveries", capture)
    return boundaries
