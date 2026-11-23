# P3.5 M14 plan — One LLM resident over several days

Planning branch `task/P3.5-M14-cards`. There are 18 executor cards in 12 waves. The owner reviews the evidence in wave 11. Wave 12 is a separate post-signature task. The milestone acceptance criteria are in §4.

Baseline `101361db91498f20511b793c6171b4b716e969b0` (fetched `origin/main`, including the merged PR-05 coordinator and PR-06 policy host). The eight P3.5 specs were frozen at M11. The 2026-11-23 owner decisions and the latest human-in-the-loop note were published separately at `ffa3f12799f1d5e10cdab59e066a5e3b1592b569` on `task/P3.5-M12-owner-decisions-1123`. Apply those rulings even where the earlier review on the base calls them provisional. PR-07 and the M12 signature are execution prerequisites.

## 1. Owner decisions

Recommendations are proposals unless a dated ruling is cited. Record the owner, date, choice and applicable revision when dispatching. [Phase plan §§4, 4.1, 9–10](../../plans/p3.5-implementation-plan-v0.1.md) · [M12 plan D1–D3](M12-plan.md) · [Open questions](../../spec/open-questions.md).

| Decision | Options | Recommendation and reason |
|---|---|---|
| D1. Which model should live on the island? | Use DeepSeek Flash from the P3 smoke, or propose a different model/provider with a documented schema, counter, price and window. | Use DeepSeek `deepseek-flash`, resolving to `DeepSeek-V4.1-Flash-1017` subject to verification before spending. Pin the actual alias resolution, API mode, dated evidence, schema and tokenizer/counter. The P3 final smoke already measured this model. Start with structured JSON and one copy of each response schema in its provider field. A change affecting the frozen form/window requires an owner CR. [ADR 0007 D7](../../adr/0007-world-agent-protocol.md) · [ADR 0013 Q7](../../adr/0013-decision-loop.md) · [M9 results](../p3/M9-evidence.md) · [provider model mapping](https://api-docs.deepseek.com/) |
| D2. How many whole game days should we buy? | Aim for three complete days (432 ticks), choose another multi-day target within the estimate, or withhold step 2 if the balance is too small. | Define “several” as three for this trial, subject to owner approval. Release at most that target after EV-05 and DL-06 measure calls/day and CNY/call. Show the affordable integer from §5, remaining cash and retry headroom. If fewer than three fit, recommend holding payment for a decision. The owner may authorize a shorter observation and record the shortfall. |
| D3. Reuse P305-U1 registration 0.2? Decide before M14 execution. | Register this strict run with a small v2 manifest and signed spend sheet, or separately review and adapt the parked registration system before any live run. | Use the v2 manifest with immutable pins, exact run identity and price authorization. Keep `task/P305-U1-registration-v02` parked. Reuse would need a separate reviewed task, integration with v2 evidence, and owner disposition. M14 executors never merge it. |
| D4. Does exploration need a full trial registration? | Apply the frozen exploration rule, or reopen it by CR to require full registration. | Confirm evaluation §9 / EV-D9, which disposed of ADR 0014 Q4. Pin commit, pack hashes, prompt versions, model ID and seeds in a reproducibility manifest. Exploration uses `explore/<slug>`, `runs/explore/` and notes in `docs/explore/`. It grants no additional paid step. Promoting a result to main takes a normal task. |
| D5. Which world should the resident use? | Run in `compat-v1` as soon as M12 is accepted, or wait for an accepted starter pack from M13. | Use the compatibility world with one memory-on LLM resident (recommend Ella) and rule-controlled companions if the fixture requires them. This lets the world and resident tracks proceed independently. The learned grass-cord axe and other starter-only evidence go to M15. |
| D6. Where do the five profiles live during migration? | Load schema 0.2 from a versioned content directory alongside 0.1, or arrange a separately reviewed migration of the current profile paths. | Keep the existing three 0.1 files available to the frozen reader. Approve `content/characters/v2/` for the three specified trait vectors and two owner-selected additional profiles. Use clearly identified fixture profiles while the two names/values are open. See OQ-P3.5-M14-1. |
| D7. What counts as a successful small live check? | Approve a fixed representative sample, or specify a larger predeclared sample within the same first paid step. | Use one prepared request of each of the six call kinds. Record first-pass validity, all dispatches and each retry. Compare decision requests to the final M9 smoke's 22/22 without local parse rejections. Require all six request forms to be accepted and parse correctly on the declared sample before step 2. Report counts and the limited sample size. See OQ-P3.5-M14-2. |

**Binding rulings from 2026-11-23.** PR-06's native fallback may synthesize `PLAN_FINISHED` only in the private v1 decision request with an empty legacy queue and no deferred trigger (`native_fallback` provenance). Only the isolated synchronous planner copy may carry private typed feedback in `context.perception.last_action_feedback`. Discard it after the call. The clean physical packet is what the journals, model and memory receive. A suppressed fallback talk waits silently and uses private `INVALID_SPEECH_ACT` back-off once. Broadcasts keep literal text and an empty addressee. Nonrepresentable or timed proposals project as statements and only representable addressed requests trigger a reply. Retain PR-05's detached deliveries and approved read-only turn ordinal access. [PR-05 review](P3.5-PR-05-review.md) · [PR-06 review](P3.5-PR-06-review.md) · [owner ruling revision](https://github.com/Lanchy-ou/Living_World/commit/ffa3f12799f1d5e10cdab59e066a5e3b1592b569).

## 2. Order and parallel work

All execution starts from accepted M12 including PR-07 and the owner's M12 Gate 3. Claude Code reviews this planning branch before implementation. Wave numbers express dependencies. Within a row, each card may start as soon as its own listed prerequisites are merged and its files are available. M13 can proceed alongside this track. After D5, a starter-pack live run additionally waits for that pack. A shared file has at most one writer across both tracks.

| Wave | Cards and work | Starts when |
|---|---|---|
| 1 | [MM-01](P3.5-MM-01.md) store, types and profiles · [DL-01](P3.5-DL-01.md) fake/provider port, framed requests, guard and attempt journal | M12 accepted, registration disposition D3 recorded, owner releases M14 |
| 2 | [MF-02](P3.5-MF-02.md) transactional change sets · [DL-02](P3.5-DL-02.md) working context · [EV-04](P3.5-EV-04.md) spend ledger | MF-02 after MM-01. DL-02 after MM-01 + DL-01. EV-04 after DL-01 |
| 3 | [MF-01](P3.5-MF-01.md) mechanical writes · [DL-03](P3.5-DL-03.md) recall, citations and use credit | Both after MM-01 + DL-02, with DL-01's typed dispatch/sent-request interface available |
| 4 | [MF-03](P3.5-MF-03.md) sleep/faint, two-call consolidation, pending periods | MF-01 + MF-02 + DL-01 + DL-02 merged |
| 5 | [DL-04](P3.5-DL-04.md) end-to-end resident loop and fallback | DL-03 + MF-03 merged |
| 6 | [DL-05](P3.5-DL-05.md) persistence, exact replay and terminal guard evidence | DL-04 merged |
| 7 | [MM-02](P3.5-MM-02.md) extension proofs and audit isolation · [EV-01](P3.5-EV-01.md) inspection export, joins and browser | DL-05 merged. EV-01 also consumes MF-02. Serialize any allocated import-linter edits |
| 8 | [EV-02](P3.5-EV-02.md) continuity, learning and section costs · [EV-03](P3.5-EV-03.md) Round 3 artifact-use counts | EV-01 merged with the export interface. EV-03 reads the M12 EN-36 vector |
| 9 | [EV-05](P3.5-EV-05.md) five-resident fake workload and one-resident cost rehearsal | MM-02, EV-01–04 merged, one heavy-job slot free, reviewed data path |
| 10 | [DL-06](P3.5-DL-06.md) paid step 1, provider live check | EV-04 ledger verified, EV-05 passed, owner confirms D1/D3/D7 and releases the bounded check |
| 11 | [EV-06](P3.5-EV-06.md) paid step 2, one live resident and Gate 3 package | Step 1 passes, all earlier cards accepted, actual cost and day estimate reconciled, owner dispatches D2/D5 |
| 12 | [EV-07](P3.5-EV-07.md) remove v1 engine and retire old viewer/replay paths | **Only after the owner signs M14 Gate 3**. Verify the signed record and the archive tag before opening the retirement task |

Build on the existing `AgentPort`, `Runner.advance`, `TurnRequest.bind/check_binding` and PR-06 `PolicyHost`/`PolicySession`. Deliver every pending packet before deciding. Commit the scheduled actor's bound submission and any objective fallback tag atomically. Preserve model handback, visible current progress and the delayed outcome filter across restore. A model `continue` drops the obsolete private queue only on commit. Reuse the compatibility bridge in its allowed mode and visible feedback only in starter mode. Use a per-resident policy assignment: one LLM resident and any standalone rule-controlled companions. A companion's ordinary speech, decisions and queue are independent of LLM fallback. The world remains the sole settlement authority. [World–agent protocol §§2–3, 11](../../spec/world-agent-protocol-v0.1.md) · [decision loop §§2, 8](../../spec/decision-loop-v0.1.md).

## 3. File ownership

Production Python paths below are under `backend/src/living_island/`. Test directory names in the right column are under `backend/tests/v2/`. Each task owns its card's handoff. Use the full branch name and recommended executor setting printed on that card. M12 D1 extends to `memory/v2/`. The M14 harness lives in `sim/v2/harness/`. M13 owns `content/packs/**`, `sim/v2/scenarios/**` and its long run. The M14 path allowance excludes those paths and all of `world/v2/**`, including the protocol. Request upstream changes through the owner.

| Card | Exclusive files and outputs | Test directory |
|---|---|---|
| MM-01 | `memory/v2/{__init__,records,kinds,store,pending,profiles,projections}.py`, five schema 0.2 files in the D6 profile directory | `memory_store/` |
| DL-01 | `agents/v2/calls/**` including fake, provider and counter, `sim/v2/harness/__init__.py` | `call_wire/` |
| MF-02 | `memory/v2/{changes,validation,provenance,capacity}.py` | `memory_changes/` |
| DL-02 | `agents/v2/context/**` including typed day entries, resident-safe fragments and morning selection | `working_context/` |
| EV-04 | `analysis/v2_spend.py`, `docs/tasks/p3.5/P3.5-spend-ledger.md` (two later sequential updates below) | `spend_ledger/` |
| MF-01 | `memory/v2/mechanical.py`, `sim/v2/harness/agreement_facts.py` | `mechanical_memory/` |
| DL-03 | `agents/v2/recall/**` | `recall/` |
| MF-03 | `sim/v2/harness/consolidation/**` | `consolidation/` |
| DL-04 | `agents/v2/decision/**`, `sim/v2/harness/{loop,session,composition}.py` | `decision_harness/` |
| DL-05 | `sim/v2/harness/{checkpoint,replay}.py` | `resident_replay/` |
| MM-02 | Synthetic registrations, audit-isolation and extension fixtures in the named test directory | `memory_extensions/` |
| EV-01 | `analysis/v2/{__init__,export,shards,joins}.py`, `frontend/src/features/v2-inspection/**`, `frontend/tests/v2-inspection.test.mjs` | `inspection_export/` |
| EV-02 | `analysis/v2/{continuity,learning,cost}.py`, `frontend/src/features/v2-analysis/**`, `frontend/tests/v2-resident-analysis.test.mjs` | `resident_analysis/` |
| EV-03 | `analysis/v2/artifact_use.py` | `artifact_use/` |
| EV-05 | Workload fixture, single-resident rehearsal and `docs/tasks/p3.5/M14-fake-workload.md` | `fake_workload/` |
| DL-06 | `sim/v2/harness/provider_check.py`, `docs/tasks/p3.5/M14-provider-check.md` | `provider_check/` |
| EV-06 | `docs/tasks/p3.5/M14-gate3.md`, paid-stage evidence receipts | `live_resident_evidence/` |
| EV-07 | Per-file retirement inventory in its PR after signature, v1-exclusive runtime/display files only after dependency audit and allocation | `v1_retirement/` |

### Shared files

These are **requests**, subject to Claude Code allocating named files at review. No executor owns an existing shared file outright. Record file, reason, branch and release of the slot in the card PR. Rebase after the preceding writer merges. If a public hook already suffices, use it.

| Candidate path | Requesting cards in order | Reason |
|---|---|---|
| `sim/v2/runner.py`, `turns.py`, `manifest.py` in the same directory | DL-04, then DL-05 (manifest only) | Boundary commit/abort, stop witness, turn registration and runtime record/replay links. Reuse PR-05 delivery and binding semantics |
| `sim/v2/cli.py` | DL-04 after PR-07, DL-05 only if replay needs normal CLI wiring, EV-01 if export needs wiring, EV-07 if routing retires | Public composition, replay and export entry points. Keep M13's scenario/long-run command registration working |
| `persistence/v2/**` | DL-01 (attempt journal adapter), DL-05 (`audit.py`, `checkpoint.py`, `replay.py`, manifest/journal links as needed) | Durable dispatch-before-I/O, terminal/late accounting, canonical parts, versioned resident checkpoint and offline audit/replay. Only the coordinator writes through the port. Resident paths never receive an audit reader |
| `backend/pyproject.toml` import-linter section | MM-02, EV-01 if needed, EV-07 on retirement if legacy modules disappear | Enforce v2 memory/agent world-protocol and audit boundaries, including context/recall/consolidation, and analysis read-only imports. Coordinate with other track's contracts |
| `contract/**`, appropriate `scripts/gen*_types.py` and `frontend/**/generated/**` | EV-01 (typed v2 inspection/replay export), EV-07 (retire v1 display models). EV-02/03 request additions only if their agreed metric rows need new types | Generated output comes from its contract generator. Preserve P3 readers until the signed removal point |
| `frontend/src/App.tsx` and existing viewer import/route glue | EV-01 then EV-02, later EV-07 | Mount inspection and analysis, link to the v2 replay moment, finally refuse archived bundle versions |
| `analysis/v2/export.py` after EV-01 | EV-02, then EV-03 if EV-01's interface needs changes | Wire the metrics and artifact traces into the standard export without colliding in wave 8 |
| `docs/tasks/p3.5/P3.5-spend-ledger.md` | EV-04 initializes, DL-06 then EV-06 regenerate only their evidence-backed rows | Separate each paid step and keep one deduplicated phase total |
| Existing historical jobs/entry points including `.github/workflows/ci.yml` | EV-07 only after signature and exact inventory | Route v1-only checks to the immutable archive, preserve independent v2 regression coverage and the active full CI pipeline |

## 4. Done when

One live LLM resident in the approved world completes the agreed several game days after the provider check. The decision loop, growing working context, consolidation and recall run end to end. Replay requires zero model calls, every context is traceable, and both resident extension tests in evaluation §8 pass. The owner signs against the committed run evidence. M15 owns the five-resident paid matrix and causal comparisons.

### Test-to-card map

Each ID in the left column names the complete acceptance row in its frozen spec. The card on the right owns the assertion even if another card supplies code or fixtures. The table spells out every ID for checking against the specs. [MM §11](../../spec/memory-model-v0.1.md) · [MF §9](../../spec/memory-formation-v0.1.md) · [DL §13](../../spec/decision-loop-v0.1.md) · [EV §§8, 10](../../spec/evaluation-v0.1.md).

| Spec tests | Evidence | Owning card |
|---|---|---|
| MM-01, MM-02, MM-03, MM-04, MM-05, MM-18 | Typed envelopes, IDs, version, index, perceived looks, intention history | [MM-01](P3.5-MM-01.md) |
| MM-06, MM-07, MM-08, MM-09, MM-10, MM-11, MM-12, MM-20, MM-22, MM-25, MF-06, MF-07, MF-09, MF-19, MF-24 | Transactional operations, authority, provenance, hearsay cap after eviction/restore, capacity and rollback | [MF-02](P3.5-MF-02.md) |
| MM-17, MM-21, MM-24, MF-01, MF-02, MF-03, MF-15, MF-18, MF-22 | Party projections, received counts, own/watched skill evidence and delayed fallback | [MF-01](P3.5-MF-01.md) |
| MF-04, MF-05, MF-08, MF-10, MF-11, MF-12, MF-16, MF-17, MF-20, MF-21, MF-23 | Two-call confirmation, rebase, pending state, fixed input floors, interruptions and timing at K | [MF-03](P3.5-MF-03.md) |
| DL-08, DL-11 | Counted pressure and ordered trimming with the notice | [DL-01](P3.5-DL-01.md) |
| DL-05, DL-06, DL-07, DL-15, DL-23 | Prefix, day entries, visible projections, dialogue and member refs | [DL-02](P3.5-DL-02.md) |
| DL-09, DL-10, DL-21, DL-22, DL-28, DL-30 | Recall strength, deliberate/recipe paths, sent citations, first-dispatch credit | [DL-03](P3.5-DL-03.md) |
| DL-01, DL-02, DL-03, DL-04, DL-12, DL-13, DL-14, DL-17, DL-18, DL-24, DL-25, DL-26 | Scheduled live loop on fake transport, alerts/operator stop, off-arm reset, fallback integration and composition | [DL-04](P3.5-DL-04.md) |
| MM-14, MF-13, DL-16, DL-20, DL-27 | All six kinds, manifests/floors/sent bytes, no-dispatch/abandonment, every store version and full offline replay | [DL-05](P3.5-DL-05.md) |
| MM-13, MM-15, MM-16, MM-19, MM-23, MF-14, DL-19 | Audit isolation and historical revision access, off-arm projections, synthetic memory kind and recall recipe | [MM-02](P3.5-MM-02.md) |
| MF-25, DL-29, EV-01, EV-14, EV-17, EV-18, EV-25 | Export and read-only viewer, immutable source/telemetry joins, actual relabel sidecar and rejection of broken references | [EV-01](P3.5-EV-01.md) |
| EV-04, EV-05, EV-23 | Learning path flags, self-found hypotheses/evidence, later-period use and guard exposure. Section token shares and cost view also feed Gate 3 | [EV-02](P3.5-EV-02.md) |
| EV-22, EV-24 | Qualifying uses, split/return sources and physical portions | [EV-03](P3.5-EV-03.md) |
| EV-13 | Full fake-model workload, replay and export before spending | [EV-05](P3.5-EV-05.md) |
| EV-02, EV-03, EV-06, EV-07, EV-08, EV-09, EV-10, EV-11, EV-12, EV-15, EV-16, EV-19, EV-20, EV-21 | **M15**. Claim chains/doubt, complete artifact/commitment/time-use metrics, cross-metric exclusions and arm comparison, probes, thresholds, axe traces and per-seed outcomes | M15 evaluation cards assigned by its planner |

This accounts for all 25 MM, 25 MF, 30 DL and 25 EV rows. Eleven EV rows have M14 owners. Fourteen remain at M15. EV-04/05 here are learning metrics, distinct from same-numbered P3.5 task IDs. The M12 rule-pack extension remains in M12.

**Round 3 handoff.** MF-01 closes the memory half of the wake-boundary gift (MF-18) against M12's delivered receipt, including merged, failed, sleeping and unseen controls. DL-05 closes the recall-manifest half (DL-20, DL-27) against PR-05's frozen pending boundary: an unfit deliberate query has measured full/candidate/floor records, null sent/submission, zero attempts or fallback, and no world effect. EV-03 closes M12 D3's qualifying-use count (EV-22) and the physical split/return example (EN-36 → EV-24). It checks the artifact threshold fixture at/below the boundary. M15 owns the full multi-capability EV-12. [M12 plan §5](M12-plan.md).

### Owner's Gate 3 inspection

1. Open `M14-provider-check.md` and the spend ledger delivered in waves 10–11. Check model identity, single-copy wire form, parse counts versus M9, cost per call, proposed and actual length, all charged attempts and remaining phase balance.
2. From `M14-gate3.md`, open the verified live export in analysis mode. Select the resident's earlier waking period, source packet and memory revision. Follow a committed consolidation into a later day's sent prefix or recall, the model decision, actual world result and matching replay tick. Show valid citations separately from dispatch-based use. Report missing or zero use/skills with evidence. Distinguish game days from K closures.
3. Inspect a self-found skill hypothesis, its source and code-counted evidence when present. Read cost per resident/day and section token share for schema, prefix, day log, state, recall and other framing. Distinguish billed per-attempt totals from estimated section attribution and report output/unattributed cost separately. Show guards, fallback and unknown usage explicitly. Starter-only evidence stays labelled for M15 on a compatibility run.
4. Verify all prepared and dispatched requests, store-version hashes, submissions, events, checkpoint and export against an offline replay with a fail-on-call transport. Open the extension receipts for **MM-16 together with MF-14**, and **DL-19**. Check the EV-13 5 × 7 rehearsal, Round 3 proofs and engineering Gate 2 records.
5. Record the owner's signed disposition, evidence commit and any missing item. An unaffordable/shortened or interrupted run remains partial. No executor, reviewer or provisional package can sign Gate 3 or release EV-07 on the owner's behalf.

## 5. Paid steps and phase spend

The owner authorizes **at most CNY 20 across all of P3.5**. There are exactly two planned paid operations. All development, CI, schema/guard tests, rehearsals, probes used as fixtures, and replay use a fake or disabled transport. No paid M15 matrix, exploration run, probe, P3 rerun or provider bake-off is scheduled here. Credentials come from `.env` only at the approved live invocation. Never display, log, commit or send keys to the model. Store sanitized request bodies and attempts without authorization headers. Keep raw `runs/` artifacts outside Git.

| Paid operation | Admission and evidence | Stop condition |
|---|---|---|
| 1. DL-06 provider live check | Owner authorizes sample, pins and a worst-case allowance that fits after all other phase liabilities. EV-05 rehearses the same wires. Persist every sent, failed, retried or interrupted attempt and raw/parsed outcome. Record tariff date, actual token categories, CNY per attempt and first-pass parse rate | A failed check, unverified model, insufficient headroom or unresolved accounting holds step 2. A tool-calling alternative requires a CR |
| 2. EV-06 one live resident | Project whole days with measured check costs, observed fake attempt counts and later-day section sizes. Owner approves horizon, resident and manifest. The operator monitors actual charges and makes new reservations before dispatch including simultaneous consolidation work | Stop before incurring an unaffordable charge. Seal outstanding accounting, stop at the next safe boundary and report incomplete days. Replay/export/inspection are offline |

**Day calculation.** In CNY, let `B = 20 − settled phase spend − outstanding worst-case reservations` after the check. Against each candidate day, multiply the measured CNY per attempt of each call kind by that day's rehearsed attempt counts, adjusted for measured request growth, peak uncached rates, the allowed output and retry exposure. Report the central estimate and the conservative amount held. The affordable horizon is the largest whole-day prefix whose cumulative conservative cost fits B. Use a forecast by day when later contexts grow. Under a flat conservative per-day estimate C, the equivalent bound is `floor(B/C)`. A day is 144 ticks. Report affordable days and the selected target; **three is the proposed target pending actual measurements**. A documented bound may replace an unavailable rate for planning; absent a credible bound, do not spend. [Decision-loop settings](../../spec/decision-loop-v0.1.md) · [phase plan §4.1](../../plans/p3.5-implementation-plan-v0.1.md).

**Admission per boundary.** EV-04 counts unique dispatched attempts and reserves the largest charge still possible until usage settles. The operator budgets a whole authorized unit through the next safe stop, including retries and overlapping consolidation already in flight. Withhold a unit that cannot be covered. Do not turn budget exhaustion into a resident action, provider failure or change to DL §8's frozen retries and gameplay. Late usage replaces its reservation once. Enter the opening phase balance from evidence. The M9 price and the earlier rough CNY 4 per resident-day estimate cannot establish current purchasing power. Keep measured charges, conservative holds and section estimates distinct. [M9 historical costs](../p3/M9-evidence.md).

## 6. Rules for every card

- Human-in-the-loop mode, 2026-11-23. Codex executors work one branch and isolated worktree per card. Claude Code independently runs Gate 2 and acceptance. The owner makes decisions, authorizes paid dispatch and signs Gate 3. Both unattended runbooks are suspended. Put review notes in the card's **own PR**. Bring fixes back through Claude Code. This planning branch is backed up without a PR.
- **Validate once, at the boundary** (AGENTS.md). Check files, wire messages, model output and public package inputs where they enter and turn them into typed data once. No internal `isinstance` checks, `.get` defaults, casts or fallbacks for states that the types already rule out. Every reachable check ships with a test that reaches it. Parse and type model output once at the provider/model boundary.
- **Record every LLM call** with input, prompt version, model, raw output, parsed result, latency and tokens. Keep all attempts, settings, required immutable versions/hashes, usage/cache and error state. Null unavailable measurements with reasons. Separate reasoning returned by a provider stays in the record and never returns to a subsequent prompt. Capture full manifests, prepared candidates and floor, sent only upon dispatch, and every durable journal cursor. Replay makes zero model calls.
- **Rework rounds** rerun only `uv run --directory backend pytest tests/v2 tests/p3/test_trial_registration.py` **in one session**. The frozen registration test inspects loaded modules. Keep v2 test imports inside tests when collection would pollute that check. Run the **full suite once before the PR, or use a draft implementation PR's GitHub CI for that run instead of running it locally**. Only **one heavy job on the host at a time**, including the long fake workload, full suite, full equivalence and other track's heavy work. Keep receipts tied to the reviewed tree; a code change affecting evidence requires the relevant recheck. Use the active CI jobs as gates.
- Gate 1 starts with the card's targeted fake tests and the registration check in one process, plus the applicable locked checks below. On Windows append a fresh, previously nonexistent `--basetemp` under a short writable parent to **every** pytest invocation. Use AGENTS.md's command-scoped Git longpaths setting when needed. Use only repository-supported Python or package scripts for reusable commands.
- Preserve isolation: agents/memory read world only through the protocol; context, recall and consolidation cannot read the audit. A facts-only agreement writer may receive its allowlisted party-specific feed from sim. Commit memory-use credit at first actual decision dispatch and world actions only after binding. Analysis reads verified recorded artifacts, the frontend renders the resulting values. Frozen specs, M13 content and engine code never change on these cards.
- Record unresolved choices at `docs/spec/open-questions.md`; use the smallest reversible fixture assumption. A contradiction with a frozen spec follows [phase plan §7](../../plans/p3.5-implementation-plan-v0.1.md). Stop only the affected part. Do not import parked P3 work or restart its trials. Every handoff includes what changed, commands/results, deviations, questions and the seven fields of [the template](../_template.md). Keep full raw runs and credentials out of all commits.
- Preserve v1 until the signed retirement point. EV-07 is subject to the repository's deletion instructions: identify files individually and request explicit user approval for any batch deletion.

Gate 1 commands from the repository root, as applicable to the card and the full CI jobs:

```sh
uv sync --directory backend --locked
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv run --directory backend lint-imports --no-cache
uv run --directory backend pytest tests/v2 tests/p3/test_trial_registration.py
uv run --directory backend pytest
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend run test:schema
pnpm --dir frontend run test
uv run --directory backend python ../scripts/gen_types.py
uv run --directory backend python ../scripts/gen_p3_inspection_types.py
git diff --exit-code
```

Run generation/drift checks on a clean committed candidate and include the new v2 generator if allocated. Use the receipts for the full checks once under the workflow above. A docs-only handoff reports its own verification scope; implementation, paid runs and reviewer decisions belong to their future cards.

## Planning handoff

The planning change adds this milestone plan, 18 executor cards and the two M14 entries in the open-question register. A read-only check compared the ownership table with the acceptance rows in the four frozen specs. All 105 IDs appear exactly once, and each M14 ID appears on its assigned card. The same check resolved the local Markdown links and anchors and verified every card's branch, executor setting, baseline, handoff fields and place in the waves and ownership table.

1. `base_commit` / `result_commit` — `101361db91498f20511b793c6171b4b716e969b0` / the commit containing this planning handoff on `task/P3.5-M14-cards`.
2. `status` — `READY_FOR_REVIEW`. Claude Code owns independent Gate 2.
3. `scope_changed` — no. The two register entries are the open-question exception requested in the planning brief.
4. `human_interventions` — no new planning decision from the owner during drafting. The 2026-11-23 rulings are inputs.
5. `rework_rounds` — zero Gate 2 rounds on this planning package at handoff.
6. `verification` — coverage, card and link audit passed. The full implementation suites, simulations, live check and live run are `NOT_RUN` on this documentation branch.
7. `open_questions` — D1–D7 await disposition where indicated. OQ-P3.5-M14-1 and -2 record the two spec details that affect the profiles and the live evidence design.
