# ADR 0007: World–agent protocol

- Status: **Proposed** (draft for owner review; not effective).
- Date: 2026-11-15.
- Baseline: `8d5b44e` (`main`).
- Phase: P3.5, system 1 of 8 ([plan index](../plans/p3.5-implementation-plan-v0.1.md)).
- Scope: the shared protocol between the world and residents (called "v2" below
  to distinguish it from the frozen v1 protocol). Out of scope: the rule
  representation (ADR 0008), the memory model (ADR 0011) and content (ADR 0010).
- Spec to be written: `docs/spec/world-agent-protocol-v0.1.md`.
- Supersedes on acceptance: the action, perception and feedback parts of
  `interface-contract-v0.1.md` and `agent-interface-v0.1.md`, which stay
  unchanged as the v1 record.
- Owner decisions taken in discussion on 2026-11-15/16 are marked **[Owner]**.
  The 2026-11-16 decisions answer the first design review (near-miss
  phenomena, process materials, compatibility pack scope) and apply the owner's
  architecture discussion of the same day (no world soft interrupts, one action
  per turn; ADR 0013 D1–D3). D10 records owner decisions on an external review
  of the same day (speech during actions, watching, agreements). The explored
  terrain rule of D4 answers the independent design review of 2026-11-17
  ([P3.5-00 review](../tasks/p3.5/P3.5-00-review.md), F-01).

## Context

The frozen v1 protocol (`backend/src/living_island/world/protocol.py`) fixes 11
`ActionType` values, one target kind and one parameter model per action
(`ACTION_SHAPES`), and 17 `FailureCode` values. Each action's legality and effects
live in engine code. Adding a material or a transformation therefore changes a
frozen contract, the engine, the model-facing schema (`p3-actions/0.1`) and the
prompt.

The next phase needs a data-driven rule system: materials carry properties,
verbs are generic, and transformations are content. In the long term an LLM
may propose new rules that are validated and then added to the rule library.
Acceptance is about the preconditions for emergence: information spreads and
is believed or doubted; rules are discovered, remembered and taught; artifacts
persist and are used by others; commitments hold across days.

The rule discovery layer (C) is not a separate system in P3.5. It is a design
constraint on this protocol and on the rule representation (D9).

The core principles are unchanged: the world is the only source of truth;
perception is not omniscience; runs replay deterministically and every LLM
call is recorded; the frontend contains no game logic.

## Decision

### D1. Three layers with different change rates

| Layer | Contents | Changes | Change process |
|---|---|---|---|
| Protocol | Intent, result and perception shapes; kernel actions | Rarely | Change request + ADR |
| Vocabularies | Verbs, property names and value domains, effect operations, phenomenon terms | Occasionally | New version and hash |
| Rule library | Verb + materials + conditions → effects | Often | Content only |

Adding rules must not change the protocol, the model-facing schema or the
prompt prefix.

### D2. Kernel actions plus one generic action

- Kernel actions with engine semantics: `move_to`, `give`, `pick_up`, `drop`,
  `wait`, `inspect`, `contribute`.
- One generic action, `act`, resolved against the rule library:

```text
ActIntent {
  intent_id, plan_id, actor_id,
  verb: Verb,                          // closed vocabulary
  target: EntityRef | TileRef | null,
  instruments: [ItemRef],              // used, not consumed
  inputs: [{ref: ItemRef, quantity}],  // consumed
  params: {},                          // closed shape per verb
  reason: string | null
}
```

- References are instance IDs. A resident may reference only instances it holds
  or perceives, checked as v1 checks exposure receipts.
- `gather`, `eat`, `drink`, `fill_canteen`, `rest` and `sleep` become rules.
  **[Owner]** Rest and sleep are rules. So the effect vocabulary must include a
  bounded operation that changes the actor's own physiology.
  **[Owner]** The resident chooses how long to sleep, as a parameter of its
  sleep action, within bounds the world sets. The world wakes it at that time
  unless something wakes it earlier (ADR 0013 D3).
- **[Owner]** Speech is not an action. v1 `talk` becomes an optional utterance
  that any turn may carry next to its action, so speaking never stops what the
  body is doing (D10). `give` stays a kernel action and moves ownership between
  two residents (ADR 0008 D6).

### D3. Capability exposure

- The model-facing schema lists the verb vocabulary and reference kinds only.
- The world never lists rules and never tracks which rules a resident knows.
  (It still keeps v1-style exposure receipts, which record what was shown to a
  resident, not what the resident concluded.)
- Known recipes are assembled by `agents` from the resident's own memory.
- **[Owner]** Residents start with no recipes. Survival instinct (eating,
  drinking and sleeping when in need), curiosity and willingness to try are
  innate. These are cognition defaults owned by `agents`, not world rules and
  not pre-known recipes. The exact boundary is open question Q1.

### D4. Perception granularity

- Each property declares its observability in content: `visible`, `on_inspect`
  (revealed by the `inspect` kernel action, which costs ticks) or `on_use`
  (revealed only by feedback from use).
- Values are delivered as coarse descriptors, not exact numbers, as v1 does with
  need bands.
- **[Owner]** Appearances may deceive. A material may declare an apparent value
  that differs from its true value for a property. Perception reports the
  apparent value; settlement always uses the true value.
- **[Owner]** Explored terrain stays world-delivered, as in v1
  (`explored_static_tiles`, `interface-contract-v0.1.md` §2.2): a resident
  knows its way around places it has seen. It is static map data, not memory,
  and is kept in both memory arms (ADR 0014 D2). Dynamic facts (fruit stock,
  items, people) are not in it; they reach later turns only through memory.
  How it is rendered in the context, given its size, is decided in the
  decision-loop spec.

### D5. Feedback

| Case | Decided by | Resident-facing feedback |
|---|---|---|
| Malformed intent | `agents` | `INVALID_PLAN`; never reaches the world (unchanged) |
| Kernel precondition fails | `world` | Existing-style failure code (too far, not held) |
| Rule matched, condition unmet | `world` | Observed phenomena only |
| No rule matched | `world` | Observed phenomena only |

- **[Owner]** Phenomena only. The resident is never told whether a rule exists
  or which condition failed. Phenomena are produced deterministically from a
  closed phenomenon vocabulary and property comparisons, for example "leaves a
  dent" or "does not cut".
- **[Owner]** A near miss may look different from a useless attempt. When the
  items fit a rule but its conditions are unmet, the resident sees that rule's
  `unmet` phenomenon (for example "the clay hardens slightly"), which may differ
  from the phenomena of an attempt no rule fits. This hint is intentional: it
  gives discovery a gradient. It names no rule and no missing condition. The
  selection order is ADR 0009 D1.
- Every attempt costs ticks.
- The objective event log records the matched `rule_id` on success and failure,
  and records `attempt_unmatched` with a normalized attempt descriptor (verb plus
  the property signatures of target, instruments and inputs). Residents never
  receive these fields. They are the input data for future rule discovery.

### D6. Multi-tick processes

- Personal timed actions keep the v1 duration and progress.
- **[Owner]** The world no longer interrupts an action because the resident
  hears speech, sees something new or crosses a need threshold (the v1 soft
  interrupts of `world-rules-v0.1.md` §4.3). It reports these as notifications
  and the action keeps running; the resident decides at its turn whether to
  continue or change (ADR 0013 D3). Only hard stops end an action from the
  world side: physical facts such as death, fainting, exhaustion, missing
  inputs or target, or a blocked path. An unconscious resident cannot take a
  turn, so waking (for example because of an urgent need) is a world rule.
- A rule declares `on_interrupt`: keep progress, lose progress, or produce a
  partial output. It applies to a hard stop and to a resident stopping its own
  action by choosing another.
- Process entities are world objects for transformations that outlive one actor
  (a burning fire, something drying) or accept several contributors.
- **[Owner]** Cooperation is in the first version: residents `contribute` work
  to a process entity until the rule's required total is reached.
- **[Owner]** A process entity holds its materials like a container. Any
  resident may put materials into it (for example branches into a construction
  site, or fuel into a fire) with the kernel item-transfer actions, which accept
  a process entity as target. Contributed work counts only while the materials
  the rule requires are present. Materials are consumed when the process
  completes, or as the rule declares (fuel burning down).
- Inputs are reserved when an action starts, so one item cannot be consumed by
  two actions. Conflicts keep the v1 deterministic order (actor ID order plus the
  seeded RNG).
- Process progress appears in perception as a coarse descriptor.

### D7. Model-facing form

- **[Owner]** One turn returns one next action, or `continue` at a turn during a
  running action, plus an optional utterance (D10) and an optional intention
  update (ADR 0013 D2). The world
  holds no queue of future actions; this replaces the P3 plan of
  1..`max_plan_actions` intents. There is no tool loop inside one request:
  results arrive only after the world has advanced, so the action–result loop
  runs across ticks.
- The schema is generated from the protocol version, the verb vocabulary and
  the reference kinds only. Rule library contents never enter the schema.
  CI keeps the P3 drift check against the protocol models.
- **[Owner]** The response schema is sent once, in the provider's
  structured-output field. The system message keeps the instructions and the
  short verb descriptions, but no second copy of the schema. P3 sent both
  (`resident-cognition-v0.1.md`, "Render exactly two ordered messages"); the
  copy in the system message was about 27% of every request (offline
  measurement, 2026-11-16). DeepSeek expands the structured-output schema into
  the prompt itself (the P3 token counter already charges it), so the model
  still sees it. A live check before the first P3.5 run confirms that
  single-copy requests are accepted and parse as often as P3's.
- Known recipes and observed phenomena go into the context built from memory.

### D8. Migration

- v1 stays frozen. v2 is a new versioned lane, as CR-005 did for P3.
- A v1 compatibility content pack expresses the 11 v1 actions on the v2 kernel
  and rules. Equivalence is checked on a projection (per-tick physical state and
  key facts) for a fixed seed set, because event types change and byte equality
  is not possible.
- **[Owner]** The compatibility pack contains v1 mechanics only. New mechanics
  (mental fatigue and fainting, tool wear, fruit decay, crafting) enter through
  the starter pack, after the equivalence check passes. The compatibility pack
  then stays as a permanent regression baseline.
- Before the v1 engine is removed, the expected projections are generated from
  the v1 engine at the archive tag and committed as test fixtures. The
  equivalence check compares v2 against these fixtures, so it keeps running
  after v1 code is gone.
- The rule-based policy runs on v2 through two adapters: a perception adapter
  (v2 perception to the v1 shape it reads) and an intent adapter (its v1
  intents to v2; a v1 `talk` becomes an utterance with a `wait` of the v1
  `talk_ticks`). It stays the baseline and fallback policy.
- v2 has no soft interrupts and no world-side plan queue, so the rule-based
  policy reproduces v1 behaviour on its own side: it keeps its v1 queue and
  stops its running action wherever v1 would have interrupted it (the v1 table
  of `world-rules-v0.1.md` §4.3 becomes part of that policy). The compatibility
  rules declare `on_interrupt` to match v1 (progress lost, completed movement
  kept), so the equivalence projection still matches.
- **[Owner]** v1 recorded runs are archived: the last v1 commit is tagged and
  old runs replay from that tag. The v2 code base keeps no v1 engine. Unknown
  versions are still refused, with no implicit migration.
- Process: change request in `docs/spec/open-questions.md` → owner decision →
  this ADR accepted → `world-agent-protocol-v0.1.md` (existing v0.1 specs are
  not rewritten) → regenerated
  frontend types and fixtures → task cards.

### D9. Provisions for LLM-proposed rules

1. A closed, versioned and hashed registry of verbs, properties, value domains,
   effect operations and phenomenon terms. Rules contain no code.
2. Rule identity and provenance: `rule_id`, content hash, `provenance`
   (authored, or proposed by an `llm_call_id`, plus approver).
3. The rule library version is in the run manifest. Changes happen only at
   boundaries and are logged as an objective `rule_added` event, like
   `config_changed`.
4. Conservation: each rule declares inputs and outputs by conservation class,
   and the validator refuses output from nothing. Physiology effects (D2) are
   bounded per rule and are not a conservation class.
5. Rule conditions and `attempt_unmatched` descriptors use one representation,
   so a proposed rule can be back-tested on recorded attempts.
6. A proposed rule is data. It passes the same validator as an authored rule,
   is inactive until approved, and its proposal is a recorded LLM call.

### D10. Speech, watching and agreements

**[Owner]** Speech runs alongside actions. An utterance is an optional part of
any turn, next to its action or `continue` (ADR 0013 D2). A resident can answer
while it keeps gathering or walking, and the running action is not stopped.
Utterances keep the v1 speech features: hearing range, dialogue sessions, the
per-session turn cap and reply checks (`world-rules-v0.1.md` §4.2).

**[Owner]** Residents can learn by watching. Within perception range a
resident sees another resident's attempts as the world shows them: who acted,
the verb, the visible items used and the phenomena visible from where it
stands. It never sees the matched rule, true values or the actor's own
`on_use` feedback. Which phenomena are visible to watchers is declared in the
phenomenon vocabulary (Q4).

**[Owner]** Formal agreements carry structured terms. The words of an utterance
stay free, but an utterance may also carry terms: who promises, to whom, what,
and an optional due time. "What" comes from a small closed set that the
objective log can check: give an item, return an item, be at a place,
contribute to a process entity. The terms become an agreement only when the
other party answers with an explicit acceptance. This generalizes the v1
`request` and `accept`/`refuse` speech acts, which carry only an item request.
As in v1, accepting moves nothing; the promised act is done separately.

- The objective event log records the accepted agreement as a fact. The world
  never enforces it.
- The commitment memory is written mechanically from the accepted terms (ADR
  0012 D1). Words without terms are only words: they reach the listener's day
  log like any speech and may become a belief or an intention at
  consolidation, but they are not commitments for code or evaluation.
- Whether an agreement was kept, broken or expired is judged from objective
  events (ADR 0014 D2), never from what the residents say about it.

## Consequences

- Content can grow without protocol, schema or prompt-prefix changes.
- Discovery is slower and costs more ticks. Phenomena-only feedback and
  deceptive appearances make learning harder by design.
- The world gains process entities, input reservation and a phenomenon
  generator, and loses its soft-interrupt table. The engine changes
  substantially.
- v1 runs no longer replay on the current code base, only from the archive tag.
- The frontend must render v2 events and process entities.
- Dialogue and work overlap, so cooperation does not stall at every reply.
- Only agreements with structured terms can be checked. A promise made only in
  words may still matter to the residents, but evaluation cannot count it.

## Open questions

| ID | Question |
|---|---|
| Q1 | Where exactly does innate survival instinct end and a learned recipe begin? Is "eat when hungry" a known way to eat any edible-looking item, or only a drive that leads to trying? |
| Q2 | How much tick cost does an attempt have, and does it differ by verb? |
| Q3 | The verb vocabulary for the first version: which verbs, and how many? |
| Q4 | The phenomenon vocabulary, how property comparisons produce phenomena, and which phenomena watchers see (D10). |
| Q5 | Deceptive appearances: is the apparent value fixed per material, per instance, or can it change (for example, rot)? Does `inspect` see through it? |
| Q6 | Resolved by the owner, 2026-11-16: residents learn by watching within perception range (D10). |
| Q7 | Physiology effects from rules: which needs, and what per-rule bounds? |
| Q8 | Process entities: decay. Ownership restricts nothing, so any resident may take outputs (ADR 0008 D6). |
| Q9 | The equivalence projection and seed set for the v1 compatibility pack. |
| Q10 | Resolved by the owner, 2026-11-16: a resident speaks during a timed action without stopping it (D10). |
| Q11 | The full list of hard stops, their priority, and how a stop chosen by the resident is reported in the result. |
| Q12 | The bounds on a chosen sleep length, and its parameter shape (a length, or a wake-up time). |
| Q13 | Agreement terms (D10): the exact term kinds, the due-time form, how a return is matched to the item lent, and whether the receiving party also gets a mechanical record. |
