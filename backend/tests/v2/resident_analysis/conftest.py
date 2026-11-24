import pytest

from living_island.analysis.v2.export import export
from living_island.analysis.v2.shards import InspectionArchive
from v2.inspection_export.conftest import capture as capture
from v2.inspection_export.conftest import fake_exchange as fake_exchange
from v2.inspection_export.conftest import formation as formation
from v2.inspection_export.conftest import packet as packet


@pytest.fixture(scope="module")
def short(capture, tmp_path_factory):
    out = tmp_path_factory.mktemp("short") / "inspection"
    export(*capture, out)
    return InspectionArchive.open(out)
