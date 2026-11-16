import assert from "node:assert/strict";
import { test } from "node:test";
import { initialState, ReplayStore } from "../src/replay/store.ts";
import { poseAt } from "../src/render/motion.ts";
import { loadHandmade } from "./lib/env.mjs";

test("each initial state owns a separate camera and store updates leave prior snapshots intact", () => {
  const first = initialState();
  const second = initialState();
  assert.notEqual(first.camera, second.camera);
  assert.deepEqual(first.camera, second.camera);

  const store = new ReplayStore();
  const previous = store.getState();
  store.setCamera({ zoom: 2, panX: -15 });
  assert.equal(store.getState().camera.zoom, 2);
  assert.deepEqual(previous.camera, second.camera);
});

test("load owns a frozen replay snapshot without freezing the caller's bundle", () => {
  const input = loadHandmade("move-and-gather.json");
  const expected = structuredClone(input);
  const store = new ReplayStore();
  store.load(input);
  const initial = store.getState();
  const owned = initial.bundle;

  input.frames[1].residents[0].position.x = 4;
  input.map.rows[0] = "changed";
  input.events[2].payload.to.x = 5;
  input.events.pop();
  assert.deepEqual(owned, expected);

  assert.throws(() => { owned.frames[1].residents[0].position.x = 4; }, TypeError);
  assert.throws(() => { owned.events[2].payload.to.x = 5; }, TypeError);
  assert.throws(() => { initial.currentTick = 1; }, TypeError);
  assert.throws(() => { initial.camera.panX = 1; }, TypeError);
  assert.throws(() => { initial.filters.failuresOnly = true; }, TypeError);
});

test("playback keeps the motion cache's bundle identity and a new load gets a fresh cache", () => {
  const input = loadHandmade("move-and-gather.json");
  const store = new ReplayStore();
  store.load(input);
  const first = store.getState().bundle;
  assert.equal(poseAt(first, 1, "ella").facing, "up");

  // Change the intermediate step, keeping the same recorded endpoints.
  input.events[2].payload.to = { x: 1, y: 2 };
  input.events[3].payload.from = { x: 1, y: 2 };
  store.play();
  store.tickPlayback();
  assert.equal(store.getState().bundle, first);
  assert.deepEqual(poseAt(first, 1, "ella", 0.5), { x: 2, y: 3, facing: "up", moving: true });

  store.load(input);
  const second = store.getState().bundle;
  assert.notEqual(second, first);
  assert.equal(poseAt(second, 1, "ella").facing, "right");
});
