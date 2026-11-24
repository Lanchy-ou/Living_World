"""Rebuild the EV-05 provider samples and run the bounded D7 check."""

import argparse
import os
import re
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from living_island.agents.llm import provider as p3
from living_island.agents.v2.calls.contracts import (
    INSTRUCTIONS,
    CallKind,
    Contract,
    digest,
    json_bytes,
    read_json,
)
from living_island.agents.v2.calls.fake import FakeClock, FakeTransport, ScriptedReply
from living_island.agents.v2.calls.guard import Prepared
from living_island.agents.v2.calls.journal import Journal
from living_island.agents.v2.calls.provider import (
    Clock,
    Dispatch,
    Returned,
    SystemClock,
    Terminal,
    attempt,
)
from living_island.agents.v2.calls.wire import RESERVE
from living_island.agents.v2.decision.caller import _DELAYS, Caller
from living_island.analysis import v2_spend as spend
from living_island.persistence.v2.audit import AuditReader, AuditWriter
from living_island.sim.v2.compat.config import load_compat_pack
from living_island.sim.v2.harness.replay import History
from living_island.world.v2.engine.validate import EnginePack
from living_island.world.v2.rules.vocabulary import parse_vocabulary

ROOT = Path(__file__).resolve().parents[6]
RUN_ID = "dl06-provider-live"
AUDIT_SHA256 = "b5e626c9bad17a41683676ee37774a742161eef25eeb17854266a3f37fb6d85d"
RECEIPT_SHA256 = "89ed3f2f9597b735faa0d793bc013924bf00f8210ef469ca5320b5773e4bacbc"
VOCABULARY_SHA256 = "5de460d9e649a1000080ad902b475026d8e1e88b571f2497557d565af3351a94"
PIN = {
    "provider": "deepseek-responses",
    "model": p3.MODEL_ID,
    "model_version": p3.COUNTER_MODEL_VERSION,
}
# Each retry class has its own allowance in the production caller.
ATTEMPTS = 1 + sum(map(len, _DELAYS.values()))
# MF §5 caps consolidation at three retries total, including the parse retry.
CONSOLIDATION_ATTEMPTS = 4
CONSOLIDATION_KINDS = frozenset({"consolidation_selection", "consolidation_change_set"})
HISTORICAL_DATE = date(2026, 11, 14)
HISTORICAL_EVIDENCE = {
    "opening": {"settled_cny": "0", "source": "P3.5-spend-ledger.md, owner 2026-11-24"},
    "tariffs": [
        {
            **PIN,
            "effective_on": HISTORICAL_DATE.isoformat(),
            "through": HISTORICAL_DATE.isoformat(),
            "source": "M9 final smoke and EV-05 forecast, historical peak only",
            "model_evidence": "M9 final CR-008 smoke, 2026-11-14",
            # Value both input categories at the peak for the historical projection.
            "cache_hit_per_million": "2",
            "cache_miss_per_million": "2",
            "output_per_million": "8",
            "peak_cache_miss_per_million": "2",
            "peak_output_per_million": "8",
        }
    ],
    "runs": {},
}
REASONING = [{"type": "reasoning", "id": "dl06-fake-reasoning", "summary": []}]


class Staged(BaseModel):
    prepared: str
    terminal: str
    sent_bytes: int
    wire_sha256: str


class Receipt(BaseModel):
    provider_check: dict[CallKind, Staged]


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dispatch_on: date
    approval: spend.Label
    wire_evidence: spend.Label
    preflight_sha256: spend.Hash
    ledger_sha256: spend.Hash
    max_cny: spend.Money


@dataclass(frozen=True)
class Sample:
    prepared: Prepared
    body: bytes
    input_bound: int
    running: bool
    staged_terminal: Terminal
    fake_body: bytes

    @property
    def kind(self) -> CallKind:
        return self.prepared.contract.kind

    @property
    def attempts(self) -> int:
        return CONSOLIDATION_ATTEMPTS if self.kind in CONSOLIDATION_KINDS else ATTEMPTS


def pinned_bytes(path: Path, expected: str) -> bytes:
    body = path.read_bytes()
    if digest(body) != expected:
        raise ValueError(f"{path.name}: pinned SHA-256 differs")
    return body


def check_wire(body: bytes, contract: Contract) -> None:
    """Inspect bytes from DL-01, including the provider's structured-output field."""
    wire = read_json(body)
    shape = read_json(contract.schema)
    if (
        wire["text"] != {"format": {"type": "json_schema", "name": contract.kind, "schema": shape}}
        or shape.get("type") != "object"
    ):
        raise ValueError(f"{contract.kind}: expected one object schema in text.format")
    if wire["tools"] or wire["tool_choice"] != "none":
        raise ValueError(f"{contract.kind}: tools must be disabled")
    if (
        wire["model"] != PIN["model"]
        or wire["reasoning"] != {"effort": "none"}
        or wire["max_output_tokens"] != RESERVE
        or wire["stream"] is not False
        or set(wire)
        != {
            "model",
            "reasoning",
            "max_output_tokens",
            "stream",
            "tools",
            "tool_choice",
            "text",
            "input",
        }
    ):
        raise ValueError(f"{contract.kind}: provider settings or stateless input differ")
    system, user = wire["input"]
    if system != {"role": "system", "content": contract.instructions} or user != {
        "role": "user",
        "content": user["content"],
    }:
        raise ValueError(f"{contract.kind}: expected only system and user text")
    compact = re.sub(r"\s+", "", contract.schema.decode())
    if compact in re.sub(r"\s+", "", user["content"]):
        raise ValueError(f"{contract.kind}: second schema copy in user text")


def load_samples(directory: Path) -> tuple[tuple[Sample, ...], str, History]:
    receipt = Receipt.model_validate_json(pinned_bytes(directory / "receipt.json", RECEIPT_SHA256))
    if receipt.provider_check.keys() != INSTRUCTIONS.keys():
        raise ValueError("expected one EV-05 sample of each call kind")
    path = directory / "provider-check.sqlite"
    pinned_bytes(path, AUDIT_SHA256)
    audit = AuditReader(path)
    history = History(audit, audit.cursor())
    vocab_raw = pinned_bytes(ROOT / "content/vocabulary/vocab-0.1.toml", VOCABULARY_SHA256)
    vocabulary = parse_vocabulary(tomllib.loads(vocab_raw.decode()))
    pack = load_compat_pack(
        ROOT / "content/worlds/default.toml", ROOT / "content/packs/compat-v1", vocabulary
    ).pack
    verbs = tuple(verb.shape for verb in EnginePack.from_pack(pack).verbs.values())

    samples = []
    for kind in INSTRUCTIONS:
        staged = receipt.provider_check[kind]
        prepared = history.request(staged.prepared, verbs)
        admitted = prepared.admitted
        if admitted is None or prepared.contract.kind != kind:
            raise ValueError(f"{kind}: staged request must have an admitted candidate")
        body = admitted.wire.body
        if digest(body) != staged.wire_sha256 or len(body) != staged.sent_bytes:
            raise ValueError(f"{kind}: staged wire differs from the EV-05 receipt")
        check_wire(body, prepared.contract)
        ((_, terminal),) = history.attempts(prepared)
        if (
            not isinstance(terminal, Terminal)
            or terminal.error_class is not None
            or terminal.raw_output_ref is None
            or terminal.parsed_ref is None
            or Journal.cursor(terminal.call_id, "0.terminal") != staged.terminal
        ):
            raise ValueError(f"{kind}: expected a successful staged fake terminal")
        running = any(
            entry.source.id.endswith("/running")
            and history.read(entry.sha256).startswith(b"Running ")
            for entry in admitted.candidate.manifest.entries
        )
        samples.append(
            Sample(
                prepared,
                body,
                admitted.wire.counted,
                running,
                terminal,
                history.read(terminal.raw_output_ref),
            )
        )
    return tuple(samples), vocabulary.vocabulary_hash, history


def preflight(samples: tuple[Sample, ...], vocabulary_hash: str) -> dict[str, object]:
    return {
        "implementation_sha256": digest(Path(__file__).read_bytes()),
        "sample_sha256": AUDIT_SHA256,
        "ev05_receipt_sha256": RECEIPT_SHA256,
        "vocabulary_sha256": VOCABULARY_SHA256,
        "canonical_vocabulary_sha256": vocabulary_hash,
        "requests": {
            sample.kind: {
                "prepared": sample.prepared.cursor,
                "wire_sha256": digest(sample.body),
                "sent_bytes": len(sample.body),
                "input_bound": sample.input_bound,
                "attempts": sample.attempts,
                "running": sample.running,
                "settings": sample.prepared.record.settings.model_dump(mode="json"),
            }
            for sample in samples
        },
    }


def price(samples: tuple[Sample, ...], evidence: dict[str, Any], day: date) -> spend.Ledger:
    plan = {
        **PIN,
        "stage": "provider_check",
        "date": day.isoformat(),
        "rows": [
            {
                "day": None,
                "kind": sample.kind,
                "n": n,
                "count": 1,
                "input_bound": sample.input_bound,
                "output_bound": RESERVE,
                "central_cny": None,
            }
            for sample in samples
            for n in range(sample.attempts)
        ],
    }
    return spend.project(spend.read_evidence(json_bytes({**evidence, "plan": plan})))


def admit(ledger: spend.Ledger, release: Release) -> None:
    sizing = ledger.sizing
    if (
        sizing is None
        or not sizing.fits
        or sizing.reserve_pico is None
        or sizing.reserve_pico > release.max_cny
    ):
        raise ValueError("no covered allowance for the check at the verified tariff and balance")


@dataclass(frozen=True)
class ProtectedTransport:
    """Keep authorization out of archives even if the remote body echoes it."""

    transport: p3.ByteTransport
    secret: bytes = field(repr=False)
    before_exchange: Callable[[], None]

    def exchange(self, body: bytes, timeout_ms: int) -> p3.TransportResponse:
        self.before_exchange()
        response = self.transport.exchange(body, timeout_ms)
        if response.body is not None:
            # Also drop a partial credential echoed at the end of a truncated body.
            if self.secret in response.body or (
                not response.complete
                and any(response.body.endswith(self.secret[:i]) for i in range(1, len(self.secret)))
            ):
                return replace(response, body=None, complete=False)
        return response


def consolidation_terminal(sample: Sample, journal: Journal, caller: Caller) -> Terminal:
    invalid = False
    n = 0
    while True:
        result = cast(
            Returned,
            attempt(
                sample.prepared,
                n=n,
                has_running_action=sample.running,
                journal=journal,
                transport=caller.transport,
                clock=caller.clock,
            ),
        )
        terminal = result.terminal
        error = terminal.error_class
        if n + 1 == CONSOLIDATION_ATTEMPTS or error in (None, "provider_error"):
            return terminal
        if error == "invalid_output":
            if invalid:
                return terminal
            invalid = True
        else:
            caller.delay(_DELAYS[error][n])
        n += 1


def execute(
    samples: tuple[Sample, ...],
    source: History,
    journal: Journal,
    caller: Caller,
    *,
    live: bool = False,
) -> None:
    for sample in samples:
        prepared = sample.prepared
        for candidate in prepared.record.candidates:
            for entry in candidate.manifest.entries:
                journal.blob(source.read(entry.sha256))
            journal.blob(source.read(candidate.wire_sha256))
        journal.fact(prepared.record.call.call_id, "prepared", prepared.record)
        terminal = (
            consolidation_terminal(sample, journal, caller)
            if sample.kind in CONSOLIDATION_KINDS
            else caller.dispatch(prepared, journal, running=sample.running).terminal
        )
        if not live:
            expected = sample.staged_terminal
            if terminal.parsed_ref != expected.parsed_ref or terminal.reasoning_ref != digest(
                json_bytes(REASONING)
            ):
                raise ValueError(f"{sample.kind}: fake parsing or reasoning evidence differs")
        if terminal.error == "RESPONSE_MODEL_MISMATCH":
            raise ValueError("response model moved away from the released alias")


def fake_check(samples: tuple[Sample, ...], history: History) -> None:
    clock = FakeClock()
    replies = []
    for sample in samples:
        response = read_json(sample.fake_body)
        response["output"][:0] = REASONING
        replies.append(ScriptedReply(p3.TransportResponse(200, json_bytes(response), True)))
    transport = FakeTransport(clock, replies)

    def ignore_fact(_key: str, _body: bytes) -> None:
        pass

    keep = Journal(ignore_fact, ignore_fact)
    execute(samples, history, keep, Caller(transport, clock, lambda _: None))
    if transport.dispatches != [sample.body for sample in samples]:
        raise ValueError("fake exchange did not send the six unchanged, stateless requests")


def archive(
    output: Path,
    audit: AuditReader,
    evidence: dict[str, Any],
    day: date,
    samples: tuple[Sample, ...],
) -> dict[str, object]:
    keys = audit.keys(0, audit.cursor())
    run: dict[str, Any] = {"stage": "provider_check", "mode": "paid", "date": day.isoformat()}
    for field_name, slot in (
        ("prepared", "prepared"),
        ("dispatches", "dispatch"),
        ("terminals", "terminal"),
    ):
        run[field_name] = [
            read_json(audit.read(key)) for key in keys if key.endswith(f".{slot}.json")
        ]
    # Include the selected calls that never reached preparation if the check stopped early.
    started = {row["call"]["call_id"] for row in run["prepared"]}
    run["undispatched"] = [
        {"call_id": sample.prepared.record.call.call_id, "kind": sample.kind, **PIN}
        for sample in samples
        if sample.prepared.record.call.call_id not in started
    ]
    # EV-04 reads accounting fields only. Do not pass contexts, responses or reasoning.
    bundle = {**evidence, "runs": {**evidence["runs"], RUN_ID: run}}
    ledger = spend.project(spend.read_evidence(json_bytes(bundle)))
    (output / "ledger-evidence.json").write_bytes(json_bytes(bundle))
    (output / "ledger.md").write_text(spend.render_markdown(ledger), encoding="utf-8")

    terminals = {
        (row["call_id"], row["n"]): Terminal.model_validate(row) for row in run["terminals"]
    }
    by_kind: dict[str, list[dict[str, object]]] = {kind: [] for kind in INSTRUCTIONS}
    for dispatch in map(Dispatch.model_validate, run["dispatches"]):
        terminal = terminals.get((dispatch.call.call_id, dispatch.n))
        by_kind[dispatch.sent.manifest.call_kind].append(
            {
                "n": dispatch.n,
                "wire_sha256": dispatch.request_sha256,
                "status": terminal.status if terminal else None,
                "http_accepted": (
                    terminal is not None
                    and terminal.status is not None
                    and 200 <= terminal.status < 300
                ),
                "outcome": (terminal.error or "parsed") if terminal else "interrupted",
                "parsed": terminal is not None and terminal.parsed_ref is not None,
            }
        )
    decisions = by_kind["decision"] + by_kind["decision_after_recall"]
    attempts = [row for rows in by_kind.values() for row in rows]
    first_pass_decisions = sum(bool(row["parsed"]) for row in decisions if row["n"] == 0)
    passed = first_pass_decisions == 2 and all(
        any(row["parsed"] for row in rows) for rows in by_kind.values()
    )
    paid_run = next(run_row for run_row in ledger.runs if run_row.run_id == RUN_ID)
    settled = all(row.settled_pico is not None for call in paid_run.calls for row in call.attempts)
    report = {
        "logical_sample_count": len(by_kind),
        "first_pass_decisions": [first_pass_decisions, 2],
        "decision_dispatches_parsed": [
            sum(bool(row["parsed"]) for row in decisions),
            len(decisions),
        ],
        "all_dispatches_parsed": [sum(bool(row["parsed"]) for row in attempts), len(attempts)],
        "all_http_accepted": [sum(bool(row["http_accepted"]) for row in attempts), len(attempts)],
        "historical_m9_decisions_parsed": [22, 22],
        "by_kind": by_kind,
        "passed": passed,
        "provider_gate_passed": (
            passed and settled and ledger.remaining_pico is not None and ledger.remaining_pico >= 0
        ),
        "audit_sha256": digest(audit.path.read_bytes()),
        "ledger_evidence_sha256": digest((output / "ledger-evidence.json").read_bytes()),
    }
    (output / "result.json").write_bytes(json_bytes(report))
    return report


def checked_day(clock: Clock, day: date) -> None:
    if clock.now().date() != day:
        raise ValueError("outside the released UTC dispatch date")


def live_check(
    samples: tuple[Sample, ...],
    history: History,
    pins: dict[str, object],
    release_path: Path,
    ledger_path: Path,
) -> int:
    release_bytes = release_path.read_bytes()
    release = Release.model_validate_json(release_bytes)
    if digest(json_bytes(pins)) != release.preflight_sha256:
        raise ValueError("release does not match the rebuilt preflight")
    evidence = read_json(pinned_bytes(ledger_path, release.ledger_sha256))
    clock = SystemClock()
    checked_day(clock, release.dispatch_on)
    ledger = price(samples, evidence, release.dispatch_on)
    if any(run.run_id == RUN_ID for run in ledger.runs):
        raise ValueError("ledger already records this one-time check")
    admit(ledger, release)
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY must be injected in the live process environment")
    transport = ProtectedTransport(
        p3.HTTPSByteTransport(key), key.encode(), lambda: checked_day(clock, release.dispatch_on)
    )
    output = ROOT / "runs" / RUN_ID
    output.mkdir()  # Exclusive: a completed or interrupted live check cannot be restarted.
    (output / "preflight.json").write_bytes(json_bytes(pins))
    (output / "release.json").write_bytes(release_bytes)
    (output / "reservation.md").write_text(spend.render_markdown(ledger), encoding="utf-8")
    writer = AuditWriter(output / "provider-check.sqlite")
    try:
        execute(
            samples,
            history,
            Journal(writer.keep, writer.create),
            Caller(transport, clock, time.sleep),
            live=True,
        )
    finally:
        report = archive(output, AuditReader(writer.path), evidence, release.dispatch_on, samples)
    print(json_bytes(report).decode())
    return 0 if report["provider_gate_passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample-dir", type=Path, required=True, help="EV-05 Ella evidence directory"
    )
    parser.add_argument(
        "--live", action="store_true", help="opt in to the separately released check"
    )
    parser.add_argument("--release", type=Path, help="owner release JSON, required for --live")
    parser.add_argument("--ledger", type=Path, help="reconciled EV-04 bundle, required for --live")
    args = parser.parse_args()
    if args.live and (args.release is None or args.ledger is None):
        parser.error("--live needs both --release and --ledger")
    try:
        samples, vocabulary_hash, history = load_samples(args.sample_dir)
        pins = preflight(samples, vocabulary_hash)
        if args.live:
            return live_check(samples, history, pins, args.release, args.ledger)
        fake_check(samples, history)
        print(json_bytes({"preflight_sha256": digest(json_bytes(pins)), **pins}).decode())
        print(spend.render_markdown(price(samples, HISTORICAL_EVIDENCE, HISTORICAL_DATE)))
    except (ValidationError, TypeError):
        parser.exit(1, "Provider check evidence has invalid fields.\n")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Provider check stopped: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
