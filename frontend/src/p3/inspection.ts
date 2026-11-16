import Ajv2020 from "ajv/dist/2020.js";
import type { ValidateFunction } from "ajv/dist/2020.js";
import { compareUtf8 } from "../replay/canon.ts";
import type { ReplayBundle, WorldEvent } from "../replay/types.ts";
import { canonicalJson, decodeInspection, padNumber, requireInspection, sha256Bytes, utf8 } from "./encoding.ts";
import type { DecisionInspection } from "./generated/decision.ts";
import type { InspectionDecisionRef, InspectionSampleRef, P3InspectionIndex, ShardRef } from "./generated/index.ts";
import type { TrialRegistration } from "./generated/registration.ts";
import type { ResidentInspection } from "./generated/sample.ts";
import type { DecisionTraceP3 } from "./generated/trace.ts";
import { checkDecision, checkSources, checkSample, checkRegistration } from "./joins.ts";

export const SHARD_LIMIT = 2_097_152;
const MAIN_FILES = ["index.json", "trace.json", "registration.json"];

export interface LocalInspectionFile {
  readonly name: string;
  readonly size: number;
  arrayBuffer(): Promise<ArrayBuffer>;
}

export interface ReplayFileSource {
  readonly bundle: ReplayBundle;
  readonly bytes: ArrayBuffer;
}

export interface VerifiedInspection {
  readonly index: P3InspectionIndex;
  readonly indexSha256: string;
  readonly registration: TrialRegistration;
  readonly decisionRefsByActor: ReadonlyMap<string, readonly InspectionDecisionRef[]>;
  readonly decisionRefsById: ReadonlyMap<string, InspectionDecisionRef>;
  readonly eventsById: ReadonlyMap<string, WorldEvent>;
  readonly eventsByIntent: ReadonlyMap<string, readonly WorldEvent[]>;
  sample(actorId: string, tick: number): InspectionSampleRef | undefined;
  readSample(ref: InspectionSampleRef): Promise<ResidentInspection>;
  readDecision(ref: InspectionDecisionRef): Promise<DecisionInspection>;
}

interface Models {
  index: P3InspectionIndex;
  trace: DecisionTraceP3;
  registration: TrialRegistration;
  decision: DecisionInspection;
  sample: ResidentInspection;
}

export type InspectionSchemas = { [Kind in keyof Models]: object };
type Checks = { [Kind in keyof Models]: ValidateFunction<Models[Kind]> };

const versions: { [Kind in keyof Models]: readonly [keyof Models[Kind] & string, string] } = {
  index: ["inspection_schema_version", "0.1"],
  trace: ["trace_schema_version", "0.2"],
  registration: ["registration_schema_version", "0.1"],
  decision: ["inspection_schema_version", "0.1"],
  sample: ["inspection_schema_version", "0.1"],
};

function parseMember<Kind extends keyof Models>(
  bytes: ArrayBuffer, name: string, kind: Kind, check: ValidateFunction<Models[Kind]>,
): Models[Kind] {
  let text: string;
  let value: unknown;
  try {
    text = decodeInspection(bytes);
    value = JSON.parse(text);
  } catch {
    throw new Error(`${name} is not valid UTF-8 JSON.`);
  }
  const [versionKey, expectedVersion] = versions[kind];
  if (value !== null && typeof value === "object" && versionKey in value) {
    const version = (value as Record<string, unknown>)[versionKey];
    requireInspection(version === expectedVersion, `${name} has an unsupported ${versionKey}.`);
  }
  if (!check(value)) {
    const issue = check.errors?.[0];
    throw new Error(`${name} failed schema validation at ${issue?.instancePath || "/"}: ${issue?.message ?? "invalid value"}.`);
  }
  requireInspection(canonicalJson(value) === text, `${name} must contain canonical JSON bytes.`);
  return value;
}

async function read(file: LocalInspectionFile, maxBytes = Infinity): Promise<ArrayBuffer> {
  requireInspection(file.size <= maxBytes, `${file.name} exceeds the 2 MiB inspection shard limit.`);
  let bytes: ArrayBuffer;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw new Error(`The browser could not read ${file.name}.`);
  }
  requireInspection(bytes.byteLength === file.size, `The size of ${file.name} changed while reading.`);
  return bytes;
}

function members(files: readonly LocalInspectionFile[]): Map<string, LocalInspectionFile> {
  const byName = new Map<string, LocalInspectionFile>();
  for (const file of files) {
    requireInspection(!byName.has(file.name), `Duplicate inspection file ${file.name}.`);
    byName.set(file.name, file);
  }
  for (const name of MAIN_FILES) requireInspection(byName.has(name), `Missing inspection file ${name}.`);
  return byName;
}

async function checkIndex(
  index: P3InspectionIndex, replay: ReplayBundle, files: Map<string, LocalInspectionFile>, signal?: AbortSignal,
) {
  requireInspection(
    index.run_id === replay.run_id && index.config_hash === replay.config_hash &&
    index.map_hash === replay.map_hash && index.final_tick === replay.frames.at(-1)?.tick,
    "Inspection run, config, map, or horizon differs from the current replay.",
  );
  const actors = index.actors.map((actor) => actor.actor_id);
  requireInspection(
    actors.length > 0 && actors.length === replay.residents.length && index.actors.every((actor, i) => {
      const resident = replay.residents[i];
      return actor.actor_id === actor.identity.actor_id && actor.actor_id === resident.id &&
        actor.identity.display_name === resident.display_name &&
        (i === 0 || compareUtf8(actors[i - 1], actor.actor_id) < 0);
    }),
    "Inspection identities or roster order differ from the replay.",
  );
  requireInspection(
    index.samples.length === actors.length * (index.final_tick + 1) &&
    index.decisions.length <= actors.length * index.final_tick,
    "Inspection index has an invalid sample or decision count.",
  );
  const actorHashes = new Map(await Promise.all(actors.map(async (actor) => [actor, await sha256Bytes(utf8(actor))] as const)));
  const expected = new Set(MAIN_FILES);
  function checkFile(ref: ShardRef, expectedName: string) {
    requireInspection(ref.file === expectedName, `Invalid literal inspection shard filename ${ref.file}.`);
    requireInspection(!expected.has(ref.file), `Duplicate inspection shard reference ${ref.file}.`);
    requireInspection(files.has(ref.file), `Missing inspection file ${ref.file}.`);
    expected.add(ref.file);
  }
  for (const [position, ref] of index.samples.entries()) {
    requireInspection(
      ref.actor_id === actors[position % actors.length] && ref.tick === Math.floor(position / actors.length),
      "Inspection samples must cover every actor and boundary in order.",
    );
    checkFile(ref.shard, `sample-${padNumber(ref.tick, 10)}-${actorHashes.get(ref.actor_id)}.json`);
  }
  const refsByActor = new Map(actors.map((actor) => [actor, [] as InspectionDecisionRef[]]));
  let previous: InspectionDecisionRef | undefined;
  for (const ref of index.decisions) {
    signal?.throwIfAborted();
    const refs = refsByActor.get(ref.actor_id);
    requireInspection(
      refs !== undefined && ref.tick < index.final_tick && ref.ordinal === refs.length &&
      (!previous || ref.tick > previous.tick ||
        (ref.tick === previous.tick && compareUtf8(ref.actor_id, previous.actor_id) > 0)),
      "Inspection decision refs have an invalid actor, tick, ordinal, or order.",
    );
    requireInspection(
      ref.decision_id === `${index.run_id}:d:${ref.actor_id}:${padNumber(ref.ordinal)}`,
      "Inspection decision ID differs from its run, actor, or ordinal.",
    );
    checkFile(ref.shard, `decision-${await sha256Bytes(utf8(ref.decision_id))}.json`);
    refs.push(ref);
    previous = ref;
  }
  for (const name of files.keys()) requireInspection(expected.has(name), `Unexpected inspection file ${name}.`);
  return refsByActor;
}

async function checkTrace(
  trace: DecisionTraceP3, index: P3InspectionIndex, decisions: Iterable<DecisionInspection>, replay: ReplayBundle,
  signal?: AbortSignal,
) {
  requireInspection(
    trace.run_id === index.run_id && trace.config_hash === index.config_hash &&
    trace.map_hash === index.map_hash && trace.final_tick === index.final_tick,
    "Inspection trace differs from the index run, config, map, or horizon.",
  );
  const rows = Array.from(decisions);
  const logs = {
    "contexts-p3.jsonl": () => rows.map((shard) => shard.context),
    "decisions-p3.jsonl": () => rows.map((shard) => shard.record),
    "events.jsonl": () => replay.events,
    "llm-calls.jsonl": () => rows.flatMap((shard) => shard.calls),
    "llm-dispatches.jsonl": () => rows.flatMap((shard) => shard.dispatches),
  };
  const names = Object.keys(logs) as (keyof typeof logs)[];
  requireInspection(
    trace.log_prefixes.length === names.length && trace.log_prefixes.every((prefix, i) => prefix.name === names[i]),
    "The trace has an invalid set of committed log prefixes.",
  );
  for (const [i, name] of names.entries()) {
    signal?.throwIfAborted();
    const prefix = trace.log_prefixes[i];
    const records = logs[name]();
    const committedBytes = await new Blob(records.map((row) => canonicalJson(row) + "\n")).arrayBuffer();
    requireInspection(
      prefix.records === records.length && prefix.sha256 === await sha256Bytes(committedBytes),
      `Inspection data differs from the trace's committed ${name} prefix.`,
    );
  }
}

/** Validate the complete selection before exposing data. Recheck each on-demand file read. */
export function createInspectionLoader(schemas: InspectionSchemas) {
  const ajv = new Ajv2020({ strict: true, ownProperties: true });
  // Pydantic's discriminator is an annotation. The generated oneOf branches enforce the tags.
  ajv.addKeyword("discriminator");
  const check: Checks = {
    index: ajv.compile<P3InspectionIndex>(schemas.index),
    trace: ajv.compile<DecisionTraceP3>(schemas.trace),
    registration: ajv.compile<TrialRegistration>(schemas.registration),
    decision: ajv.compile<DecisionInspection>(schemas.decision),
    sample: ajv.compile<ResidentInspection>(schemas.sample),
  };
  return async function load(
    files: readonly LocalInspectionFile[], replay: ReplayFileSource, signal?: AbortSignal,
  ): Promise<VerifiedInspection> {
    signal?.throwIfAborted();
    const byName = members(files);
    function readFile(name: string, maxBytes?: number) {
      const file = byName.get(name);
      requireInspection(file !== undefined, `Missing inspection file ${name}.`);
      return read(file, maxBytes);
    }
    async function readShard<Kind extends "decision" | "sample">(ref: ShardRef, kind: Kind): Promise<Models[Kind]> {
      const bytes = await readFile(ref.file, SHARD_LIMIT);
      requireInspection(await sha256Bytes(bytes) === ref.sha256, `Inspection shard hash mismatch for ${ref.file}.`);
      const validate: ValidateFunction<Models[Kind]> = check[kind];
      return parseMember(bytes, ref.file, kind, validate);
    }
    const rawIndex = await readFile("index.json");
    const index = parseMember(rawIndex, "index.json", "index", check.index);
    const decisionRefsByActor = await checkIndex(index, replay.bundle, byName, signal);
    requireInspection(await sha256Bytes(replay.bytes) === index.replay_sha256, "Inspection does not match the exact replay file bytes.");
    const rawTrace = await readFile("trace.json");
    requireInspection(await sha256Bytes(rawTrace) === index.trace_sha256, "Inspection trace hash mismatch.");
    const trace = parseMember(rawTrace, "trace.json", "trace", check.trace);
    const rawRegistration = await readFile("registration.json");
    const registration = parseMember(rawRegistration, "registration.json", "registration", check.registration);
    requireInspection(await sha256Bytes(rawRegistration) === index.registration_sha256, "Inspection registration hash mismatch.");

    const eventsById = new Map(replay.bundle.events.map((event) => [event.event_id, event]));
    const eventsByIntent = new Map<string, WorldEvent[]>();
    for (const event of replay.bundle.events) {
      if (event.intent_id === null) continue;
      const entries = eventsByIntent.get(event.intent_id) ?? [];
      entries.push(event);
      eventsByIntent.set(event.intent_id, entries);
    }
    const identities = new Map(index.actors.map((actor) => [actor.actor_id, actor.identity]));
    const decisions = new Map<string, DecisionInspection>();
    const decisionsByActorTick = new Map<string, Map<number, DecisionInspection>>();
    for (const actor of identities.keys()) decisionsByActorTick.set(actor, new Map());
    for (const ref of index.decisions) {
      signal?.throwIfAborted();
      const shard = await readShard(ref.shard, "decision");
      const identity = identities.get(ref.actor_id)!;
      requireInspection(replay.bundle.frames[ref.tick].residents.some((r) => r.id === ref.actor_id && r.alive),
        `Decision ${ref.decision_id} has no living actor at its boundary.`);
      await checkDecision(index.run_id, ref, shard, identity, eventsByIntent);
      decisions.set(ref.decision_id, shard);
      decisionsByActorTick.get(ref.actor_id)!.set(ref.tick, shard);
    }
    await checkRegistration(registration, index, decisions.values());
    await checkTrace(trace, index, decisions.values(), replay.bundle, signal);
    const sourceData = { runId: index.run_id, decisions, decisionsByActorTick, eventsById, eventsByIntent };
    for (const { context } of decisions.values()) {
      const { actor_id: actor, tick } = context.request;
      checkSources(sourceData, actor, tick, context.request.context.goals, context.request.context.recalled_experience);
    }

    const actorPositions = new Map(index.actors.map((actor, i) => [actor.actor_id, i]));
    const frameResidents = new Map(replay.bundle.residents.map((resident, i) => [resident.id, i]));
    const latestDecision = new Map<string, string>();
    const latestObservation = new Map<string, number>();
    for (const ref of index.samples) {
      signal?.throwIfAborted();
      const { actor_id: actor, tick } = ref;
      const preceding = decisionsByActorTick.get(actor)?.get(tick - 1);
      if (tick > 0) {
        const earlierFrame = replay.bundle.frames[tick - 1];
        if (earlierFrame.residents[frameResidents.get(actor)!].alive) latestObservation.set(actor, tick - 1);
        if (preceding) latestDecision.set(actor, preceding.record.decision_id);
      }
      const shard = await readShard(ref.shard, "sample");
      checkSample(ref, shard, identities.get(actor)!, latestObservation.get(actor) ?? -1, latestDecision.get(actor) ?? null);
      requireInspection(
        preceding === undefined || shard.state_sha256 === preceding.record.state_after_sha256,
        `Sample ${actor} at tick ${tick} does not hash to its preceding decision state.`,
      );
      checkSources(sourceData, actor, shard.latest_perception_tick, shard.goals, shard.recent_experience);
    }
    return {
      index, indexSha256: await sha256Bytes(rawIndex), registration, decisionRefsByActor, eventsById,
      decisionRefsById: new Map(index.decisions.map((ref) => [ref.decision_id, ref])),
      eventsByIntent,
      sample(actor, tick) {
        const position = actorPositions.get(actor);
        return position === undefined || !Number.isInteger(tick) || tick < 0 || tick > index.final_tick
          ? undefined : index.samples[tick * actorPositions.size + position];
      },
      readSample: (ref) => readShard(ref.shard, "sample"),
      readDecision: (ref) => readShard(ref.shard, "decision"),
    };
  };
}
