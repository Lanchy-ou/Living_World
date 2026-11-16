"""Pure P3 evaluation arithmetic and read-only P2 physical metric adaptation.

No provider, file, authority, policy or runtime access belongs in this module.
Technical checks and behavioral summaries are intentionally separate outputs.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any, cast

from living_island.contract.p3_inspection import (
    ActionPlan,
    AllocationEntry,
    BudgetCaps,
    CallDebit,
    DecisionInspection,
    DecisionRecordP3,
    ResidentInspection,
    canonical_sha256,
)
from living_island.contract.p3_save import TrialRegistration
from living_island.contract.replay import ReplayBundle

from .compare import DIRECTION, death_categories, run_scalars
from .data import RunData, RunLimits
from .metrics import compute_run, number
from .validity import frame_problems

RULE_TREE = "837f2f90f6b242477e43c25aec9b359ec51ba331"
WORLD_COMMIT = "7c13d78ffd7d89006f6008c8a09f37ae97c253db"


def fraction(numerator: int, denominator: int) -> dict[str, int | str | None]:
    if numerator < 0 or denominator < 0:
        raise ValueError("fractions require nonnegative counts")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else f"{numerator}/{denominator}",
    }


def usage_summary(debits: Sequence[CallDebit]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("input", "output"):
        values = [getattr(d, f"{name}_reported") for d in debits]
        missing = sum(v is None for v in values)
        known = sum(v for v in values if v is not None)
        result[name] = {
            "reported_total": None if missing else known,
            "known_subtotal": known,
            "missing_count": missing,
            "charged_total": sum(getattr(d, f"{name}_charged") for d in debits),
        }
    result["cost_ceiling_micro_cny"] = sum(d.money_charged for d in debits)
    result["unknown_usage_share"] = fraction(sum(d.usage_unknown for d in debits), len(debits))
    return result


def latency_summary(values: Sequence[int | None]) -> dict[str, Any]:
    known = sorted(v for v in values if v is not None)
    count = len(known)
    return {
        "count": count,
        "missing_latency_count": len(values) - count,
        "min": min(known) if known else None,
        "max": max(known) if known else None,
        "median": None
        if not count
        else number(Fraction(known[(count - 1) // 2] + known[count // 2], 2)),
        "p95": known[(95 * count + 99) // 100 - 1] if count else None,
    }


def _shares(records: Sequence[DecisionRecordP3], *, applicable: bool) -> dict[str, Any]:
    llm = [r for r in records if r.policy_id == "llm-v0"]
    accepted = sum(r.effective_policy_id == "llm-v0" and r.status == "ok" for r in llm)
    fallback = sum(r.effective_policy_id == "rule-based-v0" for r in llm)
    wait = sum(r.effective_policy_id == "sim-fallback-wait" for r in llm)
    return {
        "llm_decision_count": len(llm),
        "accepted_count": accepted,
        "fallback_count": fallback,
        "wait_count": wait,
        "llm_accepted_share": fraction(accepted, len(llm)),
        "fallback_share": fraction(fallback, len(llm)),
        "wait_share": fraction(wait, len(llm)),
        "retry_share": fraction(sum(len(r.call_ids) > 1 for r in llm), len(llm)),
        "context_oversize_share": fraction(
            sum(r.detail_code == "MANDATORY_OVERSIZE" for r in llm), len(llm)
        ),
        "input_limit_count": sum(r.detail_code == "INPUT_LIMIT" for r in llm),
        "v05": "NOT_APPLICABLE"
        if not applicable
        else ("PASS" if llm and accepted * 5 >= 4 * len(llm) and wait == 0 else "FAIL"),
    }


def goal_metrics(
    decisions: Sequence[DecisionInspection], samples: Sequence[ResidentInspection]
) -> dict[str, Any]:
    operations: Counter[str] = Counter({"continue": 0, "revise": 0, "abandon": 0})
    created: set[str] = set()
    retired: set[str] = set()
    references: dict[str, tuple[DecisionRecordP3, str | None]] = {}
    violations: list[str] = []
    for shard in decisions:
        record = shard.record
        change = record.accepted_delta.goal_change
        before = shard.context.request.context.goals
        operations[change.operation] += 1
        old = before.current
        attached = None if old is None or old.status == "observed_complete" else old.goal_id
        if change.operation in ("revise", "abandon") and old is not None:
            retired.add(old.goal_id)
        if change.operation == "revise":
            attached = f"{record.actor_id}:g{before.next_goal_sequence:06d}"
            if attached in created:
                violations.append(f"duplicate creation:{attached}")
            created.add(attached)
        elif change.operation == "abandon":
            attached = None
        for intent in record.plan.intents:
            references[intent.intent_id] = (record, attached)
    completed: dict[str, dict[str, Any]] = {}
    observations = [(s.tick, s.actor_id, "checkpoint", s.goals) for s in samples]
    observations += [
        (d.record.tick, d.record.actor_id, d.record.decision_id, d.context.request.context.goals)
        for d in decisions
    ]
    for tick, actor, source, goals in sorted(
        observations, key=lambda row: (row[0], row[1], row[2])
    ):
        goal = goals.current
        if goal is None or goal.status != "observed_complete":
            continue
        evidence = goal.evidence
        if evidence is None or goal.goal_id not in created:
            violations.append(f"unlinked completion:{goal.goal_id}")
            continue
        ref = evidence.owned_intent
        linked = references.get(ref.intent.intent_id)
        valid = linked is not None
        if linked is not None:
            record, attached = linked
            valid = (
                record.actor_id == actor
                and ref.decision_id == record.decision_id
                and ref.decision_ordinal == record.decision_ordinal
                and ref.committed_tick == record.tick
                and ref.intent in record.plan.intents
                and ref.goal_id == goal.goal_id == attached
                and evidence.delivery_id
                == f"{record.run_id}:perception:{evidence.observed_tick:010d}:{actor}"
                and evidence.feedback.intent_id == ref.intent.intent_id
                and evidence.feedback.status == "success"
                and goal.created_at_tick <= ref.committed_tick < evidence.observed_tick <= tick
            )
        predicate = goal.completion
        if predicate.kind != "own_action_success":
            valid = False
        else:
            valid = valid and (predicate.action_type, predicate.target, predicate.parameters) == (
                ref.intent.action_type,
                ref.intent.target,
                ref.intent.parameters,
            )
        if not valid:
            violations.append(f"invalid completion source:{goal.goal_id}")
            continue
        previous = completed.get(goal.goal_id)
        item = {
            "goal_id": goal.goal_id,
            "actor_id": actor,
            "observed_in": source,
            "tick": tick,
            "evidence": evidence.model_dump(mode="json"),
        }
        if previous is not None and previous["evidence"] != item["evidence"]:
            violations.append(f"changed terminal evidence:{goal.goal_id}")
        else:
            completed.setdefault(goal.goal_id, item)
    final_tick = max((s.tick for s in samples), default=-1)
    active = {
        s.goals.current.goal_id
        for s in samples
        if s.tick == final_tick and s.goals.current is not None
    }
    return {
        "goal_transitions": dict(operations),
        "created_count": len(created),
        "completed_count": len(completed),
        "goal_completion_share": fraction(len(completed), len(created)),
        "retired_incomplete_count": len(retired - completed.keys()),
        "active_incomplete_count": len(active - completed.keys()),
        "completions": list(completed.values()),
        "evidence_violations": len(violations),
        "evidence_errors": violations,
    }


def evaluate_cognition(
    decisions: Sequence[DecisionInspection],
    samples: Sequence[ResidentInspection],
    *,
    llm_actor_ids: Sequence[str],
    recovery_debits: Sequence[CallDebit] = (),
    missing_sources: Sequence[str] = (),
    expected_tick: int | None = None,
) -> dict[str, Any]:
    missing = list(missing_sources)
    if expected_tick is not None and max((s.tick for s in samples), default=-1) != expected_tick:
        missing.append("registered final boundary")
    if missing:
        return {"technical": "FAIL", "missing_sources": sorted(set(missing)), "metrics": None}
    records = [s.record for s in decisions]
    if len({r.decision_id for r in records}) != len(records):
        raise ValueError("duplicate committed decision ID")
    if any((r.policy_id == "llm-v0") != (r.actor_id in llm_actor_ids) for r in records):
        raise ValueError("decision primary differs from registered actor assignment")
    llm = [s for s in decisions if s.record.actor_id in llm_actor_ids]
    calls = [c for s in llm for c in s.calls]
    if len({c.call_id for c in calls}) != len(calls):
        raise ValueError("duplicate dispatched call ID")
    actors = sorted({s.actor_id for s in samples} | set(llm_actor_ids))
    per_actor = {
        actor: _shares(
            [r for r in records if r.actor_id == actor], applicable=actor in llm_actor_ids
        )
        for actor in actors
    }
    goals = goal_metrics(decisions, samples)
    manifests = []
    for shard in llm:
        manifest = shard.context.assembly.manifest
        manifests.append(
            {
                "decision_id": shard.record.decision_id,
                "evicted_record_count": manifest.evicted_record_count,
                "omissions": dict(Counter(e.omission for e in manifest.experiences if e.omission)),
                "static_tile_omissions": dict(
                    Counter(e.omission for e in manifest.static_tiles if e.omission)
                ),
            }
        )
    projected = sum(e.projected for s in llm for e in s.context.assembly.manifest.experiences)
    retrieved = sum(e.retrieved for s in llm for e in s.context.assembly.manifest.experiences)
    debits = [c.debit for c in calls]
    usage = usage_summary(debits)
    recovery = usage_summary(recovery_debits)
    metrics = {
        **_shares(records, applicable=bool(llm_actor_ids)),
        "per_actor": per_actor,
        "decision_count": len(records),
        "dispatched_attempt_count": len(calls),
        "deliberate_rule_count": sum(r.policy_id == "rule-based-v0" for r in records),
        "rejection_share": fraction(
            sum(
                c.validation_error in {"PARSE_ERROR", "INVALID_PLAN", "INVALID_DELTA"}
                for c in calls
            ),
            len(calls),
        ),
        "errors_by_enum": dict(Counter(c.validation_error for c in calls if c.validation_error)),
        "usage": usage,
        "recovery_debits": recovery,
        "charged_tokens": {
            "input": usage["input"]["charged_total"] + recovery["input"]["charged_total"],
            "output": usage["output"]["charged_total"] + recovery["output"]["charged_total"],
        },
        "cost_ceiling_micro_cny": usage["cost_ceiling_micro_cny"]
        + recovery["cost_ceiling_micro_cny"],
        "latency_ms": latency_summary([c.result.latency_ms for c in calls]),
        "retrieval_inclusion_share": fraction(projected, retrieved),
        "manifests": manifests,
        **goals,
    }
    metrics["v05"] = (
        "NOT_APPLICABLE"
        if not llm_actor_ids
        else "PASS"
        if all(per_actor[a]["v05"] == "PASS" for a in llm_actor_ids)
        and goals["evidence_violations"] == 0
        else "FAIL"
    )
    return {
        "technical": "FAIL" if goals["evidence_violations"] else "PASS",
        "missing_sources": [],
        "metrics": metrics,
    }


@dataclass(frozen=True)
class AcceptedPlanView:
    """Only the four fields consumed by frozen P2 physical calculations."""

    actor_id: str
    tick: int
    decision_ordinal: int
    plan: ActionPlan


def physical_metrics(
    replay: ReplayBundle, records: Sequence[DecisionRecordP3], limits: RunLimits
) -> dict[str, Any]:
    violations = frame_problems(tuple(replay.frames), tuple(replay.events), limits)
    if violations:
        raise ValueError(f"P3 replay violates frozen physical invariants: {violations}")
    # RunData is a read-only indexing container. Its legacy annotation predates
    # structural plan views; no DecisionRecord is fabricated or serialized here.
    plans = tuple(AcceptedPlanView(r.actor_id, r.tick, r.decision_ordinal, r.plan) for r in records)
    data = RunData(
        replay.run_id, replay.frames, replay.events, cast(Any, plans), replay.map.rows, limits
    )
    result = compute_run(data)
    return {
        "metrics": asdict(result),
        "scalars": run_scalars(result),
        "death_categories": death_categories(data, result),
    }


def matched_comparison(
    registration: TrialRegistration, cases: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    omitted = []
    pairs = []
    controls = {c.paired_case_id: c for c in registration.controls}
    if len(controls) != len(registration.controls):
        raise ValueError("duplicate registered control pairing")
    if set(controls) - {case.case_id for case in registration.cases}:
        raise ValueError("control references an unregistered P3 case")
    for case in registration.cases:
        control = controls.get(case.case_id)
        p3 = cases.get(case.case_id)
        base = None if control is None else cases.get(control.case_id)
        reason = None
        if control is None:
            reason = "missing registered control"
        elif p3 is None or base is None:
            reason = "missing arm"
        elif p3.get("technical") != "PASS" or base.get("technical") != "PASS":
            reason = "invalid arm"
        elif (
            base.get("rule_tree") != RULE_TREE
            or base.get("seed") != case.seed
            or p3.get("seed") != case.seed
            or base.get("ticks") != case.ticks
            or p3.get("ticks") != case.ticks
            or base.get("world_inputs") != p3.get("world_inputs")
        ):
            reason = "unmatched world/horizon/frozen rule identity"
        if reason is not None:
            omitted.append({"seed": case.seed, "reason": reason})
        else:
            assert p3 is not None and base is not None
            pairs.append((case.seed, p3, base))
    scalars: dict[str, Any] = {}
    for name, direction in DIRECTION.items():
        differences = [
            (seed, int(p3["scalars"][name]) - int(base["scalars"][name]))
            for seed, p3, base in pairs
        ]
        values = sorted(d for _, d in differences)
        n = len(values)
        item: dict[str, Any] = {
            "differences": [{"seed": s, "difference": d} for s, d in differences],
            "median": None if not n else number(Fraction(values[(n - 1) // 2] + values[n // 2], 2)),
            "min": min(values) if n else None,
            "max": max(values) if n else None,
        }
        if direction is not None:
            item.update(
                favorable=sum(d < 0 if direction == "lower" else d > 0 for d in values),
                unfavorable=sum(d > 0 if direction == "lower" else d < 0 for d in values),
                tied=sum(d == 0 for d in values),
            )
        scalars[name] = item
    return {
        "technical": "PASS" if registration.cases and not omitted else "FAIL",
        "pairs_expected": len(registration.cases),
        "pairs_used": len(pairs),
        "omitted": omitted,
        "scalars": scalars,
        "interpretation": "Descriptive differences; no significance or general survival claim.",
    }


@dataclass(frozen=True)
class ExpectedAllocation:
    registration_sha256: str
    case_id: str
    purpose: str
    seed: int
    caps: BudgetCaps

    @property
    def allocation_key(self) -> str:
        return canonical_sha256(
            {"registration_sha256": self.registration_sha256, "case_id": self.case_id}
        )


@dataclass(frozen=True)
class AllocationEvidence(ExpectedAllocation):
    entries: tuple[AllocationEntry, ...]
    completed_trace_sha256: str | None


@dataclass(frozen=True)
class VerifiedIssuance:
    """Read-only facts from an externally anchored archive, never a spending grant.

    The I/O boundary verifies canonical owner snapshots and all predecessor links.
    Pure arithmetic cannot authenticate an arbitrary caller-supplied key mapping.
    """

    owner_evidence_sha256: str
    slots: tuple[tuple[str, tuple[str, ...]], ...]


SLOTS = (
    ("smoke", 1292387875, (48, 1572864, 98304, 5000000)),
    ("development", 509071611, (288, 9437184, 589824, 20000000)),
    ("development", 1945790632, (288, 9437184, 589824, 20000000)),
    ("acceptance", 401604645, (864, 28311552, 1769472, 35000000)),
    ("acceptance", 4054202024, (864, 28311552, 1769472, 35000000)),
    ("acceptance", 538041037, (864, 28311552, 1769472, 35000000)),
)


def allocation_accounting(
    evidence: Sequence[AllocationEvidence],
    *,
    authorizations: Mapping[str, Sequence[str]] | None = None,
    expected: Sequence[ExpectedAllocation] = (),
    issuance: VerifiedIssuance | None = None,
) -> dict[str, Any]:
    """Deduplicate retained evidence; explicit immutable approval mirrors are required.

    authorizations maps 'purpose:seed' to the approved original, CR-007 and
    CR-008 allocation keys in issuance order. It is never a grant or live lookup.
    """
    known_slots = {f"{purpose}:{seed}" for purpose, seed, _ in SLOTS}
    if issuance is not None:
        if authorizations is not None:
            raise ValueError("raw authorization mappings cannot accompany verified issuance")
        authorizations = dict(issuance.slots)
        if len(issuance.slots) != len(known_slots) or set(authorizations) != known_slots:
            raise ValueError("verified issuance must describe all six slots")
        anchor = issuance.owner_evidence_sha256
        if len(anchor) != 64 or any(c not in "0123456789abcdef" for c in anchor):
            raise ValueError("verified issuance requires its external digest anchor")
    inventory: dict[str, ExpectedAllocation] = {}
    for item in expected:
        previous = inventory.setdefault(item.allocation_key, item)
        if previous != item:
            raise ValueError("conflicting expected allocation identity")
    if authorizations is not None and set(authorizations) - known_slots:
        raise ValueError("unknown authorization slot")
    grouped: dict[str, AllocationEvidence] = {}
    entries: dict[tuple[str, int], AllocationEntry] = {}
    completed: dict[str, str] = {}
    errors: list[str] = []
    for item in evidence:
        key = item.allocation_key
        prior = grouped.get(key)
        if prior is not None and (prior.caps, prior.purpose, prior.seed) != (
            item.caps,
            item.purpose,
            item.seed,
        ):
            raise ValueError("conflicting allocation metadata")
        expected_item = inventory.get(key)
        if expected_item is not None and (
            expected_item.purpose,
            expected_item.seed,
            expected_item.caps,
        ) != (item.purpose, item.seed, item.caps):
            raise ValueError("allocation differs from expected registration")
        grouped[key] = item
        if item.completed_trace_sha256 is not None:
            if key in completed and completed[key] != item.completed_trace_sha256:
                raise ValueError("competing completed lineages for one allocation")
            completed[key] = item.completed_trace_sha256
        for entry in item.entries:
            reservation = entry.reservation
            if reservation.allocation_key != key:
                raise ValueError("foreign reservation in allocation mirror")
            identity = (key, reservation.reservation_ordinal)
            if identity in entries and entries[identity] != entry:
                raise ValueError("conflicting copied reservation evidence")
            entries[identity] = entry
    totals: dict[str, tuple[int, int, int, int]] = {}
    rows = []
    for key, item in grouped.items():
        mine = [entry for (allocation, _), entry in sorted(entries.items()) if allocation == key]
        if [e.reservation.reservation_ordinal for e in mine] != list(range(len(mine))):
            errors.append(f"missing reservation ordinal:{key}")
        if any(e.debit is None for e in mine):
            errors.append(f"unsettled reservation:{key}")
        # Pending entries retain their conservative reservation, never zero cost.
        charged = (
            len(mine),
            sum(e.debit.input_charged if e.debit else e.reservation.input_reserved for e in mine),
            sum(e.debit.output_charged if e.debit else e.reservation.output_reserved for e in mine),
            sum(e.debit.money_charged if e.debit else e.reservation.money_reserved for e in mine),
        )
        if item.purpose == "fake" and (item.caps.micro_cny != 0 or charged[3] != 0):
            errors.append(f"fake allocation must have zero money:{key}")
        totals[key] = charged
        caps = tuple(item.caps.model_dump().values())
        if any(a > b for a, b in zip(charged, caps, strict=True)):
            errors.append(f"allocation overrun:{key}")
        rows.append(
            {
                "allocation_key": key,
                "case_id": item.case_id,
                "registration_sha256": item.registration_sha256,
                "charged": dict(
                    zip(
                        ("attempts", "input_tokens", "output_tokens", "micro_cny"),
                        charged,
                        strict=True,
                    )
                ),
                "unknown_usage_count": sum(
                    e.debit is not None and e.debit.usage_unknown for e in mine
                ),
                "unsettled_count": sum(e.debit is None for e in mine),
                "reported_usage": usage_summary([e.debit for e in mine if e.debit is not None]),
                "evidence_status": "COMPLETE" if key in completed else "INCOMPLETE",
                "missing_sources": [] if key in completed else ["verified completed lineage"],
            }
        )
    missing = set(inventory) - set(completed)
    for key in sorted(missing):
        errors.append(f"missing verified allocation completion:{key}")
        if key not in grouped:
            item = inventory[key]
            rows.append(
                {
                    "allocation_key": key,
                    "case_id": item.case_id,
                    "registration_sha256": item.registration_sha256,
                    "charged": None,
                    "unknown_usage_count": None,
                    "unsettled_count": None,
                    "reported_usage": None,
                    "evidence_status": "MISSING",
                    "missing_sources": ["verified allocation/receipt/run evidence"],
                }
            )
    live = {k: v for k, v in grouped.items() if v.purpose != "fake"}
    live_required = bool(live) or any(item.purpose != "fake" for item in inventory.values())
    if live_required and issuance is None:
        errors.append("missing immutable authorization evidence")
    slots = []
    authorized_keys: set[str] = set()
    for purpose, seed, approved_caps in SLOTS:
        slot = f"{purpose}:{seed}"
        keys = list((authorizations or {}).get(slot, ()))
        if len(keys) != len(set(keys)) or any(k in authorized_keys for k in keys):
            raise ValueError("copied allocation cannot authorize a fresh slot")
        authorized_keys.update(keys)
        if len(keys) > (3 if purpose == "smoke" else 1):
            errors.append(f"too many issued allocations:{slot}")
        envelope = (50, *approved_caps[1:]) if len(keys) == 3 else approved_caps
        earlier = [0, 0, 0, 0]
        for index, key in enumerate(keys):
            bound = grouped.get(key)
            if bound is None:
                errors.append(f"missing approved allocation evidence:{key}")
                continue
            if (bound.purpose, bound.seed) != (purpose, seed):
                errors.append(f"allocation bound to wrong slot:{key}")
            caps = tuple(bound.caps.model_dump().values())
            if index == 0 and caps != approved_caps:
                errors.append(f"original slot caps differ:{key}")
            if issuance is not None and index == 1 and caps != (34, 1114112, 69632, 2785280):
                errors.append(f"CR-007 caps differ:{key}")
            if index == 2 and caps != (34, 1114112, 69275, 3000000):
                errors.append(f"CR-008 caps differ:{key}")
            stage_envelope = envelope if index == 2 else approved_caps
            if any(
                a + b > limit for a, b, limit in zip(earlier, caps, stage_envelope, strict=True)
            ):
                errors.append(f"settled prior debits plus new caps exceed envelope:{key}")
            if index < len(keys) - 1 and key not in completed:
                errors.append(f"linked replacement lacks completed predecessor:{key}")
            earlier = [a + b for a, b in zip(earlier, totals[key], strict=True)]
        slots.append(
            {
                "slot": slot,
                "allocation_keys": keys,
                "approved_micro_cny": approved_caps[3],
                "issuance_status": ("ISSUED" if keys else "UNISSUED")
                if issuance is not None
                else "UNKNOWN",
            }
        )
    for key in live:
        if key not in authorized_keys:
            errors.append(f"allocation lacks slot authorization:{key}")
    total = sum(t[3] for key, t in totals.items() if grouped[key].purpose != "fake")
    if total > 150000000:
        errors.append("aggregate CNY150 ceiling exceeded")
    return {
        "technical": "FAIL" if errors or (live_required and issuance is None) else "PASS",
        "arithmetic_status": "FAIL"
        if any(
            not e.startswith("missing immutable authorization")
            and not e.startswith("allocation lacks slot authorization")
            for e in errors
        )
        else "PASS",
        "issuance_proof": "VERIFIED_ARCHIVE"
        if issuance is not None
        else ("MISSING" if live_required else "NOT_APPLICABLE"),
        "owner_evidence_sha256": None if issuance is None else issuance.owner_evidence_sha256,
        "errors": errors,
        "allocations": rows,
        "slots": slots,
        "cost_ceiling_micro_cny": None
        if (missing or (live_required and issuance is None) or authorized_keys - set(completed))
        else total,
        "known_subtotal_micro_cny": total,
        "evidence_complete": not missing
        and (not live_required or issuance is not None)
        and not (authorized_keys - set(completed)),
        "approved_ceiling_micro_cny": 150000000,
        "scope": (
            "Conservative charges in the supplied evidence snapshot; "
            "not current spendable balance or new authorization. "
            "UNISSUED applies only at that anchored snapshot."
        ),
        "actual_supplier_bill_micro_cny": None,
    }
