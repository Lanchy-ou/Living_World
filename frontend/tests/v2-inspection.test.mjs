import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { inspectionRouter, makeLoader } from "../src/features/v2-inspection/import.ts";
import { canonicalJson } from "../src/p3/encoding.ts";

const schema = name => JSON.parse(readFileSync(new URL(
  "../src/features/v2-inspection/generated/" + name + ".schema.json", import.meta.url)));
const load = makeLoader(schema("index"), schema("shard"));
const hash = raw => createHash("sha256").update(raw).digest("hex");

function fixture() {
  const replay = readFileSync(new URL("../../backend/tests/fixtures/replay/valid.json", import.meta.url));
  const bundle = JSON.parse(replay);
  const files = [];
  function shard(family, id, value) {
    const body = canonicalJson({ family, ...value });
    const name = hash(canonicalJson([family, id])) + ".1.json";
    const file = new File([body], name);
    files.push(file);
    return { family, id, sha256: hash(body), parts: [{name, sha256: hash(body), size: file.size}] };
  }
  const actor = bundle.residents[0].id;
  function belief(n, gist, told) {
    const content = {id: "m:" + actor + ":" + n, owner_id: actor, kind: "belief", created_tick: 0, updated_tick: 0,
      about_tick: null, sources: told ? [{kind:"told",speaker_id:"mia",utterance_id:"u1"}] : [{kind:"observed",entry_id:"e1"}],
      confidence: 3, supersedes: null, superseded_by: null, needs_review: false, gist, text: null, speech_derived: told,
      content: {subject:{kind:"place",ref:"1,1"},topics:[],stance:"stable"}};
    return {ref:{id:content.id,store_version:1,content_hash:hash(canonicalJson(content))},
      record:{...content,use_count:0,last_used_tick:null}};
  }
  const records = [belief(1,"Saw the spring",false),belief(2,"Heard about the spring",true)];
  const revisions = shard("revisions", actor + ":1", {resident_id:actor,store_version:1,records});
  const flag = {flagged:records[0].ref,overlaps:[records[1].ref],shared_keys:["place:1,1"],store_version:1,change_set_call_id:"c"};
  const store = shard("stores","p:1",{resident_id:actor,period_id:"p",store_version:1,records:records.map(r=>r.record),
    index_lines:["resident index"],relabel_flags:[flag]});
  const flagged = {...records[0].ref,content_hash:"0".repeat(64)};
  const missing = shard("stores", actor + ":end", { resident_id: actor, period_id: "p",
    store_version: 1, records: [], index_lines: [], relabel_flags: [
      {flagged, overlaps: [flagged], shared_keys: ["place:1,1"], store_version: 1, change_set_call_id: "c"}] });
  const rows = [17, 42, null].map((value, i) => ({instance_id: "id-" + i, metric: "<script>example</script>",
    trace: ["trace-" + i], value, reason: value === null ? "missing event" : null}));
  const index = {inspection_schema_version: "ia/0.1", run_id: bundle.run_id, final_tick: bundle.frames.at(-1).tick,
    replay_sha256: hash(replay), manifest_sha256: "0".repeat(64), arm: "on", pack_ids: [],
    residents: bundle.residents.map(r => ({resident_id: r.id, profile_id: "fixture"})),
    decisions: [], calls: [], stores: [store, missing].map(shard => ({resident_id: actor, period_id: "p", boundary_tick: 1, store_version: 1, shard})),
    consolidations: [], revisions: [revisions], deliveries: [], evidence_writes: [], metrics: shard("metrics", "metrics", {
      instances: rows, content_checks: [], checked_parts: [],
      resident_analysis: {packs: [], residents: [], learning: [], skills: [], uses: [], periods: [], consolidations: []},
    }),
    time_use: shard("time_use", "time_use", {intervals: []}), cost: shard("cost", "cost", {attempts: []}),
    attempts: shard("attempts", "attempts", {events: [], submissions: []})};
  return {index, files: [...files, new File([canonicalJson(index)], "index.json")], bundle, replay};
}

test("EV-14 ordinary import routes v1 and v2 and displays verified shard values", async () => {
  const {files, index, bundle, replay} = fixture();
  const source = {bundle, bytes: await new Blob([replay]).arrayBuffer()};
  const states = [];
  let legacy = 0;
  const router = inspectionRouter({reset() {}, async select() { legacy++; }}, load, s => states.push(s));
  await router.select([new File(['{"inspection_schema_version":"0.1"}'], "index.json")], source);
  assert.equal(legacy, 1);
  await router.select(files, source);
  assert.equal(states.at(-1).status, "ready", states.at(-1).message);
  const verified = states.at(-1).value;
  const metrics = await verified.read(index.metrics);
  const server = await createServer({configFile: false, server: { middlewareMode: true, watch: null },
    appType: "custom", esbuild: {jsx: "automatic"}});
  try {
    const { MetricRows, InspectionDetail } = await server.ssrLoadModule("/src/features/v2-inspection/Viewer.tsx");
    const html = renderToStaticMarkup(createElement(MetricRows, {rows: metrics.instances}));
    assert.match(html, /<td>17<\/td>/);
    assert.match(html, /<td>42<\/td>/);
    assert.match(html, /missing event/);
    assert.match(html, /&lt;script&gt;/);
    const source = verified.index.stores[0].shard;
    const value = await verified.read(source);
    const actions = [];
    const element = InspectionDetail({value, inspection: verified, source, seek: (...args) => actions.push(args),
      follow: ref => actions.push(ref.id)});
    const storeHtml = renderToStaticMarkup(element);
    assert.match(storeHtml,/Saw the spring/);
    assert.match(storeHtml,/Heard about the spring/);
    assert.match(storeHtml,/Overlapping told records/);
    function clickLinks(child) {
      if (Array.isArray(child)) child.forEach(clickLinks);
      else if (child?.type === "button") child.props.onClick();
      else if (child?.props) clickLinks(child.props.children);
    }
    clickLinks(element);
    assert.deepEqual(actions, [[value.resident_id,1], value.resident_id + ":1"]);
  } finally { await server.close(); }
  await assert.rejects(verified.read(index.stores[1].shard), /absent memory revision/);
  await router.select(files, {...source, bytes: new ArrayBuffer(0)});
  assert.equal(states.at(-1).status, "error");
});
