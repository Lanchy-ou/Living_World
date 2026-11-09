// ReplayStore: the only mutable viewer state. It holds a validated, immutable bundle plus
// local view state (tick, selection, filters, camera). It never simulates: seeking and stepping
// only change which recorded frame is current.
import type { DisplayFrame, ReplayBundle, WorldEvent } from "./types.ts";

export const SPEEDS = [1, 2, 4, 8, 16] as const;
export type Speed = (typeof SPEEDS)[number];
export const ZOOMS = [1, 2, 4] as const;
export type Zoom = (typeof ZOOMS)[number];

export interface Camera {
  zoom: Zoom;
  /** Pan offset in screen pixels, applied after the fit-to-view layout. */
  panX: number;
  panY: number;
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

  /** A newly loaded bundle starts at tick 0, paused. Residents are declared, so select the first. */
  load(bundle: ReplayBundle, fileName: string | null = null): void {
    this.state = {
      ...initialState(),
      bundle,
      fileName,
      selectedResidentId: bundle.residents[0]?.id ?? null,
      speed: this.state.speed,
    };
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

  selectResident(id: string | null): void {
    this.set({ selectedResidentId: id });
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
    this.set({ camera: { ...this.state.camera, ...patch } });
  }
}
