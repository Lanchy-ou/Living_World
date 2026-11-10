# Living Island — P2 Experiment Spec v0.1

> **Draft for M5 (P2-00).** Status: proposed. It takes effect after the owner's M5 approval.
> It defines the scenarios, seeds, metrics, pass lines and run identity used by P2-02..P2-05.

Code references are `path:line` on `04fde8b`, relative to `backend/src/living_island/`
unless stated. Abbreviations are as in `rule-policy-v0.1.md` (RP).

## 0. Run artifacts (facts on 04fde8b)

| Artifact | Content | Source |
|---|---|---|
| `events.jsonl` | every `WorldEvent`, canonical, emission order | `persistence/logs.py:19` |
| `decisions.jsonl` | every `DecisionRecord` | `persistence/logs.py:20` |
| `config.json`, `map.txt` | retained typed config and map | `persistence/content.py:32-33` |
| `checkpoint-0000000000.json`, `checkpoint-<final>.json` | `SavePackage` at tick 0 and the final tick (always written) | `sim/runner.py:154-158` |
| `decision-trace.json` | `DecisionTraceManifest` after a successful full run | `sim/runner.py:218`, `persistence/trace.py:26` |
| `frames.jsonl` → `replay.json` | one `DisplayFrame` per tick, 0..T, with exact conditions, positions, alive, fruit, canteen servings and tree stocks; written only with `--export-replay` | `sim/cli.py:291`, `:300`, `:327-328`; `persistence/replay.py:27-28`; `contract/projections.py:16-65` |

- **Tick-zero exploration footprint.** It is recorded as events. `initial_commit` emits
  `world_initialized` and then one `exploration_updated` per resident at tick 0, with that
  resident's full initial footprint (`world/engine.py:242-273`, `:816-831`). Later ticks emit
  the newly seen indices (`world/engine.py:716`). The tick-zero checkpoint holds the same
  footprint in `world.explored_tiles_by_resident`.
- Action facts carry `actor_id` = the acting resident, `target_id` = an entity or resident
  target ID (null for tile targets), and the `intent_id` (`world/engine.py:357-376`). Settled
  facts (`fruit_gathered`, `water_drank`, `item_given`, `item_picked_up`, `fruit_consumed`)
  carry `actor_id` = the acting resident (`world/actions.py:136-235`).
- A dead resident stays in every frame with `alive=false` and its last conditions
  (`contract/projections.py:30-43`, `world/death.py:71`).

**Rule:** every experiment run is started with `--export-replay`, so `replay.json` exists for
every run (plan §2 P2-00 item 4). No other sidecar is defined. The analysis reads only the
artifacts above and never writes into a run directory.

## 1. Scenario matrix

All scenarios keep the content rules of WR §1.1/§1.2, as validated by
`world/content.py`: one `S`, one `C`, one `M` with one cue, one `F` per configured tree,
spawns on passable tiles, one canteen with a configured owner, and unique IDs (CR-002).
Scenario files live under `content/scenarios/<scenario_id>/world.toml`. They reuse
`content/worlds/default-island.map` through a relative `layout_file`, which is allowed
(`persistence/content.py:40-49`). `meta.run_id` is set per scenario.

| ID | Purpose | Content (single changed factor vs. S2 original) | Policy variants | Created by |
|---|---|---|---|---|
| S1 `s1-spring-visible` | survival without discovery | spawns only: ella (33,32), ryan (34,32), mia (35,32). All grass; the spring (38,30) is in tick-zero sight from each (checked with `world/space.py:129`, radius 8 at tick 0). The cave, cue and trees are unchanged (OQ-059). | `base` | P2-02 |
| S2 `s2-default` | blind default | none: `content/worlds/default.toml` (original, label `orig`); after M6 the approved default (label `m6`) | `base`, `canteen-restricted`, `cue-ignored` | exists |
| S3 `s3-regrow288` | scarcity | `fruit.regrow_ticks = 288` (from 144). This halves regrowth supply from 6 to 3 per day, below the 5.4 per day steady demand (BN §1). Offsets 0..120 stay valid (OQ-058). | `base` | P2-02 |
| S4 `s4-decay120` | canteen round 2 | `needs.hydration_decay_per_tick = 120` (from 100; BN §5 item 3) | `base`, `canteen-restricted` | P2-04 |

- **S4 at decay 100** is the S2 pair `base` vs. `canteen-restricted`.
- **S5** is the S2 pair `base` vs. `cue-ignored`. Map, spawns, settings, cue, perception and
  triggers are identical; only RP §6.3 differs. S1 vs. S2 is a survival-versus-discovery
  diagnosis (plan §2 item 2) and is never reported as the cue's effect.
- A run of S2 `base` is computed once per seed and reused as the S4@100 and S5 control arm.
- **Policy variants** (RP §8): `base` = `{enabled, enabled}`; `canteen-restricted` =
  `{restricted, enabled}`; `cue-ignored` = `{enabled, ignored}`; numeric defaults
  `fruit_carry_target=2`, `failed_target_retry_ticks=36`.
- **Labeling:** every run is labeled `(scenario_id, content revision, policy variant)`, where
  content revision = `<label>@<config_sha256[0:12]>` of the effective config with the seed
  override (`sim/cli.py:306-309`). The full hashes are in the manifest (§6).

## 2. Seeds

Seeds come from a stated procedure, fixed before any rule-policy run. For a list name `L`:
for `i = 0, 1, 2, …`, take
`seed = 1 + (uint32_be(SHA-256(UTF8("living-island/p2/<L>/<i>"))[0:4]) mod (2^32 - 1))`.
Skip values already in the list or in any earlier registered list, and stop at 20.
The development list is generated first, then acceptance excluding it.

**Development (`development`)**, used by P2-02 and P2-04:
2195683955, 937154673, 1452436788, 1883209505, 497199041, 3459030352, 2507182619,
3698676642, 2144999532, 1263016932, 2344699806, 1011827743, 2104929825, 2520148199,
201486072, 1021125776, 1334592829, 3695162045, 3976177611, 404876745

**Acceptance (`acceptance`)**, held out and used only by P2-05 after M6 freezes the
candidate:
2600456787, 3335059634, 2733016023, 958049702, 3486741106, 1557484054, 4155892942,
3501343423, 330361958, 3178109895, 969717619, 857949281, 2170312666, 1007489817,
2560155364, 1802799976, 1569596598, 646834264, 2122883013, 598561891

The two lists are disjoint (verified when generated). Seeds are passed with `--seed`.
**Replacement:** if any acceptance result informs tuning, register a fresh list
`acceptance-r<n>` (`n = 1, 2, …`) by the same procedure, excluding all earlier lists, before
evaluating the revised candidate. Earlier acceptance results stay in the report (plan §1.1).
Development count 20 is an assumption pending measured run time (OQ-060).

## 3. Metrics

**Notation.**
- `T` is the final tick (1008); `F[k]` is the frame at tick `k`; `min` is
  `condition_bounds.min_value` (0).
- Spring tiles are the `S` positions in the retained map, with index `y*width+x` (IC §2.1).
- A position is **spring-adjacent** if it is at Manhattan distance exactly 1 from a spring
  tile.
- **Completed action:** an `action_succeeded` event of the resident (`actor_id`); its type is
  `payload.action_type` and its tick is the completion tick.

### 3.1 Per resident

| Metric | Exact definition | Source |
|---|---|---|
| `first_spring_discovery_tick` | minimum `tick` of an `exploration_updated` with `payload.resident_id = r` whose `newly_seen_tile_indices` contains a spring index; tick 0 included. Null = *not found*. | events |
| `first_drink_tick` | minimum `tick` of `water_drank` with `actor_id = r` (any source); also report `first_spring_drink_tick` (`payload.source="spring"`) | events |
| `alive_at_T` | `F[T]` resident `alive` | replay; cross-check final checkpoint |
| `death_tick`, `death_cause` | `tick` and `payload.cause` of `resident_died` with `payload.resident_id = r`; null if none | events |
| `ticks_alive` | `#{k in 1..T : F[k].alive}`; the death tick does **not** count | replay |
| `exposure_ticks` | `#{k in 1..T : F[k-1].alive}` = intervals lived through, the death interval included | replay |
| `ticks_deprived` | `#{k in 1..T : F[k-1].alive and (F[k].satiety = min or F[k].hydration = min)}`; the death tick **does** count, because health loss in that interval is deprivation (WR §3). A critical band alone is never deprivation. Also split into `_water` and `_food` (both may hold). | replay |
| `water_only_visits` | number of visits (below) with at least one completed action whose completed non-`move_to` actions are all `drink` or `fill_canteen` | replay + events |
| `dedicated_water_trips` | water-only visits whose travel leg has no completed `gather`, `give` or `pick_up` (OQ-057) | replay + events |
| `gathers_completed` | count of `fruit_gathered` with `actor_id = r` | events |
| `fruit_given`, `fruit_received`, `canteen_given`, `canteen_received` | `item_given` by `payload.from_id`/`to_id` and `item_type` | events |
| `pickups` | `item_picked_up` with `payload.resident_id = r`, by item type | events |
| `canteen_drinks`, `canteen_fills` | `water_drank` with source `canteen`; `canteen_filled`, by `actor_id` | events |
| `hydration_cap_waste` | sum over `water_drank` of `hydration_before + needs.hydration_gain_per_serving - hydration_after` | events + `config.json` |
| `movement_ticks` | number of ticks with at least one `resident_moved` of `r` | events |
| `slot_full_incidents` | `action_failed` with `failure_code="INVENTORY_FULL"` where `r` is the actor, plus failed `give`s to `r` with that code; each tagged with whether `r` held the canteen at `F[tick-1]` | events + decisions + replay |
| `censoring` | `not_found` if discovery is null; `found_not_drunk` if discovery is non-null, `r` died, and there is no `water_drank` by `r` at a tick ≥ discovery; else `none` | derived |

- **Visit:** a maximal run of consecutive frames `F[a..b]` in which `r` is alive and
  spring-adjacent.
- **Travel leg:** the ticks strictly between the end of `r`'s previous visit (or tick 0) and
  the visit start `a`.
- A completed action belongs to the visit if its completion tick is in `a..b`.
- A completed non-move action has the same position as `F[tick]`, because non-move actions
  do not move.

Censored residents are counted, never averaged. Time-to-event means and medians (discovery,
first drink) are over uncensored residents only, reported with their `n`.

### 3.2 Per run

Each instance cites event IDs and `(actor_id, decision_ordinal)` of decision records. The
target of an intent is read from the `decisions.jsonl` plan that contains its `intent_id`.

- **C1 contention:** in one tick, a successful `fruit_gathered` (or `item_picked_up`) on
  target `X`, and an `action_failed` with `RESOURCE_TAKEN` (or `ITEM_TAKEN`) by another
  resident whose intent targets `X`. For trees `X` is the tree ID; for pick-ups it is the
  tile. One instance per failed event.
- **A1 adaptation after failure:** an `action_failed` `E` of `r` with code in {`RESOURCE_TAKEN`,
  `ITEM_TAKEN`, `NO_PATH`, `PATH_BLOCKED`, `OUT_OF_REACH`, `INVENTORY_FULL`} on target `X`, and
  `r`'s first decision record `D` with `tick >= E.tick` whose plan has no intent targeting `X`.
  `move_to` and `pick_up` intents target their tile; gather, give and talk target their entity
  or resident. Cite `E.event_id` and `D`.
- **A2 adaptation after depletion:** a record `D` of `r` at tick `t` such that `r`'s previous
  record contained `gather X`, `F[t]` shows tree `X` with `stock = 0`, and `D` has no intent
  targeting `X`, and `D` is not already cited by an A1 instance (each record is counted
  once, A1 first). Cite both records and the `fruit_gathered` event with `stock_after = 0`
  for `X` at the latest tick ≤ `t`, if one exists.
- **Route and action evidence:** per resident, completed actions by type, movement ticks,
  spring-adjacent frames, and gathers per tree. These are associations. A report states a
  cause only with a single-factor paired comparison (§5), never from one run.
- **Fruit conservation:** per frame, `sum(stock at tick 0) + sum(fruit_regrew.quantity up to k)
  = trees + residents' fruit + ground fruit + sum(fruit_consumed.quantity up to k)` (WR §8.2).

## 4. Pass lines

**Technical validity (per run).** A run is valid iff all of these hold:
1. The CLI exits 0 and the final tick is `T = 1008`.
2. `decision-trace.json` loads and verifies through `persistence/trace.py:85` (`load_trace`).
3. `replay.json` exists and validates as `ReplayBundle` (`contract/replay.py:226`), with
   `T + 1` frames.
4. Fruit conservation (§3.2) holds at every frame.
5. Zero records have `substituted = true`.

An invalid run fails the technical gate and is never counted as a survival pass or failure.

**PD-05 (M7).** Run S2 `m6` × `base` × the 20 acceptance seeds. All 20 must be valid. Let `x`
be the number with all three residents `alive_at_T`. Pass iff `x >= 15`. Report the Wilson
95% interval with `z = 1.959964`, `p = x/20`, `n = 20`:
`(p + z²/2n ± z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n)`. It assumes the seeds are independent
draws from this generation procedure. It is evidence on this registered set, not a guarantee
(plan §1.1). The analysis may use floats; they never enter world state.

**S1 (B03).** On all 20 development seeds, S1 `base` runs are valid with all three alive at
`T`.

**S3 evidence (B05).** Every S3 `base` development seed has at least one C1, A1 or A2
instance, with its event IDs and decision records cited.

**Diagnostics, not gates:** behavioral variation (first discovery tick, discovery order, the
set of frontier targets in the first 144 ticks, and survival). Report the observed fraction of
seeds that differ from the modal pattern, with a Wilson interval. There is no diversity quota.

## 5. Paired comparisons

- **Pairing:** two arms on the same seed and scenario content, differing in one factor.
  Compare **run-level aggregates per seed pair**, never tick by tick (plan §1.3 item 4).
- **Report:** for each arm, absolute run totals, per-resident rates per `exposure_tick`, and
  deaths. Give the per-pair difference distribution (median, min, max, and the number of pairs
  favoring each arm). Invalid runs drop their pair, and the count is reported.
- **S4 (PD-07):**
  - Arms `base` vs. `canteen-restricted`. Round 1 is S2 at decay 100 on the 20
    development seeds. Round 2 is S4 `s4-decay120` on the same seeds, geometry, speed and
    policy version.
  - Metrics: dedicated water trips, water-only visits, movement ticks, gathers, transfers
    followed by a drink by the recipient within its next 144 ticks, canteen drinks and fills,
    cap waste, slot-full incidents per holder, ticks deprived, discovery, and deaths.
  - The confounds of plan §1.3 items 1–6 are stated in the report: initial servings are part
    of the treatment; slot occupancy; no pick-up in the restricted arm; divergence; deaths
    shorten exposure; variant identity in the manifest.
  - Deaths are tabulated by whether the resident held the canteen at `F[death_tick-1]`. A
    nonholder death is never counted as canteen benefit (WR §9).
  - Recorded re-execution (`reexecute`) is run for one seed per arm and must reproduce event
    and decision bytes and the final world hash.
  - **Deferral:** round 2 may be deferred only if measured run time makes it impractical,
    with the reason and the owner's OQ disposition recorded before M6. The 120 result never
    selects the default by itself.
  - There is no predeclared benefit threshold; the S4 report is descriptive (PD-03, OQ-061).
- **S5:** arms `base` vs. `cue-ignored` on S2. Metrics: discovery tick, censoring categories,
  deaths, and ticks deprived (water).
- **S1/S2:** survival and the censoring split *not found* / *found, not drunk* / *supply
  shortfall*. Supply shortfall means a death with water found and drunk, whose deprivation
  is food-only or comes after discovery (BN §5 item 5).

## 6. Manifest and experiment-case identity

OQ-049 stays deferred. `run_id` comes from the scenario file and is shared across seeds.
Cases are told apart by an **experiment-case ID**:
`<scenario_id>.<revision_label>.<variant_id>.s<seed>`, for example
`s2-default.orig.base.s2195683955`. Each case has its own output directory
`runs/p2/<batch_id>/<case_id>/` (ignored: root `.gitignore:25`). P2-03 writes
`p2-manifest.json` per case, canonical JSON (IC §6.3), next to it in the batch directory and
never inside the run directory:

```text
P2CaseManifest {
  manifest_version:"0.1", case_id, batch_id, scenario_id, revision_label, seed,
  policy_id:"rule-based-v0", policy_variant_id, rule_params:RuleParams,
  policy_config_sha256,          // SHA-256 of the canonical tick-0 runtime PolicyConfig
  config_sha256, map_sha256,     // from world_initialized; identity of world content
  run_id, output_dir,            // relative to the batch directory
  events_sha256, decisions_sha256, final_world_sha256,  // from decision-trace.json
  code_commit                    // git commit of the code that ran
}
```

`policy_config_sha256` separates policy arms with the same `config_sha256` (plan §1.3 item 6,
§1.2: a world config hash does not identify a policy setting). It is read from the tick-zero
checkpoint's `runtime_states[*].policy_config`, which must be identical across residents.
Re-running a manifest must reproduce identical counts and the three log/world hashes (B08).

## 7. Analysis module

- **Location:** `backend/src/living_island/analysis/`. It is pure and holds no file IO:
  metric functions over parsed `WorldEvent`, `DecisionRecord` and `ReplayBundle` objects, the
  map rows and the retained config values it needs (`hydration_gain_per_serving`).
- **Loading:** `scripts/p2_experiments.py` reads run directories. It uses the read-only
  persistence API (`load_trace`, checkpoint and replay decoding) and passes models into the
  module. It writes only manifests and summaries under the batch directory.
- **Dependency contract** (P2-03 adds it to `backend/pyproject.toml`; no existing contract
  changes):

```toml
[[tool.importlinter.contracts]]
name = "analysis is read-only: no world internals, sim, persistence or policies"
type = "forbidden"
source_modules = ["living_island.analysis"]
forbidden_modules = [
    "living_island.world",
    "living_island.sim",
    "living_island.persistence",
    "living_island.memory",
    "living_island.agents.runtime",
    "living_island.agents.policies",
    "living_island.agents.rule_based",
]
allow_indirect_imports = true
```

  The module may import `living_island.events`, `living_island.contract` and
  `living_island.agents.types`. Their own imports of `world.facts`/`world.protocol` are
  indirect and allowed by design. Without `allow_indirect_imports`, those imports would
  trigger the contract. The installed import-linter 2.16 supports this option
  (`backend/uv.lock:239-240`).
- The long matrix runs only through a separate command, outside default CI (OQ-053). P1 CI
  stays unchanged.

## 8. Worked example (test oracle for P2-03)

A toy run, `run_id="toy"`, `T = 8`, map `6×3`, one spring at `(5,1)` (index 11), tree `t1`
at `(2,2)`, residents `a`, `b`, `c`, `needs.hydration_gain_per_serving = 6000`, `min = 0`.
Frame values not listed are nonzero, and residents stay alive unless stated. Tree `t1`
has stock 1 in `F[0..4]` and 0 in `F[5..8]`.

| Tick | a position | b alive / hydration | c position |
|---|---|---|---|
| 0 | (0,1) | true / 150 | (1,2) |
| 1 | (2,1) | true / 50 | (1,2) |
| 2 | (4,1) | true / 0 | (1,2) |
| 3 | (4,1) | false / 0 | (1,2) |
| 4 | (2,1) | false / 0 | (1,2) |
| 5 | (2,1) | false / 0 | (1,2) |
| 6 | (4,1) | false / 0 | (1,2) |
| 7 | (4,1) | false / 0 | (1,2) |
| 8 | (4,1) | false / 0 | (1,2) |

`b` stays at `(0,0)`, which is not spring-adjacent.

Events (only those used; IDs `toy:<tick 10 digits>:<seq 6 digits>`):
- tick 0:
  - `exploration_updated` `a` without 11;
  - `exploration_updated` `b` with 11;
  - `exploration_updated` `c` without 11.
- tick 2: `exploration_updated` `a` with 11.
- tick 3:
  - `water_drank` actor `a`, source spring, before 2000, after 8000;
  - `action_succeeded` `a` drink;
  - `resident_died` `b` cause `DEPRIVATION`.
- tick 5:
  - `fruit_gathered` actor `a`, tree `t1`, stock 1→0 (`toy:0000000005:000000`);
  - `action_succeeded` `a` gather;
  - `action_failed` actor `c`, `RESOURCE_TAKEN`, intent `c:p000001:i0`
    (`toy:0000000005:000002`).
- tick 7:
  - `water_drank` actor `a`, source spring, before 7000, after 10000;
  - `action_succeeded` `a` drink.

Decisions:
- `c` ordinal 1 at tick 3: plan `[gather entity t1]` (intent `c:p000001:i0`).
- `c` ordinal 2 at tick 5: triggers `[ACTION_FAILED]`, plan `[move_to (0,2)]`.

Expected values:

| Metric | a | b | c |
|---|---|---|---|
| first_spring_discovery_tick | 2 | 0 | null |
| first_drink_tick | 3 | null | null |
| alive_at_T / death_tick | true / null | false / 3 | true / null |
| ticks_alive / exposure_ticks | 8 / 8 | 2 / 3 | 8 / 8 |
| ticks_deprived | 0 | 2 (k=2, k=3) | 0 |
| water_only_visits / dedicated_water_trips | 2 / 1 | 0 / 0 | 0 / 0 |
| gathers_completed | 1 | 0 | 0 |
| hydration_cap_waste | 3000 (0 + 3000) | 0 | 0 |
| censoring | none | found_not_drunk | not_found |

Derivation of `a`'s visits:
- Visits are frames 2..3 and 6..8.
- Visit 1 has the drink at tick 3, and its leg (ticks 1) has no gather: **dedicated**.
- Visit 2 has the drink at tick 7, but its leg (ticks 4..5) has the gather at tick 5:
  water-only, **not dedicated**.

Per run:
- C1 = 1: tick 5, `toy:0000000005:000000` with `toy:0000000005:000002`.
- A1 = 1: `toy:0000000005:000002` with `(c, 2)`.
- A2 = 0: `(c, 2)` also meets the A2 conditions (previous record `gather t1`, `F[5]` stock
  0), but it is already cited by A1, so it is not counted again.
