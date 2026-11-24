"""Explicit EV-05 evidence entry point. Default pytest never runs the long cases."""

import argparse
import socket
import subprocess
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter
from unittest.mock import patch

from living_island.agents.llm.provider import HTTPSByteTransport
from living_island.analysis.v2.export import fingerprint
from living_island.memory.v2.projections import ProjectedRevision
from living_island.sim.v2.harness.replay import History
from v2.fake_workload.display import Display
from v2.fake_workload.island import ROOT, Island
from v2.fake_workload.provider_check import stage
from v2.fake_workload.receipts import compare_days, finish_actor, save
from v2.fake_workload.script import WorkloadTransport
from v2.fake_workload.viewer import open_exports
from v2.resident_replay.replay_evidence import interruption_cases
from v2.resident_replay.replay_fixture import start, verify

HORIZONS = {"week": 1008, "ella": 432}
KINDS = {
    "morning",
    "decision",
    "recall",
    "decision_after_recall",
    "consolidation_selection",
    "consolidation_change_set",
}


@contextmanager
def disconnected():
    def denied(*args, **kwargs):
        raise AssertionError("The offline workload attempted network/provider access")

    with ExitStack() as stack:
        for obj, method in (
            (socket.socket, "connect"),
            (socket.socket, "connect_ex"),
            (socket, "getaddrinfo"),
            (HTTPSByteTransport, "exchange"),
        ):
            stack.enter_context(patch.object(obj, method, denied))
        yield


def terminal_cases(directory):
    record, kwargs, fake = start(directory / "floor")
    with patch.object(ProjectedRevision, "index_line", property(lambda _: "é" * 500000)):
        assert record.advance() is None
    (row,) = verify(directory / "floor", record, kwargs, boundaries=1)
    key = row.boundary.stop.stop.witness
    history = History(record.audit, record.audit.cursor())
    floor = history.request(key, ())
    assert floor.record.reason == "stopped_unfit" and not list(history.attempts(floor))
    assert fake.calls == ["decision"]
    death = directory / "death"
    record, kwargs, _ = start(death)
    record.advance()
    record.advance()
    record.save(death / "confirmed.json")
    return {
        "no_dispatch": {
            "prepared": key,
            "attempts": 0,
            "reason": floor.record.reason,
            "world_sha256": row.boundary.world_hash,
        },
        "death": interruption_cases(death, record, kwargs),
    }


def capture(directory, case, ticks):
    started = perf_counter()
    with disconnected():
        island = Island(directory, case, ticks)
        display = Display(island)
        save(
            directory / "run-manifest.json",
            {
                "case": case,
                "ticks": ticks,
                "memory": "on",
                "seed": island.setup.seed,
                "inputs": island.pins(),
                "forecast": {
                    "currency": "CNY",
                    "unit": "per million tokens",
                    "cache_hit_fraction": 0,
                    "uncached_input": 2,
                    "output": 8,
                    "price_source": "docs/tasks/p3/M9-evidence.md (2026-11-14 historical peak)",
                    "usage": "pinned input bound and scripted assistant text bound",
                    "reserve": "allowed output reserve for each observed dispatch",
                },
                "source_commit": subprocess.check_output(
                    ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
                    cwd=ROOT,
                    text=True,
                ).strip(),
            },
        )
        day_times = {}
        day_start = perf_counter()
        for i in range(1, ticks + 1):
            if island.advance() is None:
                raise RuntimeError(f"Stopped before tick {i}")
            if not all(island.world.state.residents[a].alive for a in island.fakes):
                raise RuntimeError(f"Model resident died at tick {i}")
            display.append()
            if i % 144 == 0 or i == ticks:
                day_times[1 + (i - 1) // 144] = perf_counter() - day_start
                day_start = perf_counter()
        display.save(directory / "replay.json")
        with patch.object(
            WorkloadTransport, "exchange", side_effect=AssertionError("model in replay")
        ):
            actors = {a: finish_actor(island, a, r, ticks) for a, r in island.recordings.items()}
        assert len({a["world_sha256"] for a in actors.values()}) == 1
        d7 = (
            stage(directory, island.recordings["ella"], actors["ella"]["single_copy_samples"])
            if case == "ella"
            else {}
        )
        return dict(
            case=case,
            ticks=ticks,
            run_manifest_sha256=fingerprint(directory / "run-manifest.json"),
            replay_sha256=fingerprint(directory / "replay.json"),
            actors=actors,
            terminal_counts=sum((row["terminal_counts"] for row in actors.values()), Counter()),
            recording_seconds_by_day=day_times,
            wall_seconds=perf_counter() - started,
            provider_check=d7,
            network_dispatches=0,
            paid_cny=0,
        )


def accept(report):
    ticks = HORIZONS[report["case"]]
    assert report["ticks"] == ticks
    for row in report["actors"].values():
        assert row["replayed_ticks"] == ticks
        assert set(row["days"]) == set(range(1, 1 + ticks // 144))
        assert set(row["single_copy_samples"]) == KINDS
        assert sum(d["positive_log_growth"] for d in row["days"].values()) > 0
        assert row["operations"]["committed"] and row["operations"]["dropped"]
        assert any(p["outcome"] == "committed" for p in row["periods"])
    ella = report["actors"]["ella"]
    failures = [p for p in ella["periods"] if p["outcome"] == "failed"]
    assert failures and failures[0]["period"] in failures[0]["pending_after"]
    assert any(
        p["outcome"] == "committed"
        and failures[0]["period"] not in p["pending_after"]
        and p["tick"] > failures[0]["tick"]
        for p in ella["periods"]
    )
    assert ella["terminal_counts"]["provider_error"] == 1
    assert set(ella["terminal_counts"]) == {
        "timeout",
        "rate_limit",
        "server_error",
        "provider_error",
        "invalid_output",
        "success",
    }
    if report["case"] == "week":
        assert len(report["actors"]) == 5
        forms = sum((Counter(r["forms"]) for r in report["actors"].values()), Counter())
        assert all(
            forms[k]
            for k in ("continue", "intent", "utterance", "set", "clear", "mute", "valid_citation")
        )
        noah = report["actors"]["noah"]
        assert noah["terminal_counts"]["provider_error"] == 1
        assert report["terminal_counts"]["provider_error"] == 2
        assert noah["fallback_turns"] and noah["model_handbacks"]
    else:
        assert report["terminal_counts"]["provider_error"] == 1
        assert set(report["provider_check"]) == KINDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("both", *HORIZONS), required=True)
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    cases = HORIZONS if args.case == "both" else (args.case,)
    with args.lock.open("x", encoding="utf-8") as lock:
        lock.write(f"P3.5-EV-05 {datetime.now(UTC).isoformat()}\n")
    try:
        root = ROOT / "runs"
        root.mkdir(exist_ok=True)
        session = Path(mkdtemp(prefix="ev05-", dir=root))
        print(session, flush=True)
        reports = {}
        for case in cases:
            directory = session / case
            directory.mkdir()
            report = capture(directory, case, HORIZONS[case])
            if case == "week":
                with disconnected():
                    report["terminal_vectors"] = terminal_cases(directory / "terminal")
            save(directory / "receipt.json", report)
            accept(report)
            report["analysis_mode_opened"] = open_exports(directory, report["actors"])
            save(directory / "receipt.json", report)
            print(f"{case} passed: {fingerprint(directory / 'receipt.json')}", flush=True)
            reports[case] = report
        if args.case == "both":
            save(session / "comparison.json", compare_days(reports["week"], reports["ella"]))
    finally:
        args.lock.unlink()


if __name__ == "__main__":
    main()
