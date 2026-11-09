// View-model for the resources panel: what the recorded frame contains, nothing guessed.
import type { DisplayFrame } from "../replay/types.ts";

export interface TileObjects {
  x: number;
  y: number;
  /** Every object on the tile, so several ground objects on one tile are all listed. */
  objects: string[];
}

export interface ResourcesView {
  trees: { id: string; x: number; y: number; stock: number }[];
  piles: { x: number; y: number; quantity: number }[];
  canteen: { x: number; y: number; servings: number } | null;
  corpses: { id: string; residentId: string; x: number; y: number }[];
  tiles: TileObjects[];
  empty: { trees: boolean; piles: boolean; canteen: boolean; corpses: boolean };
}

export function resourcesView(frame: DisplayFrame): ResourcesView {
  const trees = frame.fruit_trees.map((t) => ({
    id: t.id,
    x: t.position.x,
    y: t.position.y,
    stock: t.stock,
  }));
  const piles = frame.ground_fruit.map((g) => ({
    x: g.position.x,
    y: g.position.y,
    quantity: g.quantity,
  }));
  const canteen =
    frame.ground_canteen === null
      ? null
      : {
          x: frame.ground_canteen.position.x,
          y: frame.ground_canteen.position.y,
          servings: frame.ground_canteen.servings,
        };
  const corpses = frame.corpses.map((c) => ({
    id: c.id,
    residentId: c.resident_id,
    x: c.position.x,
    y: c.position.y,
  }));
  const byTile = new Map<string, TileObjects>();
  const add = (x: number, y: number, text: string) => {
    const key = `${x},${y}`;
    const entry = byTile.get(key) ?? { x, y, objects: [] };
    entry.objects.push(text);
    byTile.set(key, entry);
  };
  for (const t of trees) add(t.x, t.y, `fruit tree ${t.id}: stock ${t.stock}`);
  for (const p of piles) add(p.x, p.y, `ground fruit: ${p.quantity}`);
  if (canteen) add(canteen.x, canteen.y, `ground canteen: ${canteen.servings} servings`);
  for (const c of corpses) add(c.x, c.y, `corpse ${c.id}`);
  const tiles = [...byTile.values()].sort((a, b) => a.y - b.y || a.x - b.x);
  return {
    trees,
    piles,
    canteen,
    corpses,
    tiles,
    empty: {
      trees: trees.length === 0,
      piles: piles.length === 0,
      canteen: canteen === null,
      corpses: corpses.length === 0,
    },
  };
}
