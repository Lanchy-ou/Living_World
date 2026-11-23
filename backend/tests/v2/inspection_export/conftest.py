"""Short fake resident capture, plus a separately supplied fixture replay and seal."""

import pytest

from v2.inspection_export.short_capture import seal_capture
from v2.resident_replay.replay_fixture import start, verify
from v2.working_context.conftest import audit as audit
from v2.working_context.conftest import fake_exchange as fake_exchange
from v2.working_context.conftest import packet as packet


@pytest.fixture
def formation(tmp_path, packet, fake_exchange):
    from v2.inspection_export.formation_capture import capture_formation

    return capture_formation(tmp_path, packet, fake_exchange)


@pytest.fixture(scope="module")
def capture(tmp_path_factory):
    work = tmp_path_factory.mktemp("capture")
    source = work / "run"
    recording, kwargs, _ = start(source)
    assert recording.advance() is not None
    verify(source, recording, kwargs, boundaries=1)
    return seal_capture(work, source, recording, kwargs, "on")
