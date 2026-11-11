# Living Island — P2 Implementation Plan v0.1

> **Approved v0.1 (2026-11-10).** The owner approved this plan. Decisions are tagged **[C]**
> (confirmed by the owner) or **[P]** (direction approved; P2-00 fixes the details in specs
> and the owner signs them off at M5). Until P2-00 merges, the P1 specs stay unchanged.
>
> **Amendment 1 (owner, 2026-11-10):** PD-08 changed. Frontend design and implementation
> (P2-F0, P2-F1, milestone MF) are inserted after P2-03 and before P2-04.
>
> **Amendment 2 (owner, 2026-11-11):** the separate design-approval step is replaced by
> direct implementation. P2-F0 is folded into P2-F1: the style is chosen by the owner
> (warm top-down pixel art, concept "A"), no alternative style options are produced, and the
> design spec is written alongside the code. MF moves from "before P2-F1" to the owner's
> review of the working viewer at the end of P2-F1. Gate 1 and Gate 2 are unchanged. The
> owner's instruction is quoted in `docs/tasks/p2/P2-F1.md`.
>
> **MF accepted (owner, 2026-11-11):** the owner reviewed the working P2-F1 viewer and
> authorized acceptance and merge into local `main`. P2-F0's folded deliverables, the
> frontend design spec and ADR 0005 are accepted with the documented desktop limitations
> and P2 treatments of OQ-079 through OQ-081. See `docs/tasks/p2/P2-F1.md` for the sign-off.
>
> **M6 accepted (owner, 2026-11-11):** the default scenario uses the three approved S1
> spawn positions. `s2-default:m6` is pinned to `7c13d78`. P2-04 completed all 42 cases
> in the owner-approved six-seed development matrix (OQ-060). See
> [P2-04](../tasks/p2/P2-04.md) and its [experiment report](../tasks/p2/P2-04-report.md).
>
> **P2-05 technical acceptance:** all 20 held-out runs passed technical validation and
> all three residents survived to tick 1,008 in all 20 runs. Checkpoint recovery,
> recorded re-execution and independent review passed. The owner replay walkthrough and
> M7 sign-off are pending. See [P2-05](../tasks/p2/P2-05.md).

**Milestone P2, "Residents Survive":** on the default island, three rule-based residents
survive seven game days together in most registered test seeds, using only their own
perception. Under scarcity, contention and adaptation are observable. The canteen works and
its benefit is measured.

**Baseline:**
- `docs/spec/world-rules-v0.1.md`, `interface-contract-v0.1.md`, `balance-notes-v0.1.md`,
  `agent-interface-v0.1.md`, `p1-replay-frontend-v0.1.md` as on `main` at P1 completion;
- M4 verification commit `6d90824` for the original P1 inputs and recorded hashes;
- ADR 0002 (balance changes edit TOML only; PD-04 requires separate approval for a map
  placement change) and ADR 0003;
- the P1 plan's gates, task cards, handoff fields and change-request steps (§4–§7).

## 0. Decisions

### 0.1 Product decisions

| ID | Decision | Status |
|---|---|---|
| PD-01 | P2 passes when, on the default island, all three residents are alive at tick 1008 in most registered acceptance seeds, using only their own perception. | [C] |
| PD-02 | Under scarcity, traceable contention or adaptation must appear (for example a resident switching target after a tree empties). Forced action failures are not required. | [C] |
| PD-03 | The canteen must be used and transferred correctly, and its benefit must be measured. A small benefit does not block P2. | [C] |
| PD-04 | The original default map is run first. A small placement change is reviewed separately, only with evidence, and needs owner approval. | [C] |
| PD-05 | At least 15 of 20 registered acceptance seeds end with all three residents alive at tick 1008. All acceptance runs must also pass the technical checks (§1.1). | [P] |
| PD-06 | The private-state boundary of the rule policy (§1.2). | [P] |
| PD-07 | The canteen comparison design (§1.3). | [P] |
| PD-08 | Frontend design and implementation run after P2-03 and before P2-04: a design spec signed off at MF (P2-F0), then its implementation on the existing replay contract (P2-F1). Amended by the owner on 2026-11-10; it replaces "after M7". Amended again on 2026-11-11 (Amendment 2): P2-F0 is folded into P2-F1, and MF is the owner's review of the working viewer. | [C] |

### 0.2 Management decisions (unchanged from P1)

- At most two active workers, reviewers included. One task = one branch and one worktree.
- Gate 1 and Gate 2 for every task. Gate 3 at the P2 milestones in §4.
- Seven handoff fields. Unknown values are written as unknown, never as zero.
- Spec contradictions go through a change request. Downstream agents never edit frozen
  contracts.

**P2 scope exclusions:** LLM policies, the memory system (P4), relationships, animals, tools
other than the canteen, dreams and WebSocket live view. Frontend work is limited to P2-F0
and P2-F1: display only, on the existing replay contract, with no contract or backend
change.

## 1. Design and acceptance decisions

### 1.1 Acceptance seeds and thresholds

- **[P]** Register disjoint development and acceptance seed lists before tuning. P2-02
  and P2-04 use development seeds; P2-05 uses the held-out list after M6 freezes the
  candidate. If tuning uses any acceptance result, register a fresh held-out list before
  evaluating the revised candidate. Keep the prior results in the report.
- **[P]** Test technical validity first. Every registered run must complete tick 1008,
  produce valid required artifacts and invariants, and record zero policy-error
  substitutions. An invalid run fails the technical gate. Among valid runs, a survival
  pass means all three residents have `alive=true` at tick 1008. Require at least 15 of 20.
- **[P]** Fix the score and canonical ordering of eligible targets in P2-00. Break ties
  between genuinely equal candidates with a stable hash derived from the seed, actor ID,
  decision ordinal and a documented tie-break domain. Use the existing `random-v0`
  construction as a reference. The policy uses no world resolution RNG and does not
  override a higher-priority action to create variation.
- Report behavioral variation using first spring discovery, exploration routes and
  survival outcomes. The initialized event contains a seed-dependent config hash, so
  different event-log hashes do not establish different behavior. Behavioral variation is
  diagnostic; there is no diversity quota. Report the observed fraction and a 95% Wilson
  interval with its sampling assumptions. At 15/20 it is approximately 53–89%; the gate
  is evidence on this registered seed set, not a guarantee over other worlds or policies.
- Measure the rule policy on development runs before estimating the time for the full
  matrix. P1 random-policy timings are a reference only.

### 1.2 Perception and the policy's private state

Facts from P1:
- `Perception.explored_static_tiles` already carries the world-owned exploration footprint.
  Once seen, the spring tile, the tree patches and the moss tile stay there.
- So the policy needs **no private map memory**, and must not build one.
- Cue detail (`EnvironmentalCue.direction`) and tree stock bands are delivered only while
  observed. Remembering them is subjective state.

**[P] Allowed inputs:**
- `DecisionContext`: perception, own profile and own goals;
- the frozen `PolicyConfig` fields, plus any rule parameters added by CR-004;
- the policy's own `policy_state`.

**Forbidden inputs:**
- content files, the map, `world.spring` coordinates, other residents' state, the event log,
  `WorldState`;
- constants tuned to the default map, such as "walk east from (15, 32)". The cue is used
  only through its DTO fields (`position`, `detail_level`, `direction`).

**[P] Minimal `policy_state`.** Use a typed, bounded, versioned JSON shape with canonical
serialization and restore validation. P2-00 specifies limits, eviction and expiry:
- `commitment`: the current goal kind and target, to prevent oscillation between goals;
- issued-intent references that link the policy's recent `intent_id` values to their own
  planned targets. `ActionFeedback` carries the intent ID and failure code without the
  target. Specify retention through queued actions and restore. Back off only on a matching
  reference, and define the outcome for unmatched feedback;
- `failed_targets`: target, failure code and retry-after tick;
- `cue_impressions`: cue ID, highest detail actually observed, and any delivered direction.

Update impressions from perceptions presented at `decide`. `Runtime.ingest` runs at each
boundary, but P1 passes only the latest perception to a policy when it decides. If P2-00
finds that cues from intermediate, non-decision boundaries must persist, CR-004 must also
specify the ingestion hook, exactly-once capture and how recorded re-execution reproduces
any effect on request hashes. Keep private navigation state outside `DecisionContext` in
the initial design. Use observed stock bands as current evidence and static tiles for map
knowledge. Defer historical tree-stock tracking. Own condition thresholds use the exposed
bands (`OwnCondition`).

**Required CR (CR-004), raised by P2-00:**
- add `rule-based-v0` to `PolicyId` (`agents/types.py:35`, Agent Interface §2.5);
- let the `ResidentRuntimeState` validator (`agents/types.py:293`) accept the rule policy's
  `policy_state` schema;
- define the rule-only parameters and their canonical identity, including experimental
  switches; retain them in saved `PolicyConfig` and validate them against the source run
  on restore. Specify how existing P1 policy configurations and saves remain compatible.
  A world config hash alone does not identify a policy-only setting.

The replay contract has no `PolicyId` field (only `fallback_policy_id`), so the generated
frontend types should not change. P2-01 verifies this.

### 1.3 Confounds in the canteen comparison

The first round compares **canteen enabled** with **canteen restricted** at hydration decay
100. In the restricted arm the policy never drinks from, fills, gives or requests the
canteen. The entity and its initial slot remain. Remaining confounds and how to handle them:

1. **Initial servings.** The restricted arm also gives up the starting water. This is part
   of the treatment; report it, and do not try to remove it.
2. **Slot occupancy.** Both arms occupy one slot at the start. In the enabled arm a transfer
   moves the slot to another resident. Report slot-full incidents per holder.
3. **Pick-up after a death.** **[P]** In the restricted arm the canteen is never picked up,
   so the restriction stays symmetric across holders.
4. **Divergence.** After the first different action, contention and the shuffle diverge.
   Compare run-level aggregates per seed pair, never tick-by-tick.
5. **Deaths shorten exposure.** Report absolute run totals, per-resident rates per living
   tick, and deaths together. A nonholder dying is never counted as canteen benefit
   (World Rules §9).
6. **Policy variant identity.** Retain the saved `PolicyConfig` restriction and record its
   settings or canonical hash separately from the world config hash. Verify recorded
   re-execution in both arms.
7. **Hydration 120.** **[P]** Repeat the paired comparison at decay 120 using the same
   registered development seeds, geometry, speed and policy version (Balance Notes §5,
   item 3). If measured runtime warrants deferral, record the reason and obtain the
   owner's OQ disposition before M6. The 120 trial does not select the default by itself.
8. **A true no-canteen arm** needs an experimental fixture with an invariant exception
   (Balance Notes §5, item 3). A map with no cue also needs an approved exception to the
   single `M` requirement. The initial design keeps both invariants and labels its
   comparisons as policy restrictions.

### 1.4 Task dependencies

- P2-01 must land before P2-02, because the policy ID and save support come first.
- P2-03 depends only on P2-00. It can run alongside P2-01 and P2-02 only while no review
  holds the second slot.
- **OQ-049** is non-blocking. Keep the existing `run_id` behavior. The experiment tool
  assigns a separate experiment-case identifier and a distinct output directory per run,
  using seed, scenario and policy variant in its manifest.
- **OQ-053:** run P2's new long experiment matrix explicitly outside default CI. Keep the
  existing P1 CI coverage. Review any move of the existing long P1 integration test as a
  separate, measured CI decision.
- OQ-051 and OQ-052 have no P2 dependency. They stay deferred unless the owner pulls them
  in.

## 2. Tasks

### P2-00: Policy spec and experiment design (documentation only)

- **Lane:** first; no other P2 task starts before it merges.
- **Files:** a new `docs/spec/rule-policy-v0.1.md`; a new `docs/spec/p2-experiments-v0.1.md`;
  the CR-004 entry in `open-questions.md`; proposed amendments and an ADR 0004 draft.
  Apply only the contract changes approved at M5 before merging P2-00. No code, content
  or default config.
- **Deliverables:**
  1. **Rule policy spec.**
     - Priority order across drink, eat, rest and sleep, gather, and explore, by need band.
     - Tie-breaking, including the seeded hash.
     - Behavior on `NO_PATH`, `RESOURCE_TAKEN`, an empty tree, a full inventory, and when no
       target exists.
     - Canteen use: drink, fill, give, and when to request.
     - The allowed inputs and the `policy_state` schema, with save, restore and validation
       (§1.2).
  2. **Scenario matrix.** Use the original default as the baseline. Keep experimental
     content and policy variants separately identified.
     - S1, *spring visible*: a spawn-only variant with residents within initial sight of
       the spring. Use S1 and S2 to diagnose survival versus discovery.
     - S2, *blind default*: the original default island before tuning; the M6-approved
       default for final acceptance. Label the revision explicitly in each run.
     - S3, *scarcity*: one declared single-factor reduction, such as fewer trees or slower
       regrowth.
     - S4, *canteen comparison*: enabled versus restricted (§1.3).
     - S5, *cue use*: identical map, spawns and settings, with cue-based preferences enabled
       versus ignored by the policy. Keep the cue, world perceptions and trigger rules
       intact; the switch changes only the policy's use of cue information. S1 versus S2
       changes spawns and visibility and is not an estimate of the cue's effect.

     Each scenario names its single changed factor and states which content invariants it
     keeps.
  3. **Seed lists:** development and acceptance, disjoint, committed (§1.1).
  4. **Metrics with exact definitions and artifact sources**, computed outside the policy.
     Verify the necessary data exists in the declared run artifacts. Define any diagnostic
     sidecar explicitly and keep it read-only over the committed world.

     Per resident:
     - first recorded spring discovery: join the resident's `exploration_updated` tile
       indices with the retained map, including initialization. This measures first static
       exposure, including step observations, independently of the policy's next decision.
       P2-00 confirms where the tick-zero footprint is recorded (event or tick-zero
       checkpoint);
     - first-drink tick;
     - alive at 1008, death tick and cause;
     - ticks alive and ticks deprived, using exact conditions from per-tick committed
       frames or an equivalent read-only diagnostic. Specify whether the death boundary
       contributes to each count; the critical need band alone is not deprivation. If the
       source is replay frames, the batch tool must export a replay for every run;
     - dedicated water trips;
     - completed gathers and transfers.

     Per run:
     - contention events and adaptations, citing objective event IDs and the matching
       decision records when a policy changes target;
     - action and route evidence for diagnosing finding water, reaching or using it, and
       resource access or supply. Distinguish a measured association from a proven cause.

     **[P] Dedicated water trip:** a spring visit in which every completed action is a drink
     or a fill. It must also be preceded by a travel leg with no completed gather, give or
     pick-up since the last useful non-water action.

     **[P] Censoring:** a resident who never sees the spring is recorded as *not found*, and
     one who sees it but dies before drinking as *found, not drunk*. Neither enters time
     averages; report them as counts.
  5. **Pass lines:**
     - PD-05;
     - the S3 evidence rule: at least one traceable contention or adaptation per declared
       S3 seed, with the event and decision IDs cited;
     - all three residents survive to tick 1008 in the registered S1 development cases.
- **Pass evidence:** a reviewer can implement, measure and judge pass or fail from the specs
  alone. Every frozen-contract change is listed with its scope and approval point. Attach
  a short expected-results example for the metrics and record the artifact identity rules.
  Gate 3 (M5) is the owner's approval of PD-05..07 and CR-004.

### P2-01: Wire in the rule policy

- **Lane:** after P2-00 and CR-004.
- **Files:** `agents/types.py`, `agents/runtime.py` (factory), `agents/rule_based/__init__.py`
  and a stub policy, `sim/cli.py` (`--policy rule-based`), `sim/runner.py` (rule-only config
  wiring), tests, and save or restore validation only as authorized by CR-004. No world,
  content or replay schema change.
- **Deliverables:**
  - `rule-based-v0` ID, factory and CLI flag;
  - `PolicyConfig` and `policy_state` validation per CR-004;
  - a stub policy (for example, always `wait`) and a short fixture with a living resident at
    the resume boundary to prove the plumbing. Hand the policy directory to P2-02 after merge.
- **Pass evidence:**
  - uninterrupted run and resume match on event and decision bytes after joining the
    verified prefix and continuation suffix, and on the final world; recorded re-execution
    matches full event and decision bytes and final world, with a recorded runtime state;
  - malformed `policy_state` and a rule parameter that differs from the verified source
    policy configuration are refused on restore;
  - P1 tests and compatibility checks pass; M4 reference hashes match for the original
    P1 inputs at `6d90824`;
  - type generation leaves no diff in generated frontend artifacts.

### P2-02: Implement resident survival

- **Lane:** after P2-01 (world lane).
- **Files:** `agents/rule_based/` after the P2-01 handoff and its tests; the S1–S3 scenario
  content files under `content/scenarios/` (or a test fixture directory chosen in P2-00).
- **Deliverables:**
  - S1 survival logic first;
  - then exploration and frontier choice, cue following, detours, back-off after failure,
    and canteen use and transfer.
- **Pass evidence:**
  - S1 passes on the development seeds;
  - in S2 no resident repeats the same failed target before its retry tick (test plus
    decision-record check);
  - same context, state and config give the same plan (property test);
  - every action is still validated by the world;
  - a leak test shows the policy reads no forbidden input (§1.2);
  - canteen drink, fill and give are each exercised in a scenario test; restrictions for
    S4 and S5 are scoped to the intended policy choices;
  - resume with populated rule state preserves the same next decisions and final world.

### P2-03: Batch experiment tool

- **Lane:** side lane; can start after P2-00, in parallel with P2-01 and P2-02.
- **Files:** `scripts/p2_experiments.py` plus a read-only analysis module. The module reads
  run directories and does not import `sim` or `world` internals; P2-00 defines its location,
  data access and dependency check. Keep default CI and P1 test configuration unchanged.
- **Deliverables:**
  - a batch runner that takes a seed list and a scenario list;
  - per-resident and per-run metrics from the P2-00 experiment spec;
  - a summary table;
  - a manifest per run: unique experiment-case ID, seed, policy ID and version, canonical
    policy parameters or policy-config hash, world config and map hashes, scenario ID,
    output directory and event-log hash;
  - a separate command for long experiments with outputs under ignored `runs/` paths.
- **Pass evidence:**
  - the metrics are first validated on P1 policies and scripted fixtures with hand-checked
    expected values;
  - a second person re-running the same manifest gets identical counts and hashes;
  - the tool distinguishes two seeds with the same `run_id` and two policy arms with the
    same world config hash. It can ship on P1 policies and fixtures; the rule-policy batch
    is exercised after both lanes merge in P2-04.

### P2-F0: Frontend design spec (documentation only)

> **Folded into P2-F1 by Amendment 2 (2026-11-11).** No separate P2-F0 task runs and no
> style options are compared. The deliverables below that still apply (asset interface,
> layout, data mapping, change set, acceptance checks) are delivered by P2-F1 in
> `docs/spec/frontend-design-v0.1.md`. The text below is kept as the record of Amendment 1.

- **Lane:** after P2-03; the only active task. Inserted by Amendment 1 (PD-08).
- **Files:**
  - `docs/spec/frontend-design-v0.1.md` (new);
  - an ADR for the rendering approach, if one is chosen (for example Canvas 2D or PixiJS);
  - style samples and asset-pipeline notes under `docs/design/`;
  - new OQs.
  No code; no change to `contract/` or other specs.
- **Deliverables:**
  - the visual direction, with a small set of style samples compared;
  - the asset interface (product document §9.2):
    - tile pixel size, layer order, resident facing and animation conventions;
    - naming and file layout;
    - a license and source record for every third-party asset;
  - layout and interaction for the replay viewer: map, time controls, resident and event
    panels and the debug view;
  - a mapping from each displayed element to an existing `ReplayBundle` / `DisplayFrame`
    field. Any element without a field is out of scope and becomes an OQ for a later phase;
  - the change set against `p1-replay-frontend-v0.1.md`, stating what changes and what
    stays;
  - acceptance checks for P2-F1.
- **Pass evidence:**
  - every displayed element maps to an existing contract field;
  - no game logic is placed in the frontend (AGENTS.md principle 6);
  - Gate 3 (MF): the owner approves the design and the style.

### P2-F1: Frontend implementation

- **Lane:** after P2-03. Runs before P2-04 (Amendment 1). Under Amendment 2 it starts
  without a prior MF and also delivers the P2-F0 design documents.
- **Files:** `frontend/**` except `frontend/src/api/generated/`; asset files under the
  path the design spec fixes, with their license record; under Amendment 2 also
  `docs/spec/frontend-design-v0.1.md` (new), `docs/adr/0005-frontend-rendering.md` (new),
  `docs/design/**`, the P2-F0 and P2-F1 task cards, this plan (Amendment 2 only),
  `docs/spec/open-questions.md` (append only) and the "Inspect the replay" section of
  `README.md`. No change to `contract/`, the backend,
  generated files or any existing spec.
- **Deliverables:** the design on the existing replay viewer, including the rendering
  approach and assets; the design spec with the asset interface, data mapping, change set
  against `p1-replay-frontend-v0.1.md` and acceptance checks; and those checks as tests
  where they can be automated.
- **Pass evidence:**
  - frontend lint, typecheck, build, test and test:schema pass; type generation leaves
    no diff;
  - the P1 replay and a rule-based default-island replay load and play;
  - the design spec's acceptance checks hold;
  - Gate 3 (MF, Amendment 2): the owner watches one replay in the new viewer and approves
    the design and the style before merge.

### P2-04: Comparison experiments and tuning

- **Lane:** after P2-02, P2-03 and P2-F1. Development seeds only.
- **Files:** experiment reports under `docs/tasks/p2/`. Stage candidates in separate
  experiment inputs. Apply the recommended `content/worlds/default.toml` numeric changes
  only after M6 approval. A map placement change requires explicit PD-04 approval, including
  any matching TOML coordinates, and validation of the edited map before merge.
- **Deliverables:**
  - the S2 baseline on the original map;
  - S3 results;
  - the S4 canteen comparison at decay 100, plus round two at 120 or a deferral OQ (§1.3);
  - an S1/S2 survival-versus-discovery diagnosis and the S5 matched cue-use comparison;
  - a recommended default config.
- **Pass evidence:**
  - the report separates *not found*, *found but not drunk in time* and *supply shortfall*
    (Balance Notes §5, item 5), backed by discovery, action and resource evidence;
  - each recommended change has paired single-factor evidence;
  - if the original values already meet PD-01 on the development seeds, they are kept;
  - Gate 3 (M6): the owner approves the recommended config and any map change.

### P2-05: Integration and sign-off

- **Lane:** last.
- **Files:** README, the task card, the P2 retrospective, and an integration test, kept out
  of default CI if it runs the long experiment matrix. Keep a short deterministic integration
  check in default CI.
- **Deliverables:**
  - acceptance-seed results for the approved config;
  - one real seven-day replay;
  - resume and reexecute evidence with the rule policy;
  - the canteen function and comparison records;
  - the P2 retrospective;
  - a frozen `rule-based-v0` baseline for P3 (control group and fallback).
- **Pass evidence:**
  - all runs pass technical validity; the PD-05 survival line is met on the acceptance
    seeds, with the interval and behavioral diagnostics reported;
  - resume joins the verified prefix and suffix to match the uninterrupted logs and final
    world; recorded re-execution matches the full logs and canonical final world;
  - S3 meets its evidence rule;
  - Gate 3 (M7): the owner watches one real replay and signs off.

## 3. Order and lanes

```text
P2-00 (M5) ─ P2-01 ─ P2-02 ─┐
          └─ P2-03 ─────────┴─ P2-F1 (MF) ─ P2-04 (M6) ─ P2-05 (M7)
```

Under Amendment 2, P2-F1 includes the design deliverables originally assigned to P2-F0.

- The world lane runs P2-01 then P2-02. The side lane runs P2-03.
- A Gate 2 review takes one of the two slots, so the side lane pauses while a world-lane
  review runs.
- Parallel file scopes do not overlap. P2-01 owns policy wiring and the initial stub in
  `agents/rule_based/`. After it merges, P2-02 takes over that directory. P2-03 owns
  `scripts/` and its analysis module.
- P2-F1 runs after P2-03 and before P2-04 (PD-08, Amendment 2). It owns `frontend/`
  (except generated files) and the design documents. The viewer draws the map and values
  from replay data.
- P2 has no target date; measured experiment time and the required reviews determine when
  each milestone closes.

## 4. Milestones (Gate 3)

- **M5:** P2 specs approved: the rule policy, experiments, PD-05..07 and CR-004.
- **MF:** frontend design and style approved. Under Amendment 2 the owner approves by
  reviewing the working viewer at the end of P2-F1.
- **M6:** tuned default config approved, including any map change.
- **M7:** final P2 acceptance.

## 5. Acceptance matrix

| ID | Must hold | Evidence |
|---|---|---|
| B01 | Rule policy uses only allowed inputs | leak tests, import-linter, code review against §1.2 |
| B02 | Deterministic and resumable with the rule policy | prefix plus suffix matches the uninterrupted logs and final world; recorded re-execution matches the full logs and canonical final world |
| B03 | S1 survival | development seeds pass |
| B04 | Default island survival | all registered runs technically valid; PD-05 survival threshold, interval and behavioral diagnostics |
| B05 | Scarcity behavior | traceable contention or adaptation per S3 seed |
| B06 | Canteen function | drink, fill and give tests; uses in real runs |
| B07 | Canteen benefit measured | S4 report with the confounds of §1.3 stated |
| B08 | Experiments reproducible | manifests rerun to identical counts and hashes |
| B09 | P1 compatibility | P1 tests and replays; M4 hashes reproduced from the frozen P1 inputs |
| B10 | CI and generated types clean | CI on `main` |
| B11 | Records complete | handoffs, reviews, M5, MF, M6 and M7 sign-offs, retrospective |
| B12 | Frontend design implemented | MF sign-off; P2-F1 checks; the replays play in the new viewer |

**Allowed:** a small canteen benefit; deaths in some seeds within PD-05; dull behavior.
**Not allowed:**
- hidden map knowledge or map-specific constants in the policy;
- tuning on acceptance seeds;
- multi-factor tuning presented as single-factor evidence;
- a map change without owner approval;
- a nonholder death counted as canteen benefit.
