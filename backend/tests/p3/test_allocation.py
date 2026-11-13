"""Allocation ownership, publication and crash tests with no provider or credentials."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from living_island.agents.p3.types import (
    AllocationEntry,
    AllocationHead,
    BudgetCaps,
    CallDebit,
    CaseAllocationP3,
    PricingPin,
)
from living_island.memory.p3_types import canonical_bytes
from living_island.persistence.p3_allocation import (
    REPLACEMENT_SMOKE_CAPS,
    REPLACEMENT_SMOKE_CASE,
    AllocationError,
    AllocationStore,
    CaseAllocationSession,
    VerifiedCheckpoint,
    allocation_key,
    initialize_fake,
    initialize_pilot,
    ledger_from_entries,
    reserved_money,
)

HASH = "1" * 64
REQUEST = "2" * 64
WIRE = "3" * 64
TERMINAL = "4" * 64
MANIFEST = "5" * 64
DECISION = "test:d:ella:000000"
CALL = DECISION + ":a0"
CAPS = BudgetCaps(attempts=2, input_tokens=200, output_tokens=40, micro_cny=200)
PRICE = PricingPin(
    currency="CNY",
    date="2026-11-11",
    source_url="fixture",
    input_micro_cny_per_million_tokens=750000,
    output_micro_cny_per_million_tokens=4500000,
)
LIVE_PRICE = PricingPin(
    currency="CNY",
    date="2026-11-11",
    source_url="fixture",
    input_micro_cny_per_million_tokens=2000000,
    output_micro_cny_per_million_tokens=8000000,
)
SMOKE = BudgetCaps(attempts=48, input_tokens=1572864, output_tokens=98304, micro_cny=5000000)


class Harness:
    def __init__(self, base: Path, *, create: bool = True, caps: BudgetCaps = CAPS) -> None:
        self.base = base
        self.root = base / "authority"
        self.run = base / "run"
        self.key = allocation_key(HASH, "case")
        if create:
            initialize_fake(self.root)
            store = self.store()
            assert store.enroll_fake(HASH, "case", caps) == self.key
            with store.open_case(self.key, PRICE, None, self.verify) as session:
                self.h0 = self.publish(session, 0, [])
            (base / "head0.json").write_bytes(canonical_bytes(self.h0))
        else:
            self.h0 = AllocationHead.model_validate_json((base / "head0.json").read_bytes())

    def store(self, fault=None) -> AllocationStore:
        return AllocationStore(self.root, mode="fake", fault=fault)

    def open(self, head=None, *, offline=False, fault=None) -> CaseAllocationSession:
        return self.store(fault).open_case(
            self.key,
            PRICE,
            self.h0 if head is None else head,
            self.verify,
            offline_recovery=offline,
        )

    def verify(self, head: AllocationHead) -> VerifiedCheckpoint | None:
        path = Path(head.run_directory) / (head.checkpoint_sha256 + ".json")
        if not path.exists():
            return None
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == head.checkpoint_sha256, "corrupt checkpoint"
        obj = json.loads(data)
        entries = [AllocationEntry.model_validate(e) for e in obj["entries"]]
        assert obj["tick"] == head.checkpoint_tick
        assert len(entries) == head.reservation_cursor
        assert obj["manifest"] == head.input_manifest_sha256
        return VerifiedCheckpoint(head, entries, obj["live"], obj["complete"])

    def candidate(self, tick, entries, *, live=True, complete=False, run=None):
        data = canonical_bytes(
            {
                "tick": tick,
                "entries": [e.model_dump(mode="json") for e in entries],
                "manifest": MANIFEST,
                "live": live,
                "complete": complete,
            }
        )
        head = AllocationHead(
            checkpoint_sha256=hashlib.sha256(data).hexdigest(),
            checkpoint_tick=tick,
            input_manifest_sha256=MANIFEST,
            run_directory=str(self.run if run is None else run),
            reservation_cursor=len(entries),
        )
        return head, data

    def publish(self, session, tick, entries, *, live=True, complete=False):
        head, data = self.candidate(tick, entries, live=live, complete=complete)
        session.prepare(head, entries)
        path = Path(head.run_directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / (head.checkpoint_sha256 + ".json")).write_bytes(data)
        session.finalize(head, entries, complete=complete)
        return head

    def raw(self) -> CaseAllocationP3:
        return CaseAllocationP3.model_validate_json(
            (self.root / "allocations" / (self.key + ".json")).read_bytes()
        )


def charge(reservation, *, inputs=80, outputs=10, recovery=False):
    unknown = inputs is None or outputs is None
    use_reserved = recovery or unknown
    charged_input = max(reservation.input_reserved, inputs or 0) if use_reserved else inputs
    charged_output = max(reservation.output_reserved, outputs or 0) if use_reserved else outputs
    return CallDebit(
        call_id=reservation.call_id,
        input_reserved=reservation.input_reserved,
        output_reserved=reservation.output_reserved,
        money_reserved=reservation.money_reserved,
        input_reported=inputs,
        output_reported=outputs,
        input_charged=charged_input,
        output_charged=charged_output,
        money_charged=reserved_money(PRICE, charged_input, charged_output),
        usage_unknown=unknown,
    )


def settled(session, *, inputs=80, outputs=10):
    entry = session.snapshot().entries[-1]
    debit = charge(entry.reservation, inputs=inputs, outputs=outputs)
    session.commit(entry.reservation.call_id.rsplit(":a", 1)[0], [debit])
    return AllocationEntry.model_validate(
        {
            **entry.model_dump(mode="json"),
            "state": "settled",
            "debit": debit,
            "terminal_call_sha256": TERMINAL,
        }
    )


def recovery_origin(session, *, inputs=None, outputs=None):
    case = session.snapshot()
    assert case.head is not None
    suffix = case.entries[case.head.reservation_cursor :]
    entries = [
        AllocationEntry.model_validate(
            {
                **e.model_dump(mode="json"),
                "state": "recovery",
                "debit": charge(e.reservation, inputs=inputs, outputs=outputs, recovery=True),
                "terminal_call_sha256": None if inputs is None or outputs is None else TERMINAL,
            }
        )
        for e in suffix
    ]
    artifacts = {"authority-tail.json": canonical_bytes(case), "dispatch-tail.jsonl": b""}
    origin = canonical_bytes(
        {
            "origin_version": "0.2",
            "source_run_id": "test",
            "checkpoint_tick": case.head.checkpoint_tick,
            "checkpoint_sha256": case.head.checkpoint_sha256,
            "source_input_manifest_sha256": case.head.input_manifest_sha256,
            "log_prefixes": [],
            "recovery_mode": "offline",
            "allocation_key": case.allocation_key,
            "orphan_artifacts": [
                {"name": name, "sha256": hashlib.sha256(body).hexdigest()}
                for name, body in sorted(artifacts.items())
            ],
            "recovery_entries": [e.model_dump(mode="json") for e in entries],
            "recovery_debits": [e.debit.model_dump(mode="json") for e in entries],
        }
    )
    return origin, artifacts, entries


def assert_code(code, callback):
    with pytest.raises(AllocationError) as error:
        callback()
    assert error.value.code == code


def child(base: Path, body: str, *args: str) -> subprocess.Popen:
    # run_path makes the same deterministic checkpoint fixture available in a real process.
    script = (
        "import sys, runpy, os, json; from pathlib import Path\n"
        "globals().update(runpy.run_path(sys.argv[1]))\n"
        "base=Path(sys.argv[2])\n" + body
    )
    return subprocess.Popen(
        [sys.executable, "-c", script, str(Path(__file__).resolve()), str(base), *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish(process, expected=0):
    out, err = process.communicate(timeout=30)
    assert process.returncode == expected, (out, err)
    return out.strip()


def test_integer_micro_cny_and_tick_zero_gate(tmp_path):
    assert reserved_money(PRICE, 100, 20) == 165
    assert reserved_money(PRICE, 80, 10) == 105
    assert reserved_money(PRICE, 20, 10) == 60
    assert reserved_money(PRICE, 1, 1) == 6
    with pytest.raises(ValueError):
        reserved_money(PRICE, True, 0)
    root = tmp_path / "authority"
    initialize_fake(root)
    store = AllocationStore(root, mode="fake")
    key = store.enroll_fake(HASH, "case", CAPS)
    with store.open_case(key, PRICE, None, lambda head: None) as session:
        assert_code("ALLOCATION_INTEGRITY", lambda: session.admit(CALL, 100, 20, REQUEST, WIRE))
        assert session.snapshot().entries == []


def test_bd18_20_deferred_settlement_clean_resume_and_stale_head(tmp_path):
    h = Harness(tmp_path)
    with h.open() as session:
        reservation = session.admit(CALL, 100, 20, REQUEST, WIRE)
        assert reservation.money_reserved == 165
        entry = settled(session)
        assert session.export_ledger().money_charged == 105
        assert session.snapshot().entries[0].state == "reserved"
        assert session.admit("test:d:ella:000001:a0", 100, 20, REQUEST, WIRE) is None
        assert_code("ALLOCATION_DUPLICATE_CALL", lambda: session.admit(CALL, 1, 1, REQUEST, WIRE))
        assert_code("ALLOCATION_DUPLICATE_CALL", lambda: session.commit(DECISION, [entry.debit]))
        head1 = h.publish(session, 1, [entry])
    assert_code("ALLOCATION_STALE", h.open)
    with h.open(head1) as session:
        reservation = session.admit("test:d:ella:000001:a0", 20, 10, REQUEST, WIRE)
        assert reservation.reservation_ordinal == 1 and reservation.money_reserved == 60
        second = settled(session, inputs=20, outputs=10)
        head2 = h.publish(session, 2, [entry, second])
        assert session.export_ledger().model_dump(
            include={"attempts_charged", "input_charged", "output_charged", "money_charged"}
        ) == {
            "attempts_charged": 2,
            "input_charged": 100,
            "output_charged": 20,
            "money_charged": 165,
        }
    with h.open(head2) as session:
        assert session.admit("test:d:ella:000002:a0", 0, 0, REQUEST, WIRE) is None


@pytest.mark.parametrize(
    "caps",
    [
        BudgetCaps(attempts=0, input_tokens=200, output_tokens=40, micro_cny=200),
        BudgetCaps(attempts=2, input_tokens=99, output_tokens=40, micro_cny=200),
        BudgetCaps(attempts=2, input_tokens=200, output_tokens=19, micro_cny=200),
        BudgetCaps(attempts=2, input_tokens=200, output_tokens=40, micro_cny=164),
    ],
)
def test_caps_are_independent_hard_limits(tmp_path, caps):
    h = Harness(tmp_path, caps=caps)
    with h.open() as session:
        assert session.admit(CALL, 100, 20, REQUEST, WIRE) is None
        assert session.snapshot().entries == []


def test_unknown_usage_keeps_full_reservation(tmp_path):
    h = Harness(tmp_path)
    with h.open() as session:
        session.admit(CALL, 100, 20, REQUEST, WIRE)
        entry = settled(session, inputs=80, outputs=None)
        assert entry.debit.money_charged == 165 and entry.debit.usage_unknown
        h.publish(session, 1, [entry])
        assert session.export_ledger().unknown_usage_count == 1


def test_bd19_real_two_process_lock_and_process_death(tmp_path):
    h = Harness(tmp_path)
    first = child(
        tmp_path,
        "h=Harness(base, create=False)\ns=h.open()\nprint('HELD', flush=True)\n"
        "sys.stdin.readline()\nos._exit(73)\n",
    )
    try:
        assert first.stdout.readline().strip() == "HELD"
        second = child(
            tmp_path,
            "h=Harness(base, create=False)\ntry:\n s=h.open()\n"
            "except AllocationError as e:\n print(e.code)\n",
        )
        assert finish(second) == "ALLOCATION_BUSY"
        assert h.raw().entries == []
        first.stdin.write("exit\n")
        first.stdin.flush()
        finish(first, 73)
        with h.open() as session:
            assert session.snapshot().generation == 3
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=30)


@pytest.mark.parametrize(
    "stage,durable",
    [
        ("reservation:before_write", False),
        ("reservation:after_flush", False),
        ("reservation:after_replace", True),
    ],
)
def test_bd21_22_process_crash_at_reservation_phases(tmp_path, stage, durable):
    h = Harness(tmp_path)
    process = child(
        tmp_path,
        "h=Harness(base, create=False)\n"
        "def fault(stage):\n if stage == sys.argv[3]: os._exit(73)\n"
        "s=h.open(fault=fault)\ns.admit(CALL,100,20,REQUEST,WIRE)\n",
        stage,
    )
    finish(process, 73)
    assert len(h.raw().entries) == int(durable)
    if durable:
        assert_code("INTERRUPTED_CALL_RECOVERY_REQUIRED", h.open)
    else:
        with h.open() as session:
            assert session.export_ledger().attempts_charged == 0


@pytest.mark.parametrize("phase", ["before_write", "after_flush", "after_replace"])
@pytest.mark.parametrize("operation", ["prepare", "finalize"])
def test_bd24_prepared_publication_process_crashes(tmp_path, operation, phase):
    h = Harness(tmp_path)
    stage = operation + ":" + phase
    process = child(
        tmp_path,
        "h=Harness(base, create=False)\n"
        "def fault(stage):\n if stage == sys.argv[3]: os._exit(73)\n"
        "s=h.open(fault=fault)\ns.admit(CALL,100,20,REQUEST,WIRE)\ne=settled(s)\n"
        "head,data=h.candidate(1,[e])\n(base/'head1.json').write_bytes(canonical_bytes(head))\n"
        "s.prepare(head,[e])\n(Path(head.run_directory)/(head.checkpoint_sha256+'.json')).write_bytes(data)\n"
        "s.finalize(head,[e])\n",
        stage,
    )
    finish(process, 73)
    h1 = AllocationHead.model_validate_json((tmp_path / "head1.json").read_bytes())
    if operation == "prepare":
        assert_code("INTERRUPTED_CALL_RECOVERY_REQUIRED", h.open)
        assert h.raw().head == h.h0
        assert h.raw().entries[0].state == "reserved"
        assert h.raw().entries[0].reservation.money_reserved == 165
        assert h.raw().prepared_head is None
    else:
        # Even the stale request reconciles a fully published prepared target first.
        assert_code("ALLOCATION_STALE", h.open)
        with h.open(h1) as session:
            assert session.snapshot().prepared_head is None
            assert session.export_ledger().money_charged == 105
            assert len(session.snapshot().entries) == 1


def test_bd24_absent_and_corrupt_targets_never_refund(tmp_path):
    h = Harness(tmp_path)
    s = h.open()
    s.admit(CALL, 100, 20, REQUEST, WIRE)
    entry = settled(s)
    head, _ = h.candidate(1, [entry])
    s.prepare(head, [entry])
    assert_code("ALLOCATION_INTEGRITY", lambda: s.finalize(head, [entry]))
    assert s.snapshot().entries[0].state == "reserved"
    target = Path(head.run_directory) / (head.checkpoint_sha256 + ".json")
    target.write_bytes(b"corrupt")
    s.close(clean=False)
    with pytest.raises(AssertionError, match="corrupt checkpoint"):
        h.open()
    assert h.raw().head == h.h0 and h.raw().prepared_head == head
    assert h.raw().entries[0].state == "reserved"


@pytest.mark.parametrize("inputs,outputs", [(None, None), (80, 10), (80, None), (120, 30)])
def test_bd22_23_25_recovery_is_exact_once_and_permanently_offline(tmp_path, inputs, outputs):
    h = Harness(tmp_path)
    s = h.open()
    s.admit(CALL, 100, 20, REQUEST, WIRE)
    s.close(clean=False)
    assert_code("INTERRUPTED_CALL_RECOVERY_REQUIRED", h.open)
    s = h.open(offline=True)
    origin, evidence, entries = recovery_origin(s, inputs=inputs, outputs=outputs)
    sha = s.latch_recovery(origin, evidence, entries)
    assert sha == hashlib.sha256(origin).hexdigest()
    assert s.export_ledger().attempts_charged == 1
    assert s.export_ledger().money_charged == (225 if inputs == 120 else 165)
    assert s.recovery_evidence() == evidence
    s.close(clean=False)
    assert_code("ALLOCATION_CLOSED", h.open)
    with h.open(offline=True) as s:
        assert s.pending_recovery() == origin
        assert s.latch_recovery(origin, evidence, entries) == sha
        assert len(s.snapshot().entries) == 1
        assert_code("ALLOCATION_CLOSED", lambda: s.admit("other", 0, 0, REQUEST, WIRE))
        head = h.publish(s, 1, entries, live=False)
        assert s.pending_recovery() is None
        assert s.export_ledger().attempts_charged == 1
    assert_code("ALLOCATION_STALE", lambda: h.open(offline=True))
    assert_code("ALLOCATION_CLOSED", lambda: h.open(head))
    with h.open(head, offline=True) as s:
        assert s.snapshot().status == "offline_only"
        assert s.export_ledger().attempts_charged == 1


@pytest.mark.parametrize(
    "stage",
    [
        "recovery_evidence:before_write",
        "recovery_evidence:after_flush",
        "recovery_evidence:after_replace",
        "recovery_origin:before_write",
        "recovery_origin:after_flush",
        "recovery_origin:after_replace",
        "recovery_latch:before_write",
        "recovery_latch:after_flush",
        "recovery_latch:after_replace",
    ],
)
def test_bd25_recovery_process_crash_phases(tmp_path, stage):
    h = Harness(tmp_path)
    s = h.open()
    s.admit(CALL, 100, 20, REQUEST, WIRE)
    s.close(clean=False)
    process = child(
        tmp_path,
        "h=Harness(base, create=False)\n"
        "def fault(stage):\n if stage == sys.argv[3]: os._exit(73)\n"
        "s=h.open(offline=True,fault=fault)\no,a,e=recovery_origin(s)\n"
        "(base/'attempted-origin.json').write_bytes(o)\ns.latch_recovery(o,a,e)\n",
        stage,
    )
    finish(process, 73)
    raw = h.raw()
    assert len(raw.entries) == 1
    assert (raw.pending_recovery_sha256 is not None) == (stage == "recovery_latch:after_replace")
    with h.open(offline=True) as s:
        pending = s.pending_recovery()
        if pending is None:
            origin, evidence, entries = recovery_origin(s)
            s.latch_recovery(origin, evidence, entries)
        else:
            assert pending == (tmp_path / "attempted-origin.json").read_bytes()
            entries = s.snapshot().entries
        assert s.export_ledger().money_charged == 165
        h.publish(s, 1, entries, live=False)
        assert s.export_ledger().attempts_charged == 1


def test_recovery_rejects_mutated_evidence_and_origin(tmp_path):
    h = Harness(tmp_path)
    s = h.open()
    s.admit(CALL, 100, 20, REQUEST, WIRE)
    s.close(clean=False)
    s = h.open(offline=True)
    origin, evidence, entries = recovery_origin(s)
    changed = dict(evidence)
    changed["authority-tail.json"] = b"changed"
    assert_code("ALLOCATION_INTEGRITY", lambda: s.latch_recovery(origin, changed, entries))
    s.latch_recovery(origin, evidence, entries)
    assert_code("ALLOCATION_INTEGRITY", lambda: s.latch_recovery(origin + b" ", evidence, entries))
    s.close(clean=False)
    blob = (
        h.root
        / "recovery-evidence"
        / (hashlib.sha256(evidence["authority-tail.json"]).hexdigest() + ".bin")
    )
    blob.write_bytes(b"changed")
    assert_code("ALLOCATION_INTEGRITY", lambda: h.open(offline=True))


def test_bd26_pure_replay_ledger_with_authority_unavailable(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    with h.open() as s:
        s.admit(CALL, 100, 20, REQUEST, WIRE)
        entry = settled(s)
        h.publish(s, 1, [entry])
        expected = s.export_ledger()
    before = h.raw()

    def forbidden(*args, **kwargs):
        raise AssertionError("replay touched allocation authority")

    monkeypatch.setattr(AllocationStore, "__init__", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    assert ledger_from_entries(h.key, CAPS, [entry]) == expected
    assert ledger_from_entries(h.key, CAPS, [entry]) == expected
    assert before.generation == 2


def test_bd27_closed_lost_cloned_and_corrupt_authorities(tmp_path):
    h = Harness(tmp_path)
    with h.open() as s:
        closed = h.publish(s, 1, [], complete=True)
    assert_code("ALLOCATION_CLOSED", lambda: h.open(closed))
    assert_code("ALLOCATION_CLOSED", lambda: h.open(closed, offline=True))
    assert_code("ALLOCATION_ALREADY_ENROLLED", lambda: h.store().enroll_fake(HASH, "case", CAPS))
    copied = tmp_path / "copy-authority"
    shutil.copytree(h.root, copied)
    assert_code("ALLOCATION_UNAVAILABLE", lambda: AllocationStore(copied, mode="fake"))
    path = h.root / "allocations" / (h.key + ".json")
    path.unlink()
    assert_code("ALLOCATION_UNAVAILABLE", lambda: h.open(closed))
    assert_code("ALLOCATION_UNAVAILABLE", lambda: h.store().enroll_fake(HASH, "case", CAPS))


def test_stale_generation_and_authority_integrity(tmp_path):
    h = Harness(tmp_path)
    s = h.open()
    path = h.root / "allocations" / (h.key + ".json")
    data = h.raw().model_dump(mode="json")
    data["generation"] += 1
    path.write_bytes(canonical_bytes(data))
    assert_code("ALLOCATION_STALE", lambda: s.admit(CALL, 0, 0, REQUEST, WIRE))
    assert_code("ALLOCATION_STALE", lambda: s.close(clean=False))
    data["caps"]["micro_cny"] += 1
    path.write_bytes(canonical_bytes(data))
    assert_code("ALLOCATION_INTEGRITY", h.open)


def test_pilot_six_slots_exact_ceiling_and_one_time_binding(tmp_path):
    root, approval = tmp_path / "authority", tmp_path / "approval.json"
    initialize_pilot(approval, root)
    store = AllocationStore(root, mode="live", approval_path=approval)
    pilot = json.loads(approval.read_bytes())
    assert len(pilot["slots"]) == 6
    assert sum(s["caps"]["micro_cny"] for s in pilot["slots"]) == 150000000
    for index, slot in enumerate(pilot["slots"]):
        caps = BudgetCaps.model_validate(slot["caps"])
        key = store.enroll_live(slot["purpose"], slot["seed"], HASH, f"case-{index}", caps)
        original = (root / "allocations" / (key + ".json")).read_bytes()
        assert store.enroll_live(slot["purpose"], slot["seed"], HASH, f"case-{index}", caps) == key
        assert (root / "allocations" / (key + ".json")).read_bytes() == original
        assert_code(
            "ALLOCATION_ALREADY_ENROLLED",
            lambda slot=slot, index=index, caps=caps: store.enroll_live(
                slot["purpose"], slot["seed"], "9" * 64, f"case-{index}", caps
            ),
        )
    first = allocation_key(HASH, "case-0")
    with store.open_case(first, LIVE_PRICE, None, lambda h: None):
        pass
    assert_code(
        "ALLOCATION_ALREADY_ENROLLED",
        lambda: store.enroll_live("smoke", 1292387875, HASH, "case-0", SMOKE),
    )
    (root / "allocations" / (first + ".json")).unlink()
    assert_code(
        "ALLOCATION_UNAVAILABLE",
        lambda: store.enroll_live("smoke", 1292387875, HASH, "case-0", SMOKE),
    )
    assert_code(
        "ALLOCATION_ALREADY_ENROLLED", lambda: initialize_pilot(approval, tmp_path / "new-root")
    )
    assert not (tmp_path / "new-root").exists()


def test_pilot_refuses_unknown_changed_missing_and_fake_access(tmp_path):
    root, approval = tmp_path / "authority", tmp_path / "approval.json"
    initialize_pilot(approval, root)
    store = AllocationStore(root, mode="live", approval_path=approval)
    assert_code(
        "ALLOCATION_UNAVAILABLE", lambda: store.enroll_live("smoke", 1, HASH, "case", SMOKE)
    )
    assert_code(
        "ALLOCATION_UNAVAILABLE", lambda: store.enroll_live("smoke", 1292387875, HASH, "case", CAPS)
    )
    assert_code("ALLOCATION_UNAVAILABLE", lambda: store.enroll_fake(HASH, "case", CAPS))
    assert_code("ALLOCATION_UNAVAILABLE", lambda: AllocationStore(root, mode="fake"))
    approved = approval.read_bytes()
    fake = tmp_path / "fake"
    initialize_fake(fake)
    f = AllocationStore(fake, mode="fake")
    f.enroll_fake(HASH, "case", CAPS)
    assert_code(
        "ALLOCATION_UNAVAILABLE", lambda: f.enroll_live("smoke", 1292387875, HASH, "case", SMOKE)
    )
    assert approval.read_bytes() == approved
    approval.unlink()
    assert_code(
        "ALLOCATION_UNAVAILABLE",
        lambda: store.enroll_live("smoke", 1292387875, HASH, "case", SMOKE),
    )


@pytest.mark.parametrize("operation", ["slot_bind", "case_initialize", "slot_issue"])
@pytest.mark.parametrize("phase", ["before_write", "after_flush", "after_replace"])
def test_pilot_enrollment_process_crash_each_durable_phase(tmp_path, operation, phase):
    root, approval = tmp_path / "authority", tmp_path / "approval.json"
    initialize_pilot(approval, root)
    process = child(
        tmp_path,
        "def fault(stage):\n if stage == sys.argv[3]: os._exit(73)\n"
        "store=AllocationStore(base/'authority',mode='live',approval_path=base/'approval.json',fault=fault)\n"
        "store.enroll_live('smoke',1292387875,HASH,'case',SMOKE)\n",
        operation + ":" + phase,
    )
    finish(process, 73)
    store = AllocationStore(root, mode="live", approval_path=approval)
    key = store.enroll_live("smoke", 1292387875, HASH, "case", SMOKE)
    case = CaseAllocationP3.model_validate_json(
        (root / "allocations" / (key + ".json")).read_bytes()
    )
    assert case.generation == 0 and case.entries == [] and case.caps == SMOKE
    slots = json.loads(approval.read_bytes())["slots"]
    assert sum(s["binding"] is not None for s in slots) == 1
    assert slots[0]["binding"]["state"] == "issued"
    assert len(list((root / "allocations").glob("*.json"))) == 1


def test_pilot_enrollment_real_two_process_competition(tmp_path):
    root, approval = tmp_path / "authority", tmp_path / "approval.json"
    initialize_pilot(approval, root)
    first = child(
        tmp_path,
        "def fault(stage):\n if stage == 'slot_bind:after_replace':\n"
        "  print('HELD',flush=True)\n  sys.stdin.readline()\n"
        "s=AllocationStore(base/'authority',mode='live',approval_path=base/'approval.json',fault=fault)\n"
        "s.enroll_live('smoke',1292387875,HASH,'case',SMOKE)\n",
    )
    try:
        assert first.stdout.readline().strip() == "HELD"
        second = child(
            tmp_path,
            "s=AllocationStore(base/'authority',mode='live',approval_path=base/'approval.json')\n"
            "try:\n s.enroll_live('smoke',1292387875,HASH,'case',SMOKE)\n"
            "except AllocationError as e:\n print(e.code)\n",
        )
        assert finish(second) == "ALLOCATION_BUSY"
        first.stdin.write("continue\n")
        first.stdin.flush()
        finish(first)
        pilot = json.loads(approval.read_bytes())
        assert sum(s["binding"] is not None for s in pilot["slots"]) == 1
        assert len(list((root / "allocations").glob("*.json"))) == 1
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=30)


def test_offline_zero_suffix_requires_latch_and_stays_offline(tmp_path):
    h = Harness(tmp_path)
    with h.open(offline=True) as s:
        head, _ = h.candidate(1, [], live=False)
        assert_code("ALLOCATION_INTEGRITY", lambda: s.prepare(head, []))
        origin, evidence, entries = recovery_origin(s)
        s.latch_recovery(origin, evidence, entries)
        head = h.publish(s, 1, [], live=False)
    assert_code("ALLOCATION_CLOSED", lambda: h.open(head))
    with h.open(head, offline=True) as s:
        assert s.pending_recovery() is None
        h.publish(s, 2, [], live=False)


def test_invalid_terminal_debits_cannot_release_reservations(tmp_path):
    h = Harness(tmp_path)
    s = h.open()
    reservation = s.admit(CALL, 100, 20, REQUEST, WIRE)
    debit = charge(reservation)
    cheap = CallDebit.model_validate({**debit.model_dump(mode="json"), "money_charged": 0})
    assert_code("ALLOCATION_INTEGRITY", lambda: s.commit(DECISION, [cheap]))
    overrun = charge(reservation, inputs=101, outputs=10)
    assert_code("ALLOCATION_OVERRUN", lambda: s.commit(DECISION, [overrun]))
    assert s.snapshot().entries[0].state == "reserved"
    assert s.export_ledger().attempts_charged == 0
    s.close(clean=False)


def test_dispatch_requires_matching_durable_reservation_and_owner(tmp_path):
    import base64

    from living_island.agents.p3.types import (
        AttemptDispatch,
        ProviderRequest,
        ProviderSettings,
        SystemMessage,
        UserMessage,
        WireRequest,
    )
    from living_island.memory.p3_types import canonical_sha256

    caps = BudgetCaps(attempts=2, input_tokens=200, output_tokens=4096, micro_cny=30000)
    h = Harness(tmp_path, caps=caps)
    request = ProviderRequest(
        provider_request_version="0.1",
        model_id="fake",
        messages=[
            SystemMessage(role="system", content="fixture"),
            UserMessage(role="user", content="fixture"),
        ],
        response_schema={},
        settings=ProviderSettings(
            api="deepseek-responses",
            reasoning_effort="none",
            store=False,
            tools=[],
            background=False,
            stream=False,
            input_counter_id="fake",
            input_counter_version="1",
        ),
        max_output_tokens=2048,
    )
    wire = WireRequest(
        wire_schema_version="0.1",
        method="POST",
        origin="https://api.deepseek.com",
        path="/responses",
        content_type="application/json",
        body_base64=base64.b64encode(b"{}").decode(),
    )
    dispatch = AttemptDispatch(
        dispatch_schema_version="0.1",
        run_id="test",
        decision_id=DECISION,
        call_id=CALL,
        actor_id="ella",
        tick=0,
        decision_ordinal=0,
        attempt_index=0,
        request_sha256=HASH,
        context_sha256=HASH,
        projection_sha256=HASH,
        provider_request_sha256=canonical_sha256(request),
        provider_request=request,
        wire_request=wire,
        wire_body_sha256=hashlib.sha256(b"{}").hexdigest(),
        allocation_key=h.key,
        reservation_ordinal=0,
        prompt_version="p3-resident/0.1",
        action_schema_version="p3-actions/0.2",
        adapter_id="fake",
        adapter_version="1",
        model_id="fake",
        input_reserved=100,
        output_reserved=2048,
        money_reserved=reserved_money(PRICE, 100, 2048),
    )
    s = h.open()
    assert_code("ALLOCATION_INTEGRITY", lambda: s.verify_reservation(dispatch))
    s.admit(CALL, 100, 2048, dispatch.provider_request_sha256, dispatch.wire_body_sha256)
    assert h.raw().entries[0].reservation.money_reserved == dispatch.money_reserved
    s.verify_reservation(dispatch)
    bad = AttemptDispatch.model_validate({**dispatch.model_dump(mode="json"), "money_reserved": 1})
    assert_code("ALLOCATION_INTEGRITY", lambda: s.verify_reservation(bad))
    s.close(clean=False)
    assert_code("ALLOCATION_STALE", lambda: s.verify_reservation(dispatch))


@pytest.mark.parametrize(
    "stage", ["generation:before_write", "generation:after_flush", "generation:after_replace"]
)
def test_generation_crash_keeps_original_grant(tmp_path, stage):
    h = Harness(tmp_path)
    process = child(
        tmp_path,
        "h=Harness(base, create=False)\n"
        "def fault(stage):\n if stage == sys.argv[3]: os._exit(73)\n"
        "h.open(fault=fault)\n",
        stage,
    )
    finish(process, 73)
    with h.open() as s:
        assert s.snapshot().entries == [] and s.snapshot().caps == CAPS
        assert s.export_ledger().money_charged == 0


def test_lost_or_corrupt_pilot_record_never_reenrolls(tmp_path):
    root, approval = tmp_path / "authority", tmp_path / "approval.json"
    initialize_pilot(approval, root)
    store = AllocationStore(root, mode="live", approval_path=approval)
    original = approval.read_bytes()
    approval.write_bytes(original + b" ")
    assert_code(
        "ALLOCATION_INTEGRITY", lambda: store.enroll_live("smoke", 1292387875, HASH, "case", SMOKE)
    )
    assert not (root / "allocations").exists()
    approval.write_bytes(original)
    copied = tmp_path / "copy-authority"
    shutil.copytree(root, copied)
    assert_code(
        "ALLOCATION_UNAVAILABLE",
        lambda: AllocationStore(copied, mode="live", approval_path=approval),
    )


# Independent historical identities and charges for the CR-007 fixture.
ORIGINAL_SMOKE_SHA = "dcb337f07601f6c1b1abe9fd0a61f410a713a6caf26bcc7e4e7cf0d25e65ca5f"
ORIGINAL_SMOKE_CASE = "p3-smoke-r1.s1292387875"
REPLACEMENT_SHA = "a" * 64


def completed_original_smoke(root, approval):
    """Create a fixture pilot and publish the original ledger through real sessions."""
    initialize_pilot(approval, root)
    store = AllocationStore(root, mode="live", approval_path=approval)
    key = store.enroll_live("smoke", 1292387875, ORIGINAL_SMOKE_SHA, ORIGINAL_SMOKE_CASE, SMOKE)
    fixture = Harness.__new__(Harness)
    fixture.run = root.parent / "original-run"
    with store.open_case(key, LIVE_PRICE, None, fixture.verify) as session:
        fixture.publish(session, 0, [])
        entries = []
        for index in range(14):
            call = f"test:d:ella:{index:06d}:a0"
            inputs = 24299 if index < 13 else 24305
            reservation = session.admit(call, inputs, 2048, REQUEST, WIRE)
            assert reservation is not None
            debit = CallDebit(
                call_id=call,
                input_reserved=inputs,
                output_reserved=2048,
                money_reserved=reserved_money(LIVE_PRICE, inputs, 2048),
                input_reported=None,
                output_reported=None,
                input_charged=inputs,
                output_charged=2048,
                money_charged=reserved_money(LIVE_PRICE, inputs, 2048),
                usage_unknown=True,
            )
            session.commit(call.rsplit(":a", 1)[0], [debit])
            entries.append(
                session.snapshot()
                .entries[-1]
                .model_copy(
                    update={"state": "settled", "debit": debit, "terminal_call_sha256": TERMINAL}
                )
            )
        fixture.publish(session, 24, entries, complete=True)
    return store, root / "allocations" / f"{key}.json"


@pytest.fixture
def completed_smoke(tmp_path):
    return completed_original_smoke(tmp_path / "authority", tmp_path / "approval.json")


def authorize_replacement(store, original, digest):
    return store.authorize_replacement_smoke(
        digest, hashlib.sha256(original.read_bytes()).hexdigest()
    )


def test_replacement_requires_explicit_binding_and_keeps_original_bytes(completed_smoke):
    store, original = completed_smoke
    approval = store.approval_path
    before = {p: p.read_bytes() for p in (approval, original)}
    key = allocation_key(REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE)
    case_path = store.root / "allocations" / f"{key}.json"
    args = REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE, REPLACEMENT_SMOKE_CAPS
    assert_code("ALLOCATION_UNAVAILABLE", lambda: store.enroll_replacement_smoke(*args))
    assert_code(
        "ALLOCATION_UNAVAILABLE",
        lambda: store.enroll_live(
            "smoke", 1292387875, REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE, SMOKE
        ),
    )
    assert_code(
        "ALLOCATION_INTEGRITY", lambda: store.authorize_replacement_smoke(REPLACEMENT_SHA, "b" * 64)
    )
    assert authorize_replacement(store, original, REPLACEMENT_SHA) == key
    assert not case_path.exists()
    assert_code("ALLOCATION_UNAVAILABLE", lambda: store._read_case(key))
    assert_code(
        "ALLOCATION_ALREADY_ENROLLED", lambda: authorize_replacement(store, original, "b" * 64)
    )
    assert_code(
        "ALLOCATION_ALREADY_ENROLLED",
        lambda: store.enroll_replacement_smoke(REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE, SMOKE),
    )
    assert store.enroll_replacement_smoke(*args) == key
    assert store.enroll_replacement_smoke(*args) == key
    assert authorize_replacement(store, original, REPLACEMENT_SHA) == key
    assert {p: p.read_bytes() for p in before} == before
    assert store._read_case(key).caps == REPLACEMENT_SMOKE_CAPS
    with store.open_case(key, LIVE_PRICE, None, lambda head: None):
        pass
    assert_code("ALLOCATION_ALREADY_ENROLLED", lambda: store.enroll_replacement_smoke(*args))
    case_path.unlink()
    assert_code("ALLOCATION_UNAVAILABLE", lambda: store.enroll_replacement_smoke(*args))
    assert_code(
        "ALLOCATION_UNAVAILABLE", lambda: authorize_replacement(store, original, REPLACEMENT_SHA)
    )
    assert not case_path.exists()


@pytest.mark.parametrize("loss", ["authorization", "old allocation", "corruption", "old mutation"])
def test_replacement_refuses_lost_or_modified_authority(completed_smoke, loss):
    store, original = completed_smoke
    key = authorize_replacement(store, original, REPLACEMENT_SHA)
    store.enroll_replacement_smoke(REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE, REPLACEMENT_SMOKE_CAPS)
    record = store.root / "smoke-replacement.json"
    if loss == "authorization":
        record.unlink()
    elif loss == "old allocation":
        original.unlink()
    elif loss == "corruption":
        record.write_bytes(b"bad JSON")
    else:
        raw = json.loads(original.read_bytes())
        raw["generation"] += 1
        original.write_bytes(canonical_bytes(raw))
    assert_code(
        "ALLOCATION_UNAVAILABLE"
        if loss in {"authorization", "old allocation"}
        else "ALLOCATION_INTEGRITY",
        lambda: store._read_case(key),
    )
    with pytest.raises(AllocationError):
        store.authorize_replacement_smoke("b" * 64, "c" * 64)


def test_replacement_refuses_incomplete_or_unapproved_original(completed_smoke):
    store, original = completed_smoke
    raw = json.loads(original.read_bytes())
    raw["status"] = "running"
    original.write_bytes(canonical_bytes(raw))
    assert_code(
        "ALLOCATION_INTEGRITY", lambda: authorize_replacement(store, original, REPLACEMENT_SHA)
    )
    raw["status"] = "complete"
    raw["entries"][-1]["debit"]["money_charged"] += 1
    original.write_bytes(canonical_bytes(raw))
    assert_code(
        "ALLOCATION_INTEGRITY", lambda: authorize_replacement(store, original, REPLACEMENT_SHA)
    )
    assert not (store.root / "smoke-replacement.json").exists()


_REPLACEMENT_CHILD_STORE = (
    "s=AllocationStore(base/'authority',mode='live',approval_path=base/'approval.json',"
    "fault=fault)\n"
    "original=base/'authority'/'allocations'/(allocation_key(ORIGINAL_SMOKE_SHA,"
    "ORIGINAL_SMOKE_CASE)+'.json')\n"
)
_REPLACEMENT_CHILD_ENROLL = (
    "s.enroll_replacement_smoke(REPLACEMENT_SHA,REPLACEMENT_SMOKE_CASE,REPLACEMENT_SMOKE_CAPS)\n"
)


@pytest.mark.parametrize("operation", ["replacement_bind", "case_initialize", "replacement_issue"])
@pytest.mark.parametrize("phase", ["before_write", "after_flush", "after_replace"])
def test_replacement_crash_retry_at_every_durable_stage(
    tmp_path, completed_smoke, operation, phase
):
    store, original = completed_smoke
    old_bytes = original.read_bytes()
    approval_bytes = store.approval_path.read_bytes()
    if operation == "replacement_bind":
        action = "authorize_replacement(s, original, REPLACEMENT_SHA)\n"
    else:
        authorize_replacement(store, original, REPLACEMENT_SHA)
        action = _REPLACEMENT_CHILD_ENROLL
    process = child(
        tmp_path,
        "def fault(stage):\n if stage == sys.argv[3]: os._exit(73)\n"
        + _REPLACEMENT_CHILD_STORE
        + action,
        f"{operation}:{phase}",
    )
    finish(process, 73)
    key = authorize_replacement(store, original, REPLACEMENT_SHA)
    assert (
        store.enroll_replacement_smoke(
            REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE, REPLACEMENT_SMOKE_CAPS
        )
        == key
    )
    assert store._read_case(key).generation == 0
    assert len(list((store.root / "allocations").glob("*.json"))) == 2
    assert original.read_bytes() == old_bytes
    assert store.approval_path.read_bytes() == approval_bytes


def test_replacement_competing_processes_share_the_enrollment_lock(tmp_path, completed_smoke):
    store, original = completed_smoke
    first = child(
        tmp_path,
        "def fault(stage):\n if stage == 'replacement_bind:after_replace':\n"
        "  print('HELD',flush=True)\n  sys.stdin.readline()\n"
        + _REPLACEMENT_CHILD_STORE
        + "authorize_replacement(s, original, REPLACEMENT_SHA)\n",
    )
    try:
        assert first.stdout.readline().strip() == "HELD"
        second = child(
            tmp_path,
            "fault=None\n"
            + _REPLACEMENT_CHILD_STORE
            + "try:\n authorize_replacement(s, original, 'b'*64)\n"
            "except AllocationError as e:\n print(e.code)\n",
        )
        assert finish(second) == "ALLOCATION_BUSY"
        first.stdin.write("continue\n")
        first.stdin.flush()
        finish(first)
        key = store.enroll_replacement_smoke(
            REPLACEMENT_SHA, REPLACEMENT_SMOKE_CASE, REPLACEMENT_SMOKE_CAPS
        )
        assert store._read_case(key).status == "ready"
        assert len(list((store.root / "allocations").glob("*.json"))) == 2
    finally:
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=30)
