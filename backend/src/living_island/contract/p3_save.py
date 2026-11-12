"""Backend-only approved P3 save, retained-input and recovery envelopes."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from living_island.agents.p3.types import (
    AllocationEntry,
    BudgetCaps,
    BudgetLedgerP3,
    CallDebit,
    P3Model,
    P3PolicyConfig,
    ResidentRuntimeStateP3,
)
from living_island.agents.types import PolicyConfig
from living_island.contract.save import DeliveryCursor
from living_island.world.protocol import (
    ActionPlan,
    BoundaryPerceptionDelivery,
    DeferredDecisionTriggers,
    NonNegInt,
    PosInt,
    Sha256Hex,
    format_delivery_id,
    require_sorted_unique,
)
from living_island.world.state import WorldState

LOG_NAMES = (
    "contexts-p3.jsonl",
    "decisions-p3.jsonl",
    "events.jsonl",
    "llm-calls.jsonl",
    "llm-dispatches.jsonl",
)
INPUT_NAMES = tuple(
    sorted(
        (
            "config.json",
            "map.txt",
            "p3-policy-configs.json",
            "identities.json",
            "identity-sources.json",
            "prompt.txt",
            "action-schema.json",
            "context-profile.json",
            "trial-registration.json",
            "implementation.json",
        )
    )
)


def repository_path(value: str) -> str:
    """Validate a portable repository-relative locator, never an authority locator."""
    path = PurePosixPath(value)
    win = PureWindowsPath(value)
    if (
        not value
        or "\\" in value
        or win.drive
        or path.is_absolute()
        or str(path) != value
        or any(part in (".", "..") for part in path.parts)
    ):
        raise ValueError("expected a normalized repository-relative POSIX path")
    return value


class LogPrefix(P3Model):
    name: str
    records: NonNegInt
    sha256: Sha256Hex


def check_prefix_names(prefixes: list[LogPrefix]) -> None:
    if tuple(item.name for item in prefixes) != LOG_NAMES:
        raise ValueError("log prefixes must contain the five exact filename-sorted names")


class AgentStateP3(P3Model):
    profiles: list[dict[str, JsonValue]]
    goal_states: list[dict[str, JsonValue]]
    personal_memories: list[dict[str, JsonValue]]
    relationships: list[dict[str, JsonValue]]
    queued_plans: list[ActionPlan]
    deferred_decision_triggers: list[DeferredDecisionTriggers]
    delivered_perception_ticks: list[DeliveryCursor]
    runtime_states: list[ResidentRuntimeStateP3]

    @model_validator(mode="after")
    def _shape(self) -> AgentStateP3:
        if any((self.profiles, self.goal_states, self.personal_memories, self.relationships)):
            raise ValueError("legacy agent placeholders must be empty in P3")
        for name in (
            "queued_plans",
            "deferred_decision_triggers",
            "delivered_perception_ticks",
            "runtime_states",
        ):
            require_sorted_unique([item.actor_id for item in getattr(self, name)], name)
        return self


class SavePackageP3(P3Model):
    save_schema_version: Literal["0.2"]
    world: WorldState
    agent_state: AgentStateP3
    event_cursor: NonNegInt
    llm_record_cursor: NonNegInt
    decision_record_cursor: NonNegInt
    context_record_cursor: NonNegInt
    dispatch_record_cursor: NonNegInt
    pending_perception_deliveries: list[BoundaryPerceptionDelivery]
    canonical_config_hash: Sha256Hex
    canonical_map_hash: Sha256Hex
    input_manifest_sha256: Sha256Hex
    log_prefixes: list[LogPrefix]
    run_budget: BudgetLedgerP3
    allocation_entries: list[AllocationEntry]
    live_enabled: bool

    @model_validator(mode="after")
    def _consistent(self) -> SavePackageP3:
        world, agents = self.world, self.agent_state
        residents = [resident.id for resident in world.residents]
        living = {resident.id for resident in world.residents if resident.alive}
        runtimes = {state.actor_id: state for state in agents.runtime_states}
        cursors = {
            cursor.actor_id: cursor.last_observed_tick
            for cursor in agents.delivered_perception_ticks
        }
        if self.event_cursor != world.event_log_cursor:
            raise ValueError("event_cursor must equal world.event_log_cursor")
        if (self.canonical_config_hash, self.canonical_map_hash) != (
            world.config_hash,
            world.map_hash,
        ):
            raise ValueError("saved world and canonical content hashes disagree")
        if list(runtimes) != residents or list(cursors) != residents:
            raise ValueError("exactly one runtime and delivery cursor per resident is required")
        if (
            sum(state.next_decision_ordinal for state in runtimes.values())
            != self.decision_record_cursor
        ):
            raise ValueError("runtime ordinals must sum to committed decisions")
        if self.context_record_cursor != self.decision_record_cursor:
            raise ValueError("exactly one context per committed decision is required")
        if self.dispatch_record_cursor != self.llm_record_cursor:
            raise ValueError("every committed dispatch must have one terminal call")
        if world.tick == 0 and self.decision_record_cursor:
            raise ValueError("tick-zero checkpoint cannot contain decisions")
        for actor, cursor in cursors.items():
            if runtimes[actor].latest_perception_tick != cursor or cursor >= world.tick:
                raise ValueError("runtime/delivery cursors must agree before the saved tick")
            if actor in living and cursor != world.tick - 1:
                raise ValueError("living delivery cursor must be saved tick minus one")
        keys = [(item.observed_tick, item.actor_id) for item in self.pending_perception_deliveries]
        if keys != sorted(set(keys)) or [
            item.actor_id for item in self.pending_perception_deliveries
        ] != sorted(living):
            raise ValueError("one sorted pending packet per living resident is required")
        for packet in self.pending_perception_deliveries:
            if packet.observed_tick != world.tick or packet.delivery_id != format_delivery_id(
                world.run_id, world.tick, packet.actor_id
            ):
                raise ValueError("pending packet must retain the saved boundary identity")
        check_prefix_names(self.log_prefixes)
        counts = (
            self.context_record_cursor,
            self.decision_record_cursor,
            self.event_cursor,
            self.llm_record_cursor,
            self.dispatch_record_cursor,
        )
        if tuple(prefix.records for prefix in self.log_prefixes) != counts:
            raise ValueError("log prefix counts must equal committed cursors")
        debits = []
        for ordinal, entry in enumerate(self.allocation_entries):
            if entry.state == "reserved" or entry.debit is None:
                raise ValueError("checkpoint allocation mirror cannot contain reservations")
            if (
                entry.reservation.reservation_ordinal != ordinal
                or entry.reservation.allocation_key != self.run_budget.allocation_key
            ):
                raise ValueError("allocation mirror must preserve key and reservation order")
            debits.append(entry.debit)
        if len({debit.call_id for debit in debits}) != len(debits):
            raise ValueError("allocation mirror contains duplicate calls")
        ledger = self.run_budget
        if (
            len(debits),
            sum(d.input_charged for d in debits),
            sum(d.output_charged for d in debits),
            sum(d.money_charged for d in debits),
            sum(d.usage_unknown for d in debits),
        ) != (
            ledger.attempts_charged,
            ledger.input_charged,
            ledger.output_charged,
            ledger.money_charged,
            ledger.unknown_usage_count,
        ):
            raise ValueError("allocation mirror debit totals must equal the ledger")
        if [
            entry.debit for entry in self.allocation_entries if entry.state == "recovery"
        ] != ledger.recovery_debits:
            raise ValueError("allocation recovery entries must equal ledger recovery debits")
        return self


class NamedHash(P3Model):
    name: str
    sha256: Sha256Hex


class P3InputManifest(P3Model):
    input_manifest_version: Literal["0.1"]
    run_id: str
    files: list[NamedHash]

    @model_validator(mode="after")
    def _files(self) -> P3InputManifest:
        if tuple(item.name for item in self.files) != INPUT_NAMES:
            raise ValueError("retained manifest must contain exactly the approved sorted inputs")
        return self


class InputPin(P3Model):
    path: str
    sha256: Sha256Hex

    @model_validator(mode="after")
    def _path(self) -> InputPin:
        repository_path(self.path)
        return self


class ImplementationModule(P3Model):
    role: Literal["adapter", "counter", "goal", "runtime", "schema", "selector"]
    files: Annotated[list[InputPin], Field(min_length=1)]

    @model_validator(mode="after")
    def _files(self) -> ImplementationModule:
        require_sorted_unique([item.path for item in self.files], "implementation files")
        return self


class ImplementationPin(P3Model):
    implementation_pin_version: Literal["0.1"]
    code_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    modules: list[ImplementationModule]

    @model_validator(mode="after")
    def _modules(self) -> ImplementationPin:
        if [item.role for item in self.modules] != [
            "adapter",
            "counter",
            "goal",
            "runtime",
            "schema",
            "selector",
        ]:
            raise ValueError("implementation roles must occur once in approved enum order")
        return self


class ActorPolicyConfig(P3Model):
    actor_id: str
    config: P3PolicyConfig


class TrialCase(P3Model):
    case_id: str
    seed: Annotated[int, Field(ge=1, le=4294967295)]
    ticks: PosInt
    llm_actor_ids: list[str]
    policy_templates: list[dict[str, JsonValue]]
    caps: BudgetCaps


class ControlCase(P3Model):
    case_id: str
    paired_case_id: str
    seed: Annotated[int, Field(ge=1, le=4294967295)]
    ticks: PosInt
    policy_config: PolicyConfig
    caps: BudgetCaps


class TrialRegistration(P3Model):
    registration_schema_version: Literal["0.1"]
    registration_id: Annotated[str, Field(pattern=r"^[a-z0-9-]+$")]
    purpose: Literal["smoke", "development", "acceptance", "fake"]
    revision: PosInt
    implementation_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    implementation_pins: list[InputPin]
    world_pin_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    world_config_path: str
    world_map_path: str
    world_config_sha256: Sha256Hex
    world_map_sha256: Sha256Hex
    input_pins: list[InputPin]
    cases: Annotated[list[TrialCase], Field(min_length=1)]
    controls: list[ControlCase]
    aggregate_caps: BudgetCaps
    fake_fixture_id: str | None

    @model_validator(mode="after")
    def _registration(self) -> TrialRegistration:
        repository_path(self.world_config_path)
        repository_path(self.world_map_path)
        for pins in (self.implementation_pins, self.input_pins):
            require_sorted_unique([item.path for item in pins], "registration pins")
        if (self.purpose == "fake") != (self.fake_fixture_id is not None):
            raise ValueError("only fake registrations have a fixture identity")
        if len({case.seed for case in self.cases}) != len(self.cases):
            raise ValueError("registration seeds must be unique")
        for case in self.cases:
            if case.case_id != f"{self.registration_id}.s{case.seed}":
                raise ValueError("case ID must bind registration ID and seed")
            require_sorted_unique(case.llm_actor_ids, "llm_actor_ids")
        for field in BudgetCaps.model_fields:
            if getattr(self.aggregate_caps, field) != sum(
                getattr(case.caps, field) for case in self.cases
            ) + sum(getattr(control.caps, field) for control in self.controls):
                raise ValueError("aggregate caps must equal the component-wise case sum")
        if self.purpose != "acceptance" and self.controls:
            raise ValueError("only acceptance registrations contain controls")
        return self


class ResumeOriginP3(P3Model):
    origin_version: Literal["0.2"]
    source_run_id: str
    checkpoint_tick: NonNegInt
    checkpoint_sha256: Sha256Hex
    log_prefixes: list[LogPrefix]
    source_input_manifest_sha256: Sha256Hex
    recovery_mode: Literal["complete", "offline"]
    allocation_key: Sha256Hex
    orphan_artifacts: list[NamedHash]
    recovery_entries: list[AllocationEntry]
    recovery_debits: list[CallDebit]

    @model_validator(mode="after")
    def _recovery(self) -> ResumeOriginP3:
        check_prefix_names(self.log_prefixes)
        require_sorted_unique([item.name for item in self.orphan_artifacts], "orphan artifacts")
        for item in self.orphan_artifacts:
            repository_path(item.name)
        if self.recovery_mode == "complete" and (
            self.orphan_artifacts or self.recovery_entries or self.recovery_debits
        ):
            raise ValueError("clean continuation cannot import recovery evidence or debits")
        if any(
            entry.state != "recovery"
            or entry.debit is None
            or entry.reservation.allocation_key != self.allocation_key
            for entry in self.recovery_entries
        ):
            raise ValueError("origin entries must be recovery entries for the same allocation")
        if [entry.debit for entry in self.recovery_entries] != self.recovery_debits:
            raise ValueError("origin recovery debits must match entries in reservation order")
        ordinals = [entry.reservation.reservation_ordinal for entry in self.recovery_entries]
        if ordinals and ordinals != list(range(ordinals[0], ordinals[0] + len(ordinals))):
            raise ValueError("recovery reservations must be contiguous and ordered")
        return self


class DecisionTraceP3(P3Model):
    trace_schema_version: Literal["0.2"]
    run_id: str
    config_hash: Sha256Hex
    map_hash: Sha256Hex
    final_tick: NonNegInt
    input_manifest_sha256: Sha256Hex
    final_checkpoint_sha256: Sha256Hex
    log_prefixes: list[LogPrefix]
    final_world_sha256: Sha256Hex
    final_runtime_states_sha256: Sha256Hex
    final_budget_sha256: Sha256Hex

    @model_validator(mode="after")
    def _prefixes(self) -> DecisionTraceP3:
        check_prefix_names(self.log_prefixes)
        return self
