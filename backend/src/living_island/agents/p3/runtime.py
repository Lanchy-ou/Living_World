"""Resident-local P3 transactions and bounded, injected decision execution."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel
from pydantic_core import PydanticSerializationError

from living_island.agents.p3.cognition import (
    advance_goal_evidence,
    apply_goal_change,
    attached_goal_id,
    initial_goal_state,
    validate_proposal,
)
from living_island.agents.p3.context import assemble_context
from living_island.agents.p3.ports import (
    AttemptJournalPort,
    DecisionBudgetPort,
    FallbackAdapter,
    ProviderAdapter,
)
from living_island.agents.p3.prompts import RESIDENT_TEMPLATE, render_provider_request
from living_island.agents.p3.types import (
    CONTEXT_PROFILES,
    AttemptDispatch,
    CallDebit,
    CallReservation,
    CognitiveDelta,
    ContextAssembly,
    ContextProfile,
    ContextRecordP3,
    DecisionErrorP3,
    DecisionProposal,
    DecisionRecordP3,
    DecisionRequestP3,
    DetailCode,
    GoalChange,
    LLMCallRecordP3,
    P3IntentTemplate,
    P3PolicyConfig,
    P3PolicyPrivateState,
    PricingPin,
    ProviderRequest,
    ProviderResult,
    ResidentCognitiveState,
    ResidentIdentity,
    ResidentRuntimeStateP3,
    WireRequest,
    build_call_id,
    decode_base64,
)
from living_island.agents.types import RuleStateV0_1, build_intent_id, build_plan_id
from living_island.memory.experience import (
    capture_accepted_decision,
    ingest_experience,
    initial_experience,
)
from living_island.memory.p3_types import (
    RetrievalSelector,
    build_decision_id,
    canonical_bytes,
    canonical_sha256,
)
from living_island.world.protocol import (
    ActionIntent,
    ActionPlan,
    BoundaryPerceptionDelivery,
    DecisionTrigger,
    EmptyParameters,
    Perception,
    format_delivery_id,
)


class ReplayDiverged(ValueError):
    """Retained evidence does not reproduce this resident's transaction."""


class ProviderOverrun(ValueError):
    """A retained provider result exceeded its durable reservation."""


def _copy[T: BaseModel](value: T) -> T:
    return type(value).model_validate(value.model_dump(mode="json", warnings="error"))


def _monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def _money(input_tokens: int, output_tokens: int, pricing: PricingPin) -> int:
    return (input_tokens * pricing.input_micro_cny_per_million_tokens + 999999) // 1000000 + (
        output_tokens * pricing.output_micro_cny_per_million_tokens + 999999
    ) // 1000000


def debit_for_result(
    reservation: CallReservation, result: ProviderResult, pricing: PricingPin
) -> CallDebit:
    """Unknown usage consumes both reservations; overrun retains conservative debt."""
    unknown = result.token_input is None or result.token_output is None
    overrun = (result.token_input or 0) > reservation.input_reserved or (
        result.token_output or 0
    ) > reservation.output_reserved
    if unknown or overrun:
        input_charged = max(reservation.input_reserved, result.token_input or 0)
        output_charged = max(reservation.output_reserved, result.token_output or 0)
    else:
        assert result.token_input is not None and result.token_output is not None
        input_charged, output_charged = result.token_input, result.token_output
    return CallDebit(
        **reservation.model_dump(exclude={"allocation_key", "reservation_ordinal"}),
        input_reported=result.token_input,
        output_reported=result.token_output,
        input_charged=input_charged,
        output_charged=output_charged,
        money_charged=_money(input_charged, output_charged, pricing),
        usage_unknown=unknown,
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant: {value}")


def _parse_proposal(
    result: ProviderResult, request: DecisionRequestP3, config: P3PolicyConfig
) -> tuple[
    DecisionProposal | None,
    ActionPlan | None,
    CognitiveDelta | None,
    DecisionErrorP3 | None,
    DetailCode,
]:
    if result.outcome == "timeout":
        return None, None, None, "TIMEOUT", "ATTEMPT_TIMEOUT"
    if result.outcome == "provider_error":
        return None, None, None, "PROVIDER_ERROR", "PROVIDER_REJECTED"
    if result.outcome == "output_limit":
        return None, None, None, "PARSE_ERROR", "OUTPUT_LIMIT"
    try:
        if (
            not result.response_complete
            or result.raw_response is None
            or result.response_text is None
        ):
            raise ValueError("incomplete or undecodable response")
        body = json.loads(
            result.response_text, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        if not isinstance(body, dict) or set(body) != {
            "proposal_schema_version",
            "actions",
            "cognitive_delta",
        }:
            raise ValueError("unknown proposal envelope")
        if body["proposal_schema_version"] != "0.1":
            raise ValueError("unknown proposal version")
    except ValueError:
        return None, None, None, "PARSE_ERROR", "INVALID_JSON"
    try:
        actions = body["actions"]
        if not isinstance(actions, list) or not 1 <= len(actions) <= config.max_plan_actions:
            raise ValueError("invalid action count")
        for action in actions:
            canonical_bytes(P3IntentTemplate.model_validate(action))
    except (ValueError, TypeError, UnicodeError):
        return None, None, None, "INVALID_PLAN", "INVALID_ACTION"
    proposal = None
    try:
        proposal = DecisionProposal.model_validate(body)
        plan, delta = validate_proposal(proposal, request, config)
    except (ValueError, TypeError, UnicodeError):
        return proposal, None, None, "INVALID_DELTA", "INVALID_COGNITION"
    return proposal, plan, delta, None, None


def _validate_plan(plan: ActionPlan, request: DecisionRequestP3, limit: int) -> ActionPlan:
    if not isinstance(plan, ActionPlan):
        raise ValueError("fallback must return an ActionPlan")
    plan = _copy(plan)
    canonical_bytes(plan)
    plan_id = build_plan_id(request.actor_id, request.decision_ordinal)
    if (plan.actor_id, plan.plan_id, plan.created_at_tick) != (
        request.actor_id,
        plan_id,
        request.tick,
    ):
        raise ValueError("plan identity does not match request")
    if not 1 <= len(plan.intents) <= limit or [i.intent_id for i in plan.intents] != [
        build_intent_id(plan_id, i) for i in range(len(plan.intents))
    ]:
        raise ValueError("invalid bounded plan intents")
    return plan


def _wait(request: DecisionRequestP3) -> ActionPlan:
    plan_id = build_plan_id(request.actor_id, request.decision_ordinal)
    return ActionPlan(
        plan_id=plan_id,
        actor_id=request.actor_id,
        created_at_tick=request.tick,
        intents=[
            ActionIntent(
                intent_id=build_intent_id(plan_id, 0),
                plan_id=plan_id,
                actor_id=request.actor_id,
                action_type="wait",
                target=None,
                parameters=EmptyParameters(),
                reason=None,
            )
        ],
    )


class RuntimeP3:
    """Stage private state once; the coordinator commits budget and world-facing output."""

    def __init__(
        self,
        actor_id: str,
        policy_config: P3PolicyConfig,
        own_identity: ResidentIdentity,
        restored_state: ResidentRuntimeStateP3 | None = None,
        *,
        live_enabled: bool,
        provider: ProviderAdapter,
        budget: DecisionBudgetPort,
        attempts: AttemptJournalPort,
        fallback: FallbackAdapter,
        own_records: Sequence[DecisionRecordP3] | None = None,
        own_contexts: Sequence[ContextRecordP3] | None = None,
        run_id: str | None = None,
        context_profile: ContextProfile | None = None,
        purpose: Literal["live", "fake", "recorded-fake"] = "live",
        selector: RetrievalSelector | None = None,
        selector_sha256: str | None = None,
        template: bytes = RESIDENT_TEMPLATE,
        clock_ms: Callable[[], int] = _monotonic_ms,
    ) -> None:
        config, identity = _copy(policy_config), _copy(own_identity)
        if actor_id != identity.actor_id or config.identity_sha256 != canonical_sha256(identity):
            raise ValueError("actor identity/config mismatch")
        if type(live_enabled) is not bool or (run_id is not None and not run_id):
            raise ValueError("invalid live mode or run identity")
        self._config, self._run_id = config, run_id
        self._provider, self._budget, self._attempts, self._fallback = (
            provider,
            budget,
            attempts,
            fallback,
        )
        self._live_enabled, self._clock, self._template = live_enabled, clock_ms, template
        self._purpose, self._selector, self._selector_sha256 = purpose, selector, selector_sha256
        self._profile = (
            _copy(context_profile)
            if context_profile is not None
            else ContextProfile(
                context_profile_schema_version="0.1",
                context_profile_id=config.context_profile_id,
                retrieval_profile=CONTEXT_PROFILES[config.context_profile_id],
                projection_profile="p3-context-v0",
            )
        )
        if self._profile.context_profile_id != config.context_profile_id:
            raise ValueError("context profile/config mismatch")
        if purpose not in ("live", "fake", "recorded-fake") or (
            purpose == "live" and self._profile.retrieval_profile != "recent-relevant-v0"
        ):
            raise ValueError("fixture selectors require explicit fake purpose")
        if (own_records is None) != (own_contexts is None):
            raise ValueError("recorded decisions require their complete own context slice")
        self._records = None if own_records is None else [_copy(r) for r in own_records]
        self._contexts = None if own_contexts is None else [_copy(c) for c in own_contexts]
        if self._records is not None:
            assert self._contexts is not None
            if len(self._records) != len(self._contexts):
                raise ReplayDiverged("context/decision count differs")
            for ordinal, (record, context) in enumerate(
                zip(self._records, self._contexts, strict=True)
            ):
                if (
                    record.actor_id,
                    record.decision_ordinal,
                    context.request.actor_id,
                    context.request.decision_ordinal,
                    context.decision_id,
                    context.run_id,
                ) != (actor_id, ordinal, actor_id, ordinal, record.decision_id, record.run_id):
                    raise ReplayDiverged("own source slice is not complete and contiguous")
                if self._run_id is None:
                    self._run_id = record.run_id
                if record.run_id != self._run_id:
                    raise ReplayDiverged("source run mismatch")
        if restored_state is None:
            self._state = ResidentRuntimeStateP3(
                runtime_schema_version="0.2",
                actor_id=actor_id,
                policy_config=config,
                next_decision_ordinal=0,
                latest_perception_tick=-1,
                cognitive_state=ResidentCognitiveState(
                    cognitive_schema_version="0.1",
                    actor_id=actor_id,
                    identity=identity,
                    experience=initial_experience(actor_id),
                    goals=initial_goal_state(),
                ),
                policy_private=P3PolicyPrivateState(
                    private_schema_version="0.1",
                    mode="llm" if config.policy_id == "llm-v0" else "fallback",
                    fallback_state=RuleStateV0_1(
                        rule_state_version="0.1",
                        commitment=None,
                        issued_intents=[],
                        failed_targets=[],
                        cue_impressions=[],
                        canteen_capacity=None,
                    ),
                    last_fallback_ordinal=None,
                ),
            )
        else:
            self._state = _copy(restored_state)
            if (
                self._state.actor_id,
                self._state.policy_config,
                self._state.cognitive_state.identity,
            ) != (actor_id, config, identity) or self._run_id is None:
                raise ValueError(
                    "restored state needs matching actor/config/identity and trusted run"
                )
        self._validate_sources()
        if self._records is not None and self._state.next_decision_ordinal > len(self._records):
            raise ReplayDiverged("source slice ends before restored ordinal")
        self._decided_tick = max(
            (r.committed_tick for r in self._state.cognitive_state.experience.intent_refs),
            default=-1,
        )
        self._perception: Perception | None = None
        self._request: DecisionRequestP3 | None = None
        self._assembly: ContextAssembly | None = None
        self._pending: DecisionRecordP3 | None = None
        self._successor: ResidentRuntimeStateP3 | None = None
        self._started = 0
        self._failed = False

    @property
    def actor_id(self) -> str:
        return self._state.actor_id

    def _validate_sources(self) -> None:
        cognitive = self._state.cognitive_state
        runs = {r.source.run_id for r in cognitive.experience.records}
        for ref in cognitive.experience.intent_refs:
            suffix = f":d:{self.actor_id}:{ref.decision_ordinal:06d}"
            runs.add(ref.decision_id[: -len(suffix)])
        current = cognitive.goals.current
        if current is not None and current.evidence is not None:
            evidence = current.evidence
            if evidence.delivery_id != format_delivery_id(
                self._run_id or "", evidence.observed_tick, self.actor_id
            ):
                raise ValueError("goal evidence belongs to another run")
        if runs and runs != {self._run_id}:
            raise ValueError("restored experience belongs to another run")

    def _idle(self) -> None:
        if self._failed:
            raise ValueError("failed boundary requires checkpoint recovery")
        if self._request is not None:
            raise ValueError("decision is awaiting commitment")

    def ingest(self, delivery: BoundaryPerceptionDelivery) -> None:
        self._idle()
        packet = _copy(delivery)
        if packet.actor_id != self.actor_id:
            raise ValueError("foreign perception")
        run = self._run_id
        if run is None:
            suffix = f":perception:{packet.observed_tick:010d}:{self.actor_id}"
            if not packet.delivery_id.endswith(suffix) or len(packet.delivery_id) <= len(suffix):
                raise ValueError("delivery has no canonical run identity")
            run = packet.delivery_id[: -len(suffix)]
        if packet.delivery_id != format_delivery_id(run, packet.observed_tick, self.actor_id):
            raise ValueError("delivery run mismatch")
        current = self._state.cognitive_state
        experience = ingest_experience(current.experience, packet, run_id=run)
        goals = advance_goal_evidence(
            packet, current.experience.intent_refs, current.goals, run_id=run
        )
        cognitive = _copy(current.model_copy(update={"experience": experience, "goals": goals}))
        successor = _copy(
            self._state.model_copy(
                update={
                    "latest_perception_tick": packet.observed_tick,
                    "cognitive_state": cognitive,
                }
            )
        )
        self._state, self._perception, self._run_id = successor, packet.perception, run

    def make_request(self, tick: int, triggers: list[DecisionTrigger]) -> DecisionRequestP3:
        self._idle()
        if self._perception is None or self._perception.tick != tick or self._decided_tick == tick:
            raise ValueError("decision requires a fresh current boundary packet")
        started = self._now()
        assembly = assemble_context(
            self._perception,
            self._state.cognitive_state,
            self._profile,
            purpose=self._purpose,
            selector=self._selector,
            selector_sha256=self._selector_sha256,
        )
        request = DecisionRequestP3(
            request_schema_version="0.2",
            actor_id=self.actor_id,
            tick=tick,
            decision_ordinal=self._state.next_decision_ordinal,
            triggers=triggers,
            context=assembly.context,
        )
        self._request, self._assembly, self._started = _copy(request), assembly, started
        return _copy(request)

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or value < 0:
            raise ValueError("clock must return nonnegative integer milliseconds")
        return value

    def _remaining(self) -> int:
        elapsed = self._now() - self._started
        if elapsed < 0:
            raise ValueError("monotonic clock moved backwards")
        return self._config.limits.decision_timeout_ms - elapsed

    def decide(self, request: DecisionRequestP3) -> DecisionRecordP3:
        if (
            self._failed
            or self._pending is not None
            or self._request is None
            or _copy(request) != self._request
        ):
            raise ValueError("decision does not match the single prepared request")
        try:
            record, successor = self._replay() if self._records is not None else self._execute()
        except Exception:
            self._failed = True
            raise
        self._pending, self._successor = record, successor
        return _copy(record)

    def _continue(self) -> CognitiveDelta:
        current = self._state.cognitive_state.goals.current
        return CognitiveDelta(
            delta_schema_version="0.1",
            goal_change=GoalChange(
                operation="continue",
                expected_goal_id=None if current is None else current.goal_id,
                proposal=None,
            ),
        )

    def _stage_state(
        self, plan: ActionPlan, delta: CognitiveDelta, private: P3PolicyPrivateState
    ) -> ResidentRuntimeStateP3:
        assert self._request is not None and self._run_id is not None
        request, current = self._request, self._state.cognitive_state
        goals = apply_goal_change(
            current.goals, delta.goal_change, actor_id=self.actor_id, tick=request.tick
        )
        experience = capture_accepted_decision(
            current.experience,
            self._run_id,
            build_decision_id(self._run_id, self.actor_id, request.decision_ordinal),
            request.decision_ordinal,
            plan,
            attached_goal_id(goals),
            max_plan_actions=self._config.max_plan_actions,
        )
        cognitive = _copy(current.model_copy(update={"goals": goals, "experience": experience}))
        return _copy(
            self._state.model_copy(
                update={
                    "next_decision_ordinal": request.decision_ordinal + 1,
                    "cognitive_state": cognitive,
                    "policy_private": private,
                }
            )
        )

    def _fallback_plan(self) -> tuple[ActionPlan, P3PolicyPrivateState, bool]:
        assert self._request is not None
        # Adapter exceptions are programming/IO failures, not malformed policy output.
        output = self._fallback.decide(_copy(self._request), _copy(self._state.policy_private))
        try:
            plan, private = output
            plan = _validate_plan(plan, self._request, self._config.max_plan_actions)
            if not isinstance(private, P3PolicyPrivateState):
                raise ValueError("invalid fallback private state")
            private = _copy(private)
            if (
                private.mode != "fallback"
                or private.last_fallback_ordinal != self._request.decision_ordinal
            ):
                raise ValueError("fallback lifecycle cursor mismatch")
            self._stage_state(plan, self._continue(), private)
        except (ValueError, TypeError, PydanticSerializationError):
            return _wait(self._request), _copy(self._state.policy_private), True
        return plan, private, False

    def _prepare(self) -> ProviderRequest | None:
        assert self._assembly is not None and self._request is not None
        if self._assembly.error is not None or self._config.policy_id == "rule-based-v0":
            return None
        return render_provider_request(self._assembly, self._request, self._config, self._template)

    def _execute(self) -> tuple[DecisionRecordP3, ResidentRuntimeStateP3]:
        assert self._request is not None and self._assembly is not None and self._run_id is not None
        request, assembly, config = self._request, self._assembly, self._config
        decision_id = build_decision_id(self._run_id, self.actor_id, request.decision_ordinal)
        provider_request = self._prepare()
        wire: WireRequest | None = None
        input_tokens = 0
        error: DecisionErrorP3 | None = None
        detail: DetailCode = None
        if config.policy_id == "llm-v0":
            if not self._live_enabled:
                error, detail = "PROVIDER_ERROR", "RECOVERY_OFFLINE"
            elif assembly.error is not None:
                error, detail = "INVALID_CONTEXT", "MANDATORY_OVERSIZE"
            else:
                assert provider_request is not None
                wire = _copy(self._provider.prepare(_copy(provider_request)))
                body = decode_base64(wire.body_base64)
                decoded = json.loads(
                    body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
                )
                if canonical_bytes(decoded) != body:
                    raise ValueError("wire request must be canonical JSON bytes")
                if (
                    len(canonical_bytes(provider_request)) > config.limits.max_request_bytes
                    or len(body) > config.limits.max_request_bytes
                ):
                    error, detail = "INVALID_CONTEXT", "INPUT_LIMIT"
                else:
                    input_tokens = self._provider.count_input_tokens(
                        _copy(provider_request), _copy(wire)
                    )
                    if type(input_tokens) is not int or input_tokens < 0:
                        raise ValueError("counter must return a nonnegative integer")
                    if input_tokens > config.limits.max_input_tokens:
                        error, detail = "INVALID_CONTEXT", "INPUT_LIMIT"
                if error is not None:
                    provider_request = None
        context = ContextRecordP3(
            context_record_version="0.1",
            run_id=self._run_id,
            decision_id=decision_id,
            request=request,
            assembly=assembly,
            provider_request=provider_request,
        )
        self._attempts.stage_context(_copy(context))
        plan: ActionPlan | None = None
        delta: CognitiveDelta | None = None
        private = _copy(self._state.policy_private)
        call_ids: list[str] = []
        debits: list[CallDebit] = []
        if config.policy_id == "llm-v0" and error is None:
            assert (
                provider_request is not None
                and wire is not None
                and assembly.projection_sha256 is not None
            )
            request_hash = canonical_sha256(provider_request)
            wire_hash = hashlib.sha256(decode_base64(wire.body_base64)).hexdigest()
            for index in range(config.limits.max_attempts):
                remaining = self._remaining()
                if remaining <= 0:
                    error, detail = "TIMEOUT", "DECISION_TIMEOUT"
                    break
                call_id = build_call_id(decision_id, index)
                reservation = self._budget.admit(
                    call_id, input_tokens, config.limits.max_output_tokens, request_hash, wire_hash
                )
                if reservation is None:
                    error, detail = "BUDGET", "ADMISSION_DENIED"
                    break
                reservation = _copy(reservation)
                if (
                    reservation.call_id,
                    reservation.input_reserved,
                    reservation.output_reserved,
                    reservation.money_reserved,
                ) != (
                    call_id,
                    input_tokens,
                    config.limits.max_output_tokens,
                    _money(input_tokens, config.limits.max_output_tokens, config.pricing),
                ):
                    raise ValueError("authority reservation does not match requested admission")
                dispatch = AttemptDispatch(
                    dispatch_schema_version="0.1",
                    run_id=self._run_id,
                    decision_id=decision_id,
                    call_id=call_id,
                    actor_id=self.actor_id,
                    tick=request.tick,
                    decision_ordinal=request.decision_ordinal,
                    attempt_index=index,
                    request_sha256=canonical_sha256(request),
                    context_sha256=assembly.context_sha256,
                    projection_sha256=assembly.projection_sha256,
                    provider_request_sha256=request_hash,
                    provider_request=provider_request,
                    wire_request=wire,
                    wire_body_sha256=wire_hash,
                    allocation_key=reservation.allocation_key,
                    reservation_ordinal=reservation.reservation_ordinal,
                    prompt_version=config.prompt_version,
                    action_schema_version=config.action_schema_version,
                    adapter_id=config.adapter_id,
                    adapter_version=config.adapter_version,
                    model_id=config.model_id,
                    input_reserved=input_tokens,
                    output_reserved=reservation.output_reserved,
                    money_reserved=reservation.money_reserved,
                )
                self._attempts.before_call(_copy(context), _copy(dispatch))
                result = _copy(
                    self._provider.complete(
                        _copy(provider_request),
                        _copy(wire),
                        min(config.limits.attempt_timeout_ms, remaining),
                    )
                )
                debit = debit_for_result(reservation, result, config.pricing)
                proposal, plan, delta, error, detail = _parse_proposal(result, request, config)
                if self._remaining() <= 0:
                    error, detail = "TIMEOUT", "DECISION_TIMEOUT"
                    plan = None
                    delta = None
                terminal = LLMCallRecordP3(
                    call_schema_version="0.1",
                    run_id=self._run_id,
                    decision_id=decision_id,
                    call_id=call_id,
                    actor_id=self.actor_id,
                    tick=request.tick,
                    decision_ordinal=request.decision_ordinal,
                    attempt_index=index,
                    dispatch_sha256=canonical_sha256(dispatch),
                    result=result,
                    parsed_proposal=proposal,
                    validation_error=error,
                    detail_code=detail,
                    debit=debit,
                )
                self._attempts.after_call(_copy(terminal))
                call_ids.append(call_id)
                debits.append(debit)
                if (result.token_input or 0) > reservation.input_reserved or (
                    result.token_output or 0
                ) > reservation.output_reserved:
                    raise ProviderOverrun(
                        "provider usage exceeded its reservation; result retained"
                    )
                if error is None:
                    private = _copy(private.model_copy(update={"mode": "llm"}))
                    break
                if detail == "DECISION_TIMEOUT":
                    break
        malformed = False
        if config.policy_id == "rule-based-v0" or error is not None:
            plan, private, malformed = self._fallback_plan()
            delta = self._continue()
            if malformed and config.policy_id == "rule-based-v0":
                error, detail = "INVALID_PLAN", "INVALID_ACTION"
        assert plan is not None and delta is not None
        successor = self._stage_state(plan, delta, private)
        effective: Literal["llm-v0", "rule-based-v0", "sim-fallback-wait"] = (
            "sim-fallback-wait"
            if malformed
            else "rule-based-v0"
            if error is not None
            else config.policy_id
        )
        record = DecisionRecordP3(
            record_schema_version="0.2",
            run_id=self._run_id,
            decision_id=decision_id,
            tick=request.tick,
            actor_id=self.actor_id,
            decision_ordinal=request.decision_ordinal,
            policy_id=config.policy_id,
            effective_policy_id=effective,
            triggers=request.triggers,
            request_sha256=canonical_sha256(request),
            status="error" if error is not None else "ok",
            error_kind=error,
            detail_code=detail,
            plan=plan,
            substituted=error is not None,
            llm_call_id=call_ids[-1] if call_ids else None,
            context_sha256=assembly.context_sha256,
            projection_sha256=assembly.projection_sha256,
            accepted_delta=delta,
            call_ids=call_ids,
            state_before_sha256=canonical_sha256(self._state),
            state_after_sha256=canonical_sha256(successor),
            fallback_error="INVALID_PLAN" if malformed else None,
            policy_private_after=private,
            budget_debits=debits,
        )
        return record, successor

    def _replay(self) -> tuple[DecisionRecordP3, ResidentRuntimeStateP3]:
        assert self._request is not None and self._assembly is not None
        assert self._records is not None and self._contexts is not None
        ordinal = self._request.decision_ordinal
        if ordinal >= len(self._records):
            raise ReplayDiverged("recorded source exhausted")
        record, context = self._records[ordinal], self._contexts[ordinal]
        if (
            record.run_id != self._run_id
            or record.tick != self._request.tick
            or record.triggers != self._request.triggers
            or record.policy_id != self._config.policy_id
            or record.request_sha256 != canonical_sha256(self._request)
            or record.context_sha256 != self._assembly.context_sha256
            or record.projection_sha256 != self._assembly.projection_sha256
            or record.state_before_sha256 != canonical_sha256(self._state)
            or context.request != self._request
            or context.assembly != self._assembly
        ):
            raise ReplayDiverged("request, manifest or state-before mismatch")
        if context.provider_request is not None:
            if context.provider_request != self._prepare():
                raise ReplayDiverged("retained provider request mismatch")
        elif record.call_ids:
            raise ReplayDiverged("dispatched decision lacks provider request")
        try:
            plan = _validate_plan(record.plan, self._request, self._config.max_plan_actions)
            successor = self._stage_state(plan, record.accepted_delta, record.policy_private_after)
        except ValueError as exc:
            raise ReplayDiverged("recorded plan/delta/private state is invalid") from exc
        if record.state_after_sha256 != canonical_sha256(successor):
            raise ReplayDiverged("state-after mismatch")
        return _copy(record), successor

    def commit_decision(self, record: DecisionRecordP3) -> None:
        if (
            self._failed
            or self._pending is None
            or self._successor is None
            or _copy(record) != self._pending
        ):
            raise ValueError("commit does not match the staged decision")
        self._state, self._decided_tick = self._successor, self._pending.tick
        self._request = None
        self._assembly = None
        self._pending = None
        self._successor = None

    def abort_pending(self) -> None:
        """Discard staged cognition; durable reservations and attempts remain untouched."""
        self._request = None
        self._assembly = None
        self._pending = None
        self._successor = None
        self._failed = True

    def export_state(self) -> ResidentRuntimeStateP3:
        self._idle()
        return _copy(self._state)


def create_p3_runtime(
    actor_id: str,
    policy_config: P3PolicyConfig,
    own_identity: ResidentIdentity,
    restored_state: ResidentRuntimeStateP3 | None = None,
    *,
    live_enabled: bool,
    provider: ProviderAdapter,
    budget: DecisionBudgetPort,
    attempts: AttemptJournalPort,
    fallback: FallbackAdapter,
    own_records: Sequence[DecisionRecordP3] | None = None,
    own_contexts: Sequence[ContextRecordP3] | None = None,
    run_id: str | None = None,
    context_profile: ContextProfile | None = None,
    purpose: Literal["live", "fake", "recorded-fake"] = "live",
    selector: RetrievalSelector | None = None,
    selector_sha256: str | None = None,
    template: bytes = RESIDENT_TEMPLATE,
    clock_ms: Callable[[], int] = _monotonic_ms,
) -> RuntimeP3:
    """Create an isolated runtime using frozen ports and explicit local execution mode."""
    return RuntimeP3(
        actor_id,
        policy_config,
        own_identity,
        restored_state,
        live_enabled=live_enabled,
        provider=provider,
        budget=budget,
        attempts=attempts,
        fallback=fallback,
        own_records=own_records,
        own_contexts=own_contexts,
        run_id=run_id,
        context_profile=context_profile,
        purpose=purpose,
        selector=selector,
        selector_sha256=selector_sha256,
        template=template,
        clock_ms=clock_ms,
    )
