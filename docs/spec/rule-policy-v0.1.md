# Living Island — Rule Policy Spec v0.1 (`rule-based-v0`)

> **Draft for M5 (P2-00).** Status: proposed. It takes effect only after the owner approves
> it at M5 together with CR-004 (`open-questions.md`) and ADR 0004. Until then the P1 specs
> stay unchanged and no code may depend on this file.

**Scope:** the deterministic, rule-based resident policy for P2. It runs on the existing
Agent Interface (`agent-interface-v0.1.md` §2): one `decide(request)` per decision, returning
an `ActionPlan`. It is the P3 control group and LLM fallback (AI §0.1 AG-04). It changes no
world rule, `Perception` field, trigger code, action, failure code or event.

**Code references** are `path:line` on commit `04fde8b`, relative to
`backend/src/living_island/` unless stated. Spec references use the usual abbreviations:
WR (`world-rules-v0.1.md`), IC (`interface-contract-v0.1.md`), AI (`agent-interface-v0.1.md`),
BN (`balance-notes-v0.1.md`), plan (`docs/plans/p2-implementation-plan-v0.1.md`).

## 0. Facts this spec relies on

| # | Fact on 04fde8b | Source |
|---|---|---|
| F1 | The policy receives only the `DecisionRequest`; its context holds the latest ingested `Perception` and the own profile/goal. Earlier packets are not kept. | `agents/runtime.py:102`, `agents/runtime.py:113-130`, `agents/runtime.py:137` |
| F2 | A decision is requested only at tick zero or when the actor is idle with a nonempty deferred trigger set; a new decision discards the unstarted queue. With no trigger the next queued intent starts without a decision. | `sim/boundary.py:167-190` (`:172`, `:173`) |
| F3 | Every packet's triggers are deferred; a success that empties the queue adds `PLAN_FINISHED`; a failed or interrupted result discards the queue. | `sim/boundary.py:153-160`, `sim/boundary.py:198-201` |
| F4 | `NEW_SIGHT` interrupts only `move_to`; `URGENT_NEED` interrupts `move_to`, `gather`, `rest`, `sleep`; `DIRECT_SPEECH` interrupts `move_to`, `gather`, `rest`. | `world/interrupts.py:42-47` |
| F5 | `NEW_SIGHT` is the first exposure of an entity ID, a newly held canteen, or the first distant-to-near cue upgrade; none at tick zero. | `world/observation.py:346-359`, WR §5.1 step 6 |
| F6 | `explored_static_tiles` is the full world-owned footprint at every boundary. | `world/observation.py:375`, plan §1.2 |
| F7 | A cue's `direction` is the configured string, delivered only at `near` detail; `distant` has `direction=null`. The cue is also a `cue` entity. | `world/perception.py:187-201`, `world/content.py:194-201` |
| F8 | Reach: `gather`, spring `drink`, `fill_canteen` and `give` require Manhattan distance **exactly 1**; `pick_up` allows distance 0 or 1. A tree with stock 0 fails `RESOURCE_TAKEN` at start. | `world/actions.py:68`, `:72`, `:84`, `:97`, `:106`, `:119` |
| F9 | Talk is heard by awake residents within `hearing_radius_tiles`, never by the speaker. | `world/engine.py:626-644`, `world/dialogue.py:36-38` |
| F10 | The canteen's capacity is not in `Perception`; only `canteen_id` and `canteen_servings` of a held canteen are. | `world/protocol.py:457-466`, IC §2.2 |
| F11 | `random-v0` hash construction: `uint64_be(SHA-256("<seed>|<actor_id>|<ordinal>|<stage>")[0:8])`. | `agents/policies/random_policy.py:148-150`, AI §4.1 |
| F12 | Known passable terrain: `beach`, `grass`, `woods`, `cave`, `fruit_tree`, `damp_moss`. | AI §4.1, `agents/policies/random_policy.py:20` |
| F13 | `policy_state` is saved per resident in `ResidentRuntimeState`; today only `{}` or scripted `{cursor}` validate. | `agents/types.py:285-302` |

## 1. Inputs (PD-06, plan §1.2)

**Allowed, and nothing else:**
1. `request.context` (`DecisionContext`): `perception`, `personality_profile`,
   `current_goals`. The empty memory fields are ignored.
2. `request.actor_id`, `request.tick`, `request.decision_ordinal`, `request.triggers`.
3. The frozen `PolicyConfig`: `seed`, `max_plan_actions`, `map_width`, `map_height`, and
   `rule_params` (CR-004, §8).
4. The policy's own `policy_state` (§7).

**Forbidden:** content files, the `.map` file, `world.spring`/`world.initial_cave`/cue
coordinates from config, any `WorldState` field, other residents' state or policy state, the
event log, decision logs, checkpoints, replay frames, wall-clock time, environment variables,
global or world RNG (`resolution_rng`), and any constant tuned to the default island (a
coordinate, a direction to walk, a tree ID, a route length). Content values such as
`hearing_radius_tiles`, `canteen.capacity_servings`, step costs, durations, decay rates and
the clock are also forbidden; the policy learns about them only through `Perception`.

The cue is used only through the `EnvironmentalCue` fields `position`, `detail_level` and
`direction` (plan §1.2). Terrain names are a frozen vocabulary (IC §2.5), not map knowledge.
The policy holds **no private map memory**: static map knowledge comes from
`explored_static_tiles` (F6); live stock bands only from the current packet's
`visible_entities` and `transient_sightings`.

## 2. Definitions

All computations use integers and canonical orders (IC §6.2). `P` is the request's perception.

- **Band order:** `critical < low < moderate < good < strong` (IC §2.5). "At most `b`" means
  the band is `b` or lower.
- **Explored set `E`:** positions in `P.explored_static_tiles`. **Passable `K`:** members of
  `E` whose terrain is in F12.
- **BFS distance `d(t)`:** unit-cost breadth-first search over `K` from `P.own_position`, four
  neighbors in `N, E, S, W` order. Unreachable tiles have no distance. `P.own_position` is in
  `K` (the observer's tile is always in its footprint).
- **Frontier:** a position inside `[0,map_width) x [0,map_height)`, not in `E`, with at least
  one 4-neighbor in `K`. Its distance is `1 + min d(n)` over its reachable neighbors `n` in `K`.
- **Spring known:** some tile in `E` has terrain `spring`. **Spring stand:** a tile in `K` at
  Manhattan distance exactly 1 from a known spring tile (F8).
- **At the spring:** some tile in `P.visible_tiles` with terrain `spring` is at Manhattan
  distance exactly 1 from `P.own_position`.
- **Known tree tile:** a tile in `E` with terrain `fruit_tree`. **Tree stand:** a tile in `K`
  at Manhattan distance exactly 1 from it (F8; the tree tile itself is distance 0).
- **Current trees:** `fruit_tree` entries of `P.visible_entities` and `P.transient_sightings`.
- **Neighbor resident:** a `resident` entry of `P.visible_entities` at Manhattan distance
  exactly 1 (F8: `give` needs exactly 1).
- **Holder:** `P.own_inventory.canteen_id` is not null.
- **Target key:** `{kind:"tile",position:Coord}` or `{kind:"resident",id:string}`. Canonical
  order: tile keys first by `(y,x)`, then resident keys by ID. Trees and the ground canteen are
  keyed by their tile.
- **Failed:** a target key with an unexpired entry in `failed_targets` (§7).

### 2.1 Seeded tie-break

Only for candidates whose score is exactly equal (§4). With candidates in canonical order
`c[0..n-1]`, pick `c[h(domain) mod n]`, where

`h(domain) = uint64_be(SHA-256(UTF8("<seed>|<actor_id>|<decision_ordinal>|<domain>"))[0:8])`

as in `random-v0` (F11): decimal text without padding, `seed` from `PolicyConfig`. Domains are
the literal strings `rule-v0:water`, `rule-v0:tree`, `rule-v0:canteen` and `rule-v0:explore`;
they cannot collide with random-v0 stages `0`/`1`. With `n == 1` no hash is computed. Modulo
bias is accepted. Variation never overrides a higher-priority rule: the hash only chooses
among equal targets of the rule that already fired.

## 3. Decision procedure

`decide` runs step R0, then the rules R1–R12 in order; **the first rule that applies returns
the plan**. Exactly one rule applies because R12 always applies. The policy never checks
hidden legality (inventory room of others, path cost, stamina value); world failures are
handled by §5.

**R0 — update working state** (on a copy; committed only with the decision, §7.3):
1. Drop `failed_targets` entries with `retry_after_tick <= request.tick`.
2. Apply `P.last_action_feedback` per §5.
3. For each `P.heard_utterances` entry with `speech_act="refuse"` and
   `addressee_id == actor_id`: upsert `{resident speaker_id}` with code `REFUSED`.
4. For each current tree: band `empty` → upsert its tile with code `OBSERVED_EMPTY`; band
   `few`/`many` → delete that tile's entry if its code is `OBSERVED_EMPTY` or `RESOURCE_TAKEN`.
5. Merge `P.environmental_cues` into `cue_impressions` (§7.1).
6. If holder: `canteen_full_seen = max(canteen_full_seen or 0, canteen_servings)`.
7. Drop the commitment if §4.1 invalidates it.

**Rules** (H = hydration band, S = satiety band, T = stamina band of `P.own_condition`;
"canteen enabled" means `rule_params.canteen_use == "enabled"`):

| Rule | Applies when | Plan |
|---|---|---|
| R1 Reply | `P.heard_utterances` holds a `request` addressed to this actor (take the first in array order) | §6.2 accept or refuse |
| R2 Canteen drink | H at most `low`; holder; `canteen_servings > 0`; canteen enabled; not at the spring | `[drink {source:canteen}]` |
| R3 Spring drink | at the spring; H at most `moderate` | `[drink {source:spring}]` |
| R4 Fill | at the spring; holder; canteen enabled; `canteen_servings < canteen_full_seen` | `[fill_canteen entity(canteen_id)]` |
| R5 Eat | `fruit_count > 0`; S at most `moderate` | `[eat]` |
| R6 Seek water | H at most `low` | (a) an eligible spring stand exists → `[move_to stand]` (§4, domain `water`); (b) else if H is `critical`, canteen enabled, not holder, and an unfailed neighbor resident exists → `[talk request canteen×1]` to the lowest such ID (§6.1); (c) else → explore (§4.3) |
| R7 Sleep | T at most `low` | `[sleep]` |
| R8 Gather | `fruit_count < rule_params.fruit_carry_target` | (a) an unfailed current tree at distance exactly 1 with band `few`/`many` → gather it (lowest entity ID): `k = 1` if `few`, else `min(fruit_carry_target - fruit_count, max_plan_actions)`, plan `[gather]×k`; (b) else an eligible tree stand of an unfailed known tree tile → `[move_to stand]` (domain `tree`); (c) else fall through |
| R9 Pick up canteen | canteen enabled; not holder; a `canteen` entry in `P.visible_entities` whose tile is unfailed | distance ≤ 1 → `[pick_up tile {item_type:canteen,quantity:1}]`; else if its tile is in `K` with a BFS distance → `[move_to tile]` (domain `canteen`); else fall through |
| R10 Deliver canteen | canteen enabled; holder; `canteen_servings > 0`; H at least `good`; an unfailed neighbor resident shows the `dehydrated` sign | `[give resident {item_type:canteen,quantity:1}]` to the lowest such ID |
| R11 Explore | an eligible frontier exists (§4.3) | `[move_to frontier]` |
| R12 Idle | always | T at most `good` → `[rest]`; else `[wait]` |

All targets, parameters and reasons follow IC §2.4; every `reason` is `null`; `talk.text` is
the empty string. Plans are built with the shared ID builders (`agents/types.py:45-56`) and
have `1..max_plan_actions` intents. If `max_plan_actions` is smaller than a plan above,
truncate it to its first `max_plan_actions` intents, except R1 accept, which then becomes
refuse (§6.2).

Rule order follows plan §1.1 and §2 P2-00: drink (R2, R3, R6), eat (R5), rest/sleep (R7,
R12), gather (R8), explore (R11). R1 comes first because a heard request is delivered once
and is lost if not answered at this decision (F1); R4, R9 and R10 are canteen duties placed
next to the rule they serve.

## 4. Targets, scores and commitment

**Eligible** targets of each domain are those that are not failed, are not at
`P.own_position`, and have a BFS distance (stands, canteen tile) or a frontier distance.
**Score** = that distance; lower is better. The candidates with the minimum score are equal,
and §2.1 chooses among them in `(y,x)` order. No other tie-break exists.

### 4.1 Commitment

`commitment = {goal:"water"|"tree"|"canteen"|"explore", target:Coord, set_at_tick:integer}`
or `null`. When R6a, R8b, R9 (move) or R11 fires and the commitment has that goal and its
target is still eligible for that goal, the policy **reuses the committed target** without
re-scoring. Otherwise it scores, chooses, and replaces the commitment. This stops
oscillation when `NEW_SIGHT` interrupts a walk (F4) and a nearly equal target appears.

R0 step 7 drops the commitment when `P.own_position == target`, when the target is failed, or
when the target is no longer eligible for its goal (for explore: the tile entered `E`).
Rules that do not move leave the commitment unchanged. There is no time-based expiry.

### 4.2 Trees

R8b's candidates are stands of known tree tiles that are not failed. A remote tree is
targeted by terrain only; its entity ID and band are read when the resident stands next to
it (it is then visible) and R8a fires at the next decision. R0 step 4 provides the only
stock evidence, from the current packet (plan §1.2: no historical tree-stock tracking).

### 4.3 Exploration and the cue

Candidates are eligible frontier tiles. **Cue preference** applies when
`rule_params.cue_use == "enabled"`, the spring is not known, and `cue_impressions` holds an
impression with `detail_level="near"` and a recognized `direction` (§7.1; with several, the
lowest `cue_id`). Let `(cx,cy)` be its position. The preferred half-plane is `x > cx` for
`east`, `x < cx` for `west`, `y < cy` for `north`, `y > cy` for `south`. If any eligible
frontier lies in it, candidates are restricted to those; otherwise all eligible frontiers
remain. With `cue_use == "ignored"` the half-plane is never applied (§6.3). The domain is
`explore` for R11 and `water` for R6c.

## 5. Failure handling and back-off

`ActionFeedback` has `intent_id` and `failure_code` but no target (IC §2.4). The policy keeps
**issued-intent references** for its last committed plan (§7). In R0 step 2, if
`last_action_feedback` is a `failure` whose `intent_id` matches a reference, apply the table
below to that reference's target. Back-off sets
`retry_after_tick = request.tick + rule_params.failed_target_retry_ticks`.

| Action | Failure code | Effect |
|---|---|---|
| `move_to` | `NO_PATH`, `PATH_BLOCKED`, `INVALID_TARGET` | back off the target tile |
| `gather` | `RESOURCE_TAKEN`, `OUT_OF_REACH`, `INVALID_TARGET` | back off the tree's tile |
| `gather` | `INVENTORY_FULL` | none (own inventory); R8 does not fire while `fruit_count >= fruit_carry_target` |
| `pick_up` | `ITEM_TAKEN`, `OUT_OF_REACH`, `INVENTORY_FULL`, `INVALID_TARGET` | back off the tile |
| `give`, `talk` | any code except `DEAD`, `EXHAUSTED` | back off the resident |
| `fill_canteen` | `ALREADY_FULL` | set `canteen_full_seen = canteen_servings` (no target) |
| any | `EXHAUSTED`, `DEAD`, `NO_NEED`, `NO_WATER`, `NO_ITEM`, `OUT_OF_REACH` on drink or fill | none; the next decision sees current bands |

Why each case holds:
- **Empty tree:** a visible empty tree is backed off without an attempt (R0 step 4). An
  attempt on a stock-0 tree fails `RESOURCE_TAKEN` at start (F8), which is the same back-off.
- **Interruption** (`status="interrupted"`): no back-off; the commitment survives (§4.1).
- **Unmatched feedback:** null feedback, a `success`, or an `intent_id` with no matching
  reference (for example after a wait substitute, §7.3) changes nothing. It is not an error.
- **Nothing eligible:** the domain falls through to the next rule; R12 always plans.
- **Why a matched reference is always present:** a failure or interruption always yields a
  decision at that same boundary (F2, F3), so its feedback is in the decided packet, and it
  belongs to the last committed plan, whose references are retained.

Back-off codes come from IC §4. The policy-local codes are `OBSERVED_EMPTY` (R0 step 4),
`REFUSED` (R0 step 3) and `REQUESTED`, added for the addressee when a `talk request` plan is
committed. `REQUESTED` stops a repeated request before the retry tick, answered or not.
Upsert replaces an existing entry for the same target.

## 6. Canteen (PD-03, PD-07)

### 6.1 Use
- **Drink:** R2 drinks from the canteen at H `critical`/`low` away from the spring. At hydration
  below 4000 (`low` upper cutoff in the default config) a serving is not capped. The policy
  does not use that number; it only uses bands.
- **Fill:** R4 at the spring when `canteen_servings < canteen_full_seen`. Capacity is not
  perceivable (F10), so `canteen_full_seen` is the largest count this resident has held (R0
  step 6), corrected by `ALREADY_FULL` (§5).
- **Request:** a nonholder at H `critical`, with no eligible spring stand, asks one neighbor
  resident for the canteen (R6b). The policy cannot know who holds it (IC §2.2 hides others'
  inventories), so a nonholder may be asked and will refuse. `REQUESTED` and `REFUSED` back
  off that resident.
- **Proactive give:** R10. A holder with H at least `good` gives the canteen to a neighbor
  showing `dehydrated`. This is physical water delivery (BN §0); it moves the slot.
- **After the holder dies** the canteen lies on the corpse tile (WR §6). Any nonholder that
  sees it picks it up (R9) and then follows the holder rules.

### 6.2 Replies (R1)
For the first addressed `request` utterance `u`, with `X = u.speaker_id`:
- **Canteen request:** accept iff canteen enabled, holder, `X` is a neighbor resident (distance
  exactly 1), H at least `moderate`, and `max_plan_actions >= 2`. Plan:
  `[talk accept(in_reply_to=u.utterance_id) to X, give canteen×1 to X]`. Otherwise
  `[talk refuse(in_reply_to=u.utterance_id) to X]`.
- **Fruit request for `q`:** accept iff `fruit_count - q >= 1`, S at least `moderate`, `X` is a
  neighbor resident, and `max_plan_actions >= 2`. Plan: `[talk accept, give fruit×q]`.
  Otherwise refuse.
- A requester on the same tile (distance 0) is refused, because `give` needs distance exactly
  1 (F8).
- Other heard requests at this boundary are not answered; the world keeps no memory for them.

### 6.3 Experimental switches (S4, S5)
- `canteen_use="restricted"` (S4): R2, R4, R6b, R9 and R10 never fire, and a canteen request
  is always refused in R1. Fruit replies are unaffected. The canteen entity and its initial
  slot remain (plan §1.3).
- `cue_use="ignored"` (S5): §4.3's half-plane is never applied. Impressions are still
  recorded (R0 step 5), so the state shape is the same in both arms. Perception, the cue and
  triggers are unchanged; only this one policy choice differs.

No other rule reads either switch.

## 7. `policy_state` (schema `"0.1"`)

```text
RuleStateV0_1 {
  rule_state_version: "0.1",
  commitment: {goal:"water"|"tree"|"canteen"|"explore", target:Coord, set_at_tick:integer}|null,
  issued_intents: array<{intent_id:string, action_type:ActionType, target:TargetKey|null}>,
  failed_targets: array<{target:TargetKey, code:string, retry_after_tick:integer}>,
  cue_impressions: array<{cue_id:string, position:Coord, detail_level:"distant"|"near",
                          direction:string|null}>,
  canteen_full_seen: integer|null
}
```

All fields are required, and unknown fields are refused. `canteen_full_seen` is the one field
beyond plan §1.2's list (OQ-062). The initial state is `commitment=null`, empty arrays and
`canteen_full_seen=null`.

### 7.1 Field rules
- **`issued_intents`:** the intents of the last committed `ok` plan, in plan order, with
  each target key (`move_to`/`pick_up`: the tile; `gather`: the tree's tile; `give`/`talk`:
  the resident; others: `null`). There are at most `max_plan_actions` entries, all from one
  plan ID with contiguous indices from 0. The list is retained through queued actions, save
  and restore, and replaced by the next committed `ok` plan. Older plans cannot receive
  feedback (§5).
- **`failed_targets`:** sorted by canonical target order, unique, and at most 64 entries.
  `code` is an IC §4 failure code or `OBSERVED_EMPTY`/`REFUSED`/`REQUESTED`. Expiry is R0
  step 1. When an upsert would exceed 64, the policy first evicts the entry with the smallest
  `retry_after_tick`, ties by canonical target order. 64 bounds the state; it is not a tuning
  value. The default island has 6 trees, so the cap binds only on large frontier back-offs.
- **`cue_impressions`:** sorted by `cue_id`, unique, and at most 16 entries (v0.1 content has
  exactly one cue, OQ-004). Merge per perceived cue: keep the highest detail (`near` beats
  `distant`); when a `near` entry carries a non-null direction, store it; never clear a stored
  direction. A cue beyond 16 is ignored, deterministically in `cue_id` order. **Recognized
  directions** are exactly `north`, `east`, `south` and `west`; any other string is stored
  but treated as no direction (OQ-055).
- **`canteen_full_seen`:** null or a nonnegative integer.

### 7.2 Serialization and restore validation
`export_state()` returns the object above. It is serialized with IC §6.3 canonical encoding,
array orders as in §7.1, and no omitted fields. On restore, the CR-004 validator for
`rule-based-v0` refuses (no repair, no migration):
- an unknown `rule_state_version`, an unknown or missing field, or a wrong type;
- unsorted or duplicate arrays, or more than 64 failed targets or 16 impressions;
- coordinates outside `[0,map_width) x [0,map_height)`;
- `issued_intents` longer than `max_plan_actions`, not from one plan ID of this actor with
  ordinal `< next_decision_ordinal`, or with non-contiguous indices; it must be empty when
  `next_decision_ordinal == 0`;
- `retry_after_tick < 1` or
  `> latest_perception_tick + rule_params.failed_target_retry_ticks`, or
  `commitment.set_at_tick > latest_perception_tick`;
- a non-null `direction` with `detail_level="distant"`; a negative `canteen_full_seen`.

### 7.3 Transaction
`decide` computes the plan and the next state from the request, the committed state and
`PolicyConfig` only. The runtime keeps the next state pending. `commit_decision` installs it
for an `ok` outcome, like the scripted cursor (`agents/runtime.py:191-193`, AI §2.1). On an
`error` outcome (a defect; sim queues the wait substitute) the committed state stays
unchanged, so feedback for the substitute's intent ID is unmatched (§5). `export_state`
returns only committed state and refuses a pending decision (`agents/runtime.py:197-199`).

### 7.4 Cue capture at decision boundaries only (no ingest hook)
Impressions are updated only from the perception presented at `decide` (F1). This captures
every direction (OQ-056):
- A `near` upgrade with a direction is a `NEW_SIGHT` (F5).
- It needs movement: within `cue_detail_radius_tiles` the tile is in sight, unless the
  night radius is smaller than the detail radius. Movement happens only in `move_to`, which
  `NEW_SIGHT` interrupts (F4), or which completes in the same tick.
- The resident is therefore idle at that boundary with a nonempty trigger set, and decides
  on that same packet (F2, F3). At tick zero the first decision uses the initial packet.
- Distant-only exposures carry no direction, and the `damp_moss` tile is already kept by the
  footprint (F6).

So the CR-004 ingest hook is not needed, and recorded re-execution is unaffected. If a
config sets `night_radius_tiles < cue_detail_radius_tiles`, a dawn upgrade during rest or
sleep could be missed. P2-02 adds a test that every `near` direction in a run's packets
appears in that resident's committed state (OQ-056).

## 8. Rule parameters (CR-004)

```text
RuleParams {
  rule_params_version: "0.1",
  canteen_use: "enabled"|"restricted",
  cue_use: "enabled"|"ignored",
  fruit_carry_target: integer,          // >= 1; default 2
  failed_target_retry_ticks: integer    // >= 1; default 36
}
```

- `fruit_carry_target = 2`: steady-state demand is 1.8 fruit per resident per day (BN §1),
  rounded up to whole fruit.
- `failed_target_retry_ticks = 36`: no spec value exists (OQ-054). The assumption is reversible
  and a policy parameter, so a change is a new policy variant, identified by its hash
  (`p2-experiments-v0.1.md` §6).
- The default variant `base` is `{canteen_use:"enabled", cue_use:"enabled"}` with these
  defaults.

## 9. Determinism (acceptance for P2-02)

The same `DecisionRequest`, committed `policy_state` and `PolicyConfig` give the same
`ActionPlan` and the same next state, byte for byte in canonical encoding. The policy uses
only §2.1 hashing for choice. It does not iterate unordered sets or dicts; it uses no floats,
clock, randomness, IO or global state. It never reads `resolution_rng` (WR §5.6). All loops
are bounded by the map size, so `decide` terminates (AI §2.4). Same-input property tests,
the leak test (plan P2-02) and resume with populated state check this.
