import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { frameAt } from "../replay/store.ts";
import type { ReplayStore } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { dragPan, screenToTile } from "./camera.ts";
import type { Layout } from "./camera.ts";
import { computeSprites, drawFrame } from "./drawFrame.ts";
import { viewLayout } from "./view.ts";

interface Size {
  width: number;
  height: number;
}

export function MapCanvas({ store }: { store: ReplayStore }) {
  const state = useReplayState(store);
  const { bundle, currentTick, camera, selectedResidentId } = state;
  const wrapper = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [size, setSize] = useState<Size>({ width: 640, height: 480 });

  useEffect(() => {
    const el = wrapper.current;
    if (el === null) return;
    const observer = new ResizeObserver(() =>
      setSize({ width: Math.max(1, el.clientWidth), height: Math.max(1, el.clientHeight) }),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  function currentLayout(): Layout | null {
    if (bundle === null) return null;
    return viewLayout(bundle, currentTick, size, camera, selectedResidentId);
  }

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (el === null || !ctx || bundle === null) return;
    const dpr = window.devicePixelRatio || 1;
    el.width = Math.round(size.width * dpr);
    el.height = Math.round(size.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const layout = viewLayout(bundle, currentTick, size, camera, selectedResidentId);
    drawFrame(ctx, bundle, frameAt(bundle, currentTick), layout, size, { selectedResidentId });
  }, [bundle, currentTick, camera, selectedResidentId, size]);

  if (bundle === null) return <div className="map-empty">No replay loaded.</div>;

  function onPointerDown(e: ReactPointerEvent<HTMLCanvasElement>) {
    drag.current = { x: e.clientX, y: e.clientY };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e: ReactPointerEvent<HTMLCanvasElement>) {
    const start = drag.current;
    const layout = currentLayout();
    if (start === null || bundle === null || layout === null) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    if (Math.abs(dx) + Math.abs(dy) < 1) return;
    drag.current = { x: e.clientX, y: e.clientY };
    // Dragging only moves the camera, and stops following; entity positions never change.
    const cam = { ...camera, panX: layout.offsetX, panY: layout.offsetY };
    store.setCamera({ ...dragPan(size, bundle.map, cam, dx, dy), follow: false });
  }

  function onPointerUp(e: ReactPointerEvent<HTMLCanvasElement>) {
    const start = drag.current;
    drag.current = null;
    const layout = currentLayout();
    if (bundle === null || layout === null) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (start !== null && Math.abs(e.clientX - start.x) + Math.abs(e.clientY - start.y) < 3) {
      const tile = screenToTile(layout, e.clientX - rect.left, e.clientY - rect.top);
      const hit = computeSprites(bundle, frameAt(bundle, currentTick), layout).find(
        (s) => s.kind === "resident" && s.tileX === tile.x && s.tileY === tile.y,
      );
      if (hit !== undefined) store.selectResident(hit.id);
    }
  }

  return (
    <div className="map-wrap" ref={wrapper}>
      <canvas
        ref={canvas}
        style={{ width: size.width, height: size.height }}
        aria-label="Island map"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
    </div>
  );
}
