import assert from "node:assert/strict";
import { test } from "node:test";
import { eventPage } from "../src/panels/eventPagination.ts";
import { filterEvents } from "../src/panels/eventView.ts";
import { ReplayStore } from "../src/replay/store.ts";
import {
  BundleBuilder,
  RESIDENTS,
  Scene,
  TREES,
  generateLongBundle,
  residentFrame,
} from "./lib/builder.mjs";
import { validator } from "./lib/env.mjs";

function validate(replay) {
  const result = validator.validateText(JSON.stringify(replay));
  assert.ok(result.ok, result.ok ? "" : result.error.message);
  return result.bundle;
}

function crowdedTick() {
  const builder = new BundleBuilder({
    runId: "crowded_tick",
    worldId: "generated",
    residents: RESIDENTS,
  });
  for (let i = 0; i < 160; i += 2) {
    builder.event(0, "action_failed", { action_type: "gather", failure_code: "RESOURCE_TAKEN" }, { actor: "ella" });
    builder.event(0, "action_interrupted", { action_type: "gather", reason: "URGENT_NEED" }, { actor: "ella" });
  }
  for (let i = 0; i < 40; i++) {
    builder.event(0, "action_succeeded", { action_type: "wait", result_code: "OK" }, {
      actor: i < 20 ? "ella" : "mia",
    });
  }
  const scene = new Scene(
    [residentFrame("ella", 2, 2), residentFrame("mia", 3, 3), residentFrame("ryan", 4, 3)],
    TREES,
  );
  builder.frame(0, scene.snapshot());
  return validate(builder.build());
}

test("201 validated tick-zero events are reachable in order across two pages", () => {
  const bundle = crowdedTick();
  assert.equal(bundle.frames.length, 1);
  assert.equal(bundle.frames[0].event_range.count, 201);
  const first = eventPage(bundle.events, 0);
  const last = eventPage(bundle.events, 0, first.pageIndex + 1);
  assert.equal(first.pageIndex, 0);
  assert.equal(last.pageIndex, 1);
  assert.equal(first.pageCount, 2);
  assert.equal(first.rows.length, 150);
  assert.equal(last.start, 150);
  assert.equal(last.rows.length, 51);
  assert.deepEqual([...first.rows, ...last.rows], bundle.events);
  assert.deepEqual(eventPage(bundle.events, 0, -1), first);
  assert.deepEqual(eventPage(bundle.events, 0, last.pageIndex + 1), last);
  assert.deepEqual(eventPage(bundle.events, 0, last.pageIndex - 1), first);
});

test("resident and failure filters preserve order and limit the available pages", () => {
  const bundle = crowdedTick();
  const ella = filterEvents(bundle, { residentId: "ella", failuresOnly: true });
  const first = eventPage(ella, 0);
  const last = eventPage(ella, 0, 1);
  assert.equal(ella.length, 160);
  assert.equal(first.pageCount, 2);
  assert.equal(last.rows.length, 10);
  assert.deepEqual([...first.rows, ...last.rows], bundle.events.slice(1, 161));

  const mia = filterEvents(bundle, { residentId: "mia", failuresOnly: false });
  const only = eventPage(mia, 0, last.pageIndex);
  assert.equal(only.pageCount, 1);
  assert.equal(only.pageIndex, 0);
  assert.deepEqual(only.rows, bundle.events.slice(-20));

  const noMatches = filterEvents(bundle, { residentId: "mia", failuresOnly: true });
  assert.deepEqual(eventPage(noMatches, 0, last.pageIndex), {
    pageCount: 0, pageIndex: 0, start: 0, rows: [],
  });
});

test("selecting an event on a later page seeks to its tick and keeps its selection", () => {
  const bundle = validate(generateLongBundle(200));
  const store = new ReplayStore();
  store.load(bundle);
  const first = eventPage(bundle.events, store.getState().currentTick);
  const next = eventPage(bundle.events, store.getState().currentTick, first.pageIndex + 1);
  const picked = next.rows.at(-1);
  assert.equal(picked.tick, 200);

  store.selectEvent(picked);
  const { currentTick, selectedEventId } = store.getState();
  assert.equal(currentTick, 200);
  assert.equal(selectedEventId, picked.event_id);
  assert.equal(eventPage(bundle.events, currentTick).pageIndex, next.pageIndex);
  assert.equal(eventPage(bundle.events, 0).pageIndex, first.pageIndex);
  assert.equal(eventPage(bundle.events, 201).pageIndex, next.pageIndex);
});
