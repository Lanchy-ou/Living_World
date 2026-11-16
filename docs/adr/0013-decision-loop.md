# ADR 0013: Context assembly and decision loop

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-16.
- Baseline: `3f25930` (`task/P3.5-RR-01-world-adrs`).
- Phase: P3.5, system 7 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: how a decision's context is assembled, when the model is called, how
  dialogue is handled, and how the result reaches the world. Memory kinds are
  ADR 0011; compaction is ADR 0012; the action shape is ADR 0007.
- Spec to be written: `docs/spec/decision-loop-v0.1.md`.
- Supersedes on acceptance: `resident-cognition-v0.1.md` and
  `llm-decision-v0.1.md` for new work.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
- D1 is marked **Needs discussion**: not ready for acceptance.

## Context

P3 builds a `DecisionContextP3` per decision from perception, identity, goals and
retrieved experience, projected into a bounded provider request with mandatory and
optional parts. P3.5 replaces per-decision retrieval of raw experience with a
waking-period context, and adds the memory kinds of ADR 0011.

## Decision

### D1. Waking-period context

> **Needs discussion (owner, 2026-11-16).** Together with compaction (ADR 0012
> D2) this is the core of P3.5 and gets a dedicated discussion before
> acceptance. Topics: what a day-log entry holds, how a perception becomes a
> short deterministic change summary (Q1), what enters the fixed prefix (Q2),
> and how the P3 token distribution informs the budget. Measured P3 request
> (offline, steady state, upper-bound tokens): action schema 55% (sent twice;
> P3.5 sends it once, ADR 0007 D7), tile lists 19%, recalled experience 20%
> (half of it metadata), needs, inventory and feedback under 1%. The text below
> is the current draft.

**[Owner]** The context is organized by waking period, not by decision. It is
append-only, so a stable prefix can use prompt caching:

1. **Fixed prefix**, built at waking: system instructions, identity and
   personality, and long-term memories selected for the day (beliefs,
   impressions, skills, commitments, intention).
2. **Day log**, append-only: every delivered perception summary, decision and
   feedback of this waking period, in order.
3. **Current turn**: the trigger, current perception and any memories recalled
   for this decision, appended as new day-log entries rather than rewriting
   the prefix.

The budget follows the mental fatigue band (ADR 0012 D3). Compaction at loss of
consciousness ends the waking period.

### D2. Recipes per trigger

The recipe decides which long-term memories are recalled into the current turn:

| Trigger | Recalled memories |
|---|---|
| Plan finished | Intention, current goal |
| Addressed by a resident | Impression of the speaker, commitments to them, related beliefs |
| Action failed | Skills for the verb, the observed phenomena |
| Urgent need | Known food and water beliefs |

### D3. Plans are optional

**[Owner]** No mandatory day plan. The resident may write an intention (ADR 0011
D1) at any level of detail, or none. The loop uses an intention when one exists
and asks the model at the next trigger otherwise.

### D4. When the model is called

**[Owner]** Residents are LLM-driven: the model decides at every decision
boundary. P3.5 sets no call or token limit (ADR 0012 D4). The rule-based policy
stays only as the fallback for provider failures, as in P3.

**[Owner]** Fallback actions stay out of the resident's mind. A plan made by the
fallback policy, and the feedback from it, is written neither to memory nor to
the day log the model sees. The objective event log still records the actions,
tagged with the fallback policy, and evaluation excludes them from discovery and
teaching metrics. The world state they cause (a new position, a drunk serving)
is visible in later perception like any other change.

The P3 per-request input limit (B-05, 32768 tokens) does not apply to P3.5. The
limit is the provider model's context window (owner: DeepSeek V4.1, 1M tokens;
pinned with provider evidence before use). Token use per section is monitored,
not capped.

### D4a. Provider stability

**[Owner]** Fallback is a last resort, so the provider path must be stable:

- The request schema passes an offline check against the provider's documented
  structured-output limits before any live run (the M9 smoke failed every call
  on a hosted schema rejection).
- Errors are classified (timeout, rate limit, server error, invalid output) and
  retried with bounded backoff; the counts and limits are spec values.
- The fallback rate per resident and day is a first-class metric in the cost
  view, so instability is visible at once.

### D5. Dialogue

Each open dialogue session has a working memory in the resident's runtime state:
participants, turns so far and open requests. It is released when the session
ends. Commitments made in dialogue are written mechanically (ADR 0012 D1). The
world's per-session turn cap is unchanged.

### D6. Output

One decision returns one structured plan (ADR 0007 D7).

### D7. Tracing every piece of context

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

- An append-only day log makes most of each request a cached prefix, which
  keeps uncapped calls affordable.
- Decisions see the full waking period, so per-decision retrieval of raw
  experience is no longer needed; recall is for long-term kinds only.
- Uncapped calls make an operator-level safety limit a separate question.
- A resident may notice changes it has no memory of causing (after a fallback
  stretch). This is accepted in exchange for keeping fallback knowledge out of
  the resident.

## Open questions

| ID | Question |
|---|---|
| Q1 | How a perception is summarized into a day-log entry, and how large it may be. |
| Q2 | Selection rules for the fixed prefix at waking. |
| Q3 | An operator-level run budget or kill switch for live runs, given no per-resident limit. |
| Q4 | What happens when a waking period reaches the model's context limit before fatigue forces fainting. |
