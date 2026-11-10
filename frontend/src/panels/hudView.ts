// View-model for the global status line. Every value is read from the current recorded frame
// or is a plain count or sum of recorded values; nothing is predicted or derived from rules.
import { clockAt, isNight } from "../replay/clock.ts";
import { frameAt } from "../replay/store.ts";
import type { ReplayBundle } from "../replay/types.ts";

export interface CanteenWhere {
  /** Resident holding it, or null when it lies on the ground. */
  holderId: string | null;
  servings: number;
}

export interface HudView {
  tick: number;
  day: number;
  /** HH:MM from the bundle clock. */
  time: string;
  /** From the frozen daylight interval of the bundle clock. */
  night: boolean;
  alive: number;
  residents: number;
  /** Sum of `fruit_trees[].stock`. */
  treeFruit: number;
  trees: number;
  /** Sum of `ground_fruit[].quantity`. */
  groundFruit: number;
  canteens: CanteenWhere[];
}

export function hudView(bundle: ReplayBundle, tick: number): HudView {
  const frame = frameAt(bundle, tick);
  const clock = clockAt(tick, bundle.clock);
  const pad = (n: number) => String(n).padStart(2, "0");
  const canteens: CanteenWhere[] = frame.residents
    .filter((r) => r.canteen_servings !== null)
    .map((r) => ({ holderId: r.id, servings: r.canteen_servings as number }));
  if (frame.ground_canteen !== null) canteens.push({ holderId: null, servings: frame.ground_canteen.servings });
  return {
    tick,
    day: clock.day,
    time: `${pad(clock.hh)}:${pad(clock.mm)}`,
    night: isNight(tick, bundle.clock),
    alive: frame.residents.filter((r) => r.alive).length,
    residents: frame.residents.length,
    treeFruit: frame.fruit_trees.reduce((sum, t) => sum + t.stock, 0),
    trees: frame.fruit_trees.length,
    groundFruit: frame.ground_fruit.reduce((sum, g) => sum + g.quantity, 0),
    canteens,
  };
}
