import importlib

import pytest

SUBPACKAGES = [
    "living_island",
    "living_island.world",
    "living_island.world.protocol",
    "living_island.agents",
    "living_island.agents.rule_based",
    "living_island.agents.llm",
    "living_island.memory",
    "living_island.events",
    "living_island.events.narrative",
    "living_island.sim",
    "living_island.persistence",
    "living_island.contract",
]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_import(name: str) -> None:
    assert importlib.import_module(name) is not None
