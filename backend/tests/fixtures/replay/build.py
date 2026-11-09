"""Builds the shared replay fixtures (P1-01b).

Run ``python build.py`` from this directory to rewrite ``valid.json`` and ``invalid/*.json``.
``backend/tests/unit/test_replay_contract.py`` fails if the committed files drift from this
builder, so the builder is the single place that explains each fixture.

These are hand-made contract fixtures, not simulation output. P1-07 (exporter) and P1-08
(browser validator) reuse the same files: the browser must reject every file in ``invalid/``
and accept ``valid.json``. A file named ``schema__*`` must additionally be refused by the
generated JSON Schema alone; the other invalid files need the cross-field validators.

Fixture name = ``<rule group>__<case>``; ``INVALID`` stores the substring the backend error
must contain, which starts with the rule slug used by ``contract/replay.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from living_island.world.facts import format_event_id

HERE = Path(__file__).resolve().parent
RUN_ID = "replay_fixture_run01"
HASH_A = "a" * 64
ROWS = [
    "~~~~~~~~",
    "~..,,W^~",
    "~.F,SC.~",
    "~.,,MF.~",
    "~~~~~~~~",
]
LEGEND = [
    ("~", "sea"),
    (".", "beach"),
    (",", "grass"),
    ("W", "woods"),
    ("^", "rock"),
    ("S", "spring"),
    ("C", "cave"),
    ("F", "fruit_tree"),
    ("M", "damp_moss"),
]

Doc = dict[str, Any]


def canonical(doc: object) -> bytes:
    """Canonical JSON (IC §6.3) plus one LF; the committed fixture bytes."""
    text = json.dumps(
        doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return (text + "\n").encode("utf-8")


def coord(x: int, y: int) -> Doc:
    return {"x": x, "y": y}


def event(
    tick: int,
    seq: int,
    type_: str,
    payload: Doc,
    *,
    actor: str | None = None,
    target: str | None = None,
    intent: str | None = None,
    caused_by: list[str] | None = None,
) -> Doc:
    return {
        "schema_version": "0.1",
        "run_id": RUN_ID,
        "event_id": format_event_id(RUN_ID, tick, seq),
        "tick": tick,
        "seq_in_tick": seq,
        "type": type_,
        "actor_id": actor,
        "target_id": target,
        "intent_id": intent,
        "llm_call_id": None,
        "caused_by_event_ids": caused_by or [],
        "payload": payload,
    }


def eid(tick: int, seq: int) -> str:
    return format_event_id(RUN_ID, tick, seq)


def resident(
    rid: str,
    x: int,
    y: int,
    *,
    alive: bool = True,
    health: int = 10000,
    fruit: int = 0,
    canteen: int | None = None,
    action: Doc | None = None,
) -> Doc:
    return {
        "id": rid,
        "position": coord(x, y),
        "alive": alive,
        "satiety": 9000,
        "hydration": 8000,
        "stamina": 7000,
        "health": health,
        "fruit_count": fruit,
        "canteen_servings": canteen,
        "active_action": action,
    }


def frame(
    tick: int,
    first: int,
    count: int,
    residents: list[Doc],
    trees: list[Doc],
    *,
    piles: list[Doc] | None = None,
    corpses: list[Doc] | None = None,
) -> Doc:
    return {
        "tick": tick,
        "residents": residents,
        "fruit_trees": trees,
        "ground_fruit": piles or [],
        "ground_canteen": None,
        "corpses": corpses or [],
        "event_range": {"first_index": first, "count": count},
    }


def tree(tid: str, x: int, y: int, stock: int) -> Doc:
    return {"id": tid, "position": coord(x, y), "stock": stock}


def build_valid() -> Doc:
    gather = {
        "intent_id": "ella.plan0001.i00",
        "action_type": "gather",
        "tick_started": 0,
        "remaining_ticks": 1,
    }
    both = [tree("fruit_01", 2, 2, 3), tree("fruit_02", 5, 3, 2)]
    after = [tree("fruit_01", 2, 2, 2), tree("fruit_02", 5, 3, 2)]
    frames = [
        frame(
            0,
            0,
            1,
            [
                resident("ella", 3, 2),
                resident("mia", 3, 1, fruit=1),
                resident("ryan", 1, 1, canteen=5),
            ],
            both,
        ),
        frame(
            1,
            1,
            2,
            [
                resident("ella", 3, 2, action=gather),
                resident("mia", 3, 1, fruit=1),
                resident("ryan", 1, 1, canteen=5),
            ],
            both,
        ),
        frame(
            2,
            3,
            4,
            [
                resident("ella", 3, 2, fruit=1),
                resident("mia", 3, 1, fruit=1),
                resident("ryan", 1, 1, canteen=5),
            ],
            after,
        ),
        frame(
            3,
            7,
            4,
            [
                resident("ella", 3, 2, fruit=1),
                resident("mia", 3, 1, alive=False, health=0),
                resident("ryan", 1, 1, canteen=5),
            ],
            after,
            piles=[{"position": coord(3, 1), "quantity": 1}],
            corpses=[{"id": "corpse@mia", "resident_id": "mia", "position": coord(3, 1)}],
        ),
    ]
    cond = {
        "resident_id": "ella",
        "satiety_before": 9000,
        "satiety_after": 8990,
        "hydration_before": 8000,
        "hydration_after": 7900,
        "stamina_before": 7000,
        "stamina_after": 6990,
        "health_before": 10000,
        "health_after": 10000,
    }
    events = [
        event(
            0,
            0,
            "world_initialized",
            {"config_hash": HASH_A, "map_hash": _map_hash(ROWS), "initial_snapshot_hash": HASH_A},
        ),
        event(
            1,
            0,
            "action_started",
            {"action_type": "gather", "plan_id": "ella.plan0001", "duration_ticks": 2},
            actor="ella",
            target="fruit_01",
            intent="ella.plan0001.i00",
        ),
        event(1, 1, "condition_updated", cond, actor="ella"),
        event(
            2,
            0,
            "fruit_gathered",
            {"tree_id": "fruit_01", "quantity": 1, "stock_before": 3, "stock_after": 2},
            actor="ella",
            target="fruit_01",
            intent="ella.plan0001.i00",
            caused_by=[eid(1, 0)],
        ),
        event(
            2,
            1,
            "action_succeeded",
            {"action_type": "gather", "result_code": "OK"},
            actor="ella",
            intent="ella.plan0001.i00",
            caused_by=[eid(2, 0)],
        ),
        event(
            2,
            2,
            "utterance_spoken",
            {
                "utterance_id": eid(2, 2),
                "addressee_id": "ella",
                "speech_act": "request",
                "text": "Could you spare a fruit?",
                "request": {"item_type": "fruit", "quantity": 1},
                "in_reply_to": None,
            },
            actor="ryan",
            target="ella",
        ),
        event(
            2,
            3,
            "utterance_heard",
            {"utterance_id": eid(2, 2), "listener_id": "ella"},
            actor="ryan",
            target="ella",
            caused_by=[eid(2, 2)],
        ),
        event(
            3,
            0,
            "utterance_spoken",
            {
                "utterance_id": eid(3, 0),
                "addressee_id": "ryan",
                "speech_act": "accept",
                "text": "Yes.",
                "request": None,
                "in_reply_to": eid(2, 2),
            },
            actor="ella",
            target="ryan",
            caused_by=[eid(2, 2)],
        ),
        event(
            3,
            1,
            "resident_died",
            {"resident_id": "mia", "position": coord(3, 1), "cause": "DEPRIVATION"},
            actor="mia",
        ),
        event(
            3,
            2,
            "corpse_created",
            {"corpse_id": "corpse@mia", "resident_id": "mia", "position": coord(3, 1)},
            actor="mia",
            caused_by=[eid(3, 1)],
        ),
        event(
            3,
            3,
            "item_dropped",
            {
                "resident_id": "mia",
                "position": coord(3, 1),
                "item_type": "fruit",
                "quantity": 1,
                "canteen_id": None,
                "canteen_servings": None,
            },
            actor="mia",
            caused_by=[eid(3, 1)],
        ),
    ]
    return {
        "replay_schema_version": "0.1",
        "run_id": RUN_ID,
        "world_id": "fixture_island",
        "config_hash": HASH_A,
        "map_hash": _map_hash(ROWS),
        "clock": {"tick_minutes": 10, "start_hour": 6, "day_start_hour": 6, "day_end_hour": 20},
        "condition_bounds": {"min_value": 0, "max_value": 10000},
        "map": {
            "width": 8,
            "height": 5,
            "rows": list(ROWS),
            "terrain_legend": [{"symbol": s, "terrain": t} for s, t in LEGEND],
        },
        "residents": [
            {"id": "ella", "display_name": "艾拉"},
            {"id": "mia", "display_name": "米娅"},
            {"id": "ryan", "display_name": "莱恩"},
        ],
        "frames": frames,
        "events": events,
    }


def _map_hash(rows: list[str]) -> str:
    return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Invalid fixtures: name -> (expected error substring, mutation)
# ---------------------------------------------------------------------------

Mutation = Callable[[Doc], None]


def _set_event_id(e: Doc, run_id: str, tick: int, seq: int) -> None:
    e["run_id"], e["tick"], e["seq_in_tick"] = run_id, tick, seq
    e["event_id"] = format_event_id(run_id, tick, seq)


def _rename_tree(d: Doc, old: str, new: str) -> None:
    for f in d["frames"]:
        for t in f["fruit_trees"]:
            if t["id"] == old:
                t["id"] = new
    for e in d["events"]:
        if e["target_id"] == old:
            e["target_id"] = new
        if e["payload"].get("tree_id") == old:
            e["payload"]["tree_id"] = new


def _extra_event(d: Doc) -> None:
    d["events"].append(
        event(4, 0, "action_succeeded", {"action_type": "wait", "result_code": "OK"}, actor="ella")
    )


def _tick_shift(d: Doc) -> None:
    for f in d["frames"]:
        f["tick"] += 1


def _run_id_mismatch(d: Doc) -> None:
    e = d["events"][4]
    _set_event_id(e, "other_run", e["tick"], e["seq_in_tick"])


def _duplicate_event(d: Doc) -> None:
    d["events"][2] = copy.deepcopy(d["events"][1])


def _swap_across_ticks(d: Doc) -> None:
    ev = d["events"]
    ev[2], ev[3] = ev[3], ev[2]


def _seq_gap(d: Doc) -> None:
    _set_event_id(d["events"][2], RUN_ID, 1, 2)


def _first_seq(d: Doc) -> None:
    _set_event_id(d["events"][0], RUN_ID, 0, 1)


def _bad_event_id(d: Doc) -> None:
    d["events"][4]["event_id"] = "not-an-event-id"


def _reply_not_request(d: Doc) -> None:
    p = d["events"][5]["payload"]
    p["speech_act"], p["request"] = "statement", None


def _reply_unresolved(d: Doc) -> None:
    d["events"][7]["payload"]["in_reply_to"] = eid(9, 9)


def _wrapper(d: Doc) -> None:
    wrapped = {"ReplayBundle": copy.deepcopy(d)}
    d.clear()
    d.update(wrapped)


def _bad_legend_symbol(d: Doc) -> None:
    d["map"]["terrain_legend"][0]["symbol"] = "~~"


def _swap_legend(d: Doc) -> None:
    leg = d["map"]["terrain_legend"]
    leg[0], leg[1] = leg[1], leg[0]


def _legend_extra(d: Doc) -> None:
    d["map"]["terrain_legend"].append({"symbol": "x", "terrain": "grass"})


def _legend_alias(d: Doc) -> None:
    d["map"]["terrain_legend"][0]["terrain"] = "beach"


def _pop(path: list[str | int]) -> Mutation:
    def apply(d: Doc) -> None:
        node: Any = d
        for key in path[:-1]:
            node = node[key]
        node.pop(path[-1])

    return apply


def _setter(path: list[str | int], value: object) -> Mutation:
    def apply(d: Doc) -> None:
        node: Any = d
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return apply


def _resident_frame(frame_index: int, resident_index: int, key: str, value: object) -> Mutation:
    return _setter(["frames", frame_index, "residents", resident_index, key], value)


def _dup_resident_in_frame(d: Doc) -> None:
    d["frames"][1]["residents"].append(copy.deepcopy(d["frames"][1]["residents"][2]))


def _reverse_frame_residents(d: Doc) -> None:
    d["frames"][1]["residents"].reverse()


def _two_piles(order: str) -> Mutation:
    def apply(d: Doc) -> None:
        a = {"position": coord(3, 1), "quantity": 1}
        b = {"position": coord(2, 1), "quantity": 1}
        piles = {"unsorted": [a, b], "duplicate": [a, copy.deepcopy(a)]}[order]
        d["frames"][3]["ground_fruit"] = piles

    return apply


def _swap_trees_in_frame(d: Doc) -> None:
    t = d["frames"][1]["fruit_trees"]
    t[0], t[1] = t[1], t[0]


def _two_corpses_unsorted(d: Doc) -> None:
    c = d["frames"][3]["corpses"]
    c.insert(0, {"id": "corpse@zed", "resident_id": "ella", "position": coord(3, 2)})


def _tree_collides_with_resident(d: Doc) -> None:
    _rename_tree(d, "fruit_01", "ella")


def _rename_tree_in_one_frame(d: Doc) -> None:
    d["frames"][2]["fruit_trees"][1]["id"] = "fruit_03"


def _trees_share_position(d: Doc) -> None:
    d["frames"][0]["fruit_trees"][1]["position"] = coord(2, 2)


def _move_trees_off_f(d: Doc) -> None:
    for f in d["frames"]:
        f["fruit_trees"][0]["position"] = coord(1, 1)


INVALID: dict[str, tuple[str, Mutation]] = {
    # schema-level refusals (also refused by the generated JSON Schema)
    "schema__unknown_version": ("Input should be '0.1'", _setter(["replay_schema_version"], "0.2")),
    "schema__unknown_field": ("Extra inputs are not permitted", _setter(["debug"], 1)),
    "schema__float_where_integer": (
        "valid integer",
        _setter(["frames", 1, "residents", 0, "satiety"], 1.5),
    ),
    "schema__contract_wrapper_shape": ("Field required", _wrapper),
    "schema__missing_field": ("Field required", _pop(["clock"])),
    "schema__negative_count": (
        "greater than or equal to 0",
        _setter(["frames", 3, "ground_fruit", 0, "quantity"], -1),
    ),
    # frame ticks
    "frame_ticks__gap": ("frame_ticks", _setter(["frames", 2, "tick"], 5)),
    "frame_ticks__not_from_zero": ("frame_ticks", _tick_shift),
    # event_range slicing
    "event_range__first_index_not_cumulative": (
        "event_range: frame 2 first_index",
        _setter(["frames", 2, "event_range", "first_index"], 4),
    ),
    "event_range__count_mismatch": (
        "event_range: frame 1 count 1",
        _setter(["frames", 1, "event_range", "count"], 1),
    ),
    "event_range__slice_holds_foreign_tick": (
        "slice holds",
        _setter(["frames", 1, "event_range", "count"], 3),
    ),
    "event_range__slice_past_end": (
        "slice ends past",
        _setter(["frames", 3, "event_range", "count"], 10),
    ),
    "event_range__events_not_covered": ("slices cover", _extra_event),
    # event order, seq, IDs
    "event_order__tick_regresses": ("event_order", _swap_across_ticks),
    "event_seq__gap": ("event_seq", _seq_gap),
    "event_seq__first_not_zero": ("event_seq: first event", _first_seq),
    "run_id__mismatch": ("run_id", _run_id_mismatch),
    "event_id__bad_format": ("event_id must equal", _bad_event_id),
    "event_id__duplicate": ("duplicate event id", _duplicate_event),
    # causal and utterance references
    "causal_refs__unknown": (
        "cites unknown event",
        _setter(["events", 4, "caused_by_event_ids"], ["nope"]),
    ),
    "causal_refs__forward": (
        "not earlier",
        _setter(["events", 1, "caused_by_event_ids"], [eid(2, 0)]),
    ),
    "utterance_refs__id_not_event_id": (
        "must equal its event id",
        _setter(["events", 5, "payload", "utterance_id"], "x"),
    ),
    "utterance_refs__heard_unknown": (
        "cites no earlier utterance_spoken",
        _setter(["events", 6, "payload", "utterance_id"], "nope"),
    ),
    "utterance_refs__reply_not_request": ("must cite an earlier", _reply_not_request),
    "utterance_refs__reply_unresolved": ("must cite an earlier", _reply_unresolved),
    # resident / entity references and namespaces
    "entity_refs__actor_unknown": (
        "actor_id 'ghost'",
        _setter(["events", 3, "actor_id"], "ghost"),
    ),
    "entity_refs__payload_resident_unknown": (
        "resident_id 'ghost'",
        _setter(["events", 2, "payload", "resident_id"], "ghost"),
    ),
    "entity_refs__tree_unknown": (
        "tree_id 'fruit_99'",
        _setter(["events", 3, "payload", "tree_id"], "fruit_99"),
    ),
    "entity_refs__corpse_resident_unknown": (
        "undeclared resident 'ghost'",
        _setter(["frames", 3, "corpses", 0, "resident_id"], "ghost"),
    ),
    "namespaces__tree_collides_with_resident": ("namespaces", _tree_collides_with_resident),
    # map and legend
    "map__row_count": ("map: expected 5 rows", _pop(["map", "rows", 4])),
    "map__row_width": ("map: row 1 has length 9", _setter(["map", "rows", 1], ROWS[1] + "~")),
    "map__unknown_symbol": (
        "String should match pattern",
        _setter(["map", "rows", 0], "X" + ROWS[0][1:]),
    ),
    "map__nonpositive_dimension": (
        "greater than or equal to 1",
        _setter(["map", "width"], 0),
    ),
    "map__hash_mismatch": ("map_hash", _setter(["map_hash"], "b" * 64)),
    "legend__extra_entry": ("legend:", _legend_extra),
    "legend__wrong_order": ("legend:", _swap_legend),
    "legend__alias_terrain": ("legend:", _legend_alias),
    "legend__multichar_symbol": ("at most 1 character", _bad_legend_symbol),
    # clock and bounds
    "clock__tick_minutes_not_divisor": ("must divide 1440", _setter(["clock", "tick_minutes"], 7)),
    "clock__day_window_inverted": (
        "day_start_hour must be below",
        _setter(["clock", "day_end_hour"], 6),
    ),
    "condition_bounds__min_not_zero": (
        "Input should be 0",
        _setter(["condition_bounds", "min_value"], 5),
    ),
    "condition_bounds__max_not_above_min": (
        "greater than or equal to 1",
        _setter(["condition_bounds", "max_value"], 0),
    ),
    "conditions__above_max": (
        "conditions: satiety",
        _resident_frame(1, 0, "satiety", 10001),
    ),
    # residents per frame
    "residents__duplicate_declared": (
        "residents: duplicate",
        lambda d: d["residents"].insert(1, copy.deepcopy(d["residents"][0])),
    ),
    "residents__declared_unsorted": ("residents: declared", lambda d: d["residents"].reverse()),
    "frame_residents__missing": ("frame_residents", _pop(["frames", 1, "residents", 2])),
    "frame_residents__undeclared": (
        "frame_residents",
        _resident_frame(2, 1, "id", "nia"),
    ),
    "frame_sort__duplicate_resident": ("frame_sort: duplicate resident", _dup_resident_in_frame),
    "frame_sort__residents_unsorted": ("frame_sort", _reverse_frame_residents),
    # trees, piles, corpses, coordinates
    "trees__not_one_to_one_with_f_tiles": ("one-to-one", _pop(["frames", 0, "fruit_trees", 1])),
    "trees__off_f_tile": ("one-to-one", _move_trees_off_f),
    "trees__share_position": ("share a position", _trees_share_position),
    "trees__change_between_frames": ("differ from tick 0", _rename_tree_in_one_frame),
    "frame_sort__trees_unsorted": ("frame_sort", _swap_trees_in_frame),
    "frame_sort__corpses_unsorted": ("frame_sort", _two_corpses_unsorted),
    "frame_sort__ground_fruit_unsorted": ("frame_sort", _two_piles("unsorted")),
    "ground_fruit__duplicate_position": ("duplicate ground fruit", _two_piles("duplicate")),
    "coords__resident_outside_map": (
        "coords: resident",
        _setter(["frames", 1, "residents", 0, "position", "x"], 8),
    ),
    "coords__ground_fruit_outside_map": (
        "coords: ground fruit",
        _setter(["frames", 3, "ground_fruit", 0, "position", "y"], 5),
    ),
    "coords__corpse_outside_map": (
        "coords: corpse",
        _setter(["frames", 3, "corpses", 0, "position", "x"], 8),
    ),
    "coords__event_payload_outside_map": (
        "coords: position",
        _setter(["events", 8, "payload", "position", "x"], 9),
    ),
}


def build_all() -> dict[Path, bytes]:
    out: dict[Path, bytes] = {HERE / "valid.json": canonical(build_valid())}
    for name, (_, mutate) in INVALID.items():
        doc = build_valid()
        mutate(doc)
        out[HERE / "invalid" / f"{name}.json"] = canonical(doc)
    return out


def main() -> None:
    (HERE / "invalid").mkdir(exist_ok=True)
    for path, data in build_all().items():
        path.write_bytes(data)
    print(f"wrote {len(INVALID) + 1} fixtures")


if __name__ == "__main__":
    main()
