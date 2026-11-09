// Builds the HAND-MADE replay fixtures (replay-frontend §5). Not simulation output.
// Run: node tests/fixtures/handmade/build.mjs   (rewrites the .json files next to this script)
// tests/viewer.test.mjs fails if the committed files drift from this builder.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  BundleBuilder,
  RESIDENTS,
  Scene,
  TREES,
  canonicalJson,
  coord,
  mapHash,
  residentFrame,
} from "../../lib/builder.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Per-tick metabolism shown in the fixtures: plain data edits, authored by hand. */
function decay(scene, b, tick, only) {
  for (const r of scene.residents) {
    if (!r.alive) continue;
    const before = { s: r.satiety, h: r.hydration, st: r.stamina, hp: r.health };
    r.satiety = Math.max(0, r.satiety - 10);
    r.hydration = Math.max(0, r.hydration - 10);
    if (only.includes(r.id)) {
      b.event(
        tick,
        "condition_updated",
        {
          resident_id: r.id,
          satiety_before: before.s,
          satiety_after: r.satiety,
          hydration_before: before.h,
          hydration_after: r.hydration,
          stamina_before: before.st,
          stamina_after: r.stamina,
          health_before: before.hp,
          health_after: r.health,
        },
        { actor: r.id },
      );
    }
  }
}

const action = (intent, type, started, remaining) => ({
  intent_id: intent,
  action_type: type,
  tick_started: started,
  remaining_ticks: remaining,
});

export function moveAndGather() {
  const scene = new Scene(
    [residentFrame("ella", 1, 3, { satiety: 6000 }), residentFrame("mia", 1, 4), residentFrame("ryan", 2, 4)],
    TREES,
  );
  const b = new BundleBuilder({
    runId: "handmade_move_and_gather",
    worldId: "handmade_island",
    residents: RESIDENTS,
  });
  const ella = scene.resident("ella");
  b.frame(0, scene.snapshot());

  // tick 1: ella walks two tiles to (2,2)
  const move = b.event(
    1,
    "action_started",
    { action_type: "move_to", plan_id: "ella:p000001", duration_ticks: null },
    { actor: "ella", intent: "ella:p000001:i0" },
  );
  b.event(1, "resident_moved", { from: coord(1, 3), to: coord(2, 3), step_cost_units: 1 }, { actor: "ella", intent: "ella:p000001:i0", causedBy: [move] });
  b.event(1, "resident_moved", { from: coord(2, 3), to: coord(2, 2), step_cost_units: 1 }, { actor: "ella", intent: "ella:p000001:i0", causedBy: [move] });
  b.event(1, "action_succeeded", { action_type: "move_to", result_code: "OK" }, { actor: "ella", intent: "ella:p000001:i0" });
  ella.position = coord(2, 2);
  decay(scene, b, 1, ["ella"]);
  b.frame(1, scene.snapshot());

  // tick 2: gather starts (duration 2)
  const gather = b.event(
    2,
    "action_started",
    { action_type: "gather", plan_id: "ella:p000001", duration_ticks: 2 },
    { actor: "ella", target: "fruit_01", intent: "ella:p000001:i1" },
  );
  ella.active_action = action("ella:p000001:i1", "gather", 2, 2);
  decay(scene, b, 2, ["ella"]);
  b.frame(2, scene.snapshot());

  // tick 3: progress
  b.event(3, "action_progressed", { action_type: "gather", elapsed_ticks: 1, remaining_ticks: 1, route_cursor: null }, { actor: "ella", intent: "ella:p000001:i1" });
  ella.active_action = action("ella:p000001:i1", "gather", 2, 1);
  decay(scene, b, 3, ["ella"]);
  b.frame(3, scene.snapshot());

  // tick 4: gathered
  const got = b.event(
    4,
    "fruit_gathered",
    { tree_id: "fruit_01", quantity: 1, stock_before: 3, stock_after: 2 },
    { actor: "ella", target: "fruit_01", intent: "ella:p000001:i1", causedBy: [gather] },
  );
  b.event(4, "stamina_action_cost_applied", { amount: 50, reason: "gather" }, { actor: "ella", intent: "ella:p000001:i1", causedBy: [got] });
  b.event(4, "action_succeeded", { action_type: "gather", result_code: "OK" }, { actor: "ella", intent: "ella:p000001:i1", causedBy: [got] });
  scene.tree("fruit_01").stock = 2;
  ella.fruit_count = 1;
  ella.stamina -= 50;
  ella.active_action = null;
  decay(scene, b, 4, ["ella"]);
  b.frame(4, scene.snapshot());

  // tick 5: eat starts
  b.event(5, "action_started", { action_type: "eat", plan_id: "ella:p000001", duration_ticks: 1 }, { actor: "ella", intent: "ella:p000001:i2" });
  ella.active_action = action("ella:p000001:i2", "eat", 5, 1);
  decay(scene, b, 5, ["ella"]);
  b.frame(5, scene.snapshot());

  // tick 6: eaten
  const before = ella.satiety;
  const eaten = b.event(6, "fruit_consumed", { quantity: 1, satiety_before: before, satiety_after: before + 1500 }, { actor: "ella", intent: "ella:p000001:i2" });
  b.event(6, "action_succeeded", { action_type: "eat", result_code: "OK" }, { actor: "ella", intent: "ella:p000001:i2", causedBy: [eaten] });
  ella.satiety = before + 1500;
  ella.fruit_count = 0;
  ella.active_action = null;
  b.frame(6, scene.snapshot());
  return b.build();
}

export function contention() {
  const trees = TREES.map((t) => (t.id === "fruit_02" ? { ...t, stock: 1 } : t));
  const scene = new Scene(
    [residentFrame("ella", 5, 5), residentFrame("mia", 2, 4), residentFrame("ryan", 7, 5)],
    trees,
  );
  const b = new BundleBuilder({
    runId: "handmade_contention",
    worldId: "handmade_island",
    residents: RESIDENTS,
  });
  const ella = scene.resident("ella");
  const ryan = scene.resident("ryan");
  b.frame(0, scene.snapshot());

  const ellaStart = b.event(1, "action_started", { action_type: "gather", plan_id: "ella:p000001", duration_ticks: 2 }, { actor: "ella", target: "fruit_02", intent: "ella:p000001:i0" });
  const ryanStart = b.event(1, "action_started", { action_type: "gather", plan_id: "ryan:p000001", duration_ticks: 2 }, { actor: "ryan", target: "fruit_02", intent: "ryan:p000001:i0" });
  ella.active_action = action("ella:p000001:i0", "gather", 1, 2);
  ryan.active_action = action("ryan:p000001:i0", "gather", 1, 2);
  decay(scene, b, 1, ["ella", "ryan"]);
  b.frame(1, scene.snapshot());

  b.event(2, "action_progressed", { action_type: "gather", elapsed_ticks: 1, remaining_ticks: 1, route_cursor: null }, { actor: "ella", intent: "ella:p000001:i0" });
  b.event(2, "action_progressed", { action_type: "gather", elapsed_ticks: 1, remaining_ticks: 1, route_cursor: null }, { actor: "ryan", intent: "ryan:p000001:i0" });
  ella.active_action = action("ella:p000001:i0", "gather", 1, 1);
  ryan.active_action = action("ryan:p000001:i0", "gather", 1, 1);
  decay(scene, b, 2, ["ella", "ryan"]);
  b.frame(2, scene.snapshot());

  // tick 3: both complete; ella resolves first and takes the last fruit, ryan gets RESOURCE_TAKEN
  const got = b.event(3, "fruit_gathered", { tree_id: "fruit_02", quantity: 1, stock_before: 1, stock_after: 0 }, { actor: "ella", target: "fruit_02", intent: "ella:p000001:i0", causedBy: [ellaStart] });
  b.event(3, "stamina_action_cost_applied", { amount: 50, reason: "gather" }, { actor: "ella", intent: "ella:p000001:i0", causedBy: [got] });
  b.event(3, "action_succeeded", { action_type: "gather", result_code: "OK" }, { actor: "ella", intent: "ella:p000001:i0", causedBy: [got] });
  b.event(3, "action_failed", { action_type: "gather", failure_code: "RESOURCE_TAKEN" }, { actor: "ryan", target: "fruit_02", intent: "ryan:p000001:i0", causedBy: [ryanStart, got] });
  scene.tree("fruit_02").stock = 0;
  ella.fruit_count = 1;
  ella.stamina -= 50;
  ella.active_action = null;
  ryan.active_action = null;
  decay(scene, b, 3, ["ella", "ryan"]);
  b.frame(3, scene.snapshot());

  b.event(4, "action_started", { action_type: "wait", plan_id: "ryan:p000002", duration_ticks: 1 }, { actor: "ryan", intent: "ryan:p000002:i0" });
  ryan.active_action = action("ryan:p000002:i0", "wait", 4, 1);
  decay(scene, b, 4, ["ella", "ryan"]);
  b.frame(4, scene.snapshot());
  return b.build();
}

export function deathDropsPickup() {
  const mia = residentFrame("mia", 8, 3, {
    satiety: 50,
    hydration: 0,
    health: 300,
    fruit_count: 2,
    canteen_servings: 3,
  });
  const scene = new Scene([residentFrame("ella", 2, 2), mia, residentFrame("ryan", 7, 3)], TREES);
  const b = new BundleBuilder({
    runId: "handmade_death_drops_pickup",
    worldId: "handmade_island",
    residents: RESIDENTS,
  });
  const m = scene.resident("mia");
  const ryan = scene.resident("ryan");
  b.frame(0, scene.snapshot());

  for (const [tick, hp] of [
    [1, 200],
    [2, 100],
  ]) {
    const before = m.health;
    m.health = hp;
    b.event(tick, "condition_updated", { resident_id: "mia", satiety_before: 50, satiety_after: 50, hydration_before: 0, hydration_after: 0, stamina_before: m.stamina, stamina_after: m.stamina, health_before: before, health_after: hp }, { actor: "mia" });
    b.frame(tick, scene.snapshot());
  }

  // tick 3: death, corpse, drops
  const cond = b.event(3, "condition_updated", { resident_id: "mia", satiety_before: 50, satiety_after: 50, hydration_before: 0, hydration_after: 0, stamina_before: m.stamina, stamina_after: m.stamina, health_before: 100, health_after: 0 }, { actor: "mia" });
  const died = b.event(3, "resident_died", { resident_id: "mia", position: coord(8, 3), cause: "DEPRIVATION" }, { actor: "mia", causedBy: [cond] });
  b.event(3, "corpse_created", { corpse_id: "corpse@mia", resident_id: "mia", position: coord(8, 3) }, { actor: "mia", causedBy: [died] });
  b.event(3, "item_dropped", { resident_id: "mia", position: coord(8, 3), item_type: "fruit", quantity: 2, canteen_id: null, canteen_servings: null }, { actor: "mia", causedBy: [died] });
  b.event(3, "item_dropped", { resident_id: "mia", position: coord(8, 3), item_type: "canteen", quantity: 1, canteen_id: "canteen_01", canteen_servings: 3 }, { actor: "mia", causedBy: [died] });
  m.alive = false;
  m.health = 0;
  m.fruit_count = 0;
  m.canteen_servings = null;
  scene.corpses = [{ id: "corpse@mia", resident_id: "mia", position: coord(8, 3) }];
  scene.piles = [{ position: coord(8, 3), quantity: 2 }];
  scene.canteen = { position: coord(8, 3), servings: 3 };
  b.frame(3, scene.snapshot());

  // ryan stands next to the pile and picks up the fruit, then the canteen
  b.event(4, "action_started", { action_type: "pick_up", plan_id: "ryan:p000001", duration_ticks: 1 }, { actor: "ryan", intent: "ryan:p000001:i0" });
  ryan.active_action = action("ryan:p000001:i0", "pick_up", 4, 1);
  b.frame(4, scene.snapshot());

  const fruitUp = b.event(5, "item_picked_up", { resident_id: "ryan", position: coord(8, 3), item_type: "fruit", quantity: 2, canteen_id: null }, { actor: "ryan", intent: "ryan:p000001:i0" });
  b.event(5, "action_succeeded", { action_type: "pick_up", result_code: "OK" }, { actor: "ryan", intent: "ryan:p000001:i0", causedBy: [fruitUp] });
  ryan.fruit_count = 2;
  ryan.active_action = null;
  scene.piles = [];
  b.frame(5, scene.snapshot());

  b.event(6, "action_started", { action_type: "pick_up", plan_id: "ryan:p000002", duration_ticks: 1 }, { actor: "ryan", intent: "ryan:p000002:i0" });
  ryan.active_action = action("ryan:p000002:i0", "pick_up", 6, 1);
  b.frame(6, scene.snapshot());

  const canteenUp = b.event(7, "item_picked_up", { resident_id: "ryan", position: coord(8, 3), item_type: "canteen", quantity: 1, canteen_id: "canteen_01" }, { actor: "ryan", intent: "ryan:p000002:i0" });
  b.event(7, "action_succeeded", { action_type: "pick_up", result_code: "OK" }, { actor: "ryan", intent: "ryan:p000002:i0", causedBy: [canteenUp] });
  ryan.canteen_servings = 3;
  ryan.active_action = null;
  scene.canteen = null;
  b.frame(7, scene.snapshot());
  return b.build();
}

export function frame0Only() {
  const scene = new Scene(
    [residentFrame("ella", 1, 3), residentFrame("mia", 1, 4), residentFrame("ryan", 2, 4)],
    TREES,
  );
  const b = new BundleBuilder({ runId: "handmade_frame0_only", worldId: "handmade_island", residents: RESIDENTS });
  b.frame(0, scene.snapshot());
  return b.build();
}

export function allDead() {
  const dying = (id, x, y) => residentFrame(id, x, y, { health: 100, hydration: 0 });
  const scene = new Scene([dying("ella", 2, 2), dying("mia", 3, 3), dying("ryan", 4, 3)], TREES);
  const b = new BundleBuilder({ runId: "handmade_all_dead", worldId: "handmade_island", residents: RESIDENTS });
  b.frame(0, scene.snapshot());
  const corpses = [];
  for (const [id, x, y] of [["ella", 2, 2], ["mia", 3, 3], ["ryan", 4, 3]]) {
    const died = b.event(1, "resident_died", { resident_id: id, position: coord(x, y), cause: "DEPRIVATION" }, { actor: id });
    b.event(1, "corpse_created", { corpse_id: `corpse@${id}`, resident_id: id, position: coord(x, y) }, { actor: id, causedBy: [died] });
    const r = scene.resident(id);
    r.alive = false;
    r.health = 0;
    corpses.push({ id: `corpse@${id}`, resident_id: id, position: coord(x, y) });
  }
  scene.corpses = corpses;
  b.frame(1, scene.snapshot());
  b.frame(2, scene.snapshot());
  return b.build();
}

// --- invalid edge cases, each derived from move-and-gather by one change -------------------

function withMapRows(bundle, rows) {
  const out = structuredClone(bundle);
  out.map.rows = rows;
  out.map_hash = mapHash(rows);
  out.events[0].payload.map_hash = out.map_hash;
  return out;
}

export function unknownTerrainSymbol() {
  const base = moveAndGather();
  const rows = [...base.map.rows];
  rows[1] = "X" + rows[1].slice(1);
  return withMapRows(base, rows);
}

export function unknownVersion() {
  const out = moveAndGather();
  out.replay_schema_version = "0.2";
  return out;
}

export function eventsOutOfOrder() {
  const out = moveAndGather();
  // swap the last event of tick 1 with the first event of tick 2
  const lastOfOne = out.events.map((e) => e.tick).lastIndexOf(1);
  [out.events[lastOfOne], out.events[lastOfOne + 1]] = [out.events[lastOfOne + 1], out.events[lastOfOne]];
  return out;
}

export function missingFrame() {
  const out = moveAndGather();
  out.frames.splice(2, 1);
  return out;
}

export function brokenJsonText() {
  const text = canonicalJson(moveAndGather());
  return text.slice(0, Math.floor(text.length / 2));
}

/** file name -> { text, expect } where expect is "valid" or the refusal the viewer must give. */
export function buildAll() {
  const files = new Map();
  const add = (name, bundle, expect) => files.set(name, { text: canonicalJson(bundle), expect });
  add("move-and-gather.json", moveAndGather(), "valid");
  add("contention.json", contention(), "valid");
  add("death-drops-pickup.json", deathDropsPickup(), "valid");
  add("edge-frame0-only.json", frame0Only(), "valid");
  add("edge-all-dead.json", allDead(), "valid");
  add("edge-unknown-terrain-symbol.json", unknownTerrainSymbol(), { kind: "schema" });
  add("edge-unknown-version.json", unknownVersion(), { kind: "unknown_version" });
  add("edge-events-out-of-order.json", eventsOutOfOrder(), { kind: "cross_field", rule: "event_order" });
  add("edge-missing-frame.json", missingFrame(), { kind: "cross_field", rule: "frame_ticks" });
  files.set("edge-broken-json.json", { text: brokenJsonText(), expect: { kind: "broken_json" } });
  return files;
}


if (import.meta.url === `file://${process.argv[1].replaceAll("\\", "/")}` || process.argv[1] === fileURLToPath(import.meta.url)) {
  mkdirSync(HERE, { recursive: true });
  for (const [name, { text }] of buildAll()) writeFileSync(`${HERE}/${name}`, text);
  console.log(`wrote ${buildAll().size} hand-made fixtures`);
}
