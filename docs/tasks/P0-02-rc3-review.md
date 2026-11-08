# Task P0-02-rc3: Optimize the reviewed World Rules draft

## Brief

Branch: `task/P0-02-rc3-review-fixes`.

The user requested a concise prompt for Claude describing the rc2 review findings,
then authorized immediate optimization. Create a new rc3 review bundle rather than
overwrite rc2 or land unapproved production specifications. Fix the identified P1
contract gaps, balance reasoning and cross-file inconsistencies. Preserve the source
map and document every new candidate choice. No production engine development,
generated-type edit, dependency change, deletion or approval-status change is in scope.

## Handoff

### What changed

- Created `_design_staging/P0-02-rc3` with matching world rules, interface contract,
  TOML, unchanged map, balance notes, change log, README and a standalone checker.
- Defined pending physical observation delivery/restore, historical target exposure
  receipts, complete active intents, deterministic novelty/interrupt vocabularies,
  positive transfers, ground pile identity and final sleep-tick physiology.
- Changed only hydration among balance variables, from 120 to candidate 100/tick;
  retained rc2 geometry/speed, and replaced compulsory-cave reasoning with measurable
  travel/task/water-delivery benefits and controlled P2 comparisons.
- Corrected drink-tick metabolism, isolated death ticks and the south spring stand
  route to fruit_02: cost 48 needs 7 actual movement ticks, not 6.
- rc2, official specs/product/ADR, production code and generated types were untouched.

### Commands run and results

- `python -B _design_staging/P0-02-rc3/tools/validate_rc3.py`: exit 0, **13 checks
  passed**, including all 13 published route vectors, real tick packing, initial LOS,
  map identity, parameter references and cross-file terrain/action/failure vocabularies.
- `backend/.venv/Scripts/ruff.exe format _design_staging/P0-02-rc3/tools/validate_rc3.py`:
  formatted the new checker only; exit 0.
- `backend/.venv/Scripts/ruff.exe check _design_staging/P0-02-rc3/tools/validate_rc3.py`:
  exit 0, all checks passed.
- `backend/.venv/Scripts/ruff.exe format --check _design_staging/P0-02-rc3/tools/validate_rc3.py`:
  exit 0, already formatted.
- Production CI/type generation was not rerun: no production/dependency/contract
  implementation changed. Content/reference checks do not prove runtime save/replay
  correctness or balance. Those tests explicitly remain P1/P2 deliverables.

The first checker run caught an additional route-packing error (48 cost units do
not guarantee six ticks) and an overly broad parameter-reference match on the
Perception DTO. Corrected the route table and clarified the DTO reference.

### Deviations

- The authorized deliverable remains a staged candidate. No final approval, commit,
  production landing or message to another person/service was performed.
- Git's safe-directory exception was supplied per command, not written to config.
  Creating the required task branch needed filesystem escalation and succeeded.
- Standalone design checks accompany these draft changes; they are not a substitute
  for future world-rule tests against the implemented engine.
- The existing `.git/info/exclude` ignores `_design_staging/`; the rc3 bundle is
  present locally but intentionally not staged. Only this new task handoff appears
  in Git status; tracked production files have no diff. Do not mistake an empty
  production diff for an absent review bundle.

### Open questions

- Hydration 100 is not validated as moderate; P2 must measure it against 120 at fixed
  geometry/policy and define benefit/survival thresholds in advance.
- The no-canteen experiment needs an explicitly identified P2 fixture/schema; default
  P1 retains the invariant that exactly one canteen exists.
- Before P3, finalize agent-interface design; P4/P6 memory/dream rules remain deferred.
- New semantic choices are listed in the rc3 change log for Claude/user review; none
  is presented as previously approved. Formal `docs/spec/open-questions.md` was not
  changed because this task keeps the production specification untouched; staging
  questions live in the rc3 change log and this handoff.
