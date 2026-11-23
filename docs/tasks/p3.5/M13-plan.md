# P3.5 M13 plan — New world runs

## 1. Owner decisions

**Proposed for review, 2026-11-23.** Claude Code reviews these cards and runs acceptance. The owner chooses the operating conditions before dispatch and signs Gate 3 after seeing the evidence. Record the chosen options and date in the milestone report.

| Decision | Options | Recommendation and consequence |
|---|---|---|
| D1. How long may the proof take? | Set a fixed limit now, or set one from the signed M12 single-case timings before dispatch. | Allow **30 minutes of cumulative elapsed run time** for one 1,008-tick week, three rule-based residents, `starter-v1`, S2 m6, first registered acceptance seed (initially 2600456787). This is a proposed operating budget. Compare it with PR-07's measured timings before signing. Use the one serial host and ordinary journal/checkpoints. Preselect the case before opening results. A matching timed CT-13 treatment receipt can serve twice. P3's V-04 stopped at committed tick 132 and remains incomplete. |
| D2. When does the §9 balance check happen? | Commission a separate pre-M13 qualification, or make waves 1–3 the qualification stage of this plan. | Use waves 1–3. The pack and measurement tools have to exist first. Require calibration, development and the held-out comparison **before** accepting the candidate for M13 demonstrations and speed evidence. Both options keep the same §9 order and thresholds. Gate 3 needs the qualification receipt under either option. |
| D3. What happens to P3-PERF-U1? | Close the candidate's P3.5 disposition as dropped, or retain it for separately commissioned v1 verification. | Record “dropped for P3.5” now that EN-07 delivers the replacement store. Candidate `124e751` targeted the P3 store and lacked final verification. Record the owner's decision only. Leave branch `task/P3-PERF-U1-validation-cache` and its history intact. |
| D4. Who searches once for the original M9 artifacts? | Name one custodian now, or schedule the search separately once the retained volumes are available. | Name one custodian shared with M14. First check for an existing completed search receipt. Otherwise check the paths in M9-evidence and owner-identified backups once, read-only. Record locations checked, hashes and completeness of originals recovered, or “lost” after the agreed search is exhausted. Identify inaccessible locations as unresolved. CT-10 links the single record. This search is independent of milestone acceptance. |
| D5. What happens if tuning changes a fixed demo value? | Keep the published numeric test vectors on the release candidate, or ask the owner to distinguish a reference-vector result from an approved tuned-candidate result. | Start with the published values. If §9 cannot pass while preserving the fixed CT vectors, retain the failing candidate and its evidence and take OQ-P3.5-M13-1 to the owner before changing an expectation. |
| D6. When are benefits measured with LLM residents? | Use the already planned M15 trials, or leave the live measurement pending a separate owner decision. | Hand the six item benefits and the LLM time-use comparison to M15. M13 demonstrates the benefits by script and measures spare time on the two rule-based arms. No M13 run calls a model. |
| D7. How should the EN-22 recipe scan handle shared words? | Distinguish legitimate uses at specific source locations, or keep the current scan and block the pack until a new method is approved. | Adopt the narrow source-context approach in OQ-P3.5-M13-2. Require the scanner to catch a planted recipe reference with the same spelling. |

**Done when.** Each starter mechanic has a scripted demonstration on the qualified pack. The owner can follow mental fatigue into fainting and waking, follow a tool until it breaks, watch fruit decay, follow crafting through use of its products, and see a process persist while residents cooperate to finish it. A long rule-based run on that pack reaches tick 1,008 within D1. The owner checks the six §5.9 benefits, the §9 balance report and the measured speed alongside these demonstrations. [Phase plan §§3–5, 8, 10](../../plans/p3.5-implementation-plan-v0.1.md) · [Starter content §§5–10](../../spec/starter-content-v0.1.md) · [ADR 0010](../../adr/0010-starter-content.md)

**Baseline.** The eight specs froze at `8c803ed`. This plan was cut from `origin/main` at `101361db91498f20511b793c6171b4b716e969b0` (PR-06 review notes). PR-07 and M12 Gate 3 are prerequisites. The owner's 23 November update to M12 §2 at `ffa3f12799f1d5e10cdab59e066a5e3b1592b569` governs execution, including its dated OQ/CR rulings. Record the signed M12 and actual executor base SHAs at dispatch. M14 may use the compatibility world independently. [M12 plan](M12-plan.md) · [PR-07](P3.5-PR-07.md) · [P3 closeout](../p3/P3-closeout.md)

## 2. Waves and start conditions

| Wave | Cards | Starts when | Leaves for the next wave |
|---|---|---|---|
| 1. Compose and drive | [CT-03](P3.5-CT-03.md) starter pack and placements and [CT-04](P3.5-CT-04.md) resumable run driver | PR-07 merged, compatibility equivalence passed, owner signed M12 and authorized M13 qualification. Claude allocates any required shared edits first. CT-04 can use an existing compat fixture independently of CT-03. | Validated base/leaf hash pair and a driver that resumes inside a case. |
| 2. Calibrate | [CT-05](P3.5-CT-05.md) visible policy comparison | CT-04 merged and M12 fixtures available. Use the compatibility pack in both modes. | Pin of the policy, calibration inputs, identical decisions and trajectories. |
| 3. Qualify the pack | [CT-06](P3.5-CT-06.md) balance and spare time | CT-03 through CT-05 merged, calibration green for this mode and D1/D2 recorded before measurement. | §9 development report, then 40 valid held-out cases on the final candidate, including the preselected timing receipt. Any tuning returns to the sole pack owner, CT-03. |
| 4. Demonstrate | [CT-07](P3.5-CT-07.md) craft and cooperate, [CT-08](P3.5-CT-08.md) physiology and world-rule boundaries and [CT-09](P3.5-CT-09.md) week-long scripted matter ledger | CT-06 merged and final candidate qualified. All three consume the same immutable pack and CT-04 driver in disjoint directories. | Indexed playable event/packet traces and a seven-day ledger. Schedule heavy jobs serially even when authoring in parallel. |
| 5. Verify speed and assemble Gate 3 | [CT-10](P3.5-CT-10.md) long run and owner report | CT-06 through CT-09 merged, reviewed pins available, owner-approved D1 in hand. D3/D4 dispositions can be recorded separately. | Validated speed receipt or an explicit miss, all mechanic and benefit witnesses, Claude's acceptance verdict and a space for the owner's decision. |

Each card has its own branch, worktree and Gate 2. A pack change creates a new version/hash, invalidates qualification for that candidate and reopens CT-06 before final scenario and speed sign-off. Preserve earlier rounds. A change to execution, calibration or metrics requires rechecking the affected evidence on its new pins. Changes isolated to evidence presentation can cite the verified underlying run. No worker may use an early integration branch as evidence of M12 acceptance.

## 3. File ownership

Source paths in this section are relative to `backend/src/living_island/`. Each card also owns its named brief's handoff. Under `backend/tests/v2/m13/` each listed directory includes its own fixtures. Store large run artifacts in ignored `runs/m13/`. Commit only small fixture inputs and text evidence with hashes and locators.

| Card | Exclusive writable paths |
|---|---|
| CT-03 | `content/packs/starter-v1/**`, `sim/v2/scenarios/starter.py`, `backend/tests/v2/m13/pack/**`, `backend/tests/v2/pack/test_recipe_free.py` for actual name collisions with the new pack (OQ-P3.5-M13-2) |
| CT-04 | `sim/v2/scenarios/{__init__,runtime,receipts}.py`, `backend/tests/v2/m13/runtime/**` |
| CT-05 | `sim/v2/scenarios/calibration/**`, `backend/tests/v2/m13/calibration/**` |
| CT-06 | `sim/v2/scenarios/balance/**`, `backend/tests/v2/m13/balance/**`, `docs/tasks/p3.5/M13-balance.md` |
| CT-07 | `sim/v2/scenarios/craft/**`, `backend/tests/v2/m13/craft/**` |
| CT-08 | `sim/v2/scenarios/dynamics/**`, `backend/tests/v2/m13/dynamics/**` |
| CT-09 | `sim/v2/scenarios/conservation/**`, `backend/tests/v2/m13/conservation/**` |
| CT-10 | `sim/v2/scenarios/long_run/**`, `backend/tests/v2/m13/long_run/**`, `docs/tasks/p3.5/M13-gate3.md` |

### Shared files

These are allocation requests for Claude at review or before an overlapping edit. No row grants a write. Allocate one named file to one branch at a time across M13 and M14, record the grant in its PR, then release it after merge. Prefer the existing public operations. Check what PR-07 actually ships before granting an edit.

| Shared surface | Card and reason |
|---|---|
| `sim/v2/compat/config.py` | CT-03 expects to need a small public way to reuse registered config/map admission and bound compat templates when composing the starter leaf. Today `load_compat_pack` also requires a local compatibility code table. Keep code-table admission on the base. Reuse a public PR-07 seam if available. CT-06 would need fresh allocation here and in `compat/registry.py` only if a formally registered replacement seed list cannot be admitted. |
| `sim/v2/compat/{policy_host,bridge,adapters,receipts}.py` | CT-05 may demonstrate a calibration difference in the existing visible mode. Report the first mismatch and request allocation of the responsible file for a tested correction before running balance. |
| `sim/v2/{runner,turns,manifest}.py` and `sim/v2/cli.py` after PR-07 | CT-04 consumes the real advance/turn/manifest path. Request a specific file only if a required committed-boundary handoff cannot be observed via public APIs. Commands live under `scenarios/`. |
| `persistence/v2/**` | CT-04 uses `journal.py`, `checkpoint.py`, `replay.py` and the manifest read-only. If a reproducible journal/checkpoint defect prevents exact resumption, request only the affected file. CT-05–CT-10 consume CT-04's driver. |
| `backend/pyproject.toml` (import-linter section), `contract/**` | No planned writer. Run the existing boundary checks. An actual public contract change needs owner disposition and separate allocation. |

**Engine defects.** The pack expresses recipes as data. For a failure in, e.g., `world/v2/rules/{loader,conservation}.py` or `world/v2/engine/{effects,processes,world_rules,physiology}.py`, the detecting card records the first bad input/phase and expected witness. Claude scopes the smallest generic correction to the responsible card or a separately numbered EN/RR card, with exclusive file allocation and a synthetic `engine-test` regression under `backend/tests/v2/`. Recheck the real scenario and the M12 regression on the corrected pin. Only affected work waits. The M13 track owns necessary world fixes. Cards have no blanket engine write grant.

## 4. Test-to-card map

CT numbers in the left column are **starter-content §10 tests**. The right column gives their single M13 task owner. Several receipts may support one test. Consumers cite the producer's result.

| Test or additional requirement | Task | What the owner can open |
|---|---|---|
| CT-04 | P3.5-CT-03 | Composed pack, ancestor pins, §5.10 parse and validator refusals |
| CT-05 | P3.5-CT-07 | One continuous knap-to-shelter scenario with action IDs and inputs/outputs |
| CT-06 | P3.5-CT-07 | Actor and watcher packets for deceptive cord and traces of blocked and resumed shelter work |
| CT-07 | P3.5-CT-09 | 1,008 scripted ticks and per-class reconciliation against independent live totals |
| CT-08 | P3.5-CT-08 | Regrowth, burn/bake/spill and failed lighting, fruit rot, 20-cut break |
| CT-09 | P3.5-CT-08 | Fatigue inputs, faint interval, sleep recovery |
| CT-10 (starter half) | P3.5-CT-08 | Critical crossing wakes the sleeper, who sleeps through the urgent crossing |
| CT-11 (starter half) | P3.5-CT-08 | Asleep satiety/hydration losses of 15/60 |
| CT-12 | P3.5-CT-03 | All ten deposits on the unchanged map, with real adjacent perceptions |
| CT-13 | P3.5-CT-06 | Calibration prerequisite and final §9 paired verdict |
| CT-16 (clay pot) | P3.5-CT-07 | First fill gives one serving and the next fill reports a full pot |
| CT-18 | P3.5-CT-03 | Normalized rule effects, world-work refusal and initial corpse reserve |
| CT-19 | P3.5-CT-08 | Due-tick insertion, blocked spill then release, split stack aging |
| CT-20 | P3.5-CT-05 | WAP-23 fixtures, DL-25/WAP-35 and 20 calibration seeds, including restore |
| §5.9 six scripted benefits | P3.5-CT-07 | Flake, cord, axe, fire, pot and shelter in use |
| §9.1–9.4 balance before M13 and CT-D9 | P3.5-CT-06 | Paired reports and per-resident/day awake-time fractions for both arms |
| Phase §4 timed long rule-based run | P3.5-CT-10 | Preselected receipt, elapsed time and final committed tick |
| §9.1/§9.4 benefits and time use measured with LLM residents | M15, pending D6 | Handoff of the M13 scenario and metric definitions for pending live measurements |

M12 retains CT-01–03, CT-14, CT-15, CT-17, the canteen half of CT-16, and the compatibility halves of CT-10/11. CT-20 reuses the M12 fixture and adapter implementation. Its pre-balance calibration remains an M13 result. CT-07's scripted week and §4's rule-based week require different controllers and separate evidence.

## 5. Gate 3 evidence

CT-10 indexes the evidence below by tested commit, content pins, run ID, relative artifact location and digest. For a demonstration give the tick range, actor, intent and event IDs plus the relevant resident or watcher packet. Include a command to reopen or reproduce each entry. Claude checks the traces on the integrated version and records actual results. The owner can withhold signature or request rework on any missing witness.

| Producer | Evidence to retain |
|---|---|
| CT-03 | Loader/normalization report and both ancestry hashes, negative inputs with refusal paths, and deposit coordinates, stock and adjacent looks. |
| CT-04 | One interruption inside an action and one resume/refusal comparison, with pending delivery, committed prefix, next choice and canonical output hashes. Include the receipt format, invocation and timing convention for all later cards. |
| CT-05 | Fixture and seed table for both compat policies, first difference if any, private/visible boundary proof, restored mid-queue trace. |
| CT-06 | Per-case receipts, input pins, 20 seed pairs per round, technical validity, all tolerances/denominators and access transitions, per-day spare time, history of tuning and holdouts. |
| CT-07 | Scenario trace and six benefit rows, with watcher/start and watcher/settle looks, contributor identities, completion and shelter sleep. |
| CT-08 | Indexed continuous tick excerpts for each physiology, wear and decay boundary including a blocked transaction and its later release. |
| CT-09 | Scripted-week receipt, starting/ending inventories by matter class, sources, signed transformation losses and first divergence if any. |
| CT-10 | Owner-agreed budget and dated timing result, CPU/host and execution settings, cumulative time, ticks/s, checkpoint history and final digest. Link the decisions on P3-PERF-U1 and M9 (or independent pending status), Claude's checks, residual OQs and owner signature/date. |

## 6. Rules for every card

- Codex executes each implementation card in its own worktree. Claude Code independently reviews (Gate 2) and runs acceptance. The owner decides and signs Gate 3. Both unattended runbooks are suspended. Put review findings and rechecks in the card's own PR.
- Validate once, at the boundary (AGENTS.md). Convert file, message or public-call input to typed data there. Inside, trust the types. No `isinstance` checks, `.get` defaults, casts or fallbacks for states those types rule out. Every reachable check has a test that reaches it.
- Install locked dependencies. On each rework round rerun only `uv run --directory backend pytest tests/v2 tests/p3/test_trial_registration.py`, in **one session**. Keep v2 imports out of collection if they contaminate frozen v1 registration. On Windows use a fresh dedicated `--basetemp` from AGENTS.md for every invocation. Run the full suite once before the PR, **or** use a draft PR's GitHub CI for that full run. Record which path supplied the result. One heavy job at a time on the host, including matrices, week runs, acceptance and full pytest. PR CI covers the repository's backend, frontend and contract jobs.
- Long runs and scenario runs write durable receipts. Resume from a verified committed boundary within the interrupted case, with matching inputs and script/policy state. Preserve failures, completed cases and elapsed time across attempts. A partial case cannot pass. Use the EN-07 checkpoint, packet journal and recorded replay. Never commit `runs/` or secrets.
- No paid model calls in M13. Scripts and stand-alone rule-based policies submit through the ordinary coordinator/world boundary. Pin any scripted starting setup separately from the pack. The production balance and timed week use registered geometry and placements. Give residents only their packets and own feedback. Keep analysis of objective facts on the observer side. Leave live measurement to D6.
- Respect §3, including the M14 boundary. Forbidden writes include `agents/**`, `memory/**`, `analysis/**`, frontend, generated types, v1 modules, compat content and other tracks' new paths. Use the shared-file allocation procedure for any exception on the listed shared surfaces. Preserve the default map, v1 pins and independent compatibility evidence.
- A missing rule goes to the question register (coordinated, one writer) with the smallest reversible assumption. A frozen-spec contradiction follows phase §7 with current/requested rule, impact, options and recommendation. Await owner disposition for the affected work. Never edit a frozen spec on an implementation card.
- Each handoff records what changed, commands/results, deviations, open questions, and all seven template fields, including `NOT_RUN`. Mark gates and historical trials by their actual status. [Task template](../_template.md) · [Open questions](../../spec/open-questions.md)

## Planning handoff

These eight briefs are ready for Claude Code to review. Their implementation handoffs are intentionally open.

| Field | Planning result |
|---|---|
| base_commit / result_commit | `101361db91498f20511b793c6171b4b716e969b0` / the commit publishing this plan on `task/P3.5-M13-cards` |
| status | READY_FOR_REVIEW |
| scope_changed | No. The question register carries the two requested clarifications. |
| human_interventions | The owner supplied the planning scope and duty split. No new owner rulings are assumed. |
| rework_rounds | 0 independent review rounds at publication |
| verification | Documentation checks cover ID ownership, local links, card fields and branch diff. Runtime tests, acceptance runs and Gate 2 are NOT_RUN by the planner. |
| open_questions | D1–D7 await owner choices, including OQ-P3.5-M13-1 and OQ-P3.5-M13-2. |
