import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { decisionAt, reported } from "../src/p3/cognitionView.ts";
import { canonicalJson } from "../src/p3/encoding.ts";
import { createInspectionLoader, SHARD_LIMIT } from "../src/p3/inspection.ts";
import { validator } from "./lib/env.mjs";

const generated = new URL("../src/p3/generated/", import.meta.url);
const fixtureDir = new URL("../../backend/tests/fixtures/p3/evaluation/", import.meta.url);
const names = ["index", "trace", "registration", "decision", "sample"];
const load = createInspectionLoader(Object.fromEntries(
  names.map((name) => [name, JSON.parse(readFileSync(new URL(`${name}.schema.json`, generated)))]),
));
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const read = (path) => readFileSync(new URL(path, fixtureDir));
const fixture = async (id) => {
  const manifest = JSON.parse(read(`${id}-manifest.json`));
  const replay = read(manifest.replay);
  assert.equal(hash(replay), manifest.files[manifest.replay]);
  const parsed = validator.validateText(replay.toString("utf8"));
  assert.equal(parsed.ok, true, parsed.error?.message);
  const files = new Map(manifest.inspection_files.map((path) => {
    const bytes = read(path);
    assert.equal(hash(bytes), manifest.files[path]);
    const name = path.split("/").at(-1);
    return [name, new File([bytes], name)];
  }));
  return {
    manifest, files,
    source: { bundle: parsed.bundle, bytes: await new Blob([replay]).arrayBuffer() },
  };
};
const normal = await fixture("ui");
const death = await fixture("ui-edge");
const fileSet = (source) => [...source.files.values()];
const json = async (files, name) => JSON.parse(await files.get(name).text());
const newMember = (name, value) => {
  const text = canonicalJson(value);
  return { file: new File([text], name), sha256: hash(text) };
};
const updateIndex = async (source, edit) => {
  const files = new Map(source.files);
  const index = await json(files, "index.json");
  await edit(index, files);
  files.set("index.json", newMember("index.json", index).file);
  return [...files.values()];
};
const updateShard = (source, kind, refAt, edit) => updateIndex(source, async (index, files) => {
  const hit = index[kind].find(refAt);
  const name = hit.shard.file;
  const shard = await json(files, name);
  edit(shard);
  const { file, sha256 } = newMember(name, shard);
  files.set(name, file);
  hit.shard.sha256 = sha256;
});

test("the source-backed inspection presents exact cognition and decision boundaries", async () => {
  const verified = await load(fileSet(normal), normal.source);
  assert.equal(verified.indexSha256, normal.manifest.index_sha256);
  assert.equal(verified.index.decisions.length, 9);
  assert.equal(verified.index.samples.length, 15);
  const ella = verified.decisionRefsByActor.get("ella");
  const ryan = verified.decisionRefsByActor.get("ryan");
  assert.equal(decisionAt(ryan, 1), undefined);
  assert.equal(decisionAt(ryan, 2), undefined);
  const initial = await verified.readSample(verified.sample("ella", 0));
  assert.equal(initial.latest_perception_tick, -1);
  assert.equal(initial.latest_decision_id, null);
  assert.deepEqual(initial.identity.values, ["Observe carefully."]);
  const sample = await verified.readSample(verified.sample("ella", 1));
  assert.equal(sample.latest_perception_tick, 0);
  assert.equal(sample.latest_decision_id, decisionAt(ella, 0).decision_id);
  assert.equal(sample.goals.current.status, "intended");
  const next = await verified.readDecision(decisionAt(ella, 1));
  const goal = next.context.request.context.goals.current;
  assert.equal(goal.status, "observed_complete");
  assert.equal(goal.evidence.delivery_id, `${verified.index.run_id}:perception:0000000001:ella`);
  assert.equal(goal.evidence.owned_intent.decision_id, sample.latest_decision_id);
  assert.equal(next.record.accepted_delta.goal_change.operation, "revise");
  const later = await verified.readDecision(decisionAt(ella, 2));
  assert.equal(later.record.accepted_delta.goal_change.operation, "abandon");
  assert.equal(next.context.assembly.manifest.retrieval_profile, "recent-relevant-v0");
  assert.equal(next.context.assembly.manifest.projection_profile, "p3-context-v0");
  const recent = await verified.readSample(verified.sample("ella", 2));
  assert.equal(recent.recent_experience.length, 8);
  const speech = recent.recent_experience.find((row) => row.kind === "heard_speech");
  assert.equal(speech.payload.data.text, "<img src=x onerror=alert('fixture')> & quoted speech");
  assert.equal(speech.source.delivery_id, goal.evidence.delivery_id);
  assert.equal(verified.eventsById.get(speech.payload.data.utterance_id).type, "utterance_spoken");
  const unknown = await Promise.all(verified.decisionRefsByActor.get("mia").map(verified.readDecision));
  const attempt = unknown.flatMap((shard) => shard.calls).find((call) => call.debit.usage_unknown);
  assert.ok(attempt);
  assert.equal(reported(attempt.result.token_input), "Unknown");
  assert.equal(reported(attempt.result.token_output), "20");
  assert.equal(reported(attempt.result.latency_ms, " ms"), "Unknown");
  assert.equal(attempt.debit.money_charged, 0);
});

test("death preserves an unchanged observation cursor and zero-call decisions", async () => {
  const verified = await load(fileSet(death), death.source);
  assert.equal(verified.index.decisions.length, 3);
  for (const actor of verified.index.actors.map(({ actor_id }) => actor_id)) {
    const [ref] = verified.decisionRefsByActor.get(actor);
    const decision = await verified.readDecision(ref);
    const sample = await verified.readSample(verified.sample(actor, 4));
    assert.equal(sample.latest_perception_tick, 0);
    assert.equal(sample.latest_decision_id, ref.decision_id);
    assert.equal(decision.record.policy_id, "rule-based-v0");
    assert.deepEqual(decision.dispatches, []);
    assert.deepEqual(decision.calls, []);
    assert.equal(decisionAt([ref], 4), undefined);
  }
  assert.ok(death.source.bundle.frames[4].residents.every((resident) => !resident.alive));
});

test("replay comparison hashes exact selected bytes even when parsed replays are equal", async () => {
  const changed = new Blob([normal.source.bytes, "\n"]);
  assert.deepEqual(JSON.parse(await changed.text()), normal.source.bundle);
  await assert.rejects(load(fileSet(normal), { ...normal.source, bytes: await changed.arrayBuffer() }), /exact replay file bytes/);
  await assert.rejects(load(fileSet(normal), death.source), /config.*differs/);
});

test("unknown top-level versions and extra schema fields refuse", async () => {
  const badIndex = await updateIndex(normal, (index) => { index.inspection_schema_version = "1.0"; });
  await assert.rejects(load(badIndex, normal.source), /unsupported inspection_schema_version/);
  const withExtra = await updateShard(normal, "samples", (ref) => ref.tick === 0, (sample) => { sample.extra = 1; });
  await assert.rejects(load(withExtra, normal.source), /failed schema validation/);
  const badDecision = await updateShard(normal, "decisions", (ref) => ref.tick === 0, (shard) => {
    shard.record.record_schema_version = "9.0";
  });
  await assert.rejects(load(badDecision, normal.source), /failed schema validation/);
  const badGoal = await updateShard(normal, "samples", (ref) => ref.tick === 1 && ref.actor_id === "ella", (sample) => {
    sample.goals.current.completion.kind = "malformed";
  });
  await assert.rejects(load(badGoal, normal.source), /failed schema validation/);
});

test("missing, duplicate, extra, oversized, and incorrectly named files refuse", async () => {
  const selected = fileSet(normal);
  const shard = selected.find((file) => file.name.startsWith("sample-"));
  await assert.rejects(load(selected.filter((file) => file !== shard), normal.source), /Missing inspection file sample-/);
  await assert.rejects(load([...selected, shard], normal.source), /Duplicate inspection file/);
  await assert.rejects(load([...selected, new File(["{}"], "unrelated.json")], normal.source), /Unexpected inspection file/);
  const oversized = new File([new Uint8Array(SHARD_LIMIT + 1)], shard.name);
  await assert.rejects(load(selected.map((file) => file === shard ? oversized : file), normal.source), /2 MiB/);
  const wrongName = await updateIndex(normal, (index) => { index.samples[0].shard.file = "../" + shard.name; });
  await assert.rejects(load(wrongName, normal.source), /Invalid literal/);
  const missingRef = await updateIndex(normal, (index) => { index.samples.pop(); });
  await assert.rejects(load(missingRef, normal.source), /invalid sample or decision count/);
});

test("refuses tampered shard bytes and rechecks the file before on-demand display", async () => {
  const sampleName = (await json(normal.files, "index.json")).samples[0].shard.file;
  const original = normal.files.get(sampleName);
  const bytes = await original.arrayBuffer();
  let current = bytes;
  const selected = fileSet(normal).map((file) => file === original ? {
    name: original.name, size: original.size, async arrayBuffer() { return current; },
  } : file);
  const verified = await load(selected, normal.source);
  current = bytes.slice(0);
  new Uint8Array(current)[0] ^= 1;
  await assert.rejects(verified.readSample(verified.sample("ella", 0)), /shard hash mismatch/);
  await assert.rejects(load(selected, normal.source), /shard hash mismatch/);
});

test("cross-file joins catch corruption even after updating the local shard hash", async () => {
  const ella = (ref) => ref.tick === 1 && ref.actor_id === "ella";
  const cases = [
    ["samples", (shard) => { shard.latest_perception_tick = 1; }, /pre-ingestion cursor/],
    ["samples", (shard) => { shard.recent_experience[0].source.run_id = "other"; }, /foreign, duplicate, or future source/],
    ["decisions", (shard) => { shard.context.request.context.perception.actor_id = "ryan"; }, /mismatched request, perception/],
    ["decisions", (shard) => { shard.calls[0].actor_id = "ryan"; }, /differs from its committed request/],
    ["decisions", (shard) => { shard.outcome_event_ids = []; }, /outcome IDs differ/],
    ["decisions", (shard) => { shard.record.state_before_sha256 = "a".repeat(64); }, /committed decisions-p3.jsonl prefix/],
    ["decisions", (shard) => { shard.context.assembly.manifest.retrieval_profile = "recent-only-fixture-v0"; }, /registered case/],
  ];
  for (const [kind, mutate, message] of cases) {
    await assert.rejects(load(await updateShard(normal, kind, ella, mutate), normal.source), message);
  }
});

test("trace and registration must join the replay even with recomputed file hashes", async () => {
  for (const [name, key, mutate, expected] of [
    ["trace.json", "trace_sha256", (trace) => { trace.run_id = "wrong"; }, /trace differs/],
    ["registration.json", "registration_sha256", (registration) => {
      registration.world_map_sha256 = "a".repeat(64);
    }, /registration world config or map differs/],
  ]) {
    const files = await updateIndex(normal, async (index, members) => {
      const value = await json(members, name);
      mutate(value);
      const { file, sha256 } = newMember(name, value);
      members.set(name, file);
      index[key] = sha256;
    });
    await assert.rejects(load(files, normal.source), expected);
  }
});
