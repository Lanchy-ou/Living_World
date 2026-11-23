"""CT-13 paired verdict over one registered list, including invalid cases."""

from collections import Counter
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any

from living_island.analysis.compare import DIRECTION, arm_report, behavior_variation, paired_report
from living_island.analysis.metrics import rates_of, timing_summaries

from ..receipts import Inputs, Timing
from .measurement import Measurement
from .observations import Arm

ARMS: tuple[Arm, Arm] = ("compat-v1", "starter-v1")


@dataclass
class Case:
    directory: str
    inputs: Inputs
    receipt_sha256: str
    evidence_sha256: str
    timing: Timing
    measured: Measurement

    def details(self) -> dict[str, Any]:
        return {
            "directory": self.directory,
            "case_receipt": f"cases/{self.inputs.plan.case_index}.json",
            "evidence": "evidence.json",
            "timing_db": "progress.sqlite",
            "inputs": self.inputs.model_dump(mode="json"),
            "receipt_sha256": self.receipt_sha256,
            "evidence_sha256": self.evidence_sha256,
            "timing": self.timing.model_dump(mode="json"),
            "metrics": asdict(self.measured.metrics),
            "death_categories": self.measured.summary.death_categories,
            "rates": {
                r.resident_id: {k: asdict(v) for k, v in rates_of(r).items()}
                for r in self.measured.metrics.residents
            },
            "days": self.measured.days,
        }


def aggregate(cases: list[Case]) -> dict[str, Any]:
    summaries = [c.measured.summary for c in cases]
    result = arm_report(summaries)
    residents = [r for s in summaries for r in s.residents]
    days = [d for c in cases for actor in c.measured.days.values() for d in actor]
    times = [r.first_spring_drink_tick for r in residents]
    causes = Counter(r.death_cause for r in residents if r.death_cause is not None)
    awake = sum(d["awake"] for d in days)
    spare = sum(d["non_survival"] for d in days)
    result.update(
        residents=len(residents),
        spring_drinkers=len(times) - times.count(None),
        never_drinkers=times.count(None),
        deaths_by_cause=dict(causes),
        median_first_spring_drink=median(1009 if t is None else t for t in times)
        if times
        else None,
        mean_deprived_ticks=result["totals"]["ticks_deprived"] / len(times) if times else None,
        faints=sum(d["faints"] for d in days),
        unconscious=sum(d["unconscious"] for d in days),
        awake=awake,
        non_survival=spare,
        spare_fraction=spare / awake if awake else None,
        timing_summaries=timing_summaries(residents),
        variation=behavior_variation(summaries),
    )
    result["mean_faints_per_resident_week"] = result["faints"] / len(times) if times else None
    return result


def tolerances(c: dict[str, Any], t: dict[str, Any]) -> dict[str, bool]:
    return {
        "all_alive": t["totals"]["all_alive"] >= c["totals"]["all_alive"] - 1,
        "deprivation": t["totals"]["ticks_deprived"]
        <= c["totals"]["ticks_deprived"] + 24 * t["residents"],
        "spring_access": abs(t["median_first_spring_drink"] - c["median_first_spring_drink"]) <= 12,
        "faints": t["faints"] <= t["residents"],
        "causes": set(t["deaths_by_cause"]) <= set(c["deaths_by_cause"]),
    }


def report(
    seeds: list[int], cases: dict[tuple[int, Arm], Case], failures: dict[str, str], stage: str
) -> dict[str, Any]:
    control, treatment = ARMS
    failures = failures.copy()
    eligible = {}
    for (seed, arm), case in cases.items():
        inputs = case.inputs
        if (
            inputs.seed,
            inputs.plan.arm,
            inputs.content.pack_ids[-1],
            inputs.opening_tick,
            case.measured.metrics.final_tick,
            len(case.measured.metrics.residents),
        ) != (seed, arm, arm, 0, 1008, 3):
            failures[f"{seed}/{arm}"] = "receipt does not cover the registered case"
        else:
            eligible[seed, arm] = case
    for seed in seeds:
        if all((seed, arm) in eligible for arm in ARMS):
            left, right = (eligible[seed, arm] for arm in ARMS)
            if pair_inputs(left) != pair_inputs(right):
                failures[str(seed)] = "pair inputs or resident identities differ"
                del eligible[seed, control], eligible[seed, treatment]
    by_arm = {arm: {s: eligible[s, arm] for s in seeds if (s, arm) in eligible} for arm in ARMS}
    paired = paired_report(
        {s: c.measured.summary for s, c in by_arm[control].items()},
        {s: c.measured.summary for s, c in by_arm[treatment].items()},
        scalars=tuple(DIRECTION),
        expected_seeds=seeds,
    )
    arms = {a: aggregate(list(by_arm[a].values())) for a in ARMS}
    c, t = arms[control], arms[treatment]
    transitions = [
        {
            "seed": s,
            "resident": r,
            "control": v,
            "treatment": cases[s, treatment].measured.summary.access[r],
        }
        for s in seeds
        if all((s, a) in eligible for a in ARMS)
        for r, v in cases[s, control].measured.summary.access.items()
    ]
    valid = len(seeds) == 20 and paired["technical"] == "PASS" and not failures
    tests = tolerances(c, t) if valid else {}
    signal = None if not t["awake"] else 10 * t["non_survival"] >= 3 * t["awake"]
    return {
        "stage": stage,
        "technical": "PASS" if valid else "FAIL",
        "verdict": "PASS" if valid and all(tests.values()) else "FAIL",
        "thresholds": tests,
        "ct_d9_at_least_30_percent": signal,
        "arms": arms,
        "paired": paired,
        "access_by_resident": transitions,
        "failures": failures,
        "cases": {f"{s}/{a}": case.details() for (s, a), case in cases.items()},
        "d1_case": f"{seeds[0]}/{treatment}" if stage == "acceptance" else None,
    }


def pair_inputs(case: Case) -> tuple[object, ...]:
    inputs = case.inputs
    return (
        inputs.seed,
        inputs.config_blob_sha256,
        inputs.effective_config_sha256,
        inputs.map_blob_sha256,
        inputs.map_sha256,
        inputs.content.vocabulary_hash,
        inputs.content.run_id,
        inputs.plan.model_dump(exclude={"arm", "case_index"}),
        sorted(case.measured.summary.access),
    )
