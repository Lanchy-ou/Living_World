// Browser mirror of the backend cross-field rules (contract/replay.py, replay-frontend §2.3).
// Same rule groups and slugs, same order. Structural/domain checks only: no re-execution.
import { compareUtf8, formatEventId, mapHashOf } from "./canon.ts";
import type { ReplayBundle, ReplayError, WorldEvent } from "./types.ts";
import { RESIDENT_REF_FIELDS } from "./types.ts";

class RuleError extends Error {
  readonly rule: string;
  constructor(rule: string, message: string) {
    super(`${rule}: ${message}`);
    this.rule = rule;
  }
}

type Payload = Record<string, unknown>;
const payloadOf = (e: WorldEvent): Payload => e.payload as unknown as Payload;
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

interface Coord {
  x: number;
  y: number;
}
const inMap = (c: Coord, w: number, h: number): boolean => c.x < w && c.y < h;

function requireStrictlyAscending<T>(
  keys: T[],
  cmp: (a: T, b: T) => number,
  rule: string,
  what: string,
): void {
  for (let i = 1; i < keys.length; i++) {
    if (cmp(keys[i - 1] as T, keys[i] as T) === 0)
      throw new RuleError(rule, `duplicate ${what} ${JSON.stringify(keys[i])}`);
  }
  for (let i = 1; i < keys.length; i++) {
    if (cmp(keys[i - 1] as T, keys[i] as T) > 0)
      throw new RuleError(rule, `${what} must be sorted ascending`);
  }
}

const cmpTuple = (a: [number, number], b: [number, number]): number => a[0] - b[0] || a[1] - b[1];

// backend: ReplayClock._world_rules_1_1
function checkClock(b: ReplayBundle): void {
  const c = b.clock;
  if (1440 % c.tick_minutes !== 0) throw new RuleError("clock", "tick_minutes must divide 1440");
  if (!(c.day_start_hour < c.day_end_hour))
    throw new RuleError("clock", "day_start_hour must be below day_end_hour");
}

// backend: ReplayMap._grid_and_legend
function checkMap(b: ReplayBundle): void {
  const m = b.map;
  if (m.rows.length !== m.height)
    throw new RuleError("map", `expected ${m.height} rows, got ${m.rows.length}`);
  m.rows.forEach((row, y) => {
    if (row.length !== m.width)
      throw new RuleError("map", `row ${y} has length ${row.length}, expected ${m.width}`);
  });
  const expected = "~:sea .:beach ,:grass W:woods ^:rock S:spring C:cave F:fruit_tree M:damp_moss";
  const actual = m.terrain_legend.map((e) => `${e.symbol}:${e.terrain}`).join(" ");
  if (actual !== expected)
    throw new RuleError(
      "legend",
      "terrain_legend must be exactly the nine World Rules §1.2 pairs in order ~ . , W ^ S C F M",
    );
}

// backend: ReplayBundle._check_map_hash
function checkMapHash(b: ReplayBundle): void {
  if (b.map_hash !== mapHashOf(b.map.rows))
    throw new RuleError("map_hash", "does not match rows joined with LF plus a final LF");
}

// backend: ReplayBundle._check_declared_residents
function checkDeclaredResidents(b: ReplayBundle): void {
  requireStrictlyAscending(
    b.residents.map((r) => r.id),
    compareUtf8,
    "residents",
    "declared resident id",
  );
}

// backend: DisplayFrame._unique_and_sorted (runs per frame at parse time, before the bundle)
function checkFrameSorting(b: ReplayBundle): void {
  for (const f of b.frames) {
    requireStrictlyAscending(
      f.residents.map((r) => r.id),
      compareUtf8,
      "frame_sort",
      "resident id",
    );
    requireStrictlyAscending(
      f.fruit_trees.map((t) => t.id),
      compareUtf8,
      "frame_sort",
      "fruit tree id",
    );
    requireStrictlyAscending(
      f.corpses.map((c) => c.id),
      compareUtf8,
      "frame_sort",
      "corpse id",
    );
    requireStrictlyAscending(
      f.ground_fruit.map((g): [number, number] => [g.position.y, g.position.x]),
      cmpTuple,
      "frame_sort",
      "ground fruit (y, x)",
    );
  }
}

// backend: ReplayBundle._check_frame_ticks
function checkFrameTicks(b: ReplayBundle): void {
  b.frames.forEach((f, i) => {
    if (f.tick !== i)
      throw new RuleError(
        "frame_ticks",
        `frame at index ${i} has tick ${f.tick}; ticks must be contiguous from 0`,
      );
  });
}

// backend: ReplayBundle._check_events + _check_initialization_event
function checkEvents(b: ReplayBundle): void {
  const seen = new Set<string>();
  for (const e of b.events) {
    if (e.run_id !== b.run_id)
      throw new RuleError("run_id", `event ${e.event_id} has run_id ${JSON.stringify(e.run_id)}`);
    const expected = formatEventId(e.run_id, e.tick, e.seq_in_tick);
    if (e.event_id !== expected)
      throw new RuleError("event_id", `${e.event_id} does not match ${expected}`);
    if (seen.has(e.event_id)) throw new RuleError("event_id", `duplicate event id ${e.event_id}`);
    seen.add(e.event_id);
  }
  let prev: WorldEvent | null = null;
  for (const e of b.events) {
    if (prev === null || e.tick > prev.tick) {
      if (e.seq_in_tick !== 0)
        throw new RuleError(
          "event_seq",
          `first event of tick ${e.tick} has seq_in_tick ${e.seq_in_tick}, expected 0`,
        );
    } else if (e.tick < prev.tick || e.seq_in_tick <= prev.seq_in_tick) {
      throw new RuleError(
        "event_order",
        `${e.event_id} follows ${prev.event_id}; events must be strictly ordered by (tick, seq_in_tick)`,
      );
    } else if (e.seq_in_tick !== prev.seq_in_tick + 1) {
      throw new RuleError(
        "event_seq",
        `${e.event_id} follows ${prev.event_id}; seq_in_tick must be contiguous`,
      );
    }
    prev = e;
  }
  const first = b.events[0];
  if (first === undefined || first.tick !== 0 || first.type !== "world_initialized")
    throw new RuleError("init_event", "the first event must be world_initialized at tick 0");
  const p = payloadOf(first);
  if (p["config_hash"] !== b.config_hash)
    throw new RuleError("init_event", "world_initialized config_hash differs from the bundle");
  if (p["map_hash"] !== b.map_hash)
    throw new RuleError("init_event", "world_initialized map_hash differs from the bundle");
}

// backend: ReplayBundle._check_event_ranges
function checkEventRanges(b: ReplayBundle): void {
  const perTick = new Map<number, number>();
  for (const e of b.events) perTick.set(e.tick, (perTick.get(e.tick) ?? 0) + 1);
  let cursor = 0;
  for (const f of b.frames) {
    const { first_index: first, count } = f.event_range;
    if (first !== cursor)
      throw new RuleError(
        "event_range",
        `frame ${f.tick} first_index ${first}, expected cumulative prior count ${cursor}`,
      );
    const end = first + count;
    if (end > b.events.length)
      throw new RuleError("event_range", `frame ${f.tick} slice ends past the events`);
    for (const e of b.events.slice(first, end)) {
      if (e.tick !== f.tick)
        throw new RuleError(
          "event_range",
          `frame ${f.tick} slice holds ${e.event_id} of tick ${e.tick}`,
        );
    }
    const have = perTick.get(f.tick) ?? 0;
    if (count !== have)
      throw new RuleError(
        "event_range",
        `frame ${f.tick} count ${count} but the bundle has ${have} events at that tick`,
      );
    cursor = end;
  }
  if (cursor !== b.events.length)
    throw new RuleError(
      "event_range",
      `slices cover ${cursor} of ${b.events.length} events; every event must belong to exactly one frame`,
    );
}

// backend: ReplayBundle._check_event_references
function checkEventReferences(b: ReplayBundle): void {
  const indexOf = new Map(b.events.map((e, i) => [e.event_id, i] as const));
  const spoken = new Map<string, { act: string; speaker: string | null; addressee: string }>();
  const residents = new Set(b.residents.map((r) => r.id));
  const treeIds = new Set((b.frames[0]?.fruit_trees ?? []).map((t) => t.id));
  b.events.forEach((e, i) => {
    for (const ref of e.caused_by_event_ids) {
      const at = indexOf.get(ref);
      if (at === undefined)
        throw new RuleError("causal_refs", `${e.event_id} cites unknown event ${ref}`);
      if (at >= i)
        throw new RuleError("causal_refs", `${e.event_id} cites ${ref}, which is not earlier`);
    }
    const p = payloadOf(e);
    if (e.type === "utterance_spoken") {
      const act = String(p["speech_act"]);
      const replyTo = p["in_reply_to"] as string | null;
      if (p["utterance_id"] !== e.event_id)
        throw new RuleError(
          "utterance_refs",
          `utterance_id of ${e.event_id} must equal its event id`,
        );
      if ((act === "accept" || act === "refuse") !== (replyTo !== null))
        throw new RuleError(
          "utterance_refs",
          `${e.event_id} (${act}) requires in_reply_to for accept/refuse and forbids it otherwise`,
        );
      if (replyTo !== null) {
        const asked = spoken.get(replyTo);
        if (asked === undefined || asked.act !== "request")
          throw new RuleError(
            "utterance_refs",
            `in_reply_to of ${e.event_id} must cite an earlier utterance_spoken request`,
          );
        if (e.actor_id !== asked.addressee || p["addressee_id"] !== asked.speaker)
          throw new RuleError(
            "utterance_refs",
            `reply ${e.event_id} must come from the request addressee to its speaker`,
          );
      }
      spoken.set(e.event_id, { act, speaker: e.actor_id, addressee: String(p["addressee_id"]) });
    } else if (e.type === "utterance_heard" && !spoken.has(String(p["utterance_id"]))) {
      throw new RuleError(
        "utterance_refs",
        `utterance_heard ${e.event_id} cites no earlier utterance_spoken`,
      );
    }
    if (e.actor_id !== null && !residents.has(e.actor_id))
      throw new RuleError(
        "entity_refs",
        `actor_id ${JSON.stringify(e.actor_id)} of ${e.event_id} is not a declared resident`,
      );
    for (const name of RESIDENT_REF_FIELDS) {
      const v = str(p[name]);
      if (v !== null && !residents.has(v))
        throw new RuleError(
          "entity_refs",
          `${name} ${JSON.stringify(v)} of ${e.event_id} is not a declared resident`,
        );
    }
    const tree = str(p["tree_id"]);
    if (tree !== null && !treeIds.has(tree))
      throw new RuleError(
        "entity_refs",
        `tree_id ${JSON.stringify(tree)} of ${e.event_id} is not a fruit tree`,
      );
    for (const name of ["from", "to", "position"]) {
      const c = p[name];
      if (typeof c === "object" && c !== null && !inMap(c as Coord, b.map.width, b.map.height))
        throw new RuleError("coords", `${name} of ${e.event_id} is outside the map`);
    }
  });
}

// backend: ReplayBundle._check_frames
function checkFrames(b: ReplayBundle): void {
  const { width: w, height: h } = b.map;
  const declared = new Set(b.residents.map((r) => r.id));
  const fTiles = new Set<string>();
  b.map.rows.forEach((row, y) =>
    [...row].forEach((ch, x) => {
      if (ch === "F") fTiles.add(`${x},${y}`);
    }),
  );
  const treeKey = (t: { id: string; position: Coord }) => `${t.id}@${t.position.x},${t.position.y}`;
  const firstTrees = b.frames[0]?.fruit_trees ?? [];
  const base = firstTrees.map(treeKey);
  const basePositions = firstTrees.map((t) => `${t.position.x},${t.position.y}`);
  if (new Set(basePositions).size !== basePositions.length)
    throw new RuleError("trees", "two fruit trees share a position");
  if (basePositions.length !== fTiles.size || !basePositions.every((p) => fTiles.has(p)))
    throw new RuleError("trees", "fruit trees must correspond one-to-one to F tiles");
  const max = b.condition_bounds.max_value;
  for (const f of b.frames) {
    const ids = new Set(f.residents.map((r) => r.id));
    const missing = [...declared].filter((id) => !ids.has(id)).sort(compareUtf8);
    const extra = [...ids].filter((id) => !declared.has(id)).sort(compareUtf8);
    if (missing.length > 0 || extra.length > 0)
      throw new RuleError(
        "frame_residents",
        `frame ${f.tick} resident ids differ from declared (missing ${JSON.stringify(missing)}, undeclared ${JSON.stringify(extra)})`,
      );
    for (const r of f.residents) {
      if (!inMap(r.position, w, h))
        throw new RuleError("coords", `resident ${r.id} outside the map at ${f.tick}`);
      for (const name of ["satiety", "hydration", "stamina", "health"] as const) {
        if (r[name] > max)
          throw new RuleError("conditions", `${name} of ${r.id} exceeds ${max} at ${f.tick}`);
      }
    }
    const trees = f.fruit_trees.map(treeKey);
    if (trees.length !== base.length || trees.some((t, i) => t !== base[i]))
      throw new RuleError("trees", `frame ${f.tick} fruit tree ids or positions differ from tick 0`);
    for (const g of f.ground_fruit)
      if (!inMap(g.position, w, h))
        throw new RuleError("coords", `ground fruit outside the map at ${f.tick}`);
    if (f.ground_canteen !== null && !inMap(f.ground_canteen.position, w, h))
      throw new RuleError("coords", `ground canteen outside the map at ${f.tick}`);
    for (const c of f.corpses) {
      if (!declared.has(c.resident_id))
        throw new RuleError(
          "entity_refs",
          `corpse ${c.id} cites undeclared resident ${JSON.stringify(c.resident_id)}`,
        );
      if (!inMap(c.position, w, h))
        throw new RuleError("coords", `corpse ${c.id} outside the map at ${f.tick}`);
    }
  }
}

// backend: ReplayBundle._check_namespaces
function checkNamespaces(b: ReplayBundle): void {
  const residents = new Set(b.residents.map((r) => r.id));
  const trees = new Set((b.frames[0]?.fruit_trees ?? []).map((t) => t.id));
  const corpses = new Set(b.frames.flatMap((f) => f.corpses.map((c) => c.id)));
  const canteens = new Set<string>();
  for (const e of b.events) {
    const p = payloadOf(e);
    if (e.type === "corpse_created") corpses.add(String(p["corpse_id"]));
    const canteen = str(p["canteen_id"]);
    if (canteen !== null) canteens.add(canteen);
  }
  const pairs: [Set<string>, Set<string>, string][] = [
    [residents, trees, "resident/fruit tree"],
    [residents, corpses, "resident/corpse"],
    [trees, corpses, "fruit tree/corpse"],
    [residents, canteens, "resident/canteen"],
    [trees, canteens, "fruit tree/canteen"],
    [corpses, canteens, "corpse/canteen"],
  ];
  for (const [a, c, label] of pairs) {
    const clash = [...a].filter((id) => c.has(id)).sort(compareUtf8);
    if (clash.length > 0)
      throw new RuleError("namespaces", `${label} ids collide: ${JSON.stringify(clash)}`);
  }
}

/** Runs every backend cross-field rule in backend order. Returns null when all hold. */
export function checkCrossField(b: ReplayBundle): ReplayError | null {
  try {
    checkClock(b);
    checkMap(b);
    checkFrameSorting(b);
    checkMapHash(b);
    checkDeclaredResidents(b);
    checkFrameTicks(b);
    checkEvents(b);
    checkEventRanges(b);
    checkEventReferences(b);
    checkFrames(b);
    checkNamespaces(b);
    return null;
  } catch (err) {
    if (err instanceof RuleError)
      return { kind: "cross_field", rule: err.rule, message: err.message, details: [err.message] };
    throw err;
  }
}
