# Living Island — Frontend Design Spec v0.1 (pixel-art replay viewer)

> **Status: implemented, pending owner approval at MF.** Written alongside the code in task
> P2-F1 under plan Amendment 2 (2026-11-11), which folded the P2-F0 design task into the
> implementation. It describes the viewer as built. The owner approves it, or asks for
> changes, by reviewing the working viewer.
>
> **Relation to `p1-replay-frontend-v0.1.md`:** that file is not edited. This spec supersedes
> its FE-04, §4.1 (camera, legend placement, resident marks) and the parts of §3 and §6 listed
> in §7 below. Everything else in the P1 spec stays in force, in particular §2 (replay data and
> validation), FE-01 to FE-03 and §5.

**Goal:** make the replay pleasant to watch as a living island, without giving up any of the
inspection and debugging the P1 viewer offers, and without adding a single rule to the
frontend. The viewer still only displays recorded frames and events.

## 1. Visual direction

Warm, top-down 2D pixel art, chosen by the owner (concept image "A — Warm Pixel Art").

- **Map.** Sea in three depth tones with a foam line, a sand beach, light grass, dense woods
  of round trees, grey rock, a stone-ringed spring, a cave mouth, a dark wet moss patch, and
  larger, lighter fruit trees that carry visible fruit.
- **Residents.** 16×20 pixels: a head a little under half the height, a clear torso, arms and
  legs. Three hair designs (short, long bob, top bun) give three silhouettes; hair and shirt
  colours differ; a letter tag (A, B, C, ...) is always shown as the non-colour identifier.
- **Restraint.** Ground textures are sparse (a few specks, tufts and flowers), so residents,
  resources and ground items stand out.
- **Interface.** Cream panels, dark brown text, rounded corners, a clean system sans-serif
  font. No pixel font.

### 1.1 Departures from the concept image

| Concept image | As built | Reason |
|---|---|---|
| Overview and close-up side by side | One map with free zoom between the whole island and a close-up | The owner stated the split is a comparison, not a requirement. One large map keeps the island dominant. |
| A fixed, hand-painted island | The picture is generated from `map.rows` of the replay | The map must follow the data (plan §3: if M6 changes the map, the viewer needs no change). |
| Residents drawn at one scale | Residents and ground items are never drawn smaller than 2 screen pixels per art pixel | On the 64×64 default map one tile is about 13 px at island scale; at tile scale a resident would be unreadable. |
| Panel always visible on the right | The resident panel opens on click and floats over the map | Opening it must not resize the map or move the camera. |
| Health, Food, Water, Energy | Health, Satiety, Hydration, Stamina | These are the recorded field names; using them avoids a second vocabulary in a debugging tool. |
| Zoom and "Fit" in the bottom bar | Zoom buttons and "View entire island" sit on the map, bottom left | Map controls belong to the map; the bottom bar is time only. |
| Waterfall at the spring | A stone-ringed pool with moving glints | The spring is one tile; a pool reads at that size. |
| Nothing shown for a death | A corpse is the resident's own sprite lying down and greyed, with a grey tag ending in "×" | The replay records corpses; they must be visible and not rely on colour. |

## 2. Rendering approach

HTML Canvas 2D, no rendering library, no new dependency. See ADR 0005.

- The static terrain is rendered once per loaded map into an offscreen canvas at 16 source
  pixels per tile (twice, for a two-frame water shimmer) and then drawn with one `drawImage`
  per animation frame.
- Everything that changes (fruit in trees, ground items, corpses, residents, bubbles, labels,
  night tint, selection) is drawn each animation frame from the current recorded frame.
- All art is TypeScript source: character grids and small deterministic generators. There are
  no image files.

## 3. Asset interface

### 3.1 Tile size and scaling

- **Tile art size:** 16×16 source pixels per tile (`TILE_PX`).
- **Fit:** base tile size is `min(viewWidth / map.width, viewHeight / map.height)` (unchanged
  from P1 §4.1). Zoom 1 is "view entire island".
- **Zoom:** continuous, from 1 up to the zoom at which a tile is 96 screen pixels (6× the tile
  art). If the fit view is already larger than that, only zoom 1 exists. This replaces the P1
  steps ×1, ×2, ×4.
- **Smoothing:** the terrain image is smoothed only when it is drawn smaller than 1:1 (the
  island view of a large map). Enlarged art is drawn without smoothing.
- **Minimum entity scale:** residents, corpses, ground items and bubbles are drawn at
  `max(tileScale, 2)` screen pixels per art pixel. Below that zoom they are larger than their
  tile, anchored on it.
- **Large maps:** if `max(map.width, map.height) × 16 > 4096`, the terrain falls back to flat
  colour tiles (4 px, or 1 px above 1,024 tiles per side), with no decorations and no fruit in
  the canopies. Entities, labels and everything else work as usual.

### 3.2 Layer order (bottom to top)

| # | Layer | Contents |
|---|---|---|
| 1 | `terrain` | backdrop, cached map image (ground, coast, trees, rocks, cave, spring, moss), map edge line |
| 2 | `tree_fruit` | fruit drawn in fruit-tree canopies |
| 3 | `corpse` | corpses |
| 4 | `ground_item` | ground fruit piles, the ground canteen |
| 5 | `resident` | living residents, sorted so the one lower on screen is in front |
| 6 | `night` | night tint over the whole view |
| 7 | `emote` | action bubbles |
| 8 | `label` | fruit-tree stock badges, ground-item quantities, resident and corpse tags |
| 9 | `selection` | recorded-tile outline and corner brackets of the selected resident |

Ground items are above corpses so that what a dead resident dropped stays visible. Bubbles,
labels and the selection are above the night tint so they stay readable at night.

### 3.3 Placement on a tile

Recorded coordinates are never changed. Every sprite keeps its recorded tile and has an anchor
inside that tile when at rest:

| Sprite | Anchor in the tile (fractions of a tile from the centre) | Drawn rectangle |
|---|---|---|
| Resident | x 0, y +0.30 (feet) | bottom centre on the anchor |
| Residents sharing a tile | spread evenly over ±0.28 in x | centres at least 0.62 sprite widths apart |
| Corpse | x 0, y +0.12 | centred on the anchor; several corpses are spread like residents |
| Ground fruit | x −0.22, y +0.25 | left of the tile centre |
| Ground canteen | x +0.22, y +0.25 | right of the tile centre |

When sprites are larger than the tile (island view) or share a tile, the drawn rectangles are
moved apart so each one shows, and the letter tags never coincide. The anchors stay in the
recorded tile. When the selected resident's tile is at least 20 px wide it is outlined, so the
sprite is not mistaken for the position.

### 3.4 Facing and animation (display only)

All of the following are pure functions of recorded frames and events. None is written back,
and none is used as a world fact.

- **Path.** A tick can move a resident several tiles, and the world records one
  `resident_moved` event per entered tile. The path of a resident in tick `t` is its position
  in frame `t−1` followed by the `to` of each of its `resident_moved` events in frame `t`'s
  event slice, in order. It is used only if every event starts where the previous one ended
  and the last one ends at the position in frame `t`.
- **No invented routes.** If the events do not chain that way, a move to an adjacent tile is
  drawn as a straight slide and any other move as a jump.
- **Slide.** While playing, after the current tick advances by exactly one, the sprite moves
  along that path over one beat (`1000 / speed` ms). After a single manual step forward it
  takes 160 ms. Seeking, stepping back and loading show the frame at once. When the slide ends,
  and whenever the viewer is paused, every resident is on its recorded tile.
- **Facing.** `right`, `left`, `down` or `up`, from the direction of the path segment being
  walked; at rest, from the last recorded step up to this tick; `down` before any move.
  Horizontal wins on a diagonal step.
- **Frames.** `idle` at rest; `walk_a` and `walk_b` alternate twice per tile while sliding.
- **Bubbles.** One bubble above a living resident, from recorded data only (§5).
- **Ambient shimmer.** Water glints and the foam line alternate between two prepared terrain
  images every 0.9 s. Positions do not change.
- **Reduced motion.** With `prefers-reduced-motion: reduce` there is no slide and no shimmer.
- **Night** is a flat tint, on exactly when the bundle clock is outside
  `[day_start_hour, day_end_hour)`. There is no dusk or dawn fade, because that would show
  darkness at a time the rules count as day.

### 3.5 Naming, file layout and formats

```text
frontend/src/render/assets/
  pixels.ts        sprite primitives (RGBA buffers, mirror, rotate, recolour, display hash)
  residentArt.ts   resident sprites and looks; corpse sprite
  objectArt.ts     fruit, piles, canteen, tree fruit, bubbles
  terrainArt.ts    trees, fruit tree, rocks, cave, spring, moss, tufts, flowers
  index.ts         sprite lookup by key
  README.md        asset record (source, author, license) and conventions
frontend/src/render/terrainLayer.ts   map -> terrain pixels (code, not an asset)
```

- **Format:** a sprite is an array of equal-length strings, one character per pixel, plus a
  palette from character to `#rrggbb`. `.` is transparent. A ragged row or an unknown
  character throws, and the tests build every sprite.
- **Sprite keys** (the interface between the scene and the image cache):
  `resident/<index>/<down|up|left|right>/<idle|walk_a|walk_b>`, `corpse/<index>`,
  `item/<fruit_1|fruit_2|fruit_3|canteen|tree_fruit|apple>`,
  `emote/<sleep|water|fruit|fail|rest|talk|hand>`.
- **Resident looks** depend only on the resident's index in `bundle.residents`: hair shape
  cycles with period 3, hair colour with period 5, shirt colour with period 8, letters with
  period 26. Names and IDs are never matched.
- **Variation** (tree shapes, tufts, wave marks) uses a deterministic hash of tile or pixel
  coordinates. `Math.random` is not used.
- **Adding an asset** needs no design decision: add the grid or generator to the matching
  file, give it a key in `index.ts` if the scene draws it, and add its row to the asset record.
- **Replacing code art by image files** later is possible behind the same keys: the image
  cache (`render/atlas.ts`) is the only place that turns a key into a drawable image.

### 3.6 License and source record

`frontend/src/render/assets/README.md` has one row per asset file: contents, how it was made,
source or author, and license. A test checks that every asset module is listed. All current
assets are project-made; there are no third-party assets, and `art/LICENSES.md` stays empty.
A third-party asset needs the owner's approval in chat, a license that allows redistribution
in this repository, and a row in both records in the same commit.

## 4. Layout and interaction

```text
+--------------------------------------------------------------------------------+
| Living Island | Day 3 09:40 day | Alive 3/3 | 14 on 6 trees | canteen with C·2 |
|                                   [Events] [Resources] [Legend] [Open replay…] |
+--------------------------------------------------------------------------------+
| [A name]                                                   +-----------------+ |
| [B name]                 ISLAND MAP (fills the stage)      | resident panel  | |
| [C name]                                                   | (on selection)  | |
|                                                            +-----------------+ |
| [-] [+] [View entire island]                                                   |
|  ......... details drawer (on demand): Events | Resources | Legend ..........  |
+--------------------------------------------------------------------------------+
| |< <| play |> >|   Tick 558 · Day 4 03:00   ====o=======   Tick [558]/1008  1× 2× 4× 8× 16× |
+--------------------------------------------------------------------------------+
```

| Area | Behaviour | Change from P1 §4 |
|---|---|---|
| Map | Fills the stage. Drag to pan; wheel, pinch, double click, `+`/`-` keys and the buttons zoom; "View entire island" (or `0`) returns to zoom 1, centred. Arrow keys pan when the map has focus. | Continuous zoom instead of ×1/×2/×4. Pan is clamped so the map always covers the centre of the view (any tile can be centred, also past a floating panel); P1 clamped to the content edges. |
| Global status | Day, time, day or night; living residents; total fruit on trees; ground fruit (only when there is some); where each canteen is and its servings. | New. Counts and sums of recorded values only (§5). |
| Roster | One button per declared resident with letter, face and name; a dead resident is greyed and marked "dead". Click selects or deselects. | Replaces the resident drop-down. Gives keyboard access to selection. |
| Resident panel | Opens when a resident, its tag, its corpse or its roster button is clicked. Shows portrait, name, ID, alive or dead, tile, move since the previous tick, status chip, recorded death tick and cause, the four conditions as bars with raw values and change, fruit, canteen, the recorded action (type, start tick, remaining ticks, intent ID) and this tick's events for the resident. | Same data as P1 §4.3 plus the status chip, the death record and the tick's events. Nobody is selected after loading (P1 selected the first resident). |
| Selection rule | Selecting never changes the camera and never pauses playback. "Follow on the map" is a separate, opt-in checkbox in the panel; dragging the map turns it off. | Follow was already optional; the rule is now explicit and tested. |
| Details drawer | Closed by default. Events: the P1 event table with the resident and failure filters; clicking an event seeks to its tick and shows its raw JSON. Resources: the P1 resource lists. Legend: terrain, residents, objects, bubbles. Clicking an event in the resident panel opens the drawer on that event. | The same panels as P1 §4.3–§4.4, moved from always-visible to on demand. The legend moves here. |
| Playback bar | First, step back, play or pause, step forward, last; clock; seek slider; tick field; speeds 1, 2, 4, 8, 16 ticks per second. Space plays or pauses; Escape closes the panel, then the drawer. | Same controls and semantics as P1 §4.2; speed is a button group instead of a drop-down. |
| Loading | "Open replay…", drag and drop anywhere, and "Example". A refused file shows the validation error over the stage; the loaded replay stays; nothing is repaired. | Unchanged behaviour; the file input is behind a button. |

The floating panel and the drawer overlay the map. They never resize it, so opening them
never changes the camera.

**Accessibility.** Colour is never the only cue: residents have a letter and a silhouette;
corpses lie down and have a "×" tag; the status chip is text; night is also stated in the
status line; failures in the event table also have a code column. All controls are buttons or
inputs with accessible names. Motion respects `prefers-reduced-motion`.

## 5. Data mapping

Every displayed element reads an existing field. Line numbers refer to
`backend/src/living_island/contract/replay.py` (`replay.py`) and
`backend/src/living_island/world/facts.py` (`facts.py`) at baseline `5bb89c2`; these files are
unchanged since `821cd88`.

| Displayed element | Field(s) | Source |
|---|---|---|
| Map picture, map size | `map.width`, `map.height`, `map.rows`, `map.terrain_legend` | `replay.py:96-100`, `91-93` |
| Day, time, day/night, night tint | `clock.*`, `frame.tick` | `replay.py:69-73`, `190` |
| Resident name, ID, letter, look | `residents[].id`, `.display_name`, index in the list | `replay.py:119-123` |
| Resident position, alive | `frame.residents[].position`, `.alive` | `replay.py:140-141` |
| Condition bars and values | `.health`, `.satiety`, `.hydration`, `.stamina`, `condition_bounds` | `replay.py:142-145`, `84-88` |
| Fruit, canteen in the panel | `.fruit_count`, `.canteen_servings` | `replay.py:146-147` |
| Recorded action line | `.active_action.{intent_id, action_type, tick_started, remaining_ticks}` | `replay.py:131-135`, `148` |
| Change since previous tick | the same fields in frame `t−1` | as above |
| Fruit in canopies, stock badge | `frame.fruit_trees[].position`, `.stock` | `replay.py:151-154` |
| Ground fruit and quantity | `frame.ground_fruit[].position`, `.quantity` | `replay.py:157-159` |
| Ground canteen and servings | `frame.ground_canteen.position`, `.servings` | `replay.py:162-164` |
| Corpse, corpse tag | `frame.corpses[].id`, `.resident_id`, `.position` | `replay.py:167-170` |
| Events of a tick | `frame.event_range`, `events[]` | `replay.py:173-175`, `237` |
| Status line: alive | count of `frame.residents[].alive` | `replay.py:141` |
| Status line: fruit on trees | sum of `frame.fruit_trees[].stock` | `replay.py:154` |
| Status line: ground fruit | sum of `frame.ground_fruit[].quantity` | `replay.py:159` |
| Status line: canteen | residents with non-null `canteen_servings`; `ground_canteen` | `replay.py:147`, `194` |
| Walking path, facing | `resident_moved` events of the tick (`actor_id`, `payload.from`, `payload.to`) and positions in frames `t−1`, `t` | `facts.py:91`, `321` |
| Status chip, bubble: failure | `action_failed` of the tick by this actor: `payload.action_type`, `payload.failure_code` | `facts.py:113` |
| Status chip: interruption | `action_interrupted`: `payload.action_type`, `payload.reason` | `facts.py:118` |
| Status chip: finished action | `action_succeeded`: `payload.action_type` | `facts.py:108` |
| Bubble: water | active `drink` or `fill_canteen`; or `water_drank`, `canteen_filled` this tick | `facts.py:136`, `144` |
| Bubble: fruit | active `gather` or `eat`; or `fruit_gathered`, `fruit_consumed` this tick | `facts.py:123`, `130` |
| Bubble: talk, hand | active `talk`, `give`, `pick_up`; or `utterance_spoken`, `item_given`, `item_picked_up` this tick | `facts.py:179`, `193`, `201` |
| Bubble: sleep, rest | active `sleep`, `rest` | `replay.py:133` |
| Death tick and cause | `resident_died`: `tick`, `payload.resident_id`, `payload.cause` | `facts.py:209`, `318` |
| Event table and filters | as P1 §4.4 | unchanged |

**Status chip order** (first match): dead (`alive` false) → an `action_failed` of this actor in
this tick → `active_action` → an `action_interrupted` → an `action_succeeded` → "No action
recorded". Action types are shown through a fixed name table (`move_to` → "Walking", and so
on); an unknown type is shown as recorded.

**Not shown, because the replay has no field for it:** maximum tree stock, need bands or
thresholds, what a resident sees, goals, personality, memory, relationships, speech text
outside the event table, and why anything happened. See OQ-079 to OQ-081.

## 6. What the frontend does not do

- It computes no legality, physiology, resource change or outcome. Bars are
  `(value − min) / (max − min)` of recorded values. There are no "low" or "critical" marks,
  because the thresholds are rules and are not in the replay.
- It never predicts: the slide uses the previous and current recorded frames, never the next.
- It never fills a gap: an undefined terrain symbol is drawn as a magenta checker; a move
  whose events do not chain is drawn as a jump.
- Display state is limited to the camera, the selection, the filters, the open panel and the
  timing of the current slide. None of it is saved or sent anywhere.

## 7. Change set against `p1-replay-frontend-v0.1.md`

| P1 item | Disposition |
|---|---|
| FE-01 Replay first | Kept. |
| FE-02 Replay + basic debugging | Kept. Every listed feature remains; events, resources and the legend are on demand. |
| FE-03 Read-only | Kept, and restated in §6. |
| FE-04 Simple 2D Canvas, "coloured tiles and basic shapes" | **Superseded.** Still Canvas 2D, now with pixel art. Art remains outside the acceptance criteria of P1; it is covered by §8 here. |
| §2 Replay data, validation, capture | Kept unchanged. No contract, schema or generated file changes. |
| §3 Structure | Kept. Additions: `render/assets/`, `render/terrainLayer.ts`, `render/scene.ts`, `render/motion.ts`, `render/atlas.ts`. "Rendering reads only `currentFrame`" becomes: rendering reads the current frame, the previous frame and the current tick's events, only for the slide and the facing; it still never simulates. |
| §4.1 Map and camera | **Changed:** continuous zoom (§3.1); pan clamp (§4); residents drawn as sprites with a letter tag; trees show fruit as well as the stock number; shared-tile offsets per §3.3; legend on demand. Kept: grid from the bundle, fit formula, drag to pan, optional follow, colour never the only cue, night from the clock. |
| §4.2 Timeline and controls | Kept, including the clock formulas and the five speeds. |
| §4.3 Panels | Kept data; new placement (§4). Added: status chip, death record, events of the tick. Nobody is selected after loading. |
| §4.4 Events and debugging | Kept unchanged, inside the drawer. |
| §5 Fixtures and edge cases | Kept. |
| §6 Technical constraints | Kept: React, strict TypeScript, Vite, Canvas, local file only, no network. No new dependency. "Canvas drawing is pure" holds: `drawFrame` depends only on its arguments. |
| FE-T01, T02, T03, T05, T06, T07, T08, T09, T12 | Apply unchanged; their tests are unchanged. |
| FE-T04 Shared tile, corpse, ground items | Applies. Its test is unchanged; PF-T03 adds the sprite cases. |
| FE-T10 Camera | Applies with the new camera: the test now uses a continuous zoom and the new pan clamp; the "every entity at its recorded tile" assertions are unchanged. |
| FE-T11 Demo on a real replay | Applies; redone on the new viewer (PF-T14). |
| FE-T13 Capture during run and reexecute | Backend only; unaffected. |

## 8. Acceptance checks

| ID | Check | Pass condition | How |
|---|---|---|---|
| PF-T01 | P1 checks that still apply | FE-T01 to T10 and T12 pass | `pnpm --dir frontend test`, `test:schema` |
| PF-T02 | Layer order | Layers are painted in the order of §3.2, and each sprite in its layer | automated |
| PF-T03 | Shared tile, corpse, ground items | All are visible; residents on one tile are drawn apart with distinct tags; a corpse keeps its tile, has a non-colour mark and stands for the dead resident; sprites never go below the minimum scale | automated |
| PF-T04 | Zoom and pan | At rest every anchor maps back to its recorded tile at any zoom and pan; zoom is clamped between fit and closest; zooming at a point keeps that map point in place | automated |
| PF-T05 | Selection | Selecting changes neither camera nor playback; nobody is selected after loading; follow is opt-in | automated |
| PF-T06 | Motion is presentation only | Paths start at the previous and end at the current recorded tile and follow the recorded move events; a broken chain is drawn as a jump; progress 1 equals the recorded frame; drawing never changes the bundle; drawing is deterministic | automated |
| PF-T07 | Data-driven map | The terrain picture is a deterministic function of the map; changing a tile changes it; each terrain looks different; an undefined symbol is marked; other sizes draw; very large maps fall back | automated |
| PF-T08 | Assets | Every sprite key a scene uses resolves; residents differ in pixels, silhouette and letter; sprite grids are validated | automated |
| PF-T09 | Fruit trees | Canopy fruit and the badge come from the recorded stock; the badge is exact | automated |
| PF-T10 | Status line and status chip | Values equal counts and sums of the frame; the chip restates recorded fields; a death is not shown before its tick | automated |
| PF-T11 | 1,009 frames at 16 ticks per second | One recorded frame per beat, none skipped, 1,008 beats; and in the browser a real rule-based default-island replay advances at 16 ticks per second | automated, plus manual timing |
| PF-T12 | No game logic; contract untouched | Reviewer finds no rule in the frontend; `gen_types.py` leaves no diff; no file under `backend/`, `contract/` or `src/api/generated/` changes | Gate 2, `git diff` |
| PF-T13 | Asset record | Every asset module is listed with source and license; no third-party asset | automated, plus review |
| PF-T14 | Real replays | A rule-based default-island replay, an S1 replay and the P1 demo replay load and play: zoom and pan, shared tiles, night, death, dropped canteen, error handling | manual, recorded in the handoff |

## 9. Known limits

- The canopy shows at most 8 fruit; the badge is exact (OQ-079).
- Looks are assigned by list index, so a run with different residents reuses the same looks in
  order (OQ-080).
- No low-need warning is shown (OQ-081).
- Two frames of ambient shimmer cost a second terrain image (about 4 MB for the default map).
- Touch pinch zoom is implemented but was only exercised with mouse and wheel.
