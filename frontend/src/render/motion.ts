// Presentation-only motion: where to draw a resident between two recorded frames, and which
// way it faces. Everything is a function of an immutable bundle: recorded frames and
// `resident_moved` events up to the current tick. Nothing is written back, nothing is
// predicted, and at progress 1 the result is exactly the recorded position of the current frame.
import { eventsOfFrame, frameAt } from "../replay/store.ts";
import type { ReplayBundle } from "../replay/types.ts";
import type { Facing } from "./assets/residentArt.ts";

export interface TilePoint {
  x: number;
  y: number;
}

export interface Pose {
  /** Draw position in tile units. Equal to the recorded tile when `progress` is 1. */
  x: number;
  y: number;
  facing: Facing;
  /** True only while the sprite is between two recorded tiles. */
  moving: boolean;
}

const same = (a: TilePoint, b: TilePoint): boolean => a.x === b.x && a.y === b.y;

function positionOf(bundle: ReplayBundle, tick: number, residentId: string): TilePoint | null {
  const r = frameAt(bundle, tick).residents.find((f) => f.id === residentId);
  return r === undefined ? null : { x: r.position.x, y: r.position.y };
}

/**
 * The tiles a resident passed through during `tick`, from its position in the previous frame
 * to its position in this frame.
 *
 * The world records one `resident_moved` event per entered tile, so the path is taken from
 * those events when they chain exactly from the previous recorded position to the current
 * one (this includes a recorded walk that returns to its starting tile). Otherwise no route
 * is invented: if the two recorded tiles are adjacent the move is a straight slide between
 * them, and in every other case it is a jump (a one-point path).
 */
export function pathInto(bundle: ReplayBundle, tick: number, residentId: string): TilePoint[] {
  const now = positionOf(bundle, tick, residentId);
  if (now === null) return [];
  const before = tick > 0 ? positionOf(bundle, tick - 1, residentId) : null;
  if (before === null) return [now];
  const path: TilePoint[] = [before];
  let chained = true;
  for (const e of eventsOfFrame(bundle, frameAt(bundle, tick))) {
    if (e.type !== "resident_moved" || e.actor_id !== residentId) continue;
    const { from, to } = e.payload as unknown as { from: TilePoint; to: TilePoint };
    if (!same(from, path[path.length - 1] as TilePoint)) {
      chained = false;
      break;
    }
    path.push({ x: to.x, y: to.y });
  }
  if (chained && path.length > 1 && same(path[path.length - 1] as TilePoint, now)) return path;
  if (same(before, now)) return [now];
  const adjacent = Math.max(Math.abs(now.x - before.x), Math.abs(now.y - before.y)) === 1;
  return adjacent ? [before, now] : [now];
}

/** Horizontal movement wins on diagonals, because the side views read best. */
export function facingOf(dx: number, dy: number): Facing | null {
  if (dx > 0) return "right";
  if (dx < 0) return "left";
  if (dy > 0) return "down";
  if (dy < 0) return "up";
  return null;
}

const facingCache = new WeakMap<ReplayBundle, Map<string, Facing[]>>();

/**
 * Facing at rest for every tick: the direction of the last recorded step up to that tick, or
 * "down" before the resident has moved. The value for a tick depends only on frames and
 * events up to that tick. Memoised per bundle object: a loaded bundle is never mutated, so the
 * cache cannot change a result (a bundle edited in place would need a fresh object).
 */
function restFacings(bundle: ReplayBundle, residentId: string): Facing[] {
  let perBundle = facingCache.get(bundle);
  if (perBundle === undefined) {
    perBundle = new Map();
    facingCache.set(bundle, perBundle);
  }
  let facings = perBundle.get(residentId);
  if (facings === undefined) {
    facings = [];
    let current: Facing = "down";
    for (let tick = 0; tick < bundle.frames.length; tick++) {
      const path = pathInto(bundle, tick, residentId);
      if (path.length > 1) {
        const a = path[path.length - 2] as TilePoint;
        const b = path[path.length - 1] as TilePoint;
        current = facingOf(b.x - a.x, b.y - a.y) ?? current;
      }
      facings.push(current);
    }
    perBundle.set(residentId, facings);
  }
  return facings;
}

export function facingAt(bundle: ReplayBundle, tick: number, residentId: string): Facing {
  return restFacings(bundle, residentId)[tick] ?? "down";
}

/**
 * Where to draw a resident `progress` (0..1) of the way through the display beat of `tick`.
 * At 1, or whenever the resident did not move, this is the recorded tile itself.
 */
export function poseAt(bundle: ReplayBundle, tick: number, residentId: string, progress = 1): Pose | null {
  const now = positionOf(bundle, tick, residentId);
  if (now === null) return null;
  const rest = facingAt(bundle, tick, residentId);
  const p = Number.isFinite(progress) ? Math.min(1, Math.max(0, progress)) : 1;
  if (p >= 1) return { x: now.x, y: now.y, facing: rest, moving: false };
  const path = pathInto(bundle, tick, residentId);
  if (path.length < 2) return { x: now.x, y: now.y, facing: rest, moving: false };
  const along = p * (path.length - 1);
  const i = Math.min(path.length - 2, Math.floor(along));
  const t = along - i;
  const a = path[i] as TilePoint;
  const b = path[i + 1] as TilePoint;
  return {
    x: a.x + (b.x - a.x) * t,
    y: a.y + (b.y - a.y) * t,
    facing: facingOf(b.x - a.x, b.y - a.y) ?? rest,
    moving: true,
  };
}
