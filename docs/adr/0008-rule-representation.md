# ADR 0008: Rule representation

- Status: **Accepted** (owner M11, 2026-11-17). Existing specs stay in force
  until this ADR's spec replaces them.
- Date: 2026-11-15.
- Baseline: `bf5ed7d` (`task/P3.5-PR-01-protocol-adr`).
- Phase: P3.5, system 2 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: how entities, materials and transformation rules are written as data.
  Execution is ADR 0009; concrete content is ADR 0010; the action shape is ADR 0007.
- Spec to be written: `docs/spec/rule-representation-v0.1.md`.
- Supersedes on acceptance: the entity and resource parts of `world-rules-v0.1.md`.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.

## Context

In v1, entity kinds (`EntityType`), terrain and every transformation are fixed in
`world/protocol.py` and engine code. ADR 0007 moves the transformations into a rule
library resolved by a generic `act` action. That library needs a representation that
is pure data, uses closed vocabularies, can be validated, and enforces conservation,
so that rules proposed later by an LLM (layer C) pass the same checks as authored ones.

## Decision

### D1. Entities are composed from components

- **Material**: a named set of properties, for example wood = hardness 2,
  flammable, buoyant.
- **Component**: one behaviour plus its state, chosen from a closed vocabulary,
  for example `bears_fruit` (stock, regrow interval), `grows`, `container`
  (capacity, contents), `shelter`, `durability`, `footprint`.
- **Archetype**: a content template = material + components + default state.
- **Entity**: an instance of an archetype with its own ID and state.

Example: a fruit tree = material `wood` + `bears_fruit` + `grows`.

### D2. Properties

- Values are small integer scales (0–5) or booleans. No floats, matching the
  v1 rule that physical values are integers.
- Each property declares its observability (`visible`, `on_inspect`, `on_use`;
  ADR 0007 D4).
- A material or instance may declare an apparent value that differs from the
  true value (ADR 0007 D4). Perception reports the apparent value; settlement
  always uses the true value.

### D3. Rule structure

- **[Owner]** Inputs are matched in a hybrid way: each slot is a property
  predicate, and a predicate may also name a material directly.
- **[Owner]** An output may inherit the material of an input slot
  (`material_from`), so one rule covers a flint axe and a stone axe with
  different properties.
- **[Owner]** A rule may declare a success chance as an integer per-mille value.
  Draws use the seeded world RNG in a fixed order (ADR 0009 D1).

```toml
[[rule]]
id = "make_stone_axe"
trigger = "verb:combine"
inputs      = [{ slot = "head",   where = { hardness_min = 4, sharp = true }, qty = 1 },
               { slot = "handle", where = { material = "wood", shape = "long" }, qty = 1 },
               { slot = "bind",   where = { flexible = true }, qty = 1 }]
instruments = []
conditions  = { actor_awake = true }
work_ticks  = 6
on_interrupt = "keep_progress"
success_per_mille = 1000
outputs     = [{ archetype = "axe", material_from = "head" }]
effects     = []
phenomena   = { success = "fits_together", unmet = "falls_apart", failed_chance = "slips" }
conservation = { matter = "inputs_to_outputs" }
```

Fields: `id`, `trigger`, `inputs`, `instruments`, `conditions`, `work_ticks`,
`on_interrupt`, `success_per_mille`, `outputs`, `effects`, `phenomena`,
`conservation`. Effects come from a closed operation set: create, consume,
set component state, move, and a bounded change to the actor's own needs
(needed because rest and sleep are rules, ADR 0007 D2).

**[Owner]** Need changes are bounded per tick, not per application: a rule's
total need change divided by its `work_ticks` may not exceed the per-need rate
limit. Otherwise a one-tick "nap" repeated ten times would restore more than ten
ticks of sleep.

### D4. One format for actor and world rules

`trigger` is `verb:<verb>` for actions, `every:<ticks>` for periodic world
change (regrowth) or `when:<condition>` for conditional change (decay). World
dynamics are content, not engine code.

### D5. Structures

A structure is an entity with `footprint` and functional components such as
`shelter` or `container`. It is built through a construction-site process
entity that receives contributions (ADR 0007 D6). The first version supports
single-tile structures only.

### D6. Ownership

**[Owner]** An entity may record an `owner_id` (the maker, or the recipient of a
`give`), separate from where it is or who holds it. The world records ownership
as a fact and exposes it in events.

**[Owner]** Ownership restricts nothing. Any resident may pick up, use or take
an item that another resident owns, including the outputs of a process entity;
the world never refuses it. Taking without consent is a social act that others
may see (ADR 0007 D10), not a physical impossibility. This replaces the v1 rule
of no theft (`world-rules-v0.1.md` §4.2) for P3.5.

### D7. Validation and conservation

A static validator runs when content loads, and again on every rule proposed
later:

1. Every referenced vocabulary term, archetype and component exists.
2. All values are integers or booleans within declared ranges.
3. Matter is conserved by conservation class: outputs never exceed inputs.
4. Anything that appears from nothing (fruit regrowth) must be a declared
   source with a bounded rate.
5. No chain of rules multiplies matter in a cycle.
6. Need effects are bounded per tick of work (D3).

## Consequences

- New materials, tools and structures are content only.
- The vocabularies (properties, components, effects, phenomena) become the
  slow-changing layer and need their own versioning (ADR 0007 D1).
- Property predicates make balancing harder: one rule can match more items
  than the author expected. Validator reports should list every archetype a
  slot can match.

## Open questions

| ID | Question |
|---|---|
| Q1 | The first property and component vocabularies (shared with ADR 0010). |
| Q2 | Do success chances depend on inputs or skill (for example, a harder head raises the chance), or are they fixed per rule? |
| Q3 | Resolved by the owner, 2026-11-16: ownership is only a recorded fact and restricts nothing (D6). |
| Q4 | How is matter measured for conservation: unit count, or a mass value per archetype? |
| Q5 | When several outputs inherit from inputs, which properties are inherited and which come from the archetype? |
