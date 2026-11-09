import { useEffect } from "react";
import { clockAt } from "../replay/clock.ts";
import { SPEEDS, lastTick } from "../replay/store.ts";
import type { ReplayStore, Speed } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";

export function PlaybackBar({ store }: { store: ReplayStore }) {
  const state = useReplayState(store);
  const { bundle, currentTick, playing, speed } = state;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => store.tickPlayback(), 1000 / speed);
    return () => window.clearInterval(id);
  }, [playing, speed, store]);

  if (bundle === null) return null;
  const end = lastTick(bundle);
  const clock = clockAt(currentTick, bundle.clock);

  return (
    <section className="playback" aria-label="Playback">
      <button type="button" onClick={() => store.seek(0)} disabled={currentTick === 0}>
        |&lt;
      </button>
      <button type="button" onClick={() => store.step(-1)} disabled={currentTick === 0}>
        Step back
      </button>
      <button
        type="button"
        onClick={() => (playing ? store.pause() : store.play())}
        disabled={!playing && currentTick >= end}
      >
        {playing ? "Pause" : "Play"}
      </button>
      <button type="button" onClick={() => store.step(1)} disabled={currentTick >= end}>
        Step forward
      </button>
      <button type="button" onClick={() => store.seek(end)} disabled={currentTick >= end}>
        &gt;|
      </button>
      <input
        aria-label="Seek slider"
        type="range"
        min={0}
        max={end}
        value={currentTick}
        onChange={(e) => store.seek(Number(e.target.value))}
      />
      <label>
        Tick{" "}
        <input
          aria-label="Seek to tick"
          type="number"
          min={0}
          max={end}
          value={currentTick}
          onChange={(e) => store.seek(Number(e.target.value))}
        />{" "}
        / {end}
      </label>
      <span className="clock" aria-label="Clock">
        Tick {currentTick} · {clock.text}
      </span>
      <label>
        Speed{" "}
        <select
          value={speed}
          onChange={(e) => store.setSpeed(Number(e.target.value) as Speed)}
          aria-label="Speed in ticks per second"
        >
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s} tick/s
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
