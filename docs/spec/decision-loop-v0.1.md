# Living Island — Context Assembly and Decision Loop v0.1 (P3.5)

> **Rework 2 (2026-11-18).** Unifies origin filtering, policy calibration, request floors and durable decision evidence. DL-25–30 specify replay fixtures.

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §15 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
> Rework 1 (2026-11-18) answers the Gate 2 resident-track review
> ([review](../tasks/p3.5/P3.5-SP-01-review-agent.md) B02, B07, B08, B10–B12,
> N02, N05) and the world-track B15, and uses the protocol as amended by
> CR-010.
>
> Implements [ADR 0013](../adr/0013-decision-loop.md). Works with the frozen
> [world–agent protocol](world-agent-protocol-v0.1.md), the
> [memory model](memory-model-v0.1.md) and
> [memory formation](memory-formation-v0.1.md). When frozen, it supersedes for
> new work `resident-cognition-v0.1.md`, `llm-decision-v0.1.md` and the
> plan-queue and replanning parts of `agent-interface-v0.1.md` (AG-02, AG-03,
> §3.2). Parts of `llm-decision-v0.1.md` are reused by reference, as stated.

## 0. Scope

### 0.1 Covered here

- Roles and modules (ADR 0013 D1).
- When a resident gets a turn: reports, notification classes, muting (D3,
  Q6).
- The model's output for a turn (D2, D6, D10).
- The working context: prefix, morning selection, day log, current state
  (D4, Q1, Q2).
- Context pressure and the window guard (D4, Q4).
- Recall by recipe and on purpose, and record strength (D5, Q5).
- Model calls, errors, retries and fallback (D7, D8, Q7), and an operator stop
  (Q3).
- Dialogue working state (D9).
- Context manifests, records and replay (D10).
- The memory-off arm on the agent side (ADR 0014 D2).

### 0.2 Owned elsewhere

| Subject | Spec |
|---|---|
| `TurnSubmission`, perception, reports, the turn binding | `world-agent-protocol-v0.1.md` (frozen) |
| Memory records and the store | `memory-model-v0.1.md` |
| Mechanical writes, K, consolidation | `memory-formation-v0.1.md` |
| Metrics, probes, the dashboard | `evaluation-v0.1.md` |

## 1. Roles and modules

| Role | Owns | Code |
|---|---|---|
| World | Settlement, reports, packets | `world` |
| Resident (the model) | The turn's choices | Model output, through `agents` |
| Harness | Turn scheduling and delivery to the world | `sim` |
| Harness | Context assembly, model calls, parsing, recording | `agents` |
| Memory | Store, mechanical writes, consolidation | `agents`, `memory` |

Module boundaries are unchanged (AGENTS.md): `sim` is the only coordinator
between `agents` and `world`; `agents` reads the world only through the
protocol module; nothing in `agents` reads the audit (memory model §6).

## 2. Turns

### 2.1 When a resident gets a turn

At each boundary, after its packet is delivered (protocol §2), a living,
conscious resident gets a turn when any of these holds:

| Turn reason | From |
|---|---|
| `start` | Tick 0 |
| `woke` | A `woke` report |
| `action_ended` | An `action_ended` report (any outcome, a hard stop included) |
| `notification` | A report of an unmuted notification class (§2.2) while an action runs |

- One turn per resident per boundary. Its reasons are all that apply, sorted
  in the order of this table, then by report order.
- An unconscious or sleeping resident gets no turn (protocol §6.3).
- A resident whose action ended always gets a turn (protocol §2).

### 2.2 Notification classes

The five classes of ADR 0013 D3 (ADR 0013 Q6; owner, DL-D1):

| Class | Reports |
|---|---|
| `body` | `need_band_changed`, `need_threshold_crossed` |
| `direct_speech` | `utterance_heard` with `addressed = true` |
| `nearby_speech` | `utterance_heard` with `addressed = false` |
| `discovery` | `entity_first_seen` |
| `progress` | `progress_step` |

- `action_observed` reports are not notifications: they are written to the day
  log and give no turn on their own. Watching is learned from at the next
  turn, and a busy neighbour cannot flood a resident with turns.
- `progress_step` comes only when a coarse progress descriptor changes
  (protocol §5.3), at thirds of the work, so a long action notifies at most
  twice.
- **Unmutable.** `need_band_changed` into `critical` for `satiety` or
  `hydration` always gives a turn (ADR 0013 D3). It only offers the turn.
- A class added in a later version gives a turn unless muted.

### 2.3 Muting

- A turn that starts an action may give it a mute list: a set of classes.
  Notifications of those classes give no turn while that action runs, except
  the unmutable one.
- The list belongs to that action only. It is cleared when the action ends,
  is stopped or is replaced; `continue` keeps it (ADR 0013 D3).
- A muted report is still written to the day log, so the resident sees it at
  its next turn.
- The list is part of the recorded model output, so replay applies it.

### 2.4 What a turn can do

- At a turn with no running action, the resident chooses one action.
- At a turn during a running action, it chooses `continue` or another action;
  another action stops the running one at this boundary (protocol §4.4).
- Either way the turn may carry one utterance, an intention change and memory
  citations, and may first ask to recall (§6.3).
- The harness fills the turn's identity and checks the binding (protocol
  §3.1). A binding failure (`INVALID_TURN`) is retried once with the same
  input; a second failure uses the fallback (§8.3).
- **Origin.** Every turn, and every intent and utterance it submits, carries
  its origin, `model` or `fallback`, in the decision record, keyed by turn and
  intent ID (memory formation §1.3). A fallback turn for an LLM resident
  carries no utterance.

**Filter before consumption.** At packet ingestion resolve origin by intent
and turn against the durable bindings. Keep the exact packet for replay.
For the actor, remove fallback choices, rationale, speech and terminal
feedback/phenomena from the agent input used by the renderer, all recall
recipes and all memory writers. Preserve the neutral action-ended scheduling
signal and current running action, progress and continue/replace controls.
It supplies no recipe key from that result. Other independently delivered
senses and a witness's own observations follow ordinary rules (MF §1.3).
Apply this filter also after handback and restoration.

## 3. The model's output

```text
TurnOutput = {step:"recall", query:string}                  // at most once per turn (§6.3)
           | {step:"act",
              action:{kind:"continue"} | {kind:"intent", intent:IntentChoice},
              utterance:UtteranceChoice|null,
              intention:{set:string} | {clear:true} | null,
              mute:array<NotificationClass>,               // only with a new intent
              cite:array<string>}                           // memory or day-log IDs; agent side only
```

- `IntentChoice` and `UtteranceChoice` are the protocol's `Intent` and
  `Utterance` without the identity fields, which the harness fills (protocol
  §3.1). `reason` may be given and never affects settlement.
- The JSON schema of `TurnOutput` is generated from the protocol version, the
  enabled verbs and the reference kinds (protocol §10). Its hash is
  `action_schema_sha256`.
- Shape errors (protocol §3.4 layer 1) are agent-side `INVALID_TURN`s,
  recorded and retried (§8.2).
- `intention`, `mute` and `cite` never reach the world. The intention is
  written to the store (memory model §3.6).
- **Citations.** `cite` may name memory record IDs (`m:…`) and day-log entry
  IDs (`d:…`), at most 10. A citation is **valid** only when the cited item was
  in the request actually sent for this turn (its sent manifest, §10.1): a
  memory in full or as a recall entry, the current intention's own local ID
  rendered beside its text in either arm, or a day-log entry the guard kept.
  Bind each valid citation to the adopted act request, its immutable rendered
  fragment and revision. The off arm may cite only its current-period intention
  through this current-state path.
  Invalid citations are recorded and ignored, never an error. The instructions
  ask the resident to cite the entries and memories its choice relies on.
  Evaluation reads only valid citations (ADR 0013 D10; evaluation spec
  §3.2).
- Lengths: `query` up to 200 characters, `intention.set` up to 500,
  utterance text up to the adapter cap of 500, `reason` up to 300. Longer
  output is a shape error.

## 4. The working context

One per waking period (ADR 0013 D4). Every request is rebuilt from stored
parts; no provider session is used.

### 4.1 Parts and order

| Part | Contents | Changes |
|---|---|---|
| 1. Fixed prefix | System instructions; verb descriptions; identity (name, profile values); personality traits as words; the memories chosen at waking (§4.2) | Built once at waking |
| 2. Day log | Typed entries in order (§4.3) | Append only |
| 3. Current state | §4.4 | Replaced at every turn |

The response schema goes only in the provider's structured-output field
(ADR 0007 D7).

- **The system instructions** say how to interact: the turn format, the
  verbs, what continuing and muting mean, that speech rides alongside
  actions, the innate drives (eat, drink and sleep when in need; curiosity),
  and that words may be wrong. They never say how the world works and give no
  recipe (ADR 0007 D3, owner PR-D1). Their wording is exploration-lane work
  with a pinned prompt version.
- Personality is shown as words: each trait value 0–4 maps to a fixed phrase,
  for example `curiosity 4` → "very curious".

### 4.2 The morning selection

- At waking, a harness-side model call picks the long-term memories for the
  prefix from the store index (ADR 0013 D4). The call reads the index, the
  resident's identity and its current state at waking; it outputs up to 20
  record IDs.
- It is a separate call at waking, not the last step of consolidation
  (ADR 0013 Q2; owner, DL-D2): it runs when opening a new waking period after K, including a failed
  consolidation. Waking early keeps the existing prefix. Its input is the
  store as it stands when the new awake context opens.
- **Prefix limit:** at most 20 records (owner, DL-D2), from the soft range of
  8–20 in ADR 0013 D4. Open commitments are not forced in.
- At tick 0 and in the memory-off arm no call runs: the prefix holds no
  memories.
- The morning call has its own call record (§10.2) whatever happens: adopted
  (its IDs make the prefix), failed after its retries (the prefix holds no
  memories, and the period runs on), or never dispatched because its request
  did not fit (§7.1). There is no fallback for it.

### 4.3 The day log

Every entry has a type, the tick it describes, an ID `d:<period_id>:<n>`, its
text, and a `ref` to the delivered item it was written from. Entries are
stored once by content hash (ADR 0013 D10).

```text
DayLogEntry { id:string, type:string, tick:integer, text:string,
              delivery_id:string|null,          // the packet it came from
              ref:{kind:"feedback", intent_id}
                 |{kind:"utterance_feedback", utterance_id}
                 |{kind:"utterance", utterance_id, speaker_id}
                 |{kind:"observed_action", intent_id, phase}
                 |{kind:"entity", entity_id}|{kind:"cue", cue_id}
                 |{kind:"report", report_kind, subject_id}
                 |{kind:"turn", turn_id}|{kind:"recall", mode:"deliberate", call_id}
                 |{kind:"recall", mode:"recipe"|"off_empty", turn_id, ordinal}
                 |{kind:"inspection", intent_id},
              verbatim:object|null,             // heard speech: speaker, addressee, act, text, terms as delivered
              about:array<string> }             // witness keys, computed by code (below)
```

Store exact packet member path (field and ordered index) alongside each
packet-derived entry in inspection; entries may link multiple members for
one observation. Non-packet entries have null delivery. Record the retrieved
revision and rendered text hash for each recall. **Witness keys.** Code computes each entry's `about` keys from the delivered
item alone, never from hidden state: `entity:<id>`, `archetype:<id>` and
`material:<id>` of every entity or item it shows; `resident:<id>` of every
resident it shows, the actor of a watched action and the speaker of heard
speech; `place:<x>,<y>` of every tile position it shows; `verb:<id>` and
`phenomenon:<id>` of an action it reports; `need:<id>` of a body change;
`spoke:<utterance_id>` of the resident's own utterance feedback. The
keys say what the entry directly witnesses; memory formation §3.5 uses them
to check `observed` sources.

The `ref` is resident-safe (IDs the resident's own packets carried). The
analysis side joins it to the objective event (evaluation spec §1); the entry
itself carries only identifiers authorized by this resident's own delivery.

| Type | Written from | Template (fixed wording, pinned version) |
|---|---|---|
| `own_response` | An adopted `TurnOutput` | The response exactly as returned |
| `action_result` | An `action_feedback` entry | "Your {action} ended: {status}{, failure}. {phenomena texts}" with the looks of its `items_used` ("using a long vine cord, …") |
| `utterance_result` | A `last_utterance_feedback` | "You said to {addressee}: "{text}"" on success, "Your words to {addressee} were not said: {reason words}" on failure |
| `heard_speech` | A heard utterance | "{speaker} said to {you/addressee/everyone}: "{text}"" plus terms in words |
| `observation` | A first sighting, a cue, a watched action, or a changed look of a visible entity | "You see …", "You notice …", "{actor} starts to {verb} with {items}", "{actor} {verb}s: {phenomena}; {items}" |
| `inspection` | An `inspect` result's `InspectView` | "Looking closely at {thing}: {descriptor words}" |
| `body_change` | A band change or threshold crossing | "You feel {band words}" |
| `progress` | A progress step | "Your {action} is {progress word}" |
| `sleep` | Falling asleep, waking | "You fall asleep." / "You wake." |
| `recall` | A recall result | "You remember: {gist}. {text}" per record, with its ID |

- An `observation` of a watched action names its phase: one entry per
  `ObservedAction` (protocol §5.4), with `visible_items`, its filtered start
  target and any received portions. Journal permitted packets throughout sleep
  under MF §§2–3; selection and change-set read the frozen confirmation snapshot.
- An `inspection` entry keeps the `on_inspect` words the resident saw, so an
  inspected tell stays in the day log even though no later `EntityView`
  shows it (protocol §5.2).
- **Own perception.** The types `action_result`, `utterance_result`,
  `observation`, `inspection`, `body_change`, `progress` and `sleep` are the
  resident's own perceptions for `observed` sources (memory model §4.1);
  `heard_speech` is the only source of `told`.

- **Observations** (ADR 0013 Q1; owner, DL-D3): an entry is written for every
  `entity_first_seen` report, every cue upgrade, every `ObservedAction`, and
  every visible entity whose descriptors differ from those of its last
  observation entry in this period. An unchanged surrounding is never logged
  again (ADR 0013 D4).
- World entries are at most 1000 characters; a longer rendering is cut at a
  word boundary with "…". `own_response` and `heard_speech` entries are never
  cut: the schema's length limits bound the first, and the 500-character
  utterance cap and the closed terms bound the second (`verbatim` keeps the
  delivered speech exactly).
- Entries hold only what the resident received. Nothing from hidden state,
  the bridge or the agreement fact enters (protocol §5.1, memory formation
  §1.1).
- An observation delivered while muted is written all the same.
- A response that was not adopted (retried or replaced by the fallback) is
  not written (ADR 0013 D4).
- **Fallback origin.** Feedback, `items_used` and utterance feedback of a
  fallback-origin intent or turn are not written, whenever they arrive,
  including after the model has resumed (memory formation §1.3). The rest of
  each packet is written as usual.

### 4.4 The current state

Rendered at every turn, in this order:

1. The turn's reasons in words.
2. Body: each need band as words; mental fatigue as its own words.
3. Context pressure as its own words (§5), separate from fatigue.
4. Position, time of day and awareness.
5. Inventory: each item with its look and quantity.
6. The running action and its progress, and its mute list.
7. The current intention (citable local ID, text), or "none".
8. What is in sight: visible entities with their looks, transient sightings,
   cues; residents with their visible signs.
9. The explored map: a character grid of the bounding box of the resident's
   explored tiles, one character per terrain, `?` for unexplored, `@` for the
   resident (owner, DL-D4). Explored terrain is world-delivered static data,
   kept in both memory arms (ADR 0007 D4).

## 5. Context pressure

- **Counted:** the complete request without the pressure line: system
  message, prefix, day log, current state and the schema as the provider
  counts it (ADR 0013 D4). Counted with the pinned upper-bound counter of
  `llm-decision-v0.1.md` §2.2, never with provider usage and never by a call.
- **Window:** `W = model window − response reserve`. For the pinned provider
  model (DeepSeek V4.1, 1,000,000 tokens; pinned with provider evidence before
  use, ADR 0013 D7) and a response reserve of 8,000, `W = 992,000`.
- **Bands** of `pressure = counted ÷ W` (ADR 0013 Q4; owner, DL-D5):

  | Pressure | Band | Words in the current state |
  |---|---|---|
  | below 5% | `clear` | Your thoughts feel clear. |
  | 5% to below 15% | `busy` | Your thoughts feel busy. |
  | 15% to below 30% | `crowded` | Your thoughts feel crowded. |
  | 30% to below 50% | `heavy` | Your thoughts feel heavy and crowded. |
  | 50% or more | `overloaded` | Your thoughts feel overloaded. |

  Comparisons use integers: `100 × counted < 5 × W`, and so on.
- The words describe and never prescribe. They never mention sleep or its
  length (ADR 0013 D4).
- **Never counts itself.** Pressure is computed without its line; the line is
  then added and the complete request is counted again only for the guard
  (ADR 0013 D4).
- **Recorded** as a derived agent-side manifest entry: counter ID and version,
  wording version, counted amount, band and text. Replay recomputes it with
  the same pinned code and refuses if an input or the counter differs.
- Both memory arms use the same policy (ADR 0014 D2). The policy (counter,
  bands, wording) is an experimental condition, like the model ID.

## 6. Recall

### 6.1 Strength

Each record has a strength (ADR 0013 Q5; owner, DL-D6), computed when needed
from its envelope (memory model §2):

```text
days     = (now − (last_used_tick or created_tick)) div 144
strength = 20 × confidence + min(40, 10 × use_count) + max(0, 40 − 10 × days)
```

Strength is 0–160. A prefix or recalled record earns **use** at its first
actual dispatch in a decision or decision_after_recall request of that turn.
Deduplicate (turn_id, record_id) across retries and follow-up decisions. At
that dispatch update last_used_tick and increment use_count once, in one
store batch for newly exposed IDs. Log turn, call, revision and store-version
delta durably. Guard-trimmed or never-dispatched retrieval earns zero; a
provider error after dispatch still exposes the sent item. Index scanning
and merely rendering the intention in current state earn no use credit.
Unused records weaken, and consolidation may forget weak ones (ADR 0013 D5).
Strength is internal to recall; the index line stays as memory model §2.1
defines it.

### 6.2 Recipe recall

At every turn, before the request is built, code recalls by the turn's reasons
(ADR 0013 D5). Each recipe reaches records with strength at least 20, takes the
strongest first (then the lowest ID) and appends at most 5 records per turn in
total, skipping records already recalled or in the prefix in this period.
History and refuted skills are excluded. Suppress the entire action-ended
recipe for fallback-origin results, even a delayed result after handback.

| Turn reason | Recalled |
|---|---|
| `action_ended` of an `act` | Live skills with that verb; skills whose `expected` includes a phenomenon in the feedback |
| `direct_speech` or `nearby_speech` | The speaker's social record; open commitments with the speaker; beliefs whose subject is the speaker |
| `body` for satiety or hydration | Beliefs with the topic `food` (satiety) or `water` (hydration) |
| `discovery` | Beliefs whose subject is the seen entity or its archetype; skills whose looks name its archetype or material |
| Any turn, the counterpart in sight | Open commitments with a resident in `visible_entities` |
| Any turn, due soon | Open commitments whose `due_tick` is within the next 24 ticks |

- The two commitment cues (ADR 0011 D7: hearing, presence and an approaching
  due time) recall open commitments whatever their strength, since they are
  hard facts; they are taken first and count toward the 5.
- A registered memory kind may register its own recipes (ADR 0014 D3; memory
  model §10).

### 6.3 Deliberate recall

- A turn may first return `{step:"recall", query}`: at most one per turn
  (owner, DL-D6). The harness then makes a recall call: its input is the
  query and the index lines of records with strength at least 40; its output
  is up to 5 record IDs. They are appended as `recall` entries, and the turn's
  request is rebuilt and sent again, which must return `step:"act"`.
- Recall stays in the resident's mind and never reaches the world (ADR 0013
  D5).
- Unknown IDs, IDs below the threshold and IDs beyond 5 are ignored and
  recorded.
- A second `recall` in the same turn is a shape error.
- **Memory off.** The `recall` step stays in the schema in both arms, so the
  arms see the same choices. In the off arm no recall call is made: the
  harness appends one `recall` entry, "You cannot remember anything about
  that.", and rebuilds the turn's request as in the on arm, which must return
  `step:"act"`. The two arms therefore make the same number of decision
  calls for a turn with a recall.

## 7. The window guard

Every model call goes through the guard: decisions, deliberate recall, the
morning selection and both consolidation calls (ADR 0013 D4). The order for
consolidation is memory formation §4; for the other calls:

1. If the complete request fits `W`, nothing happens.
2. Otherwise the oldest day-log entries are left out, oldest first, keeping
   at least the newest 20 entries, until it fits (owner, DL-D7).
3. Then prefix memories are left out, the last selected first.
4. An omission notice is added: "You cannot clearly recall earlier parts of
   the day." Nothing else is put in their place.

- **Never left out:** the system instructions, the schema and its framing,
  the current state, the newest 20 day-log entries and the notice. This is the
  minimum mandatory request.
- Every guard action is recorded with the manifests before and after; the
  inspection view shows it.
- Pressure still reflects the full context, not the shortened request.

### 7.1 The pre-dispatch contract

Before any call is dispatched, the harness:

1. assembles the candidate request in full: every part, the provider framing,
   the pressure line where the call kind has one, and the omission notice if
   anything will be left out;
2. counts it with the pinned counter (§5) and compares it with `W`, the window
   minus the response reserve;
3. leaves parts out in the call kind's order (above; memory formation §4),
   recounting with the notice included, until it fits or only the floor is
   left;
4. if the floor alone does not fit, does not dispatch: the call record
   (§10.2) gets outcome `stopped_unfit` with the measured floor, the reserve,
   the window, the omitted parts and the reason; decision/morning stops take
   effect at this boundary. Consolidation stops are staged until living K
   under MF §§3.1, 7; early wake/death abandons them.
   Neither the provider nor the fallback is used on this path.

**Request and floor by kind.** Every row includes its versioned instructions,
schema, provider framing and settings. Include the exact omission notice
whenever trimming occurs. The pressure cue in a turn describes the full
decision context before trimming; morning renders waking current state
with the same pinned computation over its own full request. Recall and
consolidation have no additional live pressure computation (a frozen
context retains its existing text).

| Kind | Full request in addition to common framing | Minimum counted request |
|---|---|---|
| decision | Fixed identity/verb/personality prefix, prefix memories, log, current state with pressure | Fixed prefix, current state, latest 20 entries or all if fewer, applicable notice |
| decision_after_recall | Same plus this turn's recall result | Decision floor plus this turn's deliberate/empty recall entries, counted once |
| recall | Query and eligible index | Entire request |
| morning | Identity, waking current state with pressure, index | Entire request |
| consolidation_selection | Frozen context, pending periods, index, full open/review records | Frozen prefix/current state, index, full open/review records, applicable notice |
| consolidation_change_set | Selection request plus selected and mechanically changed records | Selection floor plus full changed mechanical records, deduplicated by revision |

For each candidate count the actual rendered parts, including applicable
notice and exact provider framing. Record the minimal candidate with the
notice it actually needs, independently of the full and sent requests.
Index size and compressed token counts have no universal constant bound.

**Wire limits.** The reused P3 provider adapter (`llm-decision-v0.1.md`
§2.2) keeps its wire preparation, but its request byte cap is replaced for
P3.5 by this contract, and its maximum output setting is the response reserve
(8,000 tokens). No second limit can then refuse a request this contract
admitted.

## 8. Model calls and fallback

### 8.1 Requests

- **Format** (ADR 0013 Q7; owner, DL-D8): structured JSON output with the
  schema sent once, in the provider's structured-output field (ADR 0007 D7).
  A live check before the first P3.5 run confirms that single-copy requests
  are accepted and parse at least as often as P3's; if it fails, the spec
  takes the provider's tool-calling form instead through a change request.
- If the provider returns a separate reasoning channel, it is recorded and
  never sent back.
- The request schema passes an offline check against the provider's
  documented structured-output limits before any live run (ADR 0013 D8).
- The provider port, attempt journal, interrupted-call handling and partial
  tails of `llm-decision-v0.1.md` (§2.2, §4.3, §7.2) are reused. Its budget
  admission and caps (§4.1, §4.2, §8) do not apply to P3.5 (ADR 0012 D4).

### 8.2 Errors and retries

| Class | Retries | Backoff |
|---|---|---|
| Timeout | 3 | 2, 4, 8 seconds |
| Rate limit | 5 | 5, 10, 20, 40, 60 seconds |
| Server error | 3 | 2, 4, 8 seconds |
| Invalid output (parse or shape), `INVALID_TURN` | 1 | none; the same input |

(ADR 0013 D8; owner, DL-D9.) Backoff is wall-clock waiting only; the world
clock is frozen during a decision call (protocol §2). Each attempt is
recorded.

### 8.3 Fallback

When a decision call still fails, the fallback policy takes that one turn
(ADR 0013 D7). The next turn tries the model again.

| Pack | Fallback |
|---|---|
| `compat-v1` | The rule-based policy through the intent and perception adapters and the legacy bridge (protocol §11.2) |
| `starter-v1` | The same policy through the same adapters, reading **visible feedback only**: no bridge (protocol §11.2 limits the bridge to the compatibility pack) |

- **Visible-feedback mode** (owner, DL-D10). A pinned mode of the rule-based
  policy that reads only what its resident perceives. It is the starter
  pack's fallback, and it is the mode of both arms of the balance runs
  (starter content §9.1). It installs no bridge and reads no `ActionResult`,
  settlement or rule ID. Its result table is keyed only by the v1 intent the
  policy itself submitted and the resident-visible feedback:

  | Submitted v1 intent | Visible feedback | v1 result |
  |---|---|---|
  | Any intent, kernel or act (before verb rows) | failed | failure with the delivered failure_code |
  | Any intent, kernel or act | stopped | EXHAUSTED/PATH_BLOCKED → failure with that code; WOKEN → interrupted/URGENT_NEED; DEATH → interrupted/DEATH. Consume own_choice once under WAP §11.2. Starter FAINTED or TARGET_GONE clears the queue; defer fresh choice until eligible |
  | Kernel other than talk | done | success |
  | `gather` | `picks_fruit` / `too_tired` / `hands_full` / `finds_nothing` / `nothing_happens` | `success` / `EXHAUSTED` / `INVENTORY_FULL` / `RESOURCE_TAKEN` / `OUT_OF_REACH` |
  | `eat` | `tastes_good` / `not_hungry` / `nothing_happens` | `success` / `NO_NEED` / `NO_ITEM` |
  | `drink {source:"spring"}` | `drinks` / `not_thirsty` / `no_water_here` | `success` / `NO_NEED` / `OUT_OF_REACH` |
  | `drink {source:"canteen"}` | `drinks` / `not_thirsty` / `no_water_here` / `nothing_happens` | `success` / `NO_NEED` / `NO_WATER` / `NO_ITEM` |
  | `fill_canteen` | `fills_up` / `no_water_here` / `already_full` / `nothing_happens` | `success` / `OUT_OF_REACH` / `ALREADY_FULL` / `NO_ITEM` |
  | `rest`, `sleep` | `rests`, `sleeps` | `success` |
  | `talk` (the `wait` carrying it) | The wait's feedback joined with `last_utterance_feedback` | `success`, or `failure` with the utterance's code, as protocol §11.2's joined talk; the failure gives `ACTION_FAILED` and discards the queue, as v1 |
  | Anything else | Any other feedback | `failure` with `INVALID_TARGET`, which the policy backs off from |

  - Dispatch status before any per-verb row; the rows below stopped apply
    only to done. The wait and utterance of an actual talk form one private
    transition under CR-011, matched to their turn and legacy talk ID.
  - The join of a failed talk uses the resident's own utterance feedback,
    which it perceives, so no bridge is needed.
  - Triggers come from the perception adapter as protocol §11.2 maps them,
    including the matching of a delayed own-choice stop (WAP-30).
  - In the compatibility pack the table reproduces the bridge on every
    reachable case, because each compatibility check has its own phenomenon
    for the submitted action (starter content §4.3, §4.5). Starter content
    §9.1 checks this before the balance runs.
- In LLM fallback only, suppress a policy-selected talk before submission:
  send its ordinary one-tick wait without an utterance, clear the dependent
  plan tail and apply failed-talk back-off to the intended addressee at
  completion. The wait remains publicly successful if it completes; its
  feedback cannot advance a queued give. Record this private suppression
  under the intent ID; restore consumes it exactly once. A stand-alone
  calibration policy speaks normally.

- The policy keeps its internal queue across consecutive fallback turns and
  discards it when the model takes a turn again (`llm-decision-v0.1.md` §5),
  and at every waking-period boundary.
- **Fallback stays out of the resident's mind** (ADR 0013 D7; memory
  formation §1.3). Fallback turns carry no utterance, and their feedback is
  never written to the day log or the store, even when it arrives after the
  model has resumed. The objective log tags them (`agent_fallback_used`,
  protocol §9), and the decision records carry the origin of every intent.
  Evaluation never credits a fallback action to the resident (evaluation
  spec §3.1).
- The fallback rate per resident and day is a first-class metric
  (evaluation spec).

### 8.4 Operator stop

No call, token or cost cap applies (ADR 0012 D4). An operator can stop a live
run by a stop request (a file or a CLI command), which takes effect at the next
boundary: the run ends as incomplete, `operator_stop`, after its records are
committed (ADR 0013 Q3; owner, DL-D11). An optional cost alert warns the
operator when recorded spend passes a configured amount; it never stops the
run on its own.

## 9. Dialogue

- Each open dialogue session (`world-rules-v0.1.md` §4.2) has a small working
  state in the resident's runtime: the participants, the proposals addressed
  to the resident still unanswered, the last tick of the session, and whose
  reply is due (ADR 0013 D9).
- It is shown in the current state under the running action as "talking with
  …", with unanswered proposals in words.
- It is released when the session closes by the world's gap rule, or when the
  waking period ends, whichever comes first. It is built only from what the
  resident heard, never from the world's session or proposal index, so a
  released state is never rebuilt: after the boundary an old proposal returns
  only if someone speaks again.
- Only an accepted agreement becomes a commitment (memory formation §1); the
  working state is not memory.

## 10. Records and manifests

### 10.1 The context manifest

```text
ContextManifest {
  manifest_schema:"cm/0.1", call_kind:CallKind,
  resident_id, tick, period_id,
  sections:array<{section:string, entries:array<{source:Ref, sha256:Hash, tokens:integer}>}>,  // in request order
  derived:array<{kind:"pressure", counter_id, counter_version, wording_version,
                 counted:integer, window:integer, band:string, text:string}>,
  tokens_total:integer
}
CallKind = "decision"|"decision_after_recall"|"recall"|"morning"
         | "consolidation_selection"|"consolidation_change_set"
Ref = {kind:"template"|"schema"|"memory"|"day_log"|"current_state"|"pending_period"
           |"index"|"query"|"notice"|"pressure"|"mechanical_record", id:string, version:string|null}
```

- The manifest holds references only, never copies (ADR 0013 D10). Every part
  is content-addressed: templates and instructions by prompt version, the
  schema by the actual call kind's schema hash, the current state as the rendered part
  itself (stored once), the recall query as its own part, index lines by the
  store version they were built from.
- Keep ordered **full**, every measured **candidate** including the minimum
  **floor**, and **sent** only for an actual dispatch. Pin each part's
  rendered bytes, member path or memory revision, and provider framing. Pressure is computed on the full
  manifest without its own line (§5); replay recounts it from the full
  manifest with the pinned counter.

### 10.2 Call records

One record per logical call, of every kind, including calls that were never
dispatched or whose output was not adopted:

```text
CallRecord {
  record_schema:"cr/0.1", call_id, call_kind:CallKind, resident_id, tick, period_id,
  turn_id:string|null, consolidation_period:string|null,
  full_manifest:ContextManifest, sent_manifest:ContextManifest|null,
  candidates:array<{manifest:ContextManifest, wire_sha256:Hash, measured_tokens:integer,
                    omitted:array<Ref>}>,
  floor_candidate:integer|null, guard:{omitted:array<Ref>, notice:boolean,
    counter_id, counter_version, framing_version, model_window, reserve, floor_tokens, reason:string|null}|null,
  settings:{provider, model, prompt_version, schema_sha256, wire_adapter_version,
            max_output_tokens, temperature},
  outcome:"adopted"|"not_adopted"|"failed"|"stopped_unfit"|"abandoned",
  attempts:array<{n:integer, request_sha256:Hash, started_at, ended_at:timestamp|null,
                  error_class:string|null, raw_output_ref:Hash|null,
                  parsed_ref:Hash|null, tokens:{input:int|null,output:int|null,cache_hit:int|null,cache_miss:int|null}|null,
                  missing_usage_reason:string|null, latency_ms:integer|null}>
}
```

- `request_sha256` covers the exact wire request bytes of that attempt. Those
  bytes are kept once in the audit's content-addressed store, as P3 keeps its
  journal (`llm-decision-v0.1.md` §4.3); replay rebuilds them from the sent
  manifest, the settings and the pinned wire adapter, and checks the hash.
- Store candidate/floor counted wire bytes by hash even for no-dispatch.
  When cancelled before preparation, record the frozen full parts and stage,
  with empty candidates and null floor/guard. After prepare and before
  dispatch, sent stays null. Journal dispatch before I/O, terminal usage
  and error on return; unresolved/unsupported measurements stay null with
  a reason. Restoring an already dispatched attempt consumes the journal
  terminal or P3 interrupted disposition without blind resend. An abandoned
  workflow can have zero or more dispatched attempts, with a late terminal
  retained only for accounting. Seal at the deterministic MF §7 boundary.
- `stopped_unfit` has no attempt (§7.1); `abandoned` is a consolidation call
  whose period was interrupted (memory formation §3.1).

### 10.3 The decision record

```text
DecisionRecordV2 {
  record_schema:"dr/0.1", turn_id, resident_id, tick, period_id, reasons:array<string>,
  call_ids:array<string>,                    // decision, recall, decision_after_recall, in order
  new_entries:array<string>,                 // day-log entry IDs written at this turn
  output:TurnOutput|null,                    // the adopted output
  valid_cites:array<string>, invalid_cites:array<string>,
  cited_parts:array<{id, act_call_id, sent_part_sha256, revision:string|null}>,
  telemetry:{delivery_id, awake_ticks, fatigue_band:string|null,
             stages:array<{call_id, full_tokens, pressure_band, pressure_text,
                           omitted:array<Ref>}>},
  use_updates:array<{record_id, revision, call_id, before_version, after_version}>,
  origin:"model"|"fallback"|null,             // null when no turn committed
  fallback:{used:boolean, reason:string|null, policy_id:string|null},
  submission:TurnSubmission|null,                 // what reached the world
  used_memories:array<string>                // records whose use counters changed
}
```

- One record per turn, including fallback turns and turns that stopped
  unfit. The morning call and consolidation calls have their own call records
  (§4.2; memory formation §7).
- For each scheduled turn, even on failure, record the delivery ID and
  tick/period, consecutive awake ticks from interval history, fatigue band
  from the delivered need (null if disabled), full decision tokens,
  pressure band/text and guard refs per decision stage. Retain selected
  versus actually sent memory revisions and use-update links. No-dispatch
  turns have no submission, adopted act, origin or outcome event. Every
  logical call (including morning) is independently indexed by run,
  resident and call ID with its turn/period parent. A recall step has three
  call IDs only when a recall call actually ran; off_empty joins the two
  decision calls and its typed local entry. Persist all exact packet
  deliveries including no-turn intervals (EN §2), plus ordered event/member
  and revision links for inspection. Audit access is analysis-only.

- A turn with a dispatched deliberate recall joins three calls in order; the recall query is a part
  of the `recall` call's manifest, so the turn's `act` output alone is never
  needed to rebuild it.

### 10.4 Replay and saves

- Replay rebuilds every request of every call kind from the stored parts,
  checks its hash, recomputes pressure from the full manifest, applies the
  recorded output or fallback choice, and makes no model call (protocol §12).
- A save holds each resident's runtime: the open working context's parts and
  entry counter, the dialogue states, the mute list, the policy queue during
  fallback, the shared adapter's receipts/deferred triggers and origin map, seen
  turn/record use keys, and MF §7's frozen inputs, stage and journal cursors. Saves are taken at completed
  boundaries only (protocol §5.3; `interface-contract-v0.1.md` §5).
- A decision or consolidation call outstanding at a save is handled as P3's
  interrupted calls (`llm-decision-v0.1.md` §7.2): it is either committed
  before the checkpoint or replayed from its journal, never billed twice.

### 10.5 Run composition

`sim` composes a run from packs and an agent configuration and refuses a
combination that breaks a cross-spec rule before tick 0: the pack's
`faint_ticks` must be at least the agent configuration's K (world engine
§9.3; memory formation §2). The world's content loader never reads K.

## 11. The memory-off arm

At the period boundary (memory formation §2), in the off arm, code resets:

| Reset | How |
|---|---|
| Day log and prefix | The new working context starts empty, with no prefix memories |
| Intention | The current one is set to `reset` (memory model §9) |
| Dialogue state | Released (§9); never rebuilt from the world's sessions |
| Recall | Recipes return nothing; a `recall` step gets the empty entry (§6.3) |
| Fallback policy state | Its queue and back-off are discarded (§8.3) |
| Pending consolidation state | None exists: no calls run |

The resident keeps its identity, its base personality, its body and
inventory, what it perceives now and its explored map, which is
world-delivered static data, including tiles now out of sight (ADR 0007 D4).
Within one period nothing is reset, so an intention set before a nap is still
there after it. Mechanical records are written but never shown; inspection
still reads them. The arm is recorded with the run.

## 12. Determinism

- Turn scheduling, notification classes, muting, recipes, strength, the
  guard, pressure and every template are pure functions of recorded inputs.
- Model outputs are the only nondeterministic inputs; they are recorded.
- Replay with the same records, content and pinned code gives the same
  submissions, the same world events and the same records.

## 13. Acceptance tests

| ID | Test |
|---|---|
| DL-01 | Turn reasons: a resident gets a turn at tick 0, on waking, when its action ends and on an unmuted notification; never while asleep or unconscious; one turn per boundary with every reason listed |
| DL-02 | Classes: each report kind maps to its class; `action_observed` writes an observation entry and gives no turn |
| DL-03 | Muting: a muted class gives no turn but its entry is written; the list clears when the action ends or is replaced and survives `continue`; a critical-band hunger or thirst notification gives a turn whatever the list |
| DL-04 | Output: each `TurnOutput` form parses; identity fields from the model are ignored and filled by the harness; a too-long field is a shape error; `intention`, `mute` and `cite` never reach the world |
| DL-05 | Prefix: the morning selection runs at waking, picks at most 20 IDs, and is skipped at tick 0 and in the off arm; open commitments are not forced in |
| DL-06 | Day log: each entry type is written from its source with its template; unchanged surroundings are not logged again; a muted observation is logged; a non-adopted response and a fallback turn write nothing |
| DL-07 | No hidden data: a request never contains true values, rule IDs, settlement kinds, bridge output, raw agreement facts or identifiers from objective-only paths (with protocol WAP-01 and WAP-25); speech IDs actually delivered remain usable |
| DL-08 | Pressure: the band follows the integer thresholds; the line is not counted in itself; replay recomputes it and refuses with another counter version |
| DL-09 | Strength and recipes: strength follows §6.1; each recipe returns the strongest eligible records, at most 5 per turn, never twice in a period, never history |
| DL-10 | Deliberate recall: one recall per turn reaches only records with strength at least 40, appends up to 5, and the turn then returns `act`; a second recall is a shape error |
| DL-11 | Guard: an oversized request leaves out the oldest entries first, keeps the newest 20, then prefix memories; adds the notice, counted before dispatch; records full and sent manifests; pressure stays computed on the full context; no fallback is used |
| DL-12 | Errors: each class is retried as §8.2; after the last retry the fallback takes the turn; the next turn tries the model |
| DL-13 | Visible-feedback mode: every row of the §8.3 table gives its code from the submitted intent and visible feedback only, with no bridge installed; a canteen and a spring drink both seeing `no_water_here` give `NO_WATER` and `OUT_OF_REACH`; a failed talk joined from the utterance feedback discards the queued give; a delayed own-choice stop is not passed on twice; on `compat-v1` the mode equals the bridge-backed policy on the WAP-23 fixtures; in `compat-v1` the ordinary fallback still uses the bridge |
| DL-14 | Fallback isolation: model, then fallback, then model again, with a restore before acknowledgement (with protocol WAP-25 and memory formation MF-15): the resumed request has no fallback entries, no fallback utterance was spoken, and a delayed fallback stop is not logged; the decision records carry each intent's origin; the objective log tags the fallback turn |
| DL-15 | Dialogue state: opened by addressed speech, shows unanswered proposals, released by the gap rule or the period end, and never rebuilt from the world's session |
| DL-16 | Records: every call of all six kinds has a full manifest and a sent manifest only on dispatch, including a failed morning call, a `stopped_unfit` decision and an abandoned consolidation; requests rebuild byte for byte from stored parts and settings; pressure recomputes from the full manifest; a deliberate recall's query is rebuilt from its own call record; the whole run replays with zero model calls |
| DL-17 | Memory off (ADR 0014 D2's synthetic test): after a period boundary the off-arm context has no intention, no dialogue state, no prefix memories, empty recall (a `recall` step gets the empty entry and a second decision call) and no fallback queue, and keeps position, inventory, visible surroundings and the explored map, including tiles now out of sight. Controls: an intention set before a nap survives the nap; an exact K sleep resets; an unfinished dialogue whose gap outlasts the sleep is not revived; a commitment record stays in the store for inspection and is never shown |
| DL-18 | Operator stop: a stop request ends the run at the next boundary as incomplete with its records committed |
| DL-19 | A registered test recall recipe is selected by its turn reason (ADR 0014 D3) |
| DL-20 | Pre-dispatch (§7.1): for each call kind a request whose floor exceeds `W` is not dispatched, gets `stopped_unfit` with the measured floor and stops at its applicable boundary (§7.1); a request that fits only without its notice is treated as not fitting until the notice is counted; the P3 byte cap does not refuse an admitted request |
| DL-21 | Citations: a cited day-log entry the guard kept and a cited memory in the sent request are valid; an omitted entry, an unknown ID and a memory never sent are invalid and ignored |
| DL-22 | Commitment cues: a silent counterpart in sight and a due tick within 24 ticks each recall the open commitment, whatever its strength |
| DL-23 | Day log: an `inspection` entry keeps the `on_inspect` words; a watched action gives one entry per phase; heard speech is never cut and its `verbatim` equals the delivered utterance; every entry's `ref` points to its delivered item |
| DL-24 | Run composition: a starter pack with `faint_ticks = 35` and K = 36 is refused by `sim` before tick 0 |
| DL-25 | Calibrate both policy modes on EXHAUSTED gather, WOKEN sleep, generic NO_ITEM, failed talk, deferred novelty and restore. Suppressed fallback accept becomes a silent wait and discards the queued give. FAINTED clears a starter queue. |
| DL-26 | Fallback action visible while running; filter delayed results before outcome-specific recall, context and evidence. Short wake preserves prefix, successful K or failed consolidation opens it once; death at K has no morning call. |
| DL-27 | Rebuild full, counted candidates/floor and any sent request of all six kinds from pinned parts. Recount pressure/notice/framing. No-dispatch has null submission and no attempt; abandoned in-flight retains a nullable terminal and journal cursor. |
| DL-28 | Use credit once for first decision dispatch per record/turn across retries; guard omission and never-dispatch get zero. Join recipe/off-empty recall without a call and cite the rendered current intention in both arms. |
| DL-29 | Export no-turn packet, watched members and exact skill-evidence revision; resolve a failed turn's telemetry, available cache counts and the morning call by index alone. |
| DL-30 | Index-only, omitted or later-revised memory cannot substitute for the fragment cited in the adopted act request. A commitment projection never exposes the raw acceptance ID. |

## 14. Disposition of open questions

| Question | Disposition |
|---|---|
| ADR 0013 Q1 Templates and observation thresholds | §4.3, owner DL-D3; wording is exploration-lane work with pinned versions |
| ADR 0013 Q2 Morning selection and prefix limit | Separate call at waking, 20 records, owner DL-D2 (§4.2) |
| ADR 0013 Q3 Operator budget or kill switch | Operator stop and optional alert, no cap, owner DL-D11 (§8.4) |
| ADR 0013 Q4 Pressure and guard | §5, §7, owners DL-D5 and DL-D7 |
| ADR 0013 Q5 Strength, threshold, N, recalls per turn | §6, owner DL-D6 |
| ADR 0013 Q6 Notification classes and progress steps | §2.2, owner DL-D1 |
| ADR 0013 Q7 Request format | Structured JSON output, confirmed by a live check, owner DL-D8 (§8.1) |
| ADR 0013 Q8 Different memory abilities | Later direction; not in this version |
| ADR 0007 D4 Rendering explored terrain | A character grid of the explored area, owner DL-D4 (§4.4) |
| Protocol §3.1 recovery from `INVALID_TURN` | One retry, then fallback (§2.4, §8.2) |

## 15. Owner decisions (recommended answers applied)

| ID | Question | Recommended answer, applied in this draft | Why |
|---|---|---|---|
| DL-D1 | Notification classes and progress | Five classes (`body`, `direct_speech`, `nearby_speech`, `discovery`, `progress`); watched actions give no turn; progress at thirds of the work | Matches ADR 0013 D3; watching cannot flood a resident with turns |
| DL-D2 | Morning selection and prefix limit | A separate call at waking; at most 20 records | Works after failed consolidations too; the upper end of the starting range |
| DL-D3 | Which perceptions become observation entries | First sightings, cue upgrades, watched actions, and visible entities whose look changed | Logs what is new or different, never unchanged surroundings |
| DL-D4 | How explored terrain is shown | A character grid of the explored area in the current state | Compact, readable, and the same in both memory arms |
| DL-D5 | Pressure bands | Five bands at 5%, 15%, 30% and 50% of the usable window | Rises well before the window is near, as ADR 0013 D4 requires |
| DL-D6 | Strength, threshold, N, recalls per turn | §6.1 formula; recipes reach strength 20 and deliberate recall 40; at most 5 records; one deliberate recall per turn | Faded memories stay reachable by cues, as ADR 0013 D5 describes |
| DL-D7 | What the guard leaves out first | Oldest day-log entries, keeping the newest 20; then prefix memories | Keeps the most recent context and the current state |
| DL-D8 | Request format | Structured JSON output, schema sent once, confirmed by a live check | The P3 path, minus the second schema copy (ADR 0007 D7) |
| DL-D9 | Retries | Timeout and server errors 3, rate limits 5, invalid output 1 | Bounded, and fallback stays a last resort (ADR 0013 D8) |
| DL-D10 | The fallback in the starter pack | The rule-based policy reading visible feedback only | The protocol keeps the bridge to the compatibility pack; phenomena carry enough for the policy |
| DL-D11 | Operator control | A manual stop at the next boundary and an optional cost alert; no automatic cap | ADR 0012 D4 sets no cap; a person can still stop a run |
