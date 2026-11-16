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
- D3 and D4 are marked **Needs discussion** for their details.

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
  effect, no ticks) or chooses another action. Choosing another action stops
  the running one, and the rule's `on_interrupt` applies (ADR 0007 D6). This
  replaces the v1 soft interrupts and deferred triggers for P3.5.
- An unconscious resident cannot take a turn. Waking (for example because of an
  urgent need) is a world rule, not a notification.
- The world clock stays frozen while a model call is outstanding, as in v1.

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

> **Needs discussion (owner, 2026-11-16).** Current draft: a mute list lasts
> for one action and is cleared when that action ends. The closed vocabulary
> of notification classes is Q6.

### D4. Waking-period working context

> **Needs discussion (owner, 2026-11-16).** The direction below is decided,
> and so is the day-log entry format. Still open: the template wording and
> which perceptions become observation entries (Q1), what enters the fixed
> prefix (Q2), the guard near the context window (Q4), and how detailed the
> day log is, which
> decides how large the context grows (ADR 0014 D2). Measured P3 request
> (offline, steady state, upper-bound tokens): action schema 55% (sent twice;
> P3.5 sends it once, ADR 0007 D7), tile lists 19%, recalled experience 20%
> (half of it metadata), needs, inventory and feedback under 1%.

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
   (need and fatigue bands), inventory, the running action and its progress,
   the current intention, and the reason for this turn.

- Dynamic world state is never kept as standing instructions. Only the current
  state shows it, and only as the resident perceives it now.
- The system instructions say how to interact (action format, verbs, innate
  drives), never how the world works: residents start with no recipes (ADR 0007
  D3).

**[Owner]** Day-log entries have fixed formats:

- World entries are rendered by fixed templates from what the world reported
  to this resident: action results, notifications, speech heard (verbatim) and
  observations. A change of state is logged as an entry ("you feel hungry");
  the full state appears only in the current state.
- Resident entries are the model's adopted responses, appended exactly as
  returned. The harness never shortens, rewrites or summarizes them; the
  response schema fixes only their shape.
- Every raw response, including one that failed to parse, is recorded in the
  audit. A response that was not adopted (retried, or replaced by the fallback
  policy, D7) does not enter the day log.
- The prefix and the day log are stable between turns, so prompt caching
  covers most of each request. Only the current state is new.

**[Owner]** The working context grows naturally. It is not compressed to a short
length during the waking period. Long-context effects of the model (missed
details, repetition, weaker attention) are accepted as part of a resident's
limited cognition. They are measured (ADR 0014 D2), not assumed. Context
length is never an input to world rules: mental fatigue is computed from world
quantities only (ADR 0012 D3).

**[Owner]** An engineering guard keeps every request within the model's
context window, so a long day cannot stop the run. The guard acts on the agent
side only and never changes world state; for example, it cannot make a
resident sleep. Its behaviour is Q4.

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

### D6. Intentions are optional

**[Owner]** No mandatory day plan. The resident may write an intention (ADR 0011
D1) at any level of detail, or none. The current intention is shown at every
turn and changed only by the resident. It never drives an action by itself.

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
requests and whose reply is due. It is released when the session ends.
Commitments made in dialogue are written mechanically (ADR 0012 D1). The
world's per-session turn cap is unchanged.

### D10. Tracing every piece of context

**[Owner]** Everything that enters a context can be traced to its source:

- Each assembled context has a manifest: for every section and entry, the
  memory, day-log entry or perception it came from, by ID, and its size in
  tokens. It holds references only, never copies.
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
| Q2 | Selection rules for the fixed prefix at waking. |
| Q3 | An operator-level run budget or kill switch for live runs, given no per-resident limit. |
| Q4 | The guard near the context window: what it drops or summarizes first, and at what threshold. It may not change world state. |
| Q5 | May the model ask for a recall itself (a memory lookup that never reaches the world)? That would make one turn more than one model call. |
| Q6 | The closed vocabulary of notification classes, and how long a mute list lasts. |
| Q7 | Request format: the provider's tool-calling messages or structured JSON output. If the provider returns a separate reasoning channel, it is recorded; whether it may be sent back in later requests depends on the provider. Both are decided by a live check. |
