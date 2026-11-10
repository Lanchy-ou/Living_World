import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import { CameraControls } from "../controls/CameraControls.tsx";
import { FIT_ZOOM, frameAt } from "../replay/store.ts";
import type { ReplayState, ReplayStore } from "../replay/store.ts";
import { buildTerrainFrames, spriteImages } from "./atlas.ts";
import { ZOOM_STEP, dragPan, panOf, zoomAt } from "./camera.ts";
import type { Layout, Viewport } from "./camera.ts";
import { drawFrame } from "./drawFrame.ts";
import { buildScene, residentAt } from "./scene.ts";
import { viewLayout } from "./view.ts";

/** Duration of the slide after a single manual step, in milliseconds. */
const STEP_TWEEN_MS = 160;
/** The two ambient terrain frames alternate at this period. */
const AMBIENT_MS = 900;
const CLICK_SLOP_PX = 4;

interface PointerInfo {
  x: number;
  y: number;
}

/**
 * The island map. It draws the current recorded frame and turns pointer input into camera
 * changes and resident selection. The only local state is display timing (how far through the
 * current beat the walk animation is); nothing here is written to the store except the camera
 * and the selection.
 */
export function MapCanvas({ store }: { store: ReplayStore }) {
  // Re-render only when the bundle changes; per-tick drawing happens in the animation loop.
  const bundle = useSyncExternalStore(store.subscribe, () => store.getState().bundle);
  const wrapper = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const size = useRef<Viewport>({ width: 1, height: 1 });
  const progress = useRef(1);
  const pointers = useRef(new Map<number, PointerInfo>());
  const gesture = useRef<{ startX: number; startY: number; moved: boolean; pinch: number | null } | null>(null);

  const terrain = useMemo(() => (bundle === null ? null : buildTerrainFrames(bundle.map)), [bundle]);

  useEffect(() => {
    const el = canvas.current;
    const wrap = wrapper.current;
    const ctx = el?.getContext("2d") ?? null;
    if (el === null || wrap === null || ctx === null || terrain === null) return;

    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let raf = 0;
    let lastKey = "";
    let shownBundle: ReplayState["bundle"] = null;
    let shownTick = -1;
    let tween: { start: number; duration: number } | null = null;

    const measure = () => {
      const dpr = window.devicePixelRatio || 1;
      size.current = { width: Math.max(1, wrap.clientWidth), height: Math.max(1, wrap.clientHeight) };
      el.width = Math.round(size.current.width * dpr);
      el.height = Math.round(size.current.height * dpr);
      lastKey = "";
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(wrap);

    const paint = (now: number) => {
      raf = requestAnimationFrame(paint);
      const state = store.getState();
      const b = state.bundle;
      if (b === null) return;
      if (b !== shownBundle || state.currentTick !== shownTick) {
        // Slide only for a single step forward. Seeking and stepping back show the frame at once.
        const stepped = b === shownBundle && state.currentTick === shownTick + 1;
        tween =
          stepped && !reducedMotion
            ? { start: now, duration: state.playing ? 1000 / state.speed : STEP_TWEEN_MS }
            : null;
        shownBundle = b;
        shownTick = state.currentTick;
      }
      if (tween !== null && !state.playing && tween.duration > STEP_TWEEN_MS) {
        // Playback was paused mid-slide: finish the slide quickly instead of over a full beat.
        const done = Math.min(1, Math.max(0, (now - tween.start) / tween.duration));
        tween = { start: now - done * STEP_TWEEN_MS, duration: STEP_TWEEN_MS };
      }
      let p = 1;
      if (tween !== null) {
        p = Math.min(1, Math.max(0, (now - tween.start) / tween.duration));
        if (p >= 1) tween = null;
      }
      progress.current = p;
      const phase = reducedMotion ? 0 : Math.floor(now / AMBIENT_MS) % 2;
      const dpr = window.devicePixelRatio || 1;
      const { camera, selectedResidentId, currentTick } = state;
      const view = size.current;
      const key = [
        currentTick,
        p,
        phase,
        camera.zoom,
        camera.panX,
        camera.panY,
        camera.follow,
        selectedResidentId,
        view.width,
        view.height,
        dpr,
      ].join("|");
      if (key === lastKey) return;
      lastKey = key;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const layout = viewLayout(b, currentTick, view, camera, selectedResidentId, p);
      if (camera.follow && selectedResidentId !== null) {
        // Remember where the follow camera is, so turning follow off leaves the view in place.
        const pan = panOf(view, b.map, layout);
        store.noteFollowPan(pan.panX, pan.panY);
      }
      drawFrame(ctx, b, frameAt(b, currentTick), layout, view, {
        selectedResidentId,
        progress: p,
        images: spriteImages,
        terrain: terrain.frames[phase as 0 | 1],
        pixelRatio: dpr,
      });
    };
    raf = requestAnimationFrame(paint);

    // Wheel zoom keeps the point under the cursor in place. Needs a non-passive listener.
    const onWheel = (e: WheelEvent) => {
      const state = store.getState();
      if (state.bundle === null) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      const factor = Math.min(2, Math.max(0.5, Math.exp(-delta * 0.0016)));
      const layout = viewLayout(
        state.bundle,
        state.currentTick,
        size.current,
        state.camera,
        state.selectedResidentId,
        progress.current,
      );
      const effective = { ...state.camera, ...panOf(size.current, state.bundle.map, layout) };
      store.setCamera(
        zoomAt(size.current, state.bundle.map, effective, factor, e.clientX - rect.left, e.clientY - rect.top),
      );
    };
    el.addEventListener("wheel", onWheel, { passive: false });

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      el.removeEventListener("wheel", onWheel);
    };
  }, [store, terrain]);

  if (bundle === null) return null;

  /** The layout as currently drawn, and the camera whose pan equals it (also while following). */
  function current(): { state: ReplayState; layout: Layout; camera: ReplayState["camera"] } | null {
    const state = store.getState();
    if (state.bundle === null) return null;
    const layout = viewLayout(
      state.bundle,
      state.currentTick,
      size.current,
      state.camera,
      state.selectedResidentId,
      progress.current,
    );
    return { state, layout, camera: { ...state.camera, ...panOf(size.current, state.bundle.map, layout) } };
  }

  function localPoint(e: { clientX: number; clientY: number }): PointerInfo {
    const rect = canvas.current?.getBoundingClientRect();
    return { x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) };
  }

  function hit(point: PointerInfo): string | null {
    const now = current();
    if (now === null || now.state.bundle === null) return null;
    const { bundle: b, currentTick, selectedResidentId } = now.state;
    const scene = buildScene(b, frameAt(b, currentTick), now.layout, {
      progress: progress.current,
      selectedResidentId,
    });
    return residentAt(scene, point.x, point.y);
  }

  function pinchDistance(): number | null {
    const [a, b] = [...pointers.current.values()];
    return a === undefined || b === undefined ? null : Math.hypot(a.x - b.x, a.y - b.y);
  }

  function onPointerDown(e: ReactPointerEvent<HTMLCanvasElement>) {
    const point = localPoint(e);
    pointers.current.set(e.pointerId, point);
    e.currentTarget.setPointerCapture(e.pointerId);
    if (pointers.current.size === 1) {
      gesture.current = { startX: point.x, startY: point.y, moved: false, pinch: null };
    } else if (gesture.current !== null) {
      gesture.current.moved = true;
      gesture.current.pinch = pinchDistance();
    }
    e.currentTarget.style.cursor = "grabbing";
  }

  function onPointerMove(e: ReactPointerEvent<HTMLCanvasElement>) {
    const point = localPoint(e);
    const previous = pointers.current.get(e.pointerId);
    const g = gesture.current;
    if (previous === undefined || g === null) {
      // Not dragging: show that a resident under the pointer can be clicked.
      e.currentTarget.style.cursor = hit(point) === null ? "grab" : "pointer";
      return;
    }
    pointers.current.set(e.pointerId, point);
    const now = current();
    if (now === null || now.state.bundle === null) return;
    const map = now.state.bundle.map;
    if (pointers.current.size >= 2) {
      // Two pointers: pinch to zoom around their midpoint.
      const distance = pinchDistance();
      const [a, b] = [...pointers.current.values()] as [PointerInfo, PointerInfo];
      if (distance !== null && g.pinch !== null && g.pinch > 0 && distance > 0) {
        store.setCamera({
          ...zoomAt(size.current, map, now.camera, distance / g.pinch, (a.x + b.x) / 2, (a.y + b.y) / 2),
          follow: false,
        });
      }
      g.pinch = distance;
      return;
    }
    const dx = point.x - previous.x;
    const dy = point.y - previous.y;
    if (Math.hypot(point.x - g.startX, point.y - g.startY) > CLICK_SLOP_PX) g.moved = true;
    if (!g.moved || (dx === 0 && dy === 0)) return;
    // Dragging only moves the camera, and stops following; entity positions never change.
    store.setCamera({ ...dragPan(size.current, map, now.camera, dx, dy), follow: false });
  }

  function onPointerUp(e: ReactPointerEvent<HTMLCanvasElement>) {
    const point = localPoint(e);
    const g = gesture.current;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size > 0) {
      if (g !== null) g.pinch = null;
      return;
    }
    gesture.current = null;
    const target = hit(point);
    e.currentTarget.style.cursor = target === null ? "grab" : "pointer";
    // A click (not a drag) on a resident selects it. This never moves the camera or pauses.
    if (g !== null && !g.moved && e.type === "pointerup" && target !== null) {
      store.selectResident(target);
    }
  }

  function zoomAround(factor: number, point: PointerInfo | null) {
    const now = current();
    if (now === null || now.state.bundle === null) return;
    const at = point ?? { x: size.current.width / 2, y: size.current.height / 2 };
    store.setCamera(zoomAt(size.current, now.state.bundle.map, now.camera, factor, at.x, at.y));
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLCanvasElement>) {
    const now = current();
    if (now === null || now.state.bundle === null) return;
    const step = 48;
    const pan = (dx: number, dy: number) =>
      store.setCamera({ ...dragPan(size.current, now.state.bundle!.map, now.camera, dx, dy), follow: false });
    switch (e.key) {
      case "ArrowLeft":
        pan(step, 0);
        break;
      case "ArrowRight":
        pan(-step, 0);
        break;
      case "ArrowUp":
        pan(0, step);
        break;
      case "ArrowDown":
        pan(0, -step);
        break;
      case "+":
      case "=":
        zoomAround(ZOOM_STEP, null);
        break;
      case "-":
      case "_":
        zoomAround(1 / ZOOM_STEP, null);
        break;
      case "0":
        store.setCamera({ zoom: FIT_ZOOM, panX: 0, panY: 0, follow: false });
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  return (
    <div className="map-wrap" ref={wrapper}>
      <canvas
        ref={canvas}
        role="img"
        tabIndex={0}
        aria-label="Island map. Drag to pan, scroll or pinch to zoom, click a resident to inspect."
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={(e) => zoomAround(ZOOM_STEP, localPoint(e))}
        onKeyDown={onKeyDown}
      />
      <CameraControls
        onZoomIn={() => zoomAround(ZOOM_STEP, null)}
        onZoomOut={() => zoomAround(1 / ZOOM_STEP, null)}
        onFit={() => store.setCamera({ zoom: FIT_ZOOM, panX: 0, panY: 0, follow: false })}
      />
    </div>
  );
}
