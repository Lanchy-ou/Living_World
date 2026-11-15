import assert from "node:assert/strict";
import { test } from "node:test";
import { createReplayLoadCoordinator, readReplayFile } from "../src/replay/loadCoordinator.ts";
import { ReplayStore } from "../src/replay/store.ts";
import { HANDMADE_DIR, readText, validator } from "./lib/env.mjs";

const exampleText = readText(HANDMADE_DIR + "move-and-gather.json");
const otherText = readText(HANDMADE_DIR + "contention.json");

function viewer() {
  const store = new ReplayStore();
  let error = null;
  const requestLoad = createReplayLoadCoordinator({
    onLoad: (bundle, name) => {
      error = null;
      store.load(bundle, name);
    },
    onError: (failure, name) => {
      error = { failure, name };
    },
  });
  return {
    store,
    getError: () => error,
    loadFile: (name, text) =>
      requestLoad(name, () => readReplayFile({ text }, validator.validateText)),
    loadExample: () => requestLoad("Example", () => validator.validateText(exampleText)),
  };
}

test("the last selected replay wins when file reads finish out of order", async () => {
  const { loadFile, store, getError } = viewer();
  const a = Promise.withResolvers();
  const b = Promise.withResolvers();
  const first = loadFile("a.json", () => a.promise);
  const second = loadFile("b.json", () => b.promise);

  b.resolve(otherText);
  await second;
  const latest = store.getState();
  assert.equal(latest.fileName, "b.json");
  assert.deepEqual(latest.bundle, JSON.parse(otherText));

  a.resolve(exampleText);
  await first;
  assert.equal(store.getState(), latest);
  assert.equal(getError(), null);
});

test("Example invalidates a pending file read", async () => {
  const { loadFile, loadExample, store, getError } = viewer();
  const reading = Promise.withResolvers();
  const pending = loadFile("pending.json", () => reading.promise);

  await loadExample();
  const example = store.getState();
  assert.equal(example.fileName, "Example");
  assert.deepEqual(example.bundle, JSON.parse(exampleText));

  reading.resolve(otherText);
  await pending;
  assert.equal(store.getState(), example);
  assert.equal(getError(), null);
});

test("a current file read failure reports an explicit error and preserves the replay", async () => {
  const { loadFile, loadExample, store, getError } = viewer();
  await loadExample();
  store.seek(3);
  const previous = store.getState();
  const reading = Promise.withResolvers();
  const pending = loadFile("unreadable.json", () => reading.promise);

  reading.reject(new Error("file unavailable"));
  await pending;
  assert.equal(store.getState(), previous);
  assert.equal(getError().name, "unreadable.json");
  assert.equal(getError().failure.kind, "file_read");
  assert.match(getError().failure.message, /could not read/i);
});

test("a stale file read failure leaves the latest successful result alone", async () => {
  const { loadFile, loadExample, store, getError } = viewer();
  const reading = Promise.withResolvers();
  const pending = loadFile("unreadable.json", () => reading.promise);

  await loadExample();
  const example = store.getState();
  reading.reject(new Error("file unavailable"));
  await pending;

  assert.equal(store.getState(), example);
  assert.equal(getError(), null);
});

test("stale successes and failures leave the latest error and replay alone", async () => {
  const { loadFile, loadExample, store, getError } = viewer();
  await loadExample();
  const example = store.getState();
  const staleSuccess = Promise.withResolvers();
  const staleFailure = Promise.withResolvers();
  const older = loadFile("pending.json", () => staleSuccess.promise);
  const old = loadFile("unreadable.json", () => staleFailure.promise);

  await loadFile("broken.json", async () => "{");
  const latest = getError();
  assert.equal(latest.name, "broken.json");
  assert.equal(latest.failure.kind, "broken_json");

  staleFailure.reject(new Error("file unavailable"));
  staleSuccess.resolve(otherText);
  await Promise.all([older, old]);

  assert.equal(store.getState(), example);
  assert.equal(getError(), latest);
});
