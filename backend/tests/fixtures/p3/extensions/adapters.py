"""Two closed-tape fake adapters for the VF-20 provider port."""

from __future__ import annotations

from scripts.p3_trials import FakeTape, TapeProvider


class FixtureAdapterA(TapeProvider):
    def __init__(self, tape: FakeTape) -> None:
        if tape.fixture_id != "vf-20-adapter-a":
            raise ValueError("adapter A requires its committed tape identity")
        super().__init__(tape)


class FixtureAdapterB(TapeProvider):
    def __init__(self, tape: FakeTape) -> None:
        if tape.fixture_id != "vf-20-adapter-b":
            raise ValueError("adapter B requires its committed tape identity")
        super().__init__(tape)
