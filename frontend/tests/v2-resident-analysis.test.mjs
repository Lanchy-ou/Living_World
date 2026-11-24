import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { gunzipSync } from "node:zlib";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { inspectionRouter, makeLoader } from "../src/features/v2-inspection/import.ts";

const schema = name => JSON.parse(readFileSync(new URL(
  "../src/features/v2-inspection/generated/" + name + ".schema.json", import.meta.url)));

test("EV-02 ordinary import opens the Python-exported resident evidence and section costs", async () => {
  const fixture = JSON.parse(gunzipSync(readFileSync(new URL(
    "../../backend/tests/v2/resident_analysis/short-inspection.json.gz", import.meta.url))));
  const files = Object.entries(fixture.files).map(([name, text]) => new File([text], name));
  let state;
  const router = inspectionRouter({ reset() {}, select() { assert.fail("unexpected v1 route"); } },
    makeLoader(schema("index"), schema("shard")), next => { state = next; });
  await router.select(files, { bundle: JSON.parse(fixture.replay), bytes: await new Blob([fixture.replay]).arrayBuffer() });
  assert.equal(state.status, "ready", state.message);
  const inspection = state.value;
  const server = await createServer({ configFile: false, server: { middlewareMode: true, watch: null },
    appType: "custom", esbuild: { jsx: "automatic" } });
  try {
    const { InspectionDetail } = await server.ssrLoadModule("/src/features/v2-inspection/Viewer.tsx");
    async function display(ref) {
      const value = await inspection.read(ref);
      const html = renderToStaticMarkup(createElement(InspectionDetail, {
        value, source: ref, inspection, follow() {}, seek() {},
      }));
      return { value, html };
    }
    const metrics = await display(inspection.index.metrics);
    const analysis = metrics.value.resident_analysis;
    const use = analysis.uses[0];
    const resident = analysis.residents.find(r => r.resident_id === use.resident_id);
    assert.ok(metrics.html.includes("Prior-day dispatches · " + resident.prior_day_uses));
    assert.ok(metrics.html.includes("Self-found skills · " + resident.self_found_skills));
    assert.ok(metrics.html.includes("Store v" + use.before_version + " → v" + use.after_version));
    for (const source of use.links) {
      assert.ok(metrics.html.includes(source.label));
      const refs = inspection.index[source.family];
      const target = refs.map(r => r.shard ?? r).find(r => r.id === source.id);
      assert.equal((await inspection.read(target)).family, source.family);
    }
    const cost = await display(inspection.index.cost);
    const row = cost.value.contexts.find(c => c.call_id === use.call_id);
    assert.ok(cost.html.includes("Full / sent · " + row.full_tokens + " / " + row.sent_tokens));
    for (const section of row.sections) {
      assert.ok(cost.html.includes("<td>" + section.section + "</td><td>" + section.tokens +
        "</td><td>" + section.share + "</td><td>" + section.estimated_input_pico_cny + "</td>"));
    }
    assert.ok(cost.html.includes("Total paid · 0 pico-CNY"));
    assert.ok(cost.html.includes(cost.value.attempts[0].missing_usage_reason));
  } finally {
    await server.close();
  }
});
