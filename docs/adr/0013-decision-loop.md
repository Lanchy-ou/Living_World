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

## Context

P3 builds a `DecisionContextP3` per decision from perception, identity, goals and
retrieved experience, projected into a bounded provider request with mandatory and
optional parts. P3.5 replaces per-decision retrieval of raw experience with a
waking-period context, and adds the memory kinds of ADR 0011.

## Decision

### D1. Waking-period context

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

### D5. Dialogue

Each open dialogue session has a working memory in the resident's runtime state:
participants, turns so far and open requests. It is released when the session
ends. Commitments made in dialogue are written mechanically (ADR 0012 D1). The
world's per-session turn cap is unchanged.

### D6. Output

One decision returns one structured plan (ADR 0007 D7).

## Consequences

- An append-only day log makes most of each request a cached prefix, which
  keeps uncapped calls affordable.
- Decisions see the full waking period, so per-decision retrieval of raw
  experience is no longer needed; recall is for long-term kinds only.
- Uncapped calls make an operator-level safety limit a separate question.

## Open questions

| ID | Question |
|---|---|
| Q1 | How a perception is summarized into a day-log entry, and how large it may be. |
| Q2 | Selection rules for the fixed prefix at waking. |
| Q3 | An operator-level run budget or kill switch for live runs, given no per-resident limit. |
| Q4 | What happens when a waking period reaches the model's context limit before fatigue forces fainting. |
