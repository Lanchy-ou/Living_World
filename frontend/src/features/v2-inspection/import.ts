import Ajv2020 from "ajv/dist/2020.js";
import type { LocalInspectionFile, ReplayFileSource } from "../../p3/inspection.ts";
import { canonicalJson, decodeInspection, requireInspection, sha256Bytes, utf8 } from "../../p3/encoding.ts";
import type { InspectionIndex, ShardRef } from "./generated/index.ts";
import type { InspectionShard } from "./generated/shard.ts";

const indexLimit = 32 * 1024 * 1024;

async function indexFile(files: readonly LocalInspectionFile[]) {
  const indexes = files.filter(f => f.name === "index.json");
  requireInspection(indexes.length === 1 && indexes[0].size <= indexLimit, "Expected one bounded index.json.");
  const text = decodeInspection(await indexes[0].arrayBuffer());
  const index: unknown = JSON.parse(text);
  if (typeof index === "object" && index !== null && "inspection_schema_version" in index &&
      index.inspection_schema_version === "ia/0.1") {
    requireInspection(canonicalJson(index) === text, "Expected a canonical inspection index.");
  }
  return index;
}

export interface Inspection {
  index: InspectionIndex;
  read(ref: ShardRef): Promise<InspectionShard>;
}

export type ImportState = { status: "idle" | "loading" } | { status: "ready"; value: Inspection } |
  { status: "error"; message: string };

export function inspectionRouter(
  v1: { reset(): void; select(files: readonly LocalInspectionFile[], replay: ReplayFileSource): Promise<void> },
  load: (files: readonly LocalInspectionFile[], replay: ReplayFileSource, index: unknown) => Promise<Inspection>,
  publish: (state: ImportState) => void,
) {
  let generation = 0;
  function reset() {
    generation++;
    v1.reset();
    publish({ status: "idle" });
  }
  return { reset, async select(files: readonly LocalInspectionFile[], replay: ReplayFileSource) {
    reset();
    const active = generation;
    publish({ status: "loading" });
    try {
      const index = await indexFile(files);
      if (active !== generation) return;
      if (typeof index === "object" && index !== null && "inspection_schema_version" in index &&
          index.inspection_schema_version === "ia/0.1") {
        const value = await load(files, replay, index);
        if (active === generation) publish({ status: "ready", value });
      } else {
        publish({ status: "idle" });
        await v1.select(files, replay);
      }
    } catch (error) {
      if (active === generation) publish({ status: "error", message: String(error) });
    }
  } };
}

export function makeLoader(indexSchema: object, shardSchema: object) {
  const ajv = new Ajv2020({ strict: false, validateFormats: false, inlineRefs: false });
  const checkIndex = ajv.compile<InspectionIndex>(indexSchema);
  const checkShard = ajv.compile<InspectionShard>(shardSchema);
  return async (files: readonly LocalInspectionFile[], replay: ReplayFileSource, index: unknown): Promise<Inspection> => {
    requireInspection(checkIndex(index), "Invalid v2 inspection index.");
    const revisionRefs = index.revisions;
    const callRefs = index.calls;
    const decisionRefs = index.decisions;
    const actors = new Set(replay.bundle.residents.map(r => r.id));
    for (const r of [...index.decisions, ...index.calls, ...index.consolidations, ...index.stores]) {
      requireInspection(actors.has(r.resident_id) && ("tick" in r ? r.tick : r.boundary_tick) <= index.final_tick,
        "Inspection reference is outside this replay.");
    }
    requireInspection(index.replay_sha256 === await sha256Bytes(replay.bytes) && index.run_id === replay.bundle.run_id &&
      index.final_tick === replay.bundle.frames.at(-1)?.tick &&
      canonicalJson(index.residents.map(r => r.resident_id).sort()) === canonicalJson(replay.bundle.residents.map(r => r.id).sort()),
      "Inspection belongs to a different replay.");
    const members = new Map(files.map(f => [f.name, f]));
    requireInspection(members.size === files.length, "Duplicate inspection file.");
    const names = new Set(["index.json"]);
    for (const family of ["decisions", "consolidations", "stores", "calls", "deliveries", "revisions", "evidence_writes",
      "metrics", "cost", "time_use", "attempts"] as const) {
      const entries = index[family];
      for (const wrapper of Array.isArray(entries) ? entries : [entries]) {
        const ref = "shard" in wrapper ? wrapper.shard : wrapper;
        requireInspection(ref.family === family, "Wrong shard family in index.");
        const prefix = await sha256Bytes(utf8(canonicalJson([family, ref.id])));
        for (const [position, part] of ref.parts.entries()) {
          requireInspection(part.name === prefix + "." + (position + 1) + ".json" &&
            !names.has(part.name) && members.get(part.name)?.size === part.size, "Missing or invalid numbered part.");
          names.add(part.name);
        }
      }
    }
    requireInspection(names.size === members.size, "Unexpected inspection file.");

    async function read(ref: ShardRef): Promise<InspectionShard> {
      const chunks: Uint8Array<ArrayBuffer>[] = [];
      for (const part of ref.parts) {
        const file = members.get(part.name);
        requireInspection(file, "Missing shard.");
        const bytes = await file.arrayBuffer();
        requireInspection(bytes.byteLength === part.size && part.sha256 === await sha256Bytes(bytes), "Shard hash mismatch.");
        if (ref.parts.length === 1) chunks.push(new Uint8Array(bytes));
        else {
          const value: unknown = JSON.parse(decodeInspection(bytes));
          requireInspection(typeof value === "string", "Invalid split part.");
          chunks.push(Uint8Array.from(atob(value), char => char.charCodeAt(0)));
        }
      }
      const body = await new Blob(chunks).arrayBuffer();
      requireInspection(await sha256Bytes(body) === ref.sha256, "Assembled shard hash mismatch.");
      const value: unknown = JSON.parse(decodeInspection(body));
      requireInspection(checkShard(value) && value.family === ref.family, "Invalid inspection shard.");
      if (value.family === "decisions" || value.family === "calls") {
        const row = value.family === "decisions" ? value.record : value.call;
        const parent = value.family === "decisions" ? decisionRefs.find(r => r.shard.id === ref.id) :
          callRefs.find(r => r.shard.id === ref.id);
        requireInspection(parent && parent.tick === row.tick && parent.resident_id === row.resident_id &&
          ("call_id" in row ? row.call_id : row.turn_id) === ref.id, "Wrong recorded call or decision.");
      }
      if (value.family === "revisions") {
        for (const { ref: revision, record } of value.records) {
          const { use_count, last_used_tick, ...content } = record;
          void use_count; void last_used_tick;
          requireInspection(revision.id === record.id && record.owner_id === value.resident_id &&
            revision.store_version === value.store_version && revision.content_hash === await sha256Bytes(utf8(canonicalJson(content))),
            "Invalid memory revision.");
        }
      }
      if (value.family === "stores" || value.family === "consolidations") {
        const row = value.family === "stores" ? value : value.record;
        for (const flag of row.relabel_flags) {
          const source = revisionRefs.find(s => s.id === row.resident_id + ":" + flag.store_version);
          requireInspection(source, "Relabel flag names a missing store version.");
          const revisions = await read(source);
          requireInspection(revisions.family === "revisions" && [flag.flagged, ...flag.overlaps].every(r =>
            revisions.records.some(v => r.id === v.ref.id && r.store_version === v.ref.store_version &&
              r.content_hash === v.ref.content_hash)), "Relabel flag names an absent memory revision.");
        }
      }
      return value;
    }
    return { index, read };
  };
}
