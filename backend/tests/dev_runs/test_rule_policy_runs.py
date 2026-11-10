"""P2-02 long checks, outside the default suite (OQ-053). Run them explicitly:

    P2_RULE_RUNS=1 P2_RUNS_OUT=<scratch dir> uv run pytest tests/dev_runs -s -p no:cacheprovider

- ``test_s1_twenty_development_seeds``: S1 pass line, p2-experiments §4 B03 (20 seeds, tick 1008,
  all residents alive, zero substituted records). Records exit code, final tick, alive flags,
  substituted count and wall time per seed, plus the total wall time.
- ``test_s2_no_repeat_on_development_seeds``: the decision-record no-repeat check over S2/base.
- ``test_rule_run_resume_and_reexecute``: default island resume and reexecute, with populated
  rule state at the checkpoint boundary.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from rule_policy_checks import no_repeat_violations, read_jsonl

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
OUT = Path(os.environ.get("P2_RUNS_OUT", "")) if os.environ.get("P2_RUNS_OUT") else None
pytestmark = pytest.mark.skipif(
    os.environ.get("P2_RULE_RUNS") != "1" or OUT is None,
    reason="set P2_RULE_RUNS=1 and P2_RUNS_OUT=<dir> to run the long rule-policy checks",
)

DEVELOPMENT_SEEDS = [
    2195683955, 937154673, 1452436788, 1883209505, 497199041, 3459030352, 2507182619,
    3698676642, 2144999532, 1263016932, 2344699806, 1011827743, 2104929825, 2520148199,
    201486072, 1021125776, 1334592829, 3695162045, 3976177611, 404876745,
]  # fmt: skip
WORKERS = int(os.environ.get("P2_RUNS_WORKERS", "6"))
S1 = ROOT / "content" / "scenarios" / "s1-spring-visible" / "orig.toml"
DEFAULT = ROOT / "content" / "worlds" / "default.toml"


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "living_island", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )


def run_case(config: Path, seed: int, out: Path, ticks: int = 1008) -> dict[str, object]:
    started = time.monotonic()
    done = cli(
        "run", "--config", str(config), "--ticks", str(ticks), "--seed", str(seed),
        "--policy", "rule-based", "--out", str(out), "--export-replay",
    )  # fmt: skip
    wall = round(time.monotonic() - started, 1)
    result: dict[str, object] = {"seed": seed, "exit": done.returncode, "wall_s": wall}
    if done.returncode != 0:
        result["stderr"] = done.stderr[-400:]
        return result
    final = sorted(out.glob("checkpoint-*.json"))[-1]
    world = json.loads(final.read_text(encoding="utf-8"))["world"]
    records = read_jsonl(out / "decisions.jsonl")
    result.update(
        final_tick=world["tick"],
        alive={r["id"]: r["alive"] for r in world["residents"]},
        substituted=sum(1 for r in records if r["substituted"]),
        decisions=len(records),
    )
    return result


def tree_tiles(config: Path) -> dict[str, tuple[int, int]]:
    import tomllib

    with config.open("rb") as f:
        raw = tomllib.load(f)
    return {t["id"]: (t["position"][0], t["position"][1]) for t in raw["world"]["fruit_trees"]}


def test_s1_twenty_development_seeds():
    assert OUT is not None
    started = time.monotonic()
    with ThreadPoolExecutor(WORKERS) as pool:
        rows = list(
            pool.map(lambda seed: run_case(S1, seed, OUT / "s1" / f"s{seed}"), DEVELOPMENT_SEEDS)
        )
    total = round(time.monotonic() - started, 1)
    summary = {"workers": WORKERS, "total_wall_s": total, "cases": rows}
    (OUT / "s1-summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    failures = [
        r
        for r in rows
        if r["exit"] != 0
        or r.get("final_tick") != 1008
        or not all(r.get("alive", {}).values())
        or r.get("substituted") != 0
    ]
    assert failures == []
    trees = tree_tiles(S1)
    for row in rows:
        assert no_repeat_violations(OUT / "s1" / f"s{row['seed']}", trees) == []


def test_s2_no_repeat_on_development_seeds():
    assert OUT is not None
    seeds = DEVELOPMENT_SEEDS[: int(os.environ.get("P2_S2_SEEDS", "4"))]
    with ThreadPoolExecutor(WORKERS) as pool:
        rows = list(pool.map(lambda seed: run_case(DEFAULT, seed, OUT / "s2" / f"s{seed}"), seeds))
    (OUT / "s2-summary.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(json.dumps(rows, indent=1))
    trees = tree_tiles(DEFAULT)
    for row in rows:
        assert row["exit"] == 0, row
        assert no_repeat_violations(OUT / "s2" / f"s{row['seed']}", trees) == []


def test_rule_run_resume_and_reexecute():
    assert OUT is not None
    base = OUT / "resume"
    source = base / "source"
    done = cli(
        "run", "--config", str(DEFAULT), "--ticks", "432", "--seed", "937154673",
        "--policy", "rule-based", "--out", str(source), "--checkpoint-every", "144",
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    checkpoints = sorted(p.name for p in source.glob("checkpoint-*.json"))
    assert "checkpoint-0000000144.json" in checkpoints
    saved = json.loads((source / "checkpoint-0000000144.json").read_text(encoding="utf-8"))
    states = [r["policy_state"] for r in saved["agent_state"]["runtime_states"]]
    populated = [
        s for s in states if s["failed_targets"] or s["cue_impressions"] or s["commitment"]
    ]
    assert populated, "no rule state at the boundary"
    resumed = base / "resumed"
    done = cli(
        "resume", "--checkpoint", str(source / "checkpoint-0000000144.json"),
        "--source-run", str(source), "--ticks", "288", "--out", str(resumed),
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    for name, cursor in (
        ("events.jsonl", saved["event_cursor"]),
        ("decisions.jsonl", saved["decision_record_cursor"]),
    ):
        tail = (source / name).read_text(encoding="utf-8").splitlines()[cursor:]
        assert (resumed / name).read_text(encoding="utf-8").splitlines() == tail, name
    name = "checkpoint-0000000432.json"
    assert (resumed / name).read_bytes() == (source / name).read_bytes(), name
    again = base / "reexecuted"
    done = cli("reexecute", "--source-run", str(source), "--out", str(again))
    assert done.returncode == 0, done.stderr
    assert (again / "events.jsonl").read_bytes() == (source / "events.jsonl").read_bytes()
    assert (again / "decisions.jsonl").read_bytes() == (source / "decisions.jsonl").read_bytes()
    final = "checkpoint-0000000432.json"
    world = [json.loads((d / final).read_text(encoding="utf-8"))["world"] for d in (again, source)]
    assert (
        world[0] == world[1]
    )  # the checkpoint's policy config differs (recorded-v0), not its world
    trace = [
        json.loads((d / "decision-trace.json").read_text(encoding="utf-8")) for d in (again, source)
    ]
    assert trace[0]["final_world_sha256"] == trace[1]["final_world_sha256"]
