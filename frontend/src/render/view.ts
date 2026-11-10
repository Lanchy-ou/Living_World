// Layout for the current view, including the optional follow-selected-resident camera.
import type { Camera } from "../replay/store.ts";
import type { ReplayBundle } from "../replay/types.ts";
import { layoutFor, panToCentre } from "./camera.ts";
import type { Layout, Viewport } from "./camera.ts";
import { poseAt } from "./motion.ts";

/**
 * Follow is opt-in. When it is on, the camera centres the selected resident's draw position
 * (which is the recorded tile at rest). Selecting a resident alone never changes the camera.
 */
export function viewLayout(
  bundle: ReplayBundle,
  tick: number,
  size: Viewport,
  camera: Camera,
  selectedResidentId: string | null,
  progress = 1,
): Layout {
  let cam = camera;
  if (camera.follow && selectedResidentId !== null) {
    const pose = poseAt(bundle, tick, selectedResidentId, progress);
    if (pose !== null) {
      const tile = layoutFor(size, bundle.map, camera).tile;
      const [panX, panY] = panToCentre(bundle.map, tile, pose.x, pose.y);
      cam = { ...camera, panX, panY };
    }
  }
  return layoutFor(size, bundle.map, cam);
}
