"""Run-artifact checks shared by the rule-policy tests (P2-02 no-repeat, S1 pass line)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Rule Policy §5: failure codes that back off, and the key kind each one uses.
BACKOFF_CODES: dict[str, dict[str, str]] = {
    "move_to": {"INVALID_TARGET": "target", "PATH_BLOCKED": "target", "NO_PATH": "target"},
    "gather": {
        "OUT_OF_REACH": "target",
        "RESOURCE_TAKEN": "target",
        "INVALID_TARGET": "target",
        "INVENTORY_FULL": "self",
    },
    "pick_up": {
        "ITEM_TAKEN": "target",
        "OUT_OF_REACH": "target",
        "INVALID_TARGET": "target",
        "INVENTORY_FULL": "self",
    },
    "give": {"OUT_OF_REACH": "target", "INVENTORY_FULL": "target", "INVALID_TARGET": "target"},
    "talk": {
        c: "target"
        for c in (
            "INVALID_TARGET",
            "OUT_OF_HEARING",
            "INVALID_SPEECH_ACT",
            "INVALID_REPLY",
            "DIALOGUE_LIMIT",
        )
    },
    "fill_canteen": {"NO_ITEM": "target", "OUT_OF_REACH": "target", "INVALID_TARGET": "target"},
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def intent_key(intent: dict[str, Any], tree_tiles: dict[str, tuple[int, int]]) -> Any:
    """The §7.1 target key of an intent record: a tuple, or None for target-less actions."""
    target = intent["target"]
    if target is None:
        return None
    if intent["action_type"] == "gather":
        return ("tile", *tree_tiles[target["id"]])
    if target["kind"] == "tile":
        return ("tile", target["position"]["x"], target["position"]["y"])
    return (target["kind"], target["id"])


def no_repeat_violations(
    run_dir: Path, tree_tiles: dict[str, tuple[int, int]], retry: int = 36
) -> list[str]:
    """Plans that contain an intent matching a failure entry before its retry tick.

    Entries are rebuilt from the run artifacts: a failed intent of a backed-off kind writes
    ``(action, key)`` at the actor's first decision at or after the failure tick, and holds
    until ``written_tick + retry``.
    """
    decisions = read_jsonl(run_dir / "decisions.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")
    by_intent = {i["intent_id"]: i for rec in decisions for i in rec["plan"]["intents"]}
    entries: list[tuple[str, str, Any, int, int]] = []  # actor, action, key, from, until
    for event in events:
        if event["type"] != "action_failed":
            continue
        intent = by_intent.get(event["intent_id"])
        code = event["payload"]["failure_code"]
        if intent is None:
            continue
        kind = BACKOFF_CODES.get(intent["action_type"], {}).get(code)
        if kind is None:
            continue
        key = "self" if kind == "self" else intent_key(intent, tree_tiles)
        written = min(
            (
                d["tick"]
                for d in decisions
                if d["actor_id"] == intent["actor_id"] and d["tick"] >= event["tick"]
            ),
            default=None,
        )
        if written is not None:
            entries.append(
                (intent["actor_id"], intent["action_type"], key, written, written + retry)
            )
    violations = []
    for rec in decisions:
        for intent in rec["plan"]["intents"]:
            for actor, action, key, start, until in entries:
                if actor != rec["actor_id"] or not (start <= rec["tick"] < until):
                    continue
                if intent["action_type"] == action and (
                    key == "self" or intent_key(intent, tree_tiles) == key
                ):
                    violations.append(f"{rec['actor_id']}@{rec['tick']}: {action} {key}")
    return violations
