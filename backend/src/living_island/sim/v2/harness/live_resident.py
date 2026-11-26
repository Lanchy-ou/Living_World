"""Run, verify and export the single M14 resident case."""

import argparse
import os
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import ExitStack, closing, contextmanager, nullcontext
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Any, Literal

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from living_island.agents.llm import provider as p3
from living_island.agents.types import OwnProfile
from living_island.agents.v2.calls.contracts import (
    INSTRUCTIONS,
    CallKind,
    Contract,
    digest,
    json_bytes,
    read_json,
)
from living_island.agents.v2.calls.fake import FakeClock
from living_island.agents.v2.calls.guard import PreparedRecord, Settings
from living_island.agents.v2.calls.journal import Fact, Journal
from living_island.agents.v2.calls.provider import (
    BudgetStop,
    Dispatch,
    SystemClock,
    Terminal,
    dispatch_admission,
)
from living_island.agents.v2.calls.wire import RESERVE
from living_island.agents.v2.context.prefix import ResidentIdentity
from living_island.agents.v2.decision.caller import Caller
from living_island.analysis import v2_spend as spend
from living_island.analysis.v2.export import FinishedRun, export, fingerprint
from living_island.analysis.v2.shards import InspectionArchive
from living_island.contract import inspection_v2 as ia
from living_island.contract.replay import DisplayFrame, ReplayBundle
from living_island.memory.v2.kinds import KindRegistry
from living_island.memory.v2.profiles import SelectedProfile
from living_island.memory.v2.store import MemoryStore
from living_island.persistence._files import atomic_create
from living_island.persistence.v2.audit import AuditReader, AuditWriter
from living_island.persistence.v2.journal import PacketJournal, store_once
from living_island.persistence.v2.manifest import RunManifest
from living_island.persistence.v2.replay import RuleStore
from living_island.sim.equivalence.v2_extract import snapshot
from living_island.sim.v2.cli import PACK, ROOT, VOCABULARY, build_world_setup
from living_island.sim.v2.compat.config import BoundCompatPack, load_compat_pack
from living_island.sim.v2.compat.policy_config import script_policy_config
from living_island.sim.v2.compat.policy_host import restore_policies
from living_island.sim.v2.harness.checkpoint import Boundary, Recording, Runtime, load
from living_island.sim.v2.harness.composition import compose
from living_island.sim.v2.harness.consolidation.workflow import Authorized, CallDisposition
from living_island.sim.v2.harness.provider_check import (
    PIN,
    ProtectedTransport,
    Release,
)
from living_island.sim.v2.harness.replay import (
    History,
    continue_offline,
    replay_resident,
    replay_revisions,
)
from living_island.sim.v2.harness.session import ResidentSession
from living_island.world.content import EffectiveConfig
from living_island.world.protocol import TERRAIN_BY_SYMBOL
from living_island.world.v2.engine import World, initialize
from living_island.world.v2.engine.snapshot import encode_snapshot
from living_island.world.v2.engine.state import state_snapshot_hash
from living_island.world.v2.engine.validate import WorldSetup
from living_island.world.v2.rules import load_vocabulary

ACTOR = "ella"
RUN_ID = "m14-ev06-ella"
LIVE_DIRECTORY = ROOT / "runs" / RUN_ID
SEED = 20261108
DAY = 144
HORIZON = 4 * DAY
REHEARSAL_SHA256 = "780d8b45c5fea228399b51b71cf64e5905ffd25dbbc558ff70c94c5f10a6fe07"
SOURCE_INPUTS = ("backend/src", "backend/prompts", "backend/uv.lock", "content")
BEIJING = timezone(timedelta(hours=8))
OFF_PEAK_RATES = (20_000, 1_000_000, 4_000_000)
PEAK_RATES = (40_000, 2_000_000, 8_000_000)
BILLING_PERIODS = ((0, 9, False), (9, 12, True), (12, 14, False), (14, 18, True), (18, 24, False))

# Sent input bounds in dispatch order within each day and call kind.
# Extracted from the pinned 576-tick Ella rehearsal; retries keep their own slots.
# fmt: off
REHEARSAL: dict[tuple[int, CallKind], tuple[int, ...]] = {
    (0, 'consolidation_change_set'): (14456, 14925, 8525),
    (0, 'consolidation_selection'): (5760, 10040, 10509, 4563),
    (0, 'decision'): (
        11590, 11590, 11590, 11590, 11590, 12315, 12521, 12736, 12904, 13225, 13767, 14185,
        12526, 13060, 12454, 12862, 13334, 13719, 14146, 14573, 15000, 15737, 16142, 16559,
        17372, 17866, 18145, 18550, 18955, 12550, 12957,
    ),
    (0, 'decision_after_recall'): (11528, 14124, 16499),
    (0, 'morning'): (996, 1025, 1206),
    (0, 'recall'): (253, 279, 306),
    (1, 'consolidation_change_set'): (12342, 12371, 11284),
    (1, 'consolidation_selection'): (7464, 7952, 6865),
    (1, 'decision'): (
        12687, 13082, 13879, 14344, 14809, 15856, 12648, 13055, 13754, 14172, 14974, 15484,
        15949, 16230, 12648, 13055, 13758, 14298, 14763, 15044,
    ),
    (1, 'decision_after_recall'): (14750, 13698),
    (1, 'morning'): (1212, 1323, 1400),
    (1, 'recall'): (334, 439),
    (2, 'consolidation_change_set'): (14745, 12287),
    (2, 'consolidation_selection'): (10326, 7409),
    (2, 'decision'): (
        12643, 13050, 13753, 14217, 14682, 14963, 15854, 16398, 17079, 17596, 18061, 18342,
        12648, 13055, 14074, 14515, 14980, 15261, 12650, 13060,
    ),
    (2, 'decision_after_recall'): (17020,),
    (2, 'morning'): (1477, 1557, 1636),
    (2, 'recall'): (518,),
    (3, 'consolidation_change_set'): (11792, 11879, 13942),
    (3, 'consolidation_selection'): (7373, 7460, 9064),
    (3, 'decision'): (
        13766, 14309, 14776, 15059, 12650, 13060, 13766, 14232, 14699, 14982, 12652, 13220,
        13907, 14405, 15153, 15591, 16058, 16422, 12652, 13062, 13768, 14234, 14701,
    ),
    (3, 'decision_after_recall'): (13707, 13849),
    (3, 'morning'): (1715, 1796, 1824),
    (3, 'recall'): (676, 834),
}
# fmt: on
RESERVED = sum(
    PEAK_RATES[1] * sum(bounds) + PEAK_RATES[2] * RESERVE * len(bounds)
    for bounds in REHEARSAL.values()
)


class ResidentRelease(Release):
    dispatch_from: AwareDatetime
    dispatch_until: AwareDatetime
    beijing_public_holidays: dict[date, StrictBool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_window(self) -> "ResidentRelease":
        start, end = self.dispatch_from, self.dispatch_until
        if (
            start >= end
            or start.astimezone(UTC).date() != self.dispatch_on
            or (end.astimezone(UTC) - timedelta(microseconds=1)).date() != self.dispatch_on
        ):
            raise ValueError("expected a signed dispatch window within dispatch_on UTC")
        return self

    def covers(self, timestamp: datetime) -> bool:
        return self.dispatch_from <= timestamp < self.dispatch_until

    def check_tariff(self, tariff: spend._Tariff) -> None:
        rates = (
            tariff.cache_hit_per_million,
            tariff.cache_miss_per_million,
            tariff.output_per_million,
        )
        start = self.dispatch_from.astimezone(BEIJING)
        end = self.dispatch_until.astimezone(BEIJING)
        midnight = datetime.combine(start.date(), time.min, BEIJING)
        while midnight < end:
            day = midnight.date()
            for first, last, weekday_peak in BILLING_PERIODS:
                if midnight + timedelta(hours=last) <= start or end <= midnight + timedelta(
                    hours=first
                ):
                    continue
                expected = OFF_PEAK_RATES
                if weekday_peak and day.weekday() < 5:
                    holiday = self.beijing_public_holidays.get(day)
                    if holiday is None:
                        raise ValueError(
                            f"release needs signed Beijing public holiday status for {day}"
                        )
                    if not holiday:
                        expected = PEAK_RATES
                if rates != expected:
                    raise ValueError(
                        "dispatch window intersects a different billing rate in Beijing"
                    )
            midnight += timedelta(days=1)


@dataclass(frozen=True)
class Case:
    bound: BoundCompatPack
    config: EffectiveConfig
    setup: WorldSetup
    profiles: dict[str, OwnProfile]
    selected: dict[str, SelectedProfile]
    manifest: RunManifest

    @classmethod
    def load(cls) -> "Case":
        bound = load_compat_pack(
            ROOT / "content/worlds/default.toml",
            PACK,
            load_vocabulary(VOCABULARY),
            map_path=ROOT / "content/worlds/default-island.map",
            seed=SEED,
        )
        config = EffectiveConfig.model_validate(bound.config)
        setup = build_world_setup(bound, config, pack_ids=bound.pack.pack_ids)
        setup = setup.model_copy(update={"run_id": RUN_ID})
        profiles = {
            row.id: OwnProfile(profile_id=row.profile_id, initial_goal=row.initial_goal)
            for row in config.residents
        }
        selected = {
            actor: SelectedProfile.load(ROOT / f"content/characters/v2/{profile.profile_id}.json")
            for actor, profile in profiles.items()
        }
        return cls(
            bound, config, setup, profiles, selected, RunManifest.capture(RUN_ID, bound.pack)
        )

    def session(
        self,
        world: World,
        runtime: Runtime | None,
        packets: PacketJournal,
        journal: Journal,
        caller: Caller,
    ) -> ResidentSession:
        return compose(
            world,
            actor=ACTOR,
            identity=ResidentIdentity("Ella", self.selected[ACTOR]),
            profiles=self.profiles,
            config=script_policy_config(self.config),
            sleep_ticks=self.config.actions.sleep_ticks,
            caller=caller,
            packets=packets,
            journal=journal,
            memory_on=True,
            compat=self.bound,
            restored=runtime.continuation if runtime else None,
        )

    def preflight(self, implementation: str) -> bytes:
        world = initialize(self.bound.pack, self.setup)
        verbs = tuple(spec.shape for spec in world.pack.verbs.values())
        setup = self.setup.model_dump(mode="json")
        setup["terrain"]["opaque_terrains"] = sorted(self.setup.terrain.opaque_terrains)
        wires = {}
        for kind in INSTRUCTIONS:
            contract = Contract(kind, verbs)
            wires[kind] = Settings(
                prompt_version=contract.prompt_version,
                prompt_sha256=digest(contract.instructions.encode()),
                schema_sha256=digest(contract.schema),
            ).model_dump(mode="json")
        return json_bytes(
            {
                "implementation_commit": implementation,
                "live_directory": LIVE_DIRECTORY.resolve().as_posix(),
                "manifest": self.manifest.model_dump(mode="json"),
                "through": HORIZON,
                "seed": SEED,
                "compat": asdict(self.bound.manifest),
                "setup_sha256": digest(json_bytes(setup)),
                "profiles": {
                    actor: {
                        "profile_id": self.profiles[actor].profile_id,
                        "sha256": profile.sha256,
                        "control": "model" if actor == ACTOR else "rule",
                        "memory_on": actor == ACTOR,
                    }
                    for actor, profile in self.selected.items()
                },
                "wires": wires,
                "rehearsal_sha256": REHEARSAL_SHA256,
                "rehearsal": {
                    f"{day + 1}:{kind}": inputs for (day, kind), inputs in REHEARSAL.items()
                },
                "reserve_pico_cny": RESERVED,
            }
        )


def implementation(revision: str, *, check_sources: bool) -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    commit = git("rev-parse", "--verify", f"{revision}^{{commit}}")
    if check_sources:
        git("cat-file", "-e", f"{commit}:backend/src/living_island/sim/v2/harness/live_resident.py")
        if git("diff", "--name-only", commit, "--", *SOURCE_INPUTS) or git(
            "ls-files", "--others", "--exclude-standard", "--", *SOURCE_INPUTS
        ):
            raise ValueError("executable sources or content differ from the implementation pin")
    return commit


class Account(Fact):
    call_id: str
    attempt: int
    settled_pico_cny: int | None
    held_pico_cny: int | None


class Refusal(Fact):
    dispatch: Dispatch
    reason: str


@dataclass(frozen=True)
class Authority:
    release: ResidentRelease
    prior: spend.Ledger
    tariff: spend._Tariff

    @classmethod
    def load(cls, authorization: bytes, raw_ledger: bytes, preflight: bytes) -> "Authority":
        release = ResidentRelease.model_validate_json(authorization)
        if (
            digest(preflight) != release.preflight_sha256
            or digest(raw_ledger) != release.ledger_sha256
        ):
            raise ValueError("release does not match the preflight and ledger pins")
        evidence = spend.read_evidence(raw_ledger)
        prior = spend.project(evidence)
        pin = PIN["provider"], PIN["model"], PIN["model_version"]
        tariff = next(
            (
                price
                for price in evidence.tariffs.get(pin, ())
                if price.effective_on <= release.dispatch_on <= price.through
            ),
            None,
        )
        if (
            tariff is None
            or (
                tariff.peak_cache_miss_per_million,
                tariff.peak_output_per_million,
            )
            != PEAK_RATES[1:]
        ):
            raise ValueError("released date requires the approved peak tariff and dated evidence")
        release.check_tariff(tariff)
        if (
            prior.remaining_pico is None
            or not RESERVED <= release.max_cny <= prior.remaining_pico
            or any(row.run_id == RUN_ID for row in prior.runs)
        ):
            raise ValueError("released reserve does not fit the reconciled phase ledger")
        return cls(release, prior, tariff)


class Budget:
    """Read durable claims and terminals before authorizing the next attempt."""

    def __init__(self, authority: Authority, audit: AuditReader, journal: Journal) -> None:
        self.authority = authority
        self.audit = audit
        self.journal = journal
        self.cursor = 0
        self.claims: dict[tuple[str, int], Dispatch] = {}
        self.accounts: dict[tuple[str, int], Account] = {}
        self.used: dict[tuple[int, CallKind], int] = {}

    @staticmethod
    def group(dispatch: Dispatch) -> tuple[int, CallKind]:
        return dispatch.call.tick // DAY, dispatch.sent.manifest.call_kind

    def refresh(self) -> None:
        end = self.audit.cursor()
        for key in self.audit.keys(self.cursor, end):
            if key.endswith(".dispatch.json"):
                dispatch = Dispatch.model_validate_json(self.audit.read(key))
                identity = dispatch.call.call_id, dispatch.n
                group = self.group(dispatch)
                self.used[group] = self.used.get(group, 0) + 1
                self.claims[identity] = dispatch
                self.accounts[identity] = self.account(dispatch, None)
            elif key.endswith(".terminal.json"):
                terminal = Terminal.model_validate_json(self.audit.read(key))
                identity = terminal.call_id, terminal.n
                account = self.account(self.claims[identity], terminal)
                self.accounts[identity] = account
                self.journal.fact(terminal.call_id, f"{terminal.n}.spend", account)
        self.cursor = end

    def account(self, dispatch: Dispatch, terminal: Terminal | None) -> Account:
        tariff = self.authority.tariff
        bound = dispatch.sent.manifest.tokens_total
        output_bound = dispatch.settings.max_output_tokens
        settled = None
        held: int | None = tariff.reserve(bound, output_bound)
        if terminal is not None:
            usage = terminal.tokens
            if (
                usage.input is not None
                and usage.output is not None
                and usage.cache_hit is not None
                and usage.cache_miss is not None
                and usage.cache_hit + usage.cache_miss == usage.input
            ):
                settled = (
                    usage.cache_hit * tariff.cache_hit_per_million
                    + usage.cache_miss * tariff.cache_miss_per_million
                    + usage.output * tariff.output_per_million
                )
                held = 0
            elif (
                max(usage.input or 0, (usage.cache_hit or 0) + (usage.cache_miss or 0)) > bound
                or (usage.output or 0) > output_bound
            ):
                held = None
        return Account(
            call_id=dispatch.call.call_id,
            attempt=dispatch.n,
            settled_pico_cny=settled,
            held_pico_cny=held,
        )

    def admit(self, dispatch: Dispatch) -> str | None:
        self.refresh()
        authority = self.authority
        if not authority.release.covers(dispatch.started_at):
            return "outside_released_dispatch_window"
        if any(row.held_pico_cny is None for row in self.accounts.values()):
            return "unbounded_attempt_liability"
        spent = sum(
            (row.settled_pico_cny or 0) + (row.held_pico_cny or 0) for row in self.accounts.values()
        )
        tariff = authority.tariff
        candidate = tariff.reserve(
            dispatch.sent.manifest.tokens_total, dispatch.settings.max_output_tokens
        )
        if (
            spent + candidate + authority.prior.settled_pico + authority.prior.reserve_pico
            > spend.CAP_PICO
        ):
            return "phase_cap"
        group = self.group(dispatch)
        remaining = sum(
            tariff.reserve(tokens, RESERVE)
            for slot, bounds in REHEARSAL.items()
            if slot[0] >= group[0]
            for tokens in bounds[self.used.get(slot, 0) + int(slot == group) :]
        )
        if spent + candidate + remaining > min(RESERVED, authority.release.max_cny):
            return "rehearsal_reserve"
        return None


class OfflineTransport:
    """Schema-valid synthetic choices for exercising the command without a provider."""

    def exchange(self, body: bytes, timeout_ms: int) -> p3.TransportResponse:
        kind = read_json(body)["text"]["format"]["name"]
        outputs = {
            "decision": {
                "step": "act",
                "action": {
                    "kind": "intent",
                    "intent": {
                        "action": "wait",
                        "verb": None,
                        "target": None,
                        "reason": None,
                        "inputs": [],
                        "instruments": [],
                        "params": {},
                    },
                },
                "utterance": None,
                "intention": None,
                "mute": [],
                "cite": [],
            },
            "recall": {"ids": []},
            "morning": {"ids": []},
            "consolidation_selection": {"read": []},
            "consolidation_change_set": {"ops": []},
        }
        output = outputs["decision" if kind == "decision_after_recall" else kind]
        return p3.TransportResponse(
            200,
            json_bytes(
                {
                    "model": p3.MODEL_ID,
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {"type": "output_text", "text": json_bytes(output).decode()}
                            ],
                        }
                    ],
                }
            ),
            True,
        )


@dataclass(frozen=True)
class CheckpointPackets(PacketJournal):
    # This writer only appends packet files. A new process rechecks the entire
    # saved prefix before it uses the cache for consecutive checkpoint writes.
    checked: list[int]

    def check_prefix(self, first_tick: int, next_tick: int) -> None:
        super().check_prefix(max(first_tick, self.checked[0]), next_tick)
        self.checked[0] = max(self.checked[0], next_tick)


class Result(Fact):
    status: Literal["completed", "incomplete"]
    tick: int
    reason: str | None = None
    refusal: Refusal | None = None


@dataclass(frozen=True)
class Capture:
    directory: Path
    case: Case
    audit: AuditReader
    journal: Journal
    packets: CheckpointPackets

    @classmethod
    def open(cls, directory: Path, case: Case, *, write: bool = True) -> "Capture":
        path = directory / "resident.sqlite"
        if write:
            writer = AuditWriter(path)
            journal = Journal(writer.keep, writer.create)
        else:

            def readonly(_key: str, _data: bytes) -> None:
                raise RuntimeError("offline verification attempted to change the raw journal")

            journal = Journal(readonly, readonly)
        return cls(
            directory,
            case,
            AuditReader(path),
            journal,
            CheckpointPackets(directory / "packets", RUN_ID, [0]),
        )

    def boundaries(self) -> list[Boundary]:
        return [
            Boundary.model_validate_json(self.audit.read(key))
            for key in self.audit.keys(0, self.audit.cursor())
            if key.endswith(".boundary.json")
        ]

    def start(self, caller: Caller) -> Recording:
        world = initialize(self.case.bound.pack, self.case.setup)
        session = self.case.session(world, None, self.packets, self.journal, caller)
        record = Recording.opening(session, self.packets, self.audit)
        record.save(self.directory / "checkpoints/0.json")
        return record

    def checkpoint(self, *, opening: bool = False) -> tuple[World, Runtime]:
        directory = self.directory / "checkpoints"
        path = (
            directory / "0.json"
            if opening
            else max(directory.glob("*.json"), key=lambda p: int(p.stem))
        )
        return load(path, self.case.bound.pack, self.packets, self.audit)

    def resume(self, caller: Caller) -> Recording:
        terminal = self.directory / "terminal.json"
        if terminal.exists():
            world, runtime = load(terminal, self.case.bound.pack, self.packets, self.audit)
            session = self.case.session(world, runtime, self.packets, self.journal, caller)
            session.runner.manifest.stop = runtime.stop
            return Recording(session, self.packets, self.audit)
        world, runtime = self.checkpoint()
        rows = self.boundaries()
        # The boundary audit commits before the checkpoint. If interrupted in
        # that interval, rebuild the committed continuation without a provider.
        pending = rows[world.tick :]
        if pending:
            restored = continue_offline(
                world, runtime, self.packets, self.audit, self.case.session, boundaries=len(pending)
            )
            runtime = Runtime(
                policies=restore_policies(restored.checkpoint()),
                resident=restored.continuation(),
                cursor=self.audit.cursor(),
                stop=restored.runner.manifest.stop,
            )
            session = self.case.session(world, runtime, self.packets, self.journal, caller)
            session.runner.manifest.stop = runtime.stop
            record = Recording(session, self.packets, self.audit)
            record.save(
                self.directory
                / ("terminal.json" if restored.incomplete else f"checkpoints/{world.tick}.json")
            )
            return record
        session = self.case.session(world, runtime, self.packets, self.journal, caller)
        return Recording(session, self.packets, self.audit)

    def tail(self, through: int) -> tuple[str, ...]:
        return tuple(
            key
            for key in self.audit.keys(through, self.audit.cursor())
            if "." in key and not key.endswith((".boundary.json", ".spend.json"))
        )

    def save_result(self, result: Result) -> Result:
        store_once(self.directory / "result.json", json_bytes(result.model_dump(mode="json")))
        return result

    def run(
        self, caller: Caller, *, through: int, resume: bool, authority: Authority | None
    ) -> Result | None:
        if (self.directory / "result.json").exists():
            raise ValueError("resident case is already sealed")
        record = self.resume(caller) if resume else self.start(caller)
        session = record.session
        budget = Budget(authority, self.audit, self.journal) if authority is not None else None
        active_guard = dispatch_admission(budget.admit) if budget else nullcontext()
        if budget:
            budget.refresh()
        tick = session.world.tick
        if session.incomplete:
            return self.save_result(
                Result(
                    status="incomplete",
                    tick=tick,
                    reason=session.incomplete.reason,
                )
            )
        if resume:
            rows = self.boundaries()
            _, opening = self.checkpoint(opening=True)
            if self.tail(rows[-1].through if rows else opening.cursor):
                return self.save_result(
                    Result(
                        status="incomplete",
                        tick=tick,
                        reason="interrupted_boundary",
                    )
                )
            if not session.world.state.residents[ACTOR].alive:
                return self.save_result(
                    Result(status="incomplete", tick=tick, reason="resident_died")
                )
        if through <= tick and tick != HORIZON:
            raise ValueError("resume target must be after the committed tick")
        with active_guard:
            while session.world.tick < through:
                try:
                    result = record.advance()
                except BudgetStop as stop:
                    return self.save_result(
                        Result(
                            status="incomplete",
                            tick=session.world.tick,
                            reason="budget_stop",
                            refusal=Refusal(dispatch=stop.dispatch, reason=stop.reason),
                        )
                    )
                finally:
                    if budget:
                        budget.refresh()
                tick = session.world.tick
                if session.incomplete:
                    record.save(self.directory / "terminal.json")
                    return self.save_result(
                        Result(
                            status="incomplete",
                            tick=tick,
                            reason=session.incomplete.reason,
                        )
                    )
                if result is None:
                    raise RuntimeError("resident runner stopped without a disposition")
                record.save(self.directory / f"checkpoints/{tick}.json")
                if not session.world.state.residents[ACTOR].alive:
                    return self.save_result(
                        Result(
                            status="incomplete",
                            tick=tick,
                            reason="resident_died",
                        )
                    )
        if through == HORIZON:
            return self.save_result(Result(status="completed", tick=through))
        return None


@dataclass(frozen=True)
class DisplayPackets(PacketJournal):
    case: Case
    frames: dict[int, DisplayFrame]

    def verify(self, world: World) -> dict[str, str]:
        receipt = super().verify(world)
        self.frames[world.tick] = display_frame(world, self.case)
        return receipt


def display_frame(world: World, case: Case) -> DisplayFrame:
    view = snapshot(world, case.config.canteen.unique_item_id)
    trees = {tree.id: tree.position for tree in case.config.world.fruit_trees}
    residents = []
    for resident in view.residents:
        active = world.state.active_actions.get(resident.id)
        action = None
        if active is not None:
            action = {
                "intent_id": active.intent.intent_id,
                "action_type": active.intent.verb or active.intent.action,
                "tick_started": active.tick_started,
                "remaining_ticks": active.due_tick - world.tick
                if active.due_tick is not None
                else None,
            }
        residents.append({**resident.model_dump(exclude={"canteen_id"}), "active_action": action})
    ground = view.canteen.ground_position
    return DisplayFrame.model_validate(
        {
            "tick": view.tick,
            "residents": residents,
            "fruit_trees": [
                {
                    "id": tree.id,
                    "stock": tree.stock,
                    "position": dict(zip("xy", trees[tree.id], strict=True)),
                }
                for tree in view.trees
            ],
            "ground_fruit": [pile.model_dump() for pile in view.ground_fruit],
            "ground_canteen": {"position": ground.model_dump(), "servings": view.canteen.servings}
            if ground is not None
            else None,
            "corpses": [corpse.model_dump(exclude={"death_tick"}) for corpse in view.corpses],
            "event_range": {"first_index": int(world.tick > 0), "count": int(world.tick == 0)},
        }
    )


def display(case: Case, opening: World, frames: dict[int, DisplayFrame]) -> ReplayBundle:
    config, setup = case.config, case.setup
    return ReplayBundle.model_validate(
        {
            "replay_schema_version": "0.1",
            "run_id": RUN_ID,
            "world_id": setup.world_id,
            "config_hash": setup.config_hash,
            "map_hash": setup.map_hash,
            "clock": config.time.model_dump(),
            "condition_bounds": {
                "min_value": config.needs.min_value,
                "max_value": config.needs.max_value,
            },
            "map": {
                "width": config.map.width,
                "height": config.map.height,
                "rows": list(case.bound.map_rows),
                "terrain_legend": [
                    {"symbol": sym, "terrain": value} for sym, value in TERRAIN_BY_SYMBOL.items()
                ],
            },
            "residents": [
                {"id": actor, "display_name": actor.title()} for actor in sorted(case.profiles)
            ],
            "frames": [frames[tick] for tick in sorted(frames)],
            # The viewer uses a legacy display envelope. Objective WAP events stay
            # byte-for-byte in the recorded boundaries and the inspection export.
            "events": [
                {
                    "schema_version": "0.1",
                    "run_id": RUN_ID,
                    "event_id": f"{RUN_ID}:0000000000:000000",
                    "tick": 0,
                    "seq_in_tick": 0,
                    "type": "world_initialized",
                    "actor_id": None,
                    "target_id": None,
                    "intent_id": None,
                    "llm_call_id": None,
                    "caused_by_event_ids": [],
                    "payload": {
                        "config_hash": setup.config_hash,
                        "map_hash": setup.map_hash,
                        "initial_snapshot_hash": state_snapshot_hash(opening.state),
                    },
                }
            ],
        }
    )


@dataclass(frozen=True)
class Verified:
    capture: Capture
    result: Result | None
    row_count: int
    through: int
    world_hash: str
    store_hash: str
    tail_attempts: int
    replay: ReplayBundle


def verify(capture: Capture) -> Verified:
    directory = capture.directory
    end_path = directory / "terminal.json"
    if end_path.exists():
        final, ending = load(end_path, capture.case.bound.pack, capture.packets, capture.audit)
    else:
        final, ending = capture.checkpoint()
    result_path = directory / "result.json"
    result = Result.model_validate_json(result_path.read_bytes()) if result_path.exists() else None
    if result is not None and result.tick != final.tick:
        raise ValueError("result and final checkpoint ticks differ")
    opening, runtime = capture.checkpoint(opening=True)
    frames = {0: display_frame(opening, capture.case)}
    packets = DisplayPackets(capture.packets.directory, RUN_ID, capture.case, frames)
    count = final.tick + int(end_path.exists())
    if len(capture.boundaries()) != count:
        raise ValueError("capture has a committed boundary beyond its checkpoint; resume it first")
    through = runtime.cursor
    world_hash = digest(encode_snapshot(opening))
    store_hash = runtime.resident.period.store.restore(KindRegistry()).store_hash
    seed = MemoryStore(ACTOR)
    list(replay_revisions(History(capture.audit, runtime.cursor), 0, seed))
    if seed.snapshot.store_hash != store_hash:
        raise ValueError("opening store does not match the recorded founding revision")
    for replayed in replay_resident(
        opening,
        runtime,
        capture.case.manifest,
        packets,
        RuleStore(directory),
        capture.audit,
        registry=KindRegistry(),
        boundaries=count,
    ):
        boundary = replayed.boundary
        through, world_hash, store_hash = boundary.through, boundary.world_hash, boundary.store_hash
    store = ending.resident.period.store.restore(KindRegistry())
    if (world_hash, store_hash) != (digest(encode_snapshot(final)), store.store_hash):
        raise ValueError("replay and final checkpoint hashes differ")
    frames[final.tick] = display_frame(final, capture.case)
    # An aborted boundary never mutates the committed world. Its immutable
    # prepared/attempt records still need verification and spend reconciliation.
    tail = History(capture.audit, capture.audit.cursor())
    verbs = tuple(spec.shape for spec in opening.pack.verbs.values())
    tail.verify_calls(through, verbs)
    list(replay_revisions(tail, through, MemoryStore.from_snapshot(store)))
    if result and result.refusal:
        dispatch = result.refusal.dispatch
        prepared = tail.request(dispatch.prepared_cursor, verbs)
        attempts = tuple(tail.attempts(prepared))
        if (
            prepared.admitted is None
            or prepared.record.call != dispatch.call
            or prepared.admitted.candidate != dispatch.sent
            or prepared.record.settings != dispatch.settings
            or dispatch.request_sha256 != prepared.admitted.candidate.wire_sha256
            or len(attempts) != dispatch.n
        ):
            raise ValueError("budget refusal differs from the unsent prepared attempt")
    return Verified(
        capture,
        result,
        count,
        through,
        world_hash,
        store_hash,
        sum(key.endswith(".dispatch.json") for key in capture.tail(through)),
        display(capture.case, opening, frames),
    )


def ledger_bundle(
    audit: AuditReader,
    base: bytes | None,
    through: int,
    capture_directory: Path,
) -> bytes:
    data: dict[str, Any] = (
        read_json(base)
        if base is not None
        else {
            "opening": {"settled_cny": "0", "source": "Offline fixture, no charge"},
            "tariffs": [],
            "runs": {},
        }
    )
    data.pop("plan", None)
    prepared, dispatches, terminals, abandoned = [], [], [], []
    started: set[str] = set()
    authorized: dict[str, Authorized] = {}
    for key in audit.keys(0, through):
        if key.endswith(".prepared.json"):
            row = PreparedRecord.model_validate_json(audit.read(key))
            started.add(row.call.call_id)
            prepared.append(
                {
                    "call": {"call_id": row.call.call_id},
                    "settings": row.settings.model_dump(mode="json", include=set(PIN)),
                    "candidates": [
                        {
                            "manifest": candidate.manifest.model_dump(
                                mode="json",
                                include={"call_kind", "tokens_total"},
                            )
                        }
                        for candidate in row.candidates
                    ],
                    "reason": row.reason,
                }
            )
        elif key.endswith(".dispatch.json"):
            claim = Dispatch.model_validate_json(audit.read(key))
            dispatches.append(
                {
                    "call": {"call_id": claim.call.call_id},
                    "n": claim.n,
                    "sent": {
                        "manifest": claim.sent.manifest.model_dump(
                            mode="json",
                            include={"call_kind", "tokens_total"},
                        )
                    },
                    "request_sha256": claim.request_sha256,
                    "settings": claim.settings.model_dump(
                        mode="json",
                        include={*PIN, "max_output_tokens"},
                    ),
                    "started_at": claim.started_at.isoformat(),
                }
            )
        elif key.endswith(".terminal.json"):
            terminal = Terminal.model_validate_json(audit.read(key))
            terminals.append(
                terminal.model_dump(
                    mode="json",
                    include={
                        "call_id",
                        "n",
                        "request_sha256",
                        "dispatch_cursor",
                        "error_class",
                        "tokens",
                    },
                )
            )
        elif key.endswith(".authorized.json"):
            item = Authorized.model_validate_json(audit.read(key))
            authorized[key] = item
        elif key.endswith(".outcome.json"):
            outcome = CallDisposition.model_validate_json(audit.read(key))
            if outcome.outcome == "abandoned":
                abandoned.append(authorized[outcome.authorized_cursor].call.call_id)
    settled_day = (
        ResidentRelease.model_validate_json(
            (capture_directory / "release.json").read_bytes()
        ).dispatch_on
        if base is not None
        else FakeClock().now().date()
    )
    data["runs"][RUN_ID] = {
        "stage": "resident_run",
        "mode": "paid" if base is not None else "fake",
        "date": settled_day.isoformat(),
        "prepared": prepared,
        "dispatches": dispatches,
        "terminals": terminals,
        "abandoned": abandoned,
        "undispatched": [
            {"call_id": item.call.call_id, "kind": item.kind, **PIN}
            for item in authorized.values()
            if item.call.call_id not in started
        ],
    }
    return json_bytes(data)


def close_view(audit: AuditReader, source: Path, through: int, count: int) -> AuditReader:
    """Materialize a read-only view of the verified boundary prefix for EV-01."""
    writer = AuditWriter(source / "resident.sqlite")
    with closing(sqlite3.connect(writer.path, uri=True)) as view, view:
        view.execute("ATTACH DATABASE ? AS recorded", (audit.path.resolve().as_uri() + "?mode=ro",))
        view.execute(
            "INSERT INTO facts SELECT * FROM recorded.facts "
            "WHERE seq <= ? OR name = ? ORDER BY seq",
            (through, Journal.cursor(RUN_ID, f"{count - 1}.boundary")),
        )
    view_audit = AuditReader(writer.path)
    journal = Journal(writer.keep, writer.create)
    keys = set(view_audit.keys(0, view_audit.cursor()))
    for key in sorted(keys):
        if not key.endswith(".authorized.json"):
            continue
        item = Authorized.model_validate_json(view_audit.read(key))
        call_id = item.call.call_id
        if Journal.cursor(call_id, "outcome") in keys:
            continue
        if Journal.cursor(call_id, "prepared") in keys:
            raise ValueError("open consolidation in the verified prefix was already prepared")
        # The capture ends with this call authorized, and no later boundary
        # confirmed it. Close only the exported logical call, never the period.
        journal.fact(
            call_id,
            "outcome",
            CallDisposition(
                authorized_cursor=key,
                prepared_cursor=None,
                attempts=(),
                outcome="abandoned",
                ignored=(),
            ),
        )
    return view_audit


def base_ledger(directory: Path) -> bytes | None:
    path = directory / "ledger-base.json"
    return path.read_bytes() if path.exists() else None


def publish_ledger(verified: Verified) -> spend.Ledger:
    capture = verified.capture
    end = capture.audit.cursor()
    data = ledger_bundle(capture.audit, base_ledger(capture.directory), end, capture.directory)
    ledger = spend.project(spend.read_evidence(data))
    run = next(row for row in ledger.runs if row.run_id == RUN_ID)
    if run.mode == "paid":
        keys = set(capture.audit.keys(0, end))
        for call in run.calls:
            for attempt_row in call.attempts:
                key = Journal.cursor(call.call_id, f"{attempt_row.n}.spend")
                if key not in keys:
                    # A crash can leave a claimed attempt without a published
                    # terminal or accounting row. EV-04 carries its reserve.
                    continue
                measured = Account.model_validate_json(capture.audit.read(key))
                if (measured.settled_pico_cny, measured.held_pico_cny) != (
                    attempt_row.settled_pico,
                    attempt_row.reserve_pico,
                ):
                    raise ValueError("recorded attempt cost differs from EV-04 reconciliation")
    if verified.result is not None:
        store_once(capture.directory / "sanitized-evidence.json", data)
        store_once(capture.directory / "ledger.md", spend.render_markdown(ledger).encode())
    return ledger


def export_verified(verified: Verified, destination: Path) -> ia.InspectionIndex:
    capture = verified.capture
    if verified.row_count == 0:
        raise ValueError("no committed resident delivery to export")
    if destination.exists():
        raise ValueError("inspection needs a fresh destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # EV-01 seals an immutable source. Keep it next to the export. The raw
    # capture stays intact, including any uncommitted paid attempt tails.
    source = destination.with_name(f"{destination.name}-source")
    source.mkdir()
    view = close_view(capture.audit, source, verified.through, verified.row_count)
    (source / "packets").mkdir()
    packet_pins = []
    for tick in range(verified.row_count):
        raw = (capture.packets.directory / f"{tick}.json").read_bytes()
        atomic_create(source / "packets" / f"{tick}.json", raw)
        packet_pins.append(digest(raw))
    base = base_ledger(capture.directory)
    ledger_path = source / "sanitized-evidence.json"
    atomic_create(ledger_path, ledger_bundle(view, base, view.cursor(), capture.directory))
    replay_path, seal_path = source / "replay.json", source / "finished.json"
    atomic_create(replay_path, verified.replay.model_dump_json().encode())
    seal = FinishedRun(
        status="finished",
        run_id=RUN_ID,
        arm="on",
        pack_ids=[
            ia.PackPin(pack_id=row.pack_id, sha256=row.pack_hash)
            for row in capture.case.manifest.packs
        ],
        residents=[
            ia.Resident(resident_id=actor, profile_id=p.profile_id)
            for actor, p in capture.case.profiles.items()
        ],
        final_tick=verified.replay.frames[-1].tick,
        replay_sha256=fingerprint(replay_path),
        audit_sha256=fingerprint(view.path),
        packet_sha256=packet_pins,
        content_checks_sha256=None,
    )
    atomic_create(seal_path, seal.model_dump_json().encode())
    index = export(source, seal_path, replay_path, destination)
    archive = InspectionArchive.open(destination)
    refs = [
        *(row.shard for row in index.decisions),
        *(row.shard for row in index.stores),
        *(row.shard for row in index.calls),
        *(row.shard for row in index.consolidations),
        *index.deliveries,
        *index.revisions,
        *index.evidence_writes,
        index.attempts,
        index.metrics,
        index.cost,
        index.time_use,
    ]
    for ref in refs:
        archive.read(ref)
    atomic_create(
        source / "capture.json",
        json_bytes(
            {
                "raw_audit_sha256": fingerprint(capture.audit.path),
                "raw_through": verified.through,
                "uncommitted_attempts": verified.tail_attempts,
                "status": verified.result.model_dump(mode="json")
                if verified.result
                else {"status": "paused"},
            }
        ),
    )
    return index


@contextmanager
def lock(path: Path) -> Iterator[None]:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(f"P3.5-EV-06 {datetime.now(UTC).isoformat()}\n")
    try:
        yield
    finally:
        path.unlink()


def checked_capture(directory: Path, case: Case, *, write: bool = False) -> Capture:
    raw = (directory / "preflight.json").read_bytes()
    revision = implementation(
        read_json(raw)["implementation_commit"], check_sources=base_ledger(directory) is not None
    )
    if raw != case.preflight(revision) or not (directory / "resident.sqlite").is_file():
        raise ValueError("resident capture differs from the pinned preflight")
    return Capture.open(directory, case, write=write)


def run_command(args: argparse.Namespace, case: Case) -> int:
    directory: Path = args.out.resolve()
    if args.live and directory != LIVE_DIRECTORY.resolve():
        raise ValueError(
            f"live output must use the preflight's one-time directory {LIVE_DIRECTORY}"
        )
    if args.resume:
        if args.release is not None or args.ledger is not None or args.implementation is not None:
            raise ValueError(
                "resume uses the original capture's release, ledger and implementation"
            )
    elif args.live != (args.release is not None and args.ledger is not None):
        raise ValueError("live capture requires both --release and --ledger")
    elif not args.live and (args.release is not None or args.ledger is not None):
        raise ValueError("release and ledger are only used for live capture")
    if not 0 < args.through <= HORIZON:
        raise ValueError(f"--through must be between 1 and {HORIZON}")

    if args.resume:
        preflight = (directory / "preflight.json").read_bytes()
        base = base_ledger(directory)
        if args.live != (base is not None):
            raise ValueError("resume must use the capture's original dispatch mode")
        revision = read_json(preflight)["implementation_commit"]
        authorization = (directory / "release.json").read_bytes() if args.live else None
    else:
        revision = args.implementation or "HEAD"
        authorization = args.release.read_bytes() if args.live else None
        base = args.ledger.read_bytes() if args.live else None
    revision = implementation(revision, check_sources=args.live)
    preflight = case.preflight(revision)
    authority = None
    if authorization is not None and base is not None:
        authority = Authority.load(authorization, base, preflight)
        clock = SystemClock()
        if not authority.release.covers(clock.now()):
            raise ValueError("outside the owner's released UTC dispatch window")
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY must be set in the live process environment")
        caller = Caller(
            ProtectedTransport(p3.HTTPSByteTransport(key), key.encode(), lambda: None), clock, sleep
        )
    else:
        caller = Caller(OfflineTransport(), FakeClock(), lambda _: None)

    with ExitStack() as locks:
        if authority is not None:
            locks.enter_context(lock(args.lock))
        if args.resume:
            locks.enter_context(lock(directory / ".writer.lock"))
            capture = checked_capture(directory, case, write=True)
            if (directory / "preflight.json").read_bytes() != preflight:
                raise ValueError("resume preflight differs from the capture")
        else:
            directory.mkdir()
            locks.enter_context(lock(directory / ".writer.lock"))
            atomic_create(directory / "preflight.json", preflight)
            if authorization is not None and base is not None:
                atomic_create(directory / "release.json", authorization)
                atomic_create(directory / "ledger-base.json", base)
            (directory / "checkpoints").mkdir()
            capture = Capture.open(directory, case)
        result = capture.run(caller, through=args.through, resume=args.resume, authority=authority)
        if result:
            verified = verify(capture)
            publish_ledger(verified)
            print(json_bytes(result.model_dump(mode="json", exclude={"refusal"})).decode())
            return int(result.status == "incomplete")
        print(json_bytes({"status": "paused", "tick": args.through}).decode())
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("preflight", help="print the immutable owner release inputs")
    pre.add_argument("--implementation", default="HEAD")
    run = commands.add_parser("run", help="start or resume the fixed resident case")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument(
        "--live", action="store_true", help="use the released live Responses transport"
    )
    run.add_argument("--release", type=Path)
    run.add_argument("--ledger", type=Path)
    run.add_argument("--implementation")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--through", type=int, default=HORIZON, help="pause after a committed tick")
    run.add_argument("--lock", type=Path, default=Path("C:/Temp/li-heavy.lock"))
    offline = commands.add_parser("replay", help="verify the capture without a provider")
    offline.add_argument("--out", type=Path, required=True)
    inspection = commands.add_parser(
        "export", help="verify and export to a fresh inspection directory"
    )
    inspection.add_argument("--out", type=Path, required=True)
    inspection.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        case = Case.load()
        if args.command == "preflight":
            raw = case.preflight(implementation(args.implementation, check_sources=True))
            print(
                json_bytes({"preflight_sha256": digest(raw), "preflight": read_json(raw)}).decode()
            )
        elif args.command == "run":
            return run_command(args, case)
        else:
            with lock(args.out / ".writer.lock"):
                verified = verify(checked_capture(args.out, case))
                publish_ledger(verified)
                if args.command == "export":
                    index = export_verified(verified, args.destination.resolve())
                    print(
                        json_bytes(
                            {
                                "index": str(args.destination / "index.json"),
                                "decisions": len(index.decisions),
                            }
                        ).decode()
                    )
                else:
                    print(
                        json_bytes(
                            {
                                "tick": verified.replay.frames[-1].tick,
                                "world_sha256": verified.world_hash,
                                "store_sha256": verified.store_hash,
                                "uncommitted_attempts": verified.tail_attempts,
                                "provider_calls": 0,
                            }
                        ).decode()
                    )
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Resident run stopped: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
