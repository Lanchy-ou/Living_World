"""Record five starter demonstrations through CT-04's resumable driver."""

import argparse
import subprocess
from collections.abc import Callable
from functools import partial
from pathlib import Path

from living_island.persistence.v2.journal import store_once
from living_island.sim.v2 import cli
from living_island.world.v2.rules.schema import content_hash

from .. import runtime
from ..receipts import CasePlan, file_digest
from .fixture import SEED, Opening
from .physical import baking, fruit, lighting, period, regrowth, rule_value, spilling, wear
from .physiology import early_wake, fainting, fatigue, fatigue_day, metabolism, night, rate_control
from .trial import Trial

VECTORS: dict[str, Callable[[], Trial]] = {
    "regrowth": regrowth,
    "light-success": partial(lighting, succeeds=True),
    "light-failure": partial(lighting, succeeds=False),
    "bake-insert-5": partial(baking, 5),
    "spill-admitted": partial(spilling, blocked=False),
    "fruit-rot": fruit,
    "fruit-crumble": partial(fruit, crumble=True),
    "axe-wear": wear,
    "fatigue-day": fatigue_day,
    "fatigue-faint": fainting,
    "fatigue-sleep": night,
    "wake-satiety-urgent": partial(early_wake, "satiety", critical=False),
    "wake-satiety-critical": partial(early_wake, "satiety", critical=True),
    "wake-hydration-urgent": partial(early_wake, "hydration", critical=False),
    "wake-hydration-critical": partial(early_wake, "hydration", critical=True),
    "asleep-awake-rates": rate_control,
    "bake-insert-6": partial(baking, 6),
    "bake-insert-7": partial(baking, 7),
    "spill-blocked": partial(spilling, blocked=True),
    "fruit-split": partial(fruit, split=True),
}


def case_plan(trial: Trial, revision: str) -> CasePlan:
    sources = Path(__file__).parent
    pin = content_hash({path.name: file_digest(path) for path in sorted(sources.glob("*.py"))})
    return CasePlan(
        revision=revision,
        runner=content_hash(
            {
                name: file_digest(Path(runtime.__file__).with_name(name))
                for name in ("runtime.py", "receipts.py")
            }
        ),
        controller=f"{trial.name}/{pin}",
        setup=f"ct08:{trial.name}:9x7-spring/{pin}",
        observer=f"ct08-boundaries/{pin}",
        arm=trial.demo,
        case_index=trial.index,
        horizon=trial.horizon,
        checkpoint_every=24,
    )


def changed_fixed_values() -> dict[str, dict[str, int]]:
    """D5 leaves the original published acceptance values visible after a tuning change."""
    opening = Opening("published-values", SEED)
    pack = opening.pack.source.data
    config = fatigue(opening)
    satiety = metabolism(opening, "satiety")
    hydration = metabolism(opening, "hydration")
    values = {
        "CT-08/deadwood_period": (72, period(opening, "regrow_deadwood")),
        "CT-08/fire_fuel": (18, pack["archetype"]["campfire"]["components"]["fuel"]["ticks_left"]),
        "CT-08/axe_wear": (
            20,
            pack["archetype"]["stone_axe"]["components"]["durability"]["max_wear"],
        ),
        "CT-08/fruit_rot_age": (432, rule_value(opening, "fruit_rots", "old")),
        "CT-08/rotten_crumble_age": (288, rule_value(opening, "rotten_fruit_crumbles", "gone")),
        "CT-09/day_fatigue": (
            6400,
            96 * config.awake_per_tick
            + 50 * config.per_utterance_heard
            + 20 * config.per_first_sighting,
        ),
        "CT-09/silent_awake_ticks": (
            200,
            (opening.pack.needs["mental_fatigue"].maximum + config.awake_per_tick - 1)
            // config.awake_per_tick,
        ),
        "CT-09/faint_ticks": (36, config.faint_ticks),
        "CT-09/night_recovery": (
            7200,
            min(opening.pack.needs["mental_fatigue"].maximum, 48 * config.recovery_per_tick_asleep),
        ),
        "CT-11/satiety_asleep_decay": (15, satiety.asleep_decay),
        "CT-11/hydration_asleep_decay": (60, hydration.asleep_decay),
    }
    return {
        key: {"published": original, "pack": actual}
        for key, (original, actual) in values.items()
        if original != actual
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--case", action="append", choices=tuple(VECTORS), help="record selected vectors only"
    )
    args = parser.parse_args()
    out: Path = args.out
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=cli.ROOT, text=True
    ).strip()
    demos: dict[str, dict[str, object]] = {}
    for name in dict.fromkeys(args.case or VECTORS):
        vector = VECTORS[name]()
        directory = out / "vectors" / name
        plan = case_plan(vector, revision)
        progress = runtime.run_or_resume(directory, plan, vector.setup)
        evidence = progress.evidence
        assert evidence is not None  # With no limit or pause the recorder completes or raises.
        prefix = directory.relative_to(out).as_posix()
        receipt = directory / "cases" / f"{plan.case_index}.json"
        demos.setdefault(vector.demo, {})[name] = {
            "receipt": receipt.relative_to(out).as_posix(),
            "receipt_sha256": file_digest(receipt),
            "evidence": f"{prefix}/evidence.json",
            "inputs": f"{prefix}/inputs.json",
            "run_id": evidence.run_id,
            "opening_tick": evidence.opening_tick,
            "final_tick": evidence.final_tick,
            "excerpts": list(evidence.observer),
        }
        print(f"{vector.demo} {name} {receipt} {file_digest(receipt)}", flush=True)

    if (
        "CT-08" in demos
        and "spill-admitted" in demos["CT-08"]
        and "spill-blocked" in demos.get("CT-19", {})
    ):
        demos["CT-08"]["spill-after-block-release"] = demos["CT-19"]["spill-blocked"]
    changes = changed_fixed_values()
    if not args.case:
        summary = out / "report.json"
        store_once(
            summary,
            cli.report_bytes(
                {
                    "revision": revision,
                    "demonstrations": demos,
                    "fixed_values_pending_d5": changes,
                }
            ),
        )
        print(f"{summary} {file_digest(summary)}")
    if changes:
        print(f"D5 owner disposition required for changed vectors: {changes}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
