# ADR 0013: Context assembly and decision loop

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-16.
- Baseline: `3f25930` (`task/P3.5-RR-01-world-adrs`).
- Phase: P3.5, system 7 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: who decides what in the loop between a resident and the world, when a
  resident gets a turn, how the waking-period context is assembled, how
  dialogue is handled, and how the result reaches the world. Memory kinds are
  ADR 0011; consolidation is ADR 0012; the action shape is ADR 0007.
- Spec to be written: `docs/spec/decision-loop-v0.1.md`.
- Supersedes on acceptance: `resident-cognition-v0.1.md` and
  `llm-decision-v0.1.md` for new work, and the plan-queue and replanning parts
  of `agent-interface-v0.1.md` (AG-02, AG-03, §3.2).
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
  D1–D4 follow the owner's architecture discussion of 2026-11-16 (agent
  harness, decision loop, memory). That discussion fixed directions only;
  formats, algorithms and numbers it did not fix are open questions, not owner
  decisions.
- The details of D3 and D4 that were marked *Needs discussion* were settled by
  the owner on 2026-11-17, after the design review. Values, templates and the
  guard's degradation strategy are spec work.
- The utterance of D2, the entry types of D4 and the commitment rule of D9
  follow an external review that the owner accepted on 2026-11-16.
- The clock exception of D3 and the period boundary in D6 and D9 answer the
  independent design review of 2026-11-17
  ([P3.5-00 review](../tasks/p3.5/P3.5-00-review.md), F-01, F-04).
- The pressure contract, the cue wording rule and the guard limits of D4
  answer the round 3 review of 2026-11-17 (P3.5-00 review §8, R3-F-01,
  R3-C-01, R3-C-02); the owner chose them on the same day.

## Context

P3 builds a `DecisionContextP3` per decision from perception, identity, goals and
retrieved experience, projected into a bounded provider request with mandatory and
optional parts. One decision returns a plan of up to five intents, which the
runtime executes in order without asking the model again. The world interrupts
a running action when the resident hears speech, sees something new or crosses
an urgent need threshold, discards the rest of the plan and asks for a new one
(`world-rules-v0.1.md` §4.3, §4.4; `agent-interface-v0.1.md` AG-02, AG-03).

In that design the world and the plan queue decide, on the resident's behalf,
when to stop and when to think again. P3.5 wants residents that are autonomous
agents acting in a world with rules and feedback, not rule-driven characters
that a model assists now and then.

## Decision

### D1. Roles

**[Owner]** The resident decides what it does, and whether it continues,
changes or drops its plan after feedback. The world only settles what an action
does.

| Role | Owns | Code |
|---|---|---|
| World engine | Physical rules, time, settlement, results and reports | `world` |
| Resident (the model) | Observing, thinking, choosing the next action, interpreting results, keeping or changing its own plans | Model output, through `agents` |
| Harness | Context assembly, model calls, parsing, recording; when a resident gets a turn; passing intents to the world | `agents` (context, calls, records) and `sim` (scheduling, delivery to the world) |
| Memory system | Working context, long-term store, formation and forgetting (ADR 0011, 0012) | `agents`, `memory` |

The harness is a role, not a new package. Module boundaries are unchanged:
`sim` stays the only coordinator between `agents` and `world`.

### D2. One action per turn

**[Owner]** A turn returns one next action (a kernel action or `act`, ADR 0007
D2). At a turn that comes while an action is running (D3), it may instead return
`continue`. A turn may also update the resident's intention (D6), give the new
action a mute list (D3) and cite memory IDs (D10).

**[Owner]** A turn may also carry one utterance (ADR 0007 D10). Speech is not
an action and does not stop the running one: a resident answers while it keeps
working. For example, A is chopping a tree and B asks to borrow the axe; A's
turn is `continue` plus "after I finish this tree", and the chopping goes on.

- The world holds no queue of the resident's future actions. A multi-step plan
  exists only as the intention in the resident's memory. The resident chooses
  every step again, with the latest result in view.
- The loop has the shape of tool calling (action, result, next action), but it
  runs across ticks: all residents settle together at tick boundaries, so a
  result arrives only after the world has advanced. Each turn is one model
  call; there is no tool loop inside one request.
- The rule-based policy may keep its own internal queue. Like any policy, it
  returns one action per turn.

### D3. Turns: hard stops and notifications

**[Owner]** The harness decides when a resident gets a turn. The resident
decides what to do with it. The world reports what happened; it never decides
that a resident should stop or replan.

A resident gets a turn when it wakes, when its action ends, and when a
notification arrives while an action is running:

| | Examples | Effect on the running action |
|---|---|---|
| Hard stop | Death, fainting, exhaustion, inputs or target gone, path blocked | The world ends the action and reports the result |
| Notification | Speech heard, a new sighting, a need crossing a band, process progress | The world reports it; the action keeps running |

- At a turn during a running action, the resident either continues (no world
  effect and no ticks, apart from delivering any utterance) or chooses another
  action. Choosing another action stops
  the running one, and the rule's `on_interrupt` applies (ADR 0007 D6). This
  replaces the v1 soft interrupts and deferred triggers for P3.5.
- An unconscious resident cannot take a turn. Waking (for example because of an
  urgent need) is a world rule, not a notification.
- The world clock stays frozen while a turn's model call is outstanding, as in
  v1. Consolidation is the exception: the world keeps running while its calls
  are pending and waits only at the tick where the result takes effect (ADR
  0012 D2).

**[Owner]** The resident chooses what not to be disturbed by. An action may
carry an optional mute list: the notification classes that should not give a
turn while that action runs. Nothing muted means every notification gives a
turn.

- The harness applies the list deterministically; the world never sees it. A
  muted notification is still written to the day log, so the resident sees it
  at its next turn. Muting changes when the resident learns something, never
  whether it does.
- The list is part of the recorded model output, so replay applies it without
  a model call.
- A notification class added later gives a turn by default, because no
  earlier choice muted it.

**[Owner]** One notification cannot be muted: hunger or thirst reaching the
critical band. It only gives the resident a turn; the resident still decides
whether to stop. Hard stops (fainting, exhaustion, death) are separate: the
world ends the action whatever the mute list says.

**[Owner]** The first version has a few stable notification classes: a change
in body state, direct speech (addressed to the resident), nearby conversation,
a new discovery, and task or environment progress. A notification only offers
a turn; it never stops the action.

- **[Owner]** A mute list holds only for the current action. It is cleared when
  that action ends, is replaced or is stopped.
- **[Owner]** Progress is not notified at every tick, only at meaningful steps,
  so a long action does not produce a stream of empty turns. The exact classes
  and steps are Q6.

### D4. Waking-period working context

> Settled by the owner on 2026-11-17: what the day log holds, the morning
> selection and context pressure (below). Still spec work: template wording
> and observation thresholds (Q1), the prefix limit (Q2), and the pressure
> thresholds, the counting details and the guard's exact rules (Q4).
> Measured P3 request (offline, steady state, upper-bound tokens): action
> schema 55% (sent twice; P3.5 sends it once, ADR 0007 D7), tile lists 19%,
> recalled experience 20% (half of it metadata), needs, inventory and
> feedback under 1%.

**[Owner]** Each resident has one working context per waking period, from
waking to loss of consciousness. The harness rebuilds every request from stored
parts; it does not rely on a provider-side session. Parts, in order:

1. **Fixed prefix**, built at waking: system instructions, short action
   descriptions, identity, personality and behaviour constraints, and long-term
   memories selected for the day. The response schema goes in the provider's
   structured-output field, not here (ADR 0007 D7).
2. **Day log**, append-only: the resident's own actions and their results,
   speech heard and said, notable observations (new sightings, changes),
   explorations, and memories recalled during the day (D5), in order.
3. **Current state**, replaced at every turn: the latest perception, body state
   (need and fatigue bands), context pressure, inventory, the running action and
   its progress, the current intention, and the reason for this turn.

- Dynamic world state is never kept as standing instructions. Only the current
  state shows it, and only as the resident perceives it now.
- The system instructions say how to interact (action format, verbs, innate
  drives), never how the world works: residents start with no recipes (ADR 0007
  D3).

**[Owner]** The objective event log keeps the full history. The day log holds
only what the resident actually received: its own actions and their results,
speech heard (verbatim), notable new observations and changes, memories it
recalled, and its adopted responses (verbatim). It never touches hidden world
state. An unchanged surrounding is not logged again. An observation that was
delivered is kept even when it gave no turn at once, for example while muted.

**[Owner]** Day-log entries have fixed formats:

- World entries are rendered by fixed templates from what the world reported
  to this resident: action results, notifications, speech heard (verbatim) and
  observations. A change of state is logged as an entry ("you feel hungry");
  the full state appears only in the current state.
- **[Owner]** Every entry carries its type (for example `action_result`,
  `observation`, `heard_speech`, `recall`, `own_response`) and the tick it
  describes. Code can then
  tell what the resident perceived from what it was told, which the
  consolidation validator checks (ADR 0012 D2).
- Resident entries are the model's adopted responses, appended exactly as
  returned. The harness never shortens, rewrites or summarizes them; the
  response schema fixes only their shape.
- Every raw response, including one that failed to parse, is recorded in the
  audit. A response that was not adopted (retried, or replaced by the fallback
  policy, D7) does not enter the day log.
- The prefix and the day log are stable between turns, so prompt caching
  covers most of each request. Only the current state is new.
- **[Owner]** The long-term memories in the fixed prefix are chosen by a
  harness-side model call (context management) from the memory index (ADR
  0012 D2), not by fixed code rules and not by the resident. The index shows
  each record's ID, kind, gist and confidence; selection is not a cut by a
  fixed importance score. As a starting experiment the prefix holds about
  8–20 memories; the real limit follows token use and tests (Q2). Open
  commitments are not forced into the prefix, so a resident may forget a
  promise (D9). During the day, cue-based recall and deliberate recall stay
  (D5).

**[Owner]** The working context grows naturally. It is not compressed to a short
length during the waking period. Long-context effects of the model (missed
details, repetition, weaker attention) are accepted as part of a resident's
limited cognition. They are measured (ADR 0014 D2), not assumed. Context
length is never an input to world rules: mental fatigue is computed from world
quantities only (ADR 0012 D3). Neither hidden compression nor automatic sleep
may mask these effects.

**[Owner]** Context pressure links the load of the day to the resident's own
choice to rest, without the harness choosing for it:

- **[Owner]** The harness computes context pressure from how full the whole
  working context is (fixed prefix, day log and current state) against the
  model's window. It is an agent-side cognitive cue, not world state, and never
  reaches the world. The growth of the day log alone is recorded next to it for
  analysis (ADR 0014 D2).
- **[Owner]** The current state shows it in plain, neutral words, separate from
  mental fatigue: each is described from its own value, so high pressure with
  low fatigue never says "you are very tired". The cue describes and never
  prescribes: "your thoughts feel crowded" is allowed, "you should sleep" is
  not. It never mentions how long a sleep must last (ADR 0012 D2).
- The cue rises gradually, well before the context nears the model's window,
  not only once the window is full.
- The resident decides whether to keep going or rest. The harness never makes
  it sleep because of pressure.
- **[Owner]** The cue never counts itself. Pressure is computed from the
  request without the pressure line; the line is then added, and the complete
  request is counted again only to check that it fits the window (the guard
  below). Otherwise a longer sentence could push the count across a band and
  change the sentence.
- **[Owner]** Pressure is computed deterministically with a pinned local
  counter (for example the P3 upper-bound counter), never from usage that the
  provider reports and never by calling the provider. It is recorded as a
  derived agent-side entry in the context manifest (D10), not as an
  observation: counter and wording versions, the counted amount, the band and
  the cue text. Replay recomputes it with the same pinned code, or refuses if
  an input or the counter differs, so a rebuilt request matches its recorded
  hash.

**[Owner]** An engineering guard keeps every model call within the model's
context window: decisions, deliberate recall, the morning selection and both
consolidation calls (ADR 0012 D2). A run then cannot fail on a resident that
keeps refusing to sleep, or on a long day at consolidation. The guard must hold
even when the resident ignores the cue. It acts on the agent side only and
never changes world state, mental fatigue included; it cannot make a resident
sleep. In the first version:

- It only leaves content out, by fixed rules (for example the oldest day-log
  entries first). It never asks a model to summarize, because that would be a
  second memory-forming call (ADR 0012 D2).
- The stored day log stays complete. Each time the guard acts, the record
  states what was left out, with manifests before and after (D10), and the
  inspection view shows it. Evaluation reports those turns apart from natural
  long-context effects (ADR 0014 D2).
- The resident is told only that it cannot clearly recall earlier parts of the
  day. Nothing is invented in their place.
- An oversized request is not a provider failure, so it does not trigger the
  fallback policy (D7).
- Pressure still reflects the full context, not the shortened request, so a
  shortened day never looks fresh.

The exact rules, what is left out first and the threshold are spec values (Q4).

Consolidation at loss of consciousness closes the working context (ADR 0012
D2). The next waking period starts a new one from the updated memory.

### D5. Recall

Long-term memories enter the working context in two ways: selected at waking
into the fixed prefix (Q2), and recalled at a turn and appended to the day log.
Recall decides what the resident remembers, never what it does. Current recipes
by turn reason:

| Turn reason | Recalled memories |
|---|---|
| Action ended | Skills for the verb, the observed phenomena |
| Spoken to | Impression of the speaker, commitments to them, related beliefs |
| Need band crossed | Known food and water beliefs |
| New sighting | Beliefs and skills about what was seen |

A memory already recalled in this waking period is not appended again.

**[Owner]** Recall by recipe is part of the memory system, not a choice of the
resident, so it does not conflict with D1: people do not choose what comes to
mind either. A resident can also try to recall something on purpose during the
day, and not everything can be recalled.

**[Owner]** Deliberate recall:

- The resident states what it tries to remember. Recall stays in the
  resident's mind and never reaches the world.
- Each long-term record has a strength, computed from how recently and how
  often it was used and from its confidence. Using a record strengthens it;
  unused records weaken, and consolidation may forget weak ones.
- Only records above a strength threshold can be reached. A harness-side model
  call picks the relevant ones from the reachable part of the index, at most N
  per recall. They are appended to the day log like recipe recall.
- Recipe recall works from cues (a person present, a verb in use) and may reach
  weaker records linked to that cue, so meeting someone can bring back a faded
  memory.

The strength formula, the threshold, N and the number of recalls per turn are
spec values (Q5).

### D6. Intentions are optional

**[Owner]** No mandatory day plan. The resident may write an intention (ADR 0011
D1) at any level of detail, or none. The current intention is shown at every
turn and changed only by the resident. It never drives an action by itself. In
the memory-off arm it is cleared at the period boundary (ADR 0014 D2).

### D7. Model calls and fallback

**[Owner]** Residents are LLM-driven: the model takes every turn. P3.5 sets no
call or token limit (ADR 0012 D4). The rule-based policy stays only as the
fallback for provider failures, as in P3.

**[Owner]** Fallback actions stay out of the resident's mind. An action chosen
by the fallback policy, and the feedback from it, is written neither to memory
nor to the day log the model sees. The objective event log still records the
actions, tagged with the fallback policy, and evaluation excludes them from
discovery and teaching metrics. The world state they cause (a new position, a
drunk serving) is visible in later perception like any other change.

The P3 per-request input limit (B-05, 32768 tokens) does not apply to P3.5. The
limit is the provider model's context window (owner: DeepSeek V4.1, 1M tokens;
pinned with provider evidence before use). Token use per section is monitored,
not capped.

### D8. Provider stability

**[Owner]** Fallback is a last resort, so the provider path must be stable:

- The request schema passes an offline check against the provider's documented
  structured-output limits before any live run (the M9 smoke failed every call
  on a hosted schema rejection).
- Errors are classified (timeout, rate limit, server error, invalid output) and
  retried with bounded backoff; the counts and limits are spec values.
- The fallback rate per resident and day is a first-class metric in the cost
  view, so instability is visible at once. It is also reported against context
  length, because long-context effects may show up as invalid output.

### D9. Dialogue

The turns of a conversation are in the day log. Each open dialogue session
also has a small working state in the resident's runtime: participants, open
requests and whose reply is due. It is released when the session ends or the
waking period ends, whichever comes first. The world's per-session turn cap is
unchanged.

**[Owner]** Only an accepted agreement with structured terms becomes a
commitment, written mechanically (ADR 0007 D10, ADR 0012 D1). The record is
kept by code, but whether the resident remembers it the next day depends on
the morning prefix and on recall (D4, D5). A resident can therefore forget a
promise, and evaluation can still tell a forgotten promise from one that was
never made.

### D10. Tracing every piece of context

**[Owner]** Everything that enters a context can be traced to its source:

- Each assembled context has a manifest: for every section and entry, the
  memory, day-log entry or perception it came from, by ID, and its size in
  tokens. Derived agent-side data, such as context pressure (D4), names the
  derivation that produced it. The manifest holds references only, never
  copies.
- Day-log entries, memories and fixed-prefix parts are stored once, by content
  hash. A decision record stores its manifest, the new entries and the model
  output. The exact request bytes are rebuilt deterministically and checked
  against the recorded request hash. P3 stored the full context several times
  per decision (about 190 KB each); with an append-only day log that would grow
  with the square of the day length.
- The model output may cite the memory IDs that a speech act or action relies
  on (optional field, agent side only, never sent to the world). Evaluation
  checks citations against the manifest, because a model's own citation can be
  wrong.

## Consequences

- The model is called once per turn, after every action and at notifications,
  so there are more calls per day than in P3. An append-only day log makes most
  of each request a cached prefix, which keeps uncapped calls affordable.
- Decisions see the full waking period, so per-decision retrieval of raw
  experience is no longer needed; recall is for long-term kinds only.
- The world no longer has soft interrupts, and the runtime no longer has a plan
  queue. Both become resident choices.
- Uncapped calls make an operator-level safety limit a separate question.
- A resident may notice changes it has no memory of causing (after a fallback
  stretch). This is accepted in exchange for keeping fallback knowledge out of
  the resident.

## Open questions

| ID | Question |
|---|---|
| Q1 | The wording of the world-entry templates, which perceptions become observation entries, and how large an entry may be. |
| Q2 | Whether the prefix selection is a separate call at waking or the last step of consolidation, and the prefix limit (start at about 8–20 memories, D4). |
| Q3 | An operator-level run budget or kill switch for live runs, given no per-resident limit. |
| Q4 | Context pressure: its bands, thresholds and wording, which parts of the request are counted, how the window is defined (including the room left for the response), and how replay verifies the derivation (D4). The guard: which entries it leaves out first, at what threshold, and what happens when a single new input is too large on its own. Neither may change world state. |
| Q5 | The strength formula, the threshold, N, and how many recalls one turn may make. A recall never reaches the world, but it makes one turn more than one model call. |
| Q6 | The exact notification classes (D3 names the first five) and which progress steps notify. |
| Q7 | Request format: the provider's tool-calling messages or structured JSON output. If the provider returns a separate reasoning channel, it is recorded; whether it may be sent back in later requests depends on the provider. Both are decided by a live check. |
| Q8 | Later direction, not in the first version: residents with different memory ability, for example a different recall reach or result count, as a trait. |
