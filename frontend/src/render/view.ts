// Layout for the current view, including the optional follow-selected-resident camera.
import { frameAt } from "../replay/store.ts";
import type { Camera } from "../replay/store.ts";
import type { ReplayBundle } from "../replay/types.ts";
import { layoutFor, panToCentre } from "./camera.ts";
import type { Layout, Viewport } from "./camera.ts";

export function viewLayout(
  bundle: ReplayBundle,
  tick: number,
  size: Viewport,
  camera: Camera,
  selectedResidentId: string | null,
): Layout {
  let cam = camera;
  if (camera.follow && selectedResidentId !== null) {
    const resident = frameAt(bundle, tick).residents.find((r) => r.id === selectedResidentId);
    if (resident !== undefined) {
      const tile = layoutFor(size, bundle.map, camera).tile;
      const [panX, panY] = panToCentre(size, tile, resident.position.x, resident.position.y);
      cam = { ...camera, panX, panY };
    }
  }
  return layoutFor(size, bundle.map, cam);
}
