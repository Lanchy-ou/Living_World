# Living Island — Starter Content v0.1 (P3.5 v2 lane)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §12 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
>
> Implements [ADR 0010](../adr/0010-starter-content.md). Uses the formats of
> [rule representation](rule-representation-v0.1.md) and the mechanisms of the
> [world engine](world-engine-v0.1.md). When frozen, it supersedes
> `balance-notes-v0.1.md` for new content (ADR 0010). `content/worlds/
> default.toml` and its map stay unchanged: they remain the v1 configuration
> and the source of the compatibility pack's values.

**Values.** Every number here is a content value. The compatibility pack's
values are v1's and are not open. The starter pack's new values are
candidates, checked by the balance runs of §9 before M13 (ADR 0010 D3). A
value changed by tuning is a content change with a new pack version and hash,
not a spec change, as long as it stays within the ranges this spec states.

## 0. Scope

### 0.1 Covered here

- Pack files, extension and hashes (ADR 0010 D4, Q5).
- The values of the vocabulary file `vocab/0.1`: descriptor tables, phenomenon
  texts and watcher flags, verb descriptions.
- The compatibility pack: the 11 v1 actions on the v2 kernel and rules, with
  the code table of the legacy bridge (ADR 0010 D1; protocol §11).
- The starter pack: materials, archetypes, recipes, world rules, placements
  and values (ADR 0010 D2, Q1, Q3, Q4).
- The synthetic test pack for engine tests (ADR 0010 D4).
- Balance checks, tolerances and spare-time measurement (ADR 0010 D3, Q2, Q6).

### 0.2 Owned elsewhere

The formats are the rule-representation spec's; how rules run is the engine
spec's; the equivalence projection and adapters are the protocol's (§11).

## 1. Packs and files

```text
content/vocabulary/vocab-0.1.toml        the vocabulary file (§2)
content/packs/<pack_id>/pack.toml        identity, extension, enabled terms, values
content/packs/<pack_id>/materials.toml
content/packs/<pack_id>/archetypes.toml
content/packs/<pack_id>/rules.toml
content/packs/<pack_id>/instances.toml
content/packs/<pack_id>/unmatched.toml   comparison tables per verb
content/packs/compat-v1/compat-codes.toml   the bridge's code table (§4.5)
```

- `pack.toml` holds `pack_id`, `pack_version`, the vocabulary version and
  SHA-256, `extends` (one base pack or none), `enabled_verbs`,
  `enabled_needs`, and the value tables: `needs`, `physiology`, `timing`,
  `inventory_slots`, `limits` and `sources`.
- **Pack hash.** The SHA-256 of the canonical encoding of the parsed pack:
  every file merged into one object. A run manifest records each active pack's
  ID and hash (`pack_ids`, engine §13).
- **Extension.** A pack with `extends` inherits everything of its base. It may
  add materials, archetypes, rules, instances, sources and comparison entries
  with new IDs, enable further verbs and needs, and override values in
  `needs`, `physiology`, `timing` and `limits`. It never redefines an
  inherited ID. The code table of §4.5 is not inherited.
- **The v1 configuration stays the source** (ADR 0010 Q5; owner, CT-D1).
  `compat-v1` names `content/worlds/default.toml` and pins its config hash.
  The loader takes every v1 value the compatibility pack needs (map, clock,
  perception, social, residents, trees, canteen, needs, durations) from that
  file. The starter pack sits beside it and extends `compat-v1`; nothing
  replaces `default.toml`.

## 2. Vocabulary values (`vocab/0.1`)

The members are fixed by rule representation §2.6.

### 2.1 Properties

| Property | Domain | Observability | Descriptor words (value or `upto` → word) | Default |
|---|---|---|---|---|
| `hardness` | scale | visible | 1 → soft, 3 → firm, 5 → hard | 0 |
| `strength` | scale | visible | 1 → weak, 3 → sturdy, 5 → strong | 0 |
| `weight` | scale | on_inspect | 1 → light, 3 → heavy, 5 → very heavy | 0 |
| `sharp` | bool | visible | true → sharp, false → blunt | false |
| `long` | bool | visible | true → long, false → short | false |
| `dry` | bool | visible | true → dry, false → damp | false |
| `flexible` | bool | on_inspect | true → bends easily, false → stiff | false |
| `malleable` | bool | on_inspect | true → can be shaped, false → keeps its shape | false |
| `flammable` | bool | on_use | — | false |
| `edible` | bool | on_use | — | false |
| `brittle` | bool | on_use | — | false |
| `watertight` | bool | on_use | — | false |
| `fruit_amount` | count | visible | 0 → empty, 2 → few, more → many | — |
| `stock_amount` | count | visible | 0 → empty, 3 → a little, more → plenty | — |
| `water_amount` | count | visible | 0 → empty, 1 → one serving, more → two servings | — |
| `wear_state` | count | visible | 2 → nearly broken, 9 → worn, more → sound | — |
| `fire_state` | count | visible | 0 → out, 3 → embers, more → burning | — |

- `fruit_amount` reproduces the v1 fruit band exactly: `empty`, `few` for
  1–2 (`perception.fruit_few_max = 2`), `many` above
  (`interface-contract-v0.1.md` §2.5).
- `water_amount` shows servings exactly, as v1 showed the holder its canteen
  servings; the perception adapter reads it (protocol §11.2).
- `on_use` properties have no words: they never appear as values.
- No property shows an item's age (owner, CT-D7): fruit gives no sign of its
  age, so residents learn that fruit rots from experience.

### 2.2 Verb descriptions

Short neutral texts for the system instructions (decision-loop spec). They
say what the body does, never what it achieves.

| Verb | Description |
|---|---|
| `gather` | Take something from a plant, a pile or a deposit next to you |
| `eat` | Eat something you hold |
| `drink` | Drink, from a spring next to you or from something you hold |
| `fill` | Fill something you hold with water |
| `rest` | Rest without sleeping |
| `sleep` | Sleep for a number of ticks you choose (6–54) |
| `combine` | Try to put held things together |
| `strike` | Strike something with a held tool |
| `cut` | Cut something with a held tool |
| `light` | Try to set something burning, or feed a fire |
| `build` | Start building on a tile next to you |

### 2.3 Phenomena

| ID | Text | Watchers |
|---|---|---|
| `picks_fruit` | You pick a fruit. | yes |
| `takes_some` | You take some. | yes |
| `finds_nothing` | There is nothing to take. | yes |
| `hands_full` | Your hands are full. | no |
| `too_tired` | You are too tired. | no |
| `tastes_good` | It tastes good. | no |
| `tastes_bad` | It tastes bad. | no |
| `not_hungry` | You are not hungry. | no |
| `drinks` | You drink. | yes |
| `not_thirsty` | You are not thirsty. | no |
| `no_water_here` | There is no water to drink. | yes |
| `fills_up` | It fills with water. | yes |
| `already_full` | It is already full. | no |
| `rests` | You rest. | yes |
| `sleeps` | You sleep. | yes |
| `nothing_happens` | Nothing happens. | yes |
| `leaves_dent` | It leaves a dent. | yes |
| `chips_off` | A chip flies off. | yes |
| `splits` | It splits. | yes |
| `cuts_through` | It cuts through. | yes |
| `does_not_cut` | It does not cut. | yes |
| `fits_together` | The pieces fit together. | yes |
| `falls_apart` | It falls apart. | yes |
| `slips` | It slips. | yes |
| `snaps` | It snaps. | yes |
| `holds_firm` | It holds firm. | yes |
| `smokes` | It smokes. | yes |
| `catches_fire` | It catches fire. | yes |
| `fizzles` | It fizzles out. | yes |
| `site_marked` | You mark out the ground. | yes |
| `ground_unsuitable` | The ground is not right for this. | yes |

## 3. Shared values

| Value | Compatibility pack | Starter pack |
|---|---|---|
| `inventory_slots` | 10 (v1 `inventory.slot_capacity`) | 10 |
| `attempt_ticks`, every enabled verb | 1 (= `invalid_attempt_ticks`, protocol §11.2) | 1 (owner, CT-D3) |
| Kernel durations | `give_ticks`, `pick_up_ticks`, `wait_ticks`, `invalid_attempt_ticks` from v1 (all 1); `drop_ticks = 1`, `inspect_ticks = 1` | Inherited |
| `limits` | `max_entities_per_tile = 16`, `max_entities_world = 4000` | Inherited |

`drop_ticks` and `inspect_ticks` are new and carried from protocol §14; one
tick each keeps them as cheap as `pick_up`.

## 4. The compatibility pack `compat-v1`

v1 mechanics only (ADR 0007 D8, ADR 0010 D1). It must reproduce v1 on the
equivalence projection (protocol §11.3).

### 4.1 Needs and physiology

| Need | Range, initial | Band cutoffs (on `c`) | Thresholds | Rate limits (gain / loss per tick) |
|---|---|---|---|---|
| `satiety` | 0–10000, 7500 | 2000, 4000, 6000, 8000 | `urgent` at 3000, wakes | 2000 / 0 |
| `hydration` | 0–10000, 8000 | same | `urgent` at 3000, wakes | 6000 / 0 |
| `stamina` | 0–10000, 8500 | same | `urgent` at 2500, wakes | 220 / 150 |
| `health` | 0–10000, 10000 | same | none | 0 / 0 |

- Ranges, initial values, cutoffs and urgent thresholds are the v1 values
  (`needs.*`, `perception.need_band_cutoffs`, `agents.urgent_*_below`). The
  urgent thresholds wake a sleeper, as v1 does (protocol §6.3).
- The rate limits are the largest v1 rule effects: eating 2000, a spring or
  canteen drink 6000, sleep by the cave 180 + 40, the gather cost 300 over its
  2 ticks.
- Physiology is v1's (engine §9.2): satiety and hydration fall 25 and 100 per
  tick, awake and asleep alike; awake stamina decay 40; movement extra cost
  60; deprivation loss 70; sleep health recovery 15 above recovery minimums of
  2500 satiety and 2500 hydration. Mental fatigue is not enabled.

### 4.2 Materials, archetypes and sources

| Archetype | Kind | Material | Stackable | Matter | Components and observed fields |
|---|---|---|---|---|---|
| `fruit_tree` | feature | `wood` | no | — | `store {archetype: fruit, capacity: 5}`; `store.count` as `fruit_amount` |
| `fruit` | item | `fruit` | yes | `plant 1` | `portable {1}` |
| `canteen` | item | — | no | `mineral 1` | `portable {1}`; `container {capacity: 2, accepts: {archetype: water}}`; `container.count:water` as `water_amount`; archetype `watertight = true` |
| `water` | item | `water` | yes | `water 1` | `portable {1}` |

Materials: `wood` (hardness 2, strength 3, weight 2, flammable), `fruit`
(hardness 1, weight 1, edible), `water` (no properties).

Sources: `fruit_regrowth` (fruit, at most 1 per application) and
`spring_water` (water, at most 2 per application).

Instances: the six v1 trees with their IDs, positions and
`phase_offset = {compat_regrow_fruit: <v1 regrow_phase_offset_ticks>}`, and
`store.count = 1` (`fruit.initial_stock_per_tree`); `canteen_01` held and owned
by `ryan`, holding the water stack `canteen_01_water` of quantity 2. The
spring, cave and cue stay map terrain and cues, as in v1.

### 4.3 Rules

| Rule | Trigger, slots | Conditions in v1 order (ID: kind) | Work | Effects | Phenomena (success; unmet by check) |
|---|---|---|---|---|---|
| `compat_gather_fruit` | `verb:gather`; target `{archetype: fruit_tree}` | `stamina`: stamina > min; `room`: free slots ≥ 1; `stock`: `store.count ≥ 1` | 2, `exhaustion_stops` | move 1 from `target.store` to `actor`; stamina −300 at completion | `picks_fruit`; stamina `too_tired`, room `hands_full`, stock `finds_nothing` |
| `compat_eat_fruit` | `verb:eat`; input `food {archetype: fruit}` × 1 | `need`: satiety < max | 1 | satiety +2000 | `tastes_good`; need `not_hungry` |
| `compat_drink_spring` | `verb:drink`; no target, no items | `need`: hydration < max; `spring`: `terrain_near spring`, distance 1–1 | 1 | hydration +6000 | `drinks`; need `not_thirsty`, spring `no_water_here` |
| `compat_drink_canteen` | `verb:drink`; instrument `canteen {archetype: canteen}` | `need`: hydration < max; `water`: `container.count:water ≥ 1` of `slot:canteen` | 1 | consume 1 water from `slot:canteen.contents`; hydration +6000 | `drinks`; need `not_thirsty`, water `no_water_here` |
| `compat_fill_canteen` | `verb:fill`; target `{archetype: canteen}` | `spring`: `terrain_near spring`, distance 1–1; `room`: `container.free ≥ 1` of target | 1 | create water `to_capacity` at `target.contents`, source `spring_water` | `fills_up`; spring `no_water_here`, room `already_full` |
| `compat_rest` | `verb:rest` | — | 6 | stamina +120 per tick | `rests` |
| `compat_sleep` | `verb:sleep` | — | `duration_ticks` | stamina +180 per tick | `sleeps` |
| `compat_sleep_cave` | `verb:sleep` | `cave`: `terrain_near cave`, distance 0–1 | `duration_ticks` | stamina +220 per tick | `sleeps` |
| `compat_regrow_fruit` | `every:144`; subject `{archetype: fruit_tree}` | `room`: `store.free ≥ 1` | — | create 1 fruit at `subject.store`, source `fruit_regrowth` | — |

- Every verb rule has `on_interrupt = "lose"`, `success_per_mille = 1000` and
  no `unmet` list beyond `unmet_by_check`; the `unmet` fallback list is
  `nothing_happens`. v1 discards progress on interruption and keeps rest and
  sleep gains already applied (`world-rules-v0.1.md` §4.1).
- Values are v1's: `gather_ticks`, `rest_ticks`, `eat_ticks`, `drink_ticks`,
  `fill_canteen_ticks`, the need gains, the gather cost, the rest and sleep
  gains and the cave bonus, and `fruit.regrow_ticks`.
- `compat_sleep_cave` is more specific than `compat_sleep` by its one
  condition, so a sleeper by the cave gets the bonus (engine §5.4).
- The checks the v1 action did before these conditions are generic checks
  (protocol §4.3); the two orders that differ are the declared exceptions of
  protocol §11.3.

### 4.4 Comparison tables

Every enabled verb's table is only `default = ["nothing_happens"]`, except
`eat`: `{compare: ["input.edible", "==", false]} → tastes_bad`. The rule-based
policy never makes an unmatched attempt; an unmatched result in a
compatibility run is a defect (§4.5).

### 4.5 The bridge's code table

`compat-codes.toml` maps every (`rule_id`, `failed_check`) of the pack to the
v1 failure code (protocol §11.2, §14). The loader refuses the pack if any
slot or condition of any verb rule is missing (protocol WAP-25).

| Rule | Check → v1 code |
|---|---|
| `compat_gather_fruit` | `target` → `OUT_OF_REACH`; `stamina` → `EXHAUSTED`; `room` → `INVENTORY_FULL`; `stock` → `RESOURCE_TAKEN` |
| `compat_eat_fruit` | `food` → `NO_ITEM`; `need` → `NO_NEED` |
| `compat_drink_spring` | `need` → `NO_NEED`; `spring` → `OUT_OF_REACH` |
| `compat_drink_canteen` | `canteen` → `NO_ITEM`; `need` → `NO_NEED`; `water` → `NO_WATER` |
| `compat_fill_canteen` | `target` → `NO_ITEM`; `spring` → `OUT_OF_REACH`; `room` → `ALREADY_FULL` |
| `compat_rest`, `compat_sleep`, `compat_sleep_cave` | none (no slots or conditions) |

- `unmatched` and `world_limit` have no code: either in a compatibility run
  is a defect that fails the equivalence check.
- Slot entries cover completion checks: a slot can fail only at completion,
  because the generic checks catch it at start.

### 4.6 Equivalence

The equivalence projection, its fixtures, the supported profile and the
declared exceptions are protocol §11.3. This pack meets the profile:
`talk_ticks = wait_ticks = invalid_attempt_ticks = 1` and `sleep_ticks = 48`
within 6–54. The seed set is protocol §11.3's: the P2 acceptance matrix, 20
seeds on `s2-default:m6` (`p2-experiments-v0.1.md` §2), the run that passed
PD-05 with all 60 residents alive (P2-05).

## 5. The starter pack `starter-v1`

`extends = "compat-v1"`. It adds the first crafting content and every mechanic
v1 does not have (ADR 0010 D1). It is loaded only after the compatibility
pack passes the equivalence check (ADR 0007 D8).

### 5.1 Changed values

| Value | Starter value | Why |
|---|---|---|
| `enabled_needs` | adds `mental_fatigue` | ADR 0012 D3 |
| `enabled_verbs` | adds `combine`, `strike`, `cut`, `light`, `build` | §5.4 |
| Satiety and hydration asleep | 15 and 60 per tick (awake 25 and 100) | Slower during sleep (owner, PR-D6; CT-D4): 60% of the awake rate |
| Thresholds of `satiety`, `hydration` | `urgent` at 3000, not waking; `critical` at 1999, wakes | The critical band is `c < 2000`, so `c ≤ 1999` (owner, PR-D6) |
| Threshold of `stamina` | `urgent` at 2500, not waking | Kept for notifications and the fallback |
| `mental_fatigue` | range 0–10000, initial 0, cutoffs 2000, 4000, 6000, 8000 on `c`; `critical` at 1999, not waking; rate limits 0 / 0 | No rule changes it; only physiology does |
| Mental fatigue coefficients | `awake_per_tick = 50`, `per_utterance_heard = 20`, `per_first_sighting = 30`, `recovery_per_tick_asleep = 150`, `faint_ticks = 36` | §5.2 (owner, CT-D5) |
| Rate limits of `stamina` | 220 / 150 (unchanged) | Starter rules stay within them |

The `urgent` thresholds stay so that the fallback policy (decision-loop
spec) still gets its v1 urgent notifications. Only `critical` wakes a sleeper.

### 5.2 Mental fatigue values

With 50 per awake tick, a resident who hears and sees nothing reaches the
maximum after 200 awake ticks, about 33 hours: fainting bounds a waking
period that never sleeps (ADR 0012 D3). A typical day of 96 awake ticks with
50 heard utterances and 20 first sightings ends near 6400 (`c ≈ 3600`, band
`low`): tired by evening. A night of 48 ticks clears 7200; a 6-tick nap clears
900, so a nap helps little (ADR 0012 Q1). `faint_ticks = 36` equals K
(memory-formation spec), so a faint always ends a waking period (engine
§9.3).

### 5.3 Materials

True values; apparent values in brackets where they differ.

| Material | hardness | strength | weight | Booleans |
|---|---|---|---|---|
| `stone` | 4 | 4 | 3 | — |
| `flint` | 5 | 2 | 2 | brittle |
| `wood` | 2 | 3 | 2 | flammable (inherited from `compat-v1`) |
| `vine` | 0 | **1 [4]** | 1 | flexible |
| `grass` | 0 | **3 [1]** | 0 | flexible, dry, flammable |
| `clay` | 1 | 1 | 3 | malleable |
| `fired_clay` | 3 | 2 | 3 | brittle, watertight |
| `rotten_fruit` | 0 | 0 | 1 | — |

**The rule against common sense** (ADR 0010 D2, owner). Vines look strong
and are weak; dry grass looks weak and is strong. A model's prior knowledge
says to bind an axe or a shelter with vine. On this island, vine cord snaps
and grass cord holds. Both materials are shown with their true IDs (protocol
§5.2), so a resident who has seen vine cord snap can recognize vine next time,
and a memory-off resident loses that lesson at its next period boundary (ADR
0014 D2). No instance overrides an apparent value in this pack, so no tell is
needed.

### 5.4 Archetypes

| Archetype | Kind | Material | Stack | Matter | Components, observed fields, archetype properties |
|---|---|---|---|---|---|
| `deposit` | feature | per instance | no | — | `store` (archetype and capacity per instance); `store.count` as `stock_amount` |
| `stone` | item | `stone` | yes | `mineral 1` | `portable {1}` |
| `flint_nodule` | item | `flint` | yes | `mineral 2` | `portable {1}` |
| `sharp_flake` | item | from rule | yes | `mineral 1` | `portable {1}`; `sharp = true` |
| `branch` | item | `wood` | yes | `plant 1` | `portable {1}`; `long = true` |
| `vine` | item | `vine` | yes | `plant 1` | `portable {1}`; `long = true` |
| `grass_tuft` | item | `grass` | yes | `plant 1` | `portable {1}` |
| `cord` | item | from rule | yes | `plant 3` | `portable {1}`; `long = true` |
| `clay_lump` | item | `clay` | yes | `mineral 1` | `portable {1}` |
| `unfired_pot` | item | `clay` | no | `mineral 2` | `portable {3}` |
| `clay_pot` | item | `fired_clay` | no | `mineral 2` | `portable {3}`; `container {capacity: 1, accepts: {archetype: water}}`; `container.count:water` as `water_amount` |
| `stone_axe` | item | from rule | no | `mineral 1, plant 4` | `portable {2}`; `durability {max_wear: 20}`; `durability.left` as `wear_state`; `sharp = true` |
| `campfire` | structure | — | no | — | `fuel {ticks_left: 18}`; `container {capacity: 3, accepts: {archetype: unfired_pot}}`; `fuel.ticks_left` as `fire_state` |
| `shelter_site` | process | — | no | — | `process`; `container {capacity: 30, accepts: {has_component: portable}}`; built-in `progress` |
| `shelter` | structure | — | no | — | `shelter`; `footprint {blocks_movement: false, opaque: false}` |
| `rotten_fruit` | item | `rotten_fruit` | yes | `plant 1` | `portable {1}` |

### 5.5 Verb rules

All have `on_interrupt = "lose"` and `exhaustion_stops = false` unless stated.
Work is in ticks; stamina costs apply at completion.

| Rule | Trigger and slots | Conditions | Work | Chance | Effects and outputs | Phenomena |
|---|---|---|---|---|---|---|
| `gather_deposit` | `gather`; target `{archetype: deposit}` | `stamina` > min; `room` free slots ≥ 1; `stock` `store.count ≥ 1` | 3, `exhaustion_stops` | 1000 | move 1 from `target.store` to `actor`; stamina −150 | `takes_some`; `too_tired`, `hands_full`, `finds_nothing` |
| `knap_flake` | `strike`; target `{archetype: flint_nodule}`; instrument `hammer {material: stone}` | — | 2 | 750, keep | consume target × 1; create 2 `sharp_flake`, `material_from = "target"`, at `actor` | `splits`; chance failed `slips` |
| `twist_cord` | `combine`; input `fibre {flexible: true}` × 3 | — | 4 | 1000 | create 1 `cord`, `material_from = "fibre"`, at `actor` | `fits_together` |
| `make_stone_axe` | `combine`; inputs `head {sharp: true, hardness_min: 4}` × 1, `handle {material: wood, long: true}` × 1, `bind {archetype: cord, strength_min: 3}` × 1 | — | 6 | 1000 | create 1 `stone_axe`, `material_from = "head"`, at `actor` | `fits_together`, `holds_firm` |
| `bind_snaps` | `combine`; inputs `head` and `handle` as above with `consumed = false`, `bind {archetype: cord, strength_max: 2}` × 1 | — | 6 | 1000 | the cord is consumed; no output | `snaps` |
| `cut_wood_with_axe` | `cut`; target `{archetype: deposit, material: wood}`; instrument `axe {archetype: stone_axe}` | `stamina` > min; `room` free slots ≥ 2; `stock` `store.count ≥ 2` | 2, `exhaustion_stops` | 1000 | move 2 from `target.store` to `actor`; axe wear +1; stamina −150 | `cuts_through`; `too_tired`, `hands_full`, `finds_nothing` |
| `light_fire` | `light`; target `{archetype: branch}`; instruments `striker {material: flint}`, `hammer {material: stone}`; input `tinder {dry: true, flammable: true}` × 1 | `pile` target `quantity ≥ 2` | 2 | 500, consume | consume target × 2; create 1 `campfire` at `target.tile` | `catches_fire`; chance failed `smokes`; pile `fizzles` |
| `feed_fire` | `light`; target `{archetype: campfire}`; input `fuel {material: wood}` × 1 | — | 1 | 1000 | target `fuel.ticks_left` +18 | `catches_fire` |
| `shape_pot` | `combine`; input `clay {archetype: clay_lump}` × 2 | — | 4 | 1000 | create 1 `unfired_pot`, `material_from = "clay"`, at `actor` | `fits_together` |
| `fill_pot` | `fill`; target `{archetype: clay_pot}` | `spring` near, distance 1–1; `room` `container.free ≥ 1` | 1 | 1000 | create water `to_capacity` at `target.contents`, source `spring_water` | `fills_up`; `no_water_here`, `already_full` |
| `drink_from_pot` | `drink`; instrument `pot {archetype: clay_pot}` | `need` hydration < max; `water` `container.count:water ≥ 1` of `slot:pot` | 1 | 1000 | consume 1 water from `slot:pot.contents`; hydration +6000 | `drinks`; `not_thirsty`, `no_water_here` |
| `mark_shelter_site` | `build`; target tile `{terrain: grass}` | — | 2 | 1000 | create 1 `shelter_site` at `target.tile` | `site_marked` |
| `sleep_in_shelter` | `sleep` | `shelter` `entity_near {has_component: shelter}`, distance 0–1 | `duration_ticks` | 1000 | stamina +220 per tick | `sleeps` |

- `bind_snaps` and `make_stone_axe` have disjoint `bind` predicates, so no
  attempt matches both.
- The unmet fallback list of every rule is `nothing_happens`.
- `sleep_in_shelter` has the same specificity as `compat_sleep_cave`; next to
  both, the lower `rule_id` (`compat_sleep_cave`) settles, with the same gain.
- Each rule's conditions and slots follow the validator: `cut_wood_with_axe`
  is the only rule whose stamina loss is close to the bound (150 over 2 ticks
  is 75 per tick).

### 5.6 World rules

| Rule | Trigger, subject | Slots and conditions | Effects |
|---|---|---|---|
| `regrow_deadwood` | `every:72`; `{archetype: deposit, material: wood}` | `room` `store.free ≥ 1` | create 1 `branch` at `subject.store`, source `deadwood_regrowth` |
| `regrow_grass` | `every:48`; `{archetype: deposit, material: grass}` | `room` `store.free ≥ 1` | create 1 `grass_tuft` at `subject.store`, source `grass_regrowth` |
| `fire_burns` | `every:1`; `{archetype: campfire}` | `lit` `fuel.ticks_left ≥ 1` | `fuel.ticks_left` −1 |
| `fire_goes_out` | `when:out`; `{archetype: campfire}` | `out` `fuel.ticks_left == 0` | consume subject; its contents fall on its tile |
| `bake_pot` | `every:6`; `{archetype: campfire}` | input `pot {archetype: unfired_pot}` × 1 from contents; `lit` `fuel.ticks_left ≥ 1` | create 1 `clay_pot`, material `fired_clay`, at `subject.tile` |
| `fruit_rots` | `when:old`; `{archetype: fruit}` | `old` `age ≥ 432` | consume subject; create `rotten_fruit`, quantity `subject.quantity`, at `subject.place` |
| `rotten_fruit_crumbles` | `when:gone`; `{archetype: rotten_fruit}` | `gone` `age ≥ 288` | consume subject |
| `axe_breaks` | `when:broken`; `{archetype: stone_axe}` | `broken` `durability.left == 0` | consume subject; create 1 `branch` at `subject.tile` |
| `finish_shelter` | `when:done`; `{archetype: shelter_site}` | inputs `frame {material: wood, long: true}` × 4, `cover {archetype: grass_tuft}` × 4, `tie {archetype: cord, strength_min: 3}` × 1; `done` `work_complete` | create 1 `shelter` at `subject.tile`; consume subject (leftover contents fall on the tile) |

- Sources: `deadwood_regrowth` (branch, 1 per application) and
  `grass_regrowth` (grass tuft, 1 per application). Vine, flint, stone and
  clay do not regrow in this version.
- `finish_shelter` needs 24 units of work (`work_ticks = 24`): one resident
  alone needs four hours, three together one hour and twenty minutes.
- Fruit that rots after 432 ticks (3 days) punishes hoarding, not normal
  eating: in P2 runs fruit was eaten within a day of gathering (P2-05). A stack
  takes the age of its oldest unit (rule representation §4.5), so adding
  fresh fruit to an old stack does not save it. Fruit on a tree does not age:
  a store holds counts, not entities.
- `fire_burns` sorts before `fire_goes_out`, so a fire runs out and is removed
  in the same tick (engine §8). A fire burns 18 ticks (3 hours); `feed_fire`
  adds 18.

### 5.7 Comparison tables

| Verb | Entries (`when` → phenomena), then default |
|---|---|
| `gather` | default `finds_nothing` |
| `eat` | `input.edible == false` → `tastes_bad`; default `nothing_happens` |
| `drink`, `fill`, `rest`, `sleep` | default `nothing_happens` |
| `combine` | default `falls_apart` |
| `strike` | `instrument.hardness > target.hardness` → `leaves_dent`; `instrument.hardness <= target.hardness` → `nothing_happens`; default `nothing_happens` |
| `cut` | `instrument.sharp == false` → `does_not_cut`; `instrument.sharp == true` → `leaves_dent`; default `does_not_cut` |
| `light` | `target.flammable == true` → `smokes`; `target.flammable == false` → `nothing_happens`; default `fizzles` |
| `build` | default `ground_unsuitable` |

### 5.8 Placements

The map is unchanged (ADR 0010 Q4; owner, CT-D6). New materials are
`deposit` instances on passable tiles, checked against the map: none sits on
a tree, a spawn, the cave, the cue or the spring.

| Instance | Tile | Terrain | Holds | Stock | Distance from spawn (34,32) |
|---|---|---|---|---|---|
| `clay_bank_01` | (37,31) | grass | `clay_lump` | 16 | 4 |
| `grass_patch_01` | (30,34) | grass | `grass_tuft` | 12, regrows | 6 |
| `stone_outcrop_01` | (37,28) | grass, by rock | `stone` | 20 | 7 |
| `grass_patch_02` | (40,36) | grass | `grass_tuft` | 12, regrows | 10 |
| `flint_scatter_01` | (28,25) | grass, by rock | `flint_nodule` | 12 | 13 |
| `deadwood_02` | (31,22) | woods | `branch` | 8, regrows | 13 |
| `deadwood_01` | (47,31) | woods | `branch` | 8, regrows | 14 |
| `vine_tangle_02` | (36,44) | woods | `vine` | 10 | 14 |
| `flint_scatter_02` | (27,41) | grass, by rock | `flint_nodule` | 12 | 16 |
| `vine_tangle_01` | (48,26) | woods | `vine` | 10 | 20 |

Each deposit's material is that of what it holds, so a resident sees "a
deposit of grass" and learns what it gives by gathering. Stores start full.
Clay and grass are near the spawn and the spring; flint and vines are farther,
so finding them takes exploring.

### 5.9 What each item is for

ADR 0010 D3 asks for a benefit the resident can perceive. M13 shows each in a
scripted scenario (plan §4).

| Item | Made from | Benefit |
|---|---|---|
| Sharp flake | Flint struck with stone | The head of an axe |
| Cord | 3 flexible fibres | Binds an axe and a shelter; grass cord holds, vine cord snaps |
| Stone axe | Flake, branch, grass cord | 2 branches per 2 ticks from deadwood, against 1 per 3 by hand: three times faster |
| Campfire | 2 branches, tinder, flint and stone | Bakes a shaped pot in 6 ticks; burns 3 hours |
| Clay pot | 2 clay, shaped, baked in a fire | Carries one more serving of water |
| Shelter | Site, 4 branches, 4 grass, 1 grass cord, 24 work | Sleep with the cave's stamina gain wherever it is built |

## 6. Cheaper food or water

ADR 0010 D3 forbids content that makes food or water cheaper than the
baseline unless the owner approves it. Three starter changes touch this:

| Change | Effect | Disposition |
|---|---|---|
| Slower hunger and thirst asleep | Less food and water per day | Owner-approved exception (PR-D6), within the tolerance of §9 |
| Clay pot | One more carried serving | Owner exception CT-D2 (recommended): capacity 1 serving and 3 slots, so a pot carries water at a sixth of the canteen's rate per slot; a resident can carry at most 3 pots (9 of 10 slots) |
| Fruit decay | Hoarded fruit is lost | Makes food dearer, not cheaper; no approval needed |

No starter rule gives satiety or hydration beyond the v1 gains.

## 7. The synthetic test pack `engine-test`

Engine tests use their own pack, never `compat-v1` or `starter-v1` (ADR 0010
D4). It is written by the M12 engine tasks with these properties:

- IDs are meaningless (`mat_a`, `arch_b`, `rule_c`) and share no ID with a
  real pack, so engine code that names a real ID is caught (engine EN-22).
- It covers every component, predicate key, condition kind, effect operation,
  trigger form, place, `on_interrupt` mode and validator error code at least
  once.
- It has its own small map and two residents.

## 8. Values carried in from other specs

| Value | Here | Source |
|---|---|---|
| Sleep bounds 6–54 | Verb `sleep` (rule representation §2.6) | Owner PR-D4 |
| K | `faint_ticks = 36` must be at least K | Memory-formation spec (K = 36) |
| Waking thresholds | §4.1, §5.1 | Protocol §6.3, owner PR-D6 |
| Code table | §4.5 | Protocol §11.2, §14 |

## 9. Balance checks

### 9.1 Method

The rule-based policy cannot craft, so the balance runs measure survival
only, which is what ADR 0010 D3 constrains. Crafting benefits are shown by
M13's scenarios and measured with LLM residents (ADR 0014 D1).

- **Arms.** Control: `compat-v1` with the rule-based policy reading
  resident-visible feedback only (decision-loop spec, the fallback mode of the
  starter pack). Treatment: `starter-v1` with the same policy and mode. The
  pack is the only factor, as P2 pairs required (`p2-experiments-v0.1.md`
  §5).
- **Seeds.** The P2 development list for tuning, then the P2 acceptance list
  once for the final candidate, each 20 seeds, 1008 ticks, `s2-default:m6`
  geometry (`p2-experiments-v0.1.md` §2). If an acceptance result informs
  tuning, a new list is registered by the P2 procedure.
- **Metrics.** The P2 metrics (`p2-experiments-v0.1.md` §3): all-alive cases,
  deaths and causes, deprived ticks, first spring drink, dedicated water trips;
  plus faints per resident and day, and ticks unconscious.

### 9.2 Tolerance

The treatment passes when, on the acceptance seeds (owner, CT-D8):

| Metric | Tolerance against the control |
|---|---|
| Cases with all residents alive | At least the control's count minus 1 (of 20) |
| Deprived ticks per resident, mean | At most the control's plus 24 |
| First spring drink, median per resident | Within 12 ticks of the control's |
| Faints | At most 1 per resident per 7 days, mean over cases |
| New death causes | None |

A failure goes back to tuning (§9.3) or to the owner. Every starter-pack
change reruns the check (ADR 0010 D3).

### 9.3 What may be tuned

Within these ranges a change is content tuning, not a spec change: mental
fatigue coefficients within ±50%; asleep need rates between 50% and 100% of
awake; deposit stocks and regrowth periods within ±50%; fire fuel within
6–36 ticks; `faint_ticks` from K up to 54; tool wear within ±50%. Anything
else is a spec change.

### 9.4 Spare time

ADR 0010 D3 asks that survival leave spare time, and Q6 how much. Spare time
is the share of awake ticks not spent on survival: walking to or acting on
food and water, gathering fruit, eating, drinking, filling, resting and
sleeping. It is measured, not tuned, in this version (owner, CT-D9):

- On the balance runs, reported per resident and day for both arms.
- With LLM residents, from ADR 0014 D1's time use.
- A provisional target of at least 30% for the treatment arm is a signal for
  the owner at M13's Gate 3, not a pass line.

## 10. Acceptance tests

| ID | Test |
|---|---|
| CT-01 | `compat-v1` loads; its values equal `default.toml`'s; changing `default.toml` changes the pinned hash and the pack is refused |
| CT-02 | The compatibility pack passes protocol §11.3's equivalence check on the 20 acceptance seeds, with the committed v1 fixtures |
| CT-03 | The code table covers every slot and condition of every verb rule; removing one entry makes the load fail (protocol WAP-25) |
| CT-04 | `starter-v1` loads and passes the validator; its pack hash includes the base pack's content; redefining an inherited ID is refused |
| CT-05 | Recipes: in a scripted scenario, a resident knaps a flake, twists grass cord, makes an axe, cuts wood three times faster than by hand, lights a fire, shapes and bakes a pot, fills it and drinks from it, and builds a shelter with others |
| CT-06 | Deception: vine shows `strength` "strong" and grass "weak"; vine cord makes `bind_snaps` settle with `snaps` and the head and handle kept; grass cord makes the axe; a shelter site with vine cord gets no work until grass cord replaces it |
| CT-07 | Conservation: every starter rule passes the validator; across a 7-day scripted run the units of each matter class equal placements plus source creation minus destruction |
| CT-08 | World rules: deadwood regrows 1 per 72 ticks up to its stock; a fire burns 18 ticks and goes out with its contents on its tile; a pot in a lit fire bakes at the next multiple of 6; fruit held 432 ticks rots; an axe breaks after 20 cuts and leaves a branch |
| CT-09 | Mental fatigue: the §5.2 day reaches about 6400; 200 silent awake ticks faint the resident for 36 ticks; a 48-tick night clears 7200 |
| CT-10 | Waking: in `starter-v1` a sleeper wakes at the critical band of hunger or thirst, not at the urgent threshold; in `compat-v1` at the urgent threshold |
| CT-11 | Asleep rates: satiety and hydration fall 15 and 60 per tick asleep in `starter-v1` and 25 and 100 in `compat-v1` |
| CT-12 | Placements: every deposit is on a passable tile, on no occupied tile, and visible to a resident standing next to it |
| CT-13 | Balance: §9.2 passes on the acceptance seeds for the final starter candidate |
| CT-14 | The engine test pack covers every closed term of rule representation §3 and shares no ID with a real pack |

## 11. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0010 Q1 Properties, recipes and values | §2, §4, §5 |
| ADR 0010 Q2 Tolerance band | §9.2, owner CT-D8 |
| ADR 0010 Q3 Container capacity and cost | Clay pot, one serving, three slots, owner CT-D2 (§6) |
| ADR 0010 Q4 Where materials appear; map changes | Map unchanged; deposits of §5.8, owner CT-D6 |
| ADR 0010 Q5 Replace or sit beside `default.toml` | Beside it, as the compatibility pack's source, owner CT-D1 (§1) |
| ADR 0010 Q6 Spare time and item benefits | Measured with a provisional 30% signal, owner CT-D9 (§9.4); benefits shown in M13 scenarios (§5.9) |
| ADR 0012 Q1 Fatigue values | §5.2, owner CT-D5 |
| Protocol §14 carried items | Slower hunger and thirst asleep (§5.1); thresholds and waking marks (§4.1, §5.1); the code table (§4.5); `drop_ticks` and `inspect_ticks` (§3) |

## 12. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| CT-D1 | Does the starter pack replace `default.toml`? | No. `default.toml` stays the v1 configuration and the compatibility pack's single source of values; the starter pack extends the compatibility pack | One source for v1 values; the equivalence holds by construction |
| CT-D2 | May craftable containers carry water? | Yes, as an exception: a clay pot holds one serving and takes three slots | ADR 0010 D3 needs owner approval; the cost keeps the canteen the best carrier |
| CT-D3 | `attempt_ticks` of the starter verbs | 1 for every verb | Trying stays cheap, which discovery needs; every attempt still costs a tick (PR-D2) |
| CT-D4 | How much slower are hunger and thirst asleep? | 60% of the awake rate | A clear effect that stays inside the survival tolerance |
| CT-D5 | Mental fatigue values | 50 per awake tick, 20 per heard utterance, 30 per first sighting, 150 recovery per tick asleep, faint for 36 ticks | Tired by evening, faint only after about 33 silent hours, a night clears it, a nap helps little |
| CT-D6 | Does the map change? | No; new materials are deposit entities on existing tiles | The P2 balance and routes stay valid |
| CT-D7 | Does fruit show its age? | No; no property shows an item's age | Residents learn that fruit rots from experience, which ADR 0014 D2 can count |
| CT-D8 | Survival tolerance | §9.2: at most one fewer all-alive case of 20, +24 deprived ticks, ±12 ticks to first drink, at most one faint per resident per week | Small enough to keep the P2 economy, wide enough for one seed of noise |
| CT-D9 | How much spare time? | Measure it; 30% of awake time is a signal for M13, not a pass line | No measured base exists yet |
| CT-D10 | The starter recipe set | §5: 13 verb rules and 9 world rules for the six items of ADR 0010 D2 | ADR 0010 said about 10 rules; each item needs a rule to make it and one to use it, and the four world rules each need their own |
