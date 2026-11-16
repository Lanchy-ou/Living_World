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
- a commitment when the resident accepts a request in dialogue;
- social fact counters (who gave what to whom).

Mechanical writes are the input of consolidation and its safety net: when
consolidation fails, they are not lost (D5).

### D2. Consolidation at loss of consciousness

> **Needs discussion (owner, 2026-11-16).** The direction below is decided.
> Still open: how the related long-term memories are selected, the change-set
> schema, how importance is judged, merge and forgetting rules (Q6), how much
> of a day becomes episodic memory (Q4), formation per memory kind (ADR 0011
> D7) and failure recovery (D5, Q5). The earlier conflict with the P3 capacity
> limits E-01/E-02 of `resident-experience-v0.1.md` no longer arises: a raw day
> log does not persist as long-term memory (ADR 0011 D6).

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
  writes of D1, and related long-term memories, including records marked
  `needs_review`. **[Owner]** The first version reads the whole waking period,
  as long as it fits the model's context window. Layered consolidation is
  evaluated later.
- **Writes**: one change set of closed operations: add, update, merge,
  supersede, change confidence, forget, and adjust a personality trait within
  bounds (ADR 0011 D5).

**[Owner]** The model proposes; code validates and commits. The validator
checks:

- provenance: every new or changed record cites sources that were in the input
  (day-log entry IDs, memory IDs). A change set citing anything else is
  rejected whole;
- ownership: it changes only the consolidating resident's records;
- format: closed operations, the common envelope (ADR 0011 D2) and the capacity
  of each kind;
- version: it applies to the memory-store version it was built from.

**[Owner]** The validator never reads world state or the objective event log. A
belief that is wrong but sincerely held is kept: code never corrects a resident
with hidden truth.

After the change set is committed, the working context of that waking period is
closed (ADR 0011 D6). The next waking period starts a new one from the updated
memory.

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

Each consolidation is one recorded model call (input manifest, prompt version,
model, raw output), plus the validator's verdict and the committed change set,
hashed like a P3 decision. Replay applies the recorded change set without a
model call.

Failure (current draft, Q5): a failed or rejected consolidation is retried a
bounded number of times. If it still fails, the waking period's working
context stays pending and is consolidated at the next loss of consciousness,
together with the new one. After repeated failures only the mechanical writes
(D1) are kept, and the rest of the pending experience counts as forgotten.

## Consequences

- One trigger for all interpretation keeps formation simple to schedule and test.
- Days without sleep are possible but end in fainting, which the world controls.
- Consolidation quality decides what residents remember long term; it needs the
  debug view of ADR 0014.
- A resident can hold wrong beliefs indefinitely; only its own later experience
  or what others tell it can change them.

## Open questions

| ID | Question |
|---|---|
| Q1 | The mental fatigue formula and its maximum (world rule, shared with ADR 0010). |
| Q2 | Does fainting or intoxication degrade consolidation (for example, memory gaps)? Deferred after the first version. |
| Q3 | Does the world clock freeze during a consolidation call, as during decision calls, or does the resident stay unconscious until it finishes while the world ticks? |
| Q4 | How much of a day becomes episodic memory: a bound per consolidation, or only the capacity of each kind (ADR 0011 Q1)? |
| Q5 | Failure recovery: retry count, how many pending waking periods may be combined, and when the rest counts as forgotten. |
| Q6 | The change-set schema, how importance is judged, and the rules for merging and forgetting. |
