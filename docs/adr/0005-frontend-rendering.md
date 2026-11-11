# ADR 0005: Frontend rendering approach

- Status: accepted (owner, MF, 2026-11-11; implemented in P2-F1 under plan Amendment 2;
  acceptance recorded in `docs/tasks/p2/P2-F1.md`)
- Date: 2026-11-11
- Task: P2-F1 (spec: `docs/spec/frontend-design-v0.1.md`; plan:
  `docs/plans/p2-implementation-plan-v0.1.md`, Amendment 2)

## Context

The P1 viewer draws coloured tiles and circles on an HTML Canvas (P1 replay spec FE-04). The
product document defers the rendering library until the art direction is set (§10: "choose
PixiJS or similar after the art direction is set"). The owner has now chosen warm top-down
pixel art and asked for a working viewer. The scene is small: one 64×64 map, a handful of
residents, a few items, at most 16 recorded frames per second.

## Decisions

- **Stay on Canvas 2D. Add no rendering library and no new dependency.**
  - The static terrain is rendered once per map into an offscreen canvas at 16 source pixels
    per tile and reused; each animation frame is one large `drawImage` plus a few dozen small
    ones. Measured on the 1,009-frame rule-based default-island replay: about 0.07 ms of
    script time per frame, and about 180 ms once to build both terrain images (method and
    limits: P2-F1 handoff, "Measurements").
  - A WebGL library would add bundle size and a second rendering model for no visible gain at
    this scale.
- **Art is TypeScript source, not image files.**
  - Sprites are character grids with palettes; trees, rocks and the coastline come from small
    deterministic generators. Everything is project-made, reviewable in a diff, testable in
    Node without a canvas, and free of license questions.
  - The scene names sprites by key and one module (`render/atlas.ts`) turns keys into images,
    so image files can replace code art later without touching the scene.
- **Scene and painting are separate and pure.**
  - `buildScene` turns a recorded frame and a view into plain data (what, where, which layer);
    `drawFrame` paints it. Neither uses randomness or touches the network, and for an
    immutable bundle each depends only on its arguments; the only module state is memoisation
    (sprite caches, facings per loaded bundle). The only display state is the camera, the
    selection and the timing of the current slide.
- **Motion is presentation only.**
  - Walking between tiles follows the recorded `resident_moved` events of the tick. If they do
    not chain to the recorded position, an adjacent move is drawn as one straight slide and any
    other move as a jump. Facing comes from recorded displacement. Nothing is predicted and
    nothing is written back.

## Alternatives considered

- **PixiJS (or another WebGL 2D library).** Rejected for now: a new dependency of several
  hundred kilobytes, a scene graph that duplicates the pure scene data, and no performance
  need. Revisit if a later phase needs thousands of animated sprites, particle effects or
  shaders (for example a lit night).
- **PNG sprite sheets.** Rejected for now: binary files that cannot be reviewed in a diff,
  need a build or export step, and need a recorded source for each file. The key interface
  keeps this open.
- **Third-party asset packs.** Rejected: the task card requires owner approval and a
  redistribution license for each asset, and a coherent original set was achievable.
- **DOM or SVG elements per tile.** Rejected: 4,096 tiles plus overlays is heavier than one
  canvas and gives no crisp pixel scaling.

## Consequences

- No change to `contract/`, the backend, the replay schema or generated files.
- The viewer bundle grows only by the art, renderer and interface source: the production
  script went from 436.5 kB to about 477 kB (139 kB gzipped), and the stylesheet from 1.8 kB
  to about 10 kB (method: P2-F1 handoff, "Measurements"). `package.json` and the lockfile are unchanged.
- A second cached terrain image is kept for the water shimmer (about 4 MB for the default map).
- Maps larger than 256 tiles per side fall back to flat tiles (spec §3.1).
- If the owner later prefers painted image assets, the work is contained in `render/assets/`
  and `render/atlas.ts`.
