# Living Island — Memory Formation v0.1 (P3.5)

> **Rework 2 (2026-11-18).** Fixes agreement and skill evidence, transaction authorization, and the sleep/dispatch boundary. MF-18–23 pin the traces.

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §12 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
> Rework 1 (2026-11-18) answers the Gate 2 resident-track review
> ([review](../tasks/p3.5/P3.5-SP-01-review-agent.md) B01–B06, B08, B09, B11)
> and uses the protocol as amended by CR-010.
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
| Skill evidence | One of this resident's `act` actions ends, or it watches an `act` settle | Its `action_feedback` with `items_used`; the watcher's `ObservedAction`s (protocol §4.1, §5.4) | `evidence` of each matching live skill (§1.2) |
| Commitment | An agreement in which this resident is a party is accepted | The agreement fact of §1.1 and the resident's own delivered packets | A new `commitment` record |
| Social facts | It gives to another; it watches another's `give` to it settle; an agreement between them is accepted; the other is seen or heard | Its own delivered packets; the agreement fact (§1.1) | `facts` of the social record for the other, created if absent |

- Every mechanical write increases the store version (memory model §1) and is
  also appended to the audit's mechanical log, so it is never lost (ADR 0012
  D5).
- Mechanical writes happen in both memory arms (ADR 0014 D2).
- Code writes a mechanical record's gist from a fixed template, for example
  `Promised mia: give 2 fruit by tick 300`.

### 1.1 The agreement fact

Owner PR-D5 gives both parties of an agreement a record even if one did not
hear the acceptance, for example because it was asleep. This is the one
objective fact that reaches memory without the resident perceiving it (owner,
MF-D1). Everything else that code writes comes from the resident's own
delivered packets.

- **Allowlist.** For each `agreement_accepted` event, `sim` passes each of the
  two parties exactly this projection, and nothing else of the event log:

  ```text
  AgreementFact { agreement_id, role:"promisor"|"promisee", counterpart_id,
                  terms:Terms, due_tick:integer|null, accepted_tick:integer,
                  proposal_id:string, acceptance_id:string }
  ```

  A resident that is not a party receives nothing. The fact goes only to the
  memory writer; it is kept in the audit's mechanical log with the event ID it
  came from, which code alone reads.
- **What the resident can see of it.** Memory model §2.1 projects every carrier, including social facts and
  mechanical inputs. The commitment shows its
  terms, counterpart, role, due tick and whether the counterpart's utterance
  was heard. Only the packet path may expose a delivered utterance ID. The fact path
  supplies no event or speech identifier to a request.
- **Sources** come from the resident's own packets, never from the fact
  (memory model §3.5): `observed` for its own proposal or acceptance, `told`
  for the counterpart's utterance only if `heard_utterances` delivered it to
  this resident. A resident who slept through an acceptance therefore has the
  commitment in its store, with `heard_counterpart = false`, and no source
  saying it heard it. Evaluation never counts a commitment record as hearing
  (evaluation spec §3.1).
- **Social facts** are counted from the packets: `given` from the resident's
  own `give` feedback with `status = "done"` and its `items_used`; `received`
  from a `settle` observation of another's `give` to it, with its
  nonempty `received_items` and self target (CR-011). Sum moved portions
  even after a merge. A failed or merely watched give supplies none.
  Internally `agreements` lists the agreement IDs of its commitment
  records. A gift received while asleep is not counted.

The fact feed is the same in both memory arms (ADR 0014 D2).

### 1.2 Skill evidence

- **What an attempt looked like.** The attempt's items are its `ItemUse`
  entries (protocol §5.1, CR-010), with role, quantity and apparent
  descriptors, as the world built them at the start. For own attempts they
  are `items_used` in the action's feedback; for watched ones, the
  `visible_items` of the `start` observation of that intent. The target, when
  it is not an item, is the attempt's target as the resident saw it
  in the typed `start_target` of own feedback or the delivered start phase
  (CR-011). Match entity looks by apparent fields and tile looks by terrain.
  A known target without a projected look cannot satisfy a required target.
  Use the submitted target presence for own actions; a redacted watched
  target is unknown and cannot establish a required absence. Nothing else is used:
  never `act_items`, never the attempt descriptor, never true values.
- **Grouping.** Input entries with equal looks (archetype, material and
  descriptor words) are summed into one group. A hypothesis input
  `{look, quantity}` fits a group whose look fits and whose total equals the
  quantity. Require exact group coverage and quantities; no part or group is reused.
  A missing required look makes the attempt unscorable. Target and
  instruments fit one to one. The assignment of looks to
  groups and items uses the rule representation's assignment order (§5.2
  there). For example, a by-kind input of 3 fibres that took 2 vine and 1 grass
  gives two groups and fits no "3 vine" hypothesis.
- A `Look` fits an item when every field it names (archetype, material,
  descriptor word) equals the item's perceived value. Fields it does not name
  are free. Perceived values are apparent values, so a deceptive item fits
  the look it shows (memory model §3.4).
- **Own attempts.** When one of the resident's `act` actions ends with
  `status = "done"`, for each live skill (`status` not `refuted`) with the same
  verb whose hypothesis fits, `attempts` increases, and then
  `matched_expected` if the phenomena include all of `expected`, else
  `other_outcomes`. `last_attempt_tick` is set. A generic failure
  (`status = "failed"`) or a stop counts nothing. Fallback-origin attempts
  count nothing (§1.3).
- **Watched attempts.** A watched `act` counts once, at its `settle`
  observation, and only if the watcher also received its `start` observation
  (the items in use). Then a fitting skill gets `watched` +1, and
  `watched_matched` +1 if the watcher-visible phenomena of the `settle`
  observation include all of `expected`. An attempt seen only at start, or
  only at the end, is unscorable and counts nothing. A `stop` counts nothing.
- Attempts that fit no skill change no record; they stay in the day log, from
  which consolidation may form a new hypothesis.

### 1.3 Fallback turns stay out of the mind

When `sim` uses the fallback policy for an LLM resident's turn (ADR 0013 D7,
decision-loop spec §8), what that turn did is not the resident's experience.
Code carries the origin (`model` or `fallback`) with each turn and each
intent, by turn and intent ID, through delivery, logging, consolidation and
evaluation:

- **Not written** for a fallback-origin intent or utterance: its feedback and
  `items_used` in the day log, the actor's skill evidence, and `given` social facts.
  This holds even when the result arrives after the model has resumed (a
  delayed stop, or a multi-tick action that ends later), and across a save and
  restore.
- **Still written**: everything the resident perceives about the world
  afterwards (its inventory, needs, position, what it sees and hears), because
  those are its senses, not the fallback's decisions; and the observations
  other residents make of the fallback's actions, which may update their
  watched skills/received facts under the ordinary tests. Mark origin in
  inspection for evaluation exclusions. Use the decision-loop §2.4 filter
  before rendering, recall or any writer. Current physical action and
  progress remain visible; fallback rationale/results supply no recall cue.
- **Fallback turns carry no utterance.** The fallback policy acts but does not
  speak for an LLM resident, so it can never propose, accept or refuse an
  agreement in the resident's name, and no commitment arises from a fallback
  turn.

### 1.4 The order of writes at one boundary

At each boundary, for each resident, code writes in this order: the day-log
entries of the delivered packet (decision-loop spec §4.3), then skill evidence,
then social facts, then commitments from agreement facts of that boundary. A
store version is taken after each mechanical write (memory model §1).

Within each category use packet member order, then intent/utterance ID,
counterpart ID, skill record ID, agreement event order and role as
applicable. Allocate local IDs and versions in that order; a single
category with multiple facts never depends on map iteration. Journal the
input member and each written before/after revision.

## 2. The waking-period boundary

- A **waking period** runs from waking until the resident has been
  unconscious (`asleep` or `unconscious`) for K consecutive ticks (ADR 0012
  D2). Its ID is `p:<resident_id>:<n>`, counting from 1.
- **K = 36** ticks, six hours (ADR 0012 Q3; owner, MF-D2). It lies within the
  sleep bounds of 6–54 (owner, PR-D4) and equals the starter pack's
  `faint_ticks`, so a faint always ends a period (engine §9.3).
- **Start `s`.** `s` is the boundary at which the first tick without awareness
  begins (world engine §9.5):
  - for a chosen sleep, the boundary of the turn that chose it, since the
    sleep runs from that tick; the packet of `s + 1` confirms it with
    `awareness = "asleep"`;
  - for a faint, the boundary of the packet that first shows
    `awareness = "unconscious"`, which also confirms it.
  Nothing starts before the confirming packet. A sleep that never starts (no
  confirming packet) starts nothing.
- **End.** The period ends at boundary `s + K` if the resident has not been
  awake at any boundary from `s + 1` to `s + K − 1`. Waking exactly at `s + K`
  still ends it. For example, a 36-tick sleep chosen at 100 is confirmed at
  101, wakes at 136 and ends the period at 136; a faint first shown at 101
  ends the period at 137. A sleep that ends before `s + K`, by choice or by
  waking, ends no period: the resident keeps its open working context (ADR
  0012 D2). The sleep itself is a day-log entry.
- **Death** at or before `s + K` ends the resident and its period, with nothing
  committed (§3.1).
- The boundary is the same in both memory arms (ADR 0014 D2) and is recorded
  with the run, so replay applies it at the same tick.
- The boundary is agent-side. The world knows nothing of K (protocol §6.3).

## 3. Consolidation

### 3.1 When it runs

| Situation | Consolidation |
|---|---|
| The confirming packet shows a sleep with `duration_ticks ≥ K`, or a faint | Its calls may start at that boundary (owner, MF-D3) |
| A sleep with `duration_ticks < K` | None; the period continues |
| The sleeper is woken before `s + K` | The calls are recorded as `abandoned` and nothing is committed; the period continues |
| The resident dies at or before `s + K` | The calls are recorded as `abandoned` with reason `death`; nothing is committed |
| Living resident reaches `s + K` | The change set is validated and committed at `s + K`, before any turn at that boundary (§3.6) |

- The world keeps running while the calls are outstanding: consolidation
  calls are not turn calls, so the protocol's frozen clock does not apply to
  them (protocol §2; world engine §3). If they have not finished by `s + K`,
  the simulation waits at boundary `s + K`, so replay commits at the same tick
  (ADR 0012 D2).
- **Inputs are a snapshot.** They are fixed when the confirming packet has
  been logged: the working context as it then stood, and the store at its
  version then (`base_version`). Until then the working context is kept open,
  so a sleep that fails to start loses nothing. After confirmation keep
  journaling actual packets separately from the frozen call input. Append
  body/own allowed feedback and, in compat-v1, delivered sleeping sight
  to the still-open period; starter delivers no sleeping sights. Early wake
  retains prefix and intervening log. On K closure these entries remain in
  the closed log (or failed period's pending copy); they never enter either
  call on the already frozen base. Keep journaling post-K packets under the
  new period ID until its first awake prefix opens. A death has no living
  packet: close the log at the last delivery and archive the workflow,
  without model commit, new prefix or fabricated terminal perception.

- Only LLM residents consolidate. In the memory-off arm no calls run; the
  working context closes at `s + K` all the same (§6).

### 3.2 Call 1: selection

**Input:** the consolidation instructions, the confirmed snapshot of the working context of the
period (prefix, day log and the last current state), any pending periods (§5),
the store index (memory model §2.1), and full resident-safe open and
needs_review records, deduplicated by revision (same required groups as §4).

**Output:**

```text
SelectionOutput { read:array<string> }    // record IDs from the index, at most 60
```

IDs not in the index, and IDs beyond the first 60, are ignored and recorded.
The model chooses; code never scores importance (ADR 0012 D2).

### 3.3 Call 2: change set

**Input:** the same instructions and working context, the pending periods, the
index, the selected records in full, the records that mechanical writes
created or changed during the period, shown as records in their usual model
view (new commitments, social records with changed facts, skills with changed
evidence; ADR 0012 D2), and two groups always included without being chosen:
open commitments and records with `needs_review` (ADR 0012 D2). Raw facts,
event IDs and the audit's mechanical log are never part of it (§1.1).

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
- `merge` creates the merged record with the union of all merged records'
  sources, plus any it adds, and marks the merged ones superseded by it.
- **Authority.** Which op may touch which kind (memory model §3), and which
  fields each may write. Anything not allowed here fails `authority` (§3.5).

  | Kind | Ops allowed | Fields the model may write | Code-owned |
  |---|---|---|---|
  | `episodic`, `belief` | all except `commitment_status`, `trait` | `gist`, `text`, `content`, `about_tick`, added `sources`, `confidence` | — |
  | `social` | `update`, `confidence`, `review_done` | `gist`, `text`, `content.impression`, `content.trust` (by at most one step per consolidation) | `about`, `facts` |
  | `skill` | `add`, `update`, `supersede`, `confidence`, `review_done`, `forget` | on `add`: the hypothesis, `status`, `gist`, `text`; on `update`: `status`, `gist`, `text` | `evidence` (all zero on `add`); the hypothesis after `add` (memory model §3.4) |
  | `commitment` | `commitment_status`, `review_done` | `status`, `status_note` | everything else |
  | `intention` | none | — | all (memory model §3.6) |
  | `personality` | `trait` | one step per trait (memory model §3.7) | `base`, `min`, `max`, history |
  | Any | — | — | `id`, `owner_id`, `kind`, `created_tick`, `updated_tick`, `last_used_tick`, `use_count`, `supersedes`, `superseded_by` (set only through ops), `needs_review` (set by code, cleared by `review_done`) |

  - `add` and `merge` may create only `episodic`, `belief` and `skill`
    records; a `merge` may not involve skills. A commitment, social,
    intention or personality record is never created by a change set.
  - `supersede` and `forget` may never name a commitment, social or
    personality record, nor may capacity eviction remove one (memory model
    §5, §7).
  - At most one `trait` op per trait and one `trust` change per social record
    in one change set.
- Intentions are not touched here. An intention is the resident's own choice
  at a turn (ADR 0013 D6); a resident drops it by clearing it.

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

The validator reads only the change set, the change-set call's sent input
(after the guard) and the store. It never reads world state, the objective
event log or the audit (ADR 0012 D2).

**The allowlist.** From the sent input, code builds a typed allowlist before
checking any op:

| Source or target | Allowed only when |
|---|---|
| `observed` `entry_id` | The entry is in the sent input (current period or a sent pending period), its type is one of the resident's own perceptions (decision-loop spec §4.3), and it **witnesses the record's subject**: its `about` keys share at least one key with the record's subject keys (below) |
| `told` `utterance_id`, `speaker_id` | A `heard_speech` entry in the sent input carries that utterance ID, and its speaker equals `speaker_id` |
| `inferred` `memory_ids`, `call_id` | `call_id` is this change-set call's ID; each memory ID is a record shown in the sent input (in full or as an index line) or a ref defined by an earlier accepted op of this set |
| `innate` | Never in a change set |
| Record named by `update`, `confidence`, `review_done`, `forget`, `commitment_status`, by `supersede` as either endpoint, or by `merge` as a merged record | The record is in the sent input **in full** (selected, mandatory or mechanical), or is an earlier accepted new ref with its full staged record; an index line alone cannot authorize mutation |

**Scope.** The witness test and the allowlist apply to the sources a change
set writes. The code-written sources of commitment records follow §1.1: an
`observed` source there is the resident's own proposal or acceptance
feedback, keyed `spoke:<utterance_id>` (decision-loop spec §4.3), and means
only that the resident spoke.

**Confidence.** A `confidence` op or a new record's confidence above 3 fails
`format` when the record is speech-derived (memory model §4.2), whether or not
it also has `observed` sources. So does an `update` or `merge` that would
leave a confidence-4 record speech-derived, for example adding a `told`
source to it. Code sets the candidate's `speech_derived` on the staged copy by
the carry-forward rule of memory model §4.2: the field of the current staged
revision (or of each merged revision) combined with the newly added sources
only, whose cited revisions are read from the sent input or the staged store.
It never re-reads a source already bound, and never reads the audit; an op
that sets the field itself fails `format`. The cap is checked on the
resulting candidate. After commit, code writes
the `possible_relabel` flags of memory model §4.2 to the consolidation
record (§7).

**Subject keys** of a record, for the witness test: a belief's `subject` (a
place `x,y` gives `place:x,y`, an entity `entity:<id>`, a resident
`resident:<id>`, a kind of thing `archetype:<id>`; a `general` belief has
none); an episodic record's participants and place; a skill's verb and the
archetype and material IDs of its looks; a social record's resident. A
record with no subject keys cannot take an `observed` source; it can rest on
`told` or `inferred` sources. The test checks attribution against what the
resident received, never whether the claim is true. For example, a hunger
entry (`need:satiety`) cannot be cited as having seen that a spring is
poisoned (`place:38,30`); an entry showing the spring tile can.

So an ID the guard left out, a guessed ID, a wrong speaker or a forged call is
refused, and the model can change only records it was shown in full.

**Checks.** Derive the write/read sets below, then check each op in this order; the first failure is its reason:

| Reason | An op fails when |
|---|---|
| `depends_on` | An earlier dropped op intersects its dependencies (step 2) |
| `format` | Duplicate op ID or producer ref (all duplicate occurrences invalid); it is not one of the closed ops; a field breaks the envelope (memory model §2); a confidence breaks the caps of memory model §4.2; a trait changes by more than one step, leaves its range or has no sources |
| `authority` | It breaks the authority table of §3.3: a kind or field it may not write, a second `trait` op for one trait, a second `trust` change for one record |
| `reference` | It names an ID that does not exist in the staged store, a ref not yet defined, or a record an earlier accepted op forgot, or a self/cyclic or conflicting supersession edge |
| `provenance` | A source or operand lacks the required same-resident authorization |
| `source_kind` | An existing source is removed or changed; a record built only from speech uses its repetition as observation of the subject. Own speech feedback may support only a statement that the resident spoke; an observation about its subject requires a separate direct perception entry (memory model §4.1) |
| `capacity` | An episodic `add` or `merge` would leave the kind above capacity; beliefs and skills make room by the eviction rule of memory model §7 and fail only when that is not enough |

**Staged application** (a transaction over one store version):

1. The ops are taken in listed order against a staged copy of the store at
   `base_version`.
2. Pre-scan explicit mutation operands of the entire submitted list,
   including both supersession endpoints and every merge member. Protect
   them (including later targets) and new records from capacity eviction
   even if the later op fails. Check unique producer refs across add/merge;
   a forward or undefined ref fails reference. New refs may be cited or
   mutated only after their producer passes, under the same kind/field
   authority as a full sent record. Supersede endpoints must be distinct,
   same kind, owned by this resident, authorized, with free link endpoints.
   Reject cycles in supersession and inferred-revision ancestry. Trait
   mutations require that resident's full personality record.
3. On the current staged copy compute the candidate's write set: explicit
   targets and produced IDs, backlinks, review flags of affected dependent
   records and deterministic capacity victims (MM §7). Flags and evictions
   are code-owned effects only. Record prospective implicit targets when
   determinable, even on rejection; never speculate a victim for an
   unresolved operand. A read/write of an earlier dropped op's declared or
   prospective write, or use of its ref, fails depends_on first (list prior
   op IDs in list order). Otherwise use the table in order. Commit all
   explicit and implicit effects of a passing op to the staged copy, or
   none on failure. Skip earlier staged writes when choosing capacity
   victims. Dependency diagnostics thus use the same order on replay.

4. After the last op, the staged effects are rebased (§3.6) and committed as
   one store version (ADR 0012 D2).

For example, an `update` that fails `provenance` while adding an `observed`
source leaves the record unchanged; a later `confidence` op on that record
depends on it and is dropped; an independent valid op in the same set still
commits. An overflowing belief `add` that fails stages no eviction.

- Every verdict, with its reason and the IDs of the ops it depends on, goes to
  the consolidation record and the audit.
- A wrong belief that passes these checks is kept: code never corrects a
  resident with hidden truth.

### 3.6 Commit and the new period

**Rebase.** Between `base_version` and the commit, only mechanical writes can
change the store: the resident is not awake, so no turn writes and no context
is assembled, and only one consolidation per resident runs at a time. Those
writes touch only code-owned fields and create only code-written records
(§3.3). The staged effects are therefore applied onto the latest version
field by field: model-owned fields from the change set, code-owned fields
(`facts`, `evidence`, use counters) from the latest version. `updated_tick` is
the commit tick, and the content hash is recomputed. No conflict is possible;
if one were found (a model-owned field changed after `base_version`), the
whole change set fails with reason `version` and the period goes to the
pending area.

**Cutoff.** Records that mechanical writes create after `base_version` (for
example an agreement a counterpart accepted while this resident slept) are
not inputs of this consolidation. They are ordinary records of the next
period and appear, as open commitments, in the next consolidation.

**Order at `s + K`.** In this order:

1. check the committed world boundary for death first, including at exact K:
   abandon and close without opening another period. For survivors at K,
   the change set is validated, rebased and committed (or the failure is
   recorded);
2. the period's working context is closed and moved to the audit; pending
   periods are updated (§5);
3. the new period starts; its working context opens when the resident wakes
   (decision-loop spec);
4. then the mechanical writes of the packet delivered at `s + K` (§1.4), which
   belong to the new period.

## 4. The window guard at consolidation

The decision loop's guard covers both consolidation calls (ADR 0013 D4, ADR
0012 D2). For consolidation it leaves content out in this fixed order until the
request fits the window with room for the response (owner, MF-D5):

1. Selected records beyond the mandatory ones, last selected first.
2. Pending periods, oldest first.
3. Day-log entries of the current period, oldest first.

**Never left out:** the instructions, the schema and its framing, the index,
open commitments, `needs_review` records, the records changed by mechanical
writes in the period, the frozen prefix/current state, and the omission notice when trimming. This is the minimum mandatory
request (P3.5 brief §11, request fit). The selection call has the same floor
without the selected and mechanical records.

- Day-log entries left out are not consolidated (ADR 0012 Q8). They stay in
  the audit's closed working context. The record lists them, with manifests
  before and after.
- **Request fit** follows the decision loop's pre-dispatch contract (§7.1
  there): the floor is measured on the actual request, notice included,
  before dispatch. The index has no fixed bound because open commitments have
  none (memory model §7). If the floor does not fit, the call is not
  dispatched; it gets a `stopped_unfit` call record with the measured floor,
  the reserve and the omitted parts; the consolidation is `failed` with that
  reason and stops the run as incomplete only at a surviving K boundary.
  Earlier wake or death through K abandons the workflow first (§7). The guard never drops a mandatory
  part, invents a summary or invokes the fallback policy to make a request
  fit.

## 5. Failure and the pending area

| Failure | Handling |
|---|---|
| Provider error or timeout on a call | Retried with the decision loop's classification and backoff, at most 3 retries per call (owner, MF-D6) |
| Output that does not parse as the schema | One retry with the same input; then the call fails |
| A call still fails | The consolidation fails: nothing is committed; the period still ends at `s + K` (ADR 0012 D5) |
| Ops fail validation | Only they and their dependents are dropped (§3.5); this is not a failed consolidation |

- **Pending area.** A failed consolidation's working context goes to the
  pending area (memory model §6), which the resident cannot reach. The next
  consolidation reads it together with the new period, oldest first (ADR
  0012 D5).
- **Which call consumes a pending period.** A pending period leaves the
  pending area only when a change set commits whose sent change-set input
  included that period in full. If the guard left it out of the change-set
  call (even when the selection call saw it), or the consolidation failed, it
  stays pending. Retries resend the same input, so they change nothing here.
- **Limit:** at most 2 pending periods (ADR 0012 Q5; owner, MF-D6). When a
  third would be added, the oldest pending period counts as forgotten and
  moves to the audit.
- The consolidation record lists, for each pending period, one state:
  `included` (consumed by this commit), `omitted` (left out by the guard,
  still pending), `retained` (still pending after a failure) or `evicted`
  (forgotten by the limit).
- Mechanical records are never lost, whatever happens to pending experience
  (§1).

## 6. The memory-off arm

At `s + K` the working context is closed and moved to the audit, with no
calls. The current intention is set to `reset` (memory model §9). The next
period starts with no earlier day log, no intention, no dialogue state, no
long-term memories in the prefix and recall that returns nothing (ADR 0014
D2; decision-loop spec §9). Mechanical writes continue.

## 7. Recording and replay

```text
ConsolidationRecord {
  record_schema:"mf/0.1", resident_id, period_id, arm:"on"|"off",
  s_tick:integer, started_tick:integer, boundary_tick:integer,
  outcome:"committed"|"failed"|"abandoned"|"off_arm",
  reason:string|null,                           // failed or abandoned: "provider", "parse", "stopped_unfit", "version", "woken", "death"
  base_version:integer, result_version:integer|null,
  selection_call_id:string|null, change_set_call_id:string|null,   // logical call records, decision-loop spec §10
  selection:SelectionOutput|null, change_set:ChangeSet|null,
  verdicts:array<{op_id, result:"committed"|"dropped", reason:string|null, depends_on:array<string>}>,
  relabel_flags:array<RelabelFlag>,             // inspection only (memory model §4.2)
  pending:array<{period_id, state:"included"|"omitted"|"retained"|"evicted"}>,
  pending_after:array<string>                   // period IDs still pending
}
RevisionRef { id:string, store_version:integer, content_hash:string }
RelabelFlag {
  flagged:RevisionRef,                          // the committed record that is not speech-derived
  overlaps:array<RevisionRef>,                  // live speech-derived records sharing a subject key, sorted by ID
  shared_keys:array<string>,                    // the overlapping subject keys, sorted
  store_version:integer, change_set_call_id:string
}
```

- `relabel_flags` are computed once, at commit, against the committed store,
  sorted by flagged ID; replay recomputes them and checks they match. They
  go to the audit with the verdicts (§3.5) and are not part of the store or
  the agent checkpoint; no context, recall or consolidation input is built
  from a consolidation record, so none can carry them (memory model §6).

- Both calls are logical calls of the decision loop's record model
  (decision-loop spec §10): one record per logical call with its kind
  (`consolidation_selection` or `consolidation_change_set`), its full and
  sent manifests, guard result and every dispatched attempt, including a
  call that was never dispatched (`stopped_unfit`) or abandoned. The
  consolidation record joins them by call ID.
- The record and the store version after commit are hashed, as P3 hashes a
  decision record. The selection output, the base version and the call
  records are part of the agent checkpoint, so a restore between selection
  and commit continues from the recorded state and gives the same result.
- Persist the frozen prefix, log/member cutoff, base revision, later packet
  cursor, wake/death disposition, stage (selection, change-set, ready or
  cancelled), both logical call IDs, prepared inputs, dispatch/terminal
  journal offsets and pending-period membership. Authorize logical stages
  in order from the frozen input, dispatch each attempt only after its
  durable preparation. Seal on early wake/death; dispatch no further
  attempt for a sealed workflow. A late terminal belongs to the audit only.
  At a surviving K wait for the applicable terminal, then commit/fail/stop
  exactly once. Timing of a provider reply or an unfit precheck never moves
  a stop ahead of that boundary. Restore from committed journal prefixes
  using DL §10.4 and the P3 interrupted-call rules.

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
| MF-02 | Agreement fact (§1.1): for A asleep and B accepting, A gets the commitment with `heard_counterpart = false` and no `told` source, B gets `told` for the proposal; a non-party gets nothing; in both arms. Check sent views by provenance: the agreement path leaks no raw event or speech IDs through records, gists or social facts; B may cite the same proposal ID independently delivered in speech. A gift received while asleep adds no `received` fact |
| MF-03 | Skill evidence from items in use: an own attempt whose `items_used` fit a skill's looks counts `matched_expected` or `other_outcomes`; a deceptive item that looks right fits; a by-kind input of 2 vine and 1 grass fits no "3 vine" look; a watched attempt with both `start` and `settle` counts `watched` and `watched_matched`; one seen only at start or only at settle counts nothing; a stop counts nothing; a refuted skill gets no evidence |
| MF-04 | Boundary: a 36-tick sleep chosen at 100 is confirmed at 101 and ends a period at 136; a faint first shown at 101 ends one at 137; a 35-tick sleep, a nap, and a 54-tick sleep woken at tick 20 do not; a sleep that fails to start starts nothing; death before `s + K` commits nothing |
| MF-05 | Timing: calls start at the confirming packet for a long sleep or a faint and never for a nap; the world runs while they are outstanding and the simulation waits at `s + K` when they are late; a woken sleeper's calls are recorded as abandoned |
| MF-06 | Change set: each op of §3.3 applies as specified on a fixture store, in listed order, with `new:<n>` refs; every forbidden cell of the authority table is refused with `authority` (an `add` of a commitment, a `merge` of skills, a skill `update` of its hypothesis, a `forget` of a social record, two `trait` ops for one trait) |
| MF-07 | Validator: one negative fixture per reason of §3.5, including a guessed ID the guard left out, a `told` source with the wrong speaker, an `inferred` source with another call's ID, an `innate` source, and an `update` of a record shown only as an index line; staged application: an invalid producer, its transitive dependents, an overflowing belief add that stages no eviction, and an independent valid op that commits; verdicts and reasons are in the record and the audit |
| MF-08 | Rebase (§3.6): a social update staged while a give changes the same record's facts commits with the new facts and the model's impression; a commitment created during the sleep is not an input and appears in the next period; the order at `s + K` puts the commit before that packet's mechanical writes; restored between selection and commit, the run commits the same version and hash |
| MF-09 | No hidden correction: a wrong but well-sourced belief is committed; the validator reads no world state (checked by injecting a world-state reader that fails when called) |
| MF-10 | Guard: an oversized consolidation request leaves out selected records, then pending periods, then the oldest entries; never a mandatory part; the record shows manifests before and after and the left-out entries |
| MF-11 | Failure: a call failing after 3 retries makes the consolidation fail; the period ends; its context goes to the pending area; a third failure in a row forgets the oldest pending period into the audit; mechanical records survive all of this |
| MF-12 | Memory off: no calls; the context closes at `s + K`; mechanical writes continue |
| MF-13 | Replay: a recorded run's stores are rebuilt from mechanical writes and change sets with zero model calls, with equal hashes at every version |
| MF-14 | A synthetic test memory kind registered by the memory model's extension point is consolidated by the same change-set ops (ADR 0014 D3) |
| MF-15 | Fallback (§1.3), run as model → fallback → model with a restore before acknowledgement: a fallback gather that fails after the model resumes, and a multi-tick fallback action ending later, write no day-log entry, no `items_used` and no skill evidence; a fallback turn carries no utterance; the resident's later perception of its inventory and needs is logged; another resident who watched the fallback action gets its observation |
| MF-16 | Pending periods (§5): a period left out of the change-set call by the guard stays pending as `omitted`; one included in a committed change set is `included` and leaves; a third pending period evicts the oldest as `evicted` |
| MF-17 | Unfit request: a change-set request whose floor exceeds the window is not dispatched; its call record is `stopped_unfit` with the measured floor; the consolidation fails with that reason; no provider and no fallback is used |
| MF-18 | A merged received portion counts once by giver and archetype. Failed, sleeping and out-of-sight cases add nothing. Receipt-only target and missing start look cannot support a skill; one-tick consumed material remains scorable. |
| MF-19 | Reject index-only successor, cycle, duplicate producer, unauthorized new-ref mutation and own repetition as observation. Protect later capacity targets; a dropped producer with a bad later operand gives depends_on first. Check rollback of flags, links and eviction. |
| MF-20 | Compat corpse sight and starter body feedback after confirmation enter only the journal/live period, survive short sleep and restore, and leave the fixed call bytes unchanged. Death at K abandons even with a ready result; equal-category writes have stable IDs. |
| MF-21 | Interrupt before dispatch, after selection and after change-set preparation: replay same prefix and disposition. Unfit floor before early wake is abandoned; surviving K records stopped_unfit without a world submission. |
| MF-22 | Resume model during and after fallback: current action visible, no rationale/result recall; an awake watcher with both phases may update its own skill. Exact packet and hypothesis revision identify the write. |
| MF-23 | Selection floor contains open/review records in full; change-set floor adds changed mechanical records. Recount framed floors including notice and restore an in-flight attempt at its journal cursor. |
| MF-24 | Observed witnesses (§3.5): B hears A say the spring is poisoned and never sees the spring; a belief about the spring citing A's `heard_speech` as `told` and B's hunger `body_change` as `observed`, at confidence 3, is refused with `provenance` (at 4 it would fail `format` first, which MF-25 tests); the same belief with only the `told` source commits at most at 3; when B's sent input holds an `observation` entry showing the spring tile, citing it as `observed` passes the witness test, but the record stays speech-derived and capped at 3 (MF-25). The check reads only B's delivered entries |
| MF-25 | Hearsay cap (§3.5, memory model §4.2): B hears "the spring is poisoned" and later sees the spring tile; the belief citing the `heard_speech` as `told` and the sighting as `observed` is accepted (the sighting witnesses the spring) but a confidence of 4 is refused, so it stays at most 3. Positive control: a belief "the cord snapped" written only from B's own `action_result` with `snaps` reaches 4. A new observed-only "the spring is poisoned" belief commits; the consolidation record and the exported `StoreInspection.relabel_flags` (evaluation spec §1) name its revision and the told belief's revision, and neither the flag nor that link appears in B's store, index or any serialized resident projection. Adding a `told` source to the cord belief at 4 fails `format`; lowering it to 3 in an earlier op lets the update commit. Commitment control: A's own delivered proposal gives an `observed` source keyed `spoke:<id>`, the unheard acceptance gives no `told` source, and no source comes from an event ID |

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
| The agreement fact (§1.1) and turn origins (§1.3) | `sim` (decision-loop spec, harness); evaluation |

## 12. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| MF-D1 | Do hard facts reach a party who did not perceive them? | Only the agreement: `sim` feeds each party an allowlisted agreement fact, to the memory writer only; its commitment record never claims the resident heard what it did not. Rework 1 derives give facts from the resident's own packets instead | Owner PR-D5 gives both parties a record; the fact is about the resident itself and never enters its context directly |
| MF-D2 | K | 36 ticks (6 hours) | A normal night consolidates; a nap or an interrupted sleep does not; equals the faint length |
| MF-D3 | When do consolidation calls start? | At the start of a sleep chosen at K or longer, or of a faint; the result is committed at `s + K` | The world keeps running while the model works; a nap costs no call |
| MF-D4 | The change-set schema | Nine closed ops: add, update, merge, supersede, confidence, review_done, forget, commitment_status, trait | Covers every change ADR 0012 D2 names, and nothing that touches hard facts |
| MF-D5 | Consolidation inputs that do not fit | Leave out extra selected records, then pending periods, then the oldest day-log entries; left-out entries are not consolidated; mandatory parts are never left out | Answers ADR 0012 Q8 without a model summary |
| MF-D6 | Retries and the pending limit | 3 retries per call, 1 parse retry, at most 2 pending periods | Bounded, and a failing provider cannot pile up unread days |
| MF-D7 | Selection limit | At most 60 records read per consolidation, beyond the mandatory ones | Bounds the call while leaving the model a real choice |
