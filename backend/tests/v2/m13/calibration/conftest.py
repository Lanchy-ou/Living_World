"""Fixed short recordings shared by the calibration recovery and integrity checks."""

import pytest


@pytest.fixture(scope="module")
def recorded_mid_queue(tmp_path_factory):
    from living_island.sim.v2.scenarios.calibration.campaign import record_pair
    from living_island.sim.v2.scenarios.calibration.fixtures import calibration_cases
    from living_island.sim.v2.scenarios.calibration.recording import scenario
    from living_island.sim.v2.scenarios.runtime import run_or_resume

    base = tmp_path_factory.mktemp("ct05")
    inputs = base / "source"
    case = next(
        case for case in calibration_cases(inputs) if case.name == "wap23-reply-first-reply"
    )

    pair = record_pair(base, case, "ct05-test")
    direct = base / "direct"
    uninterrupted = run_or_resume(
        direct,
        pair.arms["visible"].inputs.plan,
        lambda: scenario(case.prepare(inputs), "visible", direct / "trace"),
    )
    return case, base, pair, uninterrupted.evidence
