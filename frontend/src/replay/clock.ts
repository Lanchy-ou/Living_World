// Display-only clock arithmetic (replay-frontend §4.2, World Rules §1.3). Integers in, integers out.
import type { ReplayBundle } from "./types.ts";

type Clock = ReplayBundle["clock"];

export interface ClockReadout {
  day: number;
  hh: number;
  mm: number;
  text: string;
}

export function clockAt(tick: number, clock: Clock): ClockReadout {
  const elapsedMinutes = tick * clock.tick_minutes;
  const ofDay = (clock.start_hour * 60 + elapsedMinutes) % 1440;
  const hh = Math.floor(ofDay / 60);
  const mm = ofDay % 60;
  const day = 1 + Math.floor(elapsedMinutes / 1440);
  const pad = (n: number) => String(n).padStart(2, "0");
  return { day, hh, mm, text: `Day ${day} ${pad(hh)}:${pad(mm)}` };
}

/** Daylight is [day_start_hour, day_end_hour); the end hour itself is night. */
export function isNight(tick: number, clock: Clock): boolean {
  const ofDay = (clock.start_hour * 60 + tick * clock.tick_minutes) % 1440;
  return !(clock.day_start_hour * 60 <= ofDay && ofDay < clock.day_end_hour * 60);
}
