# Open Questions

Add an entry whenever the spec is missing or ambiguous. Do not invent rules or numbers:
record the question, make the smallest reversible assumption, and flag it in your handoff.

| ID | Date | Raised in task | Question | Assumption made | Status |
|---|---|---|---|---|---|
| OQ-001 | 2026-11-08 | P0-01 | The product doc names a module `interface` (player interaction, saving, observation, debugging) but the P0-01 structure has no such package; its responsibilities are spread over `sim`, `persistence` and `contract`. Is a separate `interface`/API package wanted later (FastAPI)? | None; no `interface` package created. | open |
| OQ-002 | 2026-11-08 | P0-01a | Memory import-linter contract has `unmatched_ignore_imports_alerting = "none"` because no memory module imports `world.protocol` yet. | Keep `none`; switch to `error` when the first memory module imports `world.protocol`. | open |
| OQ-003 | 2026-11-08 | P0-02 | Content-validation and engine tests listed in world rules §8 are P1 work. | None; only a minimal content test (`test_default_content.py`) is added in P0-02. | closed (P1 delivered the §8 tests; M4, 2026-11-09) |
| OQ-004 | 2026-11-09 | P1-01a | World Rules §1.2 says cue coordinates must match "the respective symbols" but only `M` maps to a cue. Are other cue kinds allowed? | `CueConfig.kind` accepts only `damp_moss`, and exactly one cue must sit on the single `M`. | accepted (owner, M1, 2026-11-09) |
| OQ-005 | 2026-11-09 | P1-01a | "Need-band cutoffs are four strictly increasing interior values" (World Rules §1.1): is the upper bound strict? | Require `min_value < a < b < c < d < max_value`. | accepted (owner, M1, 2026-11-09) |
| OQ-006 | 2026-11-09 | P1-01a | The `.map` grammar says LF line endings but not whether the last row needs one; the map hash includes a final LF. | Every row, including the last, must end in LF (the default map does). | accepted (owner, M1, 2026-11-09) |
| OQ-007 | 2026-11-09 | P1-01a | Several fields have no declared range (goal `priority`; social counters). | Unspecified counters are nonnegative; `priority` is any integer. (Rework 1: the payload `action_type`/`failure_code` narrowing was removed; they are `string` per IC §3.2.) | accepted (owner, M1, 2026-11-09) |
| OQ-008 | 2026-11-09 | P1-01a | AI §6 requires one pending packet per living actor but does not say whether `runtime_states` covers dead residents too. | `runtime_states` holds exactly one entry per world resident (alive or dead), in `actor_id` order; pending packets cover living actors only. | accepted (owner, M1, 2026-11-09) |
| CR-001 | 2026-11-09 | P1-01a (G2-06) | Change request (plan §7): does IC §4 "invalid parameter shape → bounded failure" conflict with `ActionIntent` rejecting malformed shapes at construction (AI §3.1 layer 1)? | Owner-approved option A: IC §4 covers well-formed DTOs with invalid values (bounded world failure); malformed shapes cannot be constructed and are `INVALID_PLAN` in agents. Clarification added to IC §4, marked `[A1]`. | closed |
| OQ-009 | 2026-11-09 | P1-01b | Replay-frontend §4.4 lists five resident-reference payload fields (`resident_id`, `from_id`, `to_id`, `listener_id`, `addressee_id`) but `god_intervention_recorded.recipient_id` is also a resident reference, and `actor_id`/`target_id` are not classified. | Validators require `actor_id` (when non-null), the five listed fields and `recipient_id` to be declared residents; `target_id` is not checked (it may name a tree, pile or canteen). P1-08's resident filter should include `recipient_id`. | accepted (owner, 2026-11-09) |
| OQ-010 | 2026-11-09 | P1-01b | Replay-frontend §2.2 says only "a single UTF-8 JSON file"; the byte format of `replay.json` (key order, whitespace, trailing LF) is not fixed, yet fixtures need one. | Shared fixtures use IC §6.3 canonical encoding plus exactly one final LF. The validators do not depend on key order or whitespace; P1-07 may choose the exporter format. | accepted (owner, 2026-11-09) |
| OQ-011 | 2026-11-09 | P1-01b | §2.3 lists the cross-field rules but not a few checks the models need. | Added only checks that restate existing rules: clock bounds (World Rules §1.1: `tick_minutes` divides 1440, `day_start_hour < day_end_hour`); `config_hash`/`map_hash` are SHA-256 hex (IC §6.3); payload `tree_id` resolves to a declared tree; `utterance_spoken.utterance_id` equals its event ID and `in_reply_to`/`utterance_heard` cite an earlier `utterance_spoken` (a `request` for replies; IC §3.2, World Rules §4.2); coordinates inside event payloads are inside the map. | accepted (owner, 2026-11-09) |
| OQ-012 | 2026-11-09 | P1-01b | IC §3.1 says `world_initialized` is the first event at tick 0 and its payload repeats `config_hash`/`map_hash`; §2.3 did not require the bundle validator to check either. | Decided by the owner (P1-01b rework 1): the first event must be `world_initialized` at tick 0 and its `config_hash`/`map_hash` must equal the bundle's. Implemented in `ReplayBundle._check_initialization_event`. | closed |
| OQ-013 | 2026-11-09 | P1-01b | JSON numbers carry no int/float type in the browser: Ajv2020 accepts `1.0` as `integer`, while the backend's strict models refuse it. | Accepted limitation. Fixture `schema__float_where_integer` uses `1.5`, which both refuse. P1-08 should not claim to detect `1.0`. | accepted (owner, 2026-11-09) |
| OQ-014 | 2026-11-09 | P1-02 | The frozen observation ports carried neither the static map nor the config, yet LOS, costs, radii and descriptor thresholds need both. How should the port bodies get content? | Resolved by CR-002(a): `begin_observation_tick(state, completed_tick, content)`; the accumulator keeps a private deep copy and `observe_step` / `finish_observation_tick` read content only from it. The earlier global registry is deleted. | closed (CR-002) |
| OQ-015 | 2026-11-09 | P1-02 | World Rules §4.1 lists cues among visible entities while Interface Contract §2.2 also gives them `environmental_cues` with a detail level. Which array carries a cue? | Both. A cue in sight is an ordinary `cue` entity in `visible_entities` (signs `[]`, band and quantity null), or in `transient_sightings` when seen only at an intermediate step; `environmental_cues` keeps the highest detail seen. A cue is exposed only if its tile is visible (radius + LOS); it is `near` when also within `cue_detail_radius_tiles`, else `distant` (generic text, `direction=null`). (Reverses the first P1-02 assumption, per Gate 2 G2-04.) | accepted (owner, 2026-11-09, P1-09) |
| OQ-016 | 2026-11-09 | P1-02 | Interface Contract §2.2 says a ground canteen "appears as `canteen`" but does not give its `entity_id`. | `entity_type="canteen"` with `entity_id` equal to the unique item ID (`canteen_01`); a carried canteen appears only in its holder's `own_inventory`. | accepted |
| OQ-017 | 2026-11-09 | P1-02 | Interface Contract §2.1 counts own identity/inventory as receipt exposure "(including a newly received canteen)" but gives no receipt shape or position, and does not say whether it is a NEW_SIGHT. | At every boundary each living actor gets a receipt for itself (`resident`, own tile) and, if carrying it, the canteen (`canteen`, own tile). The first exposure of an inventory canteen ID against the tick-start baseline (e.g. received by `give`) is a NEW_SIGHT; tick zero is suppressed and self is never counted. (Reverses the first P1-02 assumption, per Gate 2 G2-05.) | accepted (owner, 2026-11-09, P1-09) |
| OQ-018 | 2026-11-09 | P1-02 | World Rules §4.2 makes a `move_to` target outside "known passable or one frontier tile" an `INVALID_TARGET`, while §5.3 gives `PATH_BLOCKED` for an impassable target. What does the pure path search return? | `find_path` is pure and follows WR §5.3: an unexplored frontier target (adjacent to an already explored passable tile; the start is not implicitly explored) is always routed with grass cost whatever its real terrain, and its passability and actual cost are decided at execution (P1-04); a known (explored) impassable target is `PATH_BLOCKED`; a target neither explored nor an adjacent frontier, or unreachable, is `NO_PATH`. Mapping to `INVALID_TARGET` and the start-time eligibility check belong to P1-04. | closed (superseded by OQ-041, owner 2026-11-09) |
| CR-002 | 2026-11-09 | P1-02 (G2-02, G2-06) | Change request (plan §7): (a) the observation ports have no content argument; (b) WR §1.1 requires ID uniqueness only per domain, so a resident and a tree can share an ID and the entity namespace breaks. | Owner-approved: (a) `begin_observation_tick(state, completed_tick, content: WorldContent)`, accumulator keeps a deep copy, registry deleted, plan §2.1 updated `[CR-002]`; (b) `EffectiveConfig` rejects any ID shared across resident, fruit tree, cue and canteen IDs, and any ID starting with `ground_fruit@` or `corpse@`; one line added to WR §1.1 `[CR-002]`. | closed |
| OQ-019 | 2026-11-09 | P1-03 | IC §3.1 gives every event `actor_id` and `target_id` but the catalog (§3.2) does not say which fact type fills which. The rule functions return facts without IDs and must still name them. | Rule facts carry `actor_id` = the resident concerned and `target_id` = the thing affected: `fruit_regrew` actor null, target tree ID; `condition_updated` and `stamina_action_cost_applied` actor resident, target null; `canteen_filled` actor holder, target canteen ID; `resident_died` actor resident, target null; `corpse_created` actor resident, target corpse ID; `item_dropped` actor resident, target `ground_fruit@x,y` or the canteen ID. P1-04 passes these straight to `append_fact` and may override them by change request. | accepted (Gate 2 / owner, P1-03 rework 1) |
| OQ-020 | 2026-11-09 | P1-03 | WR §3 says a sleeping resident "above both configured recovery thresholds" recovers health, but the parameters are named `health_recovery_min_satiety` and `health_recovery_min_hydration`, which could mean at-or-above. | Follow the WR text: strictly above, checked on the values after metabolism. | accepted (Gate 2 / owner, P1-03 rework 1) |
| OQ-021 | 2026-11-09 | P1-03 | `stamina_action_cost_applied.amount` and `condition_updated` emission rules are not stated: is `amount` the configured cost or the clamped amount actually deducted, is a zero cost emitted, and is `condition_updated` emitted when nothing changed? | Owner decision (P1-03 rework 1): `amount` is the actual deduction after clamping, taking awake decay first, then the movement cost, then the gather cost, each clamped at the minimum; an actual deduction of 0 emits no fact. `condition_updated` is emitted once per resident per tick (values before phase 2 versus after phase 5) only when some value changed. Cost facts precede the combined condition fact. | closed |
| OQ-022 | 2026-11-09 | P1-03 | WR §4.3 has an unfinished action emit `action_interrupted(reason=DEATH)` on death, while IC §3.2 orders the death facts `resident_died`, `corpse_created`, `item_dropped`. Where does the interrupt fact go relative to them? | `apply_death` emits only the three death facts and returns the cancelled `ActiveAction` so P1-04 can build the `ActionResult` and interrupt fact; their position in the sequence is P1-04's decision, to be recorded on the P1-04 card before the event order is wired. | closed: placement confirmed by owner in P1-04 (phase 5, after the death facts, caused by resident_died) |
| OQ-023 | 2026-11-09 | P1-08 | The generated schema types `payload` as an `anyOf` of the 25 payload models, so a payload shaped for another event type passes the schema; the backend refuses it in `WorldEvent`, but there is no shared invalid fixture for it. | The viewer checks each payload against the generated `<Type>Payload` definition named by the event type (kind `event_payload`), reusing the same schema. Covered by a viewer-local test only. Suggest adding a shared `event_payload__type_mismatch` fixture through a change request (plan §7). Adding that shared fixture is deferred to P1-07, which owns export/import parity. | closed (P1-07 shared fixture) |
| OQ-024 | 2026-11-09 | P1-08 | Shared fixture `condition_bounds__min_value_float` (`min_value: 0.0`) must be refused by the backend but `JSON.parse` cannot distinguish `0.0` from `0` (OQ-013). FE-T12 asks every shared invalid fixture to be refused by the browser. | The browser accepts that one fixture, and a test asserts and documents this; all other shared invalid fixtures are refused. The viewer does not claim to detect integral decimals. Owner decision: accepted as a browser limitation under OQ-013; FE-T12 parity exempts integral-decimal fixtures only, via one explicit exemption list. | accepted (owner, 2026-11-09) |
| OQ-025 | 2026-11-09 | P1-08 | The spec gives no values for display-only constants. | Chosen locally and kept out of data and rules: terrain and object colours, an 8-colour resident palette, resident letters A.. by declared index, night overlay alpha 0.38, 2x2-style grid for sprites sharing a tile, and the event list rendering a 150-row window around the current tick. | accepted (owner, 2026-11-09) |
| OQ-026 | 2026-11-09 | P1-05 | AI §6 permits output directories with no run artifacts, but does not name every artifact or specify whether unrelated entries may coexist. | Accept a missing or empty output directory. Refuse existing entries and paths inside the source directory to protect source bytes and mtimes. | accepted (owner, 2026-11-09) |
| OQ-027 | 2026-11-09 | P1-05 | AI §4.2 and §6 specify policy-input hashes but do not name a retained script file or locate an external source trace on resume. | Use `script.json` for the retained script. The caller supplies the recorded-policy trace directory explicitly. Paths serve as locators and the saved hashes determine identity. | accepted (owner, 2026-11-09) |
| OQ-028 | 2026-11-09 | P1-05 | AI §6 records the origin run ID and cursors without a directory locator. How should a continuation used as a later resume source resolve its ancestor event history? | Let the caller supply the ancestor prefix in emission order. Verify the prefix with the source segment up to the saved event cursor. Defer discovery and wiring to P1-06. | accepted (owner, 2026-11-09) |
| CR-003 | 2026-11-09 | P1-04 (G2-01, OQ-040) | Change request (plan §7): `create_engine` receives only WorldState, so after restore it cannot prove historical event IDs or recover pre-checkpoint request utterances; a reply to such a request diverges from an uninterrupted run (WR §8.7, AI-08). | Owner-approved option A: `create_engine(content, restored_world, history=())` takes the verified event prefix; required on restore (length = `event_log_cursor`, same run_id), used read-only to rebuild the event-ID and request indexes; WorldState and contract unchanged. Plan §2.1 updated `[CR-003]`. Implemented in P1-04 rework 1; sim wiring in P1-06. | approved |
| OQ-040 | 2026-11-09 | P1-04 | Change request: create_engine receives only WorldState, whose cursors cannot prove that a historical event ID exists or recover a request's speaker, addressee and speech act. Exact historical replies and causal validation after restore require evidence. | CR-003 supplies the verified event prefix on restore to rebuild event and request indexes. | resolved by CR-003 |
| OQ-041 | 2026-11-09 | P1-04 | OQ-018 leaves move_to failure mapping to this task. | Non-frontier unexplored and out-of-bounds targets fail INVALID_TARGET. Explored impassable targets fail PATH_BLOCKED at start. An eligible frontier target is probed during execution and can fail PATH_BLOCKED there. A disconnected eligible target fails NO_PATH. Moving to the actor's own tile succeeds with zero steps. | accepted (owner, 2026-11-09) |
| OQ-042 | 2026-11-09 | P1-04 | The init fact names an initial snapshot hash but gives no point in initialization for hashing. | Hash the canonical committed tick-zero WorldState including seeded visibility and event cursors. | accepted (owner, 2026-11-09) |
| OQ-043 | 2026-11-09 | P1-04 | WR does not explicitly say what giving to oneself means, or how a submitted action from a dead resident can take invalid_attempt_ticks without physically acting. | Reject self-give as INVALID_TARGET. A submitted DEAD attempt can carry its countdown, with no physical activity, inventory access, packet or decision. Sim only submits for living residents. | accepted (owner, 2026-11-09) |
| OQ-044 | 2026-11-09 | P1-04 | WR leaves talk-to-self and envelope linkage for heard/reply events unstated. INVALID_SPEECH_ACT exists in the catalog, while the frozen DTO rejects invalid acts and act-specific field shapes. | Reject self-talk as INVALID_TARGET because sessions require distinct residents. A heard fact names the listener as actor and the speaker as target, and cites the spoken event. Replies cite the verified request. Invalid act shapes stay at the DTO boundary per CR-001. | accepted (owner, 2026-11-09) |
| OQ-045 | 2026-11-09 | P1-04 | The frozen engine receives individual intents, but only sim knows whether a plan has more intents or when a delivered trigger has been acknowledged. The interrupt table does not cover timed actions other than move_to, gather, rest and sleep. | The engine publishes every current physical trigger in canonical order, including those on an ongoing action. Sim owns PLAN_FINISHED, tick-zero planning and deferred-trigger queues. Other timed actions and invalid-at-start countdowns retain observations without soft interruption. Death still cancels unfinished attempts. | accepted (owner, 2026-11-09) |
| OQ-046 | 2026-11-09 | P1-04 | The frozen commit has no ActionResult field, and ActiveAction does not carry historical effect deltas or event IDs across a restore. IC gives no state_delta path or visible_effects vocabulary. | Build one internal result per terminal intent with direct effects and associated event IDs from the terminal interval, retaining the original start tick. Publish only filtered feedback through the frozen packet. Prior effects remain available as their original objective facts. An owner-approved contract change is needed if consumers need full historical results. | accepted (owner, 2026-11-09) |
| OQ-047 | 2026-11-09 | P1-06 | With no CLI ancestor flag and no path in the frozen resume origin, how does a continuation locate its source when resumed again? | A separate local resume-parent.json points to the source directory and checkpoint, relative to the output when possible. Treat paths as locators only. Verify the origin's checkpoint hash, inputs, and event/decision prefixes at each hop. Keep related run paths available. | accepted (owner, 2026-11-09) |
| OQ-048 | 2026-11-09 | P1-06 | How should a continuation-only output indicate completion when the trace manifest describes full tick-zero logs? | Publish the staged continuation only after writing its final checkpoint. Write decision-trace.json for full runs and full re-executions, which are valid RecordedPolicy sources. | accepted (owner, 2026-11-09) |
| OQ-049 | 2026-11-09 | P1-06 (Gate 2 owner note) | A CLI `--seed` override changes the effective config hash but keeps the configured `meta.run_id`, so runs with different seeds share one run ID. Should the run ID reflect the seed? | P1 keeps the configured run_id; runs are told apart by config_hash. Revisit when run naming matters (P2 or later). | deferred (owner, 2026-11-09) |
| OQ-050 | 2026-11-09 | P1-07 | Replay-frontend §2.4 points resumed runs to re-execution for a full bundle. How should a continuation that extends past its source trace provide a full re-execution input? | Keep the P1-06 input rules. Export during re-execution of a full tick-zero trace. A continuation-only directory has a final checkpoint and suffix logs per OQ-048, so it cannot be passed directly as a re-execution source. | accepted (owner, 2026-11-09) |
| OQ-051 | 2026-11-09 | P1-09 | What measured replay size or viewer load time should trigger a warning? | Keep current behavior. Record the P1 measurements and leave the threshold and warning for a later owner-approved task. | deferred |
| OQ-052 | 2026-11-09 | P1-09 (Gate 2 R-01) | Replay export checks only the last spool frame against the final checkpoint; an edited intermediate frame is still exported. Should export verify more frames? | Keep P1 behavior: frames are projected from committed state at capture, and the A09 integration test compares every frame. Revisit verification of frames at retained checkpoint ticks in P2. | deferred (owner, 2026-11-09) |
| OQ-053 | 2026-11-09 | P1-09 (Gate 2 R-02) | The default-world integration test takes about 129-168 s, roughly three quarters of the backend suite. Is that CI cost acceptable? | Accepted for P1. In P2 consider moving long runs to a separate (for example nightly) job, through a task that may change the CI workflow and pytest configuration. | accepted (owner, 2026-11-09) |
| OQ-054 | 2026-11-10 | P2-00 | The rule policy needs a back-off duration for failed targets; no spec gives one. | `rule_params.failed_target_retry_ticks = 36` (6 game hours). It is a policy parameter, not a world value, and part of the policy-config identity, so a change is a separate variant tuned on development seeds only (rule-policy §8). | accepted (owner, M5) |
| OQ-055 | 2026-11-10 | P2-00 | `EnvironmentalCue.direction` is a free string (IC §2.2, `world/content.py:201`); no direction vocabulary is frozen. | The rule policy recognizes exactly `north`, `east`, `south`, `west`; any other string is stored but treated as no direction (rule-policy §7.1). | accepted (owner, M5) |
| OQ-056 | 2026-11-10 | P2-00 | Must cue impressions seen at non-decision boundaries persist, which would need an ingest hook (plan §1.2)? Gate 2 G2-04 showed a valid content variant where a near/east cue seen during rest never reaches a decision. | Owner decision (P2-00 rework 1): decision-only capture. A cue seen only at a non-decision boundary is intentionally not retained; no ingest hook; CR-004 not extended. The S5 contrast is scoped to directions captured at decisions. Test vectors DV-10 (loss, asserted) and DV-11 (capture) in rule-policy §10. | decided (owner, 2026-11-10) |
| OQ-057 | 2026-11-10 | P2-00 | The plan's dedicated-water-trip clause "no completed gather, give or pick-up since the last useful non-water action" is circular as written; a visit whose only completion is the arrival `move_to` would also pass a literal all-completions test (G2-06). | A water-only visit needs ≥ 1 completed drink or fill and no completed action other than drink, fill or `move_to` (moves are travel). Its travel leg is ticks `p+1 .. a−1`, where `a` is the visit's first frame and `p` the last frame of the previous visit, or `p = −1` with no previous visit, so the first leg starts at tick 0. A water-only visit is dedicated iff no gather, give or pick_up completed in its leg (p2-experiments §3.1, EV-01). | accepted (owner, M5) |
| OQ-058 | 2026-11-10 | P2-00 | S3 needs one declared scarcity factor and value. | `fruit.regrow_ticks = 288` (from 144), a TOML-only change that halves regrowth supply below steady demand (BN §1). No map change. | accepted (owner, M5) |
| OQ-059 | 2026-11-10 | P2-00 | S1 needs concrete spawns within initial sight of the spring. | ella (33,32), ryan (34,32), mia (35,32), grass, consecutive like the default; each sees the spring (38,30) at tick 0 (checked with `world/space.py:129`). No other change. | accepted (owner, M5) |
| OQ-060 | 2026-11-10 | P2-00 | Rule-policy run time is unmeasured, so the matrix size (7 development runs per seed) is unknown in cost. | 20 development seeds. If P2-02's measured time makes the matrix impractical, the owner may approve a shorter prefix of the registered development list through this OQ before P2-04; the acceptance list stays 20 (PD-05). | accepted (owner, M5) |
| OQ-061 | 2026-11-10 | P2-00 | BN §5 item 3 asks for a predeclared practical canteen-benefit threshold; PD-03 says a small benefit does not block P2. | No threshold; the S4 report is descriptive with the plan §1.3 confounds stated. | accepted (owner, M5) |
| OQ-062 | 2026-11-10 | P2-00 | Canteen capacity is not in Perception; valid content allows 0 to capacity initial servings and capacity 0 (G2-03). | Add `canteen_capacity` to rule `policy_state` (the one field beyond plan §1.2's list), learned by a bounded fill probe: success or `ALREADY_FULL` fixes it, other failures back the canteen off for one retry window (rule-policy §6.1, DV-04..06). No content is excluded. | accepted (owner, M5) |
| OQ-063 | 2026-11-10 | P2-00 | WR §1.1 defines adjacency as distance ≤ 1 "including same-tile for item access", but the engine requires distance exactly 1 for gather, spring drink, fill and give (`world/actions.py:68`, `:84`, `:97`, `:106`) and allows 0 or 1 for pick_up (`:119`). | No world change in P2. The rule policy uses the engine's reach (exactly 1, pick_up ≤ 1). Whether WR wording or code should change is a later change request. | accepted for P2 (owner, M5); spec/code reach mismatch to be resolved by a later change request |
| CR-004 | 2026-11-10 | P2-00 | Change request (plan §7): the rule policy needs a policy ID, a `policy_state` validator, rule parameters with canonical identity, CLI wiring and verified-provenance restore validation. Detail in the "CR-004" section below. | Decided rules: (i) add `rule-based-v0`; (ii) `RuleStateV0_1` validator; (iii) optional `PolicyConfig.rule_params`, omitted when null, fixed CLI combinations, `rule_lineage` restore rules RJ-1..RJ-8; (iv) no ingest hook (OQ-056). No generated file changes. | approved (owner, M5, 2026-11-10) |
| OQ-064 | 2026-11-10 | P2-00 (G2-12, G2-R2-01) | `failed_targets` needs a size bound, and the P2-02 no-repeat check needs deadlines that are never released early. | Failure entries (IC §4 codes from feedback) are never deleted before `retry_after_tick` and never evicted. They are bounded by `failed_target_retry_ticks` by construction: one per decision, one decision per tick. Local entries (`OBSERVED_EMPTY`, `REFUSED`, `REQUESTED`) are capped at 64, with eviction by smallest `retry_after_tick` then canonical key; this is an approved early release outside the P2-02 check. P2-02 reports the maximum local size per development run. `cue_impressions` is capped at 1, because valid content has exactly one cue (`world/content.py:377-378`). | accepted (owner, M5) |
| OQ-065 | 2026-11-10 | P2-00 (G2-06) | The canteen transfer-then-drink metric needs a window. | One game day, `W = 1440 / time.tick_minutes` (144 at the default), from the retained config; the recipient's canteen drink must be strictly after the give, within `end(y)`, with no intervening give by the recipient (p2-experiments §5, EV-11). | accepted (owner, M5) |
| OQ-066 | 2026-11-10 | P2-00 (G2-07, G2-R2-06) | BN §5 item 5's supply shortfall needs evidence separating supply from access. | Death categories use the final deprived run `R`. Water deprivation after any spring drink is `post_access_dehydration`. A food-only `R` is `food_supply_shortfall` iff the food ledger (Σ tree stocks + Σ ground fruit + Σ fruit carried by all residents, the WR §8.2 terms without consumption) is 0 at every frame of `R`; otherwise it is `food_access_shortfall` (p2-experiments §5, EV-04/05). | accepted (owner, M5) |
| OQ-067 | 2026-11-10 | P2-00 (G2-08) | The behavioral-variation diagnostic needs a canonical signature. | Signature = discovery order, discovery ticks, early frontier `move_to` targets (ticks ≤ 144, frontier status from the actor's `exploration_updated` prefix) and survival; modal ties to the smallest canonical JSON (p2-experiments §3.2). Diagnostic only. | accepted (owner, M5) |
| OQ-068 | 2026-11-10 | P2-00 (G2-05) | How does an invalid case affect a paired S4/S5 round? | The round's technical verdict is FAIL unless all 40 cases are valid; the descriptive summary uses only pairs with both arms valid and reports `pairs_used` and dropped seeds. | accepted (owner, M5) |
| OQ-069 | 2026-11-10 | P2-00 (G2-R2-05) | Paired S4/S5 reports need a run-level scalar and, where meaningful, a favorable direction for every compared metric. | Use the scalar table in p2-experiments §5. `deaths`, `ticks_deprived`, `ticks_deprived_water` (OQ-072), `dedicated_water_trips`, `water_only_visits` and the capped discovery and drink times are lower-is-better; `all_alive`, `gathers_completed`, `discovered` and `access_drank` (OQ-072) are higher-is-better. Transfers, drinks, fills, movement, cap waste, slot incidents and censoring counts are descriptive: signed difference only, no favoring count. Null times are capped at `T+1`. | accepted (owner, M5) |
| OQ-070 | 2026-11-10 | P2-00 (G2-R3-01) | Keying failure back-off by target alone blocks unrelated actions, and the refuse exception in DV-02 broke the no-repeat guarantee. | Owner decision: failure back-off is keyed by `(action kind, target)`. A failed give to `b` blocks only gives to `b` until expiry, and a talk refuse to `b` stays allowed. The same key and matching rule apply in rule-policy §5/§7.1, the P2-02 no-repeat check and the A1 metric (p2-experiments §3.2). DV-02a/b, EV-18. | decided (owner) |
| OQ-071 | 2026-11-10 | P2-00 (G2-R3-01) | With action-kind keys, the policy-local codes `REFUSED` and `REQUESTED` need a kind. | They use the policy-local kind `request`, which matches only `talk` intents with `speech_act="request"`. They therefore block only R6b to that resident, not R1 replies or R10 deliveries. `OBSERVED_EMPTY` uses `(gather, tree tile)`. Reversible: a wider block is a later rule change. | accepted (owner, M5) |
| OQ-072 | 2026-11-10 | P2-00 (G2-R3-03) | The S5 pair report needs a water-only deprivation scalar, a comparison of the full `water_access` split, and an output for zero valid pairs. | Add `ticks_deprived_water` (lower is better), `access_drank` (higher is better), the descriptive `access_found_not_drunk`/`access_not_found` counts, and a 3×3 base-by-treatment transition table over matched residents. With `pairs_used = 0`, median/min/max are `null`, counts are 0, and the table is all zeros; fields are never omitted. An even-count median is the mean of the two middle values. EV-19. | accepted (owner, M5) |
| OQ-073 | 2026-11-10 | P2-00 (G2-R3-04) | Revision labels must identify S1, S3 and the S4 decay-120 fixture, as well as staged candidates, before P2-04. | One file per (scenario, label): `content/scenarios/<scenario_id>/<label>.toml`, committed once and never modified. A fixture's pin is its only commit. S2 `orig` is pinned to `04fde8b`, and S2 `m6` to the commit named in the M6 sign-off. P2-02 commits S1 and S3 `orig`; P2-04 commits S4 `orig` and the `cand<n>` candidates on its own branch. The tool refuses a case whose file has more than one commit or whose config hash differs from the pin's (p2-experiments §6). | accepted (owner, M5) |
| OQ-074 | 2026-11-10 | P2-00 (G2-R4-01), for P2-02 | Does action-kind matching (rule-policy §2) govern plan blocking only, with the explicit approach exclusions in R8b and R9 (rule-policy §5 check table) retained? A `(pick_up, tile)` key does not match a `move_to` intent, yet the R9 row excludes the approach move to that tile; the wording "a failure entry blocks only its own action" can be read as also governing eligibility. | Yes. Action-kind matching governs plan blocking only. The R8b and R9 approach exclusions stay: `(gather, tree tile)` removes that tree from R8b's known-tree test, and `(pick_up, tile)` excludes that canteen tile from R9, including its move branch. P2-02 describes approach eligibility separately from key matching and adds a test with a backed-off visible ground canteen two tiles away (no `move_to` toward it before expiry). | accepted (owner, M5) |
| OQ-075 | 2026-11-10 | P2-03 | §3.2 A2 says "record `o-1` of `r` contains `gather X`" but a plan can hold several gathers, and "each record is counted once". Which tree is cited for a record that qualifies for more than one? | One A2 instance per qualifying record: the first `gather` intent in plan order whose tree has stock 0 in `F[t]` and is not targeted by `D`; its depletion event is cited. | open |
| OQ-076 | 2026-11-10 | P2-03 | §5 lists `given_count`/`given_qty` and `received_count`/`received_qty` as run scalars "summed over residents" but §3.1 defines them per item type. Is the run scalar a total over item types? | The run scalar is the total over both item types (fruit and canteen); the per-item-type breakdown stays in the per-resident records. No new metric is added. | open |
| OQ-077 | 2026-11-10 | P2-03 | The card asks for one end-to-end `p1-random` and one `p1-scripted` case plus a rerun, but a 1008-tick P1 run takes about 76 s (measured on the P1-03 workstation). Do the default-CI tests run the full 1008-tick cases? | No. The pytest cases run the same batch and rerun commands for 12 ticks in a throwaway git repository (a few seconds each; the new test files add about 22 s in total); the 1008-tick cases run through `scripts/p2_experiments.py` and are recorded in the P2-03 handoff. No marker or pytest setting is added. | open |

## CR-004 (approved (owner, M5, 2026-11-10); P2-00, rework 1)

Approved by the owner at M5 on 2026-11-10; the spec text is applied in `agent-interface-v0.1.md`, marked `[CR-004]`. Applies after M5 approval only. The spec text is applied by P2-00 deliverable 5, the code by
P2-01. Code references are on `04fde8b`, relative to `backend/src/living_island/`. Every item
is one decided rule; the owner's M5 choices are listed at the end.

**(i) Policy ID.** `PolicyId` is `Literal["random-v0","scripted-v0","recorded-v0"]`
(`agents/types.py:35`, AI §2.5).
- **Rule:** add `"rule-based-v0"`.
  - `create_runtime` gains its case (`agents/runtime.py:223-252`), taking neither a script
    nor records.
  - The CLI choice list (`sim/cli.py:38`) gains `rule-based`.
- `DecisionRecord.policy_id` is a free string (`agents/types.py:135`); the record schema is
  unchanged.
- *Rejected:* reusing an existing ID with a flag, because record provenance would become
  ambiguous.

**(ii) `policy_state` validator.** `ResidentRuntimeState._policy_state` accepts only `{}` or
scripted `{cursor}` (`agents/types.py:292-302`).
- **Rule:** for `rule-based-v0`, validate `policy_state` as `RuleStateV0_1` with every check of
  rule-policy §7.2, items 1–8. That includes the reference cross-checks:
  - one plan ID of this actor, with ordinal below `next_decision_ordinal`;
  - indices `0..n-1`;
  - length ≤ `max_plan_actions`;
  - each action's target kind per rule-policy §7.1.
- Random and recorded keep `{}`; scripted keeps `{cursor}`.

**(iii) Rule parameters, CLI and identity.**
- **Model.** Add `PolicyConfig.rule_params: RuleParams | null` (rule-policy §8).
  - It is non-null iff `policy_id == "rule-based-v0"`, checked in `_identities`
    (`agents/types.py:235-241`).
  - It is **omitted from serialization when null**, in the `TalkParameters` style
    (`world/protocol.py:261-294`). P1 `PolicyConfig` JSON, checkpoints and their bytes are
    unchanged.
  - A P1 save without the key validates. An explicit `"rule_params": null` is refused, as
    are unknown keys.
  - `rule_params_version` must be `"0.1"`.
  - All `RuleParams` fields are required; the integer fields must be ≥ 1.
- **CLI (`run`).** Every other combination exits 1 with a message:
  - `--policy random`, with no `--script` and no rule flags;
  - `--policy scripted --script <file>`, with no rule flags;
  - `--policy rule-based`, with no `--script`, and either:
    - zero or more of `--rule-canteen enabled|restricted` and `--rule-cue enabled|ignored`
      (each at most once; omitted switches are `enabled`, numeric fields take the defaults
      2 and 36); or
    - `--rule-params <file>` alone, with no switch flags. The file is parsed strictly as one
      `RuleParams` object.
  - `resume` and `reexecute` have no policy flags. They take the policy from the checkpoint
    (`sim/runner.py:68-79`) or use `recorded-v0`.
- **Roster path.** The CLI builds one `RuleParams` value and passes it to
  `run(..., rule_params=...)`. `_fresh_run` then passes it to `_runtime_roster`, which puts it
  into the one `PolicyConfig` shared by all residents (`sim/runner.py:47-67`). No other path
  sets it.
- **Identity.** The SHA-256 of the canonical tick-zero `PolicyConfig` (IC §6.3), recorded as
  `policy_config_sha256` in the P2 manifest (p2-experiments §6). The retained copy is the
  run's `checkpoint-0000000000.json`, which every fresh run writes (`sim/runner.py:154-158`).
- **Source identity on restore, from verified provenance.**
  - **Today:** `_prefix` walks the continuation ancestry through `resume-origin.json` and
    `resume-parent.json` (`persistence/resume.py:177-227`). It compares each parent
    checkpoint's policy configs with the requested save (`:168-174`, `:201`), and at the root
    compares the save only if `checkpoint-0000000000.json` exists (`:205-208`). The verified
    decision prefix is joined across all hops (`:120-158`).
  - **Rule lineage.** Define `rule_lineage` as true iff any of the following holds:
    1. a runtime in the requested save has `policy_id = rule-based-v0`;
    2. a runtime in any decoded ancestor checkpoint has it;
    3. a record in the verified joined decision prefix has `policy_id` or
       `effective_policy_id` equal to `rule-based-v0`. Point 3 also catches a substituted
       non-rule runtime, and a re-executed rule run whose records keep the rule provenance.
  - When `rule_lineage` is true:
    1. The root `checkpoint-0000000000.json` is **required**, and it must be an actual
       tick-zero root bound to the root's verified event prefix (RJ-4).
    2. Every saved `PolicyConfig` must equal the root tick-zero `PolicyConfig` for the same
       actor, `rule_params` included.
    3. For every actor whose root policy is not `recorded-v0`, every prefix record of that
       actor must have `policy_id` equal to the root policy ID. Recorded runs keep their
       source provenance (AI §4.3) and are exempt.
  - When `rule_lineage` is false (all P1 runs), behavior is exactly today's; P1 saves and
    runs stay compatible.
- **Restore rejections** (each a startup refusal, never a substitution):

| ID | Refusal |
|---|---|
| RJ-1 | `rule_params` present for a non-rule policy, absent for `rule-based-v0`, or explicitly `null` |
| RJ-2 | wrong `rule_params_version`, a missing, unknown or out-of-range field |
| RJ-3 | `policy_state` fails rule-policy §7.2, including the reference cross-checks |
| RJ-4 | `rule_lineage` true and the root `checkpoint-0000000000.json` is missing, undecodable against the root's retained content, or not an actual tick-zero root: `world.tick ≠ 0`, `decision_record_cursor ≠ 0`, `event_cursor` ≠ the number of tick-0 events in the verified root event prefix, or SHA-256 of its canonical world ≠ that prefix's `world_initialized.initial_snapshot_hash` (`world/engine.py:242-259`) |
| RJ-5 | `rule_lineage` true and a saved `PolicyConfig` differs from the root tick-zero `PolicyConfig` |
| RJ-6 | an ancestor checkpoint's `PolicyConfig` differs from the save (existing, `persistence/resume.py:201`) |
| RJ-7 | `rule_lineage` true and a non-recorded actor's prefix record has a different `policy_id` |
| RJ-8 | seed, plan limit or grid bounds differ from the retained config (existing, `persistence/checkpoints.py:76-87`) |

- **Compatibility:**
  - P1 random, scripted and recorded configs, saves, traces and the M4 reference hashes at
    `6d90824` are unchanged.
  - Events, decisions and the world hash never contain `PolicyConfig`.
  - Re-execution of a rule run uses `recorded-v0` without `rule_params`.
- *Rejected:* a separate `policy.json` (it would duplicate `PolicyConfig`), and CLI flags
  for each numeric field.

**(iv) Ingest hook.** None.
- The owner decided decision-only cue capture (rule-policy §7.4, OQ-056). `Runtime.ingest`
  and the request hash are unchanged.
- P2-01 generalizes only the internal commit hook (`agents/runtime.py:191-193`, scripted-only
  today) so it installs the rule policy's pending state. This is not a frozen contract.

**Generated files.** None change.
- `gen_types.py` exports `contract.__all__ = ["SnapshotMeta"]` and the `ReplayBundle` schema
  (`scripts/gen_types.py:28-46`, `contract/__init__.py:12-14`).
- The generated frontend mentions policies only as `fallback_policy_id`.
- P2-01 runs generation and `git diff --exit-code`.

**Spec text to apply after M5** (marked `[CR-004]`), in `agent-interface-v0.1.md`:
- §2.2: add `rule-based-v0` to the `policy_id` examples.
- §2.5:
  - `policy_id: "random-v0"|"scripted-v0"|"recorded-v0"|"rule-based-v0"`;
  - add `rule_params?: RuleParams`: present iff rule-based, absent otherwise, see
    `rule-policy-v0.1.md` §8;
  - add the `rule_lineage` restore rules RJ-1 to RJ-8 above by reference.
- §4: add "§4.4 `RuleBasedPolicy` (`rule-based-v0`): specified in `rule-policy-v0.1.md`."
- §6: change the `policy_state` comment to "`{}` for random/recorded; `{cursor}` for scripted;
  `RuleStateV0_1` for rule-based (rule-policy §7)".

`interface-contract-v0.1.md` needs no change (§2.4a delegates these schemas). ADR 0004
records the decision.

**For the owner at M5:**
- CR-004 as written;
- OQ-054, OQ-055, OQ-057 to OQ-069 and OQ-071 to OQ-073 dispositions;
- OQ-056 and OQ-070 are already decided by the owner.

For each choice there is one recommendation: accept the stated assumption.
