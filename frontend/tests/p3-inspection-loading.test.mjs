import assert from "node:assert/strict";
import { test } from "node:test";
import { createInspectionImport, createReplayWithSource } from "../src/p3/loadState.ts";
import { HANDMADE_DIR, readText, validator } from "./lib/env.mjs";

const raw = new TextEncoder().encode("\ufeff" + readText(HANDMADE_DIR + "move-and-gather.json") + "\n").buffer;
const file = (name, arrayBuffer) => ({ name, size: raw.byteLength, arrayBuffer });

test("latest replay selection alone delivers its exact original bytes", async () => {
  const loaded = [];
  const errors = [];
  const { file: selectReplay, example } = createReplayWithSource(
    validator.validateText,
    (bundle, name, bytes) => loaded.push({ bundle, name, bytes }),
    (error) => errors.push(error),
  );
  const firstRead = Promise.withResolvers();
  const first = selectReplay(file("slow.json", () => firstRead.promise));
  await selectReplay(file("current.json", async () => raw));
  firstRead.resolve(raw.slice(0));
  await first;
  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].name, "current.json");
  assert.equal(loaded[0].bytes, raw);
  assert.deepEqual(errors, []);
  const unreadable = selectReplay(file("missing.json", async () => { throw new Error("read failed"); }));
  await unreadable;
  assert.equal(loaded.length, 1);
  assert.equal(errors[0].kind, "file_read");
  const later = Promise.withResolvers();
  const pending = selectReplay(file("another.json", () => later.promise));
  await example("Example", () => validator.validateText(readText(HANDMADE_DIR + "contention.json")));
  later.resolve(raw);
  await pending;
  assert.equal(loaded.length, 2);
  assert.equal(loaded[1].name, "Example");
  assert.equal(loaded[1].bytes, null);
});

test("inspection publication is latest-only and invalidated by a newly accepted replay", async () => {
  const states = [];
  const requests = [];
  const replay = { name: "current replay" };
  const importer = createInspectionImport((files, source, signal) => {
    const deferred = Promise.withResolvers();
    requests.push({ files, source, signal, deferred });
    return deferred.promise;
  }, (state) => states.push(state));
  const slow = importer.select(["old"], replay);
  const current = importer.select(["current"], replay);
  assert.equal(requests[0].source, replay);
  assert.equal(requests[0].signal.aborted, true);
  assert.equal(requests[1].signal.aborted, false);
  requests[0].deferred.resolve("old data");
  await slow;
  assert.deepEqual(states.at(-1), { status: "loading" });
  requests[1].deferred.resolve("verified current data");
  await current;
  assert.deepEqual(states.at(-1), { status: "ready", value: "verified current data" });
  const invalid = importer.select(["invalid"], replay);
  requests[2].deferred.reject(new Error("wrong replay bytes"));
  await invalid;
  assert.deepEqual(states.at(-1), { status: "error", message: "wrong replay bytes" });
  const unbound = importer.select(["stale"], replay);
  importer.reset();
  assert.equal(requests[3].signal.aborted, true);
  requests[3].deferred.resolve("prior replay data");
  await unbound;
  assert.deepEqual(states.at(-1), { status: "idle" });
});
