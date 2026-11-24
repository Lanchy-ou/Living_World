"""Starter CT-07 scripted-week evidence."""

from collections.abc import Callable
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Literal

from living_island.persistence.v2.journal import PacketJournal, store_once
from living_island.persistence.v2.manifest import RunManifest
from living_island.sim.v2 import cli
from living_island.sim.v2.scenarios.receipts import CasePlan, State, file_digest
from living_island.sim.v2.scenarios.runtime import (
    Boundary,
    Scenario,
    Session,
    run_or_resume,
    scripted,
)
from living_island.sim.v2.scenarios.starter import StarterScenario, load_starter_pack
from living_island.world.v2.engine import World, initialize
from living_island.world.v2.protocol import Coord
from living_island.world.v2.rules import Pack, load_vocabulary
from living_island.world.v2.rules.schema import canonical_json_bytes, content_hash

from .ledger import Balance, Ledger, ledger_bytes
from .script import SEED, START, WEEK, Schedule


def starter() -> StarterScenario:
    return load_starter_pack(
        cli.ROOT / "content/worlds/default.toml",
        cli.PACK.parent / "starter-v1",
        load_vocabulary(cli.VOCABULARY),
        seed=SEED,
    )


def validation(pack: Pack, run_id: str) -> bytes:
    rules = {}
    for key, rule in pack.rules.items():
        row = rule.data
        branches = ["applied"]
        if row["trigger"].startswith("verb:"):
            mode = row["on_interrupt"]
            branches.extend(["unmatched", "unmet", mode if mode == "lose" else next(iter(mode))])
            if row["success_per_mille"] < 1000:
                branches.append("chance_failed")
        rules[key] = {"branches": branches, "sha256": rule.content_hash, "definition": row}
    return canonical_json_bytes(
        {
            "content": RunManifest.capture(run_id, pack).model_dump(mode="json"),
            "report": asdict(pack.report),
            "rules": rules,
        }
    )


def verdict(balance: Balance, complete: bool) -> Literal["PASS", "FAIL", "PARTIAL"]:
    if balance.first_difference:
        return "FAIL"
    if not complete or balance.tick != WEEK:
        return "PARTIAL"
    for subtotals in (balance.sources, balance.net_sinks, balance.outputs):
        if not any(v > 0 for units in subtotals.values() for v in units.values()):
            return "FAIL"
    return "PASS" if balance.transfers else "FAIL"


def publish(directory: Path, balance: Balance, complete: bool, checkpoint: str) -> Path:
    status = verdict(balance, complete)
    tick = balance.tick
    prefix = "" if complete and tick == WEEK else f"{'fixture' if complete else 'prefix'}-{tick}-"
    data = ledger_bytes(directory, balance)
    ledger = prefix + "ledger.jsonl"
    store_once(directory / ledger, data)
    artifacts = {
        ledger: sha256(data).hexdigest(),
        "validator.json": file_digest(directory / "validator.json"),
        "inputs.json": file_digest(directory / "inputs.json"),
        checkpoint: file_digest(directory / checkpoint),
    }
    if complete:
        artifacts["evidence.json"] = file_digest(directory / "evidence.json")
    receipt = directory / (prefix + "receipt.json")
    store_once(
        receipt,
        canonical_json_bytes(
            {
                "status": status,
                "week_ticks": WEEK,
                "committed_ticks": tick,
                "balance": balance.model_dump(mode="json"),
                "artifacts": artifacts,
            }
        ),
    )
    lines = [
        f"# CT-07 scripted conservation — {status}",
        "",
        f"{tick} of {WEEK} ticks committed. Seed {SEED}.",
        f"[Ledger]({ledger}) · [Receipt]({receipt.name}) · [Validated rules](validator.json)",
        "",
        "| Matter | Initial | Expected | Observed |",
        "|---|---:|---:|---:|",
        *(
            f"| {k} | {v} | {balance.expected[k]} | {balance.observed[k]} |"
            for k, v in balance.initial.items()
        ),
        "",
        f"Sources: {balance.sources}",
        f"Net destruction by rule: {balance.net_sinks}",
        f"Unsourced outputs: {balance.outputs}",
        f"Transfers: {balance.transfers}",
    ]
    if balance.sample:
        sample = balance.sample
        sample_tick = int(sample.event_id.rsplit(":", 2)[1])
        lines.append(
            f"Sample {sample.rule_id} / {sample.branch}: "
            f"[{sample.event_id}](ledger/{sample_tick}.json)."
        )
    if diff := balance.first_difference:
        lines.extend(
            [
                "",
                f"First difference at tick {diff.tick} in {diff.matter_class}: "
                f"expected {diff.expected}, observed {diff.observed}.",
                f"[Ledger entries](ledger/{diff.tick}.json) · "
                f"[Committed events](turns/{diff.tick - 1}.json)",
            ]
        )
        lines.extend(
            f"- [{e.rule_id} / {e.branch}](validator.json), "
            f"[{e.event_id}](turns/{diff.tick - 1}.json)"
            for e in diff.entries
        )
    store_once(directory / (prefix + "summary.md"), ("\n".join(lines) + "\n").encode())
    return receipt


def run(
    directory: Path,
    prepared: StarterScenario,
    program: Schedule,
    *,
    horizon: int = WEEK,
    pause_after: Callable[[int], bool] = lambda tick: False,
) -> Path:
    pack = prepared.pack
    residents = [
        r.model_copy(update={"position": Coord(x=START[r.id][0], y=START[r.id][1])})
        for r in prepared.setup.residents
    ]
    setup = prepared.setup.model_copy(
        update={"residents": tuple(residents), "run_id": "ct09-scripted"}
    )
    opening = initialize(pack, setup)
    ledger = Ledger(directory, pack, opening.state.entities.values())
    world = opening
    make_session = scripted(lambda state: program)

    def session(restored: World, journal: PacketJournal, state: State | None) -> Session:
        nonlocal world
        world = restored
        return make_session(world, journal, state)

    def observe(saved: State, boundary: Boundary) -> State:
        if saved and ledger.balance.tick == 0:
            ledger.balance = Balance.model_validate(saved)
            ledger_bytes(directory, ledger.balance)
        ledger.observe(boundary, world.state.entities.values())
        return ledger.balance.model_dump(mode="json")

    manifest = prepared.manifest
    case = Scenario(
        opening, manifest.config_blob_sha256, manifest.map_blob_sha256, session, observe
    )
    script_pin = content_hash(
        {
            actor: [i.model_dump(mode="json") for i in steps]
            for actor, steps in program.programs.items()
        }
    )
    plan = CasePlan(
        revision=content_hash(
            [
                file_digest(Path(__file__).with_name(name))
                for name in ("__init__.py", "script.py", "ledger.py")
            ]
        ),
        runner="CT-04",
        controller=script_pin,
        setup=content_hash(setup.model_dump(mode="json")),
        observer="committed-matter-ledger",
        arm="scripted",
        case_index=0,
        horizon=horizon,
        checkpoint_every=24,
    )

    def build() -> Scenario:
        store_once(directory / "validator.json", validation(pack, world.run_id))
        return case

    progress = run_or_resume(directory, plan, build, pause_after=pause_after)
    evidence = progress.evidence
    balance = ledger.balance if evidence is None else Balance.model_validate(evidence.observer)
    return publish(directory, balance, evidence is not None, progress.checkpoint)
