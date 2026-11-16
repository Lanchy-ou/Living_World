import type { WorldEvent } from "../replay/types.ts";
import type { DecisionInspection } from "./generated/decision.ts";
import type { InspectionDecisionRef, InspectionSampleRef, P3InspectionIndex, ResidentIdentity } from "./generated/index.ts";
import type { TrialCase, TrialRegistration } from "./generated/registration.ts";
import type { ExperienceRecord, GoalState, OwnedIntentRef, ResidentInspection } from "./generated/sample.ts";
import { canonicalJson, deliveryId, padNumber, requireInspection, sameJson, sha256Bytes, utf8 } from "./encoding.ts";

const hashJson = (value: unknown) => sha256Bytes(utf8(canonicalJson(value)));
const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export async function checkDecision(
  runId: string, ref: InspectionDecisionRef, shard: DecisionInspection, identity: ResidentIdentity,
  eventsByIntent: ReadonlyMap<string, readonly WorldEvent[]>,
) {
  const { record, context, calls, dispatches } = shard;
  const { request, assembly } = context;
  const tag = ref.decision_id;
  const correctRecord = (row: typeof record | (typeof calls)[number] | (typeof dispatches)[number]) =>
    row.run_id === runId && row.decision_id === tag && row.actor_id === ref.actor_id &&
    row.tick === ref.tick && row.decision_ordinal === ref.ordinal;
  requireInspection(correctRecord(record), `Decision ${tag} differs from its index reference.`);
  requireInspection(
    context.run_id === runId && context.decision_id === tag &&
    request.actor_id === ref.actor_id && request.tick === ref.tick && request.decision_ordinal === ref.ordinal &&
    request.context.perception.actor_id === ref.actor_id && request.context.perception.tick === ref.tick &&
    sameJson(request.triggers, record.triggers) && sameJson(request.context.identity, identity) &&
    sameJson(request.context, assembly.context),
    `Decision ${tag} has a mismatched request, perception, or context identity.`,
  );
  const projection = assembly.provider_projection;
  const [requestHash, contextHash, projectionHash] = await Promise.all([
    hashJson(request),
    hashJson(assembly.context),
    projection === null ? null : hashJson(projection),
  ]);
  requireInspection(
    requestHash === record.request_sha256 && contextHash === record.context_sha256 &&
    contextHash === assembly.context_sha256 && projectionHash === record.projection_sha256 &&
    projectionHash === assembly.projection_sha256,
    `Decision ${tag} has a mismatched request, context, or projection hash.`,
  );
  const manifest = assembly.manifest;
  const recalled = new Map(assembly.context.recalled_experience.map((row) => [row.experience_id, row]));
  requireInspection(
    sameJson(manifest.experiences.filter((row) => row.retrieved).map((row) => row.experience_id), [...recalled.keys()]) &&
    sameJson(manifest.experiences.filter((row) => row.projected).map((row) => row.experience_id),
      projection?.recalled_experience.map((row) => row.experience_id) ?? []) &&
    manifest.evicted_record_count + manifest.retained_record_count === manifest.store_next_sequence,
    `Decision ${tag} has an inconsistent inclusion or eviction manifest.`,
  );
  if (projection !== null) {
    const { explored_static_tiles: projectedTiles, ...projectedPerception } = projection.perception;
    const { explored_static_tiles: fullTiles, ...fullPerception } = assembly.context.perception;
    const tileKey = (position: { x: number; y: number }) => `${position.x},${position.y}`;
    const tiles = new Map(fullTiles.map((row) => [tileKey(row.position), row]));
    const projectedKeys = new Set(projectedTiles.map((row) => tileKey(row.position)));
    const includedKeys = new Set(manifest.static_tiles.filter((row) => row.projected).map((row) => tileKey(row.position)));
    requireInspection(
      sameJson(projection.identity, identity) && sameJson(projection.goals, assembly.context.goals) &&
      sameJson(projection.owned_intents, assembly.context.owned_intents) && sameJson(projectedPerception, fullPerception) &&
      projection.recalled_experience.every((row) => recalled.has(row.experience_id) && sameJson(row, recalled.get(row.experience_id))) &&
      includedKeys.size === projectedKeys.size && [...includedKeys].every((key) => projectedKeys.has(key)) &&
      projectedTiles.every((row) => tiles.has(tileKey(row.position)) && sameJson(row, tiles.get(tileKey(row.position)))) &&
      manifest.projection_bytes === utf8(canonicalJson(projection)).byteLength && assembly.error === null,
      `Decision ${tag} has a projection that disagrees with delivered data or the manifest.`,
    );
  } else {
    requireInspection(
      assembly.error === "MANDATORY_OVERSIZE" && manifest.projection_bytes === null &&
      !manifest.static_tiles.some((row) => row.projected) && context.provider_request === null,
      `Decision ${tag} has inconsistent projection omission evidence.`,
    );
  }

  const { plan, call_ids: callIds, budget_debits: debits } = record;
  const planId = `${record.actor_id}:p${padNumber(record.decision_ordinal)}`;
  requireInspection(
    plan.plan_id === planId && plan.actor_id === record.actor_id && plan.created_at_tick === record.tick &&
    plan.intents.every((intent, i) =>
      intent.plan_id === planId && intent.intent_id === `${planId}:i${i}` && intent.actor_id === record.actor_id),
    `Decision ${tag} has a foreign accepted plan or intent.`,
  );
  requireInspection(
    callIds.length <= 2 && dispatches.length === callIds.length && calls.length === callIds.length &&
    debits.length === callIds.length && record.llm_call_id === (callIds.at(-1) ?? null) &&
    (record.policy_id === "llm-v0" || callIds.length === 0) &&
    (record.effective_policy_id !== "llm-v0" || callIds.length > 0),
    `Decision ${tag} has an incomplete attempt chain.`,
  );
  for (const [i, call] of calls.entries()) {
    const dispatch = dispatches[i];
    const callId = `${tag}:a${i}`;
    const debit = debits[i];
    requireInspection(
      correctRecord(call) && correctRecord(dispatch) && call.attempt_index === i && dispatch.attempt_index === i &&
      callId === callIds[i] && callId === call.call_id && callId === dispatch.call_id && callId === debit.call_id &&
      dispatch.request_sha256 === requestHash && dispatch.context_sha256 === contextHash &&
      dispatch.projection_sha256 === projectionHash && sameJson(dispatch.provider_request, context.provider_request) &&
      sameJson(call.debit, debit) && debit.input_reserved === dispatch.input_reserved &&
      debit.output_reserved === dispatch.output_reserved && debit.money_reserved === dispatch.money_reserved &&
      debit.input_reported === call.result.token_input && debit.output_reported === call.result.token_output &&
      debit.usage_unknown === (call.result.token_input === null || call.result.token_output === null),
      `Attempt ${callId} differs from its committed request, dispatch, result, or debit.`,
    );
    const wireBody = Uint8Array.from(atob(dispatch.wire_request.body_base64), (character) => character.charCodeAt(0));
    const [dispatchHash, providerHash, wireHash] = await Promise.all([
      hashJson(dispatch), hashJson(dispatch.provider_request), sha256Bytes(wireBody),
    ]);
    requireInspection(
      call.dispatch_sha256 === dispatchHash && dispatch.provider_request_sha256 === providerHash &&
      dispatch.wire_body_sha256 === wireHash,
      `Attempt ${callId} has a mismatched dispatch or provider request hash.`,
    );
  }
  const outcomeIds = plan.intents.flatMap((intent) => eventsByIntent.get(intent.intent_id) ?? [])
    .sort((left, right) => left.tick - right.tick || left.seq_in_tick - right.seq_in_tick)
    .map((event) => event.event_id);
  requireInspection(
    sameJson(outcomeIds, shard.outcome_event_ids),
    `Decision ${tag} outcome IDs differ from the recorded events for its accepted plan.`,
  );
}

export async function checkRegistration(
  registration: TrialRegistration, index: P3InspectionIndex, decisions: Iterable<DecisionInspection>,
) {
  requireInspection(
    registration.world_config_sha256 === index.config_hash && registration.world_map_sha256 === index.map_hash,
    "Inspection registration world config or map differs from the replay.",
  );
  const hashes = new Map(await Promise.all(index.actors.map(async ({ actor_id, identity }) =>
    [actor_id, await hashJson(identity)] as const)));
  const items = Array.from(decisions);
  const allocationKeys = new Set(items.flatMap((shard) => shard.dispatches.map((dispatch) => dispatch.allocation_key)));
  const cases: TrialCase[] = [];
  const seeds = new Set<number>();
  for (const entry of registration.cases) {
    requireInspection(
      !seeds.has(entry.seed) && entry.case_id === `${registration.registration_id}.s${entry.seed}`,
      "Inspection registration has an invalid case identity.",
    );
    seeds.add(entry.seed);
    if (entry.ticks !== index.final_tick || entry.policy_templates.length !== hashes.size) continue;
    const allocationKey = await hashJson({ case_id: entry.case_id, registration_sha256: index.registration_sha256 });
    if (allocationKeys.size > 0 && (allocationKeys.size !== 1 || !allocationKeys.has(allocationKey))) continue;
    const profiles = new Map<string, Record<string, unknown>>();
    const llmActors = new Set(entry.llm_actor_ids);
    if (llmActors.size !== entry.llm_actor_ids.length || entry.llm_actor_ids.some((actor) => !hashes.has(actor))) continue;
    for (const template of entry.policy_templates) {
      const { actor_id: actor, config } = template;
      if (typeof actor !== "string" || profiles.has(actor) || !hashes.has(actor) ||
        Object.keys(template).length !== 2 || !isRecord(config) || "trial_registration_sha256" in config ||
        config.seed !== entry.seed || config.identity_sha256 !== hashes.get(actor) ||
        config.policy_id !== (llmActors.has(actor) ? "llm-v0" : "rule-based-v0")) continue;
      profiles.set(actor, config);
    }
    if (profiles.size !== hashes.size) continue;
    if (!items.every(({ record, context, dispatches }) => {
      const config = profiles.get(record.actor_id)!;
      const policy = llmActors.has(record.actor_id) ? "llm-v0" : "rule-based-v0";
      const manifest = context.assembly.manifest;
      const retrieval = manifest.context_profile_id === "p3-context-v0" ? "recent-relevant-v0" :
        manifest.context_profile_id === "p3-context-recent-only-fixture-v0" &&
        registration.purpose === "fake" && registration.fake_fixture_id === "vf-20" ? "recent-only-fixture-v0" : undefined;
      return record.policy_id === policy && config.context_profile_id === manifest.context_profile_id &&
        manifest.retrieval_profile === retrieval && dispatches.every((dispatch) =>
          dispatch.model_id === config.model_id && dispatch.adapter_id === config.adapter_id &&
          dispatch.adapter_version === config.adapter_version && dispatch.prompt_version === config.prompt_version &&
          dispatch.action_schema_version === config.action_schema_version && isRecord(config.provider_settings) &&
          sameJson(dispatch.provider_request.settings, config.provider_settings));
    })) continue;
    cases.push(entry);
  }
  requireInspection(cases.length > 0, "No registered case matches the inspection horizon, actor identities, policies, and strategies.");
}

export function checkSample(
  ref: InspectionSampleRef, sample: ResidentInspection, identity: ResidentIdentity,
  latestObservation: number, latestDecision: string | null,
) {
  const tag = `${ref.actor_id} at tick ${ref.tick}`;
  requireInspection(
    sample.tick === ref.tick && sample.actor_id === ref.actor_id && sameJson(sample.identity, identity),
    `Sample ${tag} differs from its index or actor identity.`,
  );
  requireInspection(
    sample.latest_perception_tick === latestObservation && sample.latest_decision_id === latestDecision,
    `Sample ${tag} has an inconsistent pre-ingestion cursor or latest decision.`,
  );
  const count = Math.min(8, sample.retained_record_count);
  requireInspection(
    sample.retained_record_count <= sample.next_sequence && sample.recent_experience.length === count &&
    sample.recent_experience.every((entry, i) => entry.sequence === sample.next_sequence - count + i) &&
    (latestObservation >= 0 || (sample.next_sequence === 0 && sample.goals.current === null &&
      sample.goals.next_goal_sequence === 0)),
    `Sample ${tag} does not preserve the last retained experience sequence.`,
  );
}

const deliveryFields = {
  own_state: "own_state",
  entity_seen: "visible_entities",
  transient_seen: "transient_sightings",
  cue_seen: "environmental_cues",
  heard_speech: "heard_utterances",
  action_feedback: "last_action_feedback",
} as const;

interface SourceData {
  readonly runId: string;
  readonly decisions: ReadonlyMap<string, DecisionInspection>;
  readonly decisionsByActorTick: ReadonlyMap<string, ReadonlyMap<number, DecisionInspection>>;
  readonly eventsById: ReadonlyMap<string, WorldEvent>;
  readonly eventsByIntent: ReadonlyMap<string, readonly WorldEvent[]>;
}

export function checkSources(
  data: SourceData, actor: string, observedThrough: number, goals: GoalState,
  experiences: readonly ExperienceRecord[],
) {
  function checkOwned(ref: OwnedIntentRef) {
    const source = data.decisions.get(ref.decision_id)?.record;
    requireInspection(
      source?.actor_id === actor && source.tick === ref.committed_tick &&
      source.decision_ordinal === ref.decision_ordinal &&
      source.plan.intents.some((intent) => sameJson(intent, ref.intent)),
      `Source intent ${ref.intent.intent_id} does not resolve to its committed own decision.`,
    );
  }
  const goal = goals.current;
  if (goal !== null) {
    const evidence = goal.evidence;
    requireInspection(
      goal.goal_id === `${actor}:g${padNumber(goals.next_goal_sequence - 1)}` &&
      goal.created_at_tick <= observedThrough && (goal.status === "intended") === (evidence === null),
      `Goal ${goal.goal_id} has an inconsistent identity, cursor, or evidence state.`,
    );
    if (evidence !== null) {
      const own = evidence.owned_intent;
      checkOwned(own);
      const origin = data.decisionsByActorTick.get(actor)?.get(evidence.observed_tick);
      requireInspection(
        evidence.observed_tick <= observedThrough && evidence.observed_tick > own.committed_tick &&
        evidence.delivery_id === deliveryId(data.runId, actor, evidence.observed_tick) &&
        evidence.feedback.intent_id === own.intent.intent_id && own.goal_id === goal.goal_id &&
        (origin === undefined || sameJson(origin.context.request.context.perception.last_action_feedback, evidence.feedback)),
        `Goal ${goal.goal_id} has invalid own completion evidence.`,
      );
      if (goal.status === "observed_complete") {
        const predicate = goal.completion;
        requireInspection(
          predicate.kind === "own_action_success" && evidence.feedback.status === "success" &&
          sameJson([predicate.action_type, predicate.target, predicate.parameters],
            [own.intent.action_type, own.intent.target, own.intent.parameters]) &&
          data.eventsByIntent.get(own.intent.intent_id)?.some((event) =>
            event.type === "action_succeeded" && event.actor_id === actor && event.tick === evidence.observed_tick),
          `Goal ${goal.goal_id} completion does not match the recorded own successful action.`,
        );
      }
    }
  }
  const observedIds = new Set<string>();
  for (const experience of experiences) {
    const { source, payload, kind, observed_tick: tick } = experience;
    const label = experience.experience_id;
    requireInspection(
      !observedIds.has(label) && experience.owner_id === actor && tick <= observedThrough &&
      source.run_id === data.runId && label === `${actor}:e${padNumber(experience.sequence)}`,
      `Experience ${label} has a foreign, duplicate, or future source.`,
    );
    observedIds.add(label);
    if (source.source_kind === "decision") {
      const origin = data.decisions.get(source.decision_id)?.record;
      requireInspection(
        kind === "accepted_decision" && payload.information_kind === "interpretation" &&
        origin?.actor_id === actor && origin.tick === tick && origin.decision_ordinal === source.decision_ordinal &&
        "plan" in payload.data && sameJson(payload.data.plan, origin.plan),
        `Experience ${label} has an invalid accepted decision source.`,
      );
      continue;
    }
    requireInspection(
      kind !== "accepted_decision" && source.field === deliveryFields[kind] &&
      source.delivery_id === deliveryId(data.runId, actor, tick) && payload.information_kind === "delivered",
      `Experience ${label} has an invalid resident delivery source.`,
    );
    const perception = data.decisionsByActorTick.get(actor)?.get(tick)?.context.request.context.perception;
    if (source.field === "last_action_feedback") {
      requireInspection(
        source.index === null && "feedback" in payload.data &&
        (perception === undefined || sameJson(payload.data.feedback, perception.last_action_feedback)),
        `Experience ${label} does not match its delivered feedback.`,
      );
      if (payload.data.owned_intent !== null) checkOwned(payload.data.owned_intent);
    } else if (source.field === "own_state") {
      requireInspection(
        source.index === null && "condition" in payload.data &&
        (perception === undefined || sameJson(payload.data, {
          condition: perception.own_condition, position: perception.own_position, inventory: perception.own_inventory,
        })),
        `Experience ${label} does not match its delivered own state.`,
      );
    } else {
      requireInspection(
        source.index !== null && source.index >= 0 &&
        (perception === undefined ||
          (source.index < perception[source.field].length && sameJson(payload.data, perception[source.field][source.index]))),
        `Experience ${label} does not match its delivered field and index.`,
      );
      if (source.field === "heard_utterances") {
        requireInspection("utterance_id" in payload.data, `Experience ${label} has invalid speech data.`);
        const utterance = data.eventsById.get(payload.data.utterance_id);
        requireInspection(
          utterance?.type === "utterance_spoken" && utterance.actor_id === payload.data.speaker_id &&
          utterance.target_id === actor && utterance.tick === tick && payload.data.addressee_id === actor &&
          payload.data.heard_at_tick === tick && utterance.payload.text === payload.data.text,
          `Experience ${label} does not match the recorded utterance.`,
        );
      }
    }
  }
}
