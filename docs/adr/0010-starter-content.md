# ADR 0010: Starter content and balance

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-15.
- Baseline: `bf5ed7d` (`task/P3.5-PR-01-protocol-adr`).
- Phase: P3.5, system 4 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: the first content packs and the balance constraints they must respect.
  The rule format is ADR 0008; the engine is ADR 0009.
- Spec to be written: `docs/spec/starter-content-v0.1.md`.
- Supersedes on acceptance: `balance-notes-v0.1.md` for new content.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.

## Context

P2 tuned the survival economy in `content/worlds/default.toml`: needs on a
0–10000 scale, fruit regrowth every 144 ticks, one unique canteen with two
servings, and a 64×64 map. New materials and recipes must not break that economy.
Content is designed separately from the engine: the engine never contains code
for a specific recipe.

## Decision

### D1. Two packs

- **v1 compatibility pack**: the 11 v1 actions expressed as v2 rules on the
  default map. It is the balance baseline and the equivalence check for
  ADR 0007 D8.
- **Starter pack**: the compatibility pack plus the first crafting content and
  every mechanic v1 does not have (mental fatigue and fainting, fruit decay,
  tool wear, fire). **[Owner]** These enter only after the compatibility pack
  passes the equivalence check (ADR 0007 D8); the compatibility pack never
  contains them.

### D2. First starter content (small and complete)

About 8 materials and 10 rules. Exact values are open question Q1.

- Materials: stone, flint, wood/branch, fibre/vine, fruit, water, grass, clay.
- Craftable items: sharp flake, stone axe, cord, container, fire, simple shelter.
- World rules: fruit regrowth, fruit decay, fire burning out, tool wear.
- **[Owner]** The unique canteen stays. Craftable containers are added
  alongside it.
- **[Owner]** At least one starter rule goes against common sense through a
  deceptive appearance (ADR 0007 D4). For example, a vine that looks strong
  snaps under load, while dry grass twisted into cord holds. The model may
  already know how stone, wood and vine combine, so a first success on an
  ordinary recipe can come from prior knowledge. Learning from life on the
  island is best shown on a rule like this (ADR 0014 D2).

### D3. Balance constraints

- Every starter-pack change runs the P2 seed matrix. Survival metrics (for
  example survival rate and first-day water access) must stay within a
  tolerance of the compatibility-pack baseline. The tolerance is open
  question Q2.
- Hard constraint: no content may provide food or water cheaper than the
  baseline unless the owner approves it. Craftable containers fall under this
  constraint because they let residents carry more water (open question Q3).
- **[Owner]** Two goals sit beside the survival constraint. Survival leaves
  spare time in a day for exploring, crafting and talking. Each craftable item
  gives a benefit the resident can perceive, for example a stone axe that cuts
  faster. Both are tuned through where materials lie, crafting cost, durability
  and effect, within the survival constraint. Time use is measured (ADR 0014
  D1); how much spare time is enough is Q6.

### D4. Separation from the engine

- Packs live in `content/packs/<pack>/`, each with its own version and hash.
- Engine tests use a dedicated synthetic test pack, never the starter pack, so
  any recipe-specific engine code makes engine tests fail or go uncovered.

## Consequences

- Balance work moves from engine constants to content and regression runs.
- The compatibility pack doubles as the first real test of the rule language.

## Open questions

| ID | Question |
|---|---|
| Q1 | Exact properties, recipes and values for the starter pack. |
| Q2 | The tolerance band for survival metrics against the baseline. |
| Q3 | Craftable container capacity and cost, so carried water does not undercut the canteen and spring balance. |
| Q4 | Where new materials appear on the map, and whether the default map changes. |
| Q5 | Does the starter pack replace `content/worlds/default.toml`, or sit beside it? |
| Q6 | How much spare time a day should leave beyond survival, and how the benefit of each craftable item is checked. |
