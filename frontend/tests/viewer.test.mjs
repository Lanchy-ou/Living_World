// Viewer logic: store, camera, drawing geometry and panel view-models. All pure; no DOM.
import assert from "node:assert/strict";
import { test } from "node:test";
import { clockAt, isNight } from "../src/replay/clock.ts";
import { ReplayStore, eventsOfFrame, frameAt, lastTick } from "../src/replay/store.ts";
import {
  baseTileSize,
  dragPan,
  layoutFor,
  panNeeded,
  panToCentre,
  screenToTile,
  tileToScreen,
} from "../src/render/camera.ts";
import { computeSprites, drawFrame } from "../src/render/drawFrame.ts";
import { residentStyle } from "../src/render/theme.ts";
import { eventInvolvesResident, failureCode, filterEvents, isFailureEvent, summarize } from "../src/panels/eventView.ts";
import { residentView } from "../src/panels/residentView.ts";
import { resourcesView } from "../src/panels/resourcesView.ts";
import { generateLongBundle } from "./lib/builder.mjs";
import { loadHandmade } from "./lib/env.mjs";

const VIEW = { width: 600, height: 400 };

test("FE-T01: tick 0 positions of the move-and-gather fixture are those of frame 0", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const store = new ReplayStore();
  store.load(bundle, "move-and-gather.json");
  const s = store.getState();
  assert.equal(s.currentTick, 0);
  assert.equal(s.playing, false);
  const at0 = Object.fromEntries(frameAt(bundle, 0).residents.map((r) => [r.id, [r.position.x, r.position.y]]));
  assert.deepEqual(at0, { ella: [1, 3], mia: [1, 4], ryan: [2, 4] });
  assert.deepEqual(residentView(bundle, 0, "ella").position, { x: 1, y: 3 });
});

test("FE-T01: all valid hand-made fixtures load into the store at tick 0, paused", () => {
  for (const name of ["move-and-gather", "contention", "death-drops-pickup", "edge-frame0-only", "edge-all-dead"]) {
    const store = new ReplayStore();
    store.load(loadHandmade(`${name}.json`), name);
    assert.equal(store.getState().currentTick, 0, name);
    assert.equal(store.getState().playing, false, name);
  }
});

test("FE-T02: step stops at tick 0 and at the last tick; nothing is simulated", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const store = new ReplayStore();
  store.load(bundle);
  store.step(-1);
  assert.equal(store.getState().currentTick, 0);
  for (let i = 0; i < 20; i++) store.step(1);
  assert.equal(store.getState().currentTick, lastTick(bundle));
  store.step(1);
  assert.equal(store.getState().currentTick, lastTick(bundle));
  store.seek(3);
  store.step(1);
  assert.equal(store.getState().currentTick, 4);
  store.seek(-5);
  assert.equal(store.getState().currentTick, 0);
  store.seek(999);
  assert.equal(store.getState().currentTick, lastTick(bundle));
  store.seek(Number.NaN);
  assert.equal(store.getState().currentTick, 0);
});

test("FE-T02: playback advances one recorded frame per beat and pauses at the end", () => {
  const bundle = loadHandmade("contention.json");
  const store = new ReplayStore();
  store.load(bundle);
  store.play();
  const seen = [];
  for (let i = 0; i < 10; i++) {
    store.tickPlayback();
    seen.push(store.getState().currentTick);
  }
  assert.deepEqual(seen.slice(0, 4), [1, 2, 3, 4]);
  assert.equal(store.getState().currentTick, lastTick(bundle));
  assert.equal(store.getState().playing, false);
  store.play(); // already at the end: stays paused
  assert.equal(store.getState().playing, false);
});

test("FE-T02: a bundle with only frame 0 stays at tick 0", () => {
  const bundle = loadHandmade("edge-frame0-only.json");
  const store = new ReplayStore();
  store.load(bundle);
  store.step(1);
  store.play();
  assert.equal(store.getState().currentTick, 0);
  assert.equal(store.getState().playing, false);
  assert.equal(bundle.frames.length, 1);
});

test("FE-T03: seek, then switch resident: panel equals that frame's data", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const store = new ReplayStore();
  store.load(bundle);
  store.seek(4);
  for (const id of ["ella", "mia", "ryan"]) {
    store.selectResident(id);
    const view = residentView(bundle, store.getState().currentTick, store.getState().selectedResidentId);
    const raw = frameAt(bundle, 4).residents.find((r) => r.id === id);
    assert.deepEqual(view.position, raw.position);
    assert.equal(view.fruitCount, raw.fruit_count);
    assert.equal(view.canteenServings, raw.canteen_servings);
    assert.deepEqual(
      Object.fromEntries(view.conditions.map((c) => [c.name, c.value])),
      { satiety: raw.satiety, hydration: raw.hydration, stamina: raw.stamina, health: raw.health },
    );
  }
  const ella = residentView(bundle, 4, "ella");
  assert.equal(ella.fruitCount, 1);
  assert.equal(ella.fruitDelta, 1);
  assert.deepEqual(ella.moved, { dx: 0, dy: 0 });
  assert.equal(ella.conditions[2].delta, -50); // stamina: the recorded gather cost in the fixture
});

test("FE-T03: delta from the previous tick, tick 0 has none, bars use condition_bounds", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const at0 = residentView(bundle, 0, "ella");
  assert.equal(at0.moved, null);
  assert.ok(at0.conditions.every((c) => c.delta === null));
  const at1 = residentView(bundle, 1, "ella");
  assert.deepEqual(at1.moved, { dx: 1, dy: -1 });
  const satiety = at1.conditions.find((c) => c.name === "satiety");
  assert.equal(satiety.fraction, satiety.value / (bundle.condition_bounds.max_value - bundle.condition_bounds.min_value));
  const custom = structuredClone(bundle);
  custom.condition_bounds.max_value = 20000;
  assert.equal(residentView(custom, 0, "ella").conditions[0].fraction, 6000 / 20000);
  const gather = residentView(bundle, 3, "ella").action;
  assert.deepEqual(gather, { intentId: "ella:p000001:i1", actionType: "gather", tickStarted: 2, remainingTicks: 1 });
});

test("FE-T04: shared tile, corpse and ground items are all drawn; coordinates unchanged", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const frame = structuredClone(frameAt(bundle, 3));
  frame.residents.find((r) => r.id === "ryan").position = { x: 8, y: 3 }; // share the death tile
  const layout = layoutFor(VIEW, bundle.map, { zoom: 1, panX: 0, panY: 0, follow: false });
  const sprites = computeSprites(bundle, frame, layout);
  const here = sprites.filter((s) => s.tileX === 8 && s.tileY === 3);
  assert.deepEqual(
    here.map((s) => s.kind).sort(),
    ["corpse", "ground_canteen", "ground_fruit", "resident"],
  );
  const centres = new Set(here.map((s) => `${s.cx},${s.cy}`));
  assert.equal(centres.size, 4, "offsets keep sprites apart");
  for (const s of here) {
    assert.deepEqual(screenToTile(layout, s.cx, s.cy), { x: 8, y: 3 });
  }
  assert.deepEqual(frame.corpses[0].position, { x: 8, y: 3 }); // data untouched
  assert.ok(!sprites.some((s) => s.kind === "resident" && s.id === "mia"), "dead resident is shown by its corpse");
});

test("FE-T04: residents get a stable colour and a letter by declared index", () => {
  assert.deepEqual(residentStyle(0), residentStyle(0));
  assert.notEqual(residentStyle(0).colour, residentStyle(1).colour);
  assert.notEqual(residentStyle(0).letter, residentStyle(1).letter);
  assert.equal(residentStyle(0).letter, "A");
});

test("FE-T05: failure filter returns exactly the failure events with their codes", () => {
  const bundle = loadHandmade("contention.json");
  const failures = filterEvents(bundle, { residentId: null, failuresOnly: true });
  assert.equal(failures.length, 1);
  assert.equal(failures[0].type, "action_failed");
  assert.equal(failureCode(failures[0]), "RESOURCE_TAKEN");
  assert.equal(failures[0].actor_id, "ryan");
  assert.ok(failures.every(isFailureEvent));
});

test("FE-T05: resident filter equals the expected event IDs and ignores text", () => {
  const bundle = loadHandmade("contention.json");
  const ryan = filterEvents(bundle, { residentId: "ryan", failuresOnly: false });
  const expected = bundle.events.filter((e) => e.actor_id === "ryan" || e.target_id === "ryan" || e.payload.resident_id === "ryan");
  assert.deepEqual(ryan.map((e) => e.event_id), expected.map((e) => e.event_id));
  const both = filterEvents(bundle, { residentId: "ryan", failuresOnly: true });
  assert.deepEqual(both.map((e) => e.event_id), [bundle.events.find((e) => e.type === "action_failed").event_id]);
  const order = ryan.map((e) => [e.tick, e.seq_in_tick]);
  assert.deepEqual(order, [...order].sort((a, b) => a[0] - b[0] || a[1] - b[1]));
});

test("FE-T05: resident reference fields, including recipient_id, are matched by field, not by text", () => {
  const base = { actor_id: null, target_id: null };
  const mk = (payload) => ({ ...base, type: "god_intervention_recorded", payload });
  assert.ok(eventInvolvesResident(mk({ recipient_id: "ella" }), "ella"));
  assert.ok(eventInvolvesResident({ ...base, type: "utterance_heard", payload: { listener_id: "ella" } }, "ella"));
  assert.ok(eventInvolvesResident({ ...base, type: "item_given", payload: { from_id: "ella", to_id: "mia" } }, "mia"));
  assert.ok(eventInvolvesResident({ ...base, type: "utterance_spoken", payload: { addressee_id: "mia", text: "" } }, "mia"));
  // the name appears only inside free text: not a match
  assert.ok(!eventInvolvesResident({ ...base, type: "utterance_spoken", payload: { addressee_id: "mia", text: "hello ella" } }, "ella"));
  assert.ok(!eventInvolvesResident({ ...base, type: "fruit_gathered", payload: { tree_id: "ella" } }, "ella"));
});

test("FE-T05: summaries restate payload fields and clicking an event seeks to its tick", () => {
  const bundle = loadHandmade("contention.json");
  const failed = bundle.events.find((e) => e.type === "action_failed");
  assert.equal(summarize(failed), "gather failed: RESOURCE_TAKEN");
  const store = new ReplayStore();
  store.load(bundle);
  store.selectEvent(failed);
  assert.equal(store.getState().currentTick, failed.tick);
  assert.equal(store.getState().selectedEventId, failed.event_id);
  for (const e of bundle.events) assert.ok(summarize(e).length > 0, e.type);
});

test("FE-T06: a 1,009-frame bundle loads and seeks to the last tick", () => {
  const bundle = generateLongBundle(1008);
  const store = new ReplayStore();
  store.load(bundle);
  store.seek(1008);
  assert.equal(store.getState().currentTick, 1008);
  assert.equal(frameAt(bundle, 1008).tick, 1008);
  store.step(1);
  assert.equal(store.getState().currentTick, 1008);
  assert.equal(eventsOfFrame(bundle, frameAt(bundle, 1008)).length, 1);
});

test("FE-T07: changing speed leaves frames and data unchanged", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const snapshot = structuredClone(bundle);
  const store = new ReplayStore();
  store.load(bundle);
  store.seek(3);
  for (const speed of [1, 2, 4, 8, 16]) {
    store.setSpeed(speed);
    assert.equal(store.getState().speed, speed);
    assert.equal(store.getState().currentTick, 3);
  }
  assert.deepEqual(bundle, snapshot);
});

test("FE-T10: fit, zoom and pan keep every entity at its recorded tile", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const frame = frameAt(bundle, 3);
  for (const zoom of [1, 2, 4]) {
    for (const pan of [[0, 0], [-9999, -9999], [50, 50], [-80, -30]]) {
      const layout = layoutFor(VIEW, bundle.map, { zoom, panX: pan[0], panY: pan[1], follow: false });
      for (const s of computeSprites(bundle, frame, layout)) {
        assert.deepEqual(screenToTile(layout, s.cx, s.cy), { x: s.tileX, y: s.tileY }, `${s.id} zoom ${zoom}`);
      }
      const { left, top } = tileToScreen(layout, 0, 0);
      assert.deepEqual(screenToTile(layout, left + 0.1, top + 0.1), { x: 0, y: 0 });
    }
  }
});

test("FE-T10: fit-to-view uses min(width/map.width, height/map.height) and zoom multiplies it", () => {
  const map = { width: 12, height: 8 };
  assert.equal(baseTileSize(VIEW, map), Math.min(600 / 12, 400 / 8));
  const l1 = layoutFor(VIEW, map, { zoom: 1, panX: 0, panY: 0, follow: false });
  const l2 = layoutFor(VIEW, map, { zoom: 2, panX: 0, panY: 0, follow: false });
  assert.equal(l2.tile, l1.tile * 2);
  assert.equal(panNeeded(VIEW, map, 1), false);
  assert.equal(panNeeded(VIEW, map, 4), true);
  // content smaller than the view is centred; the whole map is visible at fit
  assert.ok(l1.offsetX >= 0 && l1.offsetY >= 0);
  assert.ok(l1.offsetX + 12 * l1.tile <= VIEW.width + 1e-9);
});

test("FE-T10: drag-pan is clamped to the content bounds, never to entity positions", () => {
  const map = { width: 12, height: 8 };
  const cam = { zoom: 4, panX: 0, panY: 0, follow: false };
  const far = dragPan(VIEW, map, cam, -100000, -100000);
  const layout = layoutFor(VIEW, map, { ...cam, ...far });
  assert.ok(layout.offsetX + map.width * layout.tile >= VIEW.width - 1e-9);
  assert.ok(layout.offsetY + map.height * layout.tile >= VIEW.height - 1e-9);
  const back = dragPan(VIEW, map, { ...cam, ...far }, 100000, 100000);
  const l2 = layoutFor(VIEW, map, { ...cam, ...back });
  assert.ok(l2.offsetX <= 0 && l2.offsetY <= 0);
  // follow: the followed tile ends up as centred as the clamp allows
  const layoutNow = layoutFor(VIEW, map, cam);
  const [px, py] = panToCentre(VIEW, layoutNow.tile, 6, 4);
  const followed = layoutFor(VIEW, map, { ...cam, panX: px, panY: py });
  const at = tileToScreen(followed, 6, 4);
  assert.ok(Math.abs(at.left + followed.tile / 2 - VIEW.width / 2) < 1e-6);
});

test("clock: tick / Day d / HH:MM follow the replay-frontend 4.2 formulas", () => {
  const clock = { tick_minutes: 10, start_hour: 6, day_start_hour: 6, day_end_hour: 20 };
  assert.deepEqual(clockAt(0, clock), { day: 1, hh: 6, mm: 0, text: "Day 1 06:00" });
  assert.equal(clockAt(6, clock).text, "Day 1 07:00");
  assert.equal(clockAt(108, clock).text, "Day 1 00:00"); // wraps past midnight, still Day 1
  assert.equal(clockAt(144, clock).text, "Day 2 06:00"); // Day counts elapsed days
  assert.equal(isNight(0, clock), false);
  assert.equal(isNight(84, clock), true); // 20:00 itself is night
  assert.equal(isNight(83, clock), false);
  assert.equal(isNight(108, clock), true);
});

test("drawing reads only the current frame and a fake canvas; night shading follows the clock", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const calls = [];
  const ctx = new Proxy(
    {},
    {
      get: (_, name) => (...args) => calls.push([name, ...args]),
      set: (_, name, value) => (calls.push(["set", name, value]), true),
    },
  );
  const layout = layoutFor(VIEW, bundle.map, { zoom: 1, panX: 0, panY: 0, follow: false });
  const before = structuredClone(bundle);
  drawFrame(ctx, bundle, frameAt(bundle, 2), layout, VIEW, { selectedResidentId: "ella" });
  assert.deepEqual(bundle, before);
  const texts = calls.filter((c) => c[0] === "fillText").map((c) => c[1]);
  assert.ok(texts.includes("A") && texts.includes("B") && texts.includes("C"), "resident letters drawn");
  assert.ok(texts.includes("3"), "tree stock number drawn");
  const night = structuredClone(bundle);
  night.clock.start_hour = 22;
  const nightCalls = [];
  const nightCtx = new Proxy({}, { get: (_, n) => (...a) => nightCalls.push([n, ...a]), set: (_, n, v) => (nightCalls.push(["set", n, v]), true) });
  drawFrame(nightCtx, night, frameAt(night, 0), layout, VIEW, { selectedResidentId: null });
  assert.ok(nightCalls.some((c) => c[0] === "set" && c[1] === "fillStyle" && String(c[2]).startsWith("rgba(10")));
  assert.ok(!calls.some((c) => c[0] === "set" && c[1] === "fillStyle" && String(c[2]).startsWith("rgba(10")));
});

test("resources panel shows empty states and lists every object on a tile", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const start = resourcesView(frameAt(bundle, 0));
  assert.equal(start.empty.piles, true);
  assert.equal(start.empty.canteen, true);
  assert.equal(start.empty.corpses, true);
  assert.equal(start.trees.length, 3);
  const dead = resourcesView(frameAt(bundle, 3));
  const tile = dead.tiles.find((t) => t.x === 8 && t.y === 3);
  assert.equal(tile.objects.length, 3);
  assert.ok(tile.objects.some((o) => o.startsWith("corpse")));
  assert.ok(tile.objects.some((o) => o.startsWith("ground fruit")));
  assert.ok(tile.objects.some((o) => o.startsWith("ground canteen")));
  const after = resourcesView(frameAt(bundle, 7));
  assert.equal(after.empty.piles, true);
  assert.equal(after.empty.canteen, true);
  assert.equal(after.empty.corpses, false);
});

test("death and pick-up: the recorded frames show the corpse staying and items moving", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const ryan = residentView(bundle, 7, "ryan");
  assert.equal(ryan.fruitCount, 2);
  assert.equal(ryan.canteenServings, 3);
  const mia = residentView(bundle, 3, "mia");
  assert.equal(mia.alive, false);
  assert.equal(mia.fruitCount, 0);
  assert.equal(frameAt(bundle, 7).corpses.length, 1);
});

test("all residents dead: frames keep every declared resident", () => {
  const bundle = loadHandmade("edge-all-dead.json");
  const last = frameAt(bundle, lastTick(bundle));
  assert.equal(last.residents.length, 3);
  assert.ok(last.residents.every((r) => !r.alive));
  assert.equal(computeSprites(bundle, last, layoutFor(VIEW, bundle.map, { zoom: 1, panX: 0, panY: 0, follow: false })).filter((s) => s.kind === "corpse").length, 3);
});

test("load replaces the whole state: tick 0, paused, filters cleared", () => {
  const store = new ReplayStore();
  store.load(loadHandmade("contention.json"));
  store.seek(3);
  store.setFilters({ failuresOnly: true });
  store.setCamera({ zoom: 4 });
  store.load(loadHandmade("move-and-gather.json"));
  const s = store.getState();
  assert.equal(s.currentTick, 0);
  assert.equal(s.playing, false);
  assert.equal(s.filters.failuresOnly, false);
  assert.equal(s.camera.zoom, 1);
});
