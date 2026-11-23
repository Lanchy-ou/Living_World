"""Project P3.5 spend from sanitized, local evidence."""

import argparse
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date
from html import escape
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

PICO_PER_CNY = 10**12
CAP_PICO = 20 * PICO_PER_CNY

type Kind = Literal[
    "decision",
    "decision_after_recall",
    "recall",
    "morning",
    "consolidation_selection",
    "consolidation_change_set",
]
type Stage = Literal["provider_check", "resident_run"]
type Mode = Literal["paid", "fake"]
type Count = Annotated[int, Field(strict=True, ge=0)]
type Positive = Annotated[int, Field(strict=True, gt=0)]
type Label = Annotated[str, Field(min_length=1, pattern=r"\S")]
type Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _scaled_decimal(value: object, places: int) -> int:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9]+(?:\.[0-9]{{1,{places}}})?", value):
        raise ValueError(f"expected a nonnegative decimal string with up to {places} places")
    whole, _, fraction = value.partition(".")
    return int(whole + fraction.ljust(places, "0"))


def _pico(value: object) -> int:
    return _scaled_decimal(value, 12)


def _rate(value: object) -> int:
    # CNY per million tokens to pico-CNY per token.
    return _scaled_decimal(value, 6)


type Money = Annotated[int, BeforeValidator(_pico)]
type Rate = Annotated[int, BeforeValidator(_rate)]


class _Input(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Fact(BaseModel):
    """Read only accounting fields from DL-01 facts, without importing its provider."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class _Pin(_Fact):
    provider: Label
    model: Label
    model_version: Label

    @property
    def key(self) -> tuple[str, str, str]:
        return self.provider, self.model, self.model_version


class _Settings(_Pin):
    max_output_tokens: Count


class _Call(_Fact):
    call_id: Label


class _Manifest(_Fact):
    call_kind: Kind
    tokens_total: Count


class _Candidate(_Fact):
    manifest: _Manifest


class _Prepared(_Fact):
    call: _Call
    settings: _Pin
    candidates: Annotated[tuple[_Candidate, ...], Field(min_length=1)]
    reason: Literal["stopped_unfit"] | None


class _Dispatch(_Fact):
    call: _Call
    n: Count
    request_sha256: Hash
    sent: _Candidate
    settings: _Settings
    started_at: AwareDatetime


class _Usage(_Fact):
    input: Count | None = None
    output: Count | None = None
    cache_hit: Count | None = None
    cache_miss: Count | None = None


class _Terminal(_Fact):
    call_id: Label
    n: Count
    dispatch_cursor: Label
    request_sha256: Hash
    error_class: (
        Literal["timeout", "rate_limit", "server_error", "provider_error", "invalid_output"] | None
    )
    tokens: _Usage


class _Opening(_Input):
    settled_cny: Money | None
    source: Label | None

    @model_validator(mode="after")
    def evidence_for_amount(self) -> Self:
        if self.settled_cny is not None and self.source is None:
            raise ValueError("opening balance requires evidence")
        return self


class _Tariff(_Pin):
    model_config = ConfigDict(extra="forbid")

    effective_on: date
    through: date
    source: Label
    model_evidence: Label
    cache_hit_per_million: Rate
    cache_miss_per_million: Rate
    output_per_million: Rate
    peak_cache_miss_per_million: Rate
    peak_output_per_million: Rate

    @model_validator(mode="after")
    def usable_peak(self) -> Self:
        if self.through < self.effective_on or (
            self.peak_cache_miss_per_million
            < max(self.cache_hit_per_million, self.cache_miss_per_million)
            or self.peak_output_per_million < self.output_per_million
        ):
            raise ValueError("tariff dates or peak rates are inconsistent")
        return self

    def reserve(self, input_bound: int, output_bound: int) -> int:
        return input_bound * self.peak_cache_miss_per_million + (
            output_bound * self.peak_output_per_million
        )


class _Undispatched(_Pin):
    model_config = ConfigDict(extra="forbid")

    call_id: Label
    kind: Kind


class _Charge(_Input):
    call_id: Label
    n: Count
    source: Label
    provider_cny: Money | None = None
    invoice_cny: Money | None = None

    @model_validator(mode="after")
    def evidence_has_charge(self) -> Self:
        if self.provider_cny is None and self.invoice_cny is None:
            raise ValueError("charge evidence requires an attributed amount")
        return self


class _RunInput(_Input):
    stage: Stage
    mode: Mode
    date: date
    prepared: tuple[_Prepared, ...] = ()
    dispatches: tuple[_Dispatch, ...] = ()
    terminals: tuple[_Terminal, ...] = ()
    abandoned: frozenset[Label] = frozenset()
    undispatched: tuple[_Undispatched, ...] = ()
    charges: tuple[_Charge, ...] = ()


class _PlanRow(_Input):
    day: Positive | None
    kind: Kind
    n: Count
    count: Positive
    input_bound: Count | None
    output_bound: Count | None
    central_cny: Money | None


class _Plan(_Pin):
    model_config = ConfigDict(extra="forbid")

    stage: Stage
    date: date
    rows: Annotated[tuple[_PlanRow, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def dated_days(self) -> Self:
        if any((row.day is None) != (self.stage == "provider_check") for row in self.rows):
            raise ValueError("game days belong to the resident run")
        days = sorted({row.day for row in self.rows if row.day is not None})
        if any(day != first + 1 for first, day in pairwise(days)):
            raise ValueError("forecast game days must be consecutive")
        return self


class _Bundle(_Input):
    opening: _Opening
    tariffs: tuple[_Tariff, ...] = ()
    runs: dict[Label, _RunInput]
    plan: _Plan | None = None


@dataclass(frozen=True)
class _AttemptFacts:
    dispatch: _Dispatch
    terminal: _Terminal | None
    charge: _Charge | None


@dataclass
class _CallFacts:
    kind: Kind
    pin: _Pin
    outcome: str
    attempts: list[_AttemptFacts] = field(default_factory=list)


@dataclass(frozen=True)
class _RunFacts:
    run_id: str
    stage: Stage
    mode: Mode
    date: date
    calls: dict[str, _CallFacts]


@dataclass(frozen=True)
class Evidence:
    opening: _Opening
    tariffs: dict[tuple[str, str, str], tuple[_Tariff, ...]]
    runs: tuple[_RunFacts, ...]
    plan: _Plan | None


def _index[K, V](facts: Iterable[V], key: Callable[[V], K], name: str) -> dict[K, V]:
    indexed: dict[K, V] = {}
    for fact in facts:
        if indexed.setdefault(key(fact), fact) != fact:
            raise ValueError(f"conflicting {name} records for the same identity")
    return indexed


def _dispatch_cursor(call_id: str, n: int) -> str:
    # DL-01 Journal.cursor in the run's flat namespace.
    return f"{hashlib.sha256(call_id.encode()).hexdigest()}.{n}.dispatch.json"


def _join_run(run_id: str, run: _RunInput) -> _RunFacts:
    prepared = _index(run.prepared, lambda fact: fact.call.call_id, "prepared")
    dispatched = _index(run.dispatches, lambda fact: (fact.call.call_id, fact.n), "dispatch")
    terminals = _index(run.terminals, lambda fact: (fact.call_id, fact.n), "terminal")
    charges = _index(run.charges, lambda fact: (fact.call_id, fact.n), "charge")
    undispatched = _index(run.undispatched, lambda fact: fact.call_id, "undispatched call")
    if (terminals.keys() | charges.keys()) - dispatched.keys():
        raise ValueError("terminal or charge has no durable dispatch")
    calls = {
        call_id: _CallFacts(
            fact.candidates[0].manifest.call_kind, fact.settings, fact.reason or "prepared"
        )
        for call_id, fact in prepared.items()
    }
    for call_id, metadata in undispatched.items():
        if call_id in calls:
            raise ValueError("undispatched metadata duplicates a prepared call")
        calls[call_id] = _CallFacts(metadata.kind, metadata, "undispatched")
    for (call_id, n), fact in sorted(dispatched.items()):
        kind = fact.sent.manifest.call_kind
        call = calls.setdefault(call_id, _CallFacts(kind, fact.settings, "dispatched"))
        if (call.kind, call.pin.key) != (kind, fact.settings.key) or call.outcome in (
            "stopped_unfit",
            "undispatched",
        ):
            raise ValueError("dispatch conflicts with its logical call")
        terminal = terminals.get((call_id, n))
        if terminal is not None and (terminal.dispatch_cursor, terminal.request_sha256) != (
            _dispatch_cursor(call_id, n),
            fact.request_sha256,
        ):
            raise ValueError("terminal belongs to a different dispatch")
        call.outcome = "dispatched"
        call.attempts.append(_AttemptFacts(fact, terminal, charges.get((call_id, n))))
    if run.abandoned - calls.keys():
        raise ValueError("abandoned call has no metadata")
    for call_id in run.abandoned:
        calls[call_id].outcome = "abandoned"
    return _RunFacts(run_id, run.stage, run.mode, run.date, calls)


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("evidence contains a duplicate JSON key")
    return result


def read_evidence(raw: bytes) -> Evidence:
    """Validate and join a sanitized evidence bundle once, on entry."""
    bundle = _Bundle.model_validate(json.loads(raw, object_pairs_hook=_unique_keys))
    tariffs: dict[tuple[str, str, str], list[_Tariff]] = {}
    for tariff in sorted(set(bundle.tariffs), key=lambda item: (item.key, item.effective_on)):
        schedule = tariffs.setdefault(tariff.key, [])
        if schedule and schedule[-1].through >= tariff.effective_on:
            raise ValueError("overlapping tariff dates for a model")
        schedule.append(tariff)
    return Evidence(
        bundle.opening,
        {key: tuple(schedule) for key, schedule in tariffs.items()},
        tuple(_join_run(run_id, run) for run_id, run in sorted(bundle.runs.items())),
        bundle.plan,
    )


@dataclass(frozen=True)
class AttemptRow:
    n: int
    date: date
    dispatch_cursor: str
    request_sha256: str
    disposition: str
    tokens: _Usage
    input_bound: int
    output_bound: int
    tariff: _Tariff | None
    charge: _Charge | None
    rated_pico: int | None
    settled_pico: int | None
    reserve_pico: int | None


@dataclass(frozen=True)
class CallRow:
    call_id: str
    kind: Kind
    model: _Pin
    outcome: str
    attempts: tuple[AttemptRow, ...]


@dataclass(frozen=True)
class RunRow:
    run_id: str
    stage: Stage
    mode: Mode
    date: date
    calls: tuple[CallRow, ...]


@dataclass(frozen=True)
class SizingRow:
    planned: _PlanRow
    peak_per_attempt_pico: int | None

    @property
    def reserve_pico(self) -> int | None:
        return _multiply(self.peak_per_attempt_pico, self.planned.count)


@dataclass(frozen=True)
class DaySizing:
    day: int | None
    attempts: int
    central_pico: int | None
    reserve_pico: int | None


@dataclass(frozen=True)
class SizingSheet:
    plan: _Plan
    tariff: _Tariff | None
    rows: tuple[SizingRow, ...]
    days: tuple[DaySizing, ...]
    reserve_pico: int | None
    affordable_days: int | None
    fits: bool


@dataclass(frozen=True)
class Ledger:
    opening: _Opening
    runs: tuple[RunRow, ...]
    settled_pico: int
    reserve_pico: int
    unbounded_attempts: int
    remaining_pico: int | None
    sizing: SizingSheet | None


def _tariff(evidence: Evidence, pin: _Pin, day: date) -> _Tariff | None:
    return next(
        (
            rate
            for rate in evidence.tariffs.get(pin.key, ())
            if rate.effective_on <= day <= rate.through
        ),
        None,
    )


def _rated(tokens: _Usage, tariff: _Tariff | None) -> int | None:
    total, hit, miss, output = tokens.input, tokens.cache_hit, tokens.cache_miss, tokens.output
    if tariff is None or total is None or hit is None or miss is None or output is None:
        return None
    if hit + miss != total:
        return None
    return (
        hit * tariff.cache_hit_per_million
        + miss * tariff.cache_miss_per_million
        + output * tariff.output_per_million
    )


def _attempt(evidence: Evidence, facts: _AttemptFacts) -> AttemptRow:
    dispatch, terminal, charge = facts.dispatch, facts.terminal, facts.charge
    day = dispatch.started_at.astimezone(UTC).date()
    tariff = _tariff(evidence, dispatch.settings, day)
    tokens = _Usage() if terminal is None else terminal.tokens
    rated = _rated(tokens, tariff)
    settled = rated
    if charge is not None:
        settled = charge.invoice_cny if charge.invoice_cny is not None else charge.provider_cny
    input_bound = dispatch.sent.manifest.tokens_total
    output_bound = dispatch.settings.max_output_tokens
    observed_input = max(tokens.input or 0, (tokens.cache_hit or 0) + (tokens.cache_miss or 0))
    reserve = None
    if settled is not None:
        reserve = 0
    elif (
        tariff is not None
        and observed_input <= input_bound
        and (tokens.output or 0) <= output_bound
    ):
        reserve = tariff.reserve(input_bound, output_bound)
    return AttemptRow(
        dispatch.n,
        day,
        _dispatch_cursor(dispatch.call.call_id, dispatch.n),
        dispatch.request_sha256,
        "terminal unavailable" if terminal is None else terminal.error_class or "returned",
        tokens,
        input_bound,
        output_bound,
        tariff,
        charge,
        rated,
        settled,
        reserve,
    )


def _multiply(amount: int | None, count: int) -> int | None:
    return None if amount is None else amount * count


def _sum_known(values: Iterable[int | None]) -> int | None:
    total = 0
    for value in values:
        if value is None:
            return None
        total += value
    return total


def _sizing(evidence: Evidence, plan: _Plan, remaining: int | None) -> SizingSheet:
    tariff = _tariff(evidence, plan, plan.date)
    rows = []
    for row in sorted(plan.rows, key=lambda row: (row.day or 0, row.kind, row.n)):
        peak = None
        if tariff is not None and row.input_bound is not None and row.output_bound is not None:
            peak = tariff.reserve(row.input_bound, row.output_bound)
        rows.append(SizingRow(row, peak))
    by_day: dict[int | None, list[SizingRow]] = {}
    for item in rows:
        by_day.setdefault(item.planned.day, []).append(item)
    days = tuple(
        DaySizing(
            day,
            sum(item.planned.count for item in group),
            _sum_known(_multiply(item.planned.central_cny, item.planned.count) for item in group),
            _sum_known(item.reserve_pico for item in group),
        )
        for day, group in by_day.items()
    )
    reserve = _sum_known(day.reserve_pico for day in days)
    affordable_days = None
    if plan.stage == "resident_run" and remaining is not None:
        affordable_days = 0
        available = remaining
        for day in days:
            if day.reserve_pico is None or day.reserve_pico > available:
                break
            available -= day.reserve_pico
            affordable_days += 1
    return SizingSheet(
        plan,
        tariff,
        tuple(rows),
        days,
        reserve,
        affordable_days,
        remaining is not None and reserve is not None and reserve <= remaining,
    )


def project(evidence: Evidence) -> Ledger:
    """Price each durable attempt and compare the proposed unit with phase headroom."""
    runs = tuple(
        RunRow(
            run.run_id,
            run.stage,
            run.mode,
            run.date,
            tuple(
                CallRow(
                    call_id,
                    call.kind,
                    call.pin,
                    call.outcome,
                    tuple(_attempt(evidence, facts) for facts in call.attempts),
                )
                for call_id, call in sorted(run.calls.items())
            ),
        )
        for run in evidence.runs
    )
    paid = [
        attempt
        for run in runs
        if run.mode == "paid"
        for call in run.calls
        for attempt in call.attempts
    ]
    opening = evidence.opening.settled_cny
    settled = (opening or 0) + sum(attempt.settled_pico or 0 for attempt in paid)
    held = sum(attempt.reserve_pico or 0 for attempt in paid)
    unbounded = sum(attempt.reserve_pico is None for attempt in paid)
    remaining = CAP_PICO - settled - held if opening is not None and not unbounded else None
    sizing = None if evidence.plan is None else _sizing(evidence, evidence.plan, remaining)
    return Ledger(evidence.opening, runs, settled, held, unbounded, remaining, sizing)


def _money(amount: int | None) -> str:
    if amount is None:
        return "unknown"
    whole, fraction = divmod(abs(amount), PICO_PER_CNY)
    sign = "-" if amount < 0 else ""
    return f"{sign}{whole}.{fraction:012d}".rstrip("0").rstrip(".")


def _text(value: object) -> str:
    return escape(" ".join(str(value).split())).replace("|", "&#124;").replace("[", "&#91;")


def _line(*cells: object) -> str:
    return "| " + " | ".join(_text(cell) for cell in cells) + " |"


def _table(*columns: str) -> list[str]:
    return [_line(*columns), _line(*("---" for _ in columns))]


def _shown(value: object | None) -> object:
    return "unknown" if value is None else value


def _price_source(tariff: _Tariff | None) -> str:
    if tariff is None:
        return "unknown"
    return (
        f"{tariff.effective_on} to {tariff.through} · {tariff.source} · "
        f"model evidence {tariff.model_evidence}"
    )


def _attempt_line(call_id: str, attempt: AttemptRow) -> str:
    charge = attempt.charge
    provider = charge.provider_cny if charge is not None else None
    invoice = charge.invoice_cny if charge is not None else None
    comparison = provider if provider is not None else attempt.rated_pico
    delta = invoice - comparison if invoice is not None and comparison is not None else None
    return _line(
        call_id,
        attempt.n,
        attempt.date,
        attempt.dispatch_cursor,
        attempt.request_sha256,
        attempt.disposition,
        _shown(attempt.tokens.input),
        _shown(attempt.tokens.cache_hit),
        _shown(attempt.tokens.cache_miss),
        _shown(attempt.tokens.output),
        attempt.input_bound,
        attempt.output_bound,
        _price_source(attempt.tariff),
        _money(attempt.rated_pico),
        _money(provider),
        _money(invoice),
        _money(delta),
        charge.source if charge else "—",
        _money(attempt.settled_pico),
        "unbounded" if attempt.reserve_pico is None else _money(attempt.reserve_pico),
    )


def _render_sizing(sizing: SizingSheet) -> list[str]:
    period = "—" if sizing.plan.stage == "provider_check" else _shown(sizing.affordable_days)
    lines = [
        "## Cost sizing",
        "",
        f"Stage `{sizing.plan.stage}` · {sizing.plan.date} · "
        f"{_text(' / '.join(sizing.plan.key))} · {_text(_price_source(sizing.tariff))}",
        "",
        *_table(
            "Game day",
            "Call kind",
            "Attempt n",
            "Count",
            "Input bound",
            "Output bound",
            "Central CNY / attempt",
            "Peak CNY / attempt",
            "Central CNY total",
            "Hold CNY",
        ),
    ]
    for item in sizing.rows:
        row = item.planned
        lines.append(
            _line(
                row.day if row.day is not None else "—",
                row.kind,
                row.n,
                row.count,
                _shown(row.input_bound),
                _shown(row.output_bound),
                _money(row.central_cny),
                _money(item.peak_per_attempt_pico),
                _money(_multiply(row.central_cny, row.count)),
                _money(item.reserve_pico),
            )
        )
    lines.extend(["", *_table("Game day", "Attempt count", "Central CNY", "Hold CNY")])
    for day in sizing.days:
        lines.append(
            _line(
                day.day if day.day is not None else "—",
                day.attempts,
                _money(day.central_pico),
                _money(day.reserve_pico),
            )
        )
    return lines + [
        "",
        f"Proposed unit hold (CNY) — {_money(sizing.reserve_pico)}",
        f"Affordable whole resident days from the proposed prefix — {period}",
        "",
    ]


def render_markdown(ledger: Ledger) -> str:
    """Render the repeatable projection without copying prompt or response bodies."""
    dispatch = "WITHHOLD"
    if ledger.sizing is not None and ledger.sizing.fits:
        dispatch = "WITHIN BUDGET (owner release required)"
    lines = [
        "# P3.5 spend projection",
        "",
        *_table(
            "Phase cap CNY",
            "Opening settled CNY",
            "Opening evidence",
            "Known settled CNY",
            "Known outstanding reserve CNY",
            "Known phase exposure CNY",
            "Unbounded paid attempts",
            "Headroom CNY",
        ),
        _line(
            _money(CAP_PICO),
            _money(ledger.opening.settled_cny),
            _shown(ledger.opening.source),
            _money(ledger.settled_pico),
            _money(ledger.reserve_pico),
            _money(ledger.settled_pico + ledger.reserve_pico),
            ledger.unbounded_attempts,
            _money(ledger.remaining_pico),
        ),
        "",
        f"Proposed dispatch budget check — **{dispatch}**",
        "",
        "Fake rows show simulated accounting and are excluded from the phase summary.",
        "",
    ]
    for stage in ("provider_check", "resident_run"):
        lines.extend([f"## {stage.replace('_', ' ').capitalize()}", ""])
        for run in ledger.runs:
            if run.stage != stage:
                continue
            attempts = [item for call in run.calls for item in call.attempts]
            lines.extend(
                [
                    f"### {_text(run.run_id)} · {run.mode.upper()} · {run.date}",
                    "",
                    f"Logical calls — {len(run.calls)}. Dispatched attempts — {len(attempts)}.",
                    "",
                    *_table(
                        "Call ID",
                        "Kind",
                        "Provider",
                        "Model alias",
                        "Pinned version",
                        "State",
                        "Attempts",
                    ),
                ]
            )
            for call in run.calls:
                lines.append(
                    _line(
                        call.call_id, call.kind, *call.model.key, call.outcome, len(call.attempts)
                    )
                )
            if attempts:
                lines.extend(
                    [
                        "",
                        *_table(
                            "Call ID",
                            "n",
                            "Dispatch date UTC",
                            "Dispatch cursor",
                            "Request SHA-256",
                            "Terminal state",
                            "Input",
                            "Cache hit",
                            "Cache miss",
                            "Output",
                            "Input bound",
                            "Output bound",
                            "Dated price and alias evidence",
                            "Rated CNY",
                            "Provider CNY",
                            "Invoice CNY",
                            "Invoice delta CNY",
                            "Charge evidence",
                            "Settled CNY",
                            "Reserve CNY",
                        ),
                    ]
                )
                lines.extend(
                    _attempt_line(call.call_id, item)
                    for call in run.calls
                    for item in call.attempts
                )
            lines.append("")
    if ledger.sizing is not None:
        lines.extend(_render_sizing(ledger.sizing))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="sanitized JSON evidence bundle")
    args = parser.parse_args()
    try:
        evidence = read_evidence(args.evidence.read_bytes())
    except ValidationError as error:
        messages = error.errors(include_input=False, include_context=False, include_url=False)
        parser.error("; ".join(message["msg"] for message in messages))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(render_markdown(project(evidence)), end="")


if __name__ == "__main__":
    main()
