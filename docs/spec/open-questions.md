# Open Questions

Add an entry whenever the spec is missing or ambiguous. Do not invent rules or numbers:
record the question, make the smallest reversible assumption, and flag it in your handoff.

| ID | Date | Raised in task | Question | Assumption made | Status |
|---|---|---|---|---|---|
| OQ-001 | 2026-11-08 | P0-01 | The product doc names a module `interface` (player interaction, saving, observation, debugging) but the P0-01 structure has no such package; its responsibilities are spread over `sim`, `persistence` and `contract`. Is a separate `interface`/API package wanted later (FastAPI)? | None; no `interface` package created. | open |
| OQ-002 | 2026-11-08 | P0-01a | Memory import-linter contract has `unmatched_ignore_imports_alerting = "none"` because no memory module imports `world.protocol` yet. | Keep `none`; switch to `error` when the first memory module imports `world.protocol`. | open |
