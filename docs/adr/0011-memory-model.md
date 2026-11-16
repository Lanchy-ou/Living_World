# ADR 0011: Memory model

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-16.
- Baseline: `3f25930` (`task/P3.5-RR-01-world-adrs`).
- Phase: P3.5, system 5 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: the kinds of resident memory, their format, provenance, confidence,
  capacity and supersession. How memory is written is ADR 0012; how it is
  selected for a decision is ADR 0013.
- Spec to be written: `docs/spec/memory-model-v0.1.md`.
- Supersedes on acceptance: `resident-experience-v0.1.md` for new work. P3
  `ExperienceRecord` becomes the episodic kind below.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.

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
| Episodic | Raw own experience (P3 `ExperienceRecord`) | Bounded; raw records may be evicted once compacted (ADR 0012) |
| Belief | Claims about the world, for example "fruit grows north" | Bounded; lowest confidence and least recently used first |
| Social | One impression per known resident: trust, debts, history | One record per resident |
| Skill | Structured rule hypotheses (D3) | Bounded; refuted hypotheses are demoted |
| Commitment | Promises to others or to oneself, with optional due time | Small set; archived when kept, broken or expired |
| Intention | An optional plan the resident chose to make (ADR 0013 D3) | Replaced by the resident |
| Personality | Stable traits | Fixed size; slow bounded drift (D5) |

Dialogue working memory belongs to the decision loop (ADR 0013), not to
long-term memory.

### D2. Common envelope

Every non-episodic record carries `id`, `owner_id`, `kind`, `created_tick`,
`updated_tick`, `sources`, `confidence`, `last_used_tick` and an optional
`supersedes` reference. All values are strings or integers.

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

### D4. Provenance, confidence and supersession

- Sources: `observed` (episodic record IDs), `told` (utterance ID and speaker),
  `inferred` (memory IDs and the formation call that produced it), `innate`.
- Confidence is an integer level 0–4. The default depends on the source:
  observed is high; told depends on the resident's trust in the speaker.
- **[Owner]** Residents may lie. The world never checks the truth of speech, so
  told memories rely on trust, and trust is updated when a told claim is
  contradicted by observation.
- A new record that contradicts an old one supersedes it. The old record stays
  as history. Records derived from it are marked `needs_review`, not deleted,
  and are resolved at the next compaction (ADR 0012).

### D5. Personality

**[Owner]** Personality changes slowly within bounds. Each trait has a base value
and a drift range; a compaction may move a trait by at most one step, and never
outside its range. Every change cites the experiences that caused it.

## Consequences

- Memory becomes several typed stores with one envelope, instead of one buffer.
- Skills and rules share a vocabulary, so changes to ADR 0008 vocabularies
  affect memory. Skills use the descriptor side of each property, so the
  descriptor bands of the vocabulary are part of the memory contract too.
- Supersession chains and `needs_review` add bookkeeping but keep the
  resident's history inspectable.

## Open questions

| ID | Question |
|---|---|
| Q1 | Capacity of each kind. |
| Q2 | The initial personality trait set and drift ranges. |
| Q3 | How trust maps to the default confidence of told claims. |
| Q4 | Is a commitment to oneself the same kind as an intention, or separate? |
