# ADR 0011: Memory model

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-16.
- Baseline: `3f25930` (`task/P3.5-RR-01-world-adrs`).
- Phase: P3.5, system 5 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: the kinds of resident memory, their format, provenance, confidence,
  capacity and supersession, and the two carriers of memory (working context and
  long-term store). How memory is written is ADR 0012; how the working context
  is assembled is ADR 0013.
- Spec to be written: `docs/spec/memory-model-v0.1.md`.
- Supersedes on acceptance: `resident-experience-v0.1.md` for new work. P3
  `ExperienceRecord` capture becomes the day log of the working context.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
  D6 and the forgetting rule of D4 follow the owner's architecture discussion
  of 2026-11-16. D7 is a draft marked **Needs discussion**.

## Context

P3 gives each resident a bounded buffer of `ExperienceRecord` (1024 records,
1 MiB, oldest-first eviction), deterministic retrieval and one current
`GoalState`. P3.5 needs memory as the core of the agent: beliefs that can be
wrong, impressions of others, learned skills, commitments across days and a
personality. Memory stays resident-local, subjective and separate from the
objective event log.

## Decision

### D1. Memory kinds

| Kind | Holds | Capacity and forgetting |
|---|---|---|
| Episodic | Experiences that consolidation kept: important events, with their sources | Bounded; forgotten when a later consolidation drops them |
| Belief | Claims about the world, for example "fruit grows north" | Bounded; lowest confidence and least recently used first |
| Social | One impression per known resident: trust, debts, history | One record per resident |
| Skill | Structured rule hypotheses (D3) | Bounded; refuted hypotheses are demoted |
| Commitment | Promises to others or to oneself, with optional due time | Small set; archived when kept, broken or expired |
| Intention | An optional plan the resident chose to make (ADR 0013 D6) | Replaced by the resident |
| Personality | Stable traits | Fixed size; slow bounded drift (D5) |

The raw record of the current day is the working context (D6), not a memory
kind. Dialogue working state belongs to the decision loop (ADR 0013 D9).

### D2. Common envelope

Every long-term record carries `id`, `owner_id`, `kind`, `created_tick`,
`updated_tick`, `sources`, `confidence`, `last_used_tick`, an optional
`supersedes` reference, and its content: structured fields, natural-language
text, or both. All values are strings or integers.

### D3. Skills are structured hypotheses

**[Owner]** A skill has the same shape as a world rule (ADR 0008 D3): verb,
instrument and input slot predicates, target predicate, and the expected
phenomenon, plus success and failure counts. It is the resident's guess, never
the true rule. It may be incomplete or wrong, for example when taught by a liar.
Teaching passes this structure; evaluation compares it with the true rules
(ADR 0014).

**[Owner]** Skill predicates are written in what the resident can perceive: the
coarse descriptors of apparent values (ADR 0007 D4), for example "looks very
hard, sharp edge", never true integer values such as `hardness_min = 4`. A
resident can then apply a skill to a new item it sees, and can be fooled by a
deceptive appearance, as intended. Mechanical evidence counting (ADR 0012 D1)
matches attempts against the descriptors the resident was shown. Evaluation
maps descriptor predicates to true property ranges when it compares skills with
rules; that mapping exists only in `analysis`.

### D4. Provenance, confidence, supersession and forgetting

- Sources: `observed` (day-log entry IDs), `told` (utterance ID and speaker),
  `inferred` (memory IDs and the consolidation call that produced it), `innate`.
- Confidence is an integer level 0–4. The default depends on the source:
  observed is high; told depends on the resident's trust in the speaker.
- **[Owner]** Residents may lie. The world never checks the truth of speech, so
  told memories rely on trust, and trust is updated when a told claim is
  contradicted by observation.
- A new record that contradicts an old one supersedes it. The old record stays
  as history the resident can still recall ("I used to think the north tree had
  fruit"). Records derived from it are marked `needs_review`, not deleted, and
  are resolved at the next consolidation (ADR 0012).
- **[Owner]** Forgetting is not supersession. A forgotten record is removed from
  the long-term store, and the resident can no longer retrieve it. The audit
  records keep it for replay and evaluation only.
- **[Owner]** A resident may keep beliefs that are wrong. Nothing corrects them
  from hidden truth (ADR 0012 D2).

### D5. Personality

**[Owner]** Personality changes slowly within bounds. Each trait has a base value
and a drift range; a consolidation may move a trait by at most one step, and
never outside its range. Every change cites the experiences that caused it.

### D6. Two carriers, plus the audit

**[Owner]** Memory has two carriers. The objective audit is separate and is not
memory.

| Carrier | Holds | Lifetime |
|---|---|---|
| Working context | The current waking period: fixed prefix, day log, current state (ADR 0013 D4) | From waking to loss of consciousness; closed after consolidation |
| Long-term store | The seven kinds of D1, as structured records (D2) | Across sleeps; changed by mechanical writes and consolidation (ADR 0012) |
| Audit (not memory) | Objective event log, recorded model calls, closed working contexts, forgotten records | The whole run; for developers, replay and evaluation |

- The working context is the main source of the resident's thinking during the
  day. It is not long-term memory and is not kept as such.
- The long-term store supports recall, adding, merging, revision, confidence
  changes and forgetting. It is a set of typed records, not one free-text file.
- **[Owner]** A resident can never reach the audit through memory: not world
  truth, not a closed working context, not a forgotten record.

### D7. Formation per kind

> **Needs discussion (owner, 2026-11-16).** Draft for the dedicated memory
> discussion; it links this ADR with ADR 0012 and ADR 0013 D5.

| Kind | During the day (mechanical, ADR 0012 D1) | At consolidation (model, ADR 0012 D2) | Recalled when (ADR 0013 D5) |
|---|---|---|---|
| Episodic | None; the day log holds the day | Keep important experiences; abstract repeated ones into beliefs or skills | By recall recipe |
| Belief | None | Add, revise, change confidence | By recall recipe |
| Social | Counters (who gave what to whom) | Update impression and trust | The resident meets or hears the person |
| Skill | Evidence counts from attempts and phenomena | Create or refine hypotheses | The verb is used or considered |
| Commitment | Written when accepted in dialogue | Mark kept, broken or expired | The other party is present, or the due time is near |
| Intention | Written by the resident at any turn | Kept or dropped | Shown at every turn |
| Personality | None | At most one step per trait | Fixed prefix |

## Consequences

- Memory becomes several typed stores with one envelope, instead of one buffer.
- The day's raw experience lives only in the working context; the long-term
  store holds what consolidation chose to keep. P3's oldest-first eviction of
  raw records has no counterpart.
- Skills and rules share a vocabulary, so changes to ADR 0008 vocabularies
  affect memory. Skills use the descriptor side of each property, so the
  descriptor bands of the vocabulary are part of the memory contract too.
- Supersession chains and `needs_review` add bookkeeping but keep the
  resident's history inspectable.
- Closed working contexts and forgotten records must be stored for the audit,
  but behind an interface that memory recall cannot reach.

## Open questions

| ID | Question |
|---|---|
| Q1 | Capacity of each kind. |
| Q2 | The initial personality trait set and drift ranges. |
| Q3 | How trust maps to the default confidence of told claims. |
| Q4 | Is a commitment to oneself the same kind as an intention, or separate? |
| Q5 | Formation per kind (D7): confirm or change the draft table. |
