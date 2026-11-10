import { useEffect } from "react";
import { clockAt } from "../replay/clock.ts";
import { SPEEDS, lastTick } from "../replay/store.ts";
import type { ReplayStore, Speed } from "../replay/store.ts";
import { useReplayState } from "../replay/useStore.ts";
import { Icon } from "./icons.tsx";

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
      <div className="transport">
        <button
          type="button"
          className="icon-button"
          aria-label="First tick"
          title="First tick"
          onClick={() => store.seek(0)}
          disabled={currentTick === 0}
        >
          <Icon name="first" />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label="Step back"
          title="Step back one tick"
          onClick={() => store.step(-1)}
          disabled={currentTick === 0}
        >
          <Icon name="stepBack" />
        </button>
        <button
          type="button"
          className="icon-button primary"
          aria-label={playing ? "Pause" : "Play"}
          title={playing ? "Pause" : "Play"}
          onClick={() => (playing ? store.pause() : store.play())}
          disabled={!playing && currentTick >= end}
        >
          <Icon name={playing ? "pause" : "play"} size={18} />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label="Step forward"
          title="Step forward one tick"
          onClick={() => store.step(1)}
          disabled={currentTick >= end}
        >
          <Icon name="stepForward" />
        </button>
        <button
          type="button"
          className="icon-button"
          aria-label="Last tick"
          title="Last tick"
          onClick={() => store.seek(end)}
          disabled={currentTick >= end}
        >
          <Icon name="last" />
        </button>
      </div>
      <span className="clock num" aria-label="Clock">
        Tick {currentTick} · {clock.text}
      </span>
      <input
        className="seek"
        aria-label="Seek slider"
        type="range"
        min={0}
        max={end}
        value={currentTick}
        onChange={(e) => store.seek(Number(e.target.value))}
      />
      <label className="tick-input">
        Tick{" "}
        <input
          aria-label="Seek to tick"
          type="number"
          min={0}
          max={end}
          value={currentTick}
          onChange={(e) => store.seek(Number(e.target.value))}
        />{" "}
        <span className="quiet">/ {end}</span>
      </label>
      <div className="speeds" role="group" aria-label="Speed in ticks per second">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            className={`speed${s === speed ? " active" : ""}`}
            aria-pressed={s === speed}
            title={`${s} tick${s === 1 ? "" : "s"} per second`}
            onClick={() => store.setSpeed(s as Speed)}
          >
            {s}×
          </button>
        ))}
      </div>
    </section>
  );
}
