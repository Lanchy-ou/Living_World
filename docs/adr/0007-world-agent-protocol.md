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
- Owner decisions taken in discussion on 2026-11-15 are marked **[Owner]**.

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

- Kernel actions with engine semantics: `move_to`, `talk`, `give`, `pick_up`,
  `drop`, `wait`, `inspect`, `contribute`.
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
- `talk` and `give` stay kernel actions. Speech carries information, not a
  physical change, and has hearing range, dialogue sessions and reply checks.
  `give` moves ownership between two residents.

### D3. Capability exposure

- The model-facing schema lists the verb vocabulary and reference kinds only.
- The world never lists rules and never tracks what a resident knows.
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
- Every attempt costs ticks.
- The objective event log records the matched `rule_id` on success and failure,
  and records `attempt_unmatched` with a normalized attempt descriptor (verb plus
  the property signatures of target, instruments and inputs). Residents never
  receive these fields. They are the input data for future rule discovery.

### D6. Multi-tick processes

- Personal timed actions keep the v1 model: duration, progress, interruption.
  A rule declares `on_interrupt`: keep progress, lose progress, or produce a
  partial output.
- Process entities are world objects for transformations that outlive one actor
  (a burning fire, something drying) or accept several contributors.
- **[Owner]** Cooperation is in the first version: residents `contribute` work
  to a process entity until the rule's required total is reached.
- Inputs are reserved when an action starts, so one item cannot be consumed by
  two actions. Conflicts keep the v1 deterministic order (actor ID order plus the
  seeded RNG).
- Process progress appears in perception as a coarse descriptor.

### D7. Model-facing form

- One decision returns one structured plan of 1..`max_plan_actions` intents, as
  in P3. No multi-turn tool loop.
- The schema is generated from the protocol version, the verb vocabulary and
  the reference kinds only. Rule library contents never enter the schema.
  CI keeps the P3 drift check against the protocol models.
- Known recipes and observed phenomena go into the context built from memory.

### D8. Migration

- v1 stays frozen. v2 is a new versioned lane, as CR-005 did for P3.
- A v1 compatibility content pack expresses the 11 v1 actions on the v2 kernel
  and rules. Equivalence is checked on a projection (per-tick physical state and
  key facts) for a fixed seed set, because event types change and byte equality
  is not possible.
- The rule-based policy runs on v2 through an intent adapter and stays the
  baseline and fallback policy.
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

## Consequences

- Content can grow without protocol, schema or prompt-prefix changes.
- Discovery is slower and costs more ticks. Phenomena-only feedback and
  deceptive appearances make learning harder by design.
- The world gains process entities, input reservation and a phenomenon
  generator. The engine changes substantially.
- v1 runs no longer replay on the current code base, only from the archive tag.
- The frontend must render v2 events and process entities.

## Open questions

| ID | Question |
|---|---|
| Q1 | Where exactly does innate survival instinct end and a learned recipe begin? Is "eat when hungry" a known way to eat any edible-looking item, or only a drive that leads to trying? |
| Q2 | How much tick cost does an attempt have, and does it differ by verb? |
| Q3 | The verb vocabulary for the first version: which verbs, and how many? |
| Q4 | The phenomenon vocabulary and how property comparisons produce phenomena. |
| Q5 | Deceptive appearances: is the apparent value fixed per material, per instance, or can it change (for example, rot)? Does `inspect` see through it? |
| Q6 | Does a resident observe phenomena from another resident's attempt (learning by watching)? |
| Q7 | Physiology effects from rules: which needs, and what per-rule bounds? |
| Q8 | Process entities: ownership, decay, and whether other residents may take outputs. |
| Q9 | The equivalence projection and seed set for the v1 compatibility pack. |
