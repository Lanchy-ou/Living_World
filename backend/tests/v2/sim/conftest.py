"""Use the shared validated engine-test pack without automatic acknowledgement."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_engine_fixtures = spec_from_file_location(
    "sim_engine_fixtures", Path(__file__).resolve().parents[1] / "engine" / "conftest.py"
)
assert _engine_fixtures is not None and _engine_fixtures.loader is not None
_engine = module_from_spec(_engine_fixtures)
_engine_fixtures.loader.exec_module(_engine)
pack = _engine.pack
setup = _engine.setup


@pytest.fixture
def real_world(pack, setup):
    from living_island.world.v2.engine import initialize

    return initialize(pack, setup)
