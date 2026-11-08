# Living Island — P1 Offline Replay Frontend Spec v0.1

> **Approved v0.1 (2026-11-08).** Amendment A1 (agent interface) is applied by P1-01a and
> amendment A2 (replay) by P1-01b; until then `interface-contract-v0.1.md` and
> `world-rules-v0.1.md` are unchanged.

**Goal:** without any live server, load a replay produced by the backend and inspect the map,
residents, conditions, actions and failures tick by tick, to debug P1 world rules.

## 0. Confirmed direction and limits

| ID | Decision | Constraint |
|---|---|---|
| FE-01 | Replay first | The backend runs and exports a file; the browser plays it locally. P1 never controls a running world. |
| FE-02 | Replay + basic debugging | Map, residents, resources, conditions, events, timeline, play/pause/step/seek/speed, resident panel, current action, inventory, failure codes, per-resident event filter. |
| FE-03 | Read-only | No legality checks, no physiology or resource computation, no re-execution, no writes to saves. |
| FE-04 | Simple 2D Canvas | Coloured tiles and basic shapes. Art, 3D and live networking are not acceptance criteria. |

**Out of scope for P1:** WebSocket/live viewer, runtime parameter edits, dreams, character
editor, memory or LLM traces, per-resident perception view (P3 debug view), narrative.

## 1. Use cases

1. A developer runs the P1 CLI for 1,008 ticks and gets `runs/<run_id>/replay.json`.
2. They open it in the browser, see the static map, the three residents, their conditions and
   current actions, and can seek to any tick.
3. They select a resident and follow position, conditions, inventory and canteen over time.
4. They filter events by resident or by failure, read the authoritative failure code, and jump
   to the event's tick.
5. They watch a death: the resident stops, a corpse stays, items drop. The UI shows only what
   was recorded.

**Core experience:** see *when* a resident did *what*, and *which* state change or failure
resulted. The UI never invents causes.

## 2. Replay data

### 2.1 Two kinds of replay

| Kind | Owner | Purpose | P1 |
|---|---|---|---|
| Authoritative re-execution | backend `world`/`sim` + `RecordedPolicy` | Recompute and prove identical state and event bytes | backend integration tests |
| Visual replay | frontend | Draw recorded display frames; never runs rules | the viewer |

Events alone cannot reconstruct every drawable state (for example, `world_initialized` carries
only hashes). The viewer therefore reads **per-tick display frames**.

### 2.2 `ReplayBundle` (new read-only display DTO, contract amendment A2)

A single UTF-8 JSON file, exported by `persistence` after the run. It is separate from the save
format (JSON snapshot + JSONL events), and the two must never be mixed.

```text
ReplayBundle {
  replay_schema_version: "0.1",
  run_id: string, world_id: string, config_hash: string, map_hash: string,
  clock: { tick_minutes: integer, start_hour: integer,
           day_start_hour: integer, day_end_hour: integer },
  condition_bounds: { min_value: integer, max_value: integer }, // effective needs bounds
  map: { width: integer, height: integer, rows: array<string>,
         terrain_legend: array<{symbol: string, terrain: Terrain}> },   // from World Rules §1.2
  residents: array<{ id: string, display_name: string }>,              // labels only
  frames: array<DisplayFrame>,                                          // ticks 0..N, no gaps
  events: array<WorldEvent>                                             // sorted (tick, seq_in_tick)
}
DisplayFrame {
  tick: integer,
  residents: array<{
    id: string, position: Coord, alive: boolean,
    satiety: integer, hydration: integer, stamina: integer, health: integer,
    fruit_count: integer, canteen_servings: integer|null,   // null = not holding the canteen
    active_action: { intent_id: string, action_type: string,
                     tick_started: integer, remaining_ticks: integer|null } | null
  }>,
  fruit_trees: array<{ id: string, position: Coord, stock: integer }>,
  ground_fruit: array<{ position: Coord, quantity: integer }>,
  ground_canteen: { position: Coord, servings: integer } | null,
  corpses: array<{ id: string, resident_id: string, position: Coord }>,
  event_range: { first_index: integer, count: integer }     // slice of `events` for this tick
}
```

Rules:
- Frames cover tick 0 and every completed tick. A 1,008-tick run has **1,009 frames**. A tick
  with no events still has a frame.
- A frame is a backend projection of the committed state at that boundary. It is **not**
  `WorldState`: it has no RNG, no plans, no receipts and no private agent state. It may show
  exact conditions and all stocks, because the viewer is the developer's god view. It must
  **never be fed back to a resident** as perception.
- Static items (spring, cave, cue) are taken from the map and are not repeated in frames.
  `max_stock` and other configuration values are not repeated either.
- All physical numbers are integers; labels/IDs remain strings and alive remains boolean.
  Arrays use the frozen sort orders (Interface Contract §6.2): resident/tree/corpse labels
  and frame entries by ID, ground fruit by (y,x), frames by tick. Legend entries follow
  the World Rules §1.2 symbol order `~ . , W ^ S C F M`.
- `event_range` replaces per-frame ID lists: `events[first_index : first_index + count]` are
  exactly the events of that tick.
- `replay_schema_version` is separate from `save_schema_version`. Unknown versions are refused;
  there is no migration.

**Expected size** (estimate, to be measured in P1-09): frames ≈ 1 KB × 1,009; events in the tens
of thousands at a few hundred bytes each. So a few MB to ~10 MB. These are estimates only.
A size warning is not P1-08 acceptance: P1-09 measures files first and records an explicit
threshold before adding it. No implementer selects an unexplained warning limit early.

### 2.3 Validation

- The Pydantic ReplayBundle model in contract is the single source. `scripts/gen_types.py`
  generates TS types and a standalone `frontend/src/api/generated/replay.schema.json`
  rooted at ReplayBundle, with its referenced definitions included. Declare JSON Schema
  2020-12 and validate with its matching browser implementation (Ajv2020). Do not relabel
  the dialect or validate a raw bundle against the existing optional Contract wrapper.
  Keep the legacy combined schema/type generation compatible for other exported models.
  Schema generation and the validator smoke test are P1-01b deliverables; P1-08 only
  consumes the generated schema. There is no hand-written second schema.
- Beyond schema checks:
  - ticks are contiguous from 0;
  - `event_range` slices cover `events` exactly once and in order;
  - coordinates are inside the map;
  - row lengths match the width;
  - resident IDs in frames match `residents`;
  - IDs are unique within a frame.
- Also require positive dimensions, exactly height rows, one-character ASCII grammar symbols,
  and the nine unique legend symbol/Terrain pairs from World Rules §1.2 (no aliases/extras).
  Verify map_hash against rows joined with LF including final LF. Config hash is an identity
  field; the viewer cannot verify absent raw config and must not claim it has done so.
- Every frame contains exactly the declared resident IDs, including dead residents. Resident
  labels and tree IDs are unique; tree IDs/positions remain stable and correspond one-to-one
  to F tiles. Ground pile coordinates are unique; all resident references in corpse/event
  fields resolve to declared labels. Entity-type namespaces remain distinct.
- Event slices start at the cumulative prior count, with nonnegative first_index/count, and
  contain **only** events whose tick equals frame.tick. Events are strictly ordered, with
  seq_in_tick contiguous from zero for each nonempty tick; run_id matches the bundle; event IDs
  match the frozen deterministic format and are unique. Causal references must resolve to
  earlier bundle events. Validate utterance ID/reference fields against the event catalog.
- condition_bounds comes from effective config, with 0=min_value < max_value; each displayed
  condition is within it. Stocks/servings/counts are nonnegative. These are structural/domain
  checks, not re-execution: the viewer does not verify physiology or infer state changes.
- Backend export and browser import enforce the same cross-field requirements, with shared
  valid/invalid fixtures. Schema tests must prove a valid raw ReplayBundle is accepted and an
  unrelated Contract wrapper is refused. All schema models reject unknown fields.
- Any failure shows a clear error and the file is refused. The viewer never repairs data and
  never modifies the file.

### 2.4 Capture and resumed exports

P1-06 must implement the observer port frozen in the implementation plan §2.1:
`on_boundary_committed(snapshot, new_events)`. It is called synchronously once after fresh
tick-zero initialization and each committed tick, before next-boundary ingest, with an
immutable snapshot and this tick's ordered events. It is not called again for the restored
checkpoint tick. The optional observer cannot change world state or draw randomness.

P1-07 supplies the projection/capture callback and wires it in `sim/cli.py`; it does not
rewrite the runner. Persistence writes one canonical DisplayFrame line to `frames.jsonl`
per callback, including tick zero; the JSONL is a display spool, not a SavePackage or world
event log. Build event_range from the captured event cursor, and freeze each frame before
advancing the next tick. At run completion assemble replay.json from this spool and the
verified event log. This explains how an export made after a run obtains earlier states;
it must not reconstruct missing states from event hashes alone.

**Resumed runs do not export replays in P1.** `resume --export-replay` is refused with a
clear message. To get a full bundle for a resumed run, re-execute it from tick zero
(`reexecute --export-replay`), which captures every frame in one pass. No frame cursor or
spool hash is added to `SavePackage`, and frames are never embedded in the authoritative save.

## 3. Structure

```text
File picker / drag-and-drop / bundled example
        |  runtime validation
   ReplayStore (frames, events, currentTick, selection, filters, camera)
     |              |                 |
  MapCanvas     PlaybackBar     ResidentPanel / EventList / DebugDetails
```

Directories follow the existing skeleton:
- `src/replay/`: loading, validation, indexes, store.
- `src/render/`: Canvas drawing of the map and the current frame.
- `src/controls/`: playback and camera controls.
- `src/panels/`: resident, resource and event panels.
- `src/debug/`: validation error details and raw event JSON.
- `src/api/generated/`: generated, never hand-edited.

Rendering reads only `currentFrame`. It never simulates from one frame to the next.

## 4. Features

### 4.1 Map and camera

- Draw the `map.width × map.height` grid from the bundle (64×64 by default). terrain_legend
  maps symbols to Terrain; an explicit frontend theme maps Terrain to colours. The bundle
  does not claim to contain colour values. Theme choices carry no terrain legality/rules.
- **Camera:**
  - default *fit to view*: base tile size is min(panelWidth/map.width,
    panelHeight/map.height), using display floats; no minimum that causes overflow;
  - zoom steps ×1, ×2, ×4 from that size;
  - drag to pan whenever content exceeds the viewport; clamp camera bounds, not entity positions;
  - an optional "follow selected resident" toggle.
- Residents get a stable colour **and** a letter. Colour is never the only cue.
- Show trees with a small stock number, ground fruit, the ground canteen and corpses. Several
  residents on one tile are drawn with offsets; their coordinates are never changed.
- **Night shading:** derived from `clock` (World Rules §1.3). This is pure display.
- Show a fixed legend.

### 4.2 Timeline and controls

| Control | Behaviour |
|---|---|
| Load | file picker or drag-and-drop; on success, go to tick 0, paused |
| Play / pause | changes the local frame only |
| Step forward / back | exactly one tick; stops at both ends |
| Seek | slider + numeric input to any tick, including 0 and the end |
| Speed | 1, 2, 4, 8, 16 ticks per second (at 16, a full run takes about 1 minute) |
| Clock | shows tick, `Day d` and `HH:MM`, derived from `clock` |

For display, elapsedMinutes=tick*tick_minutes, HH:MM uses
(start_hour*60+elapsedMinutes) mod 1440, and Day=1+floor(elapsedMinutes/1440).
Thus Day counts elapsed simulation days, not midnight crossings. Night shading uses the
frozen daylight interval. Display arithmetic/zoom floats never enter world calculations.

### 4.3 Panels

- Resident:
  - name, position, alive or dead;
  - four raw condition values and bars using condition_bounds (default 0..10000), never a
    hard-coded physiology maximum;
  - fruit count and canteen servings;
  - current action with start tick and remaining ticks;
  - the change from the previous tick.
- Resources: tree stocks, ground piles and the ground canteen at the current tick. Empty states
  are shown as empty and never guessed. Several ground objects on one tile are all listed.

### 4.4 Events and debugging

- Show events in `(tick, seq_in_tick)` order: tick, type, actor/target, a short summary built
  from payload fields, and the failure code or interruption reason.
- **Resident filter:** match on `actor_id`, `target_id`, or payload fields defined as
  resident references (`resident_id`, `from_id`, `to_id`, `listener_id`, `addressee_id`). The
  mapping is a fixed function in code and never uses name matching in text.
- **Failure filter:** `action_failed` and `action_interrupted`.
- Clicking an event seeks to its tick and expands the raw JSON.
- The viewer never generates explanations such as "she refused out of jealousy".

## 5. Fixtures

Three hand-made fixtures must conform to the final schema and are committed as test data:
1. move and gather;
2. contention: one resident wins, the other gets `RESOURCE_TAKEN`;
3. death and drops, then a pick-up.

They let the frontend proceed in parallel with the engine. They are labelled as hand-made, not
as simulation output. After P1-07, add one real exported bundle, made with `ScriptedPolicy`,
as a fixture.

The viewer must also handle these error and edge cases clearly:
- a bundle with only frame 0;
- all residents dead;
- an unknown terrain symbol;
- broken JSON;
- an unknown version;
- events out of order;
- a missing frame.

## 6. Technical constraints

- React + TypeScript (strict) + Vite + HTML Canvas. Local file only: no FastAPI, no WebSocket.
- `ReplayStore` indexes frames by tick. Canvas drawing is pure: no hidden state changes, no
  randomness, no network access.
- A future live viewer may reuse `DisplayFrame`, events and controls, but needs its own spec.
- The bundle can grow later (e.g. a P3 per-resident perception overlay) by adding optional
  fields under a new `replay_schema_version`. Nothing is reserved now.

## 7. Tests and Definition of Done

| ID | Test | Pass condition |
|---|---|---|
| FE-T01 | Load each fixture | Validation passes; tick 0 positions are correct |
| FE-T02 | Step at tick 0 and at the last tick | Stays in range; no implicit simulation |
| FE-T03 | Seek, then switch resident | Panel, map and inventory equal that frame's data |
| FE-T04 | Shared tile, corpse, ground items | All visible; coordinates unchanged |
| FE-T05 | Failure and resident filters | Results equal the expected event IDs and codes |
| FE-T06 | 1,009-frame bundle | Loads and seeks to the last tick |
| FE-T07 | Change speed | Frames and data unchanged |
| FE-T08 | Broken, unknown-version or gapped bundle | Clear error; refused; not repaired |
| FE-T09 | Type generation | No unexpected diff; strict TS, ESLint and build pass |
| FE-T10 | Camera | Fit, zoom and pan keep every entity at its recorded tile |
| FE-T11 | Demo | One real backend replay shows movement, consumption, events and failure diagnosis |
| FE-T12 | Wrong event tick/range/run ID, invalid legend/ref/bounds or wrapper-shaped input | Rejected consistently by backend and browser, without repair |
| FE-T13 | Capture during `run` and `reexecute`; attempt `resume --export-replay` | Exactly frames 0..N, one per committed boundary; the resume export is refused |

**DoD:** automated checks pass; an independent review confirms the frontend contains no world
rules; the project owner accepts a real replay (FE-T11). Fixtures or screenshots alone are not
enough.

## 8. Contract amendment A2 (applied in P1-01b)

1. `ReplayBundle` and `DisplayFrame` exactly as in §2.2, as read-only display DTOs. They never
   reuse `WorldState` or `Perception`.
2. The replay file `runs/<run_id>/replay.json`, with its own version field.
3. The runtime validator uses the generated JSON Schema.
4. condition_bounds, fixed replay version "0.1", strict structural/domain checks and the
   standalone ReplayBundle schema export in §2.3.
5. Display spool capture during `run`/`reexecute`, and refusal of resumed exports (§2.4);
   no frame data or frame cursor is inserted into WorldState or SavePackage.

These are proposed A2 amendments to land in P1-01b; the current official contract remains
unchanged until that task is approved. P1-01b owns the replay schemas; P1-06 owns observer invocation;
P1-07 owns the observer adapter/spool/export; P1-08 owns display and browser validation.
