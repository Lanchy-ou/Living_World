# M12 orchestration runbook: waves 6 to 9

This runbook is for the Codex orchestrator thread that finishes M12. Read
[AGENTS.md](../../../AGENTS.md), the [M12 plan](M12-plan.md) and every card
before you act. Where this runbook and the specs disagree, the specs win
(AGENTS.md, source of truth order).

## 1. Roles

| Role | Where it runs | Model | Writes |
|---|---|---|---|
| Orchestrator | The owner's thread | `gpt-6.2-astra`, high | Thread prompts, PRs, notes branches, owner reports. Never card code or tests |
| Executor | One thread per card, made with `create_thread`, in its own worktree on the card's branch | `gpt-6.2-sol`, high | The card's allowed files and its handoff |
| Reviewer (Gate 2) | One thread per card, made with `create_thread`, separate from the executor | `gpt-6.2-sol`, xhigh | Only `docs/tasks/p3.5/<ID>-review.md`, on its own review branch |
| Owner | The human user, out of the loop until Gate 3 | — | Gate 3 and the §6.3 report |

- A reviewer never reviews work it helped write (AGENTS.md). The executor
  and reviewer threads of a card are always different threads.
- Rework goes back to the same executor thread. The recheck goes to the same
  reviewer thread, so both keep their context.
- Prompts to executor and reviewer threads are in English. Reports to the
  owner are in plain Chinese with a concrete example, and state your
  recommendation first.

## 2. State at hand-over and the remaining order

You take over in the middle of wave 5 (hand-over on 2026-11-21). The previous
orchestrator was a Claude Code session. It ran Gate 2 round 1 for both wave 5
cards and committed its reviews with this runbook.

**Start condition.** `origin/main` contains this file,
[P3.5-EN-03-review.md](P3.5-EN-03-review.md) and
[P3.5-EN-06-review.md](P3.5-EN-06-review.md). If not, tell the owner
what is missing and wait. This is the one point before Gate 3 where you wait.
Otherwise check the state below from Git (`git log origin/main`, branches,
merged PRs), not from this file.

### 2.1 Wave 5: finish P3.5-EN-03 and P3.5-EN-06

Both cards are in Gate 2 rework. Their executor threads already exist and
were last told to fix and report. Find them with `list_threads`, by branch or
worktree:

| Card | Branch | Worktree | Round 1 findings |
|---|---|---|---|
| P3.5-EN-03 processes | `task/P3.5-EN-03-processes` (round 1 at `a09e9d3`) | `D:/Codex/.codex/worktrees/p35-en03-processes/Living_World` | B1: `TARGET_GONE` must be a phase 6 stop, outside the completion set. B2: three guards need a reaching test or removal |
| P3.5-EN-06 speech | `task/P3.5-EN-06-speech` (round 1 at `b1d3571`) | `D:/Codex/.codex/worktrees/p35-en-06-speech/Living_World` | B1: events edited after emission; add `intent_id` and `self_id_field` to `EventWriter.emit` |

The round 1 owner decisions are recorded at the end of each review:

- OQ-P3.5-EN-03 is confirmed as written;
- OQ-P3.5-EN-06 is confirmed, both parts;
- P3.5-EN-06 may edit `events.py`.

Wave 5 shared files:

- P3.5-EN-03 holds `tick.py`, `state.py`, `settle.py` and `effects.py`;
- P3.5-EN-06 holds `validate.py` and `events.py`.

Steps:

1. Wait for both executor threads with `wait_threads`. Read their reports
   with `read_thread`. Neither has pushed.
2. For each card, create a reviewer thread (§3 step 3) for the **recheck**.
   The prompt says:
   - the round 1 review is the file named above;
   - recheck every finding against the new commits, and append a "Recheck"
     section to that file on the review branch;
   - this reviewer is independent of the executor, as round 1 was.

   Then continue with §3 step 4 and onwards.
3. Merge whichever card passes first. The other one rebases on it (§3 step
   5). Expect a conflict only in `docs/spec/open-questions.md` (§5).
4. The wave 5 notes PR carries the recheck sections. It also adds a row
   for the wave 5 shared-file allocation if the M12 plan does not have one
   yet.

### 2.2 Waves 6 to 9

The remaining cards form one chain. Each one starts only after the one
before it has merged.

| Step | Card | Branch | Starts when |
|---|---|---|---|
| 1 | [P3.5-EN-05](P3.5-EN-05.md) perception and watching | `task/P3.5-EN-05-perception` | EN-02, EN-04, EN-06 merged |
| 2 | [P3.5-EN-07](P3.5-EN-07.md) persistence and replay | `task/P3.5-EN-07-persistence` | EN-01 to EN-06 merged |
| 3 | [P3.5-PR-05](P3.5-PR-05.md) phase B | `task/P3.5-PR-05-sim-turns` (exists; phase A done) | EN-05 and EN-07 merged |
| 4 | [P3.5-PR-06](P3.5-PR-06.md) policy adapters and bridge | `task/P3.5-PR-06-compat-adapters` | PR-03, PR-05, CT-02, EN-02 to EN-07 merged |
| 5 | [P3.5-PR-07](P3.5-PR-07.md) equivalence and the M12 report | `task/P3.5-PR-07-equivalence` | All other M12 cards merged |

After PR-07 merges, stop. M12 Gate 3 belongs to the owner (§6.3). Do not
start M13 work.

### PR-05 phase B

The branch `task/P3.5-PR-05-sim-turns` holds phase A at `9b24a54`, based on
`bb21352`. It was not pushed. Its worktree is
`D:/Codex/.codex/worktrees/p35-pr05-sim-turns/Living_World`. Its phase A
executor thread is told to wait for a phase B signal. Find it with
`list_threads` and continue in it. Start a new executor thread on the branch
only if the old thread is gone.

The phase B prompt must include the card's phase B section and these three
items from the phase A direction check:

1. The turn ID format `f"{actor_id}:t{ordinal:06d}"` exists in both
   `world/v2/engine/validate.py` and `sim/v2/turns.py`. Confirm that the
   protocol fixes this format. Add a real-World test in which the runner's
   turn ID binds, so the two copies cannot drift apart silently.
2. `turn_reasons` gives the `notification` reason only when
   `running_action` is not `None`. Show with a real-World test that this case
   is reachable, or remove the condition.
3. OQ-P3.5-PR-05 (reading pending deliveries and turn ordinals from
   `World.state`) is accepted for now. Confirm it against the real packets
   from EN-05.

## 3. Per-card cycle

1. **Executor thread.** Create it with `create_thread`:
   - target: this project, a worktree on the card's branch;
   - `onMissing: "create-branch"` from current `origin/main`;
   - `gpt-6.2-sol`, `thinking: "high"`.

   The prompt names the card file, the base commit, and the rules of §4 and
   §5. It ends with: "Commit, write the handoff with the seven fields, push
   nothing, report the commit SHAs."
2. **Wait** with `wait_threads`. Then read the report and the handoff. Check
   that the worktree is clean, the commits exist, and the diff touches only
   allowed files (§5).
3. **Reviewer thread.** Create it with `create_thread`:
   - its own worktree on branch `task/<ID>-review`, from `origin/main`;
   - `gpt-6.2-sol`, `thinking: "xhigh"`.

   The prompt is in §4.2.
4. **Verdict Pass:** go to step 6. **Changes requested:** send the findings,
   each with its concrete fix, to the executor thread
   (`send_message_to_thread`). When the fix comes back, send the recheck to
   the reviewer thread.

   **The owner is out of the loop for review outcomes** (owner decision,
   2026-11-21; this replaces the "one recheck" limit of M12 plan D5 for
   waves 6 to 9). A failed recheck never goes to the owner. Each failed
   recheck gives fix instructions, and the loop goes on until the reviewer
   passes the card. The reviewer stays the same independent thread throughout.

   If a fix does not converge, escalate as follows, inside Codex:
   - **First failed recheck:** the reviewer states each open finding as a
     precise change. It names the file and function, the expected behavior,
     and the test that must fail before the fix and pass after it.
   - **Same blocking finding fails a second recheck:** you write a short fix
     plan from the review and the spec. The executor follows it step by step.
   - **Still open after that:** start a fresh executor thread on the same
     branch (`gpt-6.2-sol`, high). Give it the card, every review section and
     the fix plan, and continue with the same reviewer.
   - Never pass a card by weakening a test or by narrowing the acceptance.
     Never let the executor review itself.

   Record the round count and the root causes in the handoff
   (`rework_rounds`).
5. **Rebase.** If `main` moved, the executor rebases and reruns the focused
   Gate 1 runs. The reviewer confirms that the code commits are unchanged
   (`git range-diff`).
6. **PR and merge.**
   - Push the card branch.
   - Open a PR to `main` through Codex's GitHub access, which runs as the
     owner's account. The PR body says what changed and gives the Gate 1 and
     Gate 2 results.
   - Wait for the three CI jobs (`backend`, `frontend`, `contract`). The
     backend job takes 10–20 minutes.
   - Merge with a merge commit after all three pass. Then fast-forward the
     main checkout: `git fetch`, then `git merge --ff-only origin/main`.
   - Never push to `main` directly. Never force-push a branch that is already
     in a PR. Never merge on red or pending CI.
7. **Notes PR.**
   - After each merged card, or for two adjacent cards together, make
     branch `task/P3.5-M12-<card>-review-notes` from `main`.
   - Take the review file from the review branch:
     `git checkout task/<ID>-review -- docs/tasks/p3.5/<ID>-review.md`.
   - Add any M12 plan ownership note from §5. Commit, open a PR, and merge
     it on green CI.
8. **Post a progress note** in your own thread, in two or three Chinese
   sentences: what merged, what is next, and any §6.1 decision. The owner
   reads these later; do not wait for a reply.
9. **Clean up** only what this runbook created:
   - the pytest base folders `C:\Temp\li-*` of finished runs;
   - archive the card's executor and reviewer threads after the notes PR
     merges (the app snapshots their worktrees).

   Never touch `.p3ext-*`, `g2-*`, or P3 Codex worktrees and branches. They
   are retained P3 evidence.

## 4. Rules for the threads

### 4.1 Executor prompt essentials

- Read AGENTS.md, the card, M12 plan §3 and §6, and the specs the card
  names.
- **Validate once, at the boundary** (AGENTS.md, owner decision 2026-11-20):
  - no `isinstance` checks, `.get` defaults, casts or fallbacks for states the
    types already rule out;
  - no compatibility shims;
  - every reachable check ships with a test that reaches it.
- Missing or ambiguous spec: do not invent rules or numbers.
  - Append `OQ-<ID>` to `docs/spec/open-questions.md`.
  - Make the smallest reversible assumption and flag it in the handoff.
  - A contradiction with a frozen spec follows §6.1. Never edit a frozen
    spec.
- **Gate 1, from the worktree, with locked dependencies:**
  - `uv sync --directory backend --locked`;
  - `ruff check .`, `ruff format --check .`, `mypy src` and
    `lint-imports --no-cache`, each with `uv run --directory backend`;
  - `pytest tests/v2 tests/p3/test_trial_registration.py`, in **one**
    session;
  - the full `pytest` suite.
- **On Windows:**
  - each pytest run gets a new, unused `--basetemp` under `C:\Temp\li-*`;
  - set command-scope Git long paths: `GIT_CONFIG_COUNT=1`,
    `GIT_CONFIG_KEY_0=core.longpaths`, `GIT_CONFIG_VALUE_0=true`.
- The full suite takes about 40 minutes. Run it in the background with a log
  file, and read the result when it ends.
- The handoff follows `docs/tasks/_template.md`, with the seven fields.
  Record every scope change and every edited shared file.

### 4.2 Reviewer prompt essentials

- You did not write this work, and you must not edit the card's files or
  commit to its branch. Review the exact executor commit, named by SHA.
- Check against the card's acceptance tests and the specs it names. Give a
  file-and-line finding for each spec deviation. Map each acceptance ID to a
  test.
- Flag:
  - defensive code that no input can trigger;
  - reachable checks without a test;
  - fallbacks and defaults for states the types rule out;
  - edits to objects after they are published or logged;
  - logic duplicated from another module.
- For new tests that guard wiring, run a mutation check: remove the wiring in
  a scratch worktree and confirm that the tests fail.
- Run Ruff, mypy, import-linter, and
  `pytest tests/v2 tests/p3/test_trial_registration.py` yourself (§4.1
  Windows rules). Use a scratch worktree on a short path under `C:\Temp`, and
  remove it afterwards.
- **Output.** Write `docs/tasks/p3.5/<ID>-review.md` in the format of
  [P3.5-EN-02-review.md](P3.5-EN-02-review.md):
  - Verdict;
  - Checks run;
  - Findings, each `B<n>` blocking with a concrete fix;
  - Notes;
  - open questions for the owner, with a recommendation.

  Commit it on `task/<ID>-review`. For a recheck, append a "Recheck" section.

## 5. Shared files and standing rules

The orchestrator may decide these without asking the owner. Record each one
in the card's handoff and in the next notes PR.

- `world/v2/engine/tick.py`, `state.py` and
  `backend/tests/v2/engine/conftest.py` change in **one branch at a time**
  (M12 plan §3). The chain is serial, so the running card holds them.
  Record that in the handoff.
- A card may edit an engine file owned by a merged card when its acceptance
  tests need it. Keep the change minimal and list it in the handoff. No
  open card may hold that file.
- **Tests of a merged card** may be updated only when they fail because
  newly implemented behavior now runs. Conditions:
  - keep every assertion about the behavior the test was written for;
  - add an assertion for the new effect rather than deleting an old one,
    unless the old one is now false;
  - never weaken an assertion;
  - never change a fixture pack (`engine-test*` belongs to P3.5-CT-01 and
    P3.5-RR-02);
  - list every such test under Deviations.
- **Rebase conflicts in `docs/spec/open-questions.md`:** keep every entry,
  in `main`'s order, with the new entries after.

## 6. Decisions while the owner is away

The owner is out of the loop until M12 Gate 3. Do not wait for answers.
Decide as follows, and record every decision in the handoff, the review and
a running list in the final report (§6.3).

### 6.1 Decide and continue

- **Open questions** (missing or ambiguous spec), as AGENTS.md prescribes:
  - append `OQ-<ID>` to `docs/spec/open-questions.md`;
  - take the smallest reversible assumption and flag it.

  The reviewer judges whether the assumption is the smallest reversible
  one. The question stays open for the owner.
- **Contradiction with a frozen spec:**
  - never edit `docs/spec/`, `docs/adr/` or `docs/product/`;
  - record a proposed change request in `docs/spec/open-questions.md`
    (plan §7 format, status "proposed, awaiting owner");
  - implement the frozen text as written where possible. Where the frozen text
    cannot be implemented, take the smallest reversible assumption, mark it
    in code comments and the handoff, and continue.
- **Scope beyond the card and §5** (an engine file owned by a merged card,
  or a shared test helper):
  - allow the minimal change when the card's acceptance needs it and no open
    card holds the file;
  - the reviewer checks that it is minimal.
- **Fixture pack changes** (`engine-test*`, `compat-v1`): avoid them. If a
  card cannot be accepted without one, make the smallest change in a separate
  commit, and have the reviewer confirm that every earlier test still means
  what it meant.
- **CI failing for a reason the card did not cause:** open a narrow fix card,
  `task/P3.5-FIX-<n>-<slug>`, with its own executor and reviewer. Merge it
  first, then continue.

### 6.2 Never do, even when the owner is away

- Delete anything that §3 step 9 does not list. This includes `.p3ext-*`,
  `g2-*`, and P3 Codex worktrees and branches.
- Rewrite history on `main` or on pushed branches; force-push; merge on red
  or pending CI.
- Restart deferred P3 trials or merge parked P3 candidates (AGENTS.md).
- Commit secrets, `.env`, or `runs/` content.
- Sign Gate 3, or start M13 work.

### 6.3 Final report at M12 Gate 3

After PR-07 merges, stop. Give the owner, in Chinese:

- the equivalence report (`docs/tasks/p3.5/M12-equivalence-report.md`);
- every open question, proposed change request, scope decision and fixture
  change made under §6.1, each with its card and your recommendation;
- review round counts per card.

The owner signs Gate 3 and may ask for an extra independent review first.

## 7. Tools

- **Threads:**
  - `create_thread`, `wait_threads` and `read_thread` from the Codex app
    tools;
  - `send_message_to_thread` only for threads you created under this
    runbook, which the owner's start message authorizes.
- **Git and GitHub:** `git` for branches and pushes. For PRs, CI status
  and merges, use Codex's GitHub access, which acts as the owner's account.
  The GitHub CLI `gh` also works if it is installed and signed in.
- One thread waits on at most eight others. This chain needs one executor and
  one reviewer at a time.
