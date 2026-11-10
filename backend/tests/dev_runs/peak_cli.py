"""Run the CLI in-process and record the peak back-off entry counts of every resident (OQ-064).

Usage: ``python tests/dev_runs/peak_cli.py <peak.json> <cli args...>``. The counts are taken from
each committed next state, so they cover every decision of the run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from living_island.agents.rule_based import policy as rule_policy
from living_island.agents.rule_based.keys import LOCAL_CODES
from living_island.sim.cli import main

peaks: dict[str, dict[str, int]] = {}
original = rule_policy.RuleBasedPolicy.finish_decision
original_decide = rule_policy.RuleBasedPolicy.decide
actors: dict[int, str] = {}


def decide(self: rule_policy.RuleBasedPolicy, request: Any) -> Any:
    actors[id(self)] = request.actor_id
    return original_decide(self, request)


def finish_decision(self: rule_policy.RuleBasedPolicy, accepted: bool) -> None:
    pending = self._pending
    if accepted and pending is not None:
        actor = actors[id(self)]
        local = sum(1 for e in pending.failed_targets if e.code in LOCAL_CODES)
        failure = len(pending.failed_targets) - local
        record = peaks.setdefault(actor, {"local": 0, "failure": 0})
        record["local"] = max(record["local"], local)
        record["failure"] = max(record["failure"], failure)
    original(self, accepted)


rule_policy.RuleBasedPolicy.decide = decide  # type: ignore[method-assign]
rule_policy.RuleBasedPolicy.finish_decision = finish_decision  # type: ignore[method-assign]

if __name__ == "__main__":
    out = Path(sys.argv[1])
    code = main(sys.argv[2:])
    out.write_text(json.dumps(peaks, sort_keys=True), encoding="utf-8")
    raise SystemExit(code)
