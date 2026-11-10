// ReplayStore: the only mutable viewer state. It holds a validated, immutable bundle plus
// local view state (tick, selection, filters, camera). It never simulates: seeking and stepping
// only change which recorded frame is current.
import type { DisplayFrame, ReplayBundle, WorldEvent } from "./types.ts";

export const SPEEDS = [1, 2, 4, 8, 16] as const;
export type Speed = (typeof SPEEDS)[number];
/** Zoom 1 is "view entire island" (fit to view). The upper limit depends on the viewport. */
export const FIT_ZOOM = 1;

export interface Camera {
  /** Multiplier over the fit-to-view tile size, >= 1. Clamped by the camera layout. */
  zoom: number;
  /** Screen-pixel offset of the map centre from the viewport centre; (0, 0) is centred. */
  panX: number;
  panY: number;
  /** Optional: keep the selected resident centred. Off unless the user turns it on. */
  follow: boolean;
}

export interface Filters {
  /** Resident ID, or null for all events. */
  residentId: string | null;
  failuresOnly: boolean;
}

export interface ReplayState {
  bundle: ReplayBundle | null;
  fileName: string | null;
  currentTick: number;
  playing: boolean;
  speed: Speed;
  selectedResidentId: string | null;
  selectedEventId: string | null;
  filters: Filters;
  camera: Camera;
}

const INITIAL_CAMERA: Camera = { zoom: 1, panX: 0, panY: 0, follow: false };

export function initialState(): ReplayState {
  return {
    bundle: null,
    fileName: null,
    currentTick: 0,
    playing: false,
    speed: 1,
    selectedResidentId: null,
    selectedEventId: null,
    filters: { residentId: null, failuresOnly: false },
    camera: INITIAL_CAMERA,
  };
}

/** Frames are contiguous from tick 0 (validated), so a tick is its own array index. */
export function frameAt(bundle: ReplayBundle, tick: number): DisplayFrame {
  const frame = bundle.frames[tick];
  if (frame === undefined) throw new RangeError(`no frame for tick ${tick}`);
  return frame;
}

export function lastTick(bundle: ReplayBundle): number {
  return bundle.frames.length - 1;
}

export function eventsOfFrame(bundle: ReplayBundle, frame: DisplayFrame): WorldEvent[] {
  const { first_index: first, count } = frame.event_range;
  return bundle.events.slice(first, first + count);
}

export function clampTick(bundle: ReplayBundle, tick: number): number {
  if (!Number.isFinite(tick)) return 0;
  return Math.min(Math.max(Math.trunc(tick), 0), lastTick(bundle));
}

type Listener = () => void;

export class ReplayStore {
  private state: ReplayState = initialState();
  private followPan: { panX: number; panY: number } | null = null;
  private readonly listeners = new Set<Listener>();

  getState = (): ReplayState => this.state;

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private set(patch: Partial<ReplayState>): void {
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l();
  }

  /** A newly loaded bundle starts at tick 0, paused, with the whole island in view and nobody selected. */
  load(bundle: ReplayBundle, fileName: string | null = null): void {
    this.state = {
      ...initialState(),
      bundle,
      fileName,
      speed: this.state.speed,
    };
    this.followPan = null;
    for (const l of this.listeners) l();
  }

  unload(): void {
    this.set({ ...initialState(), speed: this.state.speed });
  }

  seek(tick: number): void {
    const { bundle } = this.state;
    if (bundle === null) return;
    const t = clampTick(bundle, tick);
    this.set({ currentTick: t, playing: this.state.playing && t < lastTick(bundle) });
  }

  /** Exactly one tick; stops at both ends. */
  step(delta: 1 | -1): void {
    this.seek(this.state.currentTick + delta);
  }

  play(): void {
    const { bundle } = this.state;
    if (bundle === null || this.state.currentTick >= lastTick(bundle)) return;
    this.set({ playing: true });
  }

  pause(): void {
    this.set({ playing: false });
  }

  /** One playback beat: advances one recorded frame and pauses at the end. */
  tickPlayback(): void {
    if (this.state.playing) this.step(1);
  }

  setSpeed(speed: Speed): void {
    this.set({ speed });
  }

  /**
   * Selecting only changes the selection: it never moves the camera and never pauses playback.
   * Follow is tied to the resident it was turned on for, so changing or clearing the selection
   * turns it off and the view stays where it is.
   */
  selectResident(id: string | null): void {
    if (id === this.state.selectedResidentId) return;
    if (this.state.camera.follow) {
      this.set({ selectedResidentId: id, camera: this.withoutFollow(this.state.camera) });
    } else {
      this.set({ selectedResidentId: id });
    }
  }

  /**
   * Display bookkeeping from the map: the pan the follow camera is showing right now. It is
   * not state and notifies nobody; it only lets the view stay put when follow is turned off.
   */
  noteFollowPan(panX: number, panY: number): void {
    this.followPan = { panX, panY };
  }

  private withoutFollow(camera: Camera): Camera {
    return { ...camera, ...(this.followPan ?? {}), follow: false };
  }

  setFilters(patch: Partial<Filters>): void {
    this.set({ filters: { ...this.state.filters, ...patch } });
  }

  /** Clicking an event seeks to its tick and expands its raw JSON. */
  selectEvent(event: WorldEvent | null): void {
    if (event === null) {
      this.set({ selectedEventId: null });
      return;
    }
    this.set({ selectedEventId: event.event_id });
    this.seek(event.tick);
  }

  setCamera(patch: Partial<Camera>): void {
    const current = this.state.camera;
    // Turning follow off without giving a pan keeps the view the follow camera was showing.
    const base =
      current.follow && patch.follow === false && patch.panX === undefined && patch.panY === undefined
        ? this.withoutFollow(current)
        : current;
    if (patch.follow === true && !current.follow) this.followPan = null;
    this.set({ camera: { ...base, ...patch } });
  }
}
