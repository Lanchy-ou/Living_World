# Living Island — Rule Representation v0.1 (P3.5 v2 lane)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §13 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
> Rework 1 (2026-11-18) answers the Gate 2 world-track review
> ([review](../tasks/p3.5/P3.5-SP-01-review-world.md) B04–B10, B12, N02) and
> uses the protocol as amended by CR-010.
>
> Implements [ADR 0008](../adr/0008-rule-representation.md). Works with the
> frozen [world–agent protocol](world-agent-protocol-v0.1.md), which names the
> vocabulary kinds this spec defines. When frozen, it supersedes for new work
> in the v2 lane the entity and resource parts of `world-rules-v0.1.md` (§1.1
> entity domains, §2 entity and resource state, §3 resource balance rules).
> Those parts stay in force for v1 runs.

**Conventions.** As in the protocol spec. Content examples use TOML, the
format of content files; the parsed form is what is hashed and validated.
Values in examples are placeholders unless this spec says otherwise; real
values are in the starter-content spec.

## 0. Scope and layers

### 0.1 Covered here

- The vocabulary registry: needs, properties and descriptors, matter classes,
  verbs and phenomena (ADR 0007 D1, D9).
- The closed sets that the engine implements: components, predicate keys,
  condition kinds, effect operations and trigger forms.
- Materials, archetypes and placed instances, with true and apparent values,
  tells and stacks.
- The rule format, slot matching, specificity, phenomena and world rules.
- The attempt descriptor and the condition context, which share one
  representation (ADR 0007 D9).
- The static validator and conservation.
- Rule identity, provenance and hashes.

### 0.2 Owned elsewhere

| Subject | Spec |
|---|---|
| How and when rules are settled, tick phases, chance rolls, process progress, entity IDs, events of rule effects, snapshots | `world-engine-v0.1.md` |
| The packs, their files and every value (rates, durations, recipes, placements, thresholds, descriptor tables) | `starter-content-v0.1.md` |
| Intent, perception and feedback shapes | `world-agent-protocol-v0.1.md` (frozen) |

### 0.3 Three sets with three change processes

| Set | Defined by | Changes by |
|---|---|---|
| Components, predicate keys, condition kinds, effect operations, trigger forms | This spec | A new spec version and engine code |
| Needs, properties, matter classes, verbs, phenomena | The vocabulary file (§2) | A new vocabulary version and hash (ADR 0007 D1) |
| Materials, archetypes, instances, rules | Content packs | Content only |

A pack can use only what the first two sets define. It can never add a
component, a condition kind or an effect operation, because those need engine
code (ADR 0010 D4).

## 1. Identity, versions and hashes

- The vocabulary file declares `vocabulary_version`, for example `"vocab/0.1"`.
  `vocabulary_hash` is the SHA-256 of the canonical encoding of the parsed
  vocabulary (`interface-contract-v0.1.md` §6.3).
- Every rule has `rule_id`, `content_hash` and `provenance` (ADR 0007 D9).
  `content_hash` is the SHA-256 of the canonical encoding of the parsed rule
  without `provenance`.
- `rule_library_hash` is the SHA-256 of the canonical encoding of the array of
  active rules, sorted by `rule_id` in byte order, each with its provenance.
- IDs of every kind (`NeedId`, `PropertyId`, `MatterClassId`, `VerbId`,
  `PhenomenonId`, `MaterialId`, `ArchetypeId`, rule IDs, condition IDs, slot
  names) match `[a-z][a-z0-9_]{0,47}`. Each kind is its own namespace, except
  that within one rule the slot names (`target` included) and condition IDs
  share one namespace, the namespace of `failed_check`. `world_limit` is
  reserved in it (§3.3).
- A run manifest pins the vocabulary hash and the rule library hash (protocol
  §1). A save with different hashes is refused (ADR 0009 D5).

## 2. The vocabulary file

One file per vocabulary version, shared by all packs. A pack names the
vocabulary version and hash it was written for, and the loader refuses a
mismatch. A pack chooses which verbs and needs it enables (§2.4, §2.1).

### 2.1 Needs

```toml
[[need]]
id = "satiety"
polarity = "higher_is_better"   # or "higher_is_worse"
```

- A need is a world quantity of a living resident: an integer between the
  pack's `min` and `max` (protocol §5.1). The pack gives the range, the
  initial value, the band cutoffs, the named thresholds and the rate limits.
- **Condition value.** The protocol's bands, thresholds and crossings read a
  need from worst to best. For a `higher_is_better` need the condition value
  is `c = v − min`; for a `higher_is_worse` need, `c = max − v`. Both run over
  `0..(max − min)`, with 0 the worst. Band cutoffs and thresholds are given
  on `c`, within that range. Every pack in this version has `min = 0`, so for
  the compatibility needs `c = v` and the v1 cutoffs are unchanged. For
  example, mental fatigue stored as 9500 of 10000 has `c = 500`: deep in its
  critical band. "Mental fatigue at its maximum" (protocol §4.4) is
  `v = max`, so `c = 0`. The `need` condition kind (§3.3) reads the stored
  value `v`, not `c`.
- **Named thresholds** are declared in the pack, per need, carried from
  protocol §5.3:

  ```toml
  [needs.satiety]
  thresholds = [{ id = "urgent", at = 3000, wakes = true }]
  ```

  `at` is a condition value. A crossing is the protocol's: `c` goes from
  above `at` to at or below it during a tick. `wakes = true` is the waking
  mark of protocol §6.3. Threshold IDs are unique per need.
- **Rate limits.** The pack gives, per need, `max_gain_per_tick` and
  `max_loss_per_tick` (nonnegative integers). They bound rule effects
  (§5.5, ADR 0008 D3). They do not bound base physiology (engine spec).

### 2.2 Properties and descriptors

```toml
[[property]]
id = "hardness"
domain = "scale"                 # "scale" (0..5), "bool" or "count"
observability = "visible"        # "visible", "on_inspect" or "on_use"
descriptors = [{ upto = 1, word = "soft" }, { upto = 3, word = "firm" }, { upto = 5, word = "hard" }]
default = 0
```

- `scale` values are integers 0–5 and `bool` values are booleans, as ADR 0008
  D2 says. They describe materials and archetypes.
- `count` values are nonnegative integers. A `count` property never describes a
  material or an archetype; it only names how an archetype shows one of its
  component fields (§4.2, `observe`), such as the fruit on a tree.
- `descriptors` map values to words, the `DescriptorValue` of the protocol.
  For `scale` and `count`, entries are in increasing `upto` order and the last
  covers every larger value; a value takes the first entry with `value ≤ upto`.
  Several values may share a word, so descriptors are coarse. For `bool`, the
  table has exactly two entries, `{ value = true, word = ... }` and
  `{ value = false, word = ... }`. Words are unique within a property.
  A `visible` or `on_inspect` property must have a table. An `on_use`
  property has none (`descriptors = []`), because it is never shown as a
  descriptor (protocol §5.1); it shows only through phenomena.
- `observability` is fixed per property (ADR 0008 D2). Protocol §5.2 says what
  each level shows. An `on_use` property may still be a rule predicate; it shows
  only through phenomena.
- `default` is the value of an entity whose material and archetype both leave
  the property out.
- Progress uses the built-in property `progress`: three words by thirds of
  the work, `started` while `3 × done < need`, `halfway` while
  `3 × done < 2 × need`, otherwise `nearly_done`. It is not declared in the
  file, and its words are fixed by this spec.
  - For a process entity, `done` is `process.work_done` and `need` is the
    archetype's `process.work_required` (§3.1).
  - For an actor's own timed action (protocol `running_action.progress`),
    `done` is the elapsed work ticks and `need` the action's chosen work time
    (`work_ticks`, the `duration_param` value, or the kernel duration).
  - It is `null` for an action without a fixed duration (`move_to`), for an
    attempt that will fail at its end (`invalid_attempt_ticks` or
    `attempt_ticks` of an unmet or unmatched start) and for a one-tick action.
  - A `progress_step` report (protocol §5.3) is built when the word changes.

### 2.3 Matter classes

```toml
[[matter_class]]
id = "plant"
```

A matter class is a conservation unit (§8). Every archetype says how many
units of each class one unit of it holds.

### 2.4 Verbs

Carried from protocol §4.3 and §14.

```toml
[[verb]]
id = "fill"
description = "Fill something you hold with water."      # short text for the system instructions
target = { kinds = ["entity"], class = "container", must_be_held = true }
reach = { min = 0, max = 1 }
params = []
```

| Field | Meaning |
|---|---|
| `target.kinds` | Subset of `tile`, `entity`, `resident`, or `[]` for no target. A verb with `[]` takes no target |
| `target.class` | Optional component name (§3.1) the target entity must have; a mismatch is `INVALID_TARGET` (protocol §4.3 check 3) |
| `target.must_be_held` | The target must be in the actor's inventory; otherwise `NO_ITEM` (check 4) |
| `reach` | Manhattan distance range from the actor's tile to the target's tile (check 5). A held target is always within reach |
| `params` | The closed parameter shape: a list of `{name, type = "integer", min, max}` |
| `awareness_during` | Optional; `"asleep"` makes the actor asleep while the action runs (`sleep`) |
| `duration_param` | Optional; names the parameter that sets the matched rule's work time (`sleep`, §5.4) |

- The schema of a turn is generated from the enabled verbs' `id`, `target`
  and `params` (protocol §10). `description` goes into the system
  instructions (decision-loop spec). Rules never do.
- A verb sets no limit on how many instruments or inputs an intent lists:
  the protocol's shape checks (§3.4 there) are unchanged. An intent with more
  items than any rule has slots simply matches no rule (§5.2).
- `attempt_ticks` is a pack value per verb, at least 1 (owner, PR-D2).
- A pack lists the verbs it enables. Only enabled verbs appear in the schema.

### 2.5 Phenomena

```toml
[[phenomenon]]
id = "snaps"
text = "it snaps"                # short neutral wording shown to residents
watcher_visible = true
```

- Phenomena are the only rule feedback a resident gets (protocol §4.1).
- `watcher_visible` marks what a watcher in sight sees (protocol §5.4, ADR
  0007 D10). Sensations inside the actor ("no longer hungry") are not visible;
  physical events ("it snaps", "smoke rises") are.
- `text` never names a rule, a condition, a property value or a number.

### 2.6 The first vocabulary, `vocab/0.1`

Recommended members (owner, RR-D4). The verbs fix ADR 0007 Q3; the starter
pack's needs for each term are in the starter-content spec.

| Kind | Members |
|---|---|
| Needs | `satiety`, `hydration`, `stamina`, `health` (`higher_is_better`); `mental_fatigue` (`higher_is_worse`) |
| Matter classes | `mineral`, `plant`, `water` |
| `scale` properties | `hardness` (visible), `strength` (visible), `weight` (on_inspect) |
| `bool` properties | `sharp` (visible), `long` (visible), `dry` (visible), `flexible` (on_inspect), `malleable` (on_inspect), `flammable` (on_use), `edible` (on_use), `brittle` (on_use), `watertight` (on_use) |
| `count` properties | `fruit_amount` (visible), `stock_amount` (visible), `water_amount` (visible), `wear_state` (visible), `fire_state` (visible) |
| Compatibility verbs | `gather`, `eat`, `drink`, `fill`, `rest`, `sleep` |
| Starter verbs | `combine`, `strike`, `cut`, `light`, `build` |
| Phenomena | `picks_fruit`, `takes_some`, `finds_nothing`, `hands_full`, `too_tired`, `tastes_good`, `tastes_bad`, `not_hungry`, `drinks`, `not_thirsty`, `no_water_here`, `fills_up`, `already_full`, `rests`, `sleeps`, `nothing_happens`, `leaves_dent`, `chips_off`, `splits`, `cuts_through`, `does_not_cut`, `fits_together`, `falls_apart`, `slips`, `snaps`, `holds_firm`, `smokes`, `catches_fire`, `fizzles`, `site_marked`, `ground_unsuitable` |

Verb declarations of `vocab/0.1`:

| Verb | Target kinds, class, held | Reach | Params |
|---|---|---|---|
| `gather` | entity, class `store` | 1–1 (v1) | — |
| `eat` | none | — | — |
| `drink` | none | — | — |
| `fill` | entity, class `container`, held | 0–1 | — |
| `rest` | none | — | — |
| `sleep` | none | — | `duration_ticks` 6–54 (PR-D4); `awareness_during = "asleep"`, `duration_param = "duration_ticks"` |
| `combine` | none | — | — |
| `strike` | entity | 0–1 | — |
| `cut` | entity | 0–1 | — |
| `light` | entity | 0–1 | — |
| `build` | tile | 0–1 | — |

- The compatibility verbs copy the v1 reach and target rules (protocol §11.2):
  v1 `gather` needs distance exactly 1 (`world/actions.py` `validate`).
- `wait`, `give`, `pick_up`, `drop`, `inspect`, `contribute` and `move_to` are
  kernel actions, not verbs (protocol §3.2).

## 3. Closed sets defined by this spec

### 3.1 Components

ADR 0008 D1 names `bears_fruit` and `grows` as examples. This version covers
them with `store` plus a regrowth world rule (§5.8), which also serves deposits
of stone or grass; no separate growth component is needed.

| Component | State fields | Meaning |
|---|---|---|
| `portable` | `slots_per_unit:int≥1` (static) | The entity can be held and moved by kernel transfers. Without it, `pick_up` is `INVALID_TARGET` |
| `store` | `archetype:ArchetypeId` (static), `count:int`, `capacity:int` (static) | Holds counted units of one portable archetype that are not separate entities, such as fruit on a tree. `move` out of a store creates or grows a stack. The count is matter: only `move`, sourced `create` and `consume` change it (§8) |
| `container` | `capacity:int` (static), `accepts:Predicate` (static) | Holds item entities. Used units are the sum of `quantity × slots_per_unit` of its contents. The `accepts` predicate of a portable container must match no archetype that has `container`, so containers never nest into a cycle (§7) |
| `durability` | `wear:int`, `max_wear:int` (static) | Tool wear. Effects add wear; a `when:` rule acts on it |
| `fuel` | `ticks_left:int` | Burning time left, such as a fire |
| `shelter` | — | A marker that rule conditions can look for |
| `footprint` | `blocks_movement:bool`, `opaque:bool` (static) | A single-tile structure on a tile (ADR 0008 D5) |
| `process` | `work_done:int`, `work_required:int≥1` (static) | A process entity. It must also have `container`, which holds its materials (ADR 0007 D6). Every process rule of the archetype requires `work_required` (§5.8), so progress has one total |

- Every entity also has engine fields: `entity_id`, `archetype_id`,
  `material_id`, `quantity`, `created_tick`, `owner_id`, and a place (a tile,
  or a holder: a resident, a container or a process). `age = tick −
  created_tick` is a derived field.
- Residents and corpses are engine entities, not archetypes. Rules may target
  them where a verb allows `resident`; they have no components.
- Static fields are set by the archetype, or by an instance at placement
  where the archetype leaves them open (for example the archetype a
  `deposit`'s store holds), and never change afterwards.

### 3.2 Predicate keys

A predicate (`where`) is a table of keys. All keys must hold.

| Key | Holds when |
|---|---|
| `archetype = "<id>"` | The entity's archetype is that one |
| `material = "<id>"` | The entity's true material is that one (ADR 0008 D3) |
| `has_component = "<name>"` | The entity has that component |
| `<bool property> = true\|false` | The true value equals it |
| `<scale property>_min = n`, `<scale property>_max = n` | The true value is at least or at most `n` |

- Predicates test **true** values, never apparent ones (ADR 0008 D2).
- Each key counts as one predicate for specificity (§5.3).
- A predicate on a `count` property is not allowed; use a `state` condition.

### 3.3 Condition kinds

Each condition in a rule has an `id`, unique within the rule, and one kind.
Every condition reads only fields of the condition context or of a slot
signature (§6), so it can be evaluated on a recorded attempt.

| Kind | Fields | Holds when | Allowed in |
|---|---|---|---|
| `awareness` | `value = "awake"\|"asleep"` | The actor's awareness equals it | Verb rules |
| `need` | `need`, `op`, `value` (an integer, `"min"` or `"max"`) | The actor's stored need value `v` compares true | Verb rules |
| `free_slots` | `op`, `value` | The actor's free inventory slots compare true | Verb rules |
| `terrain_near` | `terrain`, `distance = {min, max}` | A tile with that terrain lies within the distance range of the reference tile | All |
| `entity_near` | `where`, `distance = {min, max}` | An entity matching the predicate lies within the range | All |
| `terrain_at` | `of = "target"\|"actor"\|"subject"`, `terrain` | That tile has that terrain | All |
| `state` | `of = "target"\|"slot:<name>"\|"subject"`, `field`, `op`, `value` | The field compares true | All |
| `time_phase` | `value = "day"\|"night"` | The completed tick's phase, as v1 daylight (`world-rules-v0.1.md` §1.3) | All |
| `work_complete` | — | The subject process's `work_done` is at least its `work_required` | Process rules only (§5.8) |

- `op` is one of `<`, `<=`, `==`, `!=`, `>=`, `>`.
- `state.field` is one of `quantity`, `store.count`, `store.free`
  (`capacity − count`), `container.used`, `container.free`,
  `container.count:<archetype>`, `durability.wear`, `durability.left`
  (`max_wear − wear`), `fuel.ticks_left`, `process.work_done`, `age`.
- The reference tile of `terrain_near` and `entity_near` is the actor's tile in
  a verb rule and the subject's tile in a world rule. A held entity's tile is
  its holder's tile.
- `distance.max` is at most `condition_radius`, 2 in this version, so every
  condition fits in the recorded context (§6).
- Conditions are checked in declared order; the first that fails is the
  `failed_check` (protocol §4.3). The full check order of a rule is in §5.2.
- `failed_check` is a slot name (`target` or an instrument or input slot) or a
  condition ID, from the rule's one namespace (§1).
- **The implicit `world_limit` condition.** Every rule whose effects can
  raise the engine's entity count or place an entity on a tile (a `create`
  of an entity, a `move` out of a store, a `partial` or `keep_progress`
  output) has one more condition, after its declared ones: `world_limit`, which holds when the engine's entity limits
  admit every placement of the branch about to apply (engine spec §12). It is
  a real condition of the rule, so a refusal is an ordinary `unmet` with
  `failed_check = "world_limit"` (protocol §4.3), checked before anything is
  spent. No slot or declared condition may use that name.
- A `need` condition whose need the same rule changes with a `per_tick`
  effect is refused (§7, `BAD_SHAPE`): the rule's own work would change the
  answer at completion. For example, a rest that requires stamina below its
  maximum and gains stamina each tick could invalidate itself.

### 3.4 Effect operations

The closed set of ADR 0008 D3: create, consume, set component state, move, and
a bounded change to the actor's own needs.

| Operation | Fields | Effect |
|---|---|---|
| `create` (in `outputs`) | `archetype` or `archetype_from = "<slot>"`, optional `material` or `material_from = "<slot>"`, `quantity` (§3.4.1), `at`, optional `source` | Creates new matter. Without `source` it is made from the rule's consumed inputs and destroyed entities (§8); with `source` it comes from a declared source |
| `consume` | `of` (`"subject"`, `"target"` or a contents reference such as `"slot:canteen.contents"` or `"subject.contents"`), `archetype` (for contents), `quantity` (§3.4.1; for `subject` and `target`, omitted means the whole entity) | Destroys matter (a sink) |
| `move` | `from` (`"target.store"`, `"subject.store"`, a contents reference), `to` (a place), `quantity` (§3.4.1) | Moves matter without changing it |
| `set_state` | `of`, `field` (a non-static component field other than `store.count`), `set` or `add` | Changes component state, clamped to the field's bounds (`0..max_wear`, `≥ 0`). It never changes matter: `store.count` and contents change only through `create`, `consume` and `move` (§8) |
| `need` | `need`, `delta`, `timing = "per_tick"\|"completion"` | Changes the actor's stored need value, clamped to its range. `per_tick` applies each tick of work; `completion` applies once at settlement |

#### 3.4.1 Quantities, references and materials

- **Quantity** is one of: an integer `n ≥ 1`; `{ of = "<ref>" }`; or
  `{ upto = n, of = "<ref>" }`, the smaller of `n` and the reference. The
  closed set of references:

  | Reference | Value |
  |---|---|
  | `subject.quantity`, `target.quantity` | That entity's quantity |
  | `slot:<name>.quantity` | The units resolved into that slot |
  | `fit:<place>` | How many units of the output's archetype fit at that place: a store's `capacity − count` if it holds that archetype, else 0; a container's free capacity divided by the archetype's `slots_per_unit`, rounded down, if `accepts` admits it, else 0 |
  | `<store place>.count` | A store's count, such as `target.store.count` |

- **Capture.** Every reference is read once, before any effect of the
  settlement applies, and the effects use the captured values. For example,
  `fruit_rots` consumes its whole subject stack and creates
  `{ of = "subject.quantity" }` rotten fruit: both use the quantity the stack
  had before the consume.
- A quantity that evaluates to 0 makes that effect do nothing. A rule that
  should then not apply says so with a condition, as the gather rule's
  `stock` does.
- **Material of an output**: `material` if given, else the material of the
  item in `material_from`, else the archetype's default material, else none
  (`material_id = null`). `archetype_from = "<slot>"` takes the archetype of
  the item in that slot. A `material_from` or `archetype_from` slot must hold
  items of one material and one archetype; otherwise it does not fill (§5.2).
  Structures and processes such as a fire or a shelter site have no
  material unless the rule names one.
- **Returning items.** A rule that gives items back creates them anew with
  `archetype_from` and `material_from` of their slot. For example, when a
  binding snaps, `bind_snaps` consumes head, handle and cord and creates a
  head and a handle of the same archetype and material (new entity IDs);
  inputs are always consumed (protocol §3.2).

- **Places** (`at`, `to`): `"actor"` (the actor's inventory, or the actor's
  tile when the inventory has no room), `"actor.tile"`, `"target.tile"`,
  `"target.contents"`, `"target.store"`, `"subject.tile"`,
  `"subject.contents"`, `"subject.store"`, and `"subject.place"` (wherever
  the subject itself is: a tile, an inventory or a container). A store accepts
  only its own archetype.
- Consuming an entity that holds contents first places its contents on its
  tile, and a store's count as a stack of the store's archetype, so nothing
  inside is lost without a rule saying so (§8.1).
- **Inputs are consumed** at a successful settlement, and instruments never
  are (protocol §3.2). A rule does not list `consume` for its inputs.
- **One role per entity.** The target entity must be distinct from every
  resolved instrument and input stack; if it is not, the intent fills no slot
  set and matches no rule (§5.2). So one item is never debited twice.
- `create` of a stackable item merges into an equal stack at the place (§4.5).
- An item created by a verb rule records the actor as `owner_id` if it is not
  stackable (§4.6).
- `need` effects apply only to the actor of a verb rule. World rules have no
  actor and cannot change needs; base physiology is the engine's.

### 3.5 Trigger forms

The three forms of ADR 0008 D4:

| Trigger | Fires | Subject |
|---|---|---|
| `verb:<verb>` | When an actor's `act` with that verb starts | The actor and the intent's target and items |
| `every:<n>` | At each completed tick `k` with `k mod n = phase` | Each entity that matches the rule's `subject` predicate. `phase` is the entity's `phase_offset` for this rule (§4.4), or 0 |
| `when:<condition id>` | At each completed tick at which all the rule's conditions hold for a subject, and its slots are filled. The named condition is the trigger the engine indexes on | Each entity that matches `subject` |

`every:` and `when:` rules are world rules. They run in the engine's world-rule
phase (engine spec), in `rule_id` order, then entity ID order (ADR 0009 D3).
A world rule never settles as unmet or unmatched: when its conditions do not
hold for a subject, nothing happens. A `when:` rule fires again at every tick
at which it still holds, so its effects should end the condition, as consuming
a broken tool does. A `when:` rule may not use a source (§8.2), since its rate
would have no bound.
Process rules are `when:` rules whose named condition is `work_complete`
(§5.8). They run after the other world rules, one chosen rule per process
(§5.8, engine spec).

## 4. Materials, archetypes and instances

### 4.1 Material

```toml
[[material]]
id = "vine"
properties = { strength = 1, flexible = true, flammable = true }   # true values
apparent   = { strength = 4 }                                       # what perception shows
```

- `properties` are true values of `scale` and `bool` properties.
- `apparent` overrides what perception shows for listed properties
  (ADR 0007 D4). Settlement always uses true values. A material shown to a
  resident is always shown with its true `material_id` (protocol §5.2,
  owner PR-D3), so a resident can learn that vines look strong and snap.

### 4.2 Archetype

```toml
[[archetype]]
id = "fruit_tree"
kind = "feature"                 # "item", "structure", "process" or "feature"
material = "wood"                # default material, or omitted
stackable = false
matter = {}                      # units per class for one unit; features may hold none
properties = {}                  # archetype-level true values (shape)
components = { store = { archetype = "fruit", capacity = 5 } }
observe = [{ field = "store.count", as = "fruit_amount" }]
```

- `kind` is the `EntityView.kind` of protocol §5.1.
- `matter` gives the units of each matter class in one unit of this
  archetype. A portable archetype must have at least one unit of some class;
  features, structures and processes may have none, since their matter is held
  in their components or was consumed to build them.
- `observe` shows component fields as `count` properties. The field's
  observability is the named property's.
- Component defaults come from the archetype; an instance gives the rest of
  the state (§4.4).

### 4.3 Property values and inheritance

For an entity of archetype `A` and material `M`, the **ordinary value** of
property `P` is `A.properties[P]` if declared, else `M.properties[P]`, else
the property default. The **true value** is the instance's own true value
(§4.4) if declared, else the ordinary value. The **apparent value** is the
instance's apparent override (§4.4) if declared, else `M.apparent[P]` if
declared and `A` does not declare `P` and the instance declares no own true
value of `P`, else the true value.

**Inheritance** (ADR 0008 D3, Q5; owner, RR-D3). An output with
`material_from = "<slot>"` takes the material of the item in that slot: all of
its true and apparent material values. Archetype properties of the output
still win over material ones. Instance values of the input (own true values,
apparent overrides and tells) are never inherited; the output is an ordinary
instance of its material. For example, a
flint head and a stone head give two axes of the same archetype whose
`hardness` differs, because hardness is a material property, while `sharp` is
set by the `axe` archetype.

### 4.4 Placed instances, apparent overrides and tells

A pack places instances at run start (starter-content spec):

```toml
[[instance]]
id = "grass_patch_03"
archetype = "grass_tuft"
material = "grass"
at = { tile = [20, 31] }          # or { holder = "<resident or entity ID>" }
quantity = 3
state = {}                        # component state, within bounds
phase_offset = { fruit_regrowth = 48 }   # optional, per every: rule ID
properties = { strength = 4, dry = true } # optional own true values
apparent = { strength = 1 }       # optional apparent override
tell = ["dry"]                    # required when apparent is present
owner_id = "ryan"                 # optional
```

- **Own true values.** An instance may declare true values of `scale` and
  `bool` properties for itself (`properties`). They win over the archetype
  and material (§4.3) and make this instance differ from ordinary ones of the
  same archetype and material. The `material_id` stays the material's.
- **Tells** (carried from protocol §5.2). An instance with an `apparent`
  override must list at least one tell: a `visible` or `on_inspect` property
  that the instance gives an own true value differing from its ordinary value
  (§4.3), and that is not itself in `apparent`. So the instance carries a
  genuine, perceivable difference. The example above is a grass tuft that is
  stronger than it looks, and its tell is that it is dry where ordinary grass
  is not; a resident who inspects or looks closely can notice. The validator
  refuses an override without a valid tell (`TELL_MISSING`). The world never
  says what a tell means.
- Instance IDs are content IDs. Entities created during a run get engine IDs
  (engine spec), which never collide with content IDs.
- `phase_offset` replaces the v1 `regrow_phase_offset_ticks` of each tree. It
  must lie in `0..n−1` for an `every:<n>` rule.

### 4.5 Stacks

- A `stackable` archetype is held and shown as stacks: one entity with a
  `quantity` (protocol §5.1). A non-stackable entity always has quantity 1.
- Two stacks are **equal** when archetype, material, component state, own true
  values, apparent overrides and tells are equal. Stackable items carry no
  `owner_id` (§4.6).
- Adding items to a place merges them into an equal stack already there, which
  keeps its ID. With none there, a new stack is created. Splitting a stack gives
  the moving part a new ID (protocol §5.1).
- On the ground, equal stacks on one tile are always merged. The protocol's
  equivalence projection compares the total per tile, which is the v1 ground
  pile (`world-rules-v0.1.md` §2, protocol §11.3).
- `age` of a stack is that of its oldest unit: merging keeps the smaller
  `created_tick`. A content author who wants fresh and old fruit kept apart
  gives them different states.

### 4.6 Ownership

- A non-stackable entity may have `owner_id` (ADR 0008 D6). It is set to the
  actor when a verb rule creates the entity, to the recipient by `give`, and by
  content at placement. `pick_up`, `drop` and world rules never change it.
- Stackable items carry no owner (owner, RR-D6): merging would otherwise mix
  owners in one stack. Who gave or took fruit stays in the objective events
  (`item_transferred`, protocol §9).
- Ownership restricts nothing (protocol §8).

## 5. Rules

### 5.1 Fields

```toml
[[rule]]
id = "make_stone_axe"
trigger = "verb:combine"
target = {}                                  # omitted: the rule takes no target
instruments = []
inputs = [{ slot = "head",   where = { hardness_min = 4, sharp = true }, qty = 1 },
          { slot = "handle", where = { material = "wood", long = true }, qty = 1 },
          { slot = "bind",   where = { flexible = true, strength_min = 3 }, qty = 1 }]
conditions = [{ id = "awake", kind = "awareness", value = "awake" }]
work_ticks = 6
on_interrupt = "lose"
exhaustion_stops = false
success_per_mille = 1000
on_chance_failed = "keep_inputs"
outputs = [{ archetype = "axe", material_from = "head", quantity = 1, at = "actor" }]
effects = []
phenomena = { success = ["fits_together"], unmet = ["falls_apart"], chance_failed = ["slips"] }
```

| Field | Rule |
|---|---|
| `id` | Unique in the library |
| `trigger` | §3.5 |
| `target` | For verb rules: a slot `{ where = ... }` or `{ terrain = "<terrain>" }` for a tile target, or omitted for no target. Must agree with the verb's target kinds |
| `subject` | For world rules only: a predicate on the entities the rule runs over |
| `instruments`, `inputs` | Lists of slots `{slot, where, qty}`; instruments have `qty = 1`. Inputs are always consumed at success (§3.4) |
| `conditions` | Ordered list (§3.3) |
| `work_ticks` | Integer ≥ 1, or `{ param = "<name>" }` when the verb has a `duration_param`. Omitted on process rules, whose work is the archetype's `work_required` |
| `on_interrupt` | `"lose"`, `{ partial = [outputs] }` or `{ keep_progress = "<process archetype>" }` (§5.4) |
| `exhaustion_stops` | `true` makes zero stamina a hard stop `EXHAUSTED` during the action (protocol §4.4) |
| `success_per_mille` | Integer 0–1000, fixed per rule (§5.6) |
| `on_chance_failed` | `"keep_inputs"` or `"consume_inputs"` |
| `chance_failed_effects` | Optional `set_state` effects on instruments that apply on a failed roll (§5.6) |
| `outputs`, `effects` | §3.4 |
| `conservation` | How the outputs arise (ADR 0007 D9 item 4, ADR 0008 D3): `"inputs_to_outputs"` (made from consumed matter, the default), `"source"` (from declared sources only) or `"none"` (no outputs). The validator checks it against the outputs (§8) |
| `phenomena` | Lists of phenomenon IDs for `success`, `unmet` and `chance_failed`, and an optional `unmet_by_check` table from a slot name or condition ID to its own list |
| `provenance` | §5.9; added by the loader for authored rules |

### 5.2 Slots and exact matching

A verb rule **matches** an intent when every rule slot is filled by exactly one
intent item and every intent item fills exactly one slot:

- The target: the intent has a target exactly when the rule has a target slot,
  and the target meets the slot's predicate (or the tile has the slot's
  terrain).
- Instruments: the intent's instruments are assigned one to one to the rule's
  instrument slots, each meeting its slot's predicate.
- Inputs: the intent's input entries are assigned one to one to the rule's
  input slots; each entry's items meet the slot's predicate and its quantity
  equals the slot's `qty`.
- **Assignment order.** When several assignments work, the engine uses the
  first: it tries permutations of the intent's entries in lexicographic order
  of their submitted positions and assigns the `i`-th entry to the `i`-th slot,
  instruments first, then inputs. Only rules with exactly as many slots as
  the intent has entries are tried, and a rule has at most 2 instrument slots
  and 4 input slots (§7, `BAD_SHAPE`), so this is at most 2 × 24 tries.
- An item choice by kind (`{held: archetype}`) is resolved to held items first
  (protocol §3.2); matching sees the resolved items. An entry resolved from
  several stacks keeps its parts: each part (a stack and the units taken from
  it) must meet the slot's predicate, and a slot named by `material_from` or
  `archetype_from` fills only when all parts share one material and one
  archetype (§3.4.1).
- The target must not be one of the resolved instrument or input stacks
  (§3.4); such an intent matches no rule.

This exact rule means the same items always reach the same rule. For example,
`drink` with no instrument matches the spring rule, and `drink` with a canteen
as instrument matches the canteen rule only.

**Slots filled from contents.** A world rule's or process rule's input slots
are filled from the subject's contents, which have no submitted order. The
engine assigns them by depth-first search over the slots in declared order.
For one slot, an allocation is a vector of units taken from each eligible
stack not yet used up, stacks in ascending entity ID, summing to the slot's
`qty`. Allocations are tried in decreasing lexicographic order of that
vector, so the first takes as much as possible from the lowest-ID stack.
A unit is never used twice. When a later slot cannot be filled, the search
returns to the previous slot's next allocation. The first complete
assignment is used; if none exists, the slots do not fill. The same binding
serves the check, the effects and replay.

**Check order.** At start and at completion a verb rule is checked in this
order, and the first failure is the `failed_check`:

1. `target`: it exists, is within the verb's reach and meets the slot's
   predicate (or the tile has its terrain);
2. instrument slots in declared order, then input slots in declared order:
   the bound items still exist, are held and meet the predicates;
3. the declared conditions in order;
4. `world_limit` (§3.3).

A world or process rule uses steps 2–4 over its subject. Matching (which
rule applies) uses only steps 1–2 and the arity; specificity (§5.3) then
orders the matched rules.

### 5.3 Specificity

The specificity of a rule is the number of predicate keys over its target and
all its slots, plus its number of conditions (ADR 0009 D1). A tile target slot
with `terrain` counts one. The settlement order that uses it is in the engine
spec. For example, `sleep` near the cave (one condition) is more specific than
plain `sleep` (none).

### 5.4 Work time and interruption

- A verb rule's work time is `work_ticks`, or the value of the verb's
  `duration_param` in the intent (`sleep`).
- `on_interrupt` applies when the action stops before completion: by a hard
  stop, or because the actor chose another action (protocol §4.4, ADR 0007
  D6):
  - `"lose"`: no output; reserved inputs are released and stay with their
    holder. `per_tick` need effects already applied stay applied, as v1 rest
    and sleep gains do.
  - `{ partial = [...] }`: the listed outputs are created, and the inputs are
    consumed. The partial outputs must conserve matter like any output (§8).
  - `{ keep_progress = "<process archetype>" }`: the engine places a new
    process entity of that archetype on the actor's tile, moves the reserved
    inputs into it and sets `work_done` to the elapsed work. Anyone may then
    `contribute` to finish it. The validator requires a process rule (§5.8)
    for that archetype whose inputs accept those items.
- **When the reservation no longer holds.** `partial` and `keep_progress` use
  only the reserved items that the actor still holds when the stop applies;
  each runs as one atomic branch that the engine checks first (engine spec
  §12). If a reserved item is gone, the entity limits refuse a placement, or
  the actor has died and its inventory has dropped, the mode falls back to
  `lose`: nothing is created and nothing is consumed or moved by the rule.
  For example, `keep_progress` at death leaves no process; the reserved
  materials lie on the ground with the rest of the inventory (protocol §4.4,
  engine spec §10).
- A process rule has no `on_interrupt`: its work stays with the process entity
  when a contributor stops. Whether it decays is the engine spec (ADR 0009 Q4).

### 5.5 Need effects and their bound

- `need` effects change only the actor's own needs (ADR 0007 D2, Q7). Any
  enabled need may be named.
- **Per-tick bound** (ADR 0008 D3). For each need and each sign, with `W` the
  rule's work time, `P` the sum of its `per_tick` deltas of that sign and `C`
  the sum of its `completion` deltas of that sign, the rule must satisfy
  `W × |P| + |C| ≤ W × L`, where `L` is the pack's `max_gain_per_tick` for
  gains and `max_loss_per_tick` for losses. The check uses integers, without
  rounding. For a rule whose work time is a parameter, it uses the
  parameter's minimum, which is the worst case.
- For example, with `max_gain_per_tick = 220` for stamina, a one-tick nap of
  +300 is refused, so ten naps can never beat ten ticks of sleep; and a
  four-tick rule with `+220` per tick and `+880` at completion is refused,
  because `4 × 220 + 880 = 1760 > 880`.
- **When need effects apply.** A `per_tick` delta applies at each tick of
  work, whatever the settlement turns out to be, and stays applied when the
  action stops, is unmet at completion or fails its roll, as v1 rest and sleep
  gains do. A `completion` delta applies only when the rule is `applied`.
  Because a `per_tick` gain would be kept even on a failed roll, a rule with
  `success_per_mille < 1000` may have no `per_tick` need effect (§7).

### 5.6 Success chance

- `success_per_mille` is fixed per rule (ADR 0008 Q2; owner, RR-D1). It
  depends neither on the inputs nor on a skill. A better input can still give
  a better chance through a more specific rule: a rule for heads with
  `hardness_min = 5` and a higher chance beside the general one.
- The world never tracks a resident's skill: a world-side skill would carry
  knowledge across waking periods in both memory arms, as a familiarity count
  would (protocol §5.2).
- The roll is drawn as the engine spec defines (ADR 0009 D1 item 8). On a
  failed roll, `on_chance_failed` decides whether the inputs are kept or
  consumed (ADR 0009 Q3); instruments may still wear through `effects`, which
  apply on success only unless listed under `chance_failed_effects`.
- On a failed roll nothing else of the rule applies: no outputs, no `consume`,
  `move` or `need` effects, and the target is untouched. Only the inputs (if
  `consume_inputs`) and `chance_failed_effects` change anything. For example,
  a failed `light_fire` with `consume_inputs` uses up the tinder in its input
  slot and leaves the target wood as it was.

`chance_failed_effects` is an optional list of `set_state` effects on
instruments, so a slipping tool can still wear.

### 5.7 Phenomena of a settlement

| Settlement (protocol §4.1) | Phenomena |
|---|---|
| `applied` | The rule's `success` list |
| `chance_failed` | The rule's `chance_failed` list |
| `unmet` | The rule's `unmet_by_check` list for the failed check if it has one, else its `unmet` list |
| `unmatched` | The verb's comparison table below |

`unmet_by_check` lets a rule tell physical states apart, for example "not
thirsty" from "no water here" for one drinking rule. Both lists are still the
rule's own phenomena: they describe what the resident would sense, never name
the rule or say which condition failed (ADR 0007 D5).

**Comparison tables for unmatched attempts** (ADR 0007 D5, Q4; owner,
RR-D5). A pack gives each enabled verb an ordered table:

```toml
[unmatched.strike]
entries = [
  { when = { compare = ["instrument.hardness", ">", "target.hardness"] }, phenomena = ["leaves_dent"] },
  { when = { compare = ["instrument.hardness", "<=", "target.hardness"] }, phenomena = ["nothing_happens"] },
]
default = ["nothing_happens"]
```

- `compare` reads true `scale` or `bool` property values of the target, the
  first instrument or the first input (`target.`, `instrument.`, `input.`),
  and compares them with `op` or with an integer.
- The phenomena of an unmatched attempt are the union of the lists of every
  entry whose comparison holds, sorted and unique; if none holds, `default`.
  A comparison whose operand is missing does not hold.
- The tables give physical feel without naming a rule. They read true values,
  as the world would, so a deceptive vine that looks strong still behaves
  weak.
- A table is one unit, named by its verb. A pack that extends another (§5.10)
  may replace a base table by declaring `[unmatched.<verb>]` again with
  `replace = true`; the new table, entries and `default`, takes the base
  table's place entirely. Without `replace = true`, a second table for one
  verb is a `DUPLICATE_ID`. For example, the starter pack replaces the
  `gather` table so that gathering from something that is not a store gives
  `finds_nothing`.

### 5.8 World rules and process rules

- A world rule has `trigger = "every:<n>"` or `"when:<condition id>"` and a
  `subject` predicate. It has no target, instruments, actor, `need` effects or
  `on_interrupt`, and `success_per_mille = 1000`.
- Its inputs, if any, are matched against the subject's contents.
- **Process rules.** A process rule is a `when:` rule whose named condition
  has kind `work_complete`, and whose subject predicate names exactly one
  process archetype (`archetype = "<id>"`). Its inputs are matched against the
  process entity's contents (§5.2, slots filled from contents). The work it
  requires is the archetype's `process.work_required`, so every process rule
  of one archetype requires the same total and the progress word is
  well defined. For example:

  ```toml
  [[rule]]
  id = "finish_shelter"
  trigger = "when:done"
  subject = { archetype = "shelter_site" }
  inputs = [{ slot = "frame", where = { long = true, material = "wood" }, qty = 4 },
            { slot = "cover", where = { archetype = "grass_tuft" }, qty = 6 }]
  conditions = [{ id = "done", kind = "work_complete" }]
  outputs = [{ archetype = "shelter", quantity = 1, at = "subject.tile" }]
  effects = [{ op = "consume", of = "subject" }]
  phenomena = { success = ["fits_together"], unmet = [], chance_failed = [] }
  ```

- **Eligible process rules.** A process rule is eligible for a process in a
  tick when its slots fill from the contents and its conditions other than
  `work_complete` hold. Work counts for a process in a tick only while at
  least one rule is eligible (protocol §6.2).
- **One rule per process.** Process rules run after all other world rules of
  the tick, one process at a time in entity ID order. For each process the
  engine takes, on the state at that moment, the most specific eligible
  rule whose `work_complete` holds (ties by `rule_id`), and settles only that
  one. So the outcome never depends on how rule IDs sort against unrelated
  world rules.
- Consuming the process subject places its remaining contents on its tile
  first (§3.4); contents the rule's slots did not use are therefore never
  lost.
- A process entity's own archetype must have `process` and `container`.

### 5.9 Provenance and proposed rules

```text
provenance = {kind:"authored", pack_id:string}
           | {kind:"proposed", llm_call_id:string, approved_by:string, approved_at_tick:integer}
```

- A proposed rule is data. It passes the same validator as an authored rule,
  is inactive until approved and enters the library only at a boundary, with a
  `rule_added` event (ADR 0007 D9, ADR 0009 D5). Inactive proposals are not
  part of `rule_library_hash`.
- P3.5 implements the format and the validator for proposals. It implements
  no proposal flow (ADR 0007 context: layer C is a design constraint, not a
  system).

### 5.10 Packs that extend packs

A pack may declare `extends = "<pack_id>"` (the starter pack extends the
compatibility pack). The extending pack's content is the base pack's plus its
own, under these rules:

- New entries (materials, archetypes, instances, rules, sources) need IDs not
  used in the base pack.
- An entry with an existing ID may be redeclared with `replace = true`, which
  replaces it whole. Rules, archetypes, materials, comparison tables (§5.7)
  and pack values (rates, thresholds, durations) may be replaced this way;
  a replaced rule gets a new `content_hash` and provenance naming the
  extending pack.
- Nothing is removed implicitly. `disable = ["<rule_id>", ...]` removes base
  rules from the library.
- The composed pack is validated as one pack (§7), and its hashes are those of
  the composed content (§1).

## 6. Attempt descriptor and condition context

One representation serves rule conditions and recorded attempts, so a
proposed rule can be back-tested on what residents tried (ADR 0007 D5, D9).

```text
AttemptDescriptor {
  verb:VerbId, tick:integer,
  target:Signature|null,
  instruments:array<Signature>,                 // submitted order
  inputs:array<{quantity:integer,               // submitted order
                parts:array<{signature:Signature, quantity:integer}>}>, // stacks, ascending entity ID
  context:ConditionContext
}
Signature {
  ref_kind:"tile"|"entity"|"resident",
  archetype_id:string|null, material_id:string|null, terrain:Terrain|null,
  components:array<string>,                     // component names, sorted
  properties:array<{property_id:string, value:integer|boolean}>,  // true values, every declared property, by ID
  state:array<{field:string, value:integer}>,   // the §3.3 state fields that exist, by field
  held:boolean, distance:integer                // from the actor's tile
}
ConditionContext {
  awareness:"awake"|"asleep",
  needs:array<{need_id:string, value:integer}>, // stored values, by ID
  free_slots:integer,
  position:Coord, terrain_here:Terrain, time_phase:"day"|"night",
  nearby_terrain:array<{terrain:Terrain, distances:array<integer>}>, // every distance 0..condition_radius at which that terrain lies, sorted; by terrain
  nearby_entities:array<{signature:Signature, distance:integer}> // within condition_radius, by distance then entity ID
}
```

- `components` makes `has_component` testable on a record, including marker
  components with no state, such as `shelter`.
- `nearby_terrain` lists every distance at which a terrain occurs within the
  radius, not only the nearest, so a `terrain_near` interval that excludes the
  nearest tile is evaluated the same way on the record as live. For example,
  an actor on grass with grass also adjacent records `distances = [0, 1]`;
  without adjacent grass, `[0]` or `[0, 2]`.
- An input entry resolved from several stacks records each part, so the
  back-test applies §5.2 to every part.

- The engine builds this for every `act` at its start check (protocol §2), and
  every condition of §3.3 is a function of a rule, the signatures and the
  context. `work_complete` is the only exception; it applies to processes, not
  attempts.
- **Back-test.** A rule matches a recorded descriptor exactly when it would
  have matched the attempt: §5.2 on the signatures, then its conditions on the
  context.
- The descriptor holds true values. It is objective data: it appears only in
  the `attempt_unmatched` event (protocol §9) and never reaches a resident.
- `nearby_entities` signatures carry no entity ID, so a back-test depends on
  what things were, not on which ones.

## 7. The validator

The validator runs when content loads and on every proposed rule (ADR 0008 D7).
It produces a deterministic report; any error refuses the load or the
proposal.

| Check | Error code | Refuses |
|---|---|---|
| 1. References resolve | `UNKNOWN_TERM` | A vocabulary term, archetype, material, component, field, slot or condition ID that does not exist |
| 1. IDs | `DUPLICATE_ID` | A repeated ID in one namespace, or an ID that breaks §1 |
| 2. Ranges | `OUT_OF_RANGE` | A value outside its domain: scale 0–5, chances 0–1000, `work_ticks ≥ 1`, thresholds within the need's range, `distance.max ≤ condition_radius`, phase offsets within the period |
| 2. Shapes | `BAD_SHAPE` | A target slot that disagrees with the verb's target kinds; more than 2 instrument slots or 4 input slots; an instrument with `qty ≠ 1`; a `conservation` declaration that disagrees with the outputs (§8); a condition kind used where §3.3 does not allow it; a world rule with actor-only fields; a slot name and a condition ID that collide, or either named `world_limit` (§1); `set_state` on `store.count` (§3.4); a `when:` rule with a sourced output (§3.5); a `per_tick` need effect on a rule with `success_per_mille < 1000`, or a `need` condition on a need the same rule changes per tick (§3.3, §5.5); a portable container whose `accepts` matches an archetype with `container` (§3.1); a process rule whose subject does not name one process archetype, or that sets `work_ticks` (§5.8); a `material_from` or `archetype_from` naming no slot of the rule; a missing descriptor table on a `visible` or `on_inspect` property, or a table on an `on_use` one (§2.2) |
| 3. Conservation | `CONSERVATION` | A branch of a rule whose credits exceed its debits in some class (§8.1) |
| 4. Sources | `UNDECLARED_SOURCE` | Creation from nothing without a declared source; a source without a rate bound; outputs of one settlement whose static bounds on one source sum above its `max_per_application` (§8.2) |
| 5. Cycles | — | Follows from check 3 (§8.3) |
| 6. Need bound | `NEED_RATE` | A rule beyond the per-tick bound (§5.5) |
| Tells | `TELL_MISSING` | An apparent override without a valid tell (§4.4) |
| Interruption | `INTERRUPT_MODE` | `keep_progress` without a matching process rule; `on_interrupt` on a world rule |
| Phenomena | `UNKNOWN_TERM` | A phenomenon list naming an unknown term; an enabled verb without a comparison table |

The report also lists, deterministically sorted:

- **Slot coverage**: for each slot of each rule, every (archetype, material)
  pair in the pack that can match it, as ADR 0008's consequences ask.
- **Overlaps**: pairs of rules with the same trigger whose slots can be
  filled by the same items and whose specificity is equal. These are
  warnings; settlement still resolves them by `rule_id` (engine spec).
- **Unreachable checks**: pairs (`rule_id`, check) that can never be the
  reported `failed_check`. The validator proves a pair (R, c) unreachable
  when another rule R′ has the same trigger and slot structure, each of its
  slot predicates is a subset of the keys of R's corresponding predicate (so
  R′ matches every intent R matches), and all its conditions are among R's
  conditions declared before c. Whenever c is R's first failing check, R′ is
  then eligible, and an eligible rule always wins over an unmet one (engine
  spec §5.2). For example, (`compat_sleep_cave`, `cave`) is unreachable
  because plain `compat_sleep` has the same slots and no conditions.
  The compatibility code table uses this list (starter-content spec §4.5).

## 8. Conservation

### 8.1 Units per class

Matter is counted in units per matter class (ADR 0008 Q4; owner, RR-D2). Each
archetype gives the units of each class in one unit of it. Items inside a
`store` or a `container` count as units of their archetype. Destroying matter
is allowed (eating, burning); creating it is not, except from a source
(§8.2). For example, a stone axe of `{mineral = 1, plant = 2}` may be made
from a stone head (`mineral = 1`), a wooden handle and a fibre binding
(`plant = 1` each).

**Branches.** A rule can settle in several ways, and each is checked on its
own:

| Branch | Debits | Credits |
|---|---|---|
| `applied` | Consumed inputs, `consume` effects | `outputs` without a source |
| `chance_failed` | Inputs if `consume_inputs` | None (§5.6) |
| `on_interrupt = partial` | Inputs | The partial outputs |
| `keep_progress`, `lose`, `unmet`, `unmatched` | None | None (`keep_progress` only moves) |

For every branch and every class: `credits ≤ debits`.

**Amounts.** Each amount is a units-per-class count times a quantity (§3.4.1).
The check is symbolic, so it holds for every runtime value:

- A credit counts an integer `n` as `n`, `{ of = r }` as the reference `r`,
  and `{ upto = n, of = r }` as `n`.
- A debit counts an integer as itself, an input slot as its `qty`, a whole
  `subject` or `target` consume and `{ of = r }` as the reference, and
  `{ upto = n, of = r }` as 0, since its lower bound is unknown.
- `slot:<name>.quantity` is that slot's `qty`, a constant, on either side.
- A credit with `archetype_from = s` and a quantity of at most `s`'s `qty` is
  covered by the debit of slot `s` itself, for every archetype that can fill
  `s` (slot coverage, §7), because it returns the same archetype. This is how
  `bind_snaps` passes.
- The branch passes when, per class, the credited constant is at most the
  debited constant and each reference's credited coefficient is at most its
  debited coefficient. A credit by `fit:` without a source never passes,
  since no debit uses `fit:`.

For example, `fruit_rots` debits `subject.quantity × units(fruit)` and
credits `subject.quantity × units(rotten_fruit)`; it passes when rotten fruit
holds no more units per class than fruit. A rule that consumes one unit and
creates a two-unit partial output fails its `partial` branch.

**Matter only moves through ledgered operations.** `store.count` and
contents change only through `create`, `consume` and `move` (§3.4). Consuming
an entity first places its contents and its store count on its tile (as a
stack of the store's archetype), so a consume debits only the entity's own
matter. With one role per entity (§3.4) and no unit used twice (§5.2), no
unit is debited twice. The engine applies each branch atomically (engine
spec §12).

The rule's `conservation` field must agree with its outputs: `"none"` has no
outputs, `"source"` has only outputs with a `source`, and
`"inputs_to_outputs"` has none with a `source`.

### 8.2 Sources

A source is the only way matter appears from nothing (ADR 0008 D7 check 4):

```toml
[[source]]
id = "fruit_regrowth"
archetype = "fruit"
max_per_application = 1
```

- An output with `source` creates units of that archetype only, at most
  `max_per_application` per settlement, plus any cap its quantity imposes (a
  tree's free stock through `fit:`).
- **Static bound.** Each sourced output has a static upper bound: `n` for an
  integer or `{ upto = n, ... }`, and for `{ of = "fit:<place>" }` the largest
  capacity of any archetype that can fill that place's slot (slot coverage,
  §7). The bounds of all outputs of one settlement that name one source must
  sum to at most its `max_per_application`.
- A source used by an `every:<n>` rule creates at most
  `max_per_application` per `n` ticks per subject: its rate bound.
- A source used by a verb rule (the spring filling a container) is bounded per
  settlement; the verb's work time bounds its rate.
- A `when:` rule cannot use a source (§3.5).

### 8.3 Cycles

Because no branch of any rule creates more units of any class than it
consumes, any chain of rules has the same property, so no cycle can multiply
matter (ADR 0008 D7 check 5). Sources are the only growth, and they are
rate-bounded. A `when:` rule that adds to a store count with no source, which
could alternate with a withdrawal to create fruit, cannot be written:
`set_state` cannot touch `store.count`, and an unsourced `create` must be
paid for by debits.

### 8.4 What conservation does not cover

Need effects are not matter (ADR 0007 D9 item 4). Drinking at the spring
restores hydration from nothing; it is bounded by §5.5 instead.

## 9. Example: compatibility rules

The starter-content spec lists the full compatibility pack. Two rules show
how v1 checks become conditions in v1 order (protocol §11.2; v1 checks room
before stock, `world/actions.py` `validate`):

```toml
[[rule]]
id = "compat_gather_fruit"
trigger = "verb:gather"
target = { where = { archetype = "fruit_tree" } }
conditions = [
  { id = "stamina", kind = "need", need = "stamina", op = ">", value = "min" },   # v1 EXHAUSTED
  { id = "room",    kind = "free_slots", op = ">=", value = 1 },                  # v1 INVENTORY_FULL
  { id = "stock",   kind = "state", of = "target", field = "store.count", op = ">=", value = 1 },  # v1 RESOURCE_TAKEN
]
work_ticks = 2
on_interrupt = "lose"
exhaustion_stops = true
success_per_mille = 1000
effects = [{ op = "move", from = "target.store", to = "actor", quantity = 1 },
           { op = "need", need = "stamina", delta = -300, timing = "completion" }]
phenomena = { success = ["picks_fruit"], unmet = ["finds_nothing"], chance_failed = [] }

[[rule]]
id = "compat_drink_spring"
trigger = "verb:drink"
conditions = [
  { id = "need",   kind = "need", need = "hydration", op = "<", value = "max" },  # v1 NO_NEED
  { id = "spring", kind = "terrain_near", terrain = "spring", distance = { min = 1, max = 1 } },  # v1 OUT_OF_REACH
]
work_ticks = 1
on_interrupt = "lose"
success_per_mille = 1000
effects = [{ op = "need", need = "hydration", delta = 6000, timing = "completion" }]
phenomena = { success = ["drinks"], unmet = ["no_water_here"], chance_failed = [] }
```

The legacy bridge maps (`rule_id`, `failed_check`) to v1 codes, for example
(`compat_gather_fruit`, `stock`) to `RESOURCE_TAKEN` (protocol §11.2). The
starter-content spec gives that table. These rules have one phenomenon for
every unmet condition; the bridge, not the phenomena, carries the v1 code.

## 10. Determinism

- Every list in the parsed forms keeps its declared order where order
  matters (slots, conditions, effects, comparison entries, descriptor tables)
  and is sorted by ID elsewhere.
- Matching, specificity, phenomena and the validator report are pure
  functions of content and the descriptor. They read no clock, RNG or agent
  data.
- Hashes use the canonical encoding of `interface-contract-v0.1.md` §6.3.

## 11. Acceptance tests

| ID | Test |
|---|---|
| RR-01 | Parsing the same vocabulary and pack twice gives the same `vocabulary_hash`, `content_hash` per rule and `rule_library_hash`; reordering rules in the file leaves the library hash unchanged; changing one value changes it |
| RR-02 | A pack naming another vocabulary version or hash is refused at load |
| RR-03 | Each validator error code of §7 has a negative fixture that is refused with that code, and a positive control that loads |
| RR-04 | Conservation: an axe from head, handle and binding loads; the same axe from a head alone (`plant` short) is refused; a rule creating fruit with no source is refused; a declared source with no bound is refused. Per branch (§8.1): one consumed unit with a two-unit `partial` output is refused; `fruit_rots` with `subject.quantity` on both sides loads, and a stack of 4 gives 4 rotten; `set_state` on `store.count` is refused; a `when:` rule with a source is refused; two outputs of one settlement whose bounds on one source sum above its `max_per_application` are refused; a target that is also an input stack matches no rule |
| RR-05 | Need bound: a one-tick +300 stamina rule is refused at `max_gain_per_tick = 220`; a six-tick `per_tick` +120 rest loads; a sleep rule with `per_tick` +220 and `duration_param` loads, checked at the minimum duration; a four-tick rule with `+220` per tick and `+880` at completion is refused; a rule with `success_per_mille = 500` and a `per_tick` gain is refused; a rest that requires stamina below its maximum and gains stamina per tick is refused |
| RR-06 | Tells: two grass instances of one archetype and material load, one ordinary and one with `properties = {strength = 4, dry = true}`, `apparent = {strength = 1}` and `tell = ["dry"]`; the second shows `dry` and the true `material_id` and settles with strength 4, while the first stays not dry. Without a tell, with a tell equal to the ordinary value, or with a tell that is also in `apparent`, the instance is refused |
| RR-07 | Property values: instance own value over archetype over material over default; apparent value from instance, then material, else true; perception shows apparent values and the true `material_id`; settlement and predicates use true values |
| RR-08 | Inheritance: flint-head and stone-head axes from one rule differ in `hardness` and share `sharp`; an input's instance override is not inherited |
| RR-09 | Exact matching: `drink` with no instrument matches only the spring rule; `drink` with a canteen matches only the canteen rule; an intent with an extra input matches neither the rule with fewer slots nor any other; a quantity unequal to `qty` does not match |
| RR-10 | Assignment order: with slot 1 accepting A or B and slot 2 only A, the intent `[A, B]` matches through the second permutation; the result is the same on every run. A by-kind input of 3 that takes 2 units from one stack and 1 from another fills a slot only if both parts meet its predicate, and a `material_from` slot only if they share one material. Slots from contents: with stacks e1 (2 units, fits X and Y) and e2 (1 unit, fits X only), X needing 1 and Y needing 2, the first allocation of X (e1) leaves Y short, so backtracking binds X to e2 and Y to e1; the same binding is used after restore |
| RR-11 | Specificity counts: a rule with two predicate keys and one condition has specificity 3; a tile terrain slot counts one; the clay vectors of ADR 0009 D1 give the expected counts |
| RR-12 | Unmatched phenomena: a strike with a harder instrument gives `leaves_dent`; with two holding entries the union is sorted and unique; with none, `default`; a deceptive vine compared by true strength behaves weak |
| RR-13 | Watcher visibility: a watcher's `ObservedAction` carries only phenomena with `watcher_visible = true` (with protocol WAP-08) |
| RR-14 | Condition context: every §3.3 condition kind evaluated live and on the recorded descriptor of the same attempt gives the same result, for a positive and a negative case each, including `terrain_near` with `distance = {min = 1, max = 1}` for an actor on grass with and without adjacent grass, and `has_component = "shelter"` on a marker component |
| RR-15 | Back-test: a rule added after a run matches exactly the recorded `attempt_unmatched` descriptors it would have matched live |
| RR-16 | Condition value: for `mental_fatigue`, stored 9500 of 10000 is `c = 500`; a threshold at `c = 1000` is crossed when `v` rises from 8900 to 9000; bands read worst to best |
| RR-17 | Stacks: fruit added to a tile with an equal stack merges and keeps the ID; splitting gives a new ID; two fruit stacks with different state stay apart; a stackable item has no `owner_id` |
| RR-18 | Ownership: a verb rule's non-stackable output has the actor as owner; `give` sets the recipient; `pick_up` leaves the owner unchanged |
| RR-19 | `on_interrupt`: `lose` releases inputs and keeps applied `per_tick` gains; `partial` creates its outputs and consumes inputs; `keep_progress` leaves a process entity holding the inputs with `work_done` equal to elapsed work, and another resident can finish it by `contribute`. At death, with a reserved item gone, or with a placement the limits refuse, `partial` and `keep_progress` fall back to `lose`, creating and consuming nothing |
| RR-20 | Process rules: work counts only while a process rule's slots are filled by the contents; the rule settles when `work_complete` holds against the archetype's `work_required`; a process archetype without `container`, or a process rule with its own `work_ticks`, is refused. Two complete eligible rules `a_finish` (less specific) and `z_finish` on one process, with a world rule `m_change` that would clear a condition of `z_finish`: the result is the same whatever the rule IDs, because process rules run after the other world rules, on the state at that point; contents no slot used land on the tile |
| RR-21 | World rules: an `every:144` rule with phase offsets 0 and 24 fires for each tree at its own ticks, never at tick 0; a `when:` rule on `durability.left == 0` fires once when wear reaches the maximum |
| RR-22 | Provenance: an authored rule gets `{kind:"authored"}`; a proposed rule passes the same validator and is not in the library hash until it is added at a boundary with `rule_added` |
| RR-23 | Schema: adding a rule leaves the generated turn schema unchanged; enabling a verb changes it (with protocol WAP-11) |
| RR-24 | Validator report: slot coverage lists every matching (archetype, material) pair; an equal-specificity overlap is reported as a warning and still loads |
| RR-25 | No pack can declare a component, condition kind, effect operation or trigger form that this spec does not define: each is refused with `UNKNOWN_TERM` |
| RR-26 | Quantities (§3.4.1): `{ of = "fit:target.contents" }` on a two-serving container with one serving free creates one; `{ upto = 2, of = "fit:subject.store" }` on stock 4 of 5 creates one and on stock 3 creates two; references are read before any effect, so a whole-subject consume and a `subject.quantity` output use the same value |
| RR-27 | Outputs: the material comes from `material`, else `material_from`, else the archetype default, else `null`; `archetype_from` copies the slot's archetype; `bind_snaps` gives back a head and a handle of the original archetype and material, with new IDs, and no cord |
| RR-28 | Check order (§5.2): with a missing input and a failing condition, `failed_check` names the input slot, at start, at completion and after restore; with every declared check holding and a placement refused by the entity limits, it is `world_limit` and nothing is spent |
| RR-29 | Unreachable checks (§7): the report lists (`compat_sleep_cave`, `cave`); a pair whose less specific rule has a condition declared after the check is not listed |
| RR-30 | Pack extension (§5.10): a base rule redeclared without `replace = true` is `DUPLICATE_ID`; with it, the composed library holds the new rule; a replaced comparison table takes the base table's place entirely; `disable` removes a base rule; the composed hashes differ from the base pack's |
| RR-31 | Shapes: a portable container whose `accepts` matches an archetype with `container` is refused; an `on_use` property without a descriptor table loads, with one it is refused; a `visible` property without one is refused |
| RR-32 | Progress words (§2.2): a process with `work_required = 24` reads `started`, `halfway` and `nearly_done` at work 7, 8 and 16; a six-tick personal action reads them at elapsed 1, 2 and 4; `move_to` and an unmet start have `progress = null` |

## 12. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0008 Q1 First vocabularies | §2.6, owner RR-D4; values per term in the starter-content spec |
| ADR 0008 Q2 Success chance by input or skill | Fixed per rule, owner RR-D1 (§5.6) |
| ADR 0008 Q3 Ownership | Resolved by the owner (ADR 0008 D6); §4.6 |
| ADR 0008 Q4 How matter is measured | Units per class, owner RR-D2 (§8) |
| ADR 0008 Q5 Inheritance | Material from the slot, archetype properties win, owner RR-D3 (§4.3) |
| ADR 0007 Q3 First verbs | §2.6, owner RR-D4 |
| ADR 0007 Q4 Phenomena and watcher visibility | §2.5, §5.7, owner RR-D5 |
| ADR 0007 Q7 Physiology effects | Any enabled need, per-tick bound (§5.5); rates in the starter-content spec |
| Protocol §14: named thresholds and waking mark | §2.1 |
| Protocol §14: `failed_check` IDs | Slot names and condition IDs (§3.3, §5.1) |
| Protocol §14: verb target kinds, class, held flag, reach | §2.4, §2.6 |
| Protocol §14: tells | §4.4 |
| Protocol §14: watcher-visibility flag | §2.5 |
| ADR 0009 Q3 Inputs on a failed roll | Declared per rule (`on_chance_failed`, §5.6); the engine spec applies it |

## 13. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| RR-D1 | Does a rule's success chance depend on the inputs or on skill? | Fixed per rule. Better inputs can get a better chance through a more specific rule. No world-side skill | Simple and testable. A world-side skill would carry knowledge across waking periods in the memory-off arm |
| RR-D2 | How is matter measured? | Units per matter class (`mineral`, `plant`, `water`) per archetype | Mass values need balancing of their own; a unit count alone cannot tell stone from wood |
| RR-D3 | What does an output inherit? | The input's material with its true and apparent values; archetype properties win; instance overrides are not inherited | Flint and stone axes then differ by material, as ADR 0008 D3 intends, and deception stays per material |
| RR-D4 | The first vocabulary | 5 needs, 3 matter classes, 17 properties, 6 compatibility verbs plus 5 starter verbs (`combine`, `strike`, `cut`, `light`, `build`), 31 phenomena | Small enough to test, enough for the starter content of ADR 0010 D2 |
| RR-D5 | How are phenomena of unmatched attempts made? | Per-verb comparison tables over true values; the union of holding entries, else a default | Gives physical feel without naming a rule (ADR 0007 D5) |
| RR-D6 | Do stackable items record an owner? | No; only non-stackable entities do | Merging stacks would mix owners; `item_transferred` events keep who gave what |
