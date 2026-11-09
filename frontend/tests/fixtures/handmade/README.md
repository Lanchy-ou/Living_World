# Hand-made fixtures

These replay bundles were authored by hand with `build.mjs` (replay-frontend spec section 5).
They are NOT simulation output. They let the viewer be built and tested before the engine
exists. Valid ones must also pass the backend `ReplayBundle` validator; `edge-*` files named in
`build.mjs` with a refusal are invalid on purpose.

Regenerate: `node tests/fixtures/handmade/build.mjs`. A test fails if the committed files drift.
