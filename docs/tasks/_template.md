# Task <ID>: <title>

Copy this file to `docs/tasks/<phase>/<id>.md` (e.g. `docs/tasks/p1/P1-02.md`). Template source: P1 plan §5 (card) and §6 (handoff).

## Brief

```text
Task ID / title:
Spec baseline (commit SHA):
Goal / non-goals:
Lane / depends on:
Allowed files / forbidden dependencies:
Deliverables:
Acceptance (positive, negative, edge, determinism):
Verification commands:
Open risks / deferred decisions:
```

## Handoff

Keep the prose required by AGENTS.md, then the seven fields. Unknown values are written as
`unknown`, never as zero. Do not invent a result commit before one exists.

### What changed

### Commands and results

### Deviations

### Open questions

### Required fields

1. `base_commit` / `result_commit`:
2. `status`: `READY_FOR_REVIEW` / `CHANGES_REQUESTED` / `ACCEPTED` / `BLOCKED`
3. `scope_changed`: yes or no, and who approved it:
4. `human_interventions`: count and reasons:
5. `rework_rounds`: count and root causes:
6. `verification`: commands, exit codes, test counts, `NOT_RUN` items:
7. `open_questions`:
