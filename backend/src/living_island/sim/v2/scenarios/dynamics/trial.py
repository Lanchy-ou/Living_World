"""One independently resumable vector within a mapped starter demonstration."""

from dataclasses import dataclass

from ..runtime import Scenario
from .fixture import Opening, Schedule
from .observe import Witness


@dataclass(frozen=True)
class Trial:
    index: int
    demo: str
    name: str
    horizon: int
    scenario: Scenario

    def setup(self) -> Scenario:
        return self.scenario


def trial(
    index: int,
    demo: str,
    name: str,
    setup: Opening,
    horizon: int,
    script: Schedule,
    witness: Witness,
) -> Trial:
    return Trial(index, demo, name, horizon, setup.scenario(script, witness))
