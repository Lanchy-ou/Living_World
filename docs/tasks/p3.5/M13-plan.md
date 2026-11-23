# P3.5 M13 plan — New world runs

## 1. Owner decisions

**Decided by the owner on 2026-11-23.** Claude Code runs independent Gate 2 and acceptance. The owner signs Gate 3 after reviewing the evidence.

| Decision | Approved terms |
|---|---|
| D1. Long-run budget | Allow **30 minutes of cumulative elapsed run time** for a 1,008-tick week on `starter-v1` with three rule-based residents, S2 m6 geometry and ordinary journaling/checkpoints. Use the first registered acceptance seed (initially 2600456787), selected before opening results. A fully timed matching treatment receipt from test CT-13 may also prove D1. P3's V-04 stopped at committed tick 132. |
| D2. Balance qualification | Waves 1–3 carry out starter §9. Calibrate, tune on development seeds, then qualify the final candidate on the held-out pairs before using it for the mechanic demonstrations or speed verdict. |
| D3. P3-PERF-U1 | Dropped for P3.5. EN-07 replaces the store targeted by candidate `124e751`. Preserve `task/P3-PERF-U1-validation-cache` and its history. |
| D4. Original M9 artifacts | **Claude Code** is the custodian for both tracks. Check for a completed search receipt first. If none exists, search the recorded M9 paths and owner-identified backups once, read-only. Record locations, hashes and completeness of any originals. Mark exhausted searches “lost” and inaccessible locations unresolved. CT-10 cites this one record. The search is independent of milestone acceptance. |
| D5. Fixed demo values | Start with the published values. If §9 requires changing a fixed test vector, preserve both sets of values and results and bring OQ-P3.5-M13-1 back to the owner before changing the expectation. |
| D6. LLM measurements | M15 measures item benefits and time use with LLM residents. M13 demonstrates all six benefits by script and measures spare time in both rule-based arms. |
| D7. Recipe-ID scan | Apply the narrow source-context approach in OQ-P3.5-M13-2. A planted recipe reference with the same spelling must still be detected. |

**Early start and risk (owner, 2026-11-23).** M13 and M14 may start while P3.5-PR-07 runs and before the owner signs M12 Gate 3. Dispatch CT-03, CT-04 and EN-08 from current `origin/main`. Work that needs `sim/v2/cli.py` or `sim/equivalence/**` waits until PR-07 merges. Starter §5 still requires the compatibility equivalence check to pass before loading the starter pack. An M12 failure that requires an engine fix may send M13 work back for rework. Recheck affected evidence on the corrected engine. CT-10 waits for the signed M12 before assembling the M13 Gate 3 package.

**Done when.** Each starter mechanic has a scripted demonstration on the qualified pack. The owner can follow mental fatigue into fainting and waking, follow a tool until it breaks, watch fruit decay, follow crafting through use of its products, and see a process persist while residents cooperate to finish it. A long rule-based run on that pack reaches tick 1,008 within D1. The owner checks the six §5.9 benefits, the §9 balance report and the measured speed alongside these demonstrations. [Phase plan §§3–5, 8, 10](../../plans/p3.5-implementation-plan-v0.1.md) · [Starter content §§5–10](../../spec/starter-content-v0.1.md) · [ADR 0010](../../adr/0010-starter-content.md)

**Baseline.** The eight specs froze at `8c803ed`. The original planning base was `101361db91498f20511b793c6171b4b716e969b0`. Record each executor's actual base SHA at dispatch. The owner's 23 November update to M12 §2 at `ffa3f12799f1d5e10cdab59e066a5e3b1592b569` governs review and acceptance. The owner's later 2026-11-23 directions in §6 govern executor tests, CI and long runs for all nine M13 cards. [M12 plan](M12-plan.md) · [PR-07](P3.5-PR-07.md) · [P3 closeout](../p3/P3-closeout.md)

## 2. Waves and start conditions

| Wave | Cards | Starts when | Leaves for the next wave |
|---|---|---|---|
| 1. Pack, run driver and copy cost | [P3.5-CT-03](P3.5-CT-03.md) starter pack, [P3.5-CT-04](P3.5-CT-04.md) resumable driver and [P3.5-EN-08](P3.5-EN-08.md) copy cost | Start from current `origin/main` while PR-07 runs. CT-03 can author pack data, CT-04 can drive existing compat fixtures and EN-08 can trace copy ownership. Apply §1 to work that consumes PR-07. Claude allocates shared edits under §3. | Validated pack pins, a resumable driver and matched before/after time per tick. EN-08 completes its 20-seed per-tick equivalence rerun after PR-07 merges. |
| 2. Calibrate | [CT-05](P3.5-CT-05.md) visible policy comparison | CT-04 and PR-07 merged. Use EN-08's verified revision for the final calibration evidence. | Pin of the policy, calibration inputs, identical decisions and trajectories. |
| 3. Qualify the pack | [CT-06](P3.5-CT-06.md) balance and spare time | CT-03 through CT-05 and EN-08 merged. Calibration is green on the runner used for the paired measurement. | §9 development report, then 40 valid held-out cases on the final candidate, including the preselected D1 timing receipt. Any tuning returns to CT-03. |
| 4. Demonstrate | [CT-07](P3.5-CT-07.md) craft and cooperate, [CT-08](P3.5-CT-08.md) physiology and world-rule boundaries and [CT-09](P3.5-CT-09.md) week-long scripted matter ledger | CT-06 merged and final candidate qualified. All three consume the same immutable pack and CT-04 driver in disjoint directories. | Indexed playable event/packet traces and a seven-day ledger. Schedule heavy jobs serially even when authoring in parallel. |
| 5. Verify speed and assemble Gate 3 | [CT-10](P3.5-CT-10.md) long run and owner report | The owner has signed M12 Gate 3, CT-06 through CT-09 have merged and the qualified pins are available. | D1 timing verdict, mechanic and benefit witnesses, Claude's acceptance verdict and the owner's signature line. |

Each card has its own branch, worktree and Gate 2. A pack change creates a new version/hash, invalidates qualification for that candidate and reopens CT-06 before final scenario and speed sign-off. Preserve earlier rounds. A change to execution, calibration or metrics requires rechecking the affected evidence on its new pins. Changes isolated to evidence presentation can cite the verified underlying run. No worker may use an early integration branch as evidence of M12 acceptance.

## 3. File ownership

Source paths in this section are relative to `backend/src/living_island/`. Each card also owns its named brief's handoff. Under `backend/tests/v2/m13/` each listed directory includes its own fixtures. Store large run artifacts in ignored `runs/m13/`. Commit only small fixture inputs and text evidence with hashes and locators.

| Card | Exclusive writable paths |
|---|---|
| CT-03 | `content/packs/starter-v1/**`, `sim/v2/scenarios/starter.py`, `backend/tests/v2/m13/pack/**` |
| CT-04 | `sim/v2/scenarios/{__init__,runtime,receipts}.py`, `backend/tests/v2/m13/runtime/**` |
| EN-08 | `backend/tests/v2/m13/copy_cost/**` for any missing isolation regression. Production edits require the shared-file allocations below. |
| CT-05 | `sim/v2/scenarios/calibration/**`, `backend/tests/v2/m13/calibration/**` |
| CT-06 | `sim/v2/scenarios/balance/**`, `backend/tests/v2/m13/balance/**`, `docs/tasks/p3.5/M13-balance.md` |
| CT-07 | `sim/v2/scenarios/craft/**`, `backend/tests/v2/m13/craft/**` |
| CT-08 | `sim/v2/scenarios/dynamics/**`, `backend/tests/v2/m13/dynamics/**` |
| CT-09 | `sim/v2/scenarios/conservation/**`, `backend/tests/v2/m13/conservation/**` |
| CT-10 | `sim/v2/scenarios/long_run/**`, `backend/tests/v2/m13/long_run/**`, `docs/tasks/p3.5/M13-gate3.md` |

### Shared files

Claude allocates one named file to one branch at a time across PR-07, M13 and M14. Record the grant in the card's PR and release it after merge. The recipe-scan grant is already in effect. All other entries below are requests or read-only dependencies.

| Shared surface | Card and reason |
|---|---|
| `backend/tests/v2/pack/test_recipe_free.py` | Granted to P3.5-CT-03 by the owner and reviewer on 2026-11-23 for OQ-P3.5-M13-2. Record the grant in CT-03's PR. |
| `sim/v2/compat/policy_host.py` | P3.5-EN-08 requests the policy decision path to remove unnecessary deep copies. Schedule any later CT-05 correction or M14 DL-04 integration after this edit, on the merged revision. |
| `world/v2/engine/tick.py` | P3.5-EN-08 requests the `World.pending_packets` copy path. Preserve the detached delivery approved under OQ-P3.5-PR-05. |
| `sim/v2/compat/config.py` | CT-03 expects to need a small public way to reuse registered config/map admission and bound compat templates when composing the starter leaf. Today `load_compat_pack` also requires a local compatibility code table. Keep code-table admission on the base. Reuse a public PR-07 seam if available. CT-06 would need fresh allocation here and in `compat/registry.py` only if a formally registered replacement seed list cannot be admitted. |
| `sim/v2/compat/{bridge,adapters,receipts}.py` | CT-05 may demonstrate a calibration difference in the existing visible mode. Report the first mismatch and request allocation of the responsible file before running balance. |
| `sim/v2/{runner,turns,manifest}.py` and `sim/v2/cli.py` after PR-07 | CT-04 consumes the existing advance/turn/manifest path. Once PR-07 merges, reuse its per-case receipt and resume mechanism. Request a specific file only if a required boundary handoff cannot be observed via public APIs. M13 commands live under `scenarios/`. |
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
| Copy cost and compatibility after optimization | P3.5-EN-08 | Time per tick before/after on one matched case (121 ticks proposed on EN-08), detached-delivery evidence, green CI for the reviewed commit and a fresh per-tick match on all 20 PR-07 acceptance seeds |
| Phase §4 timed long rule-based run | P3.5-CT-10 | Preselected receipt, elapsed time and final committed tick |
| §9.1/§9.4 benefits and time use measured with LLM residents | M15 (D6) | Handoff of the M13 scenario and metric definitions for the live measurements |

M12 retains CT-01–03, CT-14, CT-15, CT-17, the canteen half of CT-16, and the compatibility halves of CT-10/11. CT-20 reuses the M12 fixture and adapter implementation. Its pre-balance calibration remains an M13 result. CT-07's scripted week and §4's rule-based week require different controllers and separate evidence.

## 5. Gate 3 evidence

CT-10 indexes the evidence below by tested commit, content pins, run ID, relative artifact location and digest. For a demonstration give the tick range, actor, intent and event IDs plus the relevant resident or watcher packet. Include a command to reopen or reproduce each entry. Claude checks the traces on the integrated version and records actual results. The owner can withhold signature or request rework on any missing witness.

| Producer | Evidence to retain |
|---|---|
| EN-08 | Profile locator, compared revisions, matched case and milliseconds/tick before and after. Include the isolation check and PR-07 rerun receipt for 20 matching acceptance trajectories. CT-06 uses this runner for the held-out pairs and CT-10 cites it alongside D1. |
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
- **Local Gate 1 (owner, 2026-11-23).** Install the locked backend dependencies. Every round runs `uv run --directory backend` with each of `ruff check .`, `ruff format --check .`, `mypy src` and `lint-imports --no-cache`. For the initial pytest run select the card's own test folder and the test folders of the modules it actually edits, including any shared file granted under §3. On rework, rerun only failing tests and the card's own tests, then push. On Windows give each pytest invocation a fresh dedicated `--basetemp`. Keep v2 imports out of test collection where they affect frozen v1 registration.
- **GitHub CI.** Push the implementation branch and open a draft PR. The full backend suite runs only on GitHub CI, alongside the frontend and contract jobs. Report the PR, commit and current check status, then continue other work while CI runs. Use green backend, frontend and contract jobs on the reviewed commit as the full-suite evidence. A rework push reruns these jobs.
- **Test count.** Use one test per mapped spec item, plus one per reachable boundary check (AGENTS.md). Reuse existing tests where they cover the item or check. Exercise the item's required outcomes within its test. Add no other tests.
- **Host lock (M13 and M14).** Before a heavy job (full suite, matrix, week run, balance round, long fake workload or full equivalence), create `C:\Temp\li-heavy.lock` exclusively with the card ID and start time inside. If the file exists, wait. The holder deletes the lock when the job ends, including on failure. A lock older than 12 hours may be removed only after confirming there is no live process for that job. Note the stale lock removal in the handoff.
- **Long evidence runs.** Run the card's long workloads once at the end under the host lock, at the smallest case count the spec permits. This applies to matrices, balance rounds, week runs and the five-resident fake workload on its owning track. Keep these runs out of routine pytest and CI iterations. On rework rerun only affected cases, then rebuild the report using verified receipts for unaffected cases. Preserve the complete required seed lists, arms and horizons. For example, CT-06 needs one 40-case development round and one 40-case held-out round for a passing candidate. A changed candidate must still satisfy starter §9.
- **Sizing.** Where the spec leaves a long run's size open, the card states a concrete proposed size and asks the owner to confirm it before execution. In M13, settle flexible sizes after P3.5-EN-08 lands using its measured time per tick. The EN-08 comparison itself uses its card's before/after timing workload. Existing decisions stand for fixed sizes, including D1's single three-resident week. CT-10 reuses the preselected CT-06 timing receipt when it meets D1.
- Long runs and scenario runs write durable receipts. Resume from a verified committed boundary within the interrupted case, with matching inputs and script/policy state. Preserve failures, completed cases and elapsed time across attempts. A partial case cannot pass. Use the EN-07 checkpoint, packet journal and recorded replay. Never commit `runs/` or secrets.
- No paid model calls in M13. Scripts and stand-alone rule-based policies submit through the ordinary coordinator/world boundary. Pin any scripted starting setup separately from the pack. The production balance and timed week use registered geometry and placements. Give residents only their packets and own feedback. Keep analysis of objective facts on the observer side. Leave live measurement to D6.
- Respect §3, including the M14 boundary. Forbidden writes include `agents/**`, `memory/**`, `analysis/**`, frontend, generated types, v1 modules, compat content and other tracks' new paths. Use the shared-file allocation procedure for any exception on the listed shared surfaces. Preserve the default map, v1 pins and independent compatibility evidence.
- A missing rule goes to the question register (coordinated, one writer) with the smallest reversible assumption. A frozen-spec contradiction follows phase §7 with current/requested rule, impact, options and recommendation. Await owner disposition for the affected work. Never edit a frozen spec on an implementation card.
- Each handoff records what changed, commands/results, deviations, open questions, and all seven template fields, including `NOT_RUN`. Distinguish spec tests (e.g. “test CT-04”) from their implementation tasks (“card P3.5-CT-03”). Mark gates and historical trials by their actual status. [Task template](../_template.md) · [Open questions](../../spec/open-questions.md)

## Planning handoff

Claude Code requested four changes to `73abdca`, implemented in `b91e19c`. This follow-up applies the owner's 2026-11-23 verification and run-sizing rules to all nine cards.

| Field | Planning result |
|---|---|
| base_commit / result_commit | `b91e19c` / the commit applying the owner's executor rules on `task/P3.5-M13-cards` |
| status | READY_FOR_REVIEW |
| scope_changed | Yes. The owner approved the early start, EN-08 copy-cost work and the common host lock on 2026-11-23. |
| human_interventions | The owner approved D1–D7 and the Gate 2 revisions on 2026-11-23, then assigned full-suite verification to GitHub CI and limited local tests and long evidence runs. |
| rework_rounds | 1. B1 corrects the start conditions, B2 adds EN-08, B3 adds the host lock and B4 moves the M13 entries to the end of the question register. |
| verification | Checked the local and rework commands for all nine cards, CI handoff, long-run scopes, receipt reuse and the 14 mapped starter tests. This revision changes planning documents only. |
| open_questions | D1–D7 are decided. If tuning requires new fixed expectations, return to the owner under D5. When merging second, rebase and retain both tracks' P3.5 question-register entries. |
