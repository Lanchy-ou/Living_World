# Living Island — Evaluation, Observability and Engineering Constraints v0.1 (P3.5)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §14 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
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
- **Fallback excluded.** Turns tagged `agent_fallback_used` never count as
  discovered, taught or acted on (ADR 0014 D2).
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
  metrics:ShardRef, cost:ShardRef, time_use:ShardRef, attempts:ShardRef
}
DecisionInspectionV2 { record:DecisionRecordV2, parts:array<StoredPart>, calls:array<CallRecord>,
                       outcome_event_ids:array<string> }
ConsolidationInspection { record:ConsolidationRecord, parts:array<StoredPart>, calls:array<CallRecord> }
StoreInspection { resident_id, period_id, store_version, records:array<MemoryRecord>, index_lines:array<string> }
```

- `parts` are the stored parts a record's manifests name, so a shard rebuilds
  its requests on its own.
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
- **Learning event sources**: own attempts (`act_settled` with this actor),
  watched attempts (`ObservedAction` delivered, protocol §5.4), heard speech
  (`utterance_heard`), and memories in context (manifest refs).
- **Items used** by an `act` come from the engine's `act_items` event (engine
  §11), which names the reserved entity of each slot.
- An instance's **trace** is the list of IDs that prove it; it is stored with
  the instance.

### 3.2 Information spreads

A **claim chain** starts at an utterance `U₀` and follows hops (ADR 0014 D2,
Q1; owner, EV-D1):

- A **hop** from speaker `A` to listener `B` holds when `B` heard `Uᵢ`
  (`utterance_heard`), and later `B` spoke an utterance `Uᵢ₊₁` at a turn whose
  manifest contains either the day-log entry of hearing `Uᵢ` or a record with
  a `told` source citing `Uᵢ`, and whose output `cite` names that entry or
  record.
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
- **Learning path** of that first success (ADR 0014 D2): every flag that
  holds, from the manifest of the turn that chose the action:

  | Flag | Holds when the turn's context contained |
  |---|---|
  | `own_failures` | Day-log entries of `X`'s own earlier attempts with the same verb that did not settle `applied` under `R` |
  | `watched` | An observation entry of another resident's attempt that settled under `R` (judged from the objective log) |
  | `told` | A `heard_speech` entry, or a record with a `told` source, cited by the turn's output, or a `told` skill record with this verb |
  | `earlier_day` | A prefix or recall record created in an earlier period that is a skill with this verb or cites an attempt that settled under `R` |
  | `prior_knowledge` | None of the above: right on the first attempt, with no related experience |

  A first success with any flag other than `prior_knowledge` counts as
  **learned on the island**. The flags are reported as a set, so mixed paths
  stay visible.
- **Coverage** of `R`: the residents with a live skill whose evidence
  attempts include at least one that settled `applied` under `R`.
- **Skill accuracy** (ADR 0014 D2; owner, EV-D2): for each skill with at least
  one evidence attempt, `matched_expected ÷ attempts` from its code-counted
  evidence (memory model §3.4). A skill is never scored by mapping descriptors
  to true values. Accuracy is reported per skill and as a distribution.
- **The rule against common sense** (starter content §5.3; owner, EV-D7). A
  **learned grass-cord axe** is a non-fallback `make_stone_axe` settlement
  `applied` by resident `X`, whose `bind` slot (`act_items`) holds a cord of
  material `grass`, where all of these hold:
  1. **An island event.** Earlier in the run, some resident's `act_settled`
     was `bind_snaps` (a vine cord snapped) or `make_stone_axe` with a grass
     cord.
  2. **It reached `X`.** Through `X`'s own feedback (it made that attempt),
     through an `ObservedAction` of it delivered to `X` (watched), or through
     an utterance `X` heard whose content refers to it, checked by hand
     (§3.7) (told).
  3. **It is in the decision.** The manifest of the turn that chose the axe
     attempt contains the day-log entry of that delivery, or a memory record
     whose sources lead back to it by IDs: an `observed` source citing that
     entry, a `told` source citing that utterance, or an `inferred` source
     citing a record that does.
  - Not enough: a success right on the first attempt with none of the above,
    and a context that holds only some other `combine` experience (the general
    `own_failures` flag). The trace names the event, the delivery, the
    manifest entry and the settlement.
- **Per-seed report for the axe.** For each run, per resident: whether it
  **met** both materials (perceived vine and grass, or cords of both),
  **tried** (a `combine` that offered a head, a handle and a cord: any
  settlement of `make_stone_axe` or `bind_snaps`, or an unmatched attempt with
  a cord among its inputs), **succeeded** (`make_stone_axe` applied) and
  **learned** (a learned grass-cord axe). The report keeps "never got that
  far" apart from "got there and did not learn".
- Hidden values never enter resident memory; the true rules are read only by
  `analysis`.

### 3.4 Artifacts persist and are used

- An **artifact** is an entity created by a rule output whose settlement had
  an actor (verb rules), or by a process rule. Its **makers** are that actor,
  or the contributors of the process (`process_progressed`). Merged stacks
  carry the union of their makers (`stack_merged`).
- A **use** is an `act_items` slot that names the artifact, in an `act` that
  settled `applied`, by a resident who is not one of its makers. A shelter is
  used when a non-maker's `sleep_in_shelter` settles `applied` within its
  reach.
- **Persistence**: an artifact counts as persisting across a day when it
  exists at a later day's start than the day it was made.

### 3.5 Commitments hold across days

Agreements come from `agreement_accepted` (protocol §7.2). An agreement
**spans a sleep** when its promisor passes a period boundary (memory
formation §2) after the acceptance and before the agreement is judged.

| Kind | Kept when, after acceptance and by `due_tick` (or by the run end without one) |
|---|---|
| `give_item {item_id}` | That item moves from the promisor to the promisee by `give` |
| `give_item {archetype, quantity}` | `give` transfers from promisor to promisee of that archetype sum to at least `quantity` |
| `return_item {item_id}` | That same item moves from the promisor to the promisee (owner, PR-D5) |
| `be_at {position, due_tick}` | The promisor stands at the position at some boundary from `due_tick − 6` to `due_tick + 6` (owner, EV-D3) |
| `contribute {process_id, work_ticks}` | The promisor's contributions to that process sum to at least `work_ticks` |

- **Broken**: `due_tick` passed without the agreement being kept while both
  parties lived, or the promisor made it impossible (gave the promised item
  to someone else, consumed it, or let the process complete without its
  share).
- **Expired**: it became impossible without the promisor's act (a party
  died, a world rule destroyed the item, others removed the process) before it
  was kept.
- **Open**: no `due_tick`, and not kept by the run end.
- Judgements read only objective events and positions (ADR 0014 D2). What the
  residents' commitment records say (memory model §3.5) is reported beside
  them, as the residents' view, so a forgotten promise and a broken one stay
  apart.

### 3.6 Time use

Each awake resident-tick is assigned one class by the action running in it
(ADR 0014 Q1, ADR 0010 Q6; owner, EV-D4):

| Class | Actions |
|---|---|
| `survival` | `eat`, `drink`, `fill`, `gather` from a fruit tree, `rest`; a `move_to` whose next started action is one of these within reach of the destination |
| `crafting` | `combine`, `strike`, `cut`, `light`, `build`, `gather` from a deposit, `contribute`, and transfers into a process or container |
| `exploring` | Any other `move_to`; `inspect` |
| `social` | `give`, `pick_up` and `drop` between residents; `wait` at a turn that carries an utterance |
| `idle` | Any other `wait` |

- Sleep and unconsciousness are reported apart, not as awake ticks.
- **Talking** is an overlay: the ticks in which the resident spoke, counted
  beside the classes, because speech rides alongside actions.
- **Spare time** is the share of awake ticks outside `survival` (starter
  content §9.4).

### 3.7 Content checks

Some evidence needs a reader: whether a retelling passes on what was heard
(§3.2), and whether a heard utterance refers to an event (§3.3). For M15
acceptance a person checks each such instance in the replay (owner, EV-D1):

- The checker is the owner or someone the owner names at Gate 3.
- For each instance the analysis lists the two texts with their IDs, ticks
  and speakers, and the replay moment. The checker marks it `carries` (the
  later text passes on the earlier message or refers to the event, garbled or
  embellished included) or `different`.
- The verdicts are stored beside the run's analysis in `content-checks.json`:
  `{instance_id, ids:array<string>, verdict:"carries"|"different", checker,
  date, note}`. Only `carries` instances count for acceptance.
- Acceptance needs only a few instances (§7.2), so this is a short review,
  not a labelling project. Instances outside acceptance stay `unchecked`.

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
| Forgotten intention | The intention set at an earlier turn of the period is neither pursued (an action citing or matching it) nor changed for 72 awake ticks |
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
- skills carried over: first successes with the `earlier_day` flag (§3.3);
- forgetting: records forgotten per consolidation, and how many of those were
  ever used;
- contradictory pairs left in a store: two live beliefs about one subject
  with the stance `stable` and opposite claims, found by the consolidation
  diagnostics in the memory browser; dated observations of a changed world
  are not counted (ADR 0012 D2).

### 4.3 Guard exposure

Guard effects can outlast the call (P3.5 brief §11, R4-C-01). Evaluation
records guard exposure per waking period and per consolidation, and marks
later outcomes as possibly affected: a skill missing after a consolidation
that left entries out, or a commitment forgotten after a guarded morning
selection.

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
  too simple to need them (no rule with an `earlier_day` first success in
  either arm), or prior knowledge enough (first successes mostly
  `prior_knowledge`). The owner decides at Gate 3 (plan §4.1).
- The model ID and the pressure cue policy are experimental conditions:
  results are reported as obtained under them (ADR 0014 D2).

## 6. Counterfactual probes

A probe tests whether one memory changed one choice (ADR 0014 D2, Q6; owner,
EV-D6).

- **Key turns**, at most 20 per run: turns whose output cites a memory, first
  successes with a `told`, `watched` or `earlier_day` flag, and turns that
  fulfil a commitment spanning a sleep. Chosen in that order, then by tick.
- **Samples**: 5 calls with the memory and 5 without, at the recorded model
  settings.
- **Changed choice**: the most frequent choice (action, verb, target) without
  the memory differs from the most frequent with it, or from the recorded
  choice. Ties count as unchanged.
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
| Rules discovered and taught | 2 rules whose first success, by some resident, is learned on the island; at least 1 first success through `watched` or `told`; and at least 1 learned grass-cord axe (§3.3) by some resident, its evidence traced from an island event to the axe decision |
| Artifacts persist and are used | 3 uses of artifacts by non-makers, at least 1 on a later day than the artifact was made |
| Commitments hold across days | 3 agreements that span a sleep and are judged; at least 2 of them kept |

- The axe line needs one learned grass-cord axe across the three on-arm runs,
  not one per run (owner, EV-D7). Making an axe needs a resident to find the
  materials, have time to spare and try, so with three seeds a per-seed
  minimum would mix "never got that far" with "got there and did not learn".
- The per-seed report of §3.3 is given for every run: met, tried, succeeded,
  learned. A learned axe in one seed shows that the behaviour can arise on its
  own; how often it recurs is stated as open.
- Told evidence for the axe and every counted hop pass the content check of
  §3.7.
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
| EV-02 | Claim chains: a scripted three-resident fixture with cited retellings gives one chain of 2 hops, marked `unchecked`; with `carries` verdicts it counts for acceptance, and with one `different` verdict it does not; an uncited retelling is a context-only candidate, not a hop |
| EV-03 | Belief and doubt: told records at confidence 3 and 1 give believed and doubted; a cited later action gives acted on |
| EV-04 | Learning paths: fixtures for each flag; a first success with only `prior_knowledge`; a mixed case reports both flags |
| EV-05 | Skill accuracy from code-counted evidence; a deceptive-material fixture scores a correct lesson ("vine cord snaps") as accurate |
| EV-06 | Artifacts: a cord made by A and used by B in an axe counts; A's own use does not; a merged stack keeps both makers; a shelter built by A and C and slept in by B counts |
| EV-07 | Commitments: one fixture per term kind for kept, broken, expired and open; `be_at` within ±6 ticks is kept and at 7 is not |
| EV-08 | Time use: each class from its action; a `move_to` ending next to a spring before a drink is survival; talking overlays |
| EV-09 | Fallback and guard turns are excluded or reported apart in every metric that §0.2 names |
| EV-10 | Arms: on-arm-only measures are marked not applicable in the off arm; per-arm reports include prefix tokens, pressure at waking and sleep timing |
| EV-11 | Probes: key-turn selection order; 5 + 5 samples; the two labels recorded separately; no probe call appears in the run or its replay |
| EV-12 | M15 counts: a synthetic metrics fixture at the minimum passes and one below fails each line |
| EV-13 | The fake-model run of §7.3 passes |
| EV-14 | Read-only: `analysis` passes the import-linter contract; the frontend computes no metric (its tests read values from the shards) |
| EV-15 | Grass-cord axe: learned via own snapped vine cord, via a watched `bind_snaps`, and via a told account with a `carries` verdict; not learned when the axe succeeds on the first try, when the context holds only another `combine` attempt, or when the told account is marked `different`; the trace names event, delivery, manifest entry and settlement |
| EV-16 | Per-seed report: fixtures for a resident that never met both materials, one that met them and never tried, one that tried and failed, and one that learned, each reported in its own column |

## 11. What other specs must record

| Needed by | Recorded in |
|---|---|
| Items used by an `act` | Engine `act_items` event (engine §11) |
| Makers of process outputs | `process_progressed` (engine §11) |
| Turn manifests and citations | Decision records (decision loop §10) |
| Period boundaries and arms | Memory formation §7, decision loop §11 |
| Guard events | Manifests (decision loop §10.1), consolidation records (memory formation §7) |
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
| EV-D7 | M15 minimum occurrences | 3 content-checked chains of 2+ hops; 2 learned rules with 1 via watching or telling, plus at least 1 learned grass-cord axe across the three on-arm runs, traced from an island event to the axe decision; a per-seed report (met, tried, succeeded, learned) with no per-seed minimum; 3 non-maker uses with 1 on a later day; 3 judged cross-sleep agreements with 2 kept (owner, 2026-11-18) | The axe is the strongest sign of learning on the island; three seeds are too few to require it in two of them |
| EV-D8 | Artifact limits | 8 MiB per shard, 32 MiB index, split never truncate | Fits a browser load; long runs shard instead of failing silently |
| EV-D9 | Exploration registration | A reproducibility manifest only, no budget approval | P3.5 has no trial caps (ADR 0012 D4) |
