# P3.5 M14 plan — One LLM resident over several days

Planning branch `task/P3.5-M14-cards`. There are 18 executor cards in 12 waves. The owner reviews the evidence in wave 11. Wave 12 is a separate post-signature task. The milestone acceptance criteria are in §4.

Baseline `101361db91498f20511b793c6171b4b716e969b0` (fetched `origin/main`, including the merged PR-05 coordinator and PR-06 policy host). The eight P3.5 specs were frozen at M11. The 2026-11-23 owner decisions and the latest human-in-the-loop note were published separately at `ffa3f12799f1d5e10cdab59e066a5e3b1592b569` on `task/P3.5-M12-owner-decisions-1123`. Apply those rulings even where the earlier review on the base calls them provisional. The owner set separate start conditions for offline work and paid work in the 2026-11-23 M14 Gate 2 review (§§1–2).

## 1. Owner decisions

The owner approved D1–D7 as recommended on **2026-11-23**. The paid cards record the actual model, prices, cost estimates and dispatch authorization against these decisions. [Phase plan §§4, 4.1, 9–10](../../plans/p3.5-implementation-plan-v0.1.md) · [M12 plan D1–D3](M12-plan.md) · [Open questions](../../spec/open-questions.md).

| Decision | Options considered | Owner decision (2026-11-23) |
|---|---|---|
| D1. Live model | DeepSeek Flash from the P3 smoke or a different pinned provider/model | Use DeepSeek `deepseek-flash`. Verify the alias resolution against `DeepSeek-V4.1-Flash-1017` before spending. Pin model evidence, API mode, schema and tokenizer/counter. Send structured JSON with one copy of each response schema in its provider field. A change affecting the frozen form/window requires an owner CR. [ADR 0007 D7](../../adr/0007-world-agent-protocol.md) · [ADR 0013 Q7](../../adr/0013-decision-loop.md) · [M9 results](../p3/M9-evidence.md) · [provider model mapping](https://api-docs.deepseek.com/) |
| D2. Live duration | Three complete days, another measured horizon, or hold step 2 | Target **three complete game days (432 ticks)**. Use EV-05's calls per day and DL-06's measured costs to check the remaining P3.5 budget against the CNY 20 total cap, including retry headroom. If fewer than three whole days fit, hold paid step 2 and ask the owner. |
| D3. Live registration | A v2 manifest and signed spend sheet or separate review and adaptation of P305-U1 | Use the v2 manifest with immutable pins, exact run identity and price authorization. Keep `task/P305-U1-registration-v02` parked. Any future reuse requires its own reviewed task and owner disposition. |
| D4. Exploration registration | Apply the frozen exploration rule or reopen it by CR | Apply EV-D9. An exploration run needs only a reproducibility manifest pinning commit, pack hashes, prompt versions, model ID and seeds. Use `explore/<slug>`, `runs/explore/` and `docs/explore/`. Promotion to main takes a normal task. |
| D5. World and roster | Compatibility world or wait for M13 starter content | Use `compat-v1` with Ella as the one memory-on LLM resident and rule-controlled companions. The learned grass-cord axe and other starter-only evidence go to M15. |
| D6. Resident profiles | Keep schema versions side by side or migrate the existing profile paths | Put the schema 0.2 files in `content/characters/v2/` beside 0.1. Use the three frozen trait vectors. The owner will supply the names and five trait values for each of the two additional profiles before P3.5-EV-05. Earlier cards use synthetic fixture profiles until then. See OQ-P3.5-M14-1. |
| D7. Provider check | A fixed six-kind sample or a larger predeclared sample | Prepare one request of each of the six call kinds. All six must be accepted and parsed before paid step 2. Record first-pass validity, all dispatches and retries, and compare decision parsing with the final M9 smoke's 22/22. See OQ-P3.5-M14-2. |

**Early start and risk (owner, 2026-11-23).** M13 and M14 may start while P3.5-PR-07 is running and before the owner signs M12 Gate 3. Waves 1–9 branch from current `origin/main` as each card's prerequisites merge. A card that needs `sim/v2/cli.py` waits for PR-07 to merge. Both paid cards, P3.5-DL-06 and P3.5-EV-06, wait for the owner's signed M12 Gate 3 because the live run depends on compatibility equivalence. If M12 uncovers an engine or coordinator defect, affected M14 cards may need rework and fresh evidence on the corrected base.

**Binding rulings from 2026-11-23.** PR-06's native fallback may synthesize `PLAN_FINISHED` only in the private v1 decision request with an empty legacy queue and no deferred trigger (`native_fallback` provenance). Only the isolated synchronous planner copy may carry private typed feedback in `context.perception.last_action_feedback`. Discard it after the call. The clean physical packet is what the journals, model and memory receive. A suppressed fallback talk waits silently and uses private `INVALID_SPEECH_ACT` back-off once. Broadcasts keep literal text and an empty addressee. Nonrepresentable or timed proposals project as statements and only representable addressed requests trigger a reply. Retain PR-05's detached deliveries and approved read-only turn ordinal access. [PR-05 review](P3.5-PR-05-review.md) · [PR-06 review](P3.5-PR-06-review.md) · [owner ruling revision](https://github.com/Lanchy-ou/Living_World/commit/ffa3f12799f1d5e10cdab59e066a5e3b1592b569).

## 2. Order and parallel work

Waves 1–9 start on current `origin/main` as their own prerequisites merge. The CLI dependency in §1 applies to every card that needs `sim/v2/cli.py`. Claude Code reviews this planning branch before implementation. Each shared file has one writer at a time across M13 and M14.

| Wave | Cards and work | Starts when |
|---|---|---|
| 1 | [MM-01](P3.5-MM-01.md) store, types and profiles · [DL-01](P3.5-DL-01.md) fake/provider port, framed requests, guard and attempt journal | Current `origin/main` with the merged M12 schema, coordinator and policy port |
| 2 | [MF-02](P3.5-MF-02.md) transactional change sets · [DL-02](P3.5-DL-02.md) working context · [EV-04](P3.5-EV-04.md) spend ledger | MF-02 after MM-01. DL-02 after MM-01 + DL-01. EV-04 after DL-01 |
| 3 | [MF-01](P3.5-MF-01.md) mechanical writes · [DL-03](P3.5-DL-03.md) recall, citations and use credit | Both after MM-01 + DL-02, with DL-01's typed dispatch/sent-request interface available |
| 4 | [MF-03](P3.5-MF-03.md) sleep/faint, two-call consolidation, pending periods | MF-01 + MF-02 + DL-01 + DL-02 merged |
| 5 | [DL-04](P3.5-DL-04.md) end-to-end resident loop and fallback | DL-03 + MF-03 merged. Rebase after M13's P3.5-EN-08 performance change to `sim/v2/compat/policy_host.py` |
| 6 | [DL-05](P3.5-DL-05.md) persistence, exact replay and terminal guard evidence | DL-04 merged |
| 7 | [MM-02](P3.5-MM-02.md) extension proofs and audit isolation · [EV-01](P3.5-EV-01.md) inspection export, joins and browser | DL-05 merged. EV-01 also consumes MF-02. Serialize any allocated import-linter edits |
| 8 | [EV-02](P3.5-EV-02.md) continuity, learning and section costs · [EV-03](P3.5-EV-03.md) Round 3 artifact-use counts | EV-01 merged with the export interface. EV-03 reads the M12 EN-36 vector |
| 9 | [EV-05](P3.5-EV-05.md) five-resident fake workload and one-resident cost rehearsal | MM-02 and EV-01–04 merged, owner supplies the two D6 profile definitions, reviewed data path and host lock (§6) |
| 10 | [DL-06](P3.5-DL-06.md) paid step 1, provider live check | Signed M12 Gate 3, EV-04 ledger verified, EV-05 passed and owner releases the bounded D7 check |
| 11 | [EV-06](P3.5-EV-06.md) paid step 2, one live resident and Gate 3 package | Signed M12 Gate 3, step 1 passed, all earlier cards accepted and measured costs reconciled. Owner releases the D2/D5 run |
| 12 | [EV-07](P3.5-EV-07.md) remove v1 engine and retire old viewer/replay paths | **Only after the owner signs M14 Gate 3**. Verify the signed record and the archive tag before opening the retirement task |

Build on the existing `AgentPort`, `Runner.advance`, `TurnRequest.bind/check_binding` and PR-06 `PolicyHost`/`PolicySession`. Deliver every pending packet before deciding. Commit the scheduled actor's bound submission and any objective fallback tag atomically. Preserve model handback, visible current progress and the delayed outcome filter across restore. A model `continue` drops the obsolete private queue only on commit. Reuse the compatibility bridge in its allowed mode and visible feedback only in starter mode. Use a per-resident policy assignment: one LLM resident and any standalone rule-controlled companions. A companion's ordinary speech, decisions and queue are independent of LLM fallback. The world remains the sole settlement authority. [World–agent protocol §§2–3, 11](../../spec/world-agent-protocol-v0.1.md) · [decision loop §§2, 8](../../spec/decision-loop-v0.1.md).

## 3. File ownership

Production Python paths below are under `backend/src/living_island/`. Test directory names in the right column are under `backend/tests/v2/`. Each task owns its card's handoff. Use the full branch name and recommended executor setting printed on that card. M12 D1 extends to `memory/v2/`. The M14 harness lives in `sim/v2/harness/`. M13 owns `content/packs/**`, `sim/v2/scenarios/**` and its long run. The M14 path allowance excludes those paths and all of `world/v2/**`, including the protocol. Request upstream changes through the owner.

| Card | Exclusive files and outputs | Test directory |
|---|---|---|
| MM-01 | `memory/v2/{__init__,records,kinds,store,pending,profiles,projections}.py`, three specified schema 0.2 profiles in the D6 directory, plus the two owner-supplied profiles if available before handoff | `memory_store/` |
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
| EV-05 | Workload fixture, single-resident rehearsal and `docs/tasks/p3.5/M14-fake-workload.md`. After MM-01, add the two owner-supplied D6 profile files if outstanding | `fake_workload/` |
| DL-06 | `sim/v2/harness/provider_check.py`, `docs/tasks/p3.5/M14-provider-check.md` | `provider_check/` |
| EV-06 | `docs/tasks/p3.5/M14-gate3.md`, paid-stage evidence receipts | `live_resident_evidence/` |
| EV-07 | Per-file retirement inventory in its PR after signature, v1-exclusive runtime/display files only after dependency audit and allocation | `v1_retirement/` |

### Shared files

These are **requests**, subject to Claude Code allocating named files at review. No executor owns an existing shared file outright. Record file, reason, branch and release of the slot in the card PR. Rebase after the preceding writer merges. If a public hook already suffices, use it.

| Candidate path | Requesting cards in order | Reason |
|---|---|---|
| `sim/v2/runner.py`, `turns.py`, `manifest.py` in the same directory | DL-04, then DL-05 (manifest only) | Boundary commit/abort, stop witness, turn registration and runtime record/replay links. Reuse PR-05 delivery and binding semantics |
| `sim/v2/compat/policy_host.py` | M13's P3.5-EN-08 makes its performance edit first. DL-04 rebases after EN-08 merges | DL-04 integrates fallback against the updated host. Any further edit requires an allocation |
| `sim/v2/cli.py` | After PR-07 merges, DL-04, DL-05 if replay needs normal CLI wiring, EV-01 if export needs wiring, EV-07 if routing retires | Public composition, replay and export entry points. Keep M13's scenario/long-run command registration working |
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

The owner authorizes **at most CNY 20 across all of P3.5**. Both paid operations require the owner's signed M12 Gate 3. All development, CI, schema/guard tests, rehearsals, probes used as fixtures, and replay use a fake or disabled transport. No paid M15 matrix, exploration run, probe, P3 rerun or provider bake-off is scheduled here. Credentials come from `.env` only at the approved live invocation. Never display, log, commit or send keys to the model. Store sanitized request bodies and attempts without authorization headers. Keep raw `runs/` artifacts outside Git.

EV-05 has two distinct evidence cases. EV-13 fixes the first at one five-resident, seven-day fake run. For the separate cost rehearsal, EV-05 proposes one seed with Ella on fake transport for three game days and asks the owner to confirm that size. Use both receipts from the card's final locked run when preparing the paid steps.

| Paid operation | Admission and evidence | Stop condition |
|---|---|---|
| 1. DL-06 provider live check | Owner releases the D7 sample against verified pins and a worst-case allowance that fits after all other phase liabilities. EV-05 rehearses the same wires. Persist every sent, failed, retried or interrupted attempt and raw/parsed outcome. Record tariff date, actual token categories, CNY per attempt and first-pass parse rate | A failed check, unverified model, insufficient headroom or unresolved accounting holds step 2. A tool-calling alternative requires a CR |
| 2. EV-06 one live resident | Project whole days with measured check costs, observed fake attempt counts and later-day section sizes. Owner releases Ella's run against the pinned manifest and measured three-day estimate. The operator monitors actual charges and makes new reservations before dispatch including simultaneous consolidation work | Stop before incurring an unaffordable charge. Seal outstanding accounting, stop at the next safe boundary and report incomplete days. Replay/export/inspection are offline |

**Day calculation.** In CNY, let `B = 20 − settled phase spend − outstanding worst-case reservations` after the check. Against each candidate day, multiply the measured CNY per attempt of each call kind by that day's rehearsed attempt counts, adjusted for measured request growth, peak uncached rates, the allowed output and retry exposure. Report the central estimate and the conservative amount held. The affordable horizon is the largest whole-day prefix whose cumulative conservative cost fits B. Use a forecast by day when later contexts grow. Under a flat conservative per-day estimate C, the equivalent bound is `floor(B/C)`. A day is 144 ticks. Report the affordable number alongside the approved three-day target. If fewer than three days fit, hold the run and ask the owner before spending. A documented bound may replace an unavailable rate for planning; absent a credible bound, do not spend. [Decision-loop settings](../../spec/decision-loop-v0.1.md) · [phase plan §4.1](../../plans/p3.5-implementation-plan-v0.1.md).

**Admission per boundary.** EV-04 counts unique dispatched attempts and reserves the largest charge still possible until usage settles. The operator budgets a whole authorized unit through the next safe stop, including retries and overlapping consolidation already in flight. Withhold a unit that cannot be covered. Do not turn budget exhaustion into a resident action, provider failure or change to DL §8's frozen retries and gameplay. Late usage replaces its reservation once. Enter the opening phase balance from evidence. The M9 price and the earlier rough CNY 4 per resident-day estimate cannot establish current purchasing power. Keep measured charges, conservative holds and section estimates distinct. [M9 historical costs](../p3/M9-evidence.md).

## 6. Rules for every card

The owner set the following verification rules on **2026-11-23** for all 18 M14 implementation cards.

| Stage | Executor action | Evidence |
|---|---|---|
| Local Gate 1 | Each round, run Ruff lint and format checks, mypy and import-linter. On the first pass, run pytest on the card's own test folder and the test folders for modules the patch edits. Include a shared module's tests only when the patch actually changes it. | Record the commit, commands, folders, exit codes and counts. |
| Rework | Keep the four static checks. Narrow pytest to the failing tests and the card's own tests, then push the fix to the existing draft PR. | Record the failing test selectors and their new outcomes. CI reruns the rest. |
| GitHub CI | Push the implementation branch and open a draft PR. The full backend suite, frontend job and contract generation/drift job run on GitHub CI only. | Report the PR, commit and CI status immediately and continue with available work. Green backend, frontend and contract jobs on that commit are the full-suite evidence. Link the results when available. |

- **Test count.** Add one test per spec item mapped to the card, plus one test per reachable boundary check (AGENTS.md). Add no other tests. Keep a spec row's required examples, controls and negative cases together in its test. Reuse existing coverage for the same item or boundary. Cards with no mapped items add tests only for reachable boundary checks.
- **Long evidence runs.** At the end of the card, run each required balance round, week run, five-resident fake workload or matrix once under the host lock, using the smallest case count the spec allows. Keep these runs out of routine pytest and repeated CI runs. Retain the inputs and results. On rework, rerun only the cases affected by the change. If the spec leaves the size open, the card states its proposed case count and horizon and asks the owner before running it. Cite a size the owner has already approved. For M13 cards that allow sizing to be deferred, size the long run **after P3.5-EN-08 lands**, using the updated performance measurements.
- Human-in-the-loop mode, 2026-11-23. Codex executors work one branch and isolated worktree per card. Claude Code independently runs Gate 2 and acceptance. The owner makes decisions, authorizes paid dispatch and signs Gate 3. Both unattended runbooks are suspended. Put review notes in the card's **own PR**. Bring fixes back through Claude Code. This planning branch is backed up without a PR.
- **Validate once, at the boundary** (AGENTS.md). Check files, wire messages, model output and public package inputs where they enter and turn them into typed data once. No internal `isinstance` checks, `.get` defaults, casts or fallbacks for states that the types already rule out. Every reachable check ships with a test that reaches it. Parse and type model output once at the provider/model boundary.
- **Record every LLM call** with input, prompt version, model, raw output, parsed result, latency and tokens. Keep all attempts, settings, required immutable versions/hashes, usage/cache and error state. Null unavailable measurements with reasons. Separate reasoning returned by a provider stays in the record and never returns to a subsequent prompt. Capture full manifests, prepared candidates and floor, sent only upon dispatch, and every durable journal cursor. Replay makes zero model calls.
- **Host lock (M13 and M14).** Before a heavy job (full suite, matrix, week run, balance round, long fake workload or full equivalence), create `C:\Temp\li-heavy.lock` exclusively with the card ID and start time inside. If the file exists, wait. The holder deletes the lock when the job ends, including on failure. A lock older than 12 hours may be removed only after confirming there is no live process for that job. Note the stale lock removal in the handoff.
- On Windows give each pytest invocation a fresh, previously nonexistent absolute `--basetemp` under a short writable parent. Use AGENTS.md's command-scoped Git longpaths setting when needed. Keep v2 imports out of test collection if they interfere with the historical registration check in CI. Use repository-supported Python or package scripts for reusable commands.
- Preserve isolation: agents/memory read world only through the protocol; context, recall and consolidation cannot read the audit. A facts-only agreement writer may receive its allowlisted party-specific feed from sim. Commit memory-use credit at first actual decision dispatch and world actions only after binding. Analysis reads verified recorded artifacts, the frontend renders the resulting values. Frozen specs, M13 content and engine code never change on these cards.
- Record unresolved choices at `docs/spec/open-questions.md`; use the smallest reversible fixture assumption. A contradiction with a frozen spec follows [phase plan §7](../../plans/p3.5-implementation-plan-v0.1.md). Stop only the affected part. Do not import parked P3 work or restart its trials. Every handoff includes what changed, commands/results, deviations, questions and the seven fields of [the template](../_template.md). Keep full raw runs and credentials out of all commits.
- Preserve v1 until the signed retirement point. EV-07 is subject to the repository's deletion instructions: identify files individually and request explicit user approval for any batch deletion.

Run the four static checks from the repository root with the locked backend dependencies. Then use the card's scoped pytest command. For example, DL-05 runs `uv run --directory backend pytest tests/v2/resident_replay tests/v2/persistence` if its patch also edits persistence. During rework its pytest selection is `tests/v2/resident_replay` plus any failing selectors outside that folder.

```sh
uv sync --directory backend --locked
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
uv run --directory backend mypy src
uv run --directory backend lint-imports --no-cache
```

The [CI workflow](../../../.github/workflows/ci.yml) defines all three jobs. A card that introduces a v2 contract generator includes its drift check in the contract job through the allocated integration change. A documentation-only handoff records its document checks.

## Planning handoff

The planning change adds this milestone plan, 18 executor cards and the two M14 entries in the open-question register. A read-only check compared the ownership table with the acceptance rows in the four frozen specs. All 105 IDs appear exactly once, and each M14 ID appears on its assigned card. The same check resolved the local Markdown links and anchors and verified every card's branch, executor setting, baseline, handoff fields and place in the waves and ownership table.

Rework on 2026-11-23 incorporates Claude Code's Gate 2 findings B1–B3 on `7af14f2`. The plan and affected cards now distinguish offline and paid start conditions, share the M13 host lock and order the EN-08/DL-04 handoff. The two M14 question entries follow the existing P3.5 entries. When merging the second planning branch, rebase and retain both tracks' register entries.

The owner's subsequent 2026-11-23 addition assigns focused checks to executors and the full jobs to GitHub CI. Section 6 and all 18 cards carry that workflow. Long evidence is scheduled at the end of the owning card.

1. `base_commit` / `result_commit` — `52c51f3d18abeb2255f5060faf17a3d63b7b2648` / the commit containing the verification-policy update on `task/P3.5-M14-cards`.
2. `status` — `READY_FOR_REVIEW` for Claude Code's Gate 2 recheck.
3. `scope_changed` — the owner revised how executors verify cards and size evidence runs. Milestone acceptance and file ownership remain as reviewed.
4. `human_interventions` — two owner instructions on 2026-11-23: the Gate 2 disposition and the subsequent verification-policy addition.
5. `rework_rounds` — one Gate 2 rework round for start conditions, host locking and register order.
6. `verification` — `git diff --check` and a read-only audit passed. The audit checked the local commands, rework scope, CI evidence and test budget on all 18 cards, the long-run sizes and 94 local links and anchors. All 105 spec items retained their assignments. Implementation suites, simulations and live calls are `NOT_RUN` for this documentation change.
7. `open_questions` — D1–D7 are decided. The owner supplies two profile names and trait values before EV-05. The cards request sizing decisions for the DL-05 replay, EV-05 cost rehearsal and EV-07 archive demonstration. Paid dispatch still depends on the M12 signature and measured budget.
