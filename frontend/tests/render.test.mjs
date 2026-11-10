// Pixel-art renderer checks (frontend-design-v0.1 §8, PF-T02..PF-T13). All pure; no DOM.
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { activityOf, deathRecord } from "../src/panels/activityView.ts";
import { hudView } from "../src/panels/hudView.ts";
import { spriteByKey } from "../src/render/assets/index.ts";
import { EMOTE_NAMES, emoteKey } from "../src/render/assets/objectArt.ts";
import { hash01, spriteFromRows } from "../src/render/assets/pixels.ts";
import {
  FACINGS,
  RESIDENT_FRAMES,
  RESIDENT_HEIGHT,
  RESIDENT_WIDTH,
  corpseSprite,
  residentLook,
  residentSprite,
} from "../src/render/assets/residentArt.ts";
import { FRUIT_SLOTS } from "../src/render/assets/terrainArt.ts";
import { clampZoom, layoutFor, maxZoom, screenToTile, zoomAt } from "../src/render/camera.ts";
import { drawFrame } from "../src/render/drawFrame.ts";
import { facingAt, facingOf, pathInto, poseAt } from "../src/render/motion.ts";
import { MIN_ENTITY_SCALE, SCENE_LAYERS, buildScene, computeSprites, residentAt } from "../src/render/scene.ts";
import { TILE_PX, buildTerrainLayer, terrainSwatch, terrainTilePx } from "../src/render/terrainLayer.ts";
import { viewLayout } from "../src/render/view.ts";
import { ReplayStore, frameAt, lastTick } from "../src/replay/store.ts";
import { LEGEND, MAP_ROWS, generateLongBundle } from "./lib/builder.mjs";
import { SHARED_DIR, loadHandmade, readText, validator } from "./lib/env.mjs";

const VIEW = { width: 900, height: 600 };
const FIT = { zoom: 1, panX: 0, panY: 0, follow: false };
const MAP = { width: MAP_ROWS[0].length, height: MAP_ROWS.length, rows: MAP_ROWS, terrain_legend: LEGEND };

function realExport() {
  const result = validator.validateText(readText(`${SHARED_DIR}mechanics.replay.json`));
  assert.ok(result.ok);
  return result.bundle;
}

function recorder() {
  const calls = [];
  const ctx = new Proxy(
    {},
    {
      get: (_, name) => (...args) => calls.push([name, ...args]),
      set: (_, name, value) => (calls.push(["set", name, value]), true),
    },
  );
  return { ctx, calls };
}

const sameBytes = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
const differs = (a, b) => !sameBytes(a.data, b.data);

test("PF-T02: layers are painted in the fixed order, bottom to top", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const layout = layoutFor(VIEW, bundle.map, FIT);
  const seen = [];
  const { ctx } = recorder();
  drawFrame(ctx, bundle, frameAt(bundle, 3), layout, VIEW, { selectedResidentId: "ryan", onLayer: (l) => seen.push(l) });
  assert.deepEqual(seen, [...SCENE_LAYERS]);
  assert.deepEqual(
    [...SCENE_LAYERS],
    ["terrain", "tree_fruit", "corpse", "ground_item", "resident", "night", "emote", "label", "selection"],
  );
});

test("PF-T02: every sprite is drawn in its layer, and images are used when present", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const frame = frameAt(bundle, 3);
  const layout = layoutFor(VIEW, bundle.map, FIT);
  const scene = buildScene(bundle, frame, layout, {});
  const { ctx, calls } = recorder();
  const order = [];
  const images = { get: (key) => ({ key }) };
  drawFrame(ctx, bundle, frame, layout, VIEW, {
    selectedResidentId: null,
    images,
    terrain: { image: { key: "terrain" }, tilePx: TILE_PX },
    onLayer: (l) => order.push([l, calls.length]),
  });
  const drawn = calls.map((c, i) => [i, c]).filter(([, c]) => c[0] === "drawImage");
  const layerAt = (i) => order.filter(([, at]) => at <= i).at(-1)[0];
  const byLayer = (layer) => drawn.filter(([i]) => layerAt(i) === layer).map(([, c]) => c[1].key);
  assert.deepEqual(byLayer("terrain"), ["terrain"]);
  assert.equal(byLayer("tree_fruit").length, scene.treeFruit.length);
  assert.deepEqual(byLayer("corpse"), scene.sprites.filter((s) => s.kind === "corpse").map((s) => s.image));
  assert.deepEqual(
    byLayer("ground_item"),
    scene.sprites.filter((s) => s.kind === "ground_fruit" || s.kind === "ground_canteen").map((s) => s.image),
  );
  assert.deepEqual(byLayer("resident"), scene.sprites.filter((s) => s.kind === "resident").map((s) => s.image));
  assert.deepEqual(byLayer("emote"), scene.emotes.map((e) => e.image));
  assert.ok(byLayer("corpse").length === 1 && byLayer("ground_item").length === 2 && byLayer("resident").length === 2);
});

test("PF-T03: residents sharing a tile are all visible and identified at every zoom", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const frame = structuredClone(frameAt(bundle, 0));
  for (const r of frame.residents) r.position = { x: 4, y: 4 };
  for (const zoom of [1, 1.7, 3, 99]) {
    const layout = layoutFor(VIEW, bundle.map, { ...FIT, zoom });
    const residents = computeSprites(bundle, frame, layout).filter((s) => s.kind === "resident");
    assert.equal(residents.length, 3);
    for (const s of residents) {
      assert.deepEqual([s.tileX, s.tileY], [4, 4]);
      assert.deepEqual(screenToTile(layout, s.cx, s.cy), { x: 4, y: 4 }, "anchor stays in the recorded tile");
    }
    const centres = residents.map((s) => s.rect.x + s.rect.w / 2).sort((a, b) => a - b);
    // drawn at least 60% of a sprite width apart, so each one shows
    assert.ok(centres[1] - centres[0] >= residents[0].rect.w * 0.6 - 1e-9);
    assert.ok(centres[2] - centres[1] >= residents[0].rect.w * 0.6 - 1e-9);
    const tags = buildScene(bundle, frame, layout, {}).labels.filter((l) => l.kind === "tag");
    assert.deepEqual(tags.map((t) => t.text).sort(), ["A", "B", "C"]);
    assert.equal(new Set(tags.map((t) => Math.round(t.x))).size, 3, "letter tags do not coincide");
  }
});

test("PF-T03: a corpse keeps its tile, carries a non-colour mark, and stands for the dead resident", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  const frame = frameAt(bundle, 3);
  const layout = layoutFor(VIEW, bundle.map, FIT);
  const scene = buildScene(bundle, frame, layout, { selectedResidentId: "mia" });
  const corpse = scene.sprites.find((s) => s.kind === "corpse");
  assert.deepEqual([corpse.tileX, corpse.tileY], [frame.corpses[0].position.x, frame.corpses[0].position.y]);
  assert.equal(corpse.residentId, "mia");
  assert.ok(!scene.sprites.some((s) => s.kind === "resident" && s.id === "mia"));
  const tag = scene.labels.find((l) => l.kind === "corpse_tag");
  assert.equal(tag.text, "B×");
  // selecting a dead resident marks its corpse
  assert.deepEqual(scene.selection.rect, corpse.rect);
  assert.equal(residentAt(scene, corpse.rect.x + corpse.rect.w / 2, corpse.rect.y + corpse.rect.h / 2), "mia");
});

test("PF-T03: sprites never shrink below the minimum scale, so they stay visible at island scale", () => {
  const bundle = generateLongBundle(4);
  const big = structuredClone(bundle);
  big.map = { ...big.map, width: 64, height: 64, rows: Array.from({ length: 64 }, () => ",".repeat(64)) };
  const layout = layoutFor(VIEW, big.map, FIT);
  assert.ok(layout.tile < TILE_PX);
  for (const s of computeSprites(big, frameAt(big, 0), layout)) {
    if (s.kind === "resident") {
      assert.equal(s.rect.w, RESIDENT_WIDTH * MIN_ENTITY_SCALE);
      assert.equal(s.rect.h, RESIDENT_HEIGHT * MIN_ENTITY_SCALE);
    }
    assert.deepEqual(screenToTile(layout, s.cx, s.cy), { x: s.tileX, y: s.tileY });
  }
});

test("PF-T04: free zoom and pan keep every anchor on its recorded tile", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  for (let tick = 0; tick <= lastTick(bundle); tick++) {
    const frame = frameAt(bundle, tick);
    for (const zoom of [1, 1.01, 1.37, 2.5, 4, 50]) {
      for (const [panX, panY] of [[0, 0], [-9999, 9999], [123.4, -77.7], [-40, 12]]) {
        const layout = layoutFor(VIEW, bundle.map, { zoom, panX, panY, follow: false });
        for (const s of computeSprites(bundle, frame, layout)) {
          assert.deepEqual(screenToTile(layout, s.cx, s.cy), { x: s.tileX, y: s.tileY }, `${s.id} t${tick} z${zoom}`);
        }
      }
    }
  }
});

test("PF-T04: zoom is clamped between the fit view and the closest view", () => {
  const map = { width: 64, height: 64 };
  assert.equal(clampZoom(VIEW, map, 0.2), 1);
  assert.equal(clampZoom(VIEW, map, Number.NaN), 1);
  assert.equal(clampZoom(VIEW, map, 1e9), maxZoom(VIEW, map));
  assert.ok(maxZoom(VIEW, map) > 1);
  // a small map on a large screen is already past the closest view: fit is still available
  assert.equal(maxZoom({ width: 4000, height: 4000 }, { width: 4, height: 4 }), 1);
  const closest = layoutFor(VIEW, map, { ...FIT, zoom: 1e9 });
  assert.ok(Math.abs(closest.tile - 96) < 1e-9);
});

test("PF-T04: zooming at a point keeps the map position under that point", () => {
  const map = { width: 64, height: 64 };
  let camera = { ...FIT };
  const point = [610, 220];
  const worldAt = (cam) => {
    const l = layoutFor(VIEW, map, cam);
    return [(point[0] - l.offsetX) / l.tile, (point[1] - l.offsetY) / l.tile];
  };
  const start = worldAt(camera);
  for (const factor of [1.3, 1.3, 2, 0.7, 1.11]) {
    camera = { ...camera, ...zoomAt(VIEW, map, camera, factor, point[0], point[1]) };
    const now = worldAt(camera);
    assert.ok(Math.abs(now[0] - start[0]) < 1e-6 && Math.abs(now[1] - start[1]) < 1e-6, `factor ${factor}`);
  }
  // zooming all the way out returns to the fit size
  camera = { ...camera, ...zoomAt(VIEW, map, camera, 1e-6, point[0], point[1]) };
  assert.equal(camera.zoom, 1);
});

test("PF-T05: selecting a resident changes neither the camera nor playback", () => {
  const bundle = loadHandmade("contention.json");
  const store = new ReplayStore();
  store.load(bundle);
  assert.equal(store.getState().selectedResidentId, null, "nobody is selected after loading");
  store.setCamera({ zoom: 2.2, panX: -31, panY: 17 });
  store.play();
  const before = store.getState();
  for (const id of ["ryan", "ella", null, "mia"]) {
    store.selectResident(id);
    const now = store.getState();
    assert.equal(now.selectedResidentId, id);
    assert.deepEqual(now.camera, before.camera);
    assert.equal(now.playing, true);
    assert.equal(now.currentTick, before.currentTick);
    assert.equal(now.speed, before.speed);
  }
  // the drawn layout is the same with and without a selection while follow is off
  const camera = store.getState().camera;
  assert.deepEqual(viewLayout(bundle, 1, VIEW, camera, "ryan"), viewLayout(bundle, 1, VIEW, camera, null));
});

test("PF-T05: follow is opt-in and centres the selected resident's recorded tile", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const store = new ReplayStore();
  store.load(bundle);
  assert.equal(store.getState().camera.follow, false);
  const camera = { zoom: 1.6, panX: 0, panY: 0, follow: true };
  const layout = viewLayout(bundle, 2, VIEW, camera, "ella");
  const ella = frameAt(bundle, 2).residents.find((r) => r.id === "ella");
  assert.ok(Math.abs(layout.offsetX + (ella.position.x + 0.5) * layout.tile - VIEW.width / 2) < 1e-6);
  assert.ok(Math.abs(layout.offsetY + (ella.position.y + 0.5) * layout.tile - VIEW.height / 2) < 1e-6);
});

test("PF-T06: a path starts at the previous recorded tile and ends at the current one", () => {
  for (const bundle of [realExport(), loadHandmade("move-and-gather.json")]) {
    let moved = 0;
    for (let tick = 0; tick <= lastTick(bundle); tick++) {
      for (const r of frameAt(bundle, tick).residents) {
        const path = pathInto(bundle, tick, r.id);
        assert.deepEqual(path.at(-1), r.position, `end ${r.id} t${tick}`);
        if (path.length > 1) {
          moved++;
          const before = frameAt(bundle, tick - 1).residents.find((p) => p.id === r.id).position;
          assert.deepEqual(path[0], before, `start ${r.id} t${tick}`);
          for (let i = 1; i < path.length; i++) {
            const step = Math.max(Math.abs(path[i].x - path[i - 1].x), Math.abs(path[i].y - path[i - 1].y));
            assert.equal(step, 1, "only adjacent steps are drawn");
          }
        }
        // progress 1 is exactly the recorded frame
        const rest = poseAt(bundle, tick, r.id, 1);
        assert.deepEqual([rest.x, rest.y, rest.moving], [r.position.x, r.position.y, false]);
      }
    }
    assert.ok(moved > 0, "the fixture contains movement");
  }
});

test("PF-T06: the path follows the recorded resident_moved events, tile by tile", () => {
  const bundle = generateLongBundle(4);
  const b = structuredClone(bundle);
  const id = b.residents[0].id;
  const from = b.frames[1].residents.find((r) => r.id === id).position;
  // Three recorded steps in one tick: right, right, down.
  const steps = [
    { x: from.x + 1, y: from.y },
    { x: from.x + 2, y: from.y },
    { x: from.x + 2, y: from.y + 1 },
  ];
  const template = b.events[b.frames[2].event_range.first_index];
  const moves = steps.map((to, i) => ({
    ...structuredClone(template),
    type: "resident_moved",
    actor_id: id,
    payload: { from: i === 0 ? from : steps[i - 1], to, step_cost_units: 1 },
  }));
  b.events.splice(b.frames[2].event_range.first_index, b.frames[2].event_range.count, ...moves);
  const shift = moves.length - b.frames[2].event_range.count;
  b.frames[2].event_range.count = moves.length;
  for (let t = 3; t < b.frames.length; t++) b.frames[t].event_range.first_index += shift;
  for (let t = 2; t < b.frames.length; t++) b.frames[t].residents.find((r) => r.id === id).position = steps[2];

  assert.deepEqual(pathInto(b, 2, id), [from, ...steps]);
  const third = poseAt(b, 2, id, 1 / 6);
  assert.deepEqual([third.x, third.y, third.facing, third.moving], [from.x + 0.5, from.y, "right", true]);
  const last = poseAt(b, 2, id, 5 / 6);
  assert.deepEqual([last.x, last.y, last.facing], [from.x + 2, from.y + 0.5, "down"]);
  assert.equal(facingAt(b, 2, id), "down");
  assert.equal(facingAt(b, 3, id), "down", "facing persists while standing");
  assert.equal(facingAt(b, 0, id), "down", "default facing before any move");

  // If the recorded events do not chain to the recorded position, no route is invented.
  const broken = structuredClone(b);
  broken.events[broken.frames[2].event_range.first_index + 1].payload.from = { x: 0, y: 0 };
  assert.deepEqual(pathInto(broken, 2, id), [steps[2]]);
  const jump = poseAt(broken, 2, id, 0.5);
  assert.deepEqual([jump.x, jump.y, jump.moving], [steps[2].x, steps[2].y, false]);
});

test("PF-T06: facing comes only from recorded displacement", () => {
  assert.equal(facingOf(1, 0), "right");
  assert.equal(facingOf(-1, 0), "left");
  assert.equal(facingOf(0, 1), "down");
  assert.equal(facingOf(0, -1), "up");
  assert.equal(facingOf(1, -1), "right");
  assert.equal(facingOf(0, 0), null);
});

test("PF-T06: drawing with motion never changes the bundle, and progress 1 equals the plain draw", () => {
  const bundle = realExport();
  const before = structuredClone(bundle);
  const layout = layoutFor(VIEW, bundle.map, { ...FIT, zoom: 2 });
  for (let tick = 0; tick <= lastTick(bundle); tick++) {
    for (const progress of [0, 0.25, 0.5, 0.99, 1]) {
      const { ctx } = recorder();
      drawFrame(ctx, bundle, frameAt(bundle, tick), layout, VIEW, { selectedResidentId: "ryan", progress });
    }
    assert.deepEqual(
      computeSprites(bundle, frameAt(bundle, tick), layout, { progress: 1 }),
      computeSprites(bundle, frameAt(bundle, tick), layout),
    );
  }
  assert.deepEqual(bundle, before);
});

test("PF-T06: drawing is deterministic for the same bundle, tick and view", () => {
  const bundle = realExport();
  const layout = layoutFor(VIEW, bundle.map, { ...FIT, zoom: 1.4 });
  const run = () => {
    const { ctx, calls } = recorder();
    drawFrame(ctx, bundle, frameAt(bundle, 3), layout, VIEW, { selectedResidentId: "mia", progress: 0.4 });
    return JSON.stringify(calls);
  };
  assert.equal(run(), run());
});

test("PF-T07: the terrain layer is a deterministic function of the map", () => {
  const a = buildTerrainLayer(MAP);
  const b = buildTerrainLayer(structuredClone(MAP));
  assert.equal(a.width, MAP.width * TILE_PX);
  assert.equal(a.height, MAP.height * TILE_PX);
  assert.ok(sameBytes(a.data, b.data));
  assert.ok(a.data.every((v, i) => i % 4 !== 3 || v === 255), "the layer is fully opaque");
  // the ambient phase only moves water glints: land tiles away from water are identical
  const shimmer = buildTerrainLayer(MAP, 1);
  assert.ok(differs(a, shimmer));
  const px = (layer, x, y) => [...layer.data.subarray((y * layer.width + x) * 4, (y * layer.width + x) * 4 + 3)];
  assert.deepEqual(px(a, 6 * TILE_PX + 8, 6 * TILE_PX + 8), px(shimmer, 6 * TILE_PX + 8, 6 * TILE_PX + 8));
});

test("PF-T07: the drawing follows the map data, not a fixed picture", () => {
  const base = buildTerrainLayer(MAP);
  for (const symbol of ["~", ".", "W", "^", "S", "C", "F", "M"]) {
    const rows = [...MAP_ROWS];
    rows[6] = rows[6].slice(0, 5) + symbol + rows[6].slice(6);
    assert.ok(differs(base, buildTerrainLayer({ ...MAP, rows })), `changing a tile to ${symbol} changes the picture`);
  }
  // a different size and shape draws without code changes
  const wide = { width: 7, height: 3, rows: ["~~~~~~~", "~.,W^.~", "~~~~~~~"], terrain_legend: LEGEND };
  const layer = buildTerrainLayer(wide);
  assert.deepEqual([layer.width, layer.height], [7 * TILE_PX, 3 * TILE_PX]);
});

test("PF-T07: each terrain has its own look, and an undefined symbol is marked, not guessed", () => {
  const swatches = LEGEND.map((e) => [e.terrain, terrainSwatch(e.terrain)]);
  for (let i = 0; i < swatches.length; i++) {
    for (let j = i + 1; j < swatches.length; j++) {
      assert.ok(differs(swatches[i][1], swatches[j][1]), `${swatches[i][0]} vs ${swatches[j][0]}`);
    }
  }
  const unknown = buildTerrainLayer({ width: 1, height: 1, rows: ["?"], terrain_legend: LEGEND });
  const colours = new Set();
  for (let i = 0; i < unknown.data.length; i += 4) colours.add(`${unknown.data[i]},${unknown.data[i + 1]},${unknown.data[i + 2]}`);
  assert.deepEqual([...colours].sort(), ["255,0,255", "26,26,26"]);
});

test("PF-T07: a very large map falls back to flat tiles instead of a huge image", () => {
  assert.equal(terrainTilePx({ width: 64, height: 64 }), TILE_PX);
  assert.equal(terrainTilePx({ width: 256, height: 10 }), TILE_PX);
  assert.equal(terrainTilePx({ width: 300, height: 10 }), 4);
  assert.equal(terrainTilePx({ width: 5000, height: 10 }), 1);
  const rows = Array.from({ length: 2 }, () => ",".repeat(300));
  const layer = buildTerrainLayer({ width: 300, height: 2, rows, terrain_legend: LEGEND });
  assert.deepEqual([layer.width, layer.height], [1200, 8]);
});

test("PF-T08: every sprite key a scene uses resolves to a sprite", () => {
  const keys = new Set();
  for (const name of ["move-and-gather", "contention", "death-drops-pickup", "edge-all-dead"]) {
    const bundle = loadHandmade(`${name}.json`);
    const layout = layoutFor(VIEW, bundle.map, FIT);
    for (let tick = 0; tick <= lastTick(bundle); tick++) {
      for (const progress of [0.3, 1]) {
        const scene = buildScene(bundle, frameAt(bundle, tick), layout, { progress });
        for (const s of [...scene.sprites, ...scene.treeFruit, ...scene.emotes]) keys.add(s.image);
      }
    }
  }
  assert.ok(keys.size >= 8);
  for (const key of keys) assert.notEqual(spriteByKey(key), null, key);
  for (const name of EMOTE_NAMES) assert.notEqual(spriteByKey(emoteKey(name)), null);
  assert.equal(spriteByKey("resident/0/sideways/idle"), null);
  assert.equal(spriteByKey("no/such/key"), null);
});

test("PF-T08: residents differ by look and by letter, in every view and frame", () => {
  for (const facing of FACINGS) {
    for (const frame of RESIDENT_FRAMES) {
      const sprites = [0, 1, 2].map((i) => residentSprite(i, facing, frame));
      for (const s of sprites) assert.deepEqual([s.width, s.height], [RESIDENT_WIDTH, RESIDENT_HEIGHT]);
      assert.ok(differs(sprites[0], sprites[1]) && differs(sprites[1], sprites[2]) && differs(sprites[0], sprites[2]));
    }
  }
  // the silhouettes differ too (alpha channel only), so the cue does not depend on colour
  const outline = (s) => s.data.filter((_, i) => i % 4 === 3);
  const fronts = [0, 1, 2].map((i) => outline(residentSprite(i, "down", "idle")));
  assert.ok(!sameBytes(fronts[0], fronts[1]) && !sameBytes(fronts[1], fronts[2]) && !sameBytes(fronts[0], fronts[2]));
  const looks = Array.from({ length: 8 }, (_, i) => residentLook(i));
  assert.equal(new Set(looks.map((l) => l.letter)).size, 8);
  assert.equal(new Set(looks.map((l) => l.colour)).size, 8);
  assert.deepEqual(residentLook(2), residentLook(2));
  assert.ok(differs(residentSprite(0, "left", "idle"), residentSprite(0, "right", "idle")));
  assert.ok(differs(residentSprite(0, "down", "walk_a"), residentSprite(0, "down", "walk_b")));
  // a corpse is the resident's sprite turned on its side
  const corpse = corpseSprite(1);
  assert.deepEqual([corpse.width, corpse.height], [RESIDENT_HEIGHT, RESIDENT_WIDTH]);
});

test("PF-T08: sprite grids are validated and the display hash is deterministic", () => {
  assert.throws(() => spriteFromRows(["ab", "a"], { a: "#000000", b: "#ffffff" }), /wide/);
  assert.throws(() => spriteFromRows(["az"], { a: "#000000" }), /no colour/);
  assert.equal(hash01(3, 4, 5), hash01(3, 4, 5));
  assert.ok(hash01(3, 4, 5) >= 0 && hash01(3, 4, 5) < 1);
  assert.notEqual(hash01(3, 4, 5), hash01(4, 3, 5));
});

test("PF-T09: fruit in a tree and its badge come from the recorded stock", () => {
  const bundle = loadHandmade("move-and-gather.json");
  const frame = structuredClone(frameAt(bundle, 0));
  const layout = layoutFor(VIEW, bundle.map, FIT);
  frame.fruit_trees[0].stock = 0;
  frame.fruit_trees[1].stock = 2;
  frame.fruit_trees[2].stock = 99;
  const scene = buildScene(bundle, frame, layout, {});
  const count = (id) => scene.treeFruit.filter((f) => f.treeId === id).length;
  assert.equal(count(frame.fruit_trees[0].id), 0);
  assert.equal(count(frame.fruit_trees[1].id), 2);
  assert.equal(count(frame.fruit_trees[2].id), FRUIT_SLOTS.length, "the drawing is capped; the badge is exact");
  const badges = scene.labels.filter((l) => l.kind === "tree_stock");
  assert.deepEqual(badges.map((l) => l.text), ["0", "2", "99"]);
  assert.deepEqual(badges.map((l) => l.dim), [true, false, false]);
});

test("PF-T10: the status line equals counts and sums of the recorded frame", () => {
  const bundle = loadHandmade("death-drops-pickup.json");
  for (let tick = 0; tick <= lastTick(bundle); tick++) {
    const frame = frameAt(bundle, tick);
    const hud = hudView(bundle, tick);
    assert.equal(hud.alive, frame.residents.filter((r) => r.alive).length);
    assert.equal(hud.residents, 3);
    assert.equal(hud.treeFruit, frame.fruit_trees.reduce((n, t) => n + t.stock, 0));
    assert.equal(hud.groundFruit, frame.ground_fruit.reduce((n, g) => n + g.quantity, 0));
    const holders = frame.residents.filter((r) => r.canteen_servings !== null).map((r) => r.id);
    assert.deepEqual(hud.canteens.filter((c) => c.holderId !== null).map((c) => c.holderId), holders);
    assert.equal(hud.canteens.some((c) => c.holderId === null), frame.ground_canteen !== null);
  }
  const clock = hudView(bundle, 0);
  assert.equal(`Day ${clock.day} ${clock.time}`, "Day 1 06:00");
});

test("PF-T10: the status chip restates recorded fields and never guesses", () => {
  const contention = loadHandmade("contention.json");
  const failed = contention.events.find((e) => e.type === "action_failed");
  const activity = activityOf(contention, failed.tick, failed.actor_id);
  assert.equal(activity.kind, "failed");
  assert.equal(activity.code, "RESOURCE_TAKEN");
  assert.equal(activity.label, "Gathering failed: RESOURCE_TAKEN");
  assert.equal(activity.emote, "fail");

  const gather = loadHandmade("move-and-gather.json");
  const active = activityOf(gather, 3, "ella");
  assert.deepEqual([active.kind, active.label, active.actionType], ["active", "Gathering", "gather"]);
  const idle = activityOf(gather, 0, "ella");
  assert.deepEqual([idle.kind, idle.label, idle.emote], ["none", "No action recorded", null]);

  const death = loadHandmade("death-drops-pickup.json");
  const died = death.events.find((e) => e.type === "resident_died");
  assert.equal(activityOf(death, died.tick, "mia").kind, "dead");
  assert.deepEqual(deathRecord(death, died.tick, "mia"), { tick: died.tick, cause: died.payload.cause });
  assert.equal(deathRecord(death, died.tick - 1, "mia"), null, "a death is not shown before its tick");
  assert.equal(deathRecord(death, lastTick(death), "ryan"), null);
});

test("PF-T11: a 1,009-frame bundle plays through one recorded frame per beat at 16 ticks per second", () => {
  const bundle = generateLongBundle(1008);
  const store = new ReplayStore();
  store.load(bundle);
  store.setSpeed(16);
  store.play();
  const layout = layoutFor(VIEW, bundle.map, FIT);
  let beats = 0;
  let last = 0;
  while (store.getState().playing) {
    store.tickPlayback();
    beats++;
    const tick = store.getState().currentTick;
    assert.equal(tick, last + 1, "no recorded frame is skipped");
    last = tick;
    // each beat can be laid out mid-slide and at rest
    buildScene(bundle, frameAt(bundle, tick), layout, { progress: 0.5 });
    buildScene(bundle, frameAt(bundle, tick), layout, {});
  }
  assert.equal(beats, 1008);
  assert.equal(store.getState().currentTick, 1008);
  // 1,008 beats at 16 per second is 63 seconds of playback
  assert.equal(beats / store.getState().speed, 63);
});

test("PF-T13: the asset record names every asset module", () => {
  const dir = fileURLToPath(new URL("../src/render/assets/", import.meta.url));
  const readme = readText(`${dir}README.md`);
  for (const file of readdirSync(dir).filter((f) => f.endsWith(".ts"))) {
    assert.ok(readme.includes(`\`${file}\``), `${file} is recorded in assets/README.md`);
  }
  assert.match(readme, /third-party/i);
});
