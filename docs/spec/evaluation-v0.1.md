# Living Island — Evaluation, Observability and Engineering Constraints v0.1 (P3.5)

> **Rework 2 (2026-11-18).** Pins retained evidence and the units, clocks and origin rules for M15. EV-18–23 give positive and negative threshold fixtures.

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §14 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
> Rework 1 (2026-11-18) answers the Gate 2 resident-track review
> ([review](../tasks/p3.5/P3.5-SP-01-review-agent.md) B02, B12–B15, N04) and
> the world-track B14 and B16, applies the owner's 2026-11-18 decisions on the
> axe link and on judging agreements, and uses the protocol as amended by
> CR-010.
>
> Implements [ADR 0014](../adr/0014-evaluation.md). Reads what the other P3.5
> specs record: objective events ([protocol](world-agent-protocol-v0.1.md) §9,
> [engine](world-engine-v0.1.md) §11), decision and consolidation records
> ([decision loop](decision-loop-v0.1.md) §10,
> [memory formation](memory-formation-v0.1.md) §7) and memory stores
> ([memory model](memory-model-v0.1.md)). When frozen, it supersedes
> `p3-evaluation-v0.1.md` for new work; its inspection-artifact rules are
> reused as stated.

## 0. Scope

### 0.1 Covered here

- The inspection artifact and its limits (ADR 0014 D1, Q3).
- The dashboard views and what each reads (D1).
- Exact definitions of the four capabilities, learning paths, skill scoring
  and time use (D2, Q1).
- Measures for the two experimental questions (D2, Q5).
- The memory-on/off comparison (D2).
- Counterfactual probes (D2, Q6).
- M15 acceptance counts (Q2) and the fake-model run (plan §4.1).
- Extension-point tests (D3) and the two lanes (D4, Q4).

### 0.2 Principles

- **Read-only.** `analysis` computes every metric from recorded artifacts. It
  imports no world internals, `sim`, `persistence` writers or policies (the
  existing import-linter contract). The frontend displays results and
  computes nothing (ADR 0014 D1).
- **Traceable.** Every counted instance lists the event IDs, record IDs and
  turn IDs it rests on (plan §4.1).
- **Objective judgements.** Keeping a commitment, using an artifact and
  succeeding with a rule are judged from objective events, never from what
  residents say (ADR 0014 D2).
- **Fallback excluded.** An intent or turn whose origin is `fallback`
  (decision loop §2.4) never counts as the resident's discovery, teaching,
  learning, use or keeping, whenever its result arrives (ADR 0014 D2). Other
  residents' observations of it are genuine for them and may count as their
  learning sources.
- **Guard turns apart.** Turns where the guard left content out are reported
  separately and never counted as natural long-context effects (ADR 0013
  D4).
- **Unknown is not zero.** A missing input makes a metric `null` with a
  reason; a count of nothing is 0, as in P2 (`p2-experiments-v0.1.md` §3.0).

## 1. The inspection artifact

The P3 rules carry over (`p3-evaluation-v0.1.md` §6): export to a fresh
directory after verifying the source run; bounded shards loaded lazily by the
viewer; canonical JSON hashed without a trailing LF; closed types; literal
file names from hashed IDs; validation before display; escaped plain text.

```text
InspectionIndexV2 {
  inspection_schema_version:"ia/0.1", run_id, manifest_sha256, replay_sha256,
  arm:"on"|"off", pack_ids:array<{pack_id, sha256}>, final_tick,
  residents:array<{resident_id, profile_id}>,
  decisions:array<{turn_id, resident_id, tick, shard:ShardRef}>,
  consolidations:array<{period_id, resident_id, boundary_tick, shard:ShardRef}>,
  stores:array<{resident_id, period_id, store_version, shard:ShardRef}>,
  deliveries:array<ShardRef>, revisions:array<ShardRef>, evidence_writes:array<ShardRef>,
  calls:array<{call_id, call_kind, resident_id, turn_id:string|null, period_id, shard:ShardRef}>,
  metrics:ShardRef, cost:ShardRef, time_use:ShardRef, attempts:ShardRef
}
DecisionInspectionV2 { record:DecisionRecordV2, parts:array<StoredPart>, calls:array<CallRecord>,
                       outcome_event_ids:array<string> }
ConsolidationInspection { record:ConsolidationRecord, parts:array<StoredPart>, calls:array<CallRecord> }
StoreInspection { resident_id, period_id, store_version, records:array<MemoryRecord>, index_lines:array<string> }
```

- `parts` are the stored parts a record's manifests name, so a shard rebuilds
  its dispatched requests and measured floor on its own. Export every exact
  delivered packet (including no-turn intervals), typed member refs, versioned
  memory and rendered bytes, per-attempt evidence writes, action intervals
  and the owner's persisted content checks. Index morning independently.
  Every shard family supports numbered parts within the §1 byte limits.
- A store shard is written at every period boundary and at the run end.
- **Limits** (ADR 0014 Q3; owner, EV-D8): a shard is at most 8 MiB and the
  index at most 32 MiB. A decision shard over the limit is split into numbered
  parts; nothing is truncated. An export that cannot meet the limits fails
  explicitly and leaves the source run untouched.

## 2. Dashboard views

An analysis mode in the existing frontend, reading finished runs (ADR 0014
D1). A decision jumps to its moment on the map replay.

| View | Reads |
|---|---|
| Decision inspector | Decision shards: turn reasons, manifest sections with sources and tokens, rebuilt request, raw and parsed output, the submission, the world result (`outcome_event_ids`), memories written afterwards, guard and pressure entries |
| Memory browser | Store shards: records by kind, supersession chains, `needs_review`, personality over time, the index as the resident's consolidation saw it |
| Emergence metrics | The metrics shard (§3), with each instance linked to its events and records |
| Comparison | Two runs' metrics side by side, by arm and seed (§5) |
| Cost | The cost shard: calls, input and output tokens, cache hits, latency and fallback rate per resident and day; token share per manifest section; context size, pressure band and day-log growth per turn; guard events; fallback rate against context size (ADR 0013 D4, D8) |
| Rules and attempts | The attempts shard: settlements per rule and kind; unmatched attempts grouped by verb and descriptor |
| Time use | The time-use shard (§3.6) |

## 3. Capabilities and measures

### 3.1 Common definitions

- **Turn**, **period** and **arm** as in the decision-loop and
  memory-formation specs.
- **Learning event sources**: own attempts (`act_settled` with this actor,
  model origin), watched attempts (`ObservedAction`s delivered, protocol
  §5.4), heard speech (`utterance_heard`), and memories in context (sent
  manifest refs). A commitment record is never a source of hearing: only a
  `told` source or a `heard_speech` entry is (memory model §3.5).
- **Items used** by an `act`, objectively, come from the engine's `act_items`
  event (engine §11), with true archetype and material per slot and part.
  **What a resident saw** of them comes from its own packets only:
  `items_used` for its own attempts, and for a watched one the `visible_items`
  of the `start` and `settle` observations it received. A watcher who did not
  receive the `start` observation did not see the items.
- **Lineage** of an item: `entity_created` (`made_from`, `process_id`),
  `stack_split`, `stack_merged` and `item_transferred` (engine §6, §11). An
  output's ingredients explain manufacture. Physical identity and eligible
  use follow §3.4. Record recreated_from separately for each returned part.
- **Joins** (§3.8): a day-log entry is joined to its objective counterpart by
  its `ref` and `delivery_id` (decision loop §4.3).
- An instance's **trace** is the list of IDs that prove it; it is stored with
  the instance.

### 3.2 Information spreads

A **claim chain** starts at an utterance `U₀` and follows hops (ADR 0014 D2,
Q1; owner, EV-D1):

- A **hop** from speaker `A` to listener `B` holds when `B` heard `Uᵢ`
  (`utterance_heard`), and later `B` spoke an utterance `Uᵢ₊₁` at a
  model-origin turn whose **valid** citations (decision loop §3) name either
  the `heard_speech` entry whose `ref` is `Uᵢ` or a record with a `told`
  source citing `Uᵢ`. Valid means it was in the request actually sent, so an
  entry the guard left out never makes a hop. Two identical utterances have
  different IDs and different entries; only the cited one makes the hop.
- The chain's **hop count** is the number of hops. Chains branch; each branch
  is counted once, and a branch never revisits a resident.
- **Believed or doubted**, per listener, from its store (on arm): believed when
  a record with a `told` source citing the utterance has confidence ≥ 3, or
  when a later non-fallback action's turn cites that record (**acted on**);
  doubted when such a record has confidence ≤ 1; otherwise unknown.
- **Context-only candidates**, where the manifest held the source but `cite`
  did not name it, are reported as a separate count, never as hops: a model's
  citation can be wrong, but an uncited retelling cannot be traced.
- **Content check** (owner, EV-D1). A citation alone does not show that `Uᵢ₊₁`
  passes on `Uᵢ`: the resident may cite it and talk about something else.
  Every hop counted for M15 acceptance is therefore checked by hand (§3.7):
  the later utterance must carry the earlier message. A garbled or embellished
  retelling still carries it. The automatic metric reports cited hops as
  `unchecked` until then.

### 3.3 Rules discovered and taught

- **True rules** are the verb rules of the active packs. The compatibility
  rules are reported apart, because the policy and the prior knowledge of any
  model cover them.
- **First success** of rule `R` by resident `X`: its first non-fallback
  `act_settled` with `rule_id = R` and `kind = applied`.
- **Related to `R`.** An attempt is related to `R` when it has `R`'s verb and
  either settled under `R` (any kind) or used at least one item of an
  archetype that fills a slot of `R` in `X`'s first success (by `act_items`).
  So an earlier failed pot does not count towards an axe.
- **Learning path** of that first success (ADR 0014 D2): every flag that
  holds, from the sent manifest of the turn that chose the action:

  | Flag | Holds when the turn's sent context contained |
  |---|---|
  | `own_failures` | Day-log entries of `X`'s own earlier model-origin attempts related to `R` that did not settle `applied` under `R` |
  | `watched` | Observation entries of another resident's attempt that settled `applied` under `R`, with both its `start` and `settle` observations delivered to `X` |
  | `told` | A `heard_speech` entry or a record with a `told` source, validly cited by the turn's output, whose utterance a checker marks `carries` for `R` (§3.7) |
  | `earlier_period` | A prefix or recall record created in an earlier waking period (not an earlier calendar day) whose pinned sources lead to a related attempt or whose prediction matches the successful slot looks, verb and delivered outcome of `R`; a shared verb alone fails |
  | `prior_knowledge` | None of the above: right on the first attempt, with no related experience |

  A first success with any flag other than `prior_knowledge` counts as
  **learned on the island**. The flags are reported as a set, so mixed paths
  stay visible. A `told` flag counts for acceptance only with its check;
  unchecked, it is reported as `unchecked`.
- **Coverage** of `R`: the residents with a live skill whose evidence
  attempts include at least one that settled `applied` under `R`.
- **Skill accuracy** (ADR 0014 D2; owner, EV-D2): for each skill with at least
  one evidence attempt, `matched_expected ÷ attempts` from its code-counted
  evidence (memory model §3.4). A skill is never scored by mapping descriptors
  to true values. Accuracy is reported per skill and as a distribution.
- **The rule against common sense** (starter content §5.3; owner, EV-D7 and
  2026-11-18). A **learned grass-cord axe** is a model-origin
  `make_stone_axe` settlement `applied` by resident `X`, whose `bind` slot
  (`act_items`) holds a cord of material `grass`, where all of these hold:
  1. **An island event (the lesson).** Earlier in the run, an objective
     settlement taught the rule: a `bind_snaps` that settled `applied`, emitted
     `snaps`, and whose `bind` slot held a vine
     cord, or a `make_stone_axe` `applied` whose `bind` slot held a grass cord.
     The material comes from `act_items`, never from what anyone said.
  2. **It reached `X`, with the material.** One of:
     - *own*: it was `X`'s own model-origin attempt, and its `items_used`
       showed the cord's material and its delivered feedback carried `snaps`
       for vine or the successful axe phenomenon for grass;
     - *watched*: `X` received both the `start` observation, whose
       `visible_items` show that cord with its material, and the `settle`
       observation with the matching `snaps` or axe-success phenomenon;
     - *told*: `X` heard an utterance that a checker marks `carries` for this
       event (§3.7).
  3. **It is linked to the choice.** The turn that chose `X`'s grass-cord
     attempt validly cites (decision loop §3) a day-log entry or a memory
     record that carries this lesson: the entry of that delivery (its
     `action_result`, its `observation` entries or its `heard_speech`), or a
     record whose sources lead back to one of them by IDs (`observed`,
     `told`, or `inferred` through records that do). A checker then confirms
     that the cited item bears on choosing grass over vine and marks the
     instance `relevant` (§3.7).
  - Not enough: a success right on the first attempt with none of the above; a
    context that merely contains the lesson, uncited; a citation marked
    `not_relevant`; a watch that saw only the start, or saw the snap without
    the cord's material; and a context that holds only some other `combine`
    experience. The trace names the event, the delivery, the cited entry or
    record, the check and the settlement. Causal claims beyond this link come
    only from probes (§6).
  For a direct watch citation require both cited fragments as actually
  rendered and sent (material at start and matching outcome at settle),
  or one cited immutable memory revision carrying both, with provenance
  back to those deliveries. Apply the same material/outcome test to the
  rendered own-result or heard account. A full packet cannot restore text
  trimmed from the cited representation. Bind each content check to the
  antecedent settlement, delivery members, rendered hashes, adopted act
  turn and resulting applied axe. Coverage joins hypothesis/attempt writes
  to their exact revision and applied settlement; totals cannot prove it.

- **Per-seed report for the axe.** For each run, per resident: whether it
  **met** both materials (an `ItemView` or `EntityView` with material `vine`
  and one with `grass`, in its own packets), **tried** (any settlement of
  `make_stone_axe` or `bind_snaps`, or an unmatched `combine` whose attempt
  descriptor has exactly three input entries whose signatures are a `sharp`
  item, a `long` wood item and a cord), **succeeded** (`make_stone_axe`
  applied) and **learned** (a learned grass-cord axe). The report keeps "never
  got that far" apart from "got there and did not learn".
- Hidden values never enter resident memory; the true rules are read only by
  `analysis`.

### 3.4 Artifacts persist and are used

- An **artifact** starts at an actor's manufactured output or a completed
  process output. Its makers are the actor or all distinct contributors
  recorded for that process before closure. Record its creation day.
  Transport, splitting and merging preserve provenance; for a merged
  stack use the union of maker sets and preserve constituent creation IDs
  and days. For later partial splits assign constituent portions in
  creation-event order, oldest first. An ordinary new output starts a new
  artifact with its own makers; made_from edges explain ingredients only.
  A snap's recreated parts have new physical IDs: map each returned portion
  only to its recreated_from source for maker/day attribution.
- A qualifying **use** is one model-origin applied act using a crafted
  portion as instrument or input, or one model-origin shelter sleep with a
  delivered physical benefit witnessed in EN §11. Use the event-local
  artifact and maker set at the use: for a merged stack require the actor
  outside the whole merged maker set. Count once per (run, actor, intent)
  across slots, split parts, ancestors and repeated shelter benefit ticks;
  list all qualifying artifact portions in the trace. Later-day credit
  needs an actually used qualifying portion made on an earlier day.
  Report target-only interactions from the canonical target part separately.
  A replaced shelter earns attribution only on ticks its own ID witnessed
  the benefit. No settlement-time substitution.

- **Persistence**: an artifact counts as persisting across a day when it
  exists at a later day's start than the day it was made.

### 3.5 Commitments hold across days

Agreements come from `agreement_accepted` (protocol §7.2). An agreement
**spans a sleep** when its promisor passes a period boundary (memory
formation §2) after the acceptance and before the agreement is judged.

Each agreement has a **deadline**: the boundary `due_tick + 6` for `be_at`,
the boundary `due_tick` for the other kinds with a due tick, and none
without one.

| Kind | Kept when, after acceptance and by the deadline (inclusive) |
|---|---|
| `give_item {item_id}` | That item moves from the promisor to the promisee by `give` |
| `give_item {archetype, quantity}` | `give` transfers from promisor to promisee of that archetype sum to at least `quantity` |
| `return_item {item_id}` | That same item moves from the promisor to the promisee (owner, PR-D5) |
| `be_at {position, due_tick}` | The promisor stands at the position at some boundary from `due_tick − 6` to `due_tick + 6` (owner, EV-D3) |
| `contribute {process_id, work_ticks}` | The promisor's contributions to that process sum to at least `work_ticks` |

- **Broken**: the deadline passed without the agreement being kept while both
  parties lived, or the promisor made it impossible (gave the promised item
  to someone else, consumed it, or let the process complete without its
  share).
- **Expired**: it became impossible without the promisor's act (a party
  died, a world rule destroyed the item, others removed the process) before it
  was kept.
- **Horizon first (M15).** If the effective deadline is beyond final_tick,
  label unjudged and exclude from every M15 agreement count, even if already
  fulfilled or impossible. Report that early physical outcome separately.
  No deadline and no decisive event by run end is open. Otherwise judged
  means kept, broken or expired. Only judged agreements spanning the
  promisor's qualifying sleep enter the three-agreement line.
- **Witness order.** Start strictly after acceptance; process committed
  world events in sequence, including transfer (via give), contribution,
  loss/destruction, process closure and death. The first decisive event
  fixes the physical outcome. At each completed boundary, after world
  events, insert the living promisor's confirmed K closure (either arm),
  then the living position sample for be_at in its inclusive ±6 window,
  then expiry of an inclusive deadline with no earlier decision. Thus death
  in phase 5 precedes a same-boundary position test; earlier successful
  transfer precedes a later death. Exact-K death contributes no closure.
  For a spanning agreement acceptance precedes K and K precedes the
  deciding witness in this same order. No deadline is required for an
  agreement actually fulfilled or made impossible.
- **Credit.** All physical acts, including fallback, can objectively
  fulfill. Record the origin of each necessary witness and a separate
  resident-kept flag. For quantity/work require sufficient model-origin
  units by the objective fulfillment witness. For a position use the
  intent that established the current uninterrupted stay (or the
  model-origin action maintaining an initially occupied place during the
  window); absent attributable choice gives no resident credit. A
  fallback-only fulfillment counts as objectively kept, never toward the
  two resident-kept minimum. Report the resident's subjective status
  separately.

### 3.6 Time use

Each awake tick of a living resident is assigned exactly one class by the
action running in it, whatever its outcome (a failed start counts as the
action it attempted) (ADR 0014 Q1, ADR 0010 Q6; owner, EV-D4). The table is
applied with the ordered fall-through rules below.

| Class | Actions |
|---|---|
| `survival` | `eat`, `drink`, `fill`, `gather` from a fruit tree, `rest`; `pick_up` and `drop` of fruit or of a water container; a `move_to` whose next started action is one of these within reach of the destination |
| `crafting` | `combine`, `strike`, `cut`, `light`, `build`, `gather` from a deposit, `contribute`; `pick_up` and `drop` of anything else, including into or out of a process or container |
| `exploring` | Any other `move_to`; `inspect` |
| `social` | `give`; `wait` at a turn that carries an utterance |
| `idle` | Any other `wait` |

- The tick `t → t+1` belongs to the action running in it; when an action is
  replaced at boundary `t`, the tick belongs to the new one. Reconstruct the paid interval from
  committed submission, action_started/progress/terminal events and EN §9.5
  awareness during that interval (including the final living interval).
  Remove asleep/unconscious intervals first. For each remaining interval
  select exactly one active attempt, including a paid generic failure,
  using its submitted action and the retained start target/choice or
  objective act_items when available. Apply specific rows above first.
  Awake unsuccessful sleep is survival. Gather with no proven fruit-tree
  or deposit target is crafting (attempted resource collection); an unknown
  pickup/drop item falls through to crafting. For move look only to the
  immediately next started non-move action if it is also the next start:
  use its start position, destination and the verb's reach (drink from a
  spring uses adjacent terrain). No next start, missing target evidence or
  failed reach test means exploring. A future unmapped verb is an export
  schema error. Check class sums against living awake intervals.
- Fallback-origin ticks are classified the same way and also counted in a
  `fallback` column.
- Sleep and unconsciousness are reported apart, not as awake ticks.
- **Talking** is an overlay: the ticks in which the resident spoke, counted
  beside the classes, because speech rides alongside actions.
- **Spare time** is the share of awake ticks outside `survival` (starter
  content §9.4).

### 3.7 Content checks

Some evidence needs a reader. For M15 acceptance a person checks each such
instance in the replay (owner, EV-D1 and 2026-11-18):

| Check | Question | Verdicts |
|---|---|---|
| `hop` | Does the retelling pass on what was heard (§3.2)? | `carries`, `different` |
| `told_event` | Does a heard utterance refer to the event or rule (§3.3)? | `carries`, `different` |
| `choice_link` | Does the cited entry or record bear on the choice, such as grass over vine (§3.3)? | `relevant`, `not_relevant` |
| `contradiction` | Are two live stable beliefs about one subject opposite claims (§4.2)? Diagnostic only | `contradicts`, `consistent` |

- The checker is the owner or someone the owner names at Gate 3.
- For each instance the analysis lists the texts with their IDs, ticks and
  speakers, the cited items, and the replay moment. "Carries" includes a
  garbled or embellished retelling.
- The verdicts are stored beside the run's analysis in `content-checks.json`:
  `{instance_id, check, ids:array<string>, verdict, checker, date, note}`.
  For choice_link store cited sent fragment hashes, source revision/member
  IDs, antecedent and chosen outcome IDs; display the exact as-sent texts.
  Only `carries` and `relevant` instances count for acceptance.
- Acceptance needs only a few instances (§7.2), so this is a short review,
  not a labelling project. Instances outside acceptance stay `unchecked`.

### 3.8 Instances, joins and missing inputs

- **Instance ID**: `<metric>:` followed by the first 16 hex digits of the
  SHA-256 of the canonical, sorted trace, so the same evidence always gives
  the same ID across exports.
- **Joins**, read from recorded artifacts only:

  | From | To | Key |
  |---|---|---|
  | `heard_speech` entry | `utterance_heard` event | `ref.utterance_id` and the listener |
  | `observation` entry of a watched action | `action_observed` event | `ref.intent_id`, `ref.phase` and the observer |
  | `action_result` entry | `act_settled` or `action_*` event | `ref.intent_id` |
  | Packet-derived entry | Exact journal packet/member(s) | run, resident, delivery_id and ordered member path |
  | Recall entry / own response | Producing call or recipe/off-empty turn / adopted turn | typed ref and revision |
  | Evidence write / inferred source | Attempt and immutable hypothesis/ancestor revisions | intent, delivery members, store version and content hash |
  | Decision record | Call records, manifests | `call_ids` |
  | Call record | Parts | Manifest refs, by content hash |
  | Turn and intent | Origin | Decision record `origin` |

  Deliveries with no turn (a resident that only received a packet) are joined
  by `delivery_id` all the same.
- **Missing inputs.** A metric whose input record is missing is `null` with a
  reason (§0.2), per instance; the per-turn telemetry covers every turn,
  including fallback turns and turns that stopped unfit (DL §10.3); join
  each call and its dispatched attempts to full/sent tokens, guard, cache
  hit/miss counts and pressure. Unavailable provider usage stays null with
  a reason. Thus a missing turn
  record is a defect.

## 4. The two experimental questions

These are measured, not assumed (ADR 0014 D2, Q5; owner, EV-D5).

### 4.1 Does a growing working context change behaviour?

Per turn, recorded: context tokens, pressure band and its text, fatigue band,
ticks awake, guard events. Measured per turn and binned by context tokens
(deciles of the run), by pressure band and by fatigue band:

| Behaviour | Definition |
|---|---|
| Repeat after failure | The turn chooses the same action, verb, target and item kinds as the previous turn's, whose action failed or settled `unmet` |
| Missed reply | A `propose` addressed to the resident is not answered (`accept` or `refuse`) before its dialogue session closes |
| Forgotten intention | The current intention set at an earlier turn of the period is neither pursued (a later turn's output validly cites its record) nor cleared or replaced for 72 awake ticks; no free-text matching is used |
| Invalid output | Attempts with invalid output, and turns that reached the fallback |

- Pressure and fatigue rise together over a day, so their correlations are
  reported but never read as causes. Causes come from probes (§6) that drop
  or change one cue while keeping the other.
- Guard turns are reported in their own column.

### 4.2 Does consolidation improve continuity across days?

On the on arm, and against the off arm where the evidence exists in both
(§5):

- commitments that span a sleep and are kept, broken or expired (§3.5);
- records used after the period that created them (`use_count` changes in a
  later period), by kind;
- skills carried over: first successes with the `earlier_period` flag (§3.3);
- forgetting: records forgotten per consolidation, and how many of those were
  ever used (DL §6.1: first actual decision dispatch per record and turn;
  retrieval trimmed from all dispatches earns no credit);
- contradictory pairs left in a store, as a diagnostic: candidates are two
  live beliefs with the stance `stable` and the same subject; a checker marks
  each `contradicts` or `consistent` (§3.7), and the count is over checked
  candidates. Dated observations of a changed world are never candidates
  (ADR 0012 D2).

### 4.3 Guard exposure

Guard effects can outlast the call (P3.5 brief §11, R4-C-01). Evaluation
keeps two kinds of exposure record and joins them forward:

```text
PeriodExposure        { period_id, resident_id, calls:array<{call_id, call_kind, omitted:array<Ref>}> }   // decision, recall, morning calls of the period
ConsolidationExposure { period_id, resident_id, consolidation_attempt,
                        selection_call_id:string|null, change_set_call_id:string|null,
                        omissions:array<{call_id, ref:Ref}>, outcome, supplies_period:string|null }
```

- Write an exposure row for every attempted consolidation, even if only
  selection ran. Include all omitted references (records, entries and
  pending periods) from each logical call and its terminal disposition.
  Only a committed supplier names its new period. For a resident, propagate
  omissions on a committed supplier to that period and later periods.
  Failed/abandoned calls remain observable attempts with a null supplier;
  report possible downstream effects and their evidence separately from
  that join. Morning and turn calls keep their own period exposures.

## 5. Memory on and off

- **Boundary**: both arms end a period after K ticks of unconsciousness (memory
  formation §2); the world runs the same in both (ADR 0014 D2).
- **Compared** only on evidence both arms produce: utterances, attempts,
  actions, outcomes and agreements in the objective log. Measures that need
  consolidated records (told memories, skill accuracy, coverage) are on-arm
  only and marked not applicable in the off arm.
- **Reported per arm**: prefix tokens, pressure at waking, its growth through
  the day, sleep timing and length, guard events, fallback rate. Neither arm
  is padded or trimmed.
- **Pairs**: the same seed in both arms is a pair; results are reported per
  pair and as counts over pairs, never tick by tick (as P2 pairs,
  `p2-experiments-v0.1.md` §5). Derived chance rolls give both arms the same
  luck for the same events (engine §5.3).
- **No difference** is a valid result. The report then gives a diagnosis from
  measured signs: memories never recalled (`use_count` stays 0), a world
  too simple to need them (no rule with an `earlier_period` first success in
  either arm), or prior knowledge enough (first successes mostly
  `prior_knowledge`). The owner decides at Gate 3 (plan §4.1).
- The model ID and the pressure cue policy are experimental conditions:
  results are reported as obtained under them (ADR 0014 D2).

## 6. Counterfactual probes

A probe tests whether one memory changed one choice (ADR 0014 D2, Q6; owner,
EV-D6).

- **Key turns**, at most 20 per run: turns whose output cites a memory, first
  successes with a `told`, `watched` or `earlier_period` flag, and turns that
  fulfil a commitment spanning a sleep. Chosen in that order, then by tick.
- **Samples**: 5 calls with the memory and 5 without, at the recorded model
  settings.
- **Changed choice**: the most frequent choice (action, verb, target) without
  the memory differs from the most frequent with it. Ties count as unchanged.
  The recorded choice is reported beside both; when the with-memory mode
  differs from the recorded choice, the probe is `unstable` and counts as
  neither changed nor unchanged.
- **Labels**: `cue_fixed` keeps the recorded pressure line and every other
  recorded input; `rebuilt` rebuilds the whole request, so the cue and the
  guard follow the change. Both are reported separately, with the manifests
  before and after.
- Probes are new model calls in a separate experiment record. They never
  enter a run or its replay.

## 7. M15 acceptance

### 7.1 The runs

As plan §4.1: 5 LLM residents, 7 game days, memory on and off, 3 seeds per
arm, judged by occurrence and traceability. The seeds come from the P2 seed
procedure with the list name `p3.5-m15` (`p2-experiments-v0.1.md` §2).

### 7.2 Minimum occurrences

Across the three on-arm runs (ADR 0014 Q2; owner, EV-D7):

| Capability | Minimum, each instance traced |
|---|---|
| Information spreads | 3 claim chains with at least 2 hops, every counted hop content-checked (§3.7) |
| Rules discovered and taught | 2 rules whose first success, by some resident, is learned on the island; at least 1 first success through `watched` or a checked `told`; and at least 1 learned grass-cord axe (§3.3) by some resident: lesson event, delivery with the material, a valid citation and a `relevant` check |
| Artifacts persist and are used | 3 uses of artifacts by non-makers, at least 1 on a later day than the artifact was made |
| Commitments hold across days | 3 agreements that span a sleep and are judged (kept, broken or expired, §3.5); at least 2 with resident-kept credit |

- The axe line needs one learned grass-cord axe across the three on-arm runs,
  not one per run (owner, EV-D7). Making an axe needs a resident to find the
  materials, have time to spare and try, so with three seeds a per-seed
  minimum would mix "never got that far" with "got there and did not learn".
- The per-seed report of §3.3 is given for every run: met, tried, succeeded,
  learned. A learned axe in one seed shows that the behaviour can arise on its
  own; how often it recurs is stated as open.
- Told evidence for the axe and every counted hop pass the content check of
  §3.7, and the axe's citation passes its `choice_link` check.
- The on/off difference is reported (§5), with no threshold, as planned.

### 7.3 The fake-model run

Before paid runs, a fake-model run with 5 residents over 7 game days exercises
the whole data path without provider calls (plan §4.1). The fake model returns
recorded or scripted outputs of every `TurnOutput` form, selection and change
sets with valid and invalid ops, and every error class. It passes when: the
run completes; contexts grow; consolidations commit, fail and go pending as
scripted; every request rebuilds from its parts; replay matches; and the
inspection export validates within its limits.

## 8. Extension-point tests

| Test | Milestone (ADR 0014 D3) |
|---|---|
| A test rule pack is settled by the engine; the validator rejects a rule that breaks conservation (rule representation RR-04; engine EN-22) | M12 |
| A test memory kind is stored, consolidated and assembled (memory model MM-16; memory formation MF-14) | M14 |
| A test recall recipe is selected by its turn reason (decision loop DL-19) | M14 |

All pass before M15.

## 9. The two lanes

As ADR 0014 D4:

| | Strict lane | Exploration lane |
|---|---|---|
| Covers | Protocol, engine, rule validator, persistence and replay, memory provenance checks, metric definitions | Prompt wording, consolidation prompt, recall recipes, day-log template wording, turn-policy narrowing, content values within their ranges, dashboard layout |
| Process | Spec and Gates 1–3 | No Gate 2 |
| Branch | `task/P3.5-…` | `explore/<slug>` |
| Runs | `runs/` | `runs/explore/` |
| Notes | Task card handoff | `docs/explore/<slug>.md` |

- An exploration run is registered for reproducibility only (ADR 0014 Q4;
  owner, EV-D9): a manifest pinning the commit, pack hashes, prompt versions,
  model ID and seeds. It needs no budget approval.
- Exploration may not change frozen contracts or specs; reaching `main`
  requires promotion through a normal task.

## 10. Acceptance tests

| ID | Test |
|---|---|
| EV-01 | Export: a finished run exports to a fresh directory; every shard validates by hash and schema; the source run is unchanged; an oversized shard is split, never truncated |
| EV-02 | Claim chains: a scripted three-resident fixture with cited retellings gives one chain of 2 hops, marked `unchecked`; with `carries` verdicts it counts for acceptance, and with one `different` verdict it does not; an uncited retelling is a context-only candidate, not a hop. Two identical utterances heard at one boundary: only the cited entry makes the hop; a cited entry the guard left out is invalid and makes none |
| EV-03 | Belief and doubt: told records at confidence 3 and 1 give believed and doubted; a cited later action gives acted on |
| EV-04 | Learning paths: fixtures for each flag; a first success with only `prior_knowledge`; a mixed case reports both flags; an earlier failed pot is not an `own_failures` flag for an axe; a watch with only the `start` observation gives no `watched` flag; a told flag counts only with its check; `earlier_period` follows waking periods, not calendar days |
| EV-05 | Skill accuracy from code-counted evidence; a deceptive-material fixture scores a correct lesson ("vine cord snaps") as accurate |
| EV-06 | Artifacts: a cord made by A and used by B in an axe counts; A's own use does not; a stack split from A's cord and used by B counts; a merged stack keeps both makers; a shelter built by A and C and slept in by B counts by its `condition_witness`, and with two shelters in reach the witnessed one is used; two processes completing in one tick credit their own contributors |
| EV-07 | Commitments: one fixture per term kind for kept, broken, expired, unjudged and open; `be_at` within ±6 ticks is kept and at 7 is not; a `be_at` reached at `due_tick + 4` after a K sleep is kept and is never judged broken at `due_tick`; a fulfilment and a breaking event in one tick resolve by event order; an agreement due after the run end is unjudged and not counted |
| EV-08 | Time use: every action and verb of both packs maps to exactly one class; a failed start counts as its action; a ground pickup of a stone is crafting and of fruit survival; a `move_to` ending next to a spring before a drink is survival; talking overlays; fallback ticks are also in their column |
| EV-09 | Fallback and guard turns are excluded or reported apart in every metric that §0.2 names; a fallback result arriving after the model resumed is still excluded. Guard exposure: a consolidation that left entries out marks the next period exposed although none of its calls was guarded; a guarded morning selection marks its period exposed |
| EV-10 | Arms: on-arm-only measures are marked not applicable in the off arm; per-arm reports include prefix tokens, pressure at waking and sleep timing |
| EV-11 | Probes: key-turn selection order; 5 + 5 samples; the two labels recorded separately; a with-memory mode that differs from the recorded choice is `unstable`; no probe call appears in the run or its replay |
| EV-12 | M15 counts: a synthetic metrics fixture at the minimum passes and one below fails each line |
| EV-13 | The fake-model run of §7.3 passes |
| EV-14 | Read-only: `analysis` passes the import-linter contract; the frontend computes no metric (its tests read values from the shards) |
| EV-15 | Grass-cord axe: learned via own snapped vine cord, via a watched `bind_snaps` with both phases, and via a told account with a `carries` verdict, each with a valid citation marked `relevant`. Not learned: a first-try success; a context that holds the lesson uncited; a citation marked `not_relevant` (the stated reason is unrelated); a watch that saw only the start; a snap watched without the cord's material; a told account marked `different`; only another `combine` attempt in context. The trace names event, delivery, citation, check and settlement |
| EV-16 | Per-seed report: fixtures for a resident that never met both materials, one that met them and never tried, one that tried and failed, and one that learned, each reported in its own column; an unmatched `combine` with head, handle and cord signatures counts as tried, and a cord-only attempt does not |
| EV-17 | Instances and joins (§3.8): the same evidence gives the same instance ID in two exports; every join of the table resolves on a fixture run, including a delivery with no turn; a metric with a missing record is `null` with a reason |
| EV-18 | Using only exported shards and saved content checks, rebuild a no-turn material sighting, an inferred lesson revised later, per-hypothesis coverage, off-arm intention citation and failed-turn telemetry. Missing usage is null, not zero. |
| EV-19 | Unmet bind_snaps, own material without snap, truncated watch start, missing settle citation and unrelated same-verb earlier skill fail. Both rendered cited phases or one sourced combined revision with relevant check can pass. |
| EV-20 | Due after horizon: early success and early impossibility both unjudged. Due+6 beyond horizon also excluded. Within horizon a fallback transfer is objectively kept with zero resident credit; death precedes boundary position; exact-K closure precedes living position. Exercise three judged/two resident-kept threshold. |
| EV-21 | Failed non-store gather is crafting; awake failed sleep survival. A substituted action owns the next interval. Check no-next-action and absent-target move fall-through and sum all five classes to the awake denominator. |
| EV-22 | A makes cord, B uses it for an axe then cuts: only B's cord use qualifies. Two split parts in one action count once. Target-only feed/strike appears in inspection only. Attribute shelter benefits before/after replacement separately; rerun EV-12 at and below threshold. |
| EV-23 | Guarded selection only, omitted selected records, failed/abandoned change set and committed supplier each get an exposure row. Only the commit propagates by supplies_period. Retrieved but never dispatched memory leaves continuity unchanged. |

## 11. What other specs must record

| Needed by | Recorded in |
|---|---|
| Items used by an `act` | Engine `act_items` event (engine §11) |
| What residents saw of items in use | `items_used` and `ObservedAction` phases (protocol §4.1, §5.4, CR-010) |
| Makers of process outputs | `entity_created.process_id`, `process_progressed` (engine §11) |
| Lineage | `made_from`, `stack_split`, `stack_merged`, `item_transferred` (engine §6, §11) |
| Shelter used | `condition_witness` (engine §11) |
| Turn manifests, valid citations, origins | Call and decision records (decision loop §10) |
| Day-log links | Entry `ref` and `delivery_id` (decision loop §4.3) |
| Period boundaries and arms | Memory formation §7, decision loop §11 |
| Guard events | Call records (decision loop §10.2), consolidation records (memory formation §7) |
| Skill evidence | Store records (memory model §3.4) and the mechanical log |

## 12. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0014 Q1 Metric definitions, "acted on", time-use classes | §3, owners EV-D1 to EV-D4; content checks §3.7 |
| ADR 0014 Q2 Minimum occurrences | §7.2, owner EV-D7 |
| ADR 0014 Q3 Artifact size and sharding | §1, owner EV-D8 |
| ADR 0014 Q4 Exploration registration | Reproducibility manifest only, owner EV-D9 (§9) |
| ADR 0014 Q5 Measures for the experimental questions | §4, owner EV-D5 |
| ADR 0014 Q6 Probes | §6, owner EV-D6 |
| P3.5 brief §11, R4-C-01 guard exposure | §4.3 |

## 13. Plan items this spec fixes

- The M15 seed list name `p3.5-m15` (§7.1).
- The fake-model run's pass conditions (§7.3).

## 14. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| EV-D1 | What counts as a hop of information | A heard utterance retold at a turn whose context held it and whose output cites it; uncited retellings reported apart. Each hop counted for acceptance is also checked by hand: the retelling must carry the earlier message, garbled or embellished included (owner, 2026-11-18) | Every counted hop is then traceable, as plan §4.1 requires; a citation alone may point at something else |
| EV-D2 | How skills are scored | Code-counted evidence: expected phenomena seen ÷ applications | Matches ADR 0014 D2; deception cannot make a correct lesson look wrong |
| EV-D3 | When a `be_at` promise is kept | At the place within 6 ticks (one hour) either side of `due_tick` | Residents cannot time a tick exactly; one hour is a fair meeting window |
| EV-D4 | Time-use classes | Survival, crafting, exploring, social, idle; sleep apart; talking as an overlay | Covers ADR 0014 D1's four shares; speech rides alongside actions |
| EV-D5 | Measures for the two questions | Repeat after failure, missed reply, forgotten intention, invalid output, by context size, pressure and fatigue; continuity by commitments, reuse, carried skills and forgetting | Behaviours that objective logs can show without judging text |
| EV-D6 | Probe design | Up to 20 key turns per run, 5 + 5 samples, modal choice compared, both labels | Small enough to afford, enough to see a clear change |
| EV-D7 | M15 minimum occurrences | 3 content-checked chains of 2+ hops; 2 learned rules with 1 via watching or telling, plus at least 1 learned grass-cord axe across the three on-arm runs, traced from an island event to the axe decision; a per-seed report (met, tried, succeeded, learned) with no per-seed minimum; 3 non-maker uses with 1 on a later day; 3 judged cross-sleep agreements with 2 kept (owner, 2026-11-18). The link to the axe decision is a valid citation of the lesson plus a `relevant` check by hand; agreements due after the run end are unjudged and not counted (owner, 2026-11-18, rework 1) | The axe is the strongest sign of learning on the island; three seeds are too few to require it in two of them |
| EV-D8 | Artifact limits | 8 MiB per shard, 32 MiB index, split never truncate | Fits a browser load; long runs shard instead of failing silently |
| EV-D9 | Exploration registration | A reproducibility manifest only, no budget approval | P3.5 has no trial caps (ADR 0012 D4) |
