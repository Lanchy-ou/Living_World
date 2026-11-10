# Living Island — Rule Policy Spec v0.1 (`rule-based-v0`)

> **Draft for M5 (P2-00, rework 1).** Status: proposed. It takes effect only after the owner
> approves it at M5 together with CR-004 (`open-questions.md`) and ADR 0004. Until then the
> P1 specs stay unchanged and no code may depend on this file.

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
| F1 | The policy receives only the `DecisionRequest`; its context holds the latest ingested `Perception` and the own profile/goal. Earlier packets are not kept. | `agents/runtime.py:102`, `:113-130`, `:137` |
| F2 | A decision is requested only at tick zero or when the actor is idle with a nonempty deferred trigger set; a new decision discards the unstarted queue. With no trigger the next queued intent starts without a decision. | `sim/boundary.py:167-190` (`:172`, `:173`) |
| F3 | Every packet's triggers are deferred; a success that empties the queue adds `PLAN_FINISHED`; a failed or interrupted result discards the queue. | `sim/boundary.py:153-160`, `:198-201` |
| F4 | `NEW_SIGHT` interrupts only `move_to`; `URGENT_NEED` interrupts `move_to`, `gather`, `rest`, `sleep`; `DIRECT_SPEECH` interrupts `move_to`, `gather`, `rest`. | `world/interrupts.py:42-47` |
| F5 | `NEW_SIGHT` is the first exposure of an entity ID, a newly held canteen, or the first distant-to-near cue upgrade; none at tick zero. | `world/observation.py:346-359`, WR §5.1 step 6 |
| F6 | `explored_static_tiles` is the full world-owned footprint at every boundary. | `world/observation.py:375`, plan §1.2 |
| F7 | A cue's `direction` is the configured string, delivered only at `near` detail; `distant` has `direction=null`. The cue is also a `cue` entity. Valid content has exactly one cue. | `world/perception.py:187-201`, `world/content.py:194-201`, `:377-378` |
| F8 | Reach: `gather`, spring `drink`, `fill_canteen` and `give` require Manhattan distance **exactly 1**; `pick_up` allows distance 0 or 1. A tree with stock 0 fails `RESOURCE_TAKEN` at start. The engine's reach differs from WR §1.1 wording (OQ-063). | `world/actions.py:68`, `:72`, `:84`, `:97`, `:106`, `:119` |
| F9 | Own room = `slot_capacity − fruit_count − (1 if holder)`; gather and pick_up check the actor's room, give checks the recipient's room. `slot_capacity` may be 1. | `world/actions.py:34-39`, `:70`, `:115`, `:130`; `world/content.py:136-137` |
| F10 | Canteen capacity is not in `Perception`; valid content allows `initial_servings` from 0 to `capacity_servings`, and capacity 0. `fill_canteen` refills to capacity. | `world/protocol.py:457-466`, `world/content.py:140-150`, WR §3 |
| F11 | `random-v0` hash construction: `uint64_be(SHA-256("<seed>|<actor_id>|<ordinal>|<stage>")[0:8])`. | `agents/policies/random_policy.py:148-150`, AI §4.1 |
| F12 | Known passable terrain: `beach`, `grass`, `woods`, `cave`, `fruit_tree`, `damp_moss`. | AI §4.1, `agents/policies/random_policy.py:20` |
| F13 | `policy_state` is saved per resident in `ResidentRuntimeState`; today only `{}` or scripted `{cursor}` validate. | `agents/types.py:285-302` |
| F14 | `heard_utterances` keeps emission order; `utterance_id` is the `utterance_spoken` event ID, so ascending ID is emission order. The speaker never hears itself. | `world/engine.py:615-644`, IC §2.5 |

## 1. Inputs (PD-06, plan §1.2)

**Allowed, and nothing else:**
1. `request.context`: `perception`, `personality_profile`, `current_goals`. Rules R0–R12
   read only `perception`. Profile and goals are accepted and unused in v0.1. Memory fields
   are empty (AI §2.3).
2. The frozen `PolicyConfig`: `seed`, `max_plan_actions`, `map_width`, `map_height`,
   `rule_params` (CR-004, §8).
3. The policy's own committed `policy_state` (§7).
4. **Required envelope metadata**, used only as stated:
   - `request.actor_id` and `request.decision_ordinal`, for the shared plan/intent ID
     builders and the §2.1 hash;
   - `request.tick`, for `created_at_tick`, back-off expiry and `set_at_tick`.

   `request.triggers` is **not read**: the rules depend only on perception and state.

**Forbidden:** content files, the `.map` file, `world.spring`/`world.initial_cave`/cue
coordinates from config, any `WorldState` field, other residents' state or policy state, the
event log, decision logs, checkpoints, replay frames, wall-clock time, environment variables,
global or world RNG (`resolution_rng`), and any constant tuned to the default island (a
coordinate, a direction to walk, a tree ID, a route length). Content values such as
`hearing_radius_tiles`, `capacity_servings`, `slot_capacity`, step costs, durations, decay
rates and the clock are also forbidden. The policy learns about them only through
`Perception` and its own feedback.

The cue is used only through the `EnvironmentalCue` fields `position`, `detail_level` and
`direction`. Terrain names are a frozen vocabulary (IC §2.5), not map knowledge. The policy
holds **no private map memory**: map knowledge comes from `explored_static_tiles` (F6); live
stock bands only from the current packet.

## 2. Definitions

All computations use integers and canonical orders (IC §6.2). `P` is the request's perception.

- **Band order:** `critical < low < moderate < good < strong`. "At most `b`" means `b` or
  lower; "at least `b`" means `b` or higher.
- **Explored set `E`:** positions in `P.explored_static_tiles`. **Passable `K`:** members of
  `E` whose terrain is in F12.
- **BFS distance `d(t)`:**
  - unit-cost breadth-first search over `K` from `P.own_position`, expanding neighbors in
    `N, E, S, W` order;
  - defined only for tiles reached; `d(P.own_position) = 0`;
  - the observer's tile is always in its footprint.
- **Frontier:**
  - a position inside `[0,map_width) x [0,map_height)` that is not in `E` and has at least one
    4-neighbor in `K` **with a defined BFS distance**;
  - its distance is `1 + min d(n)` over those neighbors;
  - a position whose neighbors in `K` are all unreachable is **not** a frontier.
- **Spring tiles:** tiles in `E` with terrain `spring`. **Spring stand:** a tile of `K` at
  Manhattan distance exactly 1 from at least one spring tile (F8).
- **At the spring:** some `P.visible_tiles` entry with terrain `spring` is at Manhattan
  distance exactly 1 from `P.own_position`.
- **Known tree tiles:** tiles in `E` with terrain `fruit_tree`. **Tree stand:** a tile of `K`
  at distance exactly 1 from at least one known tree tile (the tree tile itself is distance
  0, F8).
- **Current trees:** the `fruit_tree` entries of `P.visible_entities` and
  `P.transient_sightings`.
- **Neighbor resident:** a `resident` entry of `P.visible_entities` at Manhattan distance
  exactly 1.
- **Holder:** `P.own_inventory.canteen_id` is not null.
- **Target keys and their canonical order** (first by kind, in this order):
  1. `{kind:"self"}` — own inventory;
  2. `{kind:"tile",position:Coord}`, ordered by `(y,x)` — trees, stands, frontiers and the
     ground canteen, all keyed by their tile;
  3. `{kind:"entity",id:string}`, ordered by ID — the held canteen, for fill only;
  4. `{kind:"resident",id:string}`, ordered by ID.
- **Failed:** the key has an entry in `failed_targets` (§7) after R0 step 1 expiry.

### 2.1 Selection and seeded tie-break

Every choice among targets uses the same procedure:
1. Build the **candidate set**: distinct target keys, deduplicated by key, keeping only those
   that pass the rule's eligibility filter.
2. Compute each candidate's integer **score**; lower is better.
3. Keep the candidates with the minimum score, in canonical key order: `c[0..n-1]`.
4. If `n == 1`, pick `c[0]`. Otherwise pick `c[h(domain) mod n]`, where
   `h(domain) = uint64_be(SHA-256(UTF8("<seed>|<actor_id>|<decision_ordinal>|<domain>"))[0:8])`.

The hash is the `random-v0` construction (F11): decimal text without padding. Domains are the
literal strings `rule-v0:water`, `rule-v0:tree`, `rule-v0:gather`, `rule-v0:canteen`,
`rule-v0:request`, `rule-v0:deliver` and `rule-v0:explore`; they cannot collide with
random-v0 stages `0`/`1`. Modulo bias is accepted. The hash never changes which rule fires,
so variation never overrides a higher priority.

## 3. Decision procedure

`decide` runs R0, then evaluates R1–R12 in order. A rule **applies** only if its condition
holds **and** it produces a plan. When its condition holds but every branch finds no
eligible candidate, evaluation **falls through** to the next rule. R12 always produces a
plan. The policy never checks hidden legality; world failures are handled by §5.

**R0 — update working state** (on a copy, committed with the decision, §7.3):
1. Delete `failed_targets` entries with `retry_after_tick <= request.tick`.
2. Apply `P.last_action_feedback` per §5 (including the fill-probe outcomes, §6.1).
3. For each `P.heard_utterances` entry with `speech_act="refuse"` and
   `addressee_id == actor_id`: upsert `{resident speaker_id}` with code `REFUSED`.
4. For each current tree:
   - band `empty`: upsert its tile with code `OBSERVED_EMPTY`;
   - band `few` or `many`: delete that tile's entry only if its code is `OBSERVED_EMPTY`.
     A failure entry (§5), for example `RESOURCE_TAKEN` written in step 2 of this same
     decision after same-tick regrowth (WR §5.4: settlement precedes regrowth), is **kept**
     until its `retry_after_tick` (DV-14).
5. Merge `P.environmental_cues` into `cue_impressions` (§7.1).
6. Apply §4.1 commitment invalidation.

**Rules.** H, S and T are the hydration, satiety and stamina bands of `P.own_condition`.
"Enabled" means `rule_params.canteen_use == "enabled"`.

| Rule | Condition | Plan, with the candidate set, score and tie domain |
|---|---|---|
| R1 Reply | `P.heard_utterances` holds a `request` with `addressee_id == actor_id` | Take the one with the lowest `utterance_id` (F14) and answer it per §6.2. Other requests at this boundary are not answered. |
| R2 Canteen drink | H at most `low`; holder; `canteen_servings > 0`; enabled; not at the spring | `[drink {source:canteen}]` |
| R3 Spring drink | at the spring; H at most `moderate` | `[drink {source:spring}]` |
| R4 Fill | at the spring; holder; enabled; the entity key of `canteen_id` is not failed; `canteen_capacity` is null **or** `canteen_servings < canteen_capacity` | `[fill_canteen entity(canteen_id)]` (§6.1) |
| R5 Eat | `fruit_count > 0`; S at most `moderate` | `[eat]` |
| R6 Seek water | H at most `low` | (a) Unfailed spring stands → `[move_to stand]`. Score `d(stand)`, domain `water`, commitment goal `water`. (b) Else, if H is `critical`, enabled, not holder: unfailed neighbor residents → `[talk request canteen×1]`. All score 0, domain `request`. (c) Else, explore per §4.3 with domain `water` and goal `explore`. (d) Else fall through. |
| R7 Sleep | T at most `low` | `[sleep]` |
| R8 Gather | `fruit_count < rule_params.fruit_carry_target`; key `self` not failed | (a) Unfailed current trees at distance exactly 1 with band `few` or `many`. Score 0 for `many`, 1 for `few`; candidate key is the tree tile; domain `gather`. Plan `[gather entity(id)]×k`, where `k = 1` for `few`, else `min(fruit_carry_target − fruit_count, max_plan_actions)`. (b) Else, unfailed tree stands that neighbor at least one unfailed known tree tile → `[move_to stand]`. Score `d`, domain `tree`, goal `tree`. (c) Else fall through. |
| R9 Pick up canteen | enabled; not holder; key `self` not failed; a `canteen` entry is in `P.visible_entities` and its tile is not failed | Distance ≤ 1 → `[pick_up tile {item_type:canteen,quantity:1}]`. Else, if the tile is in `K` with a defined `d` → `[move_to tile]`, goal `canteen`, domain `canteen` (one candidate). Else fall through. |
| R10 Deliver canteen | enabled; holder; `canteen_servings > 0`; H at least `good` | Unfailed neighbor residents with the `dehydrated` sign → `[give resident {item_type:canteen,quantity:1}]`. Score 0, domain `deliver`. None → fall through. |
| R11 Explore | always evaluated | Explore per §4.3, domain `explore`, goal `explore`. None → fall through. |
| R12 Idle | always | T at most `good` → `[rest]`; else `[wait]` |

All targets and parameters follow IC §2.4; every `reason` is `null`; `talk.text` is the empty
string. Plans use the shared ID builders (`agents/types.py:45-56`) and have
`1..max_plan_actions` intents. Only R1 accept (2 intents) and R8a (k intents) can exceed one
intent. R8a uses `k ≤ max_plan_actions` by definition. R1 accept requires
`max_plan_actions >= 2`, else it is a refuse.

The rule order follows plan §1.1 and §2: drink (R2, R3, R6), eat (R5), rest/sleep (R7, R12),
gather (R8), explore (R11). R1 comes first because a heard request is delivered once (F1).
R4, R9 and R10 are canteen duties.

## 4. Targets, scores and commitment

**Shared eligibility for movement targets:**
- the key is not failed;
- the target is not `P.own_position`;
- the target has a defined score (`d` for stands and the canteen tile, frontier distance for
  frontiers).

A stand serving several trees, or several spring tiles, is **one** candidate: candidates are
distinct tile keys (§2.1 step 1).

### 4.1 Commitment

`commitment = {goal:"water"|"tree"|"canteen"|"explore", target:Coord, set_at_tick:integer}`
or `null`. A movement branch (R6a, R6c, R8b, R9 move, R11) selects in this order:
1. Build the branch's candidate set, including the §4.3 cue filter.
2. If `commitment.goal` equals the branch's goal and `commitment.target` is **in that
   candidate set**, reuse it.
3. Otherwise run §2.1 on the set and set
   `commitment = {goal, chosen target, set_at_tick: request.tick}`.

A cue-filtered set therefore drops a committed target outside the preferred half-plane.

R0 step 6 sets the commitment to null when any of these holds:
- `P.own_position == target`;
- the target's tile key is failed;
- for goal `explore`, the target is in `E`.

Rules that do not move leave the commitment unchanged. There is no time-based expiry. R6c
and R11 share the goal `explore`.

### 4.2 Trees

- **Remote trees:** R8b targets a remote tree by terrain only. Its entity ID and band are
  read when the resident stands next to it; the tree is then visible, since an adjacent tile
  is always in sight. R8a fires at the next decision.
- **Stock evidence:** R0 step 4 is the only source, and it uses the current packet only (plan
  §1.2: no historical tree-stock tracking).
- **Failures:** a failed tree tile excludes that tree from R8a, and excludes it from the
  "unfailed known tree tile" test in R8b. A stand is excluded only if its own tile key is
  failed or it neighbors no unfailed tree.

### 4.3 Exploration and the cue

Candidates are frontier tiles that pass the shared eligibility. **Cue filter** — applies when
all of these hold:
- `rule_params.cue_use == "enabled"`;
- no spring tile is in `E`;
- `cue_impressions` holds an entry with `detail_level="near"` and a recognized direction
  (§7.1).

Let `(cx,cy)` be that cue's position. The preferred half-plane is `x > cx` for `east`,
`x < cx` for `west`, `y < cy` for `north` and `y > cy` for `south`. If at least one candidate
lies in it, the candidate set becomes those candidates; otherwise it is unchanged. Selection
then follows §4.1. With `cue_use == "ignored"` the filter never applies (§6.3).

## 5. Failure handling and back-off

`ActionFeedback` has `intent_id` and `failure_code` but no target (IC §2.4). In R0 step 2:
1. Look for an `issued_intents` reference whose `intent_id` matches a `failure` feedback.
2. If one matches, apply the table to the pair (action of the reference, failure code). The
   key to back off comes from the reference's target and the table's key column.
3. Back-off upserts the entry `{target: <key>, code, retry_after_tick: request.tick +
   rule_params.failed_target_retry_ticks}`. The serialized field is `target` (§7).

**Entry classes and precedence.** A **failure entry** has an IC §4 code written by step 2.
A **local entry** has a policy-local code: `OBSERVED_EMPTY`, `REFUSED` or `REQUESTED`.
- A failure entry replaces any entry with the same `target`.
- A local entry is written only if the `target` has no entry, or has a local entry, which it
  replaces. It never replaces a failure entry.
- A failure entry leaves the list **only** through R0 step 1 expiry. It is never deleted early
  and never evicted (§7.1).
- So the P2-02 no-repeat check holds exactly: for every failure entry, no plan targets its key
  before its `retry_after_tick`.

Every row is one action. Its codes are the WR §4.2 failure codes for that action plus
`INVALID_TARGET`; each code appears once per action. A pair not in the table has no effect.

| Action | Code → back-off key | Code → no back-off |
|---|---|---|
| `move_to` | `INVALID_TARGET`, `PATH_BLOCKED`, `NO_PATH` → target tile | `DEAD`, `EXHAUSTED` |
| `gather` | `OUT_OF_REACH`, `RESOURCE_TAKEN`, `INVALID_TARGET` → tree tile; `INVENTORY_FULL` → `self` | `DEAD`, `EXHAUSTED` |
| `pick_up` | `ITEM_TAKEN`, `OUT_OF_REACH`, `INVALID_TARGET` → target tile; `INVENTORY_FULL` → `self` | `DEAD` |
| `give` | `OUT_OF_REACH`, `INVENTORY_FULL`, `INVALID_TARGET` → resident | `DEAD`, `NO_ITEM` |
| `talk` | `INVALID_TARGET`, `OUT_OF_HEARING`, `INVALID_SPEECH_ACT`, `INVALID_REPLY`, `DIALOGUE_LIMIT` → resident | `DEAD` |
| `fill_canteen` | `NO_ITEM`, `OUT_OF_REACH`, `INVALID_TARGET` → entity `canteen_id` | `DEAD`; `ALREADY_FULL` → no back-off, but sets `canteen_capacity = P.own_inventory.canteen_servings` (§6.1) |
| `drink`, `eat` | — | every code (`DEAD`, `NO_WATER`, `OUT_OF_REACH`, `NO_ITEM`, `NO_NEED`) |
| `rest`, `sleep`, `wait` | — | `DEAD` |

**A key backs off every candidate that uses it:**
- a resident key blocks R1 accept (it refuses instead), R6b and R10 for that resident;
- a tile key blocks every movement target and R8a/R9 target on that tile;
- `self` blocks R8 and R9;
- the canteen entity key blocks R4.

Queued transfers count too: a failed `give` in an R1 accept plan backs off the recipient. A
failed `talk` discards the queued `give` (F3), and the talk failure backs off the resident.

- **`give`/`NO_ITEM`:** the giver no longer has the item. That is own state, which the next
  decision reads from `own_inventory`. It is never a recipient back-off.
- **`INVENTORY_FULL`:** gather and pick_up check own room; give checks the recipient's room
  (F9). Hence the different keys.
- **Interruption** (`status="interrupted"`): no back-off; the commitment survives.
- **Unmatched feedback:** null, a `success`, or an `intent_id` with no matching reference
  (for example after a wait substitute, §7.3) changes nothing, except the fill-probe success
  in §6.1. It is not an error.
- **Why matched references exist:** a failure or interruption always produces a decision at
  that same boundary (F2, F3), and it belongs to the last committed plan, whose references
  are retained.

**Policy-local codes** (not world codes):
- `OBSERVED_EMPTY` (R0 step 4);
- `REFUSED` (R0 step 3);
- `REQUESTED`, upserted for the addressee in the next state when an R6b plan is produced. It
  stops a repeated request before the retry tick, answered or not.

## 6. Canteen (PD-03, PD-07)

### 6.1 Use and the fill probe
- **Drink:** R2 drinks from the canteen at H `critical` or `low`, away from the spring.
- **Capacity learning (the fill probe).** Capacity is not perceivable (F10), so the policy
  learns it from `fill_canteen` outcomes.
  - `canteen_capacity` starts null.
  - R4 fires at the spring when capacity is null (**probe**) or when
    `canteen_servings < canteen_capacity` (top-up).
  - R0 step 2 records the outcome of a matched `fill_canteen` reference:
    - `success`: `canteen_capacity = P.own_inventory.canteen_servings`. The fill was a
      single-intent plan, so its success yields `PLAN_FINISHED` and this packet (F3); fill
      sets servings to capacity (WR §3).
    - `failure ALREADY_FULL`: `canteen_capacity = canteen_servings`.
    - `failure NO_ITEM`, `OUT_OF_REACH` or `INVALID_TARGET`: back off the canteen entity key
      (§5). This pauses probing until the retry tick.
  - **Bound:** each probe either fixes `canteen_capacity` or backs the canteen off. So at
    most one probe runs per `failed_target_retry_ticks` window, and none after capacity is
    known.
  - **Cases:**
    - empty (servings 0, capacity unknown): probe → success → capacity learned;
    - partial (unknown): probe → success → learned;
    - full (unknown): probe → `ALREADY_FULL` → learned;
    - capacity 0 (valid content): probe → `ALREADY_FULL` → 0, and no more fills;
    - known capacity: fill only below it.
  - No content is unsupported. The capacity stays valid for the run (the canteen is unique),
    even if the resident gives the canteen away and later gets it back.
- **Request:** a nonholder at H `critical` with no eligible spring stand asks one neighbor
  resident for the canteen (R6b). The policy cannot know who holds it (IC §2.2), so a
  nonholder may be asked and will refuse. `REQUESTED` and `REFUSED` back off that resident.
- **Proactive give:** R10, a holder with H at least `good` to a neighbor showing
  `dehydrated` (BN §0, physical water delivery).
- **After the holder dies** the canteen lies on the corpse tile (`world/death.py:122-124`).
  Any nonholder that sees it picks it up (R9).

### 6.2 Replies (R1)
For the chosen request `u`, with `X = u.speaker_id`. **Accept** needs all of the following
(otherwise **refuse**: `[talk refuse(in_reply_to=u.utterance_id) to X]`):
- `X` is a neighbor resident and its resident key is not failed;
- `max_plan_actions >= 2`;
- for a canteen request: enabled, holder, and H at least `moderate`. Plan:
  `[talk accept(in_reply_to=u.utterance_id) to X, give canteen×1 to X]`.
- for a fruit request for `q`: `fruit_count − q >= 1` and S at least `moderate`. Plan:
  `[talk accept, give fruit×q]`.

A requester on the same tile (distance 0) is refused, because `give` needs distance exactly 1
(F8).

### 6.3 Experimental switches (S4, S5)
- **`canteen_use="restricted"` (S4):**
  - R2, R4, R6b, R9 and R10 never fire, and a canteen request is always refused in R1.
  - Fruit replies are unaffected.
  - The fill probe never runs, so `canteen_capacity` stays null.
  - The canteen entity and its initial slot remain (plan §1.3).
- **`cue_use="ignored"` (S5):**
  - The §4.3 filter never applies.
  - Impressions are still recorded (R0 step 5), so both arms have the same state shape.

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
  canteen_capacity: integer|null
}
```

All fields are required, and unknown fields are refused. `canteen_capacity` is the one field
beyond plan §1.2's list (OQ-062). The initial state is `commitment=null`, empty arrays and
`canteen_capacity=null`.

### 7.1 Field rules
- **`issued_intents`:**
  - the intents of the last committed `ok` plan, in plan order, all with one plan ID and
    contiguous indices from 0; at most `max_plan_actions` entries;
  - each target key by action:
    - `move_to`, `pick_up` → `tile` (the target tile);
    - `gather` → `tile` (the tree's position, from the visible entity used to build the
      intent);
    - `give`, `talk` → `resident`;
    - `fill_canteen` → `entity` (`canteen_id`);
    - `drink`, `eat`, `rest`, `sleep`, `wait` → `null`;
  - retained through queued actions, save and restore; replaced by the next committed `ok`
    plan.
- **`failed_targets`:**
  - sorted by canonical `target` order, unique by `target`;
  - `code` is an IC §4 failure code or `OBSERVED_EMPTY`, `REFUSED` or `REQUESTED`;
  - **failure entries** number at most `failed_target_retry_ticks`, by construction, and are
    never evicted:
    - a decision writes at most one failure entry, from its single feedback;
    - an actor decides at most once per tick;
    - an entry written at tick `t` is deleted at the first decision with tick ≥ `t + R`;
    - so at most `R` live failure entries can exist;
  - **local entries** number at most 64. When writing a new local `target` would exceed 64,
    the local entry with the smallest `retry_after_tick` is evicted first, ties by canonical
    `target` order. A local eviction is an approved early release (OQ-064). It never affects
    failure entries or the P2-02 check.
- **`cue_impressions`:**
  - sorted by `cue_id`, unique, at most **1** entry, because valid content has exactly one
    cue (F7);
  - a perceived cue with a different `cue_id`, when one is already stored, is ignored;
    impossible on valid content;
  - merge: keep the highest detail (`near` beats `distant`); store a non-null direction from a
    `near` entry; never clear a stored direction;
  - **recognized directions** are exactly `north`, `east`, `south` and `west`; any other
    string is stored but treated as no direction (OQ-055).
- **`canteen_capacity`:** null or a nonnegative integer (§6.1).

### 7.2 Serialization and restore validation
`export_state()` returns the object above. It is serialized with IC §6.3 canonical encoding,
array orders as in §7.1, and no omitted fields. On restore, the CR-004 validator for
`rule-based-v0` refuses (no repair, no migration):
1. an unknown `rule_state_version`, a missing or unknown field, or a wrong type;
2. unsorted or duplicate arrays; more than `failed_target_retry_ticks` failure entries or
   more than 64 local entries; more than 1 impression;
3. any coordinate outside `[0,map_width) x [0,map_height)`;
4. an `issued_intents` list that is any of:
   - longer than `max_plan_actions`;
   - not all from one plan ID `build_plan_id(actor_id, o)` with
     `o < next_decision_ordinal`;
   - with indices that are not `0..n-1` in order;
   - non-empty when `next_decision_ordinal == 0`;
5. a reference whose target kind does not match its `action_type` per §7.1;
6. a failed target with `retry_after_tick < 1` or
   `> latest_perception_tick + rule_params.failed_target_retry_ticks`;
   `commitment.set_at_tick > latest_perception_tick` or `< 0`;
7. a failed-target `code` outside §7.1's set, or a `self` key with a code other than
   `INVENTORY_FULL`;
8. a non-null `direction` with `detail_level="distant"`; a negative `canteen_capacity`.

### 7.3 Transaction
`decide` computes the plan and the next state from the request, the committed state and
`PolicyConfig` only. The runtime keeps the next state pending. `commit_decision` installs it
for an `ok` outcome, like the scripted cursor (`agents/runtime.py:191-193`, AI §2.1). On an
`error` outcome (a defect; sim queues the wait substitute) the committed state stays
unchanged, so the substitute's intent ID is unmatched (§5). `export_state` returns only
committed state and refuses a pending decision (`agents/runtime.py:197-199`).

### 7.4 Decision-only cue capture (owner decision, OQ-056)
`cue_impressions` is updated **only** from the perception presented at `decide` (F1). A cue
seen only at a non-decision boundary is **intentionally not retained**. There is no ingest
hook, CR-004 does not cover cue capture, and recorded re-execution is unaffected.

- **When capture happens:**
  - a resident that walks into near range is interrupted by `NEW_SIGHT` (F4, F5) and decides
    on that packet;
  - the tick-zero decision uses the initial packet.
- **When it is lost:** a near upgrade that happens while a non-move action runs is lost if
  the cue is out of sight at the next decision. Example: dawn widens sight during rest or
  sleep, and only on content whose night radius is below the detail radius. The deferred
  `NEW_SIGHT` reaches a later decision, but the packet does not.
- **Effect on S5:** the S5 contrast measures the effect of directions captured at decisions,
  not of every exposure. On the default content (night radius 3 ≥ detail radius 1) the loss
  case needs an upgrade without movement, which cannot occur. The S5 report states this
  scope.
- **Capture rule:** a direction is captured at any decision whose packet carries it,
  whether the move that brought the resident into near range **completed** (decision on
  `PLAN_FINISHED` plus `NEW_SIGHT`) or was **interrupted** (decision on `ACTION_INTERRUPTED`
  plus `NEW_SIGHT`).
- **Test vectors:** DV-10 (loss) and DV-11a/b (capture) in §10.

## 8. Rule parameters (CR-004)

```text
RuleParams {
  rule_params_version: "0.1",
  canteen_use: "enabled"|"restricted",
  cue_use: "enabled"|"ignored",
  fruit_carry_target: integer,          // >= 1
  failed_target_retry_ticks: integer    // >= 1
}
```

- **Defaults:** `fruit_carry_target = 2` and `failed_target_retry_ticks = 36`.
  - `fruit_carry_target = 2`: BN §1 gives 1.8 fruit per resident per day; rounded up.
  - `failed_target_retry_ticks = 36`: no spec value exists (OQ-054).
- Registered variants and their identity are in `p2-experiments-v0.1.md` §6. How parameters
  reach `PolicyConfig` is in CR-004.

## 9. Determinism (acceptance for P2-02)

The same `DecisionRequest`, committed `policy_state` and `PolicyConfig` give the same
`ActionPlan` and the same next state, byte for byte in canonical encoding.
- **Choice:** only through §2.1.
- **Excluded:** unordered iteration, floats, the clock, randomness, IO, global state and
  `resolution_rng` (WR §5.6).
- **Termination:** every loop is bounded by the map size or the state caps, so `decide`
  terminates (AI §2.4).

## 10. Decision vectors (test oracle for P2-02)

Common setup unless stated:
- `PolicyConfig`: `seed=1`, `max_plan_actions=5`, `map 8x8`, `rule_params` `base`
  (`{enabled, enabled, 2, 36}`); actor `a`, `decision_ordinal=0`.
- Perception: all four bands `good`; `fruit_count=0`; not holder; `E` = every tile, all
  `grass` (no frontier, no spring); other arrays empty; feedback null.
- State: initial.
- Plans are listed as action + target.

The hashes used below: `h("1|a|0|rule-v0:tree") mod 2 = 1` and
`h("1|a|0|rule-v0:explore") mod 3 = 2`.

| ID | Inputs (differences from the setup) | Expected |
|---|---|---|
| DV-01 slot capacity 1 (G2-02) | Tick 0. Holder of `canteen_01` (servings 1); `t1` `fruit_tree` at (3,2), band `many`; own position (2,2). Second decision: tick 1, ordinal 1; feedback `failure INVENTORY_FULL` for `a:p000000:i0`; same view. | Decision 1: R8a → `[gather t1, gather t1]`; refs `i0`/`i1` → tile (3,2). Decision 2: `self` backed off (`INVENTORY_FULL`, retry 37); R8 and R9 blocked; no frontier → R12 `[rest]`. |
| DV-02 give to a backed-off resident (G2-02) | Tick 10, holder (servings 2), H `good`. State has `{resident b, OUT_OF_REACH, 40}`. `b` is a neighbor at distance 1. Heard: request canteen×1 from `b`, `u=toy:0000000010:000000`. | R1 → `[talk refuse(in_reply_to=u) b]`. No give. |
| DV-03 give/NO_ITEM (G2-02) | Tick 12, ordinal 4. Refs from the last plan: `a:p000003:i0 talk→b`, `a:p000003:i1 give→b`. Feedback `failure NO_ITEM` for `i1`. Not holder now. | No failed-target entry. Rules continue: R12 `[rest]`. A later canteen request from `b` is refused because `a` is not holder. |
| DV-04 fill probe, empty (G2-03) | At the spring: (3,2) is `spring` in `E` and `visible_tiles`; own (2,2), holder, servings 0, capacity null, H `good`. | R4 probe → `[fill_canteen entity(canteen_01)]`. Next decision: feedback success for that intent, servings 2 → `canteen_capacity = 2`; R4 no longer applies (2 < 2 false). |
| DV-05 fill probe, partial and full (G2-03) | As DV-04 with servings 1, then with servings 2. | Servings 1: probe → success → capacity = servings after fill. Servings 2: probe → feedback `ALREADY_FULL` → `canteen_capacity = 2`, no back-off. In both cases no second probe at the spring once capacity equals servings. |
| DV-06 capacity 0 (G2-03) | As DV-04; feedback `ALREADY_FULL` with servings 0. | `canteen_capacity = 0`; R4 never applies again. |
| DV-07 unreachable frontier (G2-01) | Own (0,0). `E` = (0,0), (0,1) `grass`; (1,0), (1,1), (0,2) `rock`; (3,3) `grass`. Nothing else is explored. | `K = {(0,0),(0,1),(3,3)}`. The unexplored neighbors of (0,0) and (0,1) are none. (3,3) has no BFS distance, so (3,2), (4,3), (3,4) and (2,3) are not frontiers. R11 falls through → R12 `[rest]`. |
| DV-08 shared stand dedup (G2-01) | Own (0,0). Known trees `fruit_tree` at (2,1) and (2,3); the rest is grass; trees not in view. | Stands: (2,1) gives (2,0) d2, (1,1) d2, (3,1) d4, (2,2) d4; (2,3) gives (2,2) d4, (1,3) d4, (3,3) d6, (2,4) d6. Candidates are 7 distinct tiles, with (2,2) once. Minimum d=2 → `[(2,0),(1,1)]` in (y,x) order; `h(tree) mod 2 = 1` → `[move_to (1,1)]`; commitment `{tree,(1,1),0}`. |
| DV-09 cue filter overrides a commitment (G2-01) | Own (3,4). `E` = x 1..5, y 3..5, all grass; no spring. Commitment `{explore,(0,4),0}`. Impression `{moss,(3,3),near,east}`. | (0,4) is a frontier (d3) but lies outside x > 3, so it is dropped. Filtered frontiers: (4,2) d3, (5,2) d4, (6,3) d4, (6,4) d3, (6,5) d4, (4,6) d3, (5,6) d4. Minimum → `[(4,2),(6,4),(4,6)]`; `h(explore) mod 3 = 2` → `[move_to (4,6)]`; commitment `{explore,(4,6),0}`. |
| DV-10 decision-only loss (G2-04) | Content variant of the default: `start_hour=5`, `day_start_hour=6`, **`day_end_hour=7`**, `night_radius_tiles=0`, `cue_detail_radius_tiles=1`; Mia at (14,32); Mia's tick-0 plan is a 20-tick `rest` (scripted or injected). Engine integration test. | Tick 6 (06:00, daylight): the packet has `moss_east_01` near/east and `NEW_SIGHT`; the rest continues and no decision is made. From tick 12 (07:00, night, radius 0) packets carry no cue. The decision at tick 20 gets a packet without the cue. Mia's committed `cue_impressions` stays `[]` and the explore filter does not apply. **Expected loss**, asserted. |
| DV-11a capture, interrupted move (G2-04) | Default content, unchanged; `ella` at (12,32), tick-0 plan `[move_to (21,32)]`. | The move passes near range of (15,32). `NEW_SIGHT` interrupts it at (20,32) at tick 1. The tick-1 decision (`ACTION_INTERRUPTED`, `NEW_SIGHT`) sees near/east. Committed state holds `{moss_east_01, (15,32), near, "east"}`. |
| DV-11b capture, completed move (G2-04) | As DV-11a with `[move_to (16,32)]`. | The move succeeds at tick 1 with the cue near/east and `NEW_SIGHT` in the packet. The tick-1 decision (`NEW_SIGHT`, `PLAN_FINISHED`) captures the same impression. |
| DV-12 empty-domain fall-through in R6 (G2-01) | H `low` (not critical), no spring tile in `E`, no frontier. | R6a: no stands; R6b: H is not critical; R6c: no frontier → fall through. R7 (T `good`) no; R8 no trees → falls through; R9, R10 no; R11 none → R12 `[rest]`. |
| DV-13 unmatched feedback | Tick 20, ordinal 8. Feedback `failure NO_PATH` for `a:p000007:i0`, but refs are from `a:p000006`. | No back-off; plan as without feedback. |
| DV-14 failure then same-tick regrowth (G2-R2-01) | Tick 144, ordinal 5. Refs `a:p000004:i0 gather` → tile (3,2). Feedback `failure RESOURCE_TAKEN` for `i0`. The same packet shows `t1` at (3,2) with band `few` (regrew after settlement). | Step 2 writes `{target tile (3,2), RESOURCE_TAKEN, 180}`; step 4 keeps it (not `OBSERVED_EMPTY`). R8a excludes `t1`; with no other tree, R12 `[rest]`. The decision at tick 179 still excludes (3,2); at tick 180 the entry expires and R8a may target `t1`. |
| DV-15 local cap never evicts a failure (G2-R2-01) | State: 64 local `OBSERVED_EMPTY` entries with retry 100..163 and one failure entry `{tile (0,7), NO_PATH, 90}`; tick 80. A new empty tree at (7,7) is observed. | The local entry with retry 100 is evicted and `{(7,7), OBSERVED_EMPTY, 116}` is written. The failure entry `(0,7)` stays. |

P2-02 computes every `d` by BFS on the stated grids and asserts these exact plans and next states.
