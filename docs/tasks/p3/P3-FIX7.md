# Task P3-FIX7: Project entry documentation

## Brief

```text
Task ID / title: P3-FIX7 / Project entry documentation.
Spec baseline (commit SHA): ea27c67f326700e71a44c805ed6ca3a97c3d19f8.
Goal / non-goals: Provide current P3 entry points and local CI verification instructions. Preserve task scopes and approval rules.
Lane / depends on: Documentation. Start from the unified baseline after P3-CI1.
Allowed files / forbidden dependencies: README.md, AGENTS.md and this task card. No changes to specs, CI, scripts, or application code.
Deliverables: Phase status, P3 links, locked setup, CI command mapping, and Windows test guidance.
Acceptance (positive, negative, edge, determinism): Resolve local Markdown links. Match all CI run entries and frontend scripts. Check M9 acceptance and follow-up task status. Check that Windows command-scope Git configuration reaches child processes and pytest receives an unused base path.
Verification commands: Git diff check, Python inline documentation consistency checks, and PowerShell validation of Git command scope and base path generation.
Open risks / deferred decisions: The full application suite runs on the final integration branch.
```

## Handoff

### What changed

README and AGENTS link the P3 plan, the four P3 specifications, M9 evidence,
and both pending follow-up task cards. They use locked dependency setup.
AGENTS lists the backend, frontend and contract CI commands, including both
frontend test scripts. The Windows instructions document repository-local
Git configuration, inherited command-scope settings for temporary
repositories, and a dedicated pytest base path.

Implementation agent was Sol / Medium (`gpt-6.1-sol`, medium). The architecture
lead passed the required AGENTS review of the implementation commit before
integration. The independent Sol / High Gate 2 (`gpt-6.1-sol`, high) requested
one clarification: the Windows definition of done must require a new dedicated
`--basetemp` on each pytest run. The lead approved the corrected wording,
which is pending independent recheck.

### Commands and results

- `git diff --check` exited 0 on the original changes and the review correction.
- Inline `python -` exited 0. Resolved 17 distinct local Markdown targets,
  checked the order of validation commands and the locked setup in all 16 CI
  run entries across three jobs, verified the relevant frontend script names,
  and checked M9 acceptance and the two follow-up task cards.
- PowerShell check exited 0. With Git's command-scope environment set, a
  child `git -C $env:TEMP config --show-scope --get core.longpaths` reported
  `command true`. The path generated for the pytest example was unused.
- Application tests executed here: 0. Backend and frontend checks and contract
  generation are NOT_RUN for this documentation task. See the final integration
  verification. GitHub Actions for this branch is NOT_RUN.

### Deviations

None.

### Open questions

None.

### Required fields

1. `base_commit` / `result_commit`: `ea27c67f326700e71a44c805ed6ca3a97c3d19f8` / `377767afd659086b704aabef3ab6cc779b7fcb2a`.
2. `status`: `READY_FOR_REVIEW`.
3. `scope_changed`: no.
4. `human_interventions`: 0.
5. `rework_rounds`: 1. The Windows definition of done described the required pytest base path as optional.
6. `verification`: three documentation checks exited 0. Application tests
   and full local CI are NOT_RUN on this task branch. GitHub Actions is NOT_RUN
   on this task branch. Gate 2 recheck is pending.
7. `open_questions`: none.
