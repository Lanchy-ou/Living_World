# ADR 0012: Memory formation

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-16.
- Baseline: `3f25930` (`task/P3.5-RR-01-world-adrs`).
- Phase: P3.5, system 6 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: which memories are written mechanically, which are produced by an LLM,
  when that happens, and how it is recorded and replayed. Memory kinds are
  ADR 0011; the daytime context is ADR 0013.
- Spec to be written: `docs/spec/memory-formation-v0.1.md`.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
- D2 is marked **Needs discussion**: not ready for acceptance.

## Context

ADR 0011 defines typed memory stores. Something must fill them. Raw experience
can be captured mechanically, as P3 already does. Summaries, beliefs from
hearsay, generalized skills, impressions and personality drift need
interpretation by a model. That interpretation must not invent facts, must be
recorded and must replay without new model calls.

## Decision

### D1. Mechanical writes

Done at every boundary, with no model call:

- episodic capture (unchanged from P3);
- skill evidence counts from attempts and observed phenomena;
- a commitment when the resident accepts a request in dialogue;
- social fact counters (who gave what to whom).

### D2. Compaction at loss of consciousness

> **Needs discussion (owner, 2026-11-16).** Compaction and the waking-period
> context (ADR 0013 D1) are the core of P3.5 and get a dedicated discussion
> before this ADR is accepted. Topics: what compaction reads and writes, what
> happens to raw episodic records when compaction fails repeatedly (the "never
> evicted" rule below conflicts with the P3 capacity limits E-01/E-02 of
> `resident-experience-v0.1.md`), and how much raw experience is kept after
> compaction (Q4). The text below is the current draft.

**[Owner]** LLM formation happens in one place: compaction, when the resident
loses consciousness (sleep, fainting, and later intoxication). The world reports
these states; the resident does not choose when compaction runs.

- **Reads**: the waking-period context (ADR 0013 D1), plus related beliefs,
  impressions, skills and records marked `needs_review`.
- **Writes**: one structured formation delta using closed operations: add,
  update, supersede, summarize episodes, adjust a personality trait within
  bounds (ADR 0011 D5).
- **Provenance check**: every written record must cite source IDs that were in
  the input. A delta citing anything else is rejected whole.
- Episodic records that are not yet compacted are never evicted.

### D3. Mental fatigue

**[Owner]** Mental fatigue is a world need, computed deterministically from
world quantities (time awake and the amount of experience delivered, such as
utterances heard and new sightings). It never depends on token counts.

- The resident perceives it as a band, like other needs.
- `agents` sizes the waking-period context budget from that band and tells the
  model when the resident feels tired.
- At the maximum, a world rule makes the resident faint, which triggers
  compaction. This also bounds a waking period that never sleeps.

### D4. Cost

**[Owner]** No per-resident call or token limit in P3.5. Every formation call is
still recorded like a decision call.

**[Owner]** P3.5 runs also have no run-level cap. For P3.5 work this supersedes
the P3 trial caps and registration rule of `llm-decision-v0.1.md` §4 ("no
unlimited live trial") and the M8 CNY150 ceiling, which stay in force for P3
runs. Instead, input and output tokens of every call are recorded and shown per
section in the cost view (ADR 0014 D1), so the owner can see where tokens go and
adjust.

### D5. Recording and replay

Each compaction is one recorded model call plus its validated delta, hashed
like a P3 decision. Replay applies the recorded delta without a model call. A
failed or rejected compaction leaves the episodic records uncompacted and
retries at the next loss of consciousness.

## Consequences

- One trigger for all interpretation keeps formation simple to schedule and test.
- Days without sleep are possible but end in fainting, which the world controls.
- Compaction quality decides what residents remember long term; it needs the
  debug view of ADR 0014.

## Open questions

| ID | Question |
|---|---|
| Q1 | The mental fatigue formula and its maximum (world rule, shared with ADR 0010). |
| Q2 | Does fainting or intoxication degrade compaction (for example, memory gaps)? Deferred after the first version. |
| Q3 | Compaction runs while the world keeps ticking; must the resident stay unconscious until it finishes? |
| Q4 | Retention of raw episodic records after compaction: keep a bounded tail, or evict all compacted ones? |
