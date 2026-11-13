"""Durable, process-exclusive P3 allocation authority; never used by replay.

The enrollment journal issues each approved pilot slot once. A case lock is held
for an entire continuation. Reservations remain fully charged until a verified
checkpoint publication replaces them with terminal debits.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, NoReturn, Self, cast

from pydantic import model_validator

from living_island.agents.p3.types import (
    AllocationEntry,
    AllocationHead,
    AttemptDispatch,
    BudgetCaps,
    BudgetLedgerP3,
    CallDebit,
    CallReservation,
    CaseAllocationP3,
    P3Model,
    PricingPin,
    build_call_id,
)
from living_island.memory.p3_types import canonical_bytes, canonical_sha256
from living_island.world.protocol import Sha256Hex

Fault = Callable[[str], None]

REPLACEMENT_SMOKE_ID = "p3-smoke-u3-r1"
REPLACEMENT_SMOKE_SEED = 1292387875
REPLACEMENT_SMOKE_CASE = f"{REPLACEMENT_SMOKE_ID}.s{REPLACEMENT_SMOKE_SEED}"
REPLACEMENT_SMOKE_CAPS = BudgetCaps(
    attempts=34, input_tokens=1114112, output_tokens=69632, micro_cny=2785280
)
_ORIGINAL_SMOKE_CASE = "p3-smoke-r1.s1292387875"
_ORIGINAL_SMOKE_REGISTRATION = "dcb337f07601f6c1b1abe9fd0a61f410a713a6caf26bcc7e4e7cf0d25e65ca5f"
_ORIGINAL_SMOKE_CHARGED = {
    "attempts": 14,
    "input_tokens": 340192,
    "output_tokens": 28672,
    "micro_cny": 909760,
}
_REPLACEMENT_RECORD = "smoke-replacement.json"
U4_SMOKE_ID = "p3-smoke-u4-r1"
U4_SMOKE_CASE = f"{U4_SMOKE_ID}.s{REPLACEMENT_SMOKE_SEED}"
U4_SMOKE_CAPS = BudgetCaps(
    attempts=34, input_tokens=1114112, output_tokens=69275, micro_cny=3000000
)
_U4_RECORD = "smoke-u4-replacement.json"
_PRIOR_REPLACEMENT_REGISTRATION = "7e63f9d2fe41330f262e409bf942186aedbbfd5d829d65e54c5e580bb161081e"
_PRIOR_REPLACEMENT_CHARGED = (2, 29124, 357, 61104)


class AllocationError(ValueError):
    """Stable machine-readable refusal without exposing external data."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def _fail(code: str, detail: str = "") -> NoReturn:
    raise AllocationError(code, detail)


def _locator(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def allocation_key(registration_sha256: str, case_id: str) -> str:
    return canonical_sha256({"registration_sha256": registration_sha256, "case_id": case_id})


def reserved_money(pricing: PricingPin, input_tokens: int, output_tokens: int) -> int:
    if any(type(n) is not int or n < 0 for n in (input_tokens, output_tokens)):
        raise ValueError("token counts must be nonnegative integers")
    return (input_tokens * pricing.input_micro_cny_per_million_tokens + 999999) // 1000000 + (
        output_tokens * pricing.output_micro_cny_per_million_tokens + 999999
    ) // 1000000


def _fault(fault: Fault | None, stage: str) -> None:
    if fault is not None:
        fault(stage)


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _replace(source: Path, target: Path) -> None:
    if sys.platform == "win32":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        replace = kernel.MoveFileExW
        replace.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
        replace.restype = ctypes.c_int
        if not replace(str(source), str(target), 0x1 | 0x8):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, target)
        _sync_directory(target.parent)


def _atomic_write(path: Path, data: bytes, fault: Fault | None, stage: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _fault(fault, stage + ":before_write")
    fd, name = tempfile.mkstemp(prefix=".allocation-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _fault(fault, stage + ":after_flush")
        _replace(temporary, path)
        _fault(fault, stage + ":after_replace")
    finally:
        if temporary.exists():
            temporary.unlink()


def _create_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(path.parent)
    except FileExistsError:
        _fail("ALLOCATION_ALREADY_ENROLLED")


def _decode(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate object key")
            result[key] = value
        return result

    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    if canonical_bytes(value) != data:
        raise ValueError("authority bytes must be canonical")
    return value


def _read[T: P3Model](path: Path, model: type[T]) -> T:
    try:
        return model.model_validate(_decode(path.read_bytes()))
    except OSError as exc:
        raise AllocationError("ALLOCATION_UNAVAILABLE") from exc
    except ValueError as exc:
        raise AllocationError("ALLOCATION_INTEGRITY") from exc


class _ProcessLock:
    """A stable inode/Windows file handle, with no lease or time-based takeover."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None
        self.pid = os.getpid()

    def acquire(self) -> None:
        try:
            fd = os.open(self.path, os.O_RDWR | getattr(os, "O_BINARY", 0))
        except OSError as exc:
            raise AllocationError("ALLOCATION_UNAVAILABLE", "missing stable lock") from exc
        try:
            if os.fstat(fd).st_size != 1:
                _fail("ALLOCATION_INTEGRITY", "invalid stable lock")
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise AllocationError("ALLOCATION_BUSY") from exc
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        try:
            self.check()
        except BaseException:
            self.release()
            raise

    def check(self) -> None:
        if self.fd is None or self.pid != os.getpid():
            _fail("ALLOCATION_STALE", "process does not own the lock")
        try:
            opened, current = os.fstat(self.fd), self.path.stat()
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                _fail("ALLOCATION_STALE", "stable lock identity changed")
        except OSError as exc:
            raise AllocationError("ALLOCATION_UNAVAILABLE") from exc

    def release(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        try:
            if self.pid == os.getpid():
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


class _Root(P3Model):
    root_version: Literal["0.1"]
    authority_root: str
    mode: Literal["live", "fake"]
    approval_path: str | None


class _Binding(P3Model):
    registration_sha256: Sha256Hex
    case_id: str
    allocation_key: Sha256Hex
    caps: BudgetCaps
    state: Literal["initializing", "issued"]

    @model_validator(mode="after")
    def _key(self) -> Self:
        if self.allocation_key != allocation_key(self.registration_sha256, self.case_id):
            raise ValueError("binding key mismatch")
        return self


class _Slot(P3Model):
    purpose: Literal["smoke", "development", "acceptance"]
    seed: int
    caps: BudgetCaps
    binding: _Binding | None


def _pilot_slots() -> list[_Slot]:
    return [
        _Slot(
            purpose=cast(Literal["smoke", "development", "acceptance"], purpose),
            seed=seed,
            caps=BudgetCaps(
                attempts=attempts, input_tokens=inputs, output_tokens=outputs, micro_cny=money
            ),
            binding=None,
        )
        for purpose, seed, attempts, inputs, outputs, money in (
            ("smoke", 1292387875, 48, 1572864, 98304, 5000000),
            ("development", 509071611, 288, 9437184, 589824, 20000000),
            ("development", 1945790632, 288, 9437184, 589824, 20000000),
            ("acceptance", 401604645, 864, 28311552, 1769472, 35000000),
            ("acceptance", 4054202024, 864, 28311552, 1769472, 35000000),
            ("acceptance", 538041037, 864, 28311552, 1769472, 35000000),
        )
    ]


class _Pilot(P3Model):
    approval_version: Literal["0.1"]
    approval_path: str
    authority_root: str
    ceiling_micro_cny: Literal[150000000]
    slots: list[_Slot]

    @model_validator(mode="after")
    def _slots(self) -> Self:
        expected = _pilot_slots()
        if [(s.purpose, s.seed, s.caps) for s in self.slots] != [
            (s.purpose, s.seed, s.caps) for s in expected
        ]:
            raise ValueError("pilot slots must equal the six approved allocations")
        keys = [s.binding.allocation_key for s in self.slots if s.binding is not None]
        if len(set(keys)) != len(keys) or any(
            s.binding is not None and s.binding.caps != s.caps for s in self.slots
        ):
            raise ValueError("pilot binding duplicated or caps changed")
        return self


class _ReplacementSmoke(P3Model):
    replacement_version: Literal["0.1"]
    authority_root: str
    original_allocation_key: Sha256Hex
    original_allocation_sha256: Sha256Hex
    binding: _Binding


class _FakeEnrollments(P3Model):
    enrollment_version: Literal["0.1"]
    authority_root: str
    bindings: list[_Binding]

    @model_validator(mode="after")
    def _bindings(self) -> Self:
        keys = [b.allocation_key for b in self.bindings]
        if keys != sorted(set(keys)):
            raise ValueError("fake enrollments must be sorted and unique")
        return self


def _new_root(root: Path, mode: Literal["live", "fake"], approval: Path | None) -> None:
    if root.exists() and any(root.iterdir()):
        _fail("ALLOCATION_ALREADY_ENROLLED")
    root.mkdir(parents=True, exist_ok=True)
    _create_once(root / "enrollment.lock", b"\0")
    _create_once(
        root / "authority-root.json",
        canonical_bytes(
            _Root(
                root_version="0.1",
                authority_root=_locator(root),
                mode=mode,
                approval_path=None if approval is None else _locator(approval),
            )
        ),
    )


def initialize_pilot(
    approval_path: Path, authority_root: Path, *, fault: Fault | None = None
) -> None:
    """Explicit initial authorization only; never called by run, resume or replay."""
    approval_path, authority_root = approval_path.resolve(), authority_root.resolve()
    if approval_path.exists():
        _fail("ALLOCATION_ALREADY_ENROLLED")
    _new_root(authority_root, "live", approval_path)
    with _ProcessLock(authority_root / "enrollment.lock"):
        _fault(fault, "pilot:before_write")
        _create_once(
            approval_path,
            canonical_bytes(
                _Pilot(
                    approval_version="0.1",
                    approval_path=_locator(approval_path),
                    authority_root=_locator(authority_root),
                    ceiling_micro_cny=150000000,
                    slots=_pilot_slots(),
                )
            ),
        )
        _fault(fault, "pilot:after_write")


def initialize_fake(authority_root: Path, *, fault: Fault | None = None) -> None:
    """Create an isolated fixture authority with no live-approval access."""
    authority_root = authority_root.resolve()
    _new_root(authority_root, "fake", None)
    with _ProcessLock(authority_root / "enrollment.lock"):
        _atomic_write(
            authority_root / "fake-enrollments.json",
            canonical_bytes(
                _FakeEnrollments(
                    enrollment_version="0.1", authority_root=_locator(authority_root), bindings=[]
                )
            ),
            fault,
            "fake_initialize",
        )


@dataclass(frozen=True)
class VerifiedCheckpoint:
    head: AllocationHead
    entries: Sequence[AllocationEntry]
    live_enabled: bool
    complete: bool


CheckpointVerifier = Callable[[AllocationHead], VerifiedCheckpoint | None]


class AllocationStore:
    """Locate existing enrolled authorities; constructing a store never grants budget."""

    def __init__(
        self,
        authority_root: Path,
        *,
        mode: Literal["live", "fake"],
        approval_path: Path | None = None,
        fault: Fault | None = None,
    ) -> None:
        self.root = authority_root.resolve()
        self.mode = mode
        self.approval_path = None if approval_path is None else approval_path.resolve()
        self.fault = fault
        self._root()

    def _root(self) -> None:
        root = _read(self.root / "authority-root.json", _Root)
        if (root.authority_root, root.mode, root.approval_path) != (
            _locator(self.root),
            self.mode,
            None if self.approval_path is None else _locator(self.approval_path),
        ):
            _fail("ALLOCATION_UNAVAILABLE", "authority root binding mismatch")
        if (self.mode == "live") != (self.approval_path is not None):
            _fail("ALLOCATION_UNAVAILABLE", "mode requires its enrolled approval path")

    def _pilot(self) -> _Pilot:
        if self.mode != "live" or self.approval_path is None:
            _fail("ALLOCATION_UNAVAILABLE", "fake authorities cannot access pilot approval")
        self._root()
        pilot = _read(self.approval_path, _Pilot)
        if (pilot.authority_root, pilot.approval_path) != (
            _locator(self.root),
            _locator(self.approval_path),
        ):
            _fail("ALLOCATION_UNAVAILABLE", "pilot root binding mismatch")
        return pilot

    def _fake(self) -> _FakeEnrollments:
        if self.mode != "fake":
            _fail("ALLOCATION_UNAVAILABLE", "live authorities cannot enroll fake cases")
        self._root()
        result = _read(self.root / "fake-enrollments.json", _FakeEnrollments)
        if result.authority_root != _locator(self.root):
            _fail("ALLOCATION_UNAVAILABLE")
        return result

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            _fail("ALLOCATION_INTEGRITY", "invalid allocation key")
        return self.root / "allocations" / (key + ".json")

    def _binding(self, key: str) -> _Binding:
        pilot = self._pilot() if self.mode == "live" else None
        candidates = (
            [s.binding for s in pilot.slots if s.binding is not None]
            if pilot is not None
            else self._fake().bindings
        )
        matches = [b for b in candidates if b.allocation_key == key and b.state == "issued"]
        if matches:
            return matches[0]
        if pilot is not None:
            replacement = self._replacement(pilot)
            binding = replacement.binding
            if binding.allocation_key != key:
                binding = self._u4_replacement(pilot).binding
            if binding.allocation_key == key and binding.state == "issued":
                if not self._path(key).with_suffix(".lock").is_file():
                    _fail("ALLOCATION_UNAVAILABLE", "issued replacement lock is missing")
                return binding
        _fail("ALLOCATION_UNAVAILABLE", "case has not been issued")

    def _read_case(self, key: str) -> CaseAllocationP3:
        return self._bound_case(self._binding(key))

    def _bound_case(self, binding: _Binding) -> CaseAllocationP3:
        key = binding.allocation_key
        case = _read(self._path(key), CaseAllocationP3)
        if (case.allocation_key, case.registration_sha256, case.case_id, case.caps) != (
            key,
            binding.registration_sha256,
            binding.case_id,
            binding.caps,
        ):
            _fail("ALLOCATION_INTEGRITY", "case enrollment mismatch")
        return case

    def _initial_case(self, binding: _Binding) -> None:
        initial = CaseAllocationP3(
            allocation_schema_version="0.1",
            allocation_key=binding.allocation_key,
            registration_sha256=binding.registration_sha256,
            case_id=binding.case_id,
            caps=binding.caps,
            generation=0,
            status="ready",
            head=None,
            prepared_head=None,
            pending_recovery_sha256=None,
            entries=[],
        )
        path = self._path(binding.allocation_key)
        lock = path.with_suffix(".lock")
        if path.exists():
            if _read(path, CaseAllocationP3) != initial or not lock.exists():
                _fail("ALLOCATION_ALREADY_ENROLLED", "initializing authority is not empty")
            return
        if not lock.exists():
            _create_once(lock, b"\0")
        _atomic_write(path, canonical_bytes(initial), self.fault, "case_initialize")

    def enroll_live(
        self, purpose: str, seed: int, registration_sha256: str, case_id: str, caps: BudgetCaps
    ) -> str:
        self._pilot()
        if case_id in {REPLACEMENT_SMOKE_CASE, U4_SMOKE_CASE}:
            _fail("ALLOCATION_UNAVAILABLE", "replacement requires linked authorization")
        key = allocation_key(registration_sha256, case_id)
        wanted = _Binding(
            registration_sha256=registration_sha256,
            case_id=case_id,
            allocation_key=key,
            caps=caps,
            state="initializing",
        )
        with _ProcessLock(self.root / "enrollment.lock"):
            pilot = self._pilot()
            matches = [
                i
                for i, slot in enumerate(pilot.slots)
                if (slot.purpose, slot.seed) == (purpose, seed)
            ]
            if len(matches) != 1 or pilot.slots[matches[0]].caps != caps:
                _fail("ALLOCATION_UNAVAILABLE", "not an approved pilot slot/caps")
            index = matches[0]
            binding = pilot.slots[index].binding
            if binding is not None:
                if binding.model_dump(exclude={"state"}) != wanted.model_dump(exclude={"state"}):
                    _fail("ALLOCATION_ALREADY_ENROLLED", "slot already bound")
                if binding.state == "issued":
                    case = self._read_case(key)
                    if case.generation or case.head is not None or case.entries:
                        _fail("ALLOCATION_ALREADY_ENROLLED", "slot already consumed")
                    return key
            else:
                raw = pilot.model_dump(mode="json")
                raw["slots"][index]["binding"] = wanted.model_dump(mode="json")
                pilot = _Pilot.model_validate(raw)
                assert self.approval_path is not None
                _atomic_write(self.approval_path, canonical_bytes(pilot), self.fault, "slot_bind")
            self._initial_case(wanted)
            raw = pilot.model_dump(mode="json")
            raw["slots"][index]["binding"]["state"] = "issued"
            assert self.approval_path is not None
            _atomic_write(
                self.approval_path,
                canonical_bytes(_Pilot.model_validate(raw)),
                self.fault,
                "slot_issue",
            )
            return key

    def _original_smoke(self, pilot: _Pilot) -> CaseAllocationP3:
        slot = next(s for s in pilot.slots if s.purpose == "smoke")
        binding = slot.binding
        if (
            binding is None
            or binding.state != "issued"
            or binding.case_id != _ORIGINAL_SMOKE_CASE
            or binding.registration_sha256 != _ORIGINAL_SMOKE_REGISTRATION
        ):
            _fail("ALLOCATION_UNAVAILABLE", "original smoke binding unavailable")
        case = self._bound_case(binding)
        if (
            case.status != "complete"
            or case.head is None
            or case.head.checkpoint_tick != 24
            or case.head.reservation_cursor != len(case.entries)
            or case.prepared_head is not None
            or case.pending_recovery_sha256 is not None
        ):
            _fail("ALLOCATION_INTEGRITY", "original smoke must be settled and complete")
        ledger = ledger_from_entries(case.allocation_key, case.caps, case.entries)
        charged = {
            "attempts": ledger.attempts_charged,
            "input_tokens": ledger.input_charged,
            "output_tokens": ledger.output_charged,
            "micro_cny": ledger.money_charged,
        }
        if charged != _ORIGINAL_SMOKE_CHARGED or any(
            used + getattr(REPLACEMENT_SMOKE_CAPS, field) > getattr(case.caps, field)
            for field, used in charged.items()
        ):
            _fail("ALLOCATION_INTEGRITY", "replacement exceeds or disagrees with approved envelope")
        return case

    def _replacement_guard(self, filename: str = _REPLACEMENT_RECORD) -> Path:
        if self.approval_path is None:
            _fail("ALLOCATION_UNAVAILABLE", "replacement requires a live pilot")
        return self.approval_path.with_name(f"{Path(filename).stem}-guard.json")

    def _replacement(self, pilot: _Pilot, *, for_enrollment: bool = False) -> _ReplacementSmoke:
        original = self._original_smoke(pilot)
        return self._read_replacement(
            pilot,
            _REPLACEMENT_RECORD,
            original,
            REPLACEMENT_SMOKE_CASE,
            REPLACEMENT_SMOKE_CAPS,
            for_enrollment=for_enrollment,
        )

    def _u4_previous(self, pilot: _Pilot) -> CaseAllocationP3:
        binding = self._replacement(pilot).binding
        if (
            binding.state != "issued"
            or binding.registration_sha256 != _PRIOR_REPLACEMENT_REGISTRATION
        ):
            _fail("ALLOCATION_UNAVAILABLE", "prior replacement binding unavailable")
        original = self._original_smoke(pilot)
        for key in (original.allocation_key, binding.allocation_key):
            lock = self._path(key).with_suffix(".lock")
            try:
                size = lock.stat().st_size
            except OSError as exc:
                raise AllocationError("ALLOCATION_UNAVAILABLE", "predecessor lock missing") from exc
            if not lock.is_file() or size != 1:
                _fail("ALLOCATION_INTEGRITY", "invalid predecessor lock")
        previous = self._bound_case(binding)
        if (
            previous.status != "complete"
            or previous.head is None
            or previous.head.checkpoint_tick != 24
            or previous.head.reservation_cursor != len(previous.entries)
            or previous.prepared_head is not None
            or previous.pending_recovery_sha256 is not None
        ):
            _fail("ALLOCATION_INTEGRITY", "prior replacement must be settled and complete")
        ledger = ledger_from_entries(previous.allocation_key, previous.caps, previous.entries)
        charged = (
            ledger.attempts_charged,
            ledger.input_charged,
            ledger.output_charged,
            ledger.money_charged,
        )
        envelope = original.caps.model_dump()
        envelope["attempts"] = 50
        if charged != _PRIOR_REPLACEMENT_CHARGED or any(
            _ORIGINAL_SMOKE_CHARGED[field] + used + getattr(U4_SMOKE_CAPS, field) > envelope[field]
            for field, used in zip(
                ("attempts", "input_tokens", "output_tokens", "micro_cny"), charged, strict=True
            )
        ):
            _fail(
                "ALLOCATION_INTEGRITY", "U4 replacement exceeds or disagrees with approved envelope"
            )
        return previous

    def _u4_replacement(self, pilot: _Pilot, *, for_enrollment: bool = False) -> _ReplacementSmoke:
        return self._read_replacement(
            pilot,
            _U4_RECORD,
            self._u4_previous(pilot),
            U4_SMOKE_CASE,
            U4_SMOKE_CAPS,
            for_enrollment=for_enrollment,
        )

    def _read_replacement(
        self,
        pilot: _Pilot,
        filename: str,
        previous: CaseAllocationP3,
        case_id: str,
        caps: BudgetCaps,
        *,
        for_enrollment: bool,
    ) -> _ReplacementSmoke:
        record = _read(self.root / filename, _ReplacementSmoke)
        binding = record.binding
        if (
            record.authority_root != _locator(self.root)
            or record.original_allocation_key != previous.allocation_key
            or record.original_allocation_sha256 != canonical_sha256(previous)
            or binding.case_id != case_id
            or binding.registration_sha256 == previous.registration_sha256
            or any(
                slot.binding is not None
                and (
                    slot.binding.allocation_key == binding.allocation_key
                    or slot.binding.registration_sha256 == binding.registration_sha256
                )
                for slot in pilot.slots
            )
            or binding.caps != caps
        ):
            _fail("ALLOCATION_INTEGRITY", "replacement authorization mismatch")
        guard = _read(self._replacement_guard(filename), _ReplacementSmoke)
        if guard != record and not (
            for_enrollment
            and binding.state == "issued"
            and guard == self._with_replacement_state(record, "initializing")
        ):
            _fail("ALLOCATION_INTEGRITY", "replacement guard mismatch")
        return record

    @staticmethod
    def _with_replacement_state(
        record: _ReplacementSmoke, state: Literal["initializing", "issued"]
    ) -> _ReplacementSmoke:
        return record.model_copy(
            update={"binding": record.binding.model_copy(update={"state": state})}
        )

    def authorize_replacement_smoke(
        self, registration_sha256: str, original_allocation_sha256: str, *, u4: bool = False
    ) -> str:
        """Bind an explicitly approved registration before its separate enrollment."""
        with _ProcessLock(self.root / "enrollment.lock"):
            pilot = self._pilot()
            previous = self._u4_previous(pilot) if u4 else self._original_smoke(pilot)
            if canonical_sha256(previous) != original_allocation_sha256:
                _fail("ALLOCATION_INTEGRITY", "approved previous allocation hash differs")
            if registration_sha256 == previous.registration_sha256 or any(
                slot.binding is not None and registration_sha256 == slot.binding.registration_sha256
                for slot in pilot.slots
            ):
                _fail("ALLOCATION_INTEGRITY", "replacement must have a distinct registration")
            filename = _U4_RECORD if u4 else _REPLACEMENT_RECORD
            case_id = U4_SMOKE_CASE if u4 else REPLACEMENT_SMOKE_CASE
            caps = U4_SMOKE_CAPS if u4 else REPLACEMENT_SMOKE_CAPS
            key = allocation_key(registration_sha256, case_id)
            binding = _Binding(
                registration_sha256=registration_sha256,
                case_id=case_id,
                allocation_key=key,
                caps=caps,
                state="initializing",
            )
            expected = _ReplacementSmoke(
                replacement_version="0.1",
                authority_root=_locator(self.root),
                original_allocation_key=previous.allocation_key,
                original_allocation_sha256=original_allocation_sha256,
                binding=binding,
            )
            path = self.root / filename
            guard_path = self._replacement_guard(filename)
            if guard_path.exists():
                record = self._read_replacement(
                    pilot,
                    filename,
                    previous,
                    case_id,
                    caps,
                    for_enrollment=True,
                )
                if self._with_replacement_state(record, "initializing") != expected:
                    _fail("ALLOCATION_ALREADY_ENROLLED", "replacement already bound")
                if record.binding.state == "issued":
                    self._bound_case(record.binding)
                return key

            if not u4 and (
                (self.root / _U4_RECORD).exists() or self._replacement_guard(_U4_RECORD).exists()
            ):
                _fail("ALLOCATION_INTEGRITY", "successor exists without its predecessor guard")
            existing = {s.binding.allocation_key for s in pilot.slots if s.binding is not None}
            existing.add(previous.allocation_key)
            if any(
                file.stem not in existing
                for file in self._path(key).parent.iterdir()
                if file.suffix in {".json", ".lock"}
            ):
                _fail("ALLOCATION_INTEGRITY", "allocation exists without a replacement guard")
            if path.exists():
                if _read(path, _ReplacementSmoke) != expected:
                    _fail("ALLOCATION_INTEGRITY", "unguarded replacement differs")
            else:
                _atomic_write(path, canonical_bytes(expected), self.fault, "replacement_bind")
            _atomic_write(
                guard_path, canonical_bytes(expected), self.fault, "replacement_guard_bind"
            )
            return key

    def enroll_replacement_smoke(
        self, registration_sha256: str, case_id: str, caps: BudgetCaps
    ) -> str:
        """Issue only the exact bound replacement, once, under the existing lock."""
        with _ProcessLock(self.root / "enrollment.lock"):
            pilot = self._pilot()
            if case_id == U4_SMOKE_CASE:
                record = self._u4_replacement(pilot, for_enrollment=True)
                filename = _U4_RECORD
            else:
                record = self._replacement(pilot, for_enrollment=True)
                filename = _REPLACEMENT_RECORD
            binding = record.binding
            if (binding.registration_sha256, binding.case_id, binding.caps) != (
                registration_sha256,
                case_id,
                caps,
            ):
                _fail("ALLOCATION_ALREADY_ENROLLED", "replacement binding differs")
            key = binding.allocation_key
            if binding.state == "issued":
                case = self._bound_case(binding)
                if case.generation or case.head is not None or case.entries:
                    _fail("ALLOCATION_ALREADY_ENROLLED", "replacement already consumed")
                if not self._path(key).with_suffix(".lock").is_file():
                    _fail("ALLOCATION_UNAVAILABLE", "issued replacement lock is missing")
                issued = record
            else:
                self._initial_case(binding)
                issued = self._with_replacement_state(record, "issued")
                _atomic_write(
                    self.root / filename,
                    canonical_bytes(issued),
                    self.fault,
                    "replacement_issue",
                )
            guard_path = self._replacement_guard(filename)
            if _read(guard_path, _ReplacementSmoke) != issued:
                _atomic_write(
                    guard_path, canonical_bytes(issued), self.fault, "replacement_guard_issue"
                )
            return key

    def enroll_fake(self, registration_sha256: str, case_id: str, caps: BudgetCaps) -> str:
        self._fake()
        key = allocation_key(registration_sha256, case_id)
        wanted = _Binding(
            registration_sha256=registration_sha256,
            case_id=case_id,
            allocation_key=key,
            caps=caps,
            state="initializing",
        )
        with _ProcessLock(self.root / "enrollment.lock"):
            record = self._fake()
            matches = [b for b in record.bindings if b.allocation_key == key]
            if matches:
                binding = matches[0]
                if binding.model_dump(exclude={"state"}) != wanted.model_dump(exclude={"state"}):
                    _fail("ALLOCATION_ALREADY_ENROLLED")
                if binding.state == "issued":
                    self._read_case(key)
                    _fail("ALLOCATION_ALREADY_ENROLLED")
            else:
                record = _FakeEnrollments(
                    enrollment_version="0.1",
                    authority_root=_locator(self.root),
                    bindings=sorted([*record.bindings, wanted], key=lambda b: b.allocation_key),
                )
                _atomic_write(
                    self.root / "fake-enrollments.json",
                    canonical_bytes(record),
                    self.fault,
                    "slot_bind",
                )
            self._initial_case(wanted)
            bindings = [b.model_dump(mode="json") for b in record.bindings]
            for item in bindings:
                if item["allocation_key"] == key:
                    item["state"] = "issued"
            record = _FakeEnrollments.model_validate(
                {**record.model_dump(mode="json"), "bindings": bindings}
            )
            _atomic_write(
                self.root / "fake-enrollments.json",
                canonical_bytes(record),
                self.fault,
                "slot_issue",
            )
            return key

    def open_case(
        self,
        key: str,
        pricing: PricingPin,
        expected_head: AllocationHead | None,
        verify_checkpoint: CheckpointVerifier,
        *,
        offline_recovery: bool = False,
    ) -> CaseAllocationSession:
        return CaseAllocationSession(
            self, key, pricing, expected_head, verify_checkpoint, offline_recovery=offline_recovery
        )


def _ledger(
    key: str, caps: BudgetCaps, debits: Sequence[CallDebit], recoveries: Sequence[CallDebit]
) -> BudgetLedgerP3:
    return BudgetLedgerP3(
        budget_schema_version="0.1",
        allocation_key=key,
        caps=caps,
        attempts_charged=len(debits),
        input_charged=sum(d.input_charged for d in debits),
        output_charged=sum(d.output_charged for d in debits),
        money_charged=sum(d.money_charged for d in debits),
        unknown_usage_count=sum(d.usage_unknown for d in debits),
        recovery_debits=list(recoveries),
    )


def ledger_from_entries(
    key: str, caps: BudgetCaps, entries: Sequence[AllocationEntry]
) -> BudgetLedgerP3:
    """Pure mirror reconstruction: no enrollment, authority access or provider access."""
    debits: list[CallDebit] = []
    recoveries: list[CallDebit] = []
    seen: set[str] = set()
    for ordinal, entry in enumerate(entries):
        entry = AllocationEntry.model_validate(entry)
        r = entry.reservation
        if (r.allocation_key, r.reservation_ordinal) != (key, ordinal) or r.call_id in seen:
            _fail("ALLOCATION_INTEGRITY", "mirror identity mismatch")
        if entry.state == "reserved" or entry.debit is None:
            _fail("ALLOCATION_INTEGRITY", "mirror contains an unfinished attempt")
        seen.add(r.call_id)
        debits.append(entry.debit)
        if entry.state == "recovery":
            recoveries.append(entry.debit)
    return _ledger(key, caps, debits, recoveries)


def _changed(case: CaseAllocationP3, **updates: Any) -> CaseAllocationP3:
    return CaseAllocationP3.model_validate({**case.model_dump(mode="json"), **updates})


class CaseAllocationSession:
    """An acquired case generation implementing the frozen DecisionBudgetPort."""

    def __init__(
        self,
        store: AllocationStore,
        key: str,
        pricing: PricingPin,
        expected_head: AllocationHead | None,
        verify_checkpoint: CheckpointVerifier,
        *,
        offline_recovery: bool = False,
    ) -> None:
        self.store, self.key, self.pricing = store, key, PricingPin.model_validate(pricing)
        self.verify_checkpoint = verify_checkpoint
        self.offline_recovery = offline_recovery
        self.lock = _ProcessLock(store._path(key).with_suffix(".lock"))
        self.generation = -1
        self.closed = False
        self._debits: dict[str, CallDebit] = {}
        self._committed: set[str] = set()
        self.lock.acquire()
        try:
            case = store._read_case(key)
            self._validate_prefix(case)
            case = self._reconcile(case)
            if case.status == "complete":
                _fail("ALLOCATION_CLOSED")
            if case.head != expected_head:
                _fail("ALLOCATION_STALE")
            if case.status == "offline_only" and not offline_recovery:
                _fail("ALLOCATION_CLOSED", "case is permanently offline")
            cursor = 0 if case.head is None else case.head.reservation_cursor
            if len(case.entries) > cursor and not offline_recovery:
                _fail("INTERRUPTED_CALL_RECOVERY_REQUIRED")
            if store.mode == "live" and (
                pricing.input_micro_cny_per_million_tokens,
                pricing.output_micro_cny_per_million_tokens,
            ) != (2000000, 8000000):
                _fail("ALLOCATION_INTEGRITY", "live price pin differs from approved prices")
            self.generation = case.generation + 1
            case = _changed(
                case,
                generation=self.generation,
                status="offline_only" if case.status == "offline_only" else "running",
            )
            self._write(case, "generation")
            self._debits = {
                e.reservation.call_id: e.debit for e in case.entries if e.debit is not None
            }
        except BaseException:
            self.closed = True
            self.lock.release()
            raise

    def _write(self, case: CaseAllocationP3, stage: str) -> None:
        self.lock.check()
        _atomic_write(self.store._path(self.key), canonical_bytes(case), self.store.fault, stage)

    def _verified(self, head: AllocationHead) -> VerifiedCheckpoint | None:
        run = Path(head.run_directory).resolve()
        if (
            run == self.store.root
            or run.is_relative_to(self.store.root)
            or self.store.root.is_relative_to(run)
        ):
            _fail("ALLOCATION_INTEGRITY", "authority and run paths must be disjoint")
        result = self.verify_checkpoint(head)
        if result is not None:
            if result.head != head or len(result.entries) != head.reservation_cursor:
                _fail("ALLOCATION_INTEGRITY", "checkpoint verifier returned a different target")
            ledger_from_entries(self.key, self.store._binding(self.key).caps, result.entries)
        return result

    def _validate_prefix(self, case: CaseAllocationP3) -> None:
        cursor = 0 if case.head is None else case.head.reservation_cursor
        if case.head is not None:
            result = self._verified(case.head)
            if (
                result is None
                or list(result.entries) != case.entries[:cursor]
                or result.complete != (case.status == "complete")
            ):
                _fail("ALLOCATION_INTEGRITY", "authority head does not match verified checkpoint")
        if case.status == "complete" and (
            case.head is None or case.prepared_head is not None or len(case.entries) != cursor
        ):
            _fail("ALLOCATION_INTEGRITY", "complete case must have a final clean head")
        suffix = case.entries[cursor:]
        if case.pending_recovery_sha256 is not None:
            self._origin(case)
        elif any(e.state != "reserved" for e in suffix):
            _fail("ALLOCATION_INTEGRITY", "unreferenced authority suffix")

    def _reconcile(self, case: CaseAllocationP3) -> CaseAllocationP3:
        head = case.prepared_head
        if head is None:
            return case
        result = self._verified(head)
        if result is None:
            case = _changed(case, prepared_head=None)
        else:
            self._validate_candidate(case, head, result.entries)
            if case.status == "offline_only" and result.live_enabled:
                _fail("ALLOCATION_INTEGRITY", "offline case cannot publish a live checkpoint")
            case = self._finalized(case, head, result.entries, result.complete)
        self._write(case, "prepared_reconcile")
        return case

    def _refresh(self) -> CaseAllocationP3:
        if self.closed:
            _fail("ALLOCATION_STALE", "session is closed")
        self.lock.check()
        case = self.store._read_case(self.key)
        if case.generation != self.generation:
            _fail("ALLOCATION_STALE", "generation changed")
        self._validate_prefix(case)
        return case

    def snapshot(self) -> CaseAllocationP3:
        return self._refresh().model_copy(deep=True)

    def mirror_entries(self) -> list[AllocationEntry]:
        return [e.model_copy(deep=True) for e in self._refresh().entries if e.state != "reserved"]

    def export_ledger(self) -> BudgetLedgerP3:
        case = self._refresh()
        debits = [
            self._debits[e.reservation.call_id]
            for e in case.entries
            if e.reservation.call_id in self._debits
        ]
        recoveries = [
            e.debit for e in case.entries if e.state == "recovery" and e.debit is not None
        ]
        return _ledger(self.key, case.caps, debits, recoveries)

    def admit(
        self,
        call_id: str,
        input_tokens: int,
        output_tokens: int,
        provider_request_sha256: str,
        wire_body_sha256: str,
    ) -> CallReservation | None:
        case = self._refresh()
        if self.offline_recovery or case.status in ("offline_only", "complete"):
            _fail("ALLOCATION_CLOSED")
        if case.head is None or case.prepared_head is not None:
            _fail("ALLOCATION_INTEGRITY", "a finalized head is required before dispatch")
        if any(e.reservation.call_id == call_id for e in case.entries):
            _fail("ALLOCATION_DUPLICATE_CALL")
        reservation = CallReservation(
            allocation_key=self.key,
            reservation_ordinal=len(case.entries),
            call_id=call_id,
            input_reserved=input_tokens,
            output_reserved=output_tokens,
            money_reserved=reserved_money(self.pricing, input_tokens, output_tokens),
        )
        entry = AllocationEntry(
            reservation=reservation,
            provider_request_sha256=provider_request_sha256,
            wire_body_sha256=wire_body_sha256,
            state="reserved",
            debit=None,
            terminal_call_sha256=None,
        )
        inputs = outputs = money = 0
        for old in case.entries:
            if old.state == "reserved":
                inputs += old.reservation.input_reserved
                outputs += old.reservation.output_reserved
                money += old.reservation.money_reserved
            else:
                assert old.debit is not None
                inputs += old.debit.input_charged
                outputs += old.debit.output_charged
                money += old.debit.money_charged
        if (
            len(case.entries) + 1 > case.caps.attempts
            or inputs + input_tokens > case.caps.input_tokens
            or outputs + output_tokens > case.caps.output_tokens
            or money + reservation.money_reserved > case.caps.micro_cny
        ):
            return None
        self._write(_changed(case, entries=[*case.entries, entry]), "reservation")
        return reservation

    def verify_reservation(self, dispatch: AttemptDispatch) -> None:
        case = self._refresh()
        if self.offline_recovery or case.status != "running" or case.prepared_head is not None:
            _fail("ALLOCATION_CLOSED")
        index = dispatch.reservation_ordinal
        if index >= len(case.entries):
            _fail("ALLOCATION_INTEGRITY", "dispatch has no durable reservation")
        entry = case.entries[index]
        r = entry.reservation
        if entry.state != "reserved" or (
            r.allocation_key,
            r.call_id,
            r.input_reserved,
            r.output_reserved,
            r.money_reserved,
            entry.provider_request_sha256,
            entry.wire_body_sha256,
        ) != (
            dispatch.allocation_key,
            dispatch.call_id,
            dispatch.input_reserved,
            dispatch.output_reserved,
            dispatch.money_reserved,
            dispatch.provider_request_sha256,
            dispatch.wire_body_sha256,
        ):
            _fail("ALLOCATION_INTEGRITY", "dispatch does not match its durable reservation")

    def _validate_debit(self, debit: CallDebit, reservation: CallReservation) -> None:
        if (debit.call_id, debit.input_reserved, debit.output_reserved, debit.money_reserved) != (
            reservation.call_id,
            reservation.input_reserved,
            reservation.output_reserved,
            reservation.money_reserved,
        ):
            _fail("ALLOCATION_INTEGRITY", "debit reservation mismatch")
        unknown = debit.usage_unknown
        inputs = reservation.input_reserved if unknown else debit.input_reported
        outputs = reservation.output_reserved if unknown else debit.output_reported
        assert inputs is not None and outputs is not None
        if (debit.input_reported or 0) > reservation.input_reserved or (
            debit.output_reported or 0
        ) > reservation.output_reserved:
            _fail("ALLOCATION_OVERRUN")
        expected = (inputs, outputs, reserved_money(self.pricing, inputs, outputs))
        if (debit.input_charged, debit.output_charged, debit.money_charged) != expected:
            _fail("ALLOCATION_INTEGRITY", "normal debit does not match pinned pricing/usage")

    def commit(self, decision_id: str, debits: list[CallDebit]) -> None:
        case = self._refresh()
        if decision_id in self._committed:
            _fail("ALLOCATION_DUPLICATE_CALL", "decision already committed")
        validated = [CallDebit.model_validate(d) for d in debits]
        if [d.call_id for d in validated] != [
            build_call_id(decision_id, i) for i in range(len(debits))
        ]:
            _fail("ALLOCATION_INTEGRITY", "decision attempt sequence mismatch")
        entries = {e.reservation.call_id: e for e in case.entries}
        for debit in validated:
            entry = entries.get(debit.call_id)
            if entry is None or entry.state != "reserved" or debit.call_id in self._debits:
                _fail("ALLOCATION_DUPLICATE_CALL", "debit is missing or already committed")
            self._validate_debit(debit, entry.reservation)
        # Publication, not this in-memory simulation transaction, releases reservations.
        self._debits.update({d.call_id: d for d in validated})
        self._committed.add(decision_id)

    def _validate_candidate(
        self, case: CaseAllocationP3, head: AllocationHead, entries: Sequence[AllocationEntry]
    ) -> None:
        if len(entries) != head.reservation_cursor or len(entries) != len(case.entries):
            _fail("ALLOCATION_INTEGRITY", "checkpoint must account for every reservation")
        if case.head is None and (head.checkpoint_tick != 0 or entries):
            _fail("ALLOCATION_INTEGRITY", "initial publication must be empty tick zero")
        cursor = 0 if case.head is None else case.head.reservation_cursor
        if list(entries[:cursor]) != case.entries[:cursor]:
            _fail("ALLOCATION_INTEGRITY", "checkpoint rewrites finalized entries")
        if case.head is not None and (
            head.checkpoint_tick < case.head.checkpoint_tick
            or head.input_manifest_sha256 != case.head.input_manifest_sha256
        ):
            _fail("ALLOCATION_INTEGRITY", "checkpoint lineage mismatch")
        for old, new in zip(case.entries, entries, strict=True):
            if (old.reservation, old.provider_request_sha256, old.wire_body_sha256) != (
                new.reservation,
                new.provider_request_sha256,
                new.wire_body_sha256,
            ):
                _fail("ALLOCATION_INTEGRITY", "checkpoint reservation mismatch")
            if old.state != "reserved" and old != new:
                _fail("ALLOCATION_INTEGRITY", "checkpoint rewrites a finalized charge")
            if old.state == "reserved":
                if new.state != "settled" or new.debit is None:
                    _fail(
                        "ALLOCATION_INTEGRITY", "only a verified terminal may settle a reservation"
                    )
                self._validate_debit(new.debit, old.reservation)
        ledger_from_entries(self.key, case.caps, entries)

    def prepare(self, head: AllocationHead, entries: Sequence[AllocationEntry]) -> None:
        case = self._refresh()
        if case.status == "complete" or case.prepared_head is not None:
            _fail("ALLOCATION_CLOSED", "publication is already prepared or complete")
        if self.offline_recovery and case.status != "offline_only":
            _fail("ALLOCATION_INTEGRITY", "offline publication requires retained recovery origin")
        self._validate_candidate(case, head, entries)
        # Also reject an invalid locator before preparing an otherwise absent target.
        self._verified(head)
        self._write(_changed(case, prepared_head=head), "prepare")

    @staticmethod
    def _finalized(
        case: CaseAllocationP3,
        head: AllocationHead,
        entries: Sequence[AllocationEntry],
        complete: bool,
    ) -> CaseAllocationP3:
        return _changed(
            case,
            head=head,
            prepared_head=None,
            pending_recovery_sha256=None,
            entries=list(entries),
            status=(
                "complete"
                if complete
                else "offline_only"
                if case.status == "offline_only"
                else "running"
            ),
        )

    def finalize(
        self, head: AllocationHead, entries: Sequence[AllocationEntry], *, complete: bool = False
    ) -> None:
        case = self._refresh()
        if case.prepared_head != head:
            _fail("ALLOCATION_INTEGRITY", "target was not prepared")
        self._validate_candidate(case, head, entries)
        verified = self._verified(head)
        if (
            verified is None
            or list(verified.entries) != list(entries)
            or verified.complete != complete
        ):
            _fail(
                "ALLOCATION_INTEGRITY", "published target is absent or differs from prepared data"
            )
        if case.status == "offline_only" and verified.live_enabled:
            _fail("ALLOCATION_INTEGRITY", "offline checkpoint cannot enable calls")
        case = self._finalized(case, head, entries, complete)
        self._write(case, "finalize")
        self._debits = {e.reservation.call_id: e.debit for e in case.entries if e.debit is not None}

    @staticmethod
    def _origin_value(data: bytes) -> dict[str, Any]:
        value = _decode(data)
        required = {
            "origin_version",
            "source_run_id",
            "checkpoint_tick",
            "checkpoint_sha256",
            "log_prefixes",
            "source_input_manifest_sha256",
            "recovery_mode",
            "allocation_key",
            "orphan_artifacts",
            "recovery_entries",
            "recovery_debits",
        }
        if not isinstance(value, dict) or set(value) != required:
            _fail("ALLOCATION_INTEGRITY", "invalid recovery origin fields")
        names: list[str] = []
        if not isinstance(value["orphan_artifacts"], list):
            _fail("ALLOCATION_INTEGRITY", "invalid recovery artifacts")
        for artifact in value["orphan_artifacts"]:
            if not isinstance(artifact, dict) or set(artifact) != {"name", "sha256"}:
                _fail("ALLOCATION_INTEGRITY", "invalid recovery artifact")
            name, sha = artifact["name"], artifact["sha256"]
            if (
                not isinstance(name, str)
                or not isinstance(sha, str)
                or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
            ):
                _fail("ALLOCATION_INTEGRITY", "invalid recovery artifact identity")
            names.append(name)
        if names != sorted(set(names)):
            _fail("ALLOCATION_INTEGRITY", "recovery artifact names must be sorted and unique")
        return value

    def _origin(self, case: CaseAllocationP3) -> bytes | None:
        sha = case.pending_recovery_sha256
        if sha is None:
            return None
        try:
            data = (self.store.root / "recovery-origins" / (sha + ".json")).read_bytes()
            if hashlib.sha256(data).hexdigest() != sha:
                _fail("ALLOCATION_INTEGRITY", "pending origin hash mismatch")
            origin = self._origin_value(data)
            if case.head is None or (
                origin["origin_version"],
                origin["recovery_mode"],
                origin["allocation_key"],
                origin["checkpoint_sha256"],
                origin["checkpoint_tick"],
                origin["source_input_manifest_sha256"],
            ) != (
                "0.2",
                "offline",
                self.key,
                case.head.checkpoint_sha256,
                case.head.checkpoint_tick,
                case.head.input_manifest_sha256,
            ):
                _fail("ALLOCATION_INTEGRITY", "pending recovery lineage mismatch")
            entries = case.entries[case.head.reservation_cursor :]
            if origin["recovery_entries"] != [e.model_dump(mode="json") for e in entries]:
                _fail("ALLOCATION_INTEGRITY", "pending recovery entries mismatch")
            if origin["recovery_debits"] != [
                e.debit.model_dump(mode="json") for e in entries if e.debit is not None
            ]:
                _fail("ALLOCATION_INTEGRITY", "pending recovery debit mismatch")
            for artifact in origin["orphan_artifacts"]:
                body = (
                    self.store.root / "recovery-evidence" / (artifact["sha256"] + ".bin")
                ).read_bytes()
                if hashlib.sha256(body).hexdigest() != artifact["sha256"]:
                    _fail("ALLOCATION_INTEGRITY", "pending recovery evidence hash mismatch")
            return data
        except (OSError, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, AllocationError):
                raise
            raise AllocationError(
                "ALLOCATION_INTEGRITY", "pending recovery evidence invalid"
            ) from exc

    def pending_recovery(self) -> bytes | None:
        return self._origin(self._refresh())

    def recovery_evidence(self) -> dict[str, bytes]:
        """Read immutable evidence for the already-latched origin; never reimport it."""
        data = self.pending_recovery()
        if data is None:
            return {}
        origin = self._origin_value(data)
        return {
            artifact["name"]: (
                self.store.root / "recovery-evidence" / (artifact["sha256"] + ".bin")
            ).read_bytes()
            for artifact in origin["orphan_artifacts"]
        }

    def latch_recovery(
        self,
        origin_bytes: bytes,
        artifacts: Mapping[str, bytes],
        recovery_entries: Sequence[AllocationEntry],
    ) -> str:
        case = self._refresh()
        if not self.offline_recovery or case.head is None or case.prepared_head is not None:
            _fail("ALLOCATION_CLOSED", "recovery requires the acquired current head")
        sha = hashlib.sha256(origin_bytes).hexdigest()
        if case.pending_recovery_sha256 is not None:
            if case.pending_recovery_sha256 != sha or self._origin(case) != origin_bytes:
                _fail("ALLOCATION_INTEGRITY", "pending origin is immutable")
            return sha
        origin = self._origin_value(origin_bytes)
        if (
            origin["origin_version"],
            origin["recovery_mode"],
            origin["allocation_key"],
            origin["checkpoint_sha256"],
            origin["checkpoint_tick"],
            origin["source_input_manifest_sha256"],
        ) != (
            "0.2",
            "offline",
            self.key,
            case.head.checkpoint_sha256,
            case.head.checkpoint_tick,
            case.head.input_manifest_sha256,
        ):
            _fail("ALLOCATION_INTEGRITY", "recovery origin does not identify current head")
        cursor = case.head.reservation_cursor
        suffix = case.entries[cursor:]
        if len(recovery_entries) != len(suffix):
            _fail("ALLOCATION_INTEGRITY", "recovery must import each reservation once")
        validated = [AllocationEntry.model_validate(e) for e in recovery_entries]
        for old, new in zip(suffix, validated, strict=True):
            if (
                old.state != "reserved"
                or new.state != "recovery"
                or (old.reservation, old.provider_request_sha256, old.wire_body_sha256)
                != (new.reservation, new.provider_request_sha256, new.wire_body_sha256)
            ):
                _fail("ALLOCATION_INTEGRITY", "recovery entry identity mismatch")
            assert new.debit is not None
            expected_input = max(old.reservation.input_reserved, new.debit.input_reported or 0)
            expected_output = max(old.reservation.output_reserved, new.debit.output_reported or 0)
            if (new.debit.input_charged, new.debit.output_charged, new.debit.money_charged) != (
                expected_input,
                expected_output,
                reserved_money(self.pricing, expected_input, expected_output),
            ):
                _fail("ALLOCATION_INTEGRITY", "recovery charge must conservatively match usage")
        if origin["recovery_entries"] != [e.model_dump(mode="json") for e in validated] or (
            origin["recovery_debits"]
            != [e.debit.model_dump(mode="json") for e in validated if e.debit is not None]
        ):
            _fail("ALLOCATION_INTEGRITY", "origin does not bind exact recovery entries/debits")
        if artifacts.get("authority-tail.json") != canonical_bytes(case):
            _fail("ALLOCATION_INTEGRITY", "recovery must retain exact pre-latch authority bytes")
        expected_artifacts = [
            {"name": name, "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in sorted(artifacts.items())
        ]
        if origin["orphan_artifacts"] != expected_artifacts:
            _fail("ALLOCATION_INTEGRITY", "origin does not bind exact evidence bytes")
        for artifact in expected_artifacts:
            path = self.store.root / "recovery-evidence" / (artifact["sha256"] + ".bin")
            body = artifacts[artifact["name"]]
            if path.exists():
                if path.read_bytes() != body:
                    _fail("ALLOCATION_INTEGRITY", "retained evidence was changed")
            else:
                _atomic_write(path, body, self.store.fault, "recovery_evidence")
        path = self.store.root / "recovery-origins" / (sha + ".json")
        if path.exists():
            if path.read_bytes() != origin_bytes:
                _fail("ALLOCATION_INTEGRITY", "retained origin was changed")
        else:
            _atomic_write(path, origin_bytes, self.store.fault, "recovery_origin")
        case = _changed(
            case,
            status="offline_only",
            pending_recovery_sha256=sha,
            entries=[*case.entries[:cursor], *validated],
        )
        self._write(case, "recovery_latch")
        self._debits = {e.reservation.call_id: e.debit for e in case.entries if e.debit is not None}
        return sha

    def close(self, *, clean: bool = True) -> None:
        if self.closed:
            return
        try:
            case = self._refresh()
            if clean:
                cursor = 0 if case.head is None else case.head.reservation_cursor
                if (
                    case.prepared_head is not None
                    or len(case.entries) != cursor
                    or case.pending_recovery_sha256
                ):
                    _fail(
                        "INTERRUPTED_CALL_RECOVERY_REQUIRED",
                        "cannot cleanly release unfinished work",
                    )
                if case.status == "running":
                    self._write(_changed(case, status="ready"), "release")
        finally:
            self.closed = True
            self.lock.release()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close(clean=exc_type is None)
