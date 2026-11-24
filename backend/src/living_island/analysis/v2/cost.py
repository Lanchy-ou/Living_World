"""Project measured contexts beside EV-04's reconciled, per-dispatch accounting."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC
from fractions import Fraction
from pathlib import Path

from living_island.agents.v2.calls.guard import Manifest
from living_island.analysis import v2_spend
from living_island.analysis.canon import sha256_hex
from living_island.analysis.v2.continuity import game_day, omitted
from living_island.contract import inspection_v2 as ia


@dataclass(frozen=True)
class Pricing:
    input: int | None
    output: int | None
    unassignable: int | None
    total: int | None
    reason: str | None


def price(row: v2_spend.AttemptRow | None, mode: v2_spend.Mode | None) -> Pricing:
    if mode == "fake":
        return Pricing(0, 0, 0, 0, None)
    if row is None:
        return Pricing(None, None, None, None, "no matching spend ledger")
    t, rate = row.tokens, row.tariff
    total = row.settled_pico
    if row.rated_pico is None or rate is None or t.output is None or total is None:
        return Pricing(None, None, total, total, "missing tariff or reconciled cache usage")
    output = t.output * rate.output_per_million
    if total < row.rated_pico:
        return Pricing(
            None, None, total, total, "settled discount has no recorded input/output allocation"
        )
    return Pricing(row.rated_pico - output, output, total - row.rated_pico, total, None)


def ledger(
    path: Path, run_id: str, calls: dict[str, ia.CallInspection]
) -> tuple[str | None, v2_spend.Mode | None, dict[tuple[str, int], v2_spend.AttemptRow]]:
    if not path.exists():
        return None, None, {}
    raw = path.read_bytes()
    data = v2_spend.project(v2_spend.read_evidence(raw))
    run = next((r for r in data.runs if r.run_id == run_id and r.stage == "resident_run"), None)
    if run is None or {c.call_id for c in run.calls} != calls.keys():
        raise ValueError("spend ledger resident run or call IDs differ from inspection")
    prices = {}
    for c in run.calls:
        actual = calls[c.call_id]
        if c.kind != actual.call_kind or len(c.attempts) != len(actual.attempts):
            raise ValueError("spend ledger attempt count or call kind differs from inspection")
        for a, inspected in zip(c.attempts, actual.attempts, strict=True):
            dispatch, terminal = inspected.dispatch, inspected.terminal
            settings = dispatch.settings
            usage = (
                terminal.tokens.model_dump()
                if terminal
                else dict(input=None, output=None, cache_hit=None, cache_miss=None)
            )
            if (
                a.n != dispatch.n
                or a.request_sha256 != dispatch.request_sha256
                or a.tokens.model_dump() != usage
                or c.model.key != (settings.provider, settings.model, settings.model_version)
                or a.date != dispatch.started_at.astimezone(UTC).date()
            ):
                raise ValueError(
                    "spend ledger dispatch identity, date, model or usage differs from inspection"
                )
            prices[c.call_id, a.n] = a
    return sha256_hex(raw), run.mode, prices


def sections(manifest: Manifest, charge: int | None) -> list[ia.SectionCost]:
    measured: dict[str, int] = {}
    for group in manifest.sections:
        measured[group.section] = measured.get(group.section, 0) + sum(
            e.tokens for e in group.entries
        )
    total = manifest.tokens_total
    # Independent part counts need not be additive after wire framing/tokenization.
    measured["wire framing and tokenization"] = total - sum(measured.values())
    result = []
    cumulative = allocated = 0
    for name, tokens in measured.items():
        cumulative += tokens
        rounded = round(Fraction(charge * cumulative, total)) if charge is not None else None
        result.append(
            ia.SectionCost(
                section=name,
                tokens=tokens,
                share=str(Fraction(tokens, total)),
                estimated_input_pico_cny=rounded - allocated if rounded is not None else None,
            )
        )
        if rounded is not None:
            allocated = rounded
    return result


def sum_known(values: Iterable[int | None]) -> int | None:
    result = 0
    for n in values:
        if n is None:
            return None
        result += n
    return result


def context_cost(
    directory: Path,
    run_id: str,
    calls: dict[str, ia.CallInspection],
    charges: list[ia.Charge],
    decisions: list[ia.DecisionRecord],
    tick_minutes: int,
) -> ia.Cost:
    digest, mode, prices = ledger(directory / "sanitized-evidence.json", run_id, calls)
    by_turn = {d.turn_id: d for d in decisions}
    stages = {stage.call_id: stage for d in decisions for stage in d.telemetry.stages}
    order = {key: i for d in decisions for i, key in enumerate(d.call_ids)}
    rows = []
    previous: dict[tuple[str, str], int] = {}
    for call in sorted(
        calls.values(), key=lambda c: (c.call.tick, order.get(c.call.call_id, -1), c.call.call_id)
    ):
        c = call.call
        d = by_turn.get(c.turn_id or "")
        full = call.full_manifest
        log_tokens = (
            sum(
                e.tokens
                for group in full.sections
                if group.section == "day_log"
                for e in group.entries
            )
            if full
            else None
        )
        growth = None
        if call.call_kind in ("decision", "decision_after_recall") and log_tokens is not None:
            key = (c.resident_id, c.period_id)
            growth = log_tokens - previous.get(key, 0)
            previous[key] = log_tokens
        stage = stages.get(c.call_id)
        band = (
            stage.pressure_band
            if stage
            else full.derived[0].band
            if full and full.derived
            else None
        )
        logical_attempts: Iterable[ia.Attempt | None] = call.attempts or (None,)
        for attempt in logical_attempts:
            sent = attempt.dispatch.sent.manifest if attempt else None
            n = attempt.dispatch.n if attempt else None
            money = (
                price(prices.get((c.call_id, n)), mode)
                if n is not None
                else Pricing(0, 0, 0, 0, "no dispatch")
            )
            outcome = (
                "no dispatch"
                if not attempt
                else "interrupted"
                if not attempt.terminal
                else attempt.terminal.error_class or "returned"
            )
            rows.append(
                ia.ContextCost(
                    resident_id=c.resident_id,
                    period_id=c.period_id,
                    tick=c.tick,
                    day=game_day(c.tick, tick_minutes),
                    turn_id=c.turn_id,
                    call_id=c.call_id,
                    call_kind=call.call_kind,
                    outcome=call.outcome,
                    n=n,
                    attempt_outcome=outcome,
                    full_tokens=full.tokens_total if full else None,
                    sent_tokens=sent.tokens_total if sent else None,
                    full_log_tokens=log_tokens,
                    log_growth_tokens=growth,
                    pressure_band=band,
                    omitted=omitted(call),
                    fallback=d.fallback.used if d else None,
                    sections=sections(sent, money.input) if sent else [],
                    input_pico_cny=money.input,
                    output_pico_cny=money.output,
                    unassignable_pico_cny=money.unassignable,
                    paid_pico_cny=money.total,
                    cost_reason=money.reason,
                )
            )
    usage = {(r.call_id, r.n): r for r in charges}
    days = []
    groups: defaultdict[tuple[str, int], list[ia.ContextCost]] = defaultdict(list)
    turns: defaultdict[tuple[str, int], list[ia.DecisionRecord]] = defaultdict(list)
    for d in decisions:
        turns[d.resident_id, game_day(d.tick, tick_minutes)].append(d)
    for row in rows:
        groups[row.resident_id, row.day].append(row)
    for actor, day in sorted(groups.keys() | turns.keys()):
        group = groups[actor, day]
        attempts = [usage[r.call_id, r.n] for r in group if r.n is not None]
        choices = turns[actor, day]
        fallbacks = sum(d.fallback.used for d in choices)
        days.append(
            ia.DailyCost(
                resident_id=actor,
                day=day,
                calls=len({r.call_id for r in group}),
                attempts=len(attempts),
                turns=len(choices),
                fallback_turns=fallbacks,
                fallback_rate=str(Fraction(fallbacks, len(choices))) if choices else None,
                input_tokens=sum_known(a.input for a in attempts),
                output_tokens=sum_known(a.output for a in attempts),
                cache_hit=sum_known(a.cache_hit for a in attempts),
                cache_miss=sum_known(a.cache_miss for a in attempts),
                latency_ms=sum_known(a.latency_ms for a in attempts),
                input_pico_cny=sum_known(r.input_pico_cny for r in group),
                output_pico_cny=sum_known(r.output_pico_cny for r in group),
                unassignable_pico_cny=sum_known(r.unassignable_pico_cny for r in group),
                paid_pico_cny=sum_known(r.paid_pico_cny for r in group),
            )
        )
    return ia.Cost(
        attempts=charges,
        contexts=rows,
        days=days,
        ledger_mode=mode,
        ledger_sha256=digest,
        turns=[
            ia.TurnCost(
                resident_id=d.resident_id,
                turn_id=d.turn_id,
                day=game_day(d.tick, tick_minutes),
                tick=d.tick,
                period_id=d.period_id,
                call_ids=d.call_ids,
                fallback=d.fallback,
                fatigue_band=d.telemetry.fatigue_band,
                awake_ticks=d.telemetry.awake_ticks,
            )
            for d in decisions
        ],
    )
