// View-model for the resident panel: raw frame values, bars from condition_bounds, and the
// change from the previous recorded tick. Nothing is computed beyond differences of two frames.
import { frameAt } from "../replay/store.ts";
import type { ReplayBundle, ResidentFrame } from "../replay/types.ts";

export const CONDITIONS = ["satiety", "hydration", "stamina", "health"] as const;
export type ConditionName = (typeof CONDITIONS)[number];

export interface ConditionRow {
  name: ConditionName;
  value: number;
  /** Bar width 0..1 from condition_bounds (never a hard-coded maximum). */
  fraction: number;
  /** Change from the previous tick; null at tick 0. */
  delta: number | null;
}

export interface ResidentView {
  id: string;
  displayName: string;
  position: { x: number; y: number };
  alive: boolean;
  conditions: ConditionRow[];
  fruitCount: number;
  /** null = not holding the canteen. */
  canteenServings: number | null;
  action: {
    intentId: string;
    actionType: string;
    tickStarted: number;
    remainingTicks: number | null;
  } | null;
  /** Tiles moved since the previous tick; null at tick 0. */
  moved: { dx: number; dy: number } | null;
  fruitDelta: number | null;
  canteenDelta: number | null;
}

function find(frameResidents: ResidentFrame[], id: string): ResidentFrame | undefined {
  return frameResidents.find((r) => r.id === id);
}

export function residentView(bundle: ReplayBundle, tick: number, id: string): ResidentView | null {
  const now = find(frameAt(bundle, tick).residents, id);
  if (now === undefined) return null;
  const before = tick > 0 ? find(frameAt(bundle, tick - 1).residents, id) : undefined;
  const { min_value: min, max_value: max } = bundle.condition_bounds;
  const span = max - min;
  const label = bundle.residents.find((r) => r.id === id)?.display_name ?? id;
  return {
    id,
    displayName: label,
    position: { x: now.position.x, y: now.position.y },
    alive: now.alive,
    conditions: CONDITIONS.map((name) => ({
      name,
      value: now[name],
      fraction: Math.min(1, Math.max(0, (now[name] - min) / span)),
      delta: before === undefined ? null : now[name] - before[name],
    })),
    fruitCount: now.fruit_count,
    canteenServings: now.canteen_servings,
    action:
      now.active_action === null
        ? null
        : {
            intentId: now.active_action.intent_id,
            actionType: now.active_action.action_type,
            tickStarted: now.active_action.tick_started,
            remainingTicks: now.active_action.remaining_ticks,
          },
    moved:
      before === undefined
        ? null
        : { dx: now.position.x - before.position.x, dy: now.position.y - before.position.y },
    fruitDelta: before === undefined ? null : now.fruit_count - before.fruit_count,
    canteenDelta:
      before === undefined ? null : (now.canteen_servings ?? 0) - (before.canteen_servings ?? 0),
  };
}
