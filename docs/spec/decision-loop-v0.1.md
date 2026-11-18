# Living Island — Context Assembly and Decision Loop v0.1 (P3.5)

> **Draft (2026-11-18), task P3.5-SP-01. Not frozen.** Owner decisions are
> written with the author's recommended answer applied and are listed in
> §15 and in the [decision sheet](../tasks/p3.5/P3.5-SP-01-decisions.md).
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

## 3. The model's output

```text
TurnOutput = {step:"recall", query:string}                  // at most once per turn (§6.3)
           | {step:"act",
              action:{kind:"continue"} | {kind:"intent", intent:IntentChoice},
              utterance:UtteranceChoice|null,
              intention:{set:string} | {clear:true} | null,
              mute:array<NotificationClass>,               // only with a new intent
              cite:array<string>}                           // memory IDs; agent side only
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
  written to the store (memory model §3.6); `cite` is checked by evaluation
  against the manifest (ADR 0013 D10).
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
  (ADR 0013 Q2; owner, DL-D2): it also runs after a failed or abandoned
  consolidation, and its input is the store as it stands at waking.
- **Prefix limit:** at most 20 records (owner, DL-D2), from the soft range of
  8–20 in ADR 0013 D4. Open commitments are not forced in.
- At tick 0 and in the memory-off arm no call runs: the prefix holds no
  memories.

### 4.3 The day log

Every entry has a type, the tick it describes, an ID `d:<period_id>:<n>` and
its text. Entries are stored once by content hash (ADR 0013 D10).

| Type | Written from | Template (fixed wording, pinned version) |
|---|---|---|
| `own_response` | An adopted `TurnOutput` | The response exactly as returned |
| `action_result` | An `action_feedback` entry | "Your {action} ended: {status}{, failure}. {phenomena texts}" |
| `utterance_result` | A failed `last_utterance_feedback` | "Your words to {addressee} were not said: {reason words}" |
| `heard_speech` | A heard utterance | "{speaker} said to {you/addressee/everyone}: "{text}"" plus terms in words |
| `observation` | A first sighting, a cue, a watched action, or a changed look of a visible entity | "You see …", "You notice …", "{actor} {verb}s {items}: {phenomena}" |
| `body_change` | A band change or threshold crossing | "You feel {band words}" |
| `progress` | A progress step | "Your {action} is {progress word}" |
| `sleep` | Falling asleep, waking | "You fall asleep." / "You wake." |
| `recall` | A recall result | "You remember: {gist}. {text}" per record, with its ID |

- **Observations** (ADR 0013 Q1; owner, DL-D3): an entry is written for every
  `entity_first_seen` report, every cue upgrade, every `ObservedAction`, and
  every visible entity whose descriptors differ from those of its last
  observation entry in this period. An unchanged surrounding is never logged
  again (ADR 0013 D4).
- World entries are at most 1000 characters; a longer rendering is cut at a
  word boundary with "…". `own_response` entries are never cut; the schema's
  length limits bound them.
- Entries hold only what the resident received. Nothing from hidden state,
  the bridge or the party fact feed enters (protocol §5.1, memory formation
  §1.1).
- An observation delivered while muted is written all the same.
- A response that was not adopted (retried or replaced by the fallback) is
  not written (ADR 0013 D4). Fallback turns write no entry (§8.3).

### 4.4 The current state

Rendered at every turn, in this order:

1. The turn's reasons in words.
2. Body: each need band as words; mental fatigue as its own words.
3. Context pressure as its own words (§5), separate from fatigue.
4. Position, time of day and awareness.
5. Inventory: each item with its look and quantity.
6. The running action and its progress, and its mute list.
7. The current intention, or "none".
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

Strength is 0–160. A record is **used** when it enters a context, through the
prefix or a recall: `last_used_tick` becomes the current tick and `use_count`
increases by one, as a deterministic update recorded with the manifest.
Unused records weaken, and consolidation may forget weak ones (ADR 0013 D5).
Strength is internal to recall; the index line stays as memory model §2.1
defines it.

### 6.2 Recipe recall

At every turn, before the request is built, code recalls by the turn's reasons
(ADR 0013 D5). Each recipe reaches records with strength at least 20, takes the
strongest first (then the lowest ID) and appends at most 5 records per turn in
total, skipping records already recalled or in the prefix in this period.
History records are not recalled by recipe.

| Turn reason | Recalled |
|---|---|
| `action_ended` of an `act` | Live skills with that verb; skills whose `expected` includes a phenomenon in the feedback |
| `direct_speech` or `nearby_speech` | The speaker's social record; open commitments with the speaker; beliefs whose subject is the speaker |
| `body` for satiety or hydration | Beliefs with the topic `food` (satiety) or `water` (hydration) |
| `discovery` | Beliefs whose subject is the seen entity or its archetype; skills whose looks name its archetype or material |

A registered memory kind may register its own recipes (ADR 0014 D3; memory
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
- **Request fit** (P3.5 brief §11). With the entry caps of §3 and §4.3, the
  minimum mandatory decision request is at most about 60,000 tokens, far
  inside `W`. A morning selection or recall request holds the index (memory
  model §7: at most about 900 lines) and fits too. A request whose minimum
  still does not fit stops the run as incomplete, with that reason recorded;
  the guard never drops a mandatory part, summarizes by model, makes a
  resident sleep or invokes the fallback (ADR 0013 D4).
- Every guard action is recorded with the manifests before and after; the
  inspection view shows it.
- Pressure still reflects the full context, not the shortened request.

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

- **Visible-feedback mode** (owner, DL-D10). The perception adapter maps
  the resident-visible `action_feedback` to the v1 result the policy expects:
  kernel failures keep their codes; an `act` whose phenomena are the matching
  compatibility rule's `success` list is `success`; otherwise the
  `unmet_by_check` phenomenon gives the code: `too_tired` → `EXHAUSTED`,
  `hands_full` → `INVENTORY_FULL`, `finds_nothing` → `RESOURCE_TAKEN`,
  `not_hungry` and `not_thirsty` → `NO_NEED`, `no_water_here` →
  `OUT_OF_REACH` for a spring drink or a fill, `NO_WATER` for a canteen drink,
  `already_full` → `ALREADY_FULL`. Any other outcome is `failure` with
  `INVALID_TARGET`, which the policy backs off from. The starter pack's
  compatibility rules have distinct phenomena per check for this reason
  (starter content §4.3).
- The policy keeps its internal queue across consecutive fallback turns and
  discards it when the model takes a turn again (`llm-decision-v0.1.md` §5).
- **Fallback stays out of the resident's mind** (ADR 0013 D7). Fallback turns
  write nothing to the day log or the store, apart from mechanical writes.
  The objective log tags them (`agent_fallback_used`, protocol §9).
  Evaluation skips them.
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
  waking period ends, whichever comes first.
- Only an accepted agreement becomes a commitment (memory formation §1); the
  working state is not memory.

## 10. Records and manifests

### 10.1 The context manifest

```text
ContextManifest {
  manifest_schema:"cm/0.1", call_kind:"decision"|"recall"|"morning"|"selection"|"change_set",
  resident_id, tick, period_id,
  sections:array<{section:string, entries:array<{source:Ref, sha256:Hash, tokens:integer}>}>,
  derived:array<{kind:"pressure", counter_id, counter_version, wording_version,
                 counted:integer, window:integer, band:string, text:string}>,
  guard:{omitted:array<Ref>, notice:boolean}|null,
  request_sha256:Hash, tokens_total:integer
}
Ref = {kind:"prefix_part"|"memory"|"day_log"|"perception"|"pending_period"|"index", id:string}
```

The manifest holds references only, never copies (ADR 0013 D10).

### 10.2 The decision record

```text
DecisionRecordV2 {
  record_schema:"dr/0.1", turn_id, resident_id, tick, period_id, reasons:array<string>,
  manifests:array<ContextManifest>,          // one per call of the turn
  call_ids:array<string>,                    // recorded model calls
  new_entries:array<string>,                 // day-log entry IDs written at this turn
  output:TurnOutput|null,                    // the adopted output
  fallback:{used:boolean, reason:string|null, policy_id:string|null},
  submission:TurnSubmission,                 // what reached the world
  used_memories:array<string>                // records whose use counters changed
}
```

- Model calls are recorded with input manifest, prompt version, model, raw
  output, parsed output, tokens, cache hits and latency, in the P3 call-log
  form (`llm-decision-v0.1.md` §4.3), plus `call_kind`.
- Parts are stored once by content hash; a record stores its manifest, the
  new entries and the output. The exact request bytes are rebuilt from the
  parts and checked against `request_sha256` (ADR 0013 D10).

### 10.3 Replay and saves

- Replay rebuilds every request from the stored parts, checks its hash,
  applies the recorded output or fallback choice, and makes no model call
  (protocol §12).
- A save holds each resident's runtime: the open working context's parts and
  entry counter, the dialogue states, the mute list, the policy queue during
  fallback, and outstanding consolidation calls. Saves are taken at completed
  boundaries only (protocol §5.3; `interface-contract-v0.1.md` §5).
- A decision or consolidation call outstanding at a save is handled as P3's
  interrupted calls (`llm-decision-v0.1.md` §7.2): it is either committed
  before the checkpoint or replayed from its journal, never billed twice.

## 11. The memory-off arm

At the period boundary (memory formation §2), in the off arm, the new working
context starts with no earlier day log, no intention, no dialogue state, no
prefix memories, and recall that returns nothing (ADR 0014 D2). The resident
keeps its identity, its base personality, its body and inventory, what it
perceives now and its explored map. Mechanical records are written but never
shown. The arm is recorded with the run.

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
| DL-07 | No hidden data: a request never contains true values, rule IDs, settlement kinds, bridge output or party-feed facts (with protocol WAP-01 and WAP-25) |
| DL-08 | Pressure: the band follows the integer thresholds; the line is not counted in itself; replay recomputes it and refuses with another counter version |
| DL-09 | Strength and recipes: strength follows §6.1; each recipe returns the strongest eligible records, at most 5 per turn, never twice in a period, never history |
| DL-10 | Deliberate recall: one recall per turn reaches only records with strength at least 40, appends up to 5, and the turn then returns `act`; a second recall is a shape error |
| DL-11 | Guard: an oversized request leaves out the oldest entries first, keeps the newest 20, then prefix memories; adds the notice; records manifests before and after; pressure stays computed on the full context; no fallback is used |
| DL-12 | Errors: each class is retried as §8.2; after the last retry the fallback takes the turn; the next turn tries the model |
| DL-13 | Fallback in `compat-v1` uses the bridge; in `starter-v1` the visible-feedback mapping gives the stated codes from phenomena and never reads the bridge |
| DL-14 | Fallback isolation: model, then fallback, then model again (with protocol WAP-25): the resumed request has no fallback entries; the objective log tags the fallback turn |
| DL-15 | Dialogue state: opened by addressed speech, shows unanswered proposals, released by the gap rule or the period end |
| DL-16 | Records: every call has a manifest; requests rebuild byte for byte from stored parts; a decision record replays with zero model calls |
| DL-17 | Memory off: after a period boundary the off-arm context has no intention, no dialogue state, no prefix memories and empty recall, and keeps position, inventory, visible surroundings and the explored map (ADR 0014 D2's synthetic test) |
| DL-18 | Operator stop: a stop request ends the run at the next boundary as incomplete with its records committed |
| DL-19 | A registered test recall recipe is selected by its turn reason (ADR 0014 D3) |

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
