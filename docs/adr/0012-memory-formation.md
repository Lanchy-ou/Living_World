# ADR 0012: Memory formation

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-16.
- Baseline: `3f25930` (`task/P3.5-RR-01-world-adrs`).
- Phase: P3.5, system 6 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: which memories are written mechanically, which are produced by an LLM,
  when that happens, and how it is recorded and replayed. Memory kinds are
  ADR 0011; the daytime working context is ADR 0013.
- Spec to be written: `docs/spec/memory-formation-v0.1.md`.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
  The D2 direction and the D3 rule that fatigue never trims the context follow
  the owner's architecture discussion of 2026-11-16; details it did not fix are
  open questions, not owner decisions.
- D2 is marked **Needs discussion** for its details.
- The agreement rule of D1, the source-kind check of D2 and the guidance on
  dated observations follow an external review that the owner accepted on
  2026-11-16.
- "Consolidation" replaces the earlier term "compaction": the step maintains
  long-term memory, it does not just shorten the day.

## Context

ADR 0011 defines typed long-term memory stores. Something must fill them. Raw
experience of the day is captured mechanically in the working context (ADR 0013
D4). Lasting memories (important episodes, beliefs from hearsay, generalized
skills, impressions and personality drift) need interpretation by a model. That
interpretation must not invent facts, must be recorded and must replay without
new model calls.

## Decision

### D1. Mechanical writes

Done during the waking period, with no model call. They record what the
resident directly experienced, so they need no interpretation:

- day-log entries of the working context (ADR 0013 D4), which replace P3
  episodic capture as the raw record of the day;
- skill evidence counts from attempts and observed phenomena;
- a commitment when an agreement with structured terms is accepted (ADR 0007
  D10). A promise made only in words is not written here; consolidation may
  still keep it as a belief or an intention;
- social fact counters (who gave what to whom).

Mechanical writes are the input of consolidation and its safety net: when
consolidation fails, they are not lost (D5).

**[Owner]** Hard facts are written by code and never decided by the model:
commitments (who promised what to whom, and any due time), transfers (who gave
what to whom) and skill evidence (attempts and the phenomena seen).
Consolidation may read and cite them, and may mark a commitment kept, broken or
expired, but may not delete or change them. Otherwise a promise that a
consolidation call left out would look like a broken one, and the commitment
metric (ADR 0014 D2) could not tell the two apart.

### D2. Consolidation at loss of consciousness

> **Needs discussion (owner, 2026-11-16).** The direction below is decided.
> Still open: the change-set schema, merge and forgetting rules (Q6), how
> much of a day becomes episodic memory (Q4), the consolidation window (Q3)
> and failure recovery (D5, Q5). The earlier conflict with the P3 capacity
> limits E-01/E-02 of `resident-experience-v0.1.md` no longer arises: a raw
> day log does not persist as long-term memory (ADR 0011 D6).

**[Owner]** LLM formation happens in one place: consolidation, a workflow that
runs when the resident loses consciousness (sleep, fainting, and later
intoxication). The world reports these states; the resident does not choose
when consolidation runs. Daytime model calls are for living and deciding
(ADR 0013); consolidation is the only memory-forming model call.

**[Owner]** Consolidation maintains long-term memory incrementally. It does not
just summarize the day. From the waking period's experience and the related
long-term memories, the model proposes changes, for example:

- keep important experiences as episodic memories;
- abstract repeated experiences into general beliefs or skill hypotheses;
- update impressions and long-term judgements of others;
- revise old memories, or lower their confidence, when new evidence contradicts
  them;
- merge, drop or forget details that do not matter.

- **Reads**: the waking period's working context (ADR 0013 D4), the mechanical
  writes of D1, and the existing long-term memories the model chooses.
  **[Owner]** The first version reads the whole waking period, as long as it
  fits the model's context window. Layered consolidation is evaluated later.
- **[Owner]** The model chooses which existing long-term memories to read. It
  first sees an index of the resident's long-term store and names the records
  it wants, then reads those in full and writes the change set. Both steps are
  recorded model calls, so replay needs no new call.
- **Writes**: one change set of closed operations: add, update, merge,
  supersede, change confidence, forget, and adjust a personality trait within
  bounds (ADR 0011 D5). The hard facts of D1 are out of its reach, except the
  status of a commitment.

**[Owner]** The index has one line per record: ID, kind, a one-line gist and
confidence. Consolidation writes the gist whenever it creates or changes a
record (ADR 0011 D2). Two kinds of record are always included without being
chosen, because the change set must handle them: open commitments and records
marked `needs_review`. The model may still miss an old memory that today's
experience contradicts; evaluation counts contradictory pairs in the long-term
store (claims that cannot both hold, not dated observations of a world that
changed, ADR 0011 D4).

**[Owner]** The model judges what is worth keeping; code never scores
importance. The consolidation prompt gives guidance aimed at the P3.5 goals:
keep where resources are, who said what and whether it was believed, what was
promised, what was tried and with what result, and how impressions of others
changed; routine steps and repeated identical actions may be forgotten. It also
asks the model to keep stable knowledge, dated observations and guesses apart,
and to treat a later different observation as a change, not as a lie (ADR 0011
D4). Its
wording is exploration-lane work (ADR 0014 D4). Evaluation checks whether kept
memories are later used.

**[Owner]** The model proposes; code validates and commits. The validator
checks:

- provenance: every new or changed record cites sources that were in the input
  (day-log entry IDs, memory IDs). An operation citing anything else fails;
- **[Owner]** source kind: each source kind matches what it cites. An
  `observed` source cites an entry of the resident's own perception; a record
  built only from speech stays `told`; existing sources are only added to,
  never relabelled (ADR 0011 D4). Day-log entries carry their type (ADR 0013
  D4), so this needs no world state;
- ownership: it changes only the consolidating resident's records, and no
  hard fact (D1);
- format: closed operations, the common envelope (ADR 0011 D2) and the capacity
  of each kind;
- version: it applies to the memory-store version it was built from.

**[Owner]** An operation that fails a check is dropped, together with any
operation that depends on it (for example, a merge into a dropped record). The
rest of the change set is committed. Dropped operations are recorded in the
audit.

**[Owner]** The validator never reads world state or the objective event log. A
belief that is wrong but sincerely held is kept: code never corrects a resident
with hidden truth.

After the change set is committed, the working context of that waking period is
closed (ADR 0011 D6). The next waking period starts a new one from the updated
memory. In the memory-off arm (ADR 0014 D2) no consolidation runs, and the
working context closes at the same boundary.

**[Owner]** The world does not pause for consolidation, and sleep can be
interrupted. The resident chooses how long it sleeps (ADR 0007 D2). A normal
sleep is long enough for consolidation to finish and the working context to be
closed.

> **Needs discussion (owner, 2026-11-16).** Current draft of the mechanism,
> which keeps replay exact: consolidation takes effect at a fixed tick, K ticks
> after the resident loses consciousness (K is a spec value). The world keeps
> running in between. If the model has not answered by tick K, the simulation
> waits at that tick, as it waits for decision calls, so a replay applies the
> result at the same tick. If the resident wakes before tick K, because it
> chose a short sleep (a nap) or because something woke it, the result is not
> applied: the resident keeps its open working context and consolidates at the
> next loss of consciousness. A nap rests the body but does not clear the
> mind. A faint lasts at least K ticks, so fainting always ends in
> consolidation.

**[Owner]** Residents are not told that a nap does not clear the mind. They
learn it, or fail to, from experience.

### D3. Mental fatigue

**[Owner]** Mental fatigue is a world need, computed deterministically from
world quantities (time awake and the amount of experience delivered, such as
utterances heard and new sightings). It never depends on token counts.

- The resident perceives it as a band, like other needs.
- **[Owner]** `agents` tells the model how tired the resident feels. It does not
  shrink or trim the working context because of fatigue: the context grows
  naturally (ADR 0013 D4). Whether a long context and fatigue relate, and how,
  is measured (ADR 0014 D2), not designed.
- At the maximum, a world rule makes the resident faint, which triggers
  consolidation. This also bounds a waking period that never sleeps.
- Physical fatigue and rest needs stay world rules, unchanged by this ADR.

### D4. Cost

**[Owner]** No per-resident call or token limit in P3.5. Every consolidation call
is still recorded like a decision call.

**[Owner]** P3.5 runs also have no run-level cap. For P3.5 work this supersedes
the P3 trial caps and registration rule of `llm-decision-v0.1.md` §4 ("no
unlimited live trial") and the M8 CNY150 ceiling, which stay in force for P3
runs. Instead, input and output tokens of every call are recorded and shown per
section in the cost view (ADR 0014 D1), so the owner can see where tokens go and
adjust.

### D5. Recording, replay and failure

Each consolidation is two recorded model calls, selection and change set
(input manifest, prompt version, model, raw output for each), plus the
validator's verdict and the committed change set, hashed like a P3 decision. Replay applies the recorded change set without a
model call.

Failure (current draft, Q5): a consolidation with no valid output is retried a
bounded number of times. If it still fails, the waking period still ends at
the boundary (ADR 0014 D2): the resident wakes with a new working context, and
the failed one stays pending, unseen by the resident, and is consolidated at
the next loss of consciousness together with the new one. After repeated failures only the mechanical writes
(D1) are kept, and the rest of the pending experience counts as forgotten.

## Consequences

- One trigger for all interpretation keeps formation simple to schedule and test.
- Days without sleep are possible but end in fainting, which the world controls.
- Consolidation quality decides what residents remember long term; it needs the
  debug view of ADR 0014.
- A resident can hold wrong beliefs indefinitely; only its own later experience
  or what others tell it can change them.
- Whether residents learn to sleep long enough is observable behaviour, and a
  learning signal that evaluation can use.
- Consolidation revises only the old memories it chose to read, so an old
  belief it did not pick survives that night unchanged, even if the day
  contradicted it.

## Open questions

| ID | Question |
|---|---|
| Q1 | The mental fatigue formula and its maximum (world rule, shared with ADR 0010), including how much a nap lowers it. |
| Q2 | Does fainting or intoxication degrade consolidation (for example, memory gaps)? Deferred after the first version. |
| Q3 | The consolidation window K (a spec value). |
| Q4 | How much of a day becomes episodic memory: a bound per consolidation, or only the capacity of each kind (ADR 0011 Q1)? |
| Q5 | Failure recovery: retry count, how many pending waking periods may be combined, and when the rest counts as forgotten. |
| Q6 | The change-set schema and the rules for merging and forgetting. |
