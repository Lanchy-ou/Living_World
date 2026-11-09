// Test-only helpers to author replay bundles (hand-made fixtures and generated large bundles).
// These helpers only assemble data; the viewer never uses them. Not simulation output.
import { createHash } from "node:crypto";

export const HASH = "a".repeat(64);

export const MAP_ROWS = [
  "~~~~~~~~~~~~",
  "~..,,,W^^..~",
  "~.,F,,,,S..~",
  "~.,,,WW,,C.~",
  "~..,M,,,,F.~",
  "~.,,,,F,,..~",
  "~..,,,,,,..~",
  "~~~~~~~~~~~~",
];

export const LEGEND = [
  ["~", "sea"],
  [".", "beach"],
  [",", "grass"],
  ["W", "woods"],
  ["^", "rock"],
  ["S", "spring"],
  ["C", "cave"],
  ["F", "fruit_tree"],
  ["M", "damp_moss"],
].map(([symbol, terrain]) => ({ symbol, terrain }));

export const mapHash = (rows) =>
  createHash("sha256")
    .update(rows.join("\n") + "\n", "utf8")
    .digest("hex");

export const eventId = (runId, tick, seq) =>
  `${runId}:${String(tick).padStart(10, "0")}:${String(seq).padStart(6, "0")}`;

/** Sorted keys, no whitespace, LF at the end: stable fixture bytes. */
export function canonicalJson(value) {
  const sort = (v) =>
    Array.isArray(v)
      ? v.map(sort)
      : v !== null && typeof v === "object"
        ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sort(v[k])]))
        : v;
  return JSON.stringify(sort(value)) + "\n";
}

export const coord = (x, y) => ({ x, y });

export function residentFrame(id, x, y, extra = {}) {
  return {
    id,
    position: coord(x, y),
    alive: true,
    satiety: 9000,
    hydration: 8000,
    stamina: 7000,
    health: 10000,
    fruit_count: 0,
    canteen_servings: null,
    active_action: null,
    ...extra,
  };
}

/** Mutable data holder for authoring scenes; `snapshot()` freezes a copy for one frame. */
export class Scene {
  constructor(residents, trees) {
    this.residents = residents.map((r) => structuredClone(r));
    this.trees = trees.map((t) => structuredClone(t));
    this.piles = [];
    this.canteen = null;
    this.corpses = [];
  }

  resident(id) {
    const r = this.residents.find((x) => x.id === id);
    if (!r) throw new Error(`no resident ${id}`);
    return r;
  }

  tree(id) {
    const t = this.trees.find((x) => x.id === id);
    if (!t) throw new Error(`no tree ${id}`);
    return t;
  }

  snapshot() {
    return structuredClone({
      residents: this.residents,
      fruit_trees: this.trees,
      ground_fruit: [...this.piles].sort(
        (a, b) => a.position.y - b.position.y || a.position.x - b.position.x,
      ),
      ground_canteen: this.canteen,
      corpses: this.corpses,
    });
  }
}

export class BundleBuilder {
  constructor({ runId, worldId, rows = MAP_ROWS, residents, bounds, clock }) {
    this.runId = runId;
    this.worldId = worldId;
    this.rows = rows;
    this.residents = residents;
    this.bounds = bounds ?? { min_value: 0, max_value: 10000 };
    this.clock = clock ?? { tick_minutes: 10, start_hour: 6, day_start_hour: 6, day_end_hour: 20 };
    this.events = [];
    this.frames = [];
    this.seq = new Map();
    this.event(0, "world_initialized", {
      config_hash: HASH,
      map_hash: mapHash(rows),
      initial_snapshot_hash: HASH,
    });
  }

  /** Events must be added in tick order; seq_in_tick is allocated here. */
  event(tick, type, payload, { actor = null, target = null, intent = null, causedBy = [] } = {}) {
    const seq = this.seq.get(tick) ?? 0;
    this.seq.set(tick, seq + 1);
    const id = eventId(this.runId, tick, seq);
    this.events.push({
      schema_version: "0.1",
      run_id: this.runId,
      event_id: id,
      tick,
      seq_in_tick: seq,
      type,
      actor_id: actor,
      target_id: target,
      intent_id: intent,
      llm_call_id: null,
      caused_by_event_ids: causedBy,
      payload,
    });
    return id;
  }

  frame(tick, snapshot) {
    this.frames.push({ tick, ...snapshot, event_range: { first_index: 0, count: 0 } });
  }

  build() {
    let cursor = 0;
    for (const f of this.frames) {
      const count = this.events.filter((e) => e.tick === f.tick).length;
      f.event_range = { first_index: cursor, count };
      cursor += count;
    }
    return {
      replay_schema_version: "0.1",
      run_id: this.runId,
      world_id: this.worldId,
      config_hash: HASH,
      map_hash: mapHash(this.rows),
      clock: this.clock,
      condition_bounds: this.bounds,
      map: {
        width: this.rows[0].length,
        height: this.rows.length,
        rows: this.rows,
        terrain_legend: LEGEND,
      },
      residents: this.residents,
      frames: this.frames,
      events: this.events,
    };
  }
}

export const RESIDENTS = [
  { id: "ella", display_name: "艾拉" },
  { id: "mia", display_name: "米娅" },
  { id: "ryan", display_name: "莱恩" },
];

export const TREES = [
  { id: "fruit_01", position: coord(3, 2), stock: 3 },
  { id: "fruit_02", position: coord(6, 5), stock: 3 },
  { id: "fruit_03", position: coord(9, 4), stock: 3 },
];

/** A valid bundle with `ticks` + 1 frames and one condition_updated event per tick (FE-T06). */
export function generateLongBundle(ticks) {
  const scene = new Scene(
    [residentFrame("ella", 2, 2), residentFrame("mia", 3, 3), residentFrame("ryan", 4, 3)],
    TREES,
  );
  const b = new BundleBuilder({
    runId: "generated_long_run",
    worldId: "generated",
    residents: RESIDENTS,
  });
  b.frame(0, scene.snapshot());
  for (let t = 1; t <= ticks; t++) {
    const ella = scene.resident("ella");
    const before = ella.satiety;
    ella.satiety = Math.max(0, ella.satiety - 5);
    ella.position = coord(2 + (t % 2), 2);
    b.event(
      t,
      "condition_updated",
      {
        resident_id: "ella",
        satiety_before: before,
        satiety_after: ella.satiety,
        hydration_before: ella.hydration,
        hydration_after: ella.hydration,
        stamina_before: ella.stamina,
        stamina_after: ella.stamina,
        health_before: ella.health,
        health_after: ella.health,
      },
      { actor: "ella" },
    );
    b.frame(t, scene.snapshot());
  }
  return b.build();
}
