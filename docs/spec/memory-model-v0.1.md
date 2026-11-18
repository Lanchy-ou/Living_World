# Living Island — Memory Model v0.1 (P3.5)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §13 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
> Rework 1 (2026-11-18) answers the Gate 2 resident-track review
> ([review](../tasks/p3.5/P3.5-SP-01-review-agent.md) B01, B04, B08, B10,
> N01, N03) and uses the protocol as amended by CR-010.
>
> Implements [ADR 0011](../adr/0011-memory-model.md). When frozen, it
> supersedes `resident-experience-v0.1.md` for new work; P3 experience capture
> becomes the day log of the working context (decision-loop spec). How records
> are written is the [memory-formation](memory-formation-v0.1.md) spec; how they
> enter a context is the [decision-loop](decision-loop-v0.1.md) spec.

## 0. Scope

### 0.1 Covered here

- The long-term store of each resident: record IDs, the common envelope, the
  content of each of the seven kinds (ADR 0011 D1–D3).
- Sources, confidence, supersession, `needs_review`, merging and forgetting
  (D4).
- Personality traits and drift (D5).
- The two carriers and the audit, and how the audit is kept out of a
  resident's reach (D6).
- Capacities (Q1), the memory index line, store versions and persistence.

### 0.2 Owned elsewhere

| Subject | Spec |
|---|---|
| Mechanical writes, the change set, its validator, consolidation, retries and the pending area | `memory-formation-v0.1.md` |
| The working context and its day log, recall, strength, the memory-off boundary as applied to contexts | `decision-loop-v0.1.md` |
| Metrics over memory | `evaluation-v0.1.md` |

### 0.3 Principles kept

- Memory is resident-local and subjective. The world never reads it and never
  corrects it from hidden truth (AGENTS.md principle 4; ADR 0011 D4).
- Records hold only what the resident perceived, was told or concluded. They
  never hold true property values, rule IDs, settlement kinds or anything else
  the protocol keeps from residents (protocol §5.1).

## 1. The store

- Each resident has one long-term store. It lives in `agents`/`memory` and
  never imports from `world` beyond the protocol module (AGENTS.md).
- **Record IDs** are `m:<resident_id>:<n>`, `n` counting the resident's records
  from 1, never reused, so a merged or forgotten ID never returns.
- **Store version.** An integer that starts at 0 and increases by one with
  every committed change. There are three kinds: a mechanical write, a use
  update (the `last_used_tick` and `use_count` changes of one context
  assembly, as one batch), and a committed change set. A change set names the
  version it was built from (memory-formation spec).
- Records are stored by content hash, once (ADR 0013 D10). A record's content
  hash is the SHA-256 of the canonical encoding of the record without
  `last_used_tick` and `use_count`, which change on use.
- All values are strings, integers, booleans, `null`, or arrays and objects of
  them, and never floats. ADR 0011 D2 says strings or integers; booleans
  (such as `needs_review`) and `null` for absent values are the only
  additions. This is a declared variance from the letter of D2, for typed
  flags and absent values; `false` and `null` mean different things and are
  never interchanged. The owner confirms it with the freeze (decision sheet).

## 2. The common envelope

```text
MemoryRecord {
  id:string, owner_id:string, kind:MemoryKind,
  created_tick:integer, updated_tick:integer,
  about_tick:{from:integer,to:integer}|null,   // the time the content describes (D2, D4)
  sources:array<Source>,                       // sorted (§4.1); at least one, except commitments (§3.5)
  confidence:integer,                          // 0..4
  last_used_tick:integer|null, use_count:integer,
  supersedes:string|null,                      // the record this one replaced
  superseded_by:string|null,                   // set when a later record replaces this one
  needs_review:boolean,
  gist:string,                                 // one line for the index (owner, ADR 0011 D2)
  text:string|null,                            // natural-language content
  content:object{}                             // the kind's structured fields (§3)
}
MemoryKind = "episodic"|"belief"|"social"|"skill"|"commitment"|"intention"|"personality"
```

- `gist` is at most 160 characters and holds no newline. Consolidation writes
  it whenever it creates or changes a record; code writes it for mechanical
  records from a fixed template (memory-formation spec).
- `text` is at most 2000 characters.
- `about_tick` is required on episodic records and on beliefs that describe a
  dated observation; it is `null` for stable knowledge (§4.3).
- A record is **history** when `superseded_by` is set, or, for an intention,
  when its `state` is not `current` (§3.6). History stays in the store, can be
  recalled as what the resident used to think, and is shown in the index
  marked as superseded. A record is **live** otherwise.
- A commitment whose status is not `open` is **archived** (ADR 0011 D1): it
  stays in the store and is never removed, but it leaves the index, the prefix
  and recall. Evaluation and inspection still read it.

### 2.1 The index line

The index lists one line per record in the store except archived commitments
(ADR 0012 D2), sorted by ID:

```text
<id> | <kind> | c<confidence> | <flags> | <gist>
```

`flags` is a sorted, comma-separated subset of `superseded`, `needs_review`,
`open` (an open commitment), or `-`. For example:
`m:ella:42 | belief | c3 | - | Fruit grows on the tree north of the cave`.

## 3. The kinds

| Kind | `content` fields | Written by |
|---|---|---|
| `episodic` | `participants:array<string>` (resident IDs), `place:Coord|null` | Consolidation |
| `belief` | `subject:{kind:"place"|"entity"|"resident"|"kind_of_thing"|"general", ref:string|null}`, `stance:"stable"|"dated"|"guess"`, `topics:array<Topic>` | Consolidation |
| `social` | `about:string` (resident ID), `trust:integer` (0–4), `impression:string`, `facts:SocialFacts` | Facts by code; the rest by consolidation |
| `skill` | `hypothesis:SkillHypothesis`, `evidence:SkillEvidence`, `status:"active"|"doubtful"|"refuted"` | Evidence by code; the rest by consolidation |
| `commitment` | `agreement_id`, `role:"promisor"|"promisee"`, `counterpart_id`, `terms:Terms`, `due_tick:integer|null`, `heard_counterpart:boolean`, `status:"open"|"kept"|"broken"|"expired"`, `status_note:string|null` | Code; status by consolidation |
| `intention` | `set_turn:string` (the turn ID that set it), `state:"current"|"replaced"|"cleared"|"reset"`, `ended_turn:string|null` | The resident at a turn; `reset` by code (§9) |
| `personality` | `traits:array<Trait>` | Code at start; drift by consolidation |

### 3.1 Episodic

An experience the resident decided to keep: "Mia gave me two fruits by the
spring", with `about_tick`, participants and place. Repeated experiences are
abstracted into beliefs or skills by consolidation rather than kept one by one
(ADR 0011 D7).

### 3.2 Belief

A claim about the world. `stance` keeps three things apart (ADR 0011 D4):

| Stance | Example | `about_tick` |
|---|---|---|
| `stable` | The north tree bears fruit | `null` |
| `dated` | There were two fruits on the north tree at noon on day 2 | Required |
| `guess` | There may still be fruit there | Optional; source is `inferred` |

A later `dated` belief that differs from an earlier one is a change in the
world, not a contradiction; both stay (ADR 0011 D4).

`topics` is a sorted subset of `food`, `water`, `shelter`, `tools`,
`materials`, `people`, `danger` and `other`, chosen by consolidation. Recall
recipes use it, for example "known food and water beliefs" (decision-loop
spec). `subject.ref` is a place as `"x,y"`, an entity ID, a resident ID or an
archetype ID, as `subject.kind` says.

### 3.3 Social

One record per resident that this resident knows (ADR 0011 D1), created when
the other is first seen or heard.

```text
SocialFacts {                     // hard facts, written by code only (ADR 0012 D1)
  given:array<{archetype_id:string, quantity:integer}>,     // this resident gave to the other
  received:array<{archetype_id:string, quantity:integer}>,  // the other gave to this resident
  agreements:array<string>,       // agreement IDs between the two
  last_seen_tick:integer|null, last_heard_tick:integer|null
}
```

- `given` and `received` count successful `give` transfers between the two,
  by archetype, sorted, **as this resident perceived them** (memory formation
  §1.1): `given` from its own `give` feedback, `received` from the giver's
  `give` it watched settle. A gift received while asleep is not counted, as
  the resident did not see who gave it. Objective transfers stay in the event
  log for evaluation.
- `trust` (0–4) and `impression` are the resident's own view, changed only by
  consolidation. A new social record starts with `trust = 2` and an empty
  impression.

### 3.4 Skill

A structured guess with the shape of a rule (ADR 0011 D3, ADR 0008 D3),
written in what the resident perceives:

```text
SkillHypothesis {
  verb:string,
  target:Look|null,
  instruments:array<Look>,
  inputs:array<{look:Look, quantity:integer}>,
  circumstances:string|null,      // free text, e.g. "near a fire", "when not tired"
  expected:array<string>          // phenomenon IDs the resident expects
}
Look {                            // what something looks like, never true values
  archetype_id:string|null, material_id:string|null,
  descriptors:array<{property_id:string, word:string}>   // sorted by property ID
}
SkillEvidence {                   // written by code only (ADR 0012 D1)
  attempts:integer, matched_expected:integer, other_outcomes:integer,
  watched:integer, watched_matched:integer, last_attempt_tick:integer|null
}
```

- The hypothesis of a skill record never changes after it is created. A
  revised hypothesis is a new skill record that supersedes the old one, with
  evidence starting at zero, so evidence always belongs to the hypothesis it
  was counted for; the old record keeps its counts as history. Evidence is
  never merged.

- `Look` uses archetype and material IDs and descriptor words, the things a
  resident sees (protocol §5.1). For example, "a sharp flint flake bound with
  sturdy cord to a long piece of wood makes an axe". It never uses integers or
  true values (ADR 0011 D3).
- **Evidence** is counted by code (memory formation §1.2): an own attempt with
  this verb whose items fit every `Look` of the hypothesis counts in
  `attempts`, then in `matched_expected` if the delivered phenomena include
  all of `expected`, else in `other_outcomes`. A watched attempt that fits
  counts in `watched`, and in `watched_matched` if the watcher-visible
  phenomena include all of `expected`. Matching reads the looks the resident
  was shown, so a deceptive item can fool it, as intended.
- `status` is set by consolidation: `doubtful` or `refuted` when evidence goes
  against the hypothesis (ADR 0011 D1: refuted hypotheses are demoted). A
  refuted skill is kept as history; it is not recalled by recipe.
- A skill taught by another reaches the listener as heard words; consolidation
  may turn it into a hypothesis with a `told` source (ADR 0011 D3).

### 3.5 Commitment

Written by code when an agreement with structured terms is accepted (ADR 0007
D10, protocol §7.2), one record for each party (owner, PR-D5). `terms` is the
protocol's `Terms`. Consolidation may set `status` and `status_note`, and
nothing else; it may never remove the record (ADR 0012 D1).

- **Basis and sources.** The record's basis is the agreement itself
  (`agreement_id`), a hard fact the world registered; it is not a claim the
  resident heard. Its `sources` hold only what the resident actually
  perceived of the agreement: `observed` for its own proposal or acceptance
  (its own utterance feedback), and `told` for the counterpart's utterance
  only if that utterance was delivered to this resident. So a proposer who
  slept through the acceptance has `heard_counterpart = false` and no `told`
  source; `sources` may then hold only its own proposal, or be empty when
  that is not in its day log either. A commitment is the one kind that may
  have empty `sources`.
- The code template for its gist says when the answer was not heard, for
  example `Mia agreed to give me 2 fruit by tick 300 (I did not hear her
  answer)`.

- **A commitment to oneself is an intention** (ADR 0011 Q4; owner, MM-D4). The
  `commitment` kind holds only accepted agreements, so every commitment can be
  checked against objective events (ADR 0014 D2).
- A commitment is `open` until consolidation marks it otherwise; then it is
  archived (§2). Its status in memory is the resident's view; evaluation
  judges keeping from objective events, never from this field.

### 3.6 Intention

At most one intention per resident has `state = "current"`. Only the resident
changes it, at a turn (ADR 0013 D6), and code at an off-arm period boundary
(§9); consolidation never does (memory formation §3.3).

| Turn or event | Old current intention | New record |
|---|---|---|
| Sets an intention | `state = "replaced"`, `superseded_by` the new one, `ended_turn` | `state = "current"` |
| Clears it | `state = "cleared"`, `superseded_by = null`, `ended_turn` | None |
| Off-arm period boundary | `state = "reset"`, `ended_turn = null` | None |

History is every intention whose `state` is not `current`, so clearing without
a successor never leaves an old intention looking current. The text is the
resident's own words, unchanged.

### 3.7 Personality

One record per resident, written at run start from the resident's profile.

```text
Trait { trait_id:string, base:integer, value:integer, min:integer, max:integer, changes:array<TraitChange> }
TraitChange { tick:integer, from:integer, to:integer, sources:array<Source> }
```

- The trait set (ADR 0011 Q2; owner, MM-D2): `curiosity`, `caution`,
  `sociability`, `trustfulness`, `diligence`, each on 0–4.
- `min = max(0, base − 1)` and `max = min(4, base + 1)`: each trait may drift
  one step either way from its base.
- A consolidation may move a trait by at most one step, within `min..max`, and
  the change must cite its sources (ADR 0011 D5).
- Base values come from the profile (`content/characters/<profile>.json`,
  profile schema 0.2, which adds `traits`). The three existing profiles get:

  | Profile | curiosity | caution | sociability | trustfulness | diligence |
  |---|---|---|---|---|---|
  | `explorer` | 4 | 1 | 2 | 2 | 2 |
  | `cautious` | 1 | 4 | 1 | 1 | 3 |
  | `cooperative` | 2 | 2 | 4 | 3 | 2 |

  The M15 runs need five residents; their two further profiles are content
  for the M14 task cards, with the same five traits.

## 4. Sources and confidence

### 4.1 Sources

```text
Source = {kind:"observed", entry_id:string}                     // a day-log entry of own perception
       | {kind:"told", utterance_id:string, speaker_id:string}  // heard speech
       | {kind:"inferred", memory_ids:array<string>, call_id:string}  // a consolidation conclusion
       | {kind:"innate"}                                         // run-start records
```

- Sources are sorted by kind in the order above, then by their IDs.
- **No relabelling** (ADR 0011 D4). A source is never changed into another
  kind. A record built from speech keeps its `told` source however firmly it
  is believed; it gains an `observed` source only when the resident sees for
  itself, citing that entry. The formation validator enforces this
  (memory-formation spec).
- An `observed` source cites a day-log entry whose type is one of the resident's
  own perceptions (decision-loop spec), never a `heard_speech` entry. The
  feedback on the resident's own utterance is its own perception: it knows
  what it said.
- A `told` source cites an utterance that was delivered to this resident, in a
  `heard_speech` entry, with that entry's speaker. Nothing else makes a
  source `told`: not an agreement record, not another resident's report of
  what was said, not a fallback action (memory formation §1.3).
- An `innate` source is written only by code at run start. A change set can
  never create one.
- A merged record keeps every source of every record it merges (ADR 0011 D4).

### 4.2 Confidence

An integer 0–4: 0 doubt, 1 low, 2 moderate, 3 high, 4 certain.

| Source of a new record | Default confidence |
|---|---|
| `observed` only | 3 |
| `told` only | From the speaker's trust: trust 0 → 0, 1 → 1, 2 → 1, 3 → 2, 4 → 3 (ADR 0011 Q3; owner, MM-D3) |
| `inferred` | At most the lowest confidence among the records it cites |
| `innate` | 4 |
| Several kinds | The highest default among them |

- Consolidation may change confidence, one change operation at a time, within
  a cap: a record without an `observed` or `innate` source never exceeds 3. A
  resident may fully believe what it was told, but certainty needs its own
  eyes.
- Trust in a speaker falls only when a claim is contradicted at the time it
  describes, never because the world changed later (ADR 0011 D4). That is a
  consolidation judgement; the formation guidance says so.

### 4.3 Time

`created_tick` is when the record was written; `about_tick` is when its
content was true. "I saw two fruits there yesterday" written tonight has
`created_tick` tonight and `about_tick` yesterday.

## 5. Supersession, review, merging and forgetting

| Change | What happens to the old record | Recall |
|---|---|---|
| **Supersede**: a new record contradicts an old one | Old gets `superseded_by`; new gets `supersedes`. Records whose `inferred` sources cite the old one get `needs_review = true` | The old record is history: recallable, shown as what the resident used to think |
| **Merge**: several records become one | The merged records get `superseded_by` the merged record, which keeps all their sources | As for supersede |
| **Forget** | The record leaves the store and goes to the audit (§6) | Never again |

- `needs_review` records are always shown to the next consolidation (ADR 0012
  D2) and are resolved there: confirmed (flag cleared), revised, superseded or
  forgotten.
- Forgetting is not supersession (ADR 0011 D4). A forgotten record can be
  reached by no recall, no index and no context in any form (D6).
- Mechanical records cannot be forgotten, superseded or merged, directly or
  by capacity: commitments and social records (ADR 0012 D1). The `evidence` of
  a skill is code-owned: a skill record may be superseded or forgotten (its
  hypothesis is the resident's), and its evidence then stays in the audit's
  mechanical log for inspection; the resident no longer sees it. Skills are
  never merged (§3.4).
- Personality is never forgotten or superseded; it drifts (§3.7).
- Which operation may touch which kind and field is the authority table of
  memory formation §3.3.

## 6. Carriers and the audit

| Carrier | Holds | Reached by the resident |
|---|---|---|
| Working context | The waking period: prefix, day log, current state (decision-loop spec) | Yes, until it is closed |
| Long-term store | The records of §2–§5 | Yes, through the prefix, recall and the consolidation index |
| Pending area | Working contexts of periods whose consolidation failed, at most 2 (memory formation §5) | Only as input to its own next consolidation |
| Audit | Closed working contexts, forgotten records and pending periods, the mechanical log, every model call, dropped change-set operations, the objective event log | Never |

- **The audit is out of reach by construction** (ADR 0011 D6). The audit
  lives behind its own interface in `persistence`. The modules that assemble
  contexts, run recall and run consolidation have no import path to it; an
  import-linter contract enforces this (`agents` and `memory` may not import
  the audit module). Only `analysis` and replay read it.
- The first version has no retrieval of the audit in any form, including
  recall of a forgotten experience (ADR 0011 D6).
- The pending area is resident-local and lives with the store in `memory`, not
  in the audit. Only the consolidation input builder reads it (ADR 0012 D5). A
  pending period that is forgotten moves to the audit and is then out of
  reach like any audit content.

## 7. Capacities

Capacities bound each kind after every committed change (ADR 0011 Q1; owner,
MM-D1). Mechanical writes are never refused. When a change set would leave a
kind above capacity, the rule of ADR 0011 D1 for that kind applies:

- **Episodic**: the excess `add` and `merge` operations are dropped by the
  validator, in listed order (episodic memories are forgotten only when a
  consolidation drops them).
- **Belief**: code forgets live beliefs to make room, lowest confidence first,
  then least recently used (`last_used_tick`, never-used first), then lowest
  ID, skipping beliefs the change set itself adds or changes. The forgotten
  beliefs go to the audit like any forgotten record.
- **Skill**: code forgets `refuted` skills first, oldest first; if that is not
  enough, the excess adds are dropped.
- Other kinds have no overflow: `social` and `commitment` have no limit, and
  a new intention replaces the current one.
- **History beyond its bound** goes to the audit oldest first, as a forget
  does. For a skill, its evidence stays in the mechanical log.
- Capacity rules never touch commitments, social records or personality.

| Kind | Capacity (live records, history excluded) | History |
|---|---|---|
| `episodic` | 300 | Superseded and merged records: at most 300 more; beyond that the oldest history goes to the audit |
| `belief` | 200 | Same rule, 200 |
| `social` | One per known resident | Not superseded |
| `skill` | 80 | Same rule, 80 |
| `commitment` | No limit | Never removed |
| `intention` | 1 | Up to 20 earlier intentions as history |
| `personality` | 1 | Not superseded |

With the soft target of 5–15 episodic memories per consolidation (ADR 0012
D2), seven game days fill under 110 episodic records; the capacities leave room
for longer runs while bounding the index.

**Index size.** The index holds at most `(300 + 300) + (200 + 200) + (80 + 80)
= 1160` episodic, belief and skill lines, 21 intention lines, 1 personality
line, one social line per other resident, and one line per open commitment.
Open commitments have no fixed bound, so the index has none either; the
decision loop measures each request instead and stops a run that cannot fit
(decision-loop spec §7.1). An index line is at most 220 characters (ID, kind,
confidence, flags and a 160-character gist).

## 8. Persistence and replay

- A save package holds each resident's store, its version and its index
  inputs, in canonical encoding, records sorted by ID.
- Replay rebuilds the store from the recorded mechanical writes and committed
  change sets, with no model call (ADR 0012 D5), and checks the store hash at
  each committed version.
- `last_used_tick` and `use_count` change when a record is used in a context
  (decision-loop spec). These updates are deterministic and are replayed from
  the recorded manifests.

## 9. The memory-off arm

In the memory-off arm (ADR 0014 D2) the store still receives mechanical writes,
for evaluation, but nothing from it reaches the resident: no prefix records,
no recall, no consolidation index. No consolidation runs, so the store holds
only mechanical records, intentions and the personality record with its base
values. The decision-loop spec applies the period boundary.

- **One exception within a period.** The current intention is set and read
  within a waking period in both arms, because it is part of the working
  context (ADR 0013 D6). A nap does not end the period, so it survives a nap.
- **At the period boundary** code sets the current intention, if any, to
  `state = "reset"` (§3.6). Nothing the store holds is read again in that arm.
  The mechanical records stay for evaluation and inspection.

## 10. The extension point

A new memory kind is added by registering:

- its `content` schema and capacity;
- its index flags, if any;
- its recall recipes (decision-loop spec) and the change-set operations
  allowed on it (memory-formation spec).

No assembler, store or validator code changes. ADR 0014 D3's synthetic test
adds a test kind this way (M14 evidence).

## 11. Acceptance tests

| ID | Test |
|---|---|
| MM-01 | Envelope: every record has the §2 fields with valid types and ranges; a record other than a commitment with an empty `sources`, a gist over 160 characters or a newline, or a confidence outside 0–4 is refused; `false` and `null` are kept distinct |
| MM-02 | IDs: record IDs count from 1 per resident and are never reused after a merge or a forget |
| MM-03 | Store version increases by one per mechanical write and per committed change set |
| MM-04 | Index lines: format, sort order and flags, for a superseded, a `needs_review` and an open commitment record |
| MM-05 | Looks: a skill hypothesis built from perceived descriptors stores archetype, material and words only; a hypothesis carrying an integer property value is refused |
| MM-06 | Default confidence for each source kind and each trust level; a told-only record cannot be raised above 3; gaining an observed source lifts the cap |
| MM-07 | No relabelling: a change that turns a `told` source into `observed`, or adds an `observed` source citing a `heard_speech` entry, is refused |
| MM-08 | Supersession: the old record gains `superseded_by`, stays recallable as history, and records inferred from it get `needs_review` |
| MM-09 | Merge keeps the union of sources; forgetting moves the record to the audit, and no recall, index or context reaches it afterwards |
| MM-10 | Mechanical records: a forget or change of a commitment's terms, a social record's facts or a skill's evidence is refused; a status change of a commitment is accepted |
| MM-11 | Personality: base values from the profile; a change of two steps, or outside `min..max`, or without sources, is refused |
| MM-12 | Capacities: an episodic `add` beyond capacity is dropped; a belief beyond capacity forgets the lowest-confidence, least recently used belief; a skill beyond capacity forgets a refuted skill first; history beyond its bound moves to the audit oldest first; mechanical writes are never refused |
| MM-13 | Audit isolation: the import-linter contract fails when context, recall or consolidation code imports the audit module |
| MM-14 | Replay: rebuilding a store from recorded writes and change sets gives the same hash at every version, with no model call |
| MM-15 | Memory off: mechanical records are written; the prefix, recall and index return nothing; the personality stays at base |
| MM-16 | Extension: a registered test kind is stored, consolidated and assembled with no change to store, validator or assembler code (ADR 0014 D3) |
| MM-17 | Commitment sources: A proposes, falls asleep, B accepts in hearing range; A's record has `heard_counterpart = false`, an `observed` source for its own proposal and no `told` source; B's has `observed` for its acceptance and `told` for A's proposal; the gists follow the template |
| MM-18 | Intentions: setting replaces with `replaced`; clearing with no successor gives `cleared` and no current intention; an off-arm boundary gives `reset`; a history reader never returns a non-current intention as current |
| MM-19 | Archive: a commitment marked `kept` leaves the index, prefix and recall, stays in the store and is read by evaluation |
| MM-20 | Skills: a revised hypothesis is a new record superseding the old, with zero evidence; the old keeps its counts; a merge of two skills is refused |

## 12. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0011 Q1 Capacities | §7, owner MM-D1 |
| ADR 0011 Q2 Traits and drift | §3.7, owner MM-D2 |
| ADR 0011 Q3 Trust to confidence | §4.2, owner MM-D3 |
| ADR 0011 Q4 Self-commitment | It is an intention, owner MM-D4 (§3.5) |
| ADR 0012 Q4 Capacities per kind | §7 (with memory-formation for the episodic target) |
| ADR 0012 Q6 Retention rules per kind | §5, §7; the change-set schema is memory-formation's |

## 13. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| MM-D1 | Capacity of each kind | Episodic 300, belief 200, skill 80, social one per known resident, commitment unlimited, intention 1; history bounded per kind. At capacity, episodic adds are dropped, beliefs give way lowest confidence and least recently used first, skills give way refuted first (ADR 0011 D1) | A week fills less than half; the index stays readable for consolidation |
| MM-D2 | Personality traits and drift | Five traits on 0–4 (curiosity, caution, sociability, trustfulness, diligence), drift one step from base | Few enough to read in the prefix, enough to tell the three profiles apart |
| MM-D3 | Trust to default confidence of told claims | Trust 0 → 0, 1–2 → 1, 3 → 2, 4 → 3 | Hearsay starts below what one saw; full trust still falls short of certainty |
| MM-D4 | Is a commitment to oneself a commitment? | No, it is an intention; commitments are accepted agreements only | Every commitment can then be judged from objective events |
| MM-D5 | Confidence cap for hearsay | A record with no observed or innate source never exceeds 3 | A resident may believe a liar fully, but never be certain without seeing |
