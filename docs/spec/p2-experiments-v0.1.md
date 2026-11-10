# Living Island — P2 Experiment Spec v0.1

> **Draft for M5 (P2-00, rework 1).** Status: proposed. It takes effect after the owner's M5
> approval. It defines the scenarios, seeds, metrics, pass lines and run identity used by
> P2-02 to P2-05.

Code references are `path:line` on `04fde8b`, relative to `backend/src/living_island/`
unless stated. Abbreviations are as in `rule-policy-v0.1.md` (RP).

## 0. Run artifacts (facts on 04fde8b)

| Artifact | Content | Source |
|---|---|---|
| `events.jsonl` | every `WorldEvent`, canonical, in emission order | `persistence/logs.py:19` |
| `decisions.jsonl` | every `DecisionRecord` | `persistence/logs.py:20` |
| `config.json`, `map.txt` | retained typed config and map | `persistence/content.py:32-33` |
| `checkpoint-0000000000.json`, `checkpoint-<T 10 digits>.json` | `SavePackage` at tick 0 and the final tick; a fresh run always writes both | `sim/runner.py:154-158` |
| `decision-trace.json` | `DecisionTraceManifest`, after a successful full run | `sim/runner.py:218`, `persistence/trace.py:26`, `:108-131` |
| `frames.jsonl` → `replay.json` | one `DisplayFrame` per tick 0..T, with exact conditions, positions, `alive`, fruit, held canteen servings, tree stocks, ground items and corpses; written only with `--export-replay` | `sim/cli.py:49`, `:58`, `:85-86`; `persistence/replay.py:27-28`, `:51-116`; `contract/projections.py:16-65` |

- **Tick-zero footprint.** It is in the events.
  - `initial_commit` emits `world_initialized`, then one `exploration_updated` per resident
    at tick 0 carrying the full initial footprint (`world/engine.py:242-273`, `:816-831`).
  - Later ticks emit only newly seen indices (`world/engine.py:716`).
  - The tick-zero checkpoint holds the same footprint in `world.explored_tiles_by_resident`.
- **Action facts** (`action_started`, `action_succeeded`, `action_failed`,
  `action_interrupted`, `resident_moved`, `utterance_spoken`) carry the following
  (`world/engine.py:357-376`):
  - `actor_id`: the acting resident;
  - `target_id`: the entity or resident target ID, or null for tile targets;
  - `intent_id`.
- **Settled facts** (`fruit_gathered`, `water_drank`, `item_given`, `item_picked_up`,
  `fruit_consumed`) carry `actor_id` = the acting resident (`world/actions.py:136-235`).
- **A dead resident** stays in every frame with `alive=false` and its conditions from the
  death tick. Its fruit is dropped (`fruit_count=0`) and its canteen goes to the ground
  (`world/death.py:71`, `:101-104`, `:122-124`; `contract/projections.py:30-43`).

**Rules:**
- Every experiment run uses `--export-replay`.
- The only inputs to analysis are the run artifacts above, the batch's manifests and variant
  files (§6), and nothing else. There is no sidecar.
- Analysis never writes into a run directory.

## 1. Scenario matrix

All scenarios keep the content rules of WR §1.1/§1.2 as validated by `world/content.py`:
- one `S`, one `C`, one `M` with exactly one cue, and one `F` per configured tree;
- spawns on passable tiles;
- one canteen with a configured owner;
- unique IDs (CR-002).

Scenario files are `content/scenarios/<scenario_id>/world.toml`. Each reuses the map file
`content/worlds/default-island.map` through `layout_file = "../../worlds/default-island.map"`
(relative paths are accepted, `persistence/content.py:40-49`).

**Metadata, not treatment.** Only these fields may differ from S2 without counting as a
changed factor:
- the file location;
- `meta.run_id`, set to the scenario ID with `-` replaced by `_`;
- the `map.layout_file` string, which must resolve to byte-identical map content: same
  `map_sha256`.

`meta.world_id` and `meta.seed` stay as in S2; the seed is overridden per case with `--seed`.

| ID | Purpose | Single changed factor vs. S2 `orig` | Variants | Created by |
|---|---|---|---|---|
| S1 `s1-spring-visible` | survival without discovery | spawns only: ella (33,32), ryan (34,32), mia (35,32). All grass; each sees the spring (38,30) at tick 0 (`world/space.py:129`, radius 8). Cave, cue and trees unchanged (OQ-059). | `base` | P2-02 |
| S2 `s2-default` | blind default | none: `content/worlds/default.toml` (label `orig`); after M6, the approved default (label `m6`) | `base`, `canteen-restricted`, `cue-ignored` | exists |
| S3 `s3-regrow288` | scarcity | `fruit.regrow_ticks = 288` (from 144). This halves regrowth supply from 6 to 3 per day, below the 5.4 per day steady demand (BN §1). Offsets 0..120 stay valid (OQ-058). | `base` | P2-02 |
| S4 `s4-decay120` | canteen round 2 | `needs.hydration_decay_per_tick = 120` (from 100; BN §5 item 3) | `base`, `canteen-restricted` | P2-04 |

- **S4 at decay 100** is the S2 pair `base` vs. `canteen-restricted`.
- **S5** is the S2 pair `base` vs. `cue-ignored` (only RP §6.3 differs).
- S2 `base` runs once per seed and serves as the control arm of both.
- **S1 vs. S2** is a survival-versus-discovery diagnosis, never a cue estimate.
- **Development matrix per seed:** S1/base, S2/base, S2/canteen-restricted, S2/cue-ignored,
  S3/base, S4/base, S4/canteen-restricted. That is 7 cases × 20 seeds = 140.
- **Acceptance matrix:** S2 `m6`/base × 20 acceptance seeds.

## 2. Seeds

The seeds come from a stated procedure, fixed before any rule-policy run. For a list name `L`
and `i = 0, 1, 2, …`:

`seed = 1 + (uint32_be(SHA-256(UTF8("living-island/p2/<L>/<i>"))[0:4]) mod (2^32 - 1))`

Values already in this list or in any earlier registered list are skipped; generation stops
at 20 seeds. The development list is generated first.

**Development (`development`)**, used by P2-02 and P2-04:
2195683955, 937154673, 1452436788, 1883209505, 497199041, 3459030352, 2507182619,
3698676642, 2144999532, 1263016932, 2344699806, 1011827743, 2104929825, 2520148199,
201486072, 1021125776, 1334592829, 3695162045, 3976177611, 404876745

**Acceptance (`acceptance`)**, held out, used only by P2-05 after M6:
2600456787, 3335059634, 2733016023, 958049702, 3486741106, 1557484054, 4155892942,
3501343423, 330361958, 3178109895, 969717619, 857949281, 2170312666, 1007489817,
2560155364, 1802799976, 1569596598, 646834264, 2122883013, 598561891

- The two lists are disjoint: the Gate 2 reviewer regenerated both, 40 unique values.
- **Replacement:** if any acceptance result informs tuning, register `acceptance-r<n>`
  (`n = 1, 2, …`) by the same procedure, excluding all earlier lists, before evaluating the
  revised candidate. Prior results stay in the report.
- The development count 20 is pending measured time (OQ-060).

## 3. Metrics

### 3.0 Notation and joins

- **Ticks:** `T` is the final tick (1008). `F[k]` is the replay frame with `tick = k`; frames
  are complete 0..T (§4). `min = condition_bounds.min_value` (0).
- **Joins:** a resident is joined by `id` in frames and by `payload.resident_id`, `actor_id`,
  `from_id` or `to_id` as stated per metric. A tree is joined by ID and a tile by `(x,y)`.
  Events are ordered by `(tick, seq_in_tick)`.
- **Intent target:** the target of the intent with that `intent_id` in the decision record
  whose plan contains it (`decisions.jsonl`). Plan IDs are unique per actor and ordinal, so
  the join is unique.
- **Spring tiles:** the `S` positions in `replay.json` `map.rows`; tile index `y*width+x`.
  A position is **spring-adjacent** if it is at Manhattan distance exactly 1 from a spring
  tile (RP F8).
- **Completion:** an `action_succeeded` event; its actor is `actor_id`, its type
  `payload.action_type`, its intent `intent_id`, its tick the completion tick.
- **Observation end** `end(r)` = `death_tick(r)` if `r` died, else `T`. A timing event counts
  only if its tick ≤ `end(r)`; nothing exists after death.
- **Exposure:** `exposure_ticks(r) = #{k in 1..T : F[k-1].alive}`. Every resident is alive
  at tick 0, so exposure ≥ 1 when `T ≥ 1`. The rate of a count `c` is `c / exposure_ticks`,
  reported as an exact fraction plus a 6-decimal value. With `T = 0` rates are null; this
  never happens in P2 runs.
- **Nulls:** a missing event gives `null`, never 0. Counts of nothing are 0.

### 3.1 Per resident `r`

| Metric | Definition | Source |
|---|---|---|
| `first_spring_discovery_tick` | min tick of `exploration_updated` with `payload.resident_id = r` containing a spring index; tick 0 included; null if none | events |
| `first_drink_tick` | min tick of `water_drank` with `actor_id = r`, any source; null if none | events |
| `first_spring_drink_tick` | the same restricted to `payload.source="spring"` | events |
| `alive_at_T` | `F[T]` alive for `r`; must equal the final checkpoint (§4) | replay, checkpoint |
| `death_tick`, `death_cause` | tick and `payload.cause` of `resident_died` with `payload.resident_id = r`; null if none | events |
| `ticks_alive` | `#{k in 1..T : F[k].alive}`; the death tick does not count | replay |
| `ticks_deprived` | `#{k in 1..T : F[k-1].alive and (F[k].satiety = min or F[k].hydration = min)}`. The death tick counts (WR §3 health loss); a critical band alone does not. `_water` and `_food` count each condition separately; a tick may count in both. | replay |
| `water_only_visits` | visits (below) with ≥ 1 completed `drink` or `fill_canteen` and no completed action of another type except `move_to` | replay + events |
| `dedicated_water_trips` | water-only visits whose travel leg has no completed `gather`, `give` or `pick_up` (OQ-057) | replay + events |
| `gathers_completed` | count of `fruit_gathered` with `actor_id = r` (fruit quantity = this count; `quantity` is always 1) | events |
| `given_count` / `given_qty` | per `item_type`: count of `item_given` with `payload.from_id = r` / sum of `payload.quantity` | events |
| `received_count` / `received_qty` | the same with `payload.to_id = r` | events |
| `pickups_count` / `pickups_qty` | per item type: `item_picked_up` with `payload.resident_id = r` | events |
| `canteen_drinks`, `spring_drinks` | `water_drank` with `actor_id = r`, by `payload.source` | events |
| `canteen_fills` | `canteen_filled` with `actor_id = r` | events |
| `hydration_cap_waste` | Σ over `water_drank` of `r`: `hydration_before + needs.hydration_gain_per_serving − hydration_after` | events + `config.json` |
| `movement_ticks` | number of distinct ticks with ≥ 1 `resident_moved` with `actor_id = r` | events |
| `slot_full_incidents` | count of `action_failed` with `failure_code="INVENTORY_FULL"` attributed to `r`, split by `holder_at = F[tick−1]` canteen held (`canteen_servings` non-null). Attribution: the **actor** for `gather`/`pick_up` (own room); the **recipient** (`target_id`) for `give`, never the giver (`world/actions.py:70`, `:115`, `:130`) | events + replay |
| `water_access` | one of: `not_found` (discovery null); `found_not_drunk` (discovery non-null and no spring drink at a tick ≥ discovery, ≤ `end(r)`); `drank` (otherwise) | derived |

A **visit** is a maximal run of consecutive frames `F[a..b]`, `a ≤ b`, in which `r` is alive
and spring-adjacent.
- A completion by `r` belongs to the visit iff its tick is in `a..b`.
- A **`move_to` completion** inside a visit is travel and is excluded from the all-water test.
  Visit 1 of the "arrival move" counterexample (EV-01) still needs an actual drink or fill.
- The **travel leg** of a visit starting at `a` is the ticks `p+1 .. a−1`, where `p` is the
  last frame of `r`'s previous visit, or −1 if there is none, so the leg starts at tick 0.

**Timing summaries.**
- **Discovery time:** over residents with non-null discovery. Report `n`, mean, median and
  min/max; residents with null discovery are reported as a count (`not_found`).
- **Time from discovery to first spring drink:** over `water_access = drank` only.
  `found_not_drunk` and `not_found` are counts, split by `alive_at_T` (survivors who found
  water but never drank are `found_not_drunk`, alive).
- **Canteen drinks:** a canteen drink does not count as finding or drinking spring water.
  `first_drink_tick` is reported separately and never enters these two summaries.

### 3.2 Per run

Every instance cites event IDs and `(actor_id, decision_ordinal)`.

- **C1 contention.**
  - Each `action_failed` event `f` with code `RESOURCE_TAKEN` (gather) or `ITEM_TAKEN`
    (pick_up), whose intent targets `X`, gives at most one C1. `X` is a tree ID for gather and
    a tile for pick_up.
  - Its match is the `fruit_gathered` event with `payload.tree_id = X` (or the
    `item_picked_up` with `payload.position = X`) in the **same tick** by a different actor,
    with the **smallest** `seq_in_tick`.
  - No match means no C1 for `f`. The C1 count is the number of matched `f`.
- **A1 adaptation after failure.**
  - Take each `action_failed` event `E` of `r` whose intent has a non-null target `X` and
    whose action is one of:
    - `move_to` with `NO_PATH`, `PATH_BLOCKED` or `INVALID_TARGET`;
    - `gather` with `RESOURCE_TAKEN`, `OUT_OF_REACH` or `INVALID_TARGET`;
    - `pick_up` with `ITEM_TAKEN`, `OUT_OF_REACH` or `INVALID_TARGET`;
    - `give` or `talk` with any code except `DEAD`, `EXHAUSTED` or `NO_ITEM`.
  - Failures of actions with a null target (`drink`, `eat`, `rest`, `sleep`, `wait`) and of
    `fill_canteen` are excluded (no `X` exists or is relevant).
  - Let `D` be the **first** decision record of `r` with `tick ≥ E.tick`, the smallest
    ordinal. `E` counts as **A1** iff no intent of `D` targets `X`. Targets compare by tile for
    `move_to`/`pick_up`, by tree ID for gather, and by resident for give/talk. Otherwise `E`
    counts as **repeat**.
  - Later decisions are not examined for `E`.
- **A2 adaptation after depletion.**
  - Take each decision record `D` of `r` at tick `t` (ordinal `o ≥ 1`) such that:
    - record `o−1` of `r` contains `gather X`;
    - `F[t]` tree `X` has `stock = 0`;
    - no intent of `D` targets `X`;
    - `D` is not the `D` of any A1 instance (each record is counted once, A1 first).
  - Cite the latest `fruit_gathered` with `payload.tree_id = X`, `stock_after = 0` and
    tick ≤ `t`, by any actor, or `null` if there is none.
- **Behavioral variation diagnostic.** Per case, a canonical signature (canonical JSON):
  - `discovery_order`: residents sorted by `(discovery tick, nulls last, actor_id)`;
  - `discovery_ticks`: per resident in ID order, the tick or null;
  - `early_frontiers`: per resident, the list in ordinal order of `move_to` targets `p` in its
    decision records with `tick ≤ 144` where `p` was a frontier at that decision. That means
    `index(p)` is not in the union of `r`'s `exploration_updated` indices with tick ≤ the
    record's tick.
  - `survival`: per resident, `alive_at_T`.

  The **modal signature** is the most frequent one among the scenario's valid seeds; ties go
  to the lexicographically smallest canonical JSON. Report the fraction of seeds whose
  signature differs from the mode, with a Wilson interval (§4). It is diagnostic only (OQ-067).
- **Route evidence.** Per resident: completions by type, `movement_ticks`, spring-adjacent
  frames, and gathers per tree. These are associations; causes need a single-factor pair (§5).

## 4. Pass lines

**Technical validity, per run.** Valid iff every check passes. Sources are in parentheses.
1. The CLI exits 0. `decision-trace.json` loads through `load_trace`
   (`persistence/trace.py:85-103`): retained content, run ID, event and decision hashes and
   counts.
2. The manifest final tick is `T = 1008`; the configured run length is `--ticks 1008`.
3. `checkpoint-0000000000.json` and `checkpoint-0000001008.json` decode with `read_checkpoint`
   against the retained content (`persistence/checkpoints.py:90-94`).
4. For the final checkpoint:
   - `SHA-256(canonical WorldState)` equals `final_world_sha256`;
   - `event_cursor` equals `event_count`;
   - `decision_record_cursor` equals `record_count`.
5. `replay.json` validates as `ReplayBundle` (`contract/replay.py:226`) with `T+1` frames, and
   matches the run:
   - `run_id`, `config_hash` and `map_hash` equal the trace manifest's;
   - `events` equals `events.jsonl` event for event, in canonical bytes;
   - `F[T]` equals the projection of the final checkpoint world
     (`contract/projections.py:16`) with the tick-T event count.
6. Every frame passes these invariants, with limits read from `config.json`:
   - **canteen uniqueness:** exactly one of the following holds — one alive resident has
     non-null `canteen_servings`, or `ground_canteen` is non-null. Dead residents have null
     servings and `fruit_count = 0`;
   - **capacity:** servings in `0..canteen.capacity_servings`;
   - **trees:** every stock in `0..fruit.max_stock_per_tree`;
   - **slots:** for each alive resident, `fruit_count + (1 if holding the canteen)` ≤
     `inventory.slot_capacity`;
   - **conservation:** Σ stock at tick 0 + Σ `fruit_regrew.quantity` up to `k` = Σ stocks +
     Σ residents' fruit + Σ ground fruit + Σ `fruit_consumed.quantity` up to `k` (WR §8.2).
7. The tick-zero checkpoint `agent_state.runtime_states[*].policy_config` values are
   identical across residents and equal the manifest's policy config (§6).
8. Zero decision records have `substituted = true`.

An invalid run is never a survival pass or failure. It fails the technical gate of every
pass line and comparison that includes it.

**PD-05 (M7).**
- **Case set:** S2 `m6`/base on the 20 acceptance seeds.
- **Technical gate:** all 20 are valid.
- **Survival:** with `x` the number of seeds with all three `alive_at_T`, pass iff `x ≥ 15`.
- **Interval:** report the Wilson 95% interval with `z = 1.959964`, `p = x/20` and `n = 20`:
  `(p + z²/2n ± z·sqrt(p(1−p)/n + z²/4n²)) / (1 + z²/n)`. For 15/20 it is
  [53.1299%, 88.8138%] (reviewer-checked).
- **Scope:** this assumes independent draws from §2's procedure. It is evidence on this set,
  not a guarantee. Floats are used only in analysis.

**S1 (B03).** All 20 development S1/base cases are valid, with all three residents alive at
`T`.

**S3 evidence (B05).** Each of the 20 S3/base cases is valid and has ≥ 1 C1, A1 or A2, with
its IDs cited.

**S4/S5 technical verdict.**
- A comparison round is technically valid iff all of its 40 cases are valid (20 seeds × 2
  arms).
- Otherwise the round reports **technical FAIL**, listing the invalid cases. Its descriptive
  summary uses only the pairs where both arms are valid, and states `pairs_used` and the
  dropped seeds (OQ-068).

## 5. Paired comparisons

- **Pairing:** same seed and content, one factor apart. Compare **run-level aggregates per
  seed pair**, never tick by tick (plan §1.3 item 4).
- **Report per arm:**
  - totals, summed over residents;
  - per-resident rates over `exposure_ticks`;
  - deaths, by `holder_at_death`: whether `F[death_tick−1]` shows the canteen held.
- **Report per pair:** the arm difference, with median, min, max and the number of pairs
  favoring each arm.
- **S4 (PD-07).** Arms `base` vs. `canteen-restricted`. Round 1 is S2 at decay 100; round 2 is
  S4 `s4-decay120`, on the same seeds, geometry, speed and policy version.
  - **Metrics:** §3.1 water-only visits, dedicated trips, movement ticks, gathers, given and
    received counts and quantities, canteen drinks and fills, cap waste, slot-full incidents,
    ticks deprived, discovery and deaths.
  - **`transfer_then_drink`:** for each `item_given` `G` of the canteen to `y` at tick `g`,
    count `G` iff a `water_drank` with `actor_id = y`, `source = "canteen"` exists at tick `t`
    with `g < t ≤ min(g + W, end(y))`, and no `item_given` of the canteen with
    `from_id = y` has a tick in `(g, t)`.
    - `W = 1440 / time.tick_minutes` is one game day, read from `config.json` (OQ-065).
    - Same-tick events are excluded, because a recipient cannot complete a drink in the
      tick it receives the canteen.
  - **Confounds:** plan §1.3 items 1–6 are stated in the report.
  - **Nonholder deaths** are never counted as canteen benefit (WR §9).
  - **Re-execution:** `reexecute` is run for the first development seed of each arm and must
    match the source event and decision bytes and the final world hash.
  - **Deferral:** round 2 may be deferred only with the reason and an owner OQ disposition
    before M6. The 120 result never selects the default by itself.
  - **No benefit threshold** (PD-03, OQ-061).
- **S5:** `base` vs. `cue-ignored` on S2. Metrics: discovery, `water_access`, deaths and
  `ticks_deprived_water`. Scope: cue directions captured at decisions only (RP §7.4).
- **S1/S2 death categories** (BN §5 item 5; OQ-066).
  - For each death, let `R` be the final deprived run: the maximal run of consecutive ticks
    counted in `ticks_deprived` that ends at `death_tick`.
    - `not_found`: discovery null or > `death_tick`;
    - `found_not_drunk`: discovered, and no spring drink at a tick ≥ discovery and ≤
      `death_tick`;
    - `post_access_dehydration`: drank at least once, and some tick of `R` has
      `hydration = min`. The spring is inexhaustible, so this is never supply shortfall;
    - `food_supply_shortfall`: drank at least once, every tick of `R` has `satiety = min` and
      `hydration > min`, and the sum of all tree stocks is 0 at every frame `F[k]` for `k` in
      `R`;
    - `food_access_shortfall`: as the previous category, but some frame in `R` has a positive
      total tree stock.
  - Only `food_supply_shortfall` is reported as supply shortfall.

## 6. Manifest and experiment-case identity

OQ-049 stays deferred: `run_id` comes from the scenario file. A case is identified by its
**case ID**:

`<scenario_id>.<revision_label>.<variant_id>.s<seed>`, for example
`s2-default.orig.base.s2195683955`

- `revision_label` is exactly `orig` or `m6`, with no hash.
- The content hash is a separate manifest field.

**Paths** (all under the ignored `runs/`, root `.gitignore:25`), with `B = runs/p2/<batch_id>`:
- run directory: `B/cases/<case_id>/`;
- manifest: `B/manifests/<case_id>.json`, one file per case;
- variant files: `B/variants/<variant_id>.json`;
- summaries: `B/summary/`.

Nothing is written inside a run directory except by the CLI. `batch_id` is chosen by the
operator, matches `[a-z0-9-]+`, and is unique per batch.

**Registered variants** (immutable; a variant ID always means the same `RuleParams`):

| `variant_id` | `RuleParams` | CLI flags (CR-004) |
|---|---|---|
| `base` | `{"0.1", enabled, enabled, 2, 36}` | none |
| `canteen-restricted` | `{"0.1", restricted, enabled, 2, 36}` | `--rule-canteen restricted` |
| `cue-ignored` | `{"0.1", enabled, ignored, 2, 36}` | `--rule-cue ignored` |
| `p1-random`, `p1-scripted` | none (P1 policies; `rule_params` absent) | `--policy random`; `--policy scripted --script <path>` |

- **New numeric variants:** a variant with nondefault numeric parameters gets a new ID
  `<name>-v<n>`, recorded in the P2-04 report before use.
- **Variant files:** its file `B/variants/<id>.json` holds the canonical `RuleParams` and is
  passed with `--rule-params`.
- **Refusal:** the tool refuses a case whose effective `rule_params`, read from the tick-zero
  checkpoint, differ from the registry entry for its `variant_id`.

```text
P2CaseManifest {
  manifest_version:"0.1", case_id, batch_id,
  scenario_id, revision_label, scenario_file,        // repo-relative path of the world TOML
  content_revision_sha256,  // config hash of scenario_file as committed (its own meta.seed)
  seed, cli_args:array<string>,                      // exact argument vector after "-m living_island"
  policy_id,                // tick-0 agent_state.runtime_states[*].policy_config.policy_id
  policy_variant_id, rule_params:RuleParams|null, script_sha256:string|null,
  policy_config_sha256,     // SHA-256 of canonical tick-0 PolicyConfig (identical across residents)
  config_sha256, map_sha256,                       // effective identity, from world_initialized
  run_id, run_dir:"cases/<case_id>",               // relative to B
  events_sha256, decisions_sha256, final_world_sha256, // from decision-trace.json
  code_commit               // `git rev-parse HEAD` of the code that ran
}
```

`cli_args` is exactly:

`run --config <scenario_file> --ticks 1008 --seed <seed> --policy <rule-based|random|scripted> <variant flags> --out <B>/cases/<case_id> --export-replay`

- The variant flags are those in the table; `--rule-params B/variants/<id>.json` is used for
  numeric variants.
- Re-running `cli_args` at `code_commit` must reproduce the same hashes and metric values
  (B08).
- P1 fixtures (P2-03 validation on P1 policies): `policy_variant_id` is `p1-random` or
  `p1-scripted` with `rule_params = null`, and `script_sha256` comes from the tick-zero
  policy config.

## 7. Analysis module

- **Location:** `backend/src/living_island/analysis/`. It is pure and does no file IO. Its
  inputs are parsed `WorldEvent`, `DecisionRecord`, `ReplayBundle`, `SavePackage` (tick 0 and
  final) and `DecisionTraceManifest` objects, plus the config values it needs. Its outputs are
  metric records.
- **Loader:** `scripts/p2_experiments.py` reads the case directories through the read-only
  persistence API: `load_trace`, `read_checkpoint`, and replay decoding as `ReplayBundle`. It
  writes only under `B/manifests`, `B/variants` and `B/summary`.
- **Dependency contract**, added by P2-03 to `backend/pyproject.toml`; no existing contract
  changes:

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

  - The module may import `living_island.events`, `living_island.contract` and
    `living_island.agents.types` directly. Their own imports of `world.facts` and
    `world.protocol` are indirect and allowed by design.
  - The option exists in the installed import-linter 2.16 (`backend/uv.lock:239-240`).
- **CI:** the long matrix runs only through a separate command outside default CI (OQ-053).

## 8. Worked example (test oracle for P2-03)

A toy run: `run_id="toy"`, `T = 8`, map `6×3`, spring at `(5,1)` (index 11), tree `t1` at
`(2,2)`, residents `a`, `b` and `c`, `needs.hydration_gain_per_serving = 6000`, `min = 0`.
Frame values not listed are nonzero, and residents are alive unless stated. `t1` has stock
1 in `F[0..4]` and 0 in `F[5..8]`; `b` is at `(0,0)` throughout.

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

Events used (IDs `toy:<tick, 10 digits>:<seq, 6 digits>`):
- Tick 0: `exploration_updated` for `a` without 11, for `b` with 11, for `c` without 11.
- Tick 2: `exploration_updated` for `a` with 11; `action_succeeded` `a` `move_to`.
- Tick 3:
  - `water_drank` actor `a`, spring, 2000 → 8000;
  - `action_succeeded` `a` drink;
  - `resident_died` `b` `DEPRIVATION`.
- Tick 5:
  - `fruit_gathered` actor `a`, `t1`, 1 → 0 (`toy:0000000005:000000`);
  - `action_succeeded` `a` gather;
  - `action_failed` `c` `RESOURCE_TAKEN`, intent `c:p000001:i0` (`toy:0000000005:000002`).
- Tick 7: `water_drank` `a`, spring, 7000 → 10000; `action_succeeded` `a` drink.

Decisions: `c` ordinal 1 at tick 3, `[gather t1]`; `c` ordinal 2 at tick 5,
`[ACTION_FAILED]`, `[move_to (0,2)]`.

| Metric | a | b | c |
|---|---|---|---|
| first_spring_discovery_tick | 2 | 0 | null |
| first_drink_tick / first_spring_drink_tick | 3 / 3 | null / null | null / null |
| alive_at_T / death_tick | true / null | false / 3 | true / null |
| ticks_alive / exposure_ticks | 8 / 8 | 2 / 3 | 8 / 8 |
| ticks_deprived (water) | 0 | 2 (k=2, 3) | 0 |
| water_only_visits / dedicated_water_trips | 2 / 1 | 0 / 0 | 0 / 0 |
| gathers_completed | 1 | 0 | 0 |
| hydration_cap_waste | 3000 | 0 | 0 |
| water_access | drank | found_not_drunk (died) | not_found |

`a`'s visits:
- They are `F[2..3]` and `F[6..8]`. The tick-2 `move_to` completion is travel.
- Visit 1 has the drink at tick 3; its leg is tick 1, with no gather → **dedicated**.
- Visit 2 has the drink at tick 7; its leg is ticks 4–5, with the gather at 5 → water-only,
  **not dedicated**.

Per run:
- C1 = 1 (`toy:0000000005:000002` matched to `toy:0000000005:000000`);
- A1 = 1 (`toy:0000000005:000002` → `(c,2)`);
- A2 = 0 (`(c,2)` also meets A2 but is already A1);
- `b`'s death category: `found_not_drunk`.

### 8.1 Counterexample vectors (from Gate 2; each is a small standalone toy)

Same conventions as above; each vector lists only what differs.

| ID | Input | Expected |
|---|---|---|
| EV-01 arrival move only (G2-06) | `a` spring-adjacent in `F[2..3]`; the only completion in 2..3 is `move_to` at tick 2. | `water_only_visits = 0`, `dedicated_water_trips = 0` (no drink or fill). |
| EV-02 survivor found, never drank (G2-07) | `a` discovery 4; no `water_drank`; alive at T. | `water_access = found_not_drunk` (alive); excluded from the discovery-to-drink summary; counted in the alive split. |
| EV-03 canteen drink before discovery (G2-07) | `a` canteen drink at tick 2; discovery 5; no spring drink; dies at 7. | `first_drink_tick = 2`, `first_spring_drink_tick = null`, `water_access = found_not_drunk`; death category `found_not_drunk`. |
| EV-04 late dehydration after a drink (G2-07) | `a` spring drink at 3; `R` = ticks 50–60 with `hydration = 0`; dies at 60. | `post_access_dehydration`, never supply shortfall. |
| EV-05 food deaths (G2-07) | `R` ticks 300–310 with `satiety = 0` and `hydration > 0`; the tree-stock total is 0 at every frame of `R` → case A; total is 1 at `F[305]` → case B. | Case A: `food_supply_shortfall`. Case B: `food_access_shortfall`. |
| EV-06 repeated attempt (G2-08) | `c` gather `t1` fails `RESOURCE_TAKEN` at 5; record `(c,2)` at tick 5 is `[gather t1]` again; `(c,3)` at 7 is `[move_to (0,2)]`. | A1 = 0, repeat = 1 for that failure; `(c,3)` is not examined for it. |
| EV-07 null-target failure (G2-08) | `a` spring `drink` fails `OUT_OF_REACH`. | Not an A1 candidate; A1 = 0. |
| EV-08 two successes, one failure (G2-08) | Tick 5: `fruit_gathered` `t1` by `a` (seq 0) and by `d` (seq 3); `action_failed` `c` `RESOURCE_TAKEN` on `t1` (seq 5). | C1 = 1, matched to seq 0. |
| EV-09 give into a full inventory (G2-06) | `a` `give` fruit to `b` fails `INVENTORY_FULL` (`target_id = b`). | `slot_full_incidents`: `b` 1, `a` 0. |
| EV-10 canteen removed (G2-05) | In a valid 3-tick run, delete `ground_canteen` and the holder's servings from `F[1]` (schema-valid). | Technical check 6 fails (canteen uniqueness) → run invalid, although `ReplayBundle` validation and `load_trace` pass. |
| EV-11 transfer then drink (G2-06) | `tick_minutes = 10` (W = 144). Canteen given `a → b` at 10; `b` canteen drink at 154. Variant A: `b` gives it to `c` at 100, then `c` drinks at 120. | Base: counted (154 ≤ 10+144). Variant A: not counted for `G(a→b)`, because an intervening give from `b` exists; `G(b→c)` is counted (120 ≤ 244). |
| EV-12 replay mismatch (G2-05) | Change one byte of an event payload inside `replay.json` (schema-valid). | Check 5 fails (event bytes differ from `events.jsonl`) → invalid. |
| EV-13 frontier signature (G2-08) | `a` record at tick 3 `[move_to (4,1)]`. Index of (4,1) = 10 is absent from `a`'s `exploration_updated` indices with tick ≤ 3, and present at tick 4. | (4,1) is in `a`'s `early_frontiers`. A record at tick 4 targeting (4,1) would not be a frontier entry. |
