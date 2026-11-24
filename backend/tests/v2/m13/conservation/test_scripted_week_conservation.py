"""CT-07 exercises the starter validator, the event ledger and checkpoint boundary."""

import json
from hashlib import sha256
from itertools import count
from shutil import copytree

import pytest


def read(path):
    return json.loads(path.read_bytes())


@pytest.fixture(scope="module")
def short_case(tmp_path_factory):
    from living_island.sim.v2 import cli
    from living_island.sim.v2.scenarios.conservation import starter
    from living_island.sim.v2.scenarios.conservation.script import SEED, entity, intent, schedules
    from living_island.sim.v2.scenarios.starter import load_starter_pack
    from living_island.world.v2.engine.chance import chance_roll

    production = starter()
    pack = production.pack
    fixture = tmp_path_factory.mktemp("placements")
    copytree(cli.PACK, fixture / "compat-v1")
    leaf = copytree(cli.PACK.parent / "starter-v1", fixture / "starter-v1")
    light = pack.rules["light_fire"].data
    tinder = light["inputs"][0]["qty"]
    pile = next(c["value"] for c in light["conditions"] if c["id"] == "pile")
    wear = pack.data["archetype"]["stone_axe"]["components"]["durability"]["max_wear"]
    with (leaf / "instances.toml").open("a", encoding="utf-8") as f:
        for arch, qty in [("grass_tuft", tinder), ("stone", 1), ("flint_nodule", 1)]:
            f.write(
                f'\n[[instance]]\nid="held_{arch}"\narchetype="{arch}"\n'
                f'at={{holder="ella"}}\nquantity={qty}\n'
            )
        f.write(
            f'\n[[instance]]\nid="pile"\narchetype="branch"\nat={{tile=[42,11]}}\nquantity={pile}\n'
            f'\n[[instance]]\nid="worn"\narchetype="stone_axe"\nat={{tile=[37,31]}}\n'
            f"state={{durability={{wear={wear}}}}}\n"
        )
    case = load_starter_pack(
        cli.ROOT / "content/worlds/default.toml", leaf, pack.vocabulary, seed=SEED
    )
    program = schedules(case.pack)
    # Pick a turn with a deterministic failed roll. Run the real chance rule with
    # its admitted values and the actual coordinator-issued identity.
    delay = next(
        n
        for n in count()
        if chance_roll(
            SEED,
            n * pack.data["timing"]["wait_ticks"] + light["work_ticks"],
            "light_fire",
            f"ella:t{n:06d}:a",
        )
        >= light["success_per_mille"]
    )
    program.programs["ella"] = (
        *((intent(action="wait"),) * delay),
        intent(
            "light",
            entity("pile"),
            tools=("flint_nodule", "stone"),
            inputs=(("grass_tuft", tinder),),
        ),
        *program.programs["ella"],
    )
    return case, program


def test_ct07_scripted_matter_and_resume(short_case, tmp_path):
    from living_island.sim.v2.scenarios.conservation import run
    from living_island.sim.v2.scenarios.conservation.script import WEEK

    case, program = short_case
    pack = case.pack
    # First short tree-regrowth offset and the potter's craft/drop demonstrate
    # the real schedules without executing a week in Gate 1 or CI.
    tree = pack.data["instance"]["fruit_02"]
    horizon = tree["phase_offset"]["compat_regrow_fruit"]
    straight, resumed = tmp_path / "straight", tmp_path / "resumed"
    first = read(run(straight, case, program, horizon=horizon))
    pause = read(run(resumed, case, program, horizon=horizon, pause_after=lambda tick: tick == 1))
    assert pause["status"] == "PARTIAL" and pause["committed_ticks"] == 1
    assert pause["week_ticks"] == WEEK
    assert not (resumed / "evidence.json").exists()
    second = read(run(resumed, case, program, horizon=horizon))
    assert first["balance"] == second["balance"]
    for key in ("prefix_sha256", "final_snapshot_sha256"):
        assert read(straight / "evidence.json")[key] == read(resumed / "evidence.json")[key]
    ledger = f"fixture-{horizon}-ledger.jsonl"
    data = (straight / ledger).read_bytes()
    assert data == (resumed / ledger).read_bytes()
    assert first["artifacts"][ledger] == sha256(data).hexdigest()
    rows = [json.loads(line) for line in data.splitlines()]
    assert [r["tick"] for r in rows] == list(range(1, horizon + 1))
    assert all(r["expected"] == r["observed"] for r in rows)
    entries = [e for r in rows for e in r["entries"]]
    assert len(entries) == len({e["event_id"] for e in entries})
    assert {e["source"] for e in entries} >= {"spring_water", "fruit_regrowth"}
    assert any(
        e["branch"] == "chance_failed"
        and e["rule_id"] == "light_fire"
        and e["archetype"] == "grass_tuft"
        and e["operation"] == "consume"
        for e in entries
    )
    assert not any(e["rule_id"] == "light_fire" and e["archetype"] == "branch" for e in entries)
    balance = first["balance"]
    assert balance["outputs"]["shape_pot"] == pack.data["archetype"]["unfired_pot"]["matter"]
    assert balance["net_sinks"]["shape_pot"]["mineral"] == 0
    assert balance["net_sinks"]["axe_breaks"]["plant"] == (
        pack.data["archetype"]["stone_axe"]["matter"]["plant"]
        - pack.data["archetype"]["branch"]["matter"]["plant"]
    )
    split = next(
        r
        for r in rows
        if {"stack_split", "item_transferred"} <= {kind for kind, _ in r["movements"]}
    )
    before = rows[split["tick"] - 2]
    assert (
        split["expected"] == before["expected"] and split["entity_count"] > before["entity_count"]
    )
    # Independent placement oracle, including held canteen, nested water, and implicit store stock.
    opening = dict.fromkeys(pack.vocabulary.matter_classes, 0)
    for instance in pack.data["instance"].values():
        arch = pack.data["archetype"][instance["archetype"]]
        for kind, units in arch["matter"].items():
            opening[kind] += units * instance["quantity"]
        if "store" in arch["components"]:
            store = arch["components"]["store"] | instance["state"]["store"]
            for kind, units in pack.data["archetype"][store["archetype"]]["matter"].items():
                opening[kind] += units * store["count"]
    assert balance["initial"] == opening and opening["water"] > 0
    assert first["status"] == "PARTIAL" and balance["first_difference"] is None
    validated = read(straight / "validator.json")
    assert (
        validated["report"]["slot_coverage"].keys()
        == validated["rules"].keys()
        == pack.rules.keys()
    )
    assert validated["content"]["rule_library_hash"] == pack.rule_library_hash
    assert validated["content"]["packs"][-1]["pack_hash"] == pack.pack_hash
    assert "chance_failed" in validated["rules"]["light_fire"]["branches"]


def test_first_incorrect_matter_has_committed_witness(tmp_path, monkeypatch):
    from living_island.sim.v2.scenarios.conservation import ledger, run, starter
    from living_island.sim.v2.scenarios.conservation.script import schedules

    actual = ledger.transactions

    def perturbed(boundary, matter):
        for row in actual(boundary, matter):
            if row.rule_id == "compat_drink_canteen":
                yield row.model_copy(update={"units": {"water": row.units["water"] + 1}})
            else:
                yield row

    monkeypatch.setattr(ledger, "transactions", perturbed)
    case = starter()
    tick = case.pack.rules["compat_drink_canteen"].data["work_ticks"]
    result = read(run(tmp_path, case, schedules(case.pack), horizon=tick + 1))
    assert result["status"] == "FAIL"
    diff = result["balance"]["first_difference"]
    assert (diff["tick"], diff["matter_class"], diff["observed"] - diff["expected"]) == (
        tick,
        "water",
        1,
    )
    summary = (tmp_path / f"fixture-{tick + 1}-summary.md").read_text(encoding="utf-8")
    for ref in (
        diff["entries"][0]["event_id"],
        "compat_drink_canteen / applied",
        f"turns/{tick - 1}.json",
        f"ledger/{tick}.json",
    ):
        assert ref in summary


def test_changed_ledger_refused_on_resume(tmp_path):
    from living_island.sim.v2.scenarios.conservation import run, starter
    from living_island.sim.v2.scenarios.conservation.script import schedules

    case = starter()
    program = schedules(case.pack)
    run(tmp_path, case, program, pause_after=lambda tick: tick == 1)
    (tmp_path / "ledger/1.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="ledger prefix differs at committed tick 1"):
        run(tmp_path, case, program, horizon=1008, pause_after=lambda tick: tick == 2)
