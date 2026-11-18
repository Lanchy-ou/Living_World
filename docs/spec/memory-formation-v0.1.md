# Living Island — Memory Formation v0.1 (P3.5)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §12 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
>
> Implements [ADR 0012](../adr/0012-memory-formation.md). Writes the records
> of the [memory model](memory-model-v0.1.md). The working context it reads is
> the [decision loop](decision-loop-v0.1.md)'s. Mental fatigue and fainting
> are world mechanics ([world engine](world-engine-v0.1.md) §9.3).

## 0. Scope

### 0.1 Covered here

- Mechanical writes: what code writes during the day, from what, and when
  (ADR 0012 D1).
- The waking-period boundary and K (D2, Q3).
- Consolidation: its two model calls, inputs, the change-set schema, the
  validator and the commit (D2, Q6).
- The window guard as it applies to consolidation (D2, Q8).
- Recording, replay, retries and the pending area (D5, Q5).

### 0.2 Owned elsewhere

| Subject | Spec |
|---|---|
| Record formats, sources, confidence, capacities | `memory-model-v0.1.md` |
| Day-log entries, the working context, the guard's mechanics, call records, provider errors | `decision-loop-v0.1.md` |
| Mental fatigue and fainting | `world-engine-v0.1.md` §9.3; values in `starter-content-v0.1.md` §5.2 |

## 1. Mechanical writes

Code writes these with no model call (ADR 0012 D1). They record hard facts and
direct experience, and they are the input and the safety net of
consolidation.

| Write | Written when | From | Into |
|---|---|---|---|
| Day-log entries | A packet is delivered; a turn is adopted; a recall is made | The delivered packet, the adopted response, the recall result | The working context (decision-loop spec) |
| Skill evidence | One of this resident's `act` actions ends, or it watches an `act` | `action_feedback` with the looks of the items used; `ObservedAction` | `evidence` of each matching live skill (§1.2) |
| Commitment | An agreement in which this resident is a party is accepted | The `agreement_accepted` fact (§1.1) | A new `commitment` record |
| Social facts | A `give` between this resident and another succeeds; an agreement between them is accepted; the other is seen or heard | The `item_transferred` and `agreement_accepted` facts (§1.1); the packet | `facts` of the social record for the other, created if absent |

- Every mechanical write increases the store version (memory model §1) and is
  also appended to the audit's mechanical log, so it is never lost (ADR 0012
  D5).
- Mechanical writes happen in both memory arms (ADR 0014 D2).
- Code writes a mechanical record's gist from a fixed template, for example
  `Promised mia: give 2 fruit by tick 300`.

### 1.1 The party fact feed

Commitments and transfers are hard facts about the resident itself. Owner
PR-D5 gives both parties of an agreement a record even if one did not hear the
acceptance, for example because it was asleep. So `sim` passes each resident
the objective facts in which it is a party (owner, MF-D1):

- `agreement_accepted` where it is the promisor or the promisee;
- `item_transferred` with `via:"give"` where it is the giver or the
  recipient.

The feed goes only to the memory writer. It never enters the day log, the
current state or a request; the resident meets these facts only through the
records written from them, by prefix or recall. A resident who slept through
an acceptance has the commitment in its store but no memory of hearing it.

A commitment record's source is `told`, citing the other party's utterance in
the agreement: the acceptance for the proposer, the proposal for the acceptor.

### 1.2 Skill evidence

- **Own attempts.** When one of the resident's `act` actions ends, code takes
  the looks of its target, instruments and inputs as the resident perceived
  them at the turn that chose the action (from that turn's perception: the
  `EntityView` and `ItemView` descriptors) and the phenomena in its
  `action_feedback`. For each live skill (`status` not `refuted`) with the
  same verb whose every `Look` fits an item of the attempt one to one (the
  rule representation's assignment order, §5.2 there), `attempts` increases,
  and then `matched_expected` if the phenomena include all of `expected`, else
  `other_outcomes`. `last_attempt_tick` is set.
- A `Look` fits an item when every field it names (archetype, material,
  descriptor word) equals the item's perceived value. Fields it does not name
  are free. Perceived values are apparent values, so a deceptive item fits
  the look it shows (memory model §3.4).
- **Watched attempts.** For an `ObservedAction` of an `act`, the same matching
  over its `visible_items` and target increases `watched` only. The watcher's
  phenomena are the watcher-visible ones.
- Attempts that fit no skill change no record; they stay in the day log, from
  which consolidation may form a new hypothesis.

## 2. The waking-period boundary

- A **waking period** runs from waking until the resident has been
  unconscious (`asleep` or `unconscious`) for K consecutive ticks (ADR 0012
  D2). Its ID is `p:<resident_id>:<n>`, counting from 1.
- **K = 36** ticks, six hours (ADR 0012 Q3; owner, MF-D2). It lies within the
  sleep bounds of 6–54 (owner, PR-D4) and equals the starter pack's
  `faint_ticks`, so a faint always ends a period (engine §9.3).
- If unconsciousness starts at boundary `s` (the first tick of sleep or faint
  is `s → s+1`), the period ends at boundary `s + K` if the resident is still
  unconscious throughout. A sleep that ends before `s + K`, by choice or by
  waking, ends no period: the resident keeps its open working context (ADR
  0012 D2). The sleep itself is a day-log entry.
- The boundary is the same in both memory arms (ADR 0014 D2) and is recorded
  with the run, so replay applies it at the same tick.
- The boundary is agent-side. The world knows nothing of K (protocol §6.3).

## 3. Consolidation

### 3.1 When it runs

| Situation at boundary `s` | Consolidation |
|---|---|
| A sleep starts with `duration_ticks ≥ K`, or a faint starts | Its calls may start at `s` (owner, MF-D3) |
| A sleep starts with `duration_ticks < K` | None; the period continues |
| The sleeper is woken before `s + K` | The calls are recorded as abandoned and nothing is committed; the period continues |
| Boundary `s + K` is reached | The change set is validated and committed at `s + K`, before any turn at that boundary |

- The world keeps running while the calls are outstanding. If they have not
  finished by `s + K`, the simulation waits at boundary `s + K`, as it waits
  for decision calls, so replay commits at the same tick (ADR 0012 D2).
- Inputs are fixed at `s`: the working context as it stood when the resident
  lost consciousness. Nothing new enters a working context while its owner is
  unconscious, because its senses are off (protocol §5.1).
- Only LLM residents consolidate. In the memory-off arm no calls run; the
  working context closes at `s + K` all the same (§6).

### 3.2 Call 1: selection

**Input:** the consolidation instructions, the closed working context of the
period (prefix, day log and the last current state), any pending periods (§5),
and the store index (memory model §2.1).

**Output:**

```text
SelectionOutput { read:array<string> }    // record IDs from the index, at most 60
```

IDs not in the index, and IDs beyond the first 60, are ignored and recorded.
The model chooses; code never scores importance (ADR 0012 D2).

### 3.3 Call 2: change set

**Input:** the same instructions and working context, the pending periods, the
index, the selected records in full, and two groups always included without
being chosen: open commitments and records with `needs_review` (ADR 0012 D2).

**Output** (owner, MF-D4):

```text
ChangeSet { base_version:integer, ops:array<Op> }   // base_version is filled in by the harness
Op = {op_id:string} & (
    {op:"add", ref:string, record:NewRecord}          // ref: "new:<n>", for later ops to cite
  | {op:"update", id:string, gist:string, text?:string, content?:object, about_tick?:object|null, add_sources?:array<Source>}
  | {op:"merge", ids:array<string>, ref:string, record:NewRecord}
  | {op:"supersede", id:string, by:string}            // by: an existing ID or a "new:<n>" ref
  | {op:"confidence", id:string, to:integer}
  | {op:"review_done", id:string}                     // clears needs_review after review
  | {op:"forget", id:string}
  | {op:"commitment_status", id:string, status:"kept"|"broken"|"expired", note:string}
  | {op:"trait", trait_id:string, delta:-1|1, sources:array<Source>}
)
NewRecord = {kind, gist, text?, content, about_tick?, sources, confidence}
```

- Ops apply in listed order. `op_id`s are unique within the set.
- An op **depends on** another when it cites that op's `ref`, or names a
  record that op merges, supersedes or forgets.
- `update` may change only the fields the kind leaves to consolidation:
  never a commitment's terms, a social record's `facts`, a skill's
  `evidence`, or any `sources` except by adding (memory model §3, §4.1).
- `merge` creates the merged record with the union of all merged records'
  sources, plus any it adds, and marks the merged ones superseded by it.
- Intentions are not set here. An intention is the resident's own choice at a
  turn; consolidation may only `forget` or `supersede` one when the day showed
  it was dropped (ADR 0011 D7: kept or dropped).

### 3.4 What the instructions ask

The wording is exploration-lane work (ADR 0014 D4). Its required content
(ADR 0012 D2):

- Keep where resources are, who said what and whether it was believed, what
  was promised, what was tried and with what result, and how impressions of
  others changed. Routine steps and repeated identical actions may be
  forgotten.
- Keep stable knowledge, dated observations and guesses apart (memory model
  §3.2). A later different observation is a change in the world, not a lie.
- Lower trust in a speaker only when a claim is contradicted at the time it
  described.
- Turn repeated attempts into skill hypotheses written as looks, and taught
  methods into hypotheses with a `told` source.
- About 5–15 episodic memories per consolidation is a soft target, reported,
  never enforced (ADR 0012 D2, Q4).

### 3.5 The validator

The validator reads only the change set, the inputs of the call and the store.
It never reads world state or the objective event log (ADR 0012 D2).

| Check | An op fails when |
|---|---|
| Version | The store changed since `base_version` by anything other than mechanical writes. Mechanical writes since then touch only hard-fact fields and new mechanical records, which no op may change, so they do not fail the set |
| Provenance | A new or changed record cites a source that was not in the input: a day-log entry ID not in the working context or pending periods, a memory ID not in the index, an utterance ID not in a `heard_speech` entry |
| Source kind | An `observed` source cites an entry that is not the resident's own perception; a record built only from speech has a source other than `told` or `inferred`; an existing source is removed or changed (memory model §4.1) |
| Ownership | It names a record of another resident, or changes a hard fact (§1) other than a commitment's status |
| Format | It is not one of the closed ops; a field breaks the envelope (memory model §2); a confidence breaks the caps of memory model §4.2; a trait changes by more than one step, leaves its range or has no sources |
| Capacity | An `add` or `merge` would leave its kind above capacity after the earlier ops (memory model §7); the excess ops fail in listed order |
| Reference | It names an ID that does not exist, a ref not yet defined, or a record an earlier op forgot |

- A failing op is dropped, together with every op that depends on it,
  transitively. The rest is committed as one store version (ADR 0012 D2).
- Dropped ops and their reasons go to the audit.
- A wrong belief that passes these checks is kept: code never corrects a
  resident with hidden truth.

### 3.6 Commit and the new period

At `s + K`, in this order: the change set is validated and committed; records
the change set superseded have their derived records flagged `needs_review`
(memory model §5); the working context is closed and moved to the audit; a new
period starts, and its working context is opened when the resident wakes
(decision-loop spec).

## 4. The window guard at consolidation

The decision loop's guard covers both consolidation calls (ADR 0013 D4, ADR
0012 D2). For consolidation it leaves content out in this fixed order until the
request fits the window with room for the response (owner, MF-D5):

1. Selected records beyond the mandatory ones, last selected first.
2. Pending periods, oldest first.
3. Day-log entries of the current period, oldest first.

**Never left out:** the instructions, the schema and its framing, the index,
open commitments, `needs_review` records, and the omission notice. This is the
minimum mandatory request (P3.5 brief §11, request fit).

- Day-log entries left out are not consolidated (ADR 0012 Q8). They stay in
  the audit's closed working context. The record lists them, with manifests
  before and after.
- **Request fit.** With the pinned window of the provider model (decision-loop
  spec), the minimum mandatory request fits when the index holds at most the
  store capacities of memory model §7 (about 900 live and history lines) plus
  open commitments. A run whose minimum mandatory request still does not fit
  stops as incomplete, with that reason recorded. The guard never drops a
  mandatory part, invents a summary or invokes the fallback policy to make a
  request fit.

## 5. Failure and the pending area

| Failure | Handling |
|---|---|
| Provider error or timeout on a call | Retried with the decision loop's classification and backoff, at most 3 retries per call (owner, MF-D6) |
| Output that does not parse as the schema | One retry with the same input; then the call fails |
| A call still fails | The consolidation fails: nothing is committed; the period still ends at `s + K` (ADR 0012 D5) |
| Ops fail validation | Only they and their dependents are dropped (§3.5); this is not a failed consolidation |

- **Pending area.** A failed consolidation's working context goes to the
  pending area, which the resident cannot reach. The next consolidation reads
  it together with the new period, oldest first (ADR 0012 D5).
- **Limit:** at most 2 pending periods (ADR 0012 Q5; owner, MF-D6). When a
  third would be added, the oldest pending period counts as forgotten and
  stays only in the audit.
- Mechanical records are never lost, whatever happens to pending experience
  (§1).

## 6. The memory-off arm

At `s + K` the working context is closed and moved to the audit, with no
calls. The next period starts with no earlier day log, no intention, no
dialogue state, no long-term memories in the prefix and recall that returns
nothing (ADR 0014 D2; decision-loop spec). Mechanical writes continue.

## 7. Recording and replay

```text
ConsolidationRecord {
  record_schema:"mf/0.1", resident_id, period_id, arm:"on"|"off",
  started_tick:integer, boundary_tick:integer,
  outcome:"committed"|"failed"|"abandoned"|"off_arm",
  base_version:integer, result_version:integer|null,
  selection_call_id:string|null, change_set_call_id:string|null,
  input_manifests:array<ContextManifest>,        // decision-loop spec, one per call
  guard_events:array<GuardEvent>,
  selection:SelectionOutput|null, change_set:ChangeSet|null,
  verdicts:array<{op_id, result:"committed"|"dropped", reason:string|null, depends_on:array<string>}>,
  pending_after:array<string>                   // period IDs still pending
}
```

- Both calls are recorded like decision calls: input manifest, prompt version,
  model, raw output, parsed output, tokens and latency (decision-loop spec; ADR
  0012 D5).
- The record and the store version after commit are hashed, as P3 hashes a
  decision record.
- **Replay** applies the recorded change set at the recorded boundary with no
  model call, rebuilds the store and checks its hash.

## 8. What is deferred

- Whether fainting or intoxication degrades consolidation (ADR 0012 Q2):
  not in this version. A faint consolidates like a sleep.
- Layered consolidation of very long periods (ADR 0012 D2): evaluated later.

## 9. Acceptance tests

| ID | Test |
|---|---|
| MF-01 | Mechanical writes: a commitment for both parties when an agreement is accepted, also for a party who was asleep; social facts after a give; each write increases the store version and appears in the mechanical log |
| MF-02 | The party feed never reaches a day log, a current state or a request; a request hash is unchanged by it |
| MF-03 | Skill evidence: an own attempt whose items fit a skill's looks counts `matched_expected` or `other_outcomes`; a deceptive item that looks right fits; a watched attempt counts `watched` only; a refuted skill gets no evidence |
| MF-04 | Boundary: a 36-tick sleep ends a period at `s + 36`; a 35-tick sleep, a nap, and a 54-tick sleep woken at tick 20 do not; a faint of 36 ticks does |
| MF-05 | Timing: calls start at `s` for a long sleep or a faint and never for a nap; the simulation waits at `s + K` when they are late; a woken sleeper's calls are recorded as abandoned |
| MF-06 | Change set: each op of §3.3 applies as specified on a fixture store, in listed order, with `new:<n>` refs |
| MF-07 | Validator: one negative fixture per check of §3.5; a failing op drops its dependents transitively and nothing else; dropped ops are in the audit |
| MF-08 | Version: a change set built on version `v` commits after mechanical writes; it fails after another committed change set |
| MF-09 | No hidden correction: a wrong but well-sourced belief is committed; the validator reads no world state (checked by injecting a world-state reader that fails when called) |
| MF-10 | Guard: an oversized consolidation request leaves out selected records, then pending periods, then the oldest entries; never a mandatory part; the record shows manifests before and after and the left-out entries |
| MF-11 | Failure: a call failing after 3 retries makes the consolidation fail; the period ends; its context goes to the pending area; a third failure in a row forgets the oldest pending period into the audit; mechanical records survive all of this |
| MF-12 | Memory off: no calls; the context closes at `s + K`; mechanical writes continue |
| MF-13 | Replay: a recorded run's stores are rebuilt from mechanical writes and change sets with zero model calls, with equal hashes at every version |
| MF-14 | A synthetic test memory kind registered by the memory model's extension point is consolidated by the same change-set ops (ADR 0014 D3) |

## 10. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0012 Q1 Fatigue formula | Engine §9.3 (mechanism) and starter content §5.2 (values) |
| ADR 0012 Q2 Degraded consolidation | Deferred (§8) |
| ADR 0012 Q3 K | 36, owner MF-D2 (§2) |
| ADR 0012 Q4 Episodic target and capacities | Soft target reported (§3.4); capacities in memory model §7 |
| ADR 0012 Q5 Retries and the pending limit | §5, owner MF-D6 |
| ADR 0012 Q6 Change-set schema and retention | §3.3, owner MF-D4; retention in memory model §5, §7 |
| ADR 0012 Q7 What wakes a sleeper | Answered in the protocol (owner PR-D6) |
| ADR 0012 Q8 Inputs that do not fit | §4, owner MF-D5 |

## 11. Values carried to other specs

| Value | Used by |
|---|---|
| K = 36 | Starter content `faint_ticks` (§5.2 there); the decision loop's period boundary; evaluation's arm boundary |
| The party fact feed | `sim` (decision-loop spec, harness) |

## 12. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| MF-D1 | Do hard facts reach a party who did not perceive them? | Yes: `sim` feeds each party the agreement and give facts it is part of, to the memory writer only | Owner PR-D5 gives both parties a record; the facts are about the resident itself and never enter its context directly |
| MF-D2 | K | 36 ticks (6 hours) | A normal night consolidates; a nap or an interrupted sleep does not; equals the faint length |
| MF-D3 | When do consolidation calls start? | At the start of a sleep chosen at K or longer, or of a faint; the result is committed at `s + K` | The world keeps running while the model works; a nap costs no call |
| MF-D4 | The change-set schema | Nine closed ops: add, update, merge, supersede, confidence, review_done, forget, commitment_status, trait | Covers every change ADR 0012 D2 names, and nothing that touches hard facts |
| MF-D5 | Consolidation inputs that do not fit | Leave out extra selected records, then pending periods, then the oldest day-log entries; left-out entries are not consolidated; mandatory parts are never left out | Answers ADR 0012 Q8 without a model summary |
| MF-D6 | Retries and the pending limit | 3 retries per call, 1 parse retry, at most 2 pending periods | Bounded, and a failing provider cannot pile up unread days |
| MF-D7 | Selection limit | At most 60 records read per consolidation, beyond the mandatory ones | Bounds the call while leaving the model a real choice |
