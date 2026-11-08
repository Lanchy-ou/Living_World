# Living Island — v0.1 Balance Notes (values are candidates, not measured)

> **Approved v0.1 (2026-11-08).** Rules and semantics are frozen. Numeric values in
> `content/worlds/default.toml` are candidates to be tuned in P2 without changing this spec.
> `Perception`, `ActionPlan`, `ActionIntent`, `ActionResult` and `DecisionTrigger` are frozen
> unless the agent-interface spec requires a change, which must go through a spec amendment task.
> `DecisionContext` remains provisional.

**Purpose:** give the economic, spatial and timing rationale for `content/worlds/default.toml`. This is not a claim about gameplay success, and it does not replace the World Rules Spec. **Route costs in §2 were computed** with the World Rules §5.3 pathfinding algorithm on the authored map. **No survival simulation was run**, so every survival statement below is a derivation, not a measurement.

## 0. What changed from rc2 and why

rc2 enlarged the map, slowed movement and increased hydration decay together to give the canteen strategic value. That is a hypothesis, not an established balance improvement. Its cave-sleep argument was weak: 48 outdoor sleep ticks restore 8,640 stamina, already reaching the 10,000 cap when starting stamina is at least 1,360; cave sleep restores up to 10,560, so its nominal extra 1,920 is often wasted at the cap.

rc3 keeps the rc2 map and speed while changing **one balance variable**, hydration decay:
- 64×64 tiles at 50 m per tile, unchanged;
- 8 movement units per tick, unchanged;
- hydration decay **100 per tick**, a conservative review candidate; retain 120 as a separate experimental comparison, not an accepted default.

The intended benefit is **less water-related travel, longer multi-stop trips and physical water delivery to companions**. It need not make every nearby gather trip unsafe without it. A resident may rationally sleep near the spring; cave attendance and nonholder deaths are not evidence that the canteen is useful. If the benefit is negligible, consider local fruit placement or revise the value proposition before raising global deprivation. The current geometry is retained for comparison, not endorsed as the simplest final island.

## 1. Units and survival economy

| Candidate parameter(s) | Value in TOML | Consequence / rationale |
|---|---:|---|
| `time.tick_minutes` | 10 | 144 completed ticks per game day; 1,008 ticks in seven days |
| `needs.min_value`, `needs.max_value` | 0, 10,000 | integer-only scale for all four conditions; higher is always better |
| `needs.initial_satiety`, `needs.satiety_decay_per_tick` | 7,500, 25 | satiety falls 3,600 per day (unchanged) |
| `needs.initial_hydration`, `needs.hydration_decay_per_tick` | 8,000, **100** | hydration falls **14,400 per day** (rc2: 17,280) |
| `needs.satiety_gain_per_fruit` | 2,000 | **1.8 fruit per person per day** at steady state |
| `needs.hydration_gain_per_serving` | 6,000 | **2.4 servings per person per day** at steady state; one serving replaces 60 ticks (10 h) of decay, provided it is not wasted at the cap |
| `fruit.regrow_ticks`, `fruit.regrow_per_cycle` | 144, 1 | each tree below cap grows one fruit per 24 game hours |
| `fruit.initial_stock_per_tree`, `fruit.max_stock_per_tree` | 1, 5 | six fruits on trees at the start; at most 30 hanging at once |
| `canteen.capacity_servings`, `canteen.initial_servings` | 2, 2 | 12,000 portable hydration, up to **120 additional ticks (20 h)** of replacement decay if consumed without cap waste; current body hydration is separate |
| `needs.health_loss_per_tick_if_deprived` | 70 | zero satiety **or** zero hydration costs health once per tick |

**Fruit:** at steady state, three residents eat `3 × (25 × 144) / 2000 = 5.4` fruit per day. Six trees grow at most 6 per day, theoretical headroom 0.6 (~11%). Across 1,008 ticks, supply is at most `6 + 6 × 7 = 48`; cap-blocked regrowth can reduce this. Replacing all seven days of decay requires 37.8 fruit-equivalents, but initial body satiety contributes 22,500 across the three residents: the net deficit before ending satiety reaches zero is 26.55 fruit-equivalents. Neither figure is a measured consumption count or a proof of survival. Travel, discovery, cap waste and uneven access reduce effective supply. Candidate tuning is local tree placement, then tree count/regrowth, with one variable changed per comparison.

**Water:** three residents require `3 × 14,400 / 6,000 = 7.2` servings per day at steady state, excluding cap waste. The spring is inexhaustible, so pressure comes from **discovery, time and distance**, not stock:
- From hydration 10,000, the `<= 3,000` urgent crossing occurs after **70 completed ticks (11 h 40 min)**. The same decay applies awake and asleep.
- A full sleep action (48 ticks) costs 4,800 hydration. Sleep may be interrupted by an urgent crossing; 48 ticks is the duration only when uninterrupted.
- The listed spring-to-tree routes take 4–7 movement ticks. One nearby gathering trip is therefore not inherently water-limited. Longer useful itineraries and supplying others must justify the canteen.

### Worked day without the canteen

1. A spring drink completes at hydration 10,000 **before that tick's metabolism**; the committed boundary is 9,900.
2. Walk 5 ticks to the cave: 9,400.
3. Sleep 48 uninterrupted ticks: 4,600.
4. Walk 5 ticks back: **4,100**, above the urgent threshold.

This is one chosen itinerary, not a rule requiring cave sleep or a water trip every morning. For the same sequence at rc2 decay 120, committed hydration would be **9,880 → 9,280 → 3,520 → 2,920**, not the 3,040 quoted in rc2. The resident is not urgent on waking, but crosses on the return journey. At rc3 values a canteen drink on waking raises 4,600 to 10,000 before metabolism (600 serving units wasted); after that tick it is 9,900. Drinking earlier than necessary can waste water. Measure the travel benefit rather than assuming cave use is optimal.

### No-resource death approximations (from initial needs)

- **No water:** 8,000 reaches zero at completed tick **80**. The first health loss occurs that same tick, so death is at `80 + ceil(10000/70) - 1 = 222` (~**1.54 days**). rc2's comparable exact tick is 209 (~1.45 days). This is an isolated deprivation calculation, not a discoverability measurement.
- **No food:** 7,500 reaches zero at tick 300; death is at **442** (~**3.07 days**), assuming water remains sufficient and no other health loss occurs.
- Sleep and rest do not slow either decline.
- Two canteen servings replace up to **120 additional ticks** of hydration decay when used without cap waste; Ryan may transfer the canteen rather than consume both himself.

## 2. Spatial scale and computed routes

- `map.tile_size_m = 50`, so the 64×64 grid is about 3.2 km on a side. About 2,560 tiles are land (~6.4 km²), giving an island 2.5–3 km across.
- `map.walk_cost_budget_per_tick = 8` gives **2.4 km/h** on beach, grass, cave and moss (cost 1) and **1.2 km/h** in woods and fruit patches (cost 2). This is a deliberately slow pace for barefoot exploration of unknown, rough terrain.
- Sight: `day_radius_tiles = 8` (~400 m) and `night_radius_tiles = 3` (~150 m). Woods, fruit patches and rock block sight. Hearing: `hearing_radius_tiles = 1`, i.e. the same or an adjacent tile (≤ ~50 m), with no shouting.
- **A finite north–south rock ridge** at x = 26 blocks the direct camp-to-spring route. Its internal opening is y = 37–38; the northern and southern ends can also be bypassed (e.g. x=26 at y=20 or y=44). It is not a coast-to-coast partition. The shortest quoted camp route uses the internal opening.

**Computed route costs** (§5.3 algorithm on the fully explored authored map; movement ticks pack the actual route under the budget, rather than rounding `cost / 8`):

| From → To | Cost units | Movement ticks |
|---|---:|---:|
| Cave (13,32) → spring stand tile (37,30) | 36 | 5 (~50 min); Manhattan 27, the rest is the ridge detour |
| Cave → fruit_01 (16,36), near camp | 8 | 1 |
| Cave → fruit_02 (17,13), NW woods | 26 | 4 |
| Cave → fruit_03 (42,11), NE woods | 57 | 8 |
| Cave → fruit_04 (52,27), E woods | 61 | 8 |
| Cave → fruit_05 (40,51), SE woods | 52 | 7 |
| Cave → fruit_06 (48,46), SE woods | 53 | 7 |
| South spring stand tile (38,31) → fruit_01 / 02 / 03 / 04 / 05 / 06 | 30 / 48 / 31 / 25 / 31 / 29 | 4 / 7 / 4 / 4 / 4 / 4 |

All passable tiles are reachable from the cave. The spring lies outside every resident's starting sight.

Route calculations use a **fully explored map**, not the initial residents' knowledge, and terminate on the listed tree tile. Gathering may instead stop at a known adjacent tile. These are geometry checks; discovery, interruptions, gathering, eating and drinking add time. Required vector §5.3(b) also assumes all route tiles explored. The south-stand-to-fruit_02 route costs 48 but needs **7 ticks**, not `ceil(48/8)=6`, because unused budget is lost when the next wooded step does not fit. This is another correction to rc2.

## 3. Day-one water cue (approved option C)

- The damp-moss tile `M` is at **(15,32)**, east of the cave. The residents start at Ella (12,32), Ryan (13,32, on the cave tile) and Mia (14,32).
- Mia is one tile from `M`, so she gets the detailed clue ("damp trace running east") at the start. Ryan (distance 2) and Ella (distance 3) see only a dark patch until they step closer.
- All three can see `fruit_01` from the start; it holds one fruit.

Following the clue due east leads into the ridge. The gap is five tiles south, so the clue points the right way but does not give a route. The risk ordering is unchanged from rc1 and still **not measured**:
- no cue gives the highest discovery risk;
- a visible spring gives the lowest;
- the vague cue should fall between them, depending on whether a policy follows it.

Without water, the isolated death limit is about 1.54 days, while urgent hydration begins at tick 50 from the initial 8,000. Time before death must not be confused with comfortable exploration time. The vague cue, ridge and policy jointly determine discovery difficulty.

## 4. Tick contention, balance and regrowth

- Regrowth offsets are `(0, 24, 48, 72, 96, 120)` (unchanged from rc1). They spread fruit supply across the day.
- Completion shuffling and `RESOURCE_TAKEN` are unchanged from rc2. rc3 clarifies that physiology uses the action active during the tick, including the final sleep tick.
- **Per-step perception:** with up to 8 steps per tick, visibility is recomputed after every step (World Rules §5.1 step 5). Otherwise a resident could walk past a tree without seeing it.

## 5. Tests that justify or reject candidate values (future, not yet executed)

1. **Economic conservation:** at every tick, exact integer checks that initial fruit + actual regrowth = fruit on trees + fruit carried + fruit on the ground + fruit eaten. Also check canteen uniqueness and capacity, and that no stock goes negative.
2. **Baseline viability:** run 3 rule-based residents for 1,008 ticks with multiple seeds. Record:
   - how many runs keep all three alive, and the deaths;
   - when the spring is first found and how;
   - fruit-deficit incidents.
3. **Canteen ablation:** at a fixed hydration rate, compare identical seeds/policies/geometry with and without the canteen. Removing it frees a slot, so report that confound and also compare against one reserved unusable slot if inventory capacity affects outcomes. Measure per resident and for the group:
   - dedicated spring trips (a visit whose only completed useful actions are drinking/filling), movement ticks and water-related actions;
   - completed gathers/transfers and useful multi-stop itinerary length, not distance alone;
   - canteen transfers followed by drinking, and cap-wasted hydration;
   - urgent/deprived incidents, discovery time, deaths and sleeping location as diagnostics.

   First run both canteen conditions at decay **100**, then repeat at **120** without changing geometry, speed or policy. Do not assert the canteen is valuable solely because a nonholder dies, or because a deliberately water-inefficient policy uses it. If task throughput/travel do not improve meaningfully, report that result and consider local placement or a revised item goal. Predeclare the practical acceptance threshold in the P2 experiment brief; this draft does not invent a measured benefit or survival target.

   The no-canteen control needs a separately identified P2 experimental fixture/schema that permits absence of the item. It is not a valid default-island P1 save, which requires exactly one canteen. Specify that fixture and its invariant exception in the P2 brief before running the comparison; do not silently delete the item from a valid production snapshot.
4. **Cue ablation:** cue C vs. no cue vs. visible spring. Report empirical rates with their uncertainty.
5. **Fruit headroom:** if residents starve despite theoretical supply exceeding demand, separate discovery, travel, unequal access and cap waste before blaming total production. Tune declared placement/count/rates, never hidden supplies.
6. **Save/replay, path/LOS and determinism:** same as rc1, plus:
   - the two §5.3 pathfinding test vectors;
   - a per-step visibility test with a tree explicitly outside final LOS: passing it must update the footprint/receipts and deliver one captured transient entry; passing a near cue must preserve its detailed description;
   - saving before packet delivery and restoring must yield the identical packet once, then identical decisions/events;
   - complete-intent restoration for gather/give/talk, first-exposure novelty, interruption priority and final sleep-tick physiology.
7. **Stability/cost:** measure real LLM calls and latency per day after P3.

## 6. Current risks and recommended knobs

- **Moderate survival is unproven.** Decay 100 is a conservative comparison candidate, not a proven fix. First-discovery risk remains; reaching the known spring is much easier than finding it. Evaluate exploration separately from steady-state water supply.
- **Cave benefit may vanish at the cap.** Do not justify geometry or dehydration by a nominal sleep bonus that produces no actual stamina gain. A policy may reasonably camp at the spring.
- **Food is tighter than in rc1** because of travel; see §1.
- **The cue may be followed into the ridge** and abandoned. That is legitimate behaviour, but watch it in the cue ablation.
- **Bigger map and retained observation metadata.** Per-step sight is at most 8 movement samples × 3 residents × 145 candidate tiles at day radius 8, **plus boundary scans**; Bresenham also traverses intervening cells. Receipt sets and pending packets add storage. Profile the implementation rather than claiming negligible cost in advance.
- Integer state avoids floating-point drift, but determinism still depends on the explicit ordering and serialization rules.
