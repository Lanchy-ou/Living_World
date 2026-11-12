# ADR 0006: P3 resident-agent foundation

- Status: **Accepted** (owner M8, 2026-11-12).
- Date: 2026-11-12.
- Baseline: `9bd45082002e87172312484a53c4787020bd584d`.
- Scope authority: CR-005 option A, owner-approved 2026-11-11. Exact amendments
  and limits approved at M8 on 2026-11-12, with DeepSeek and CNY150 replacing
  the earlier provider/USD proposal; see the M8 decision record.

## Context

The accepted [P3-00 proposal](../plans/p3-agent-foundation-v0.1.md) requires a resident
who keeps bounded experience and a commitment between model decisions. P1/P2 already
separate runtime ingestion/commit from world execution: `backend/src/living_island/agents/runtime.py:96`,
`:172` and `backend/src/living_island/sim/boundary.py:133`, `:162` at the baseline.
The current context has empty recall/belief arrays (`backend/src/living_island/agents/runtime.py:135`),
and physiological NeedBand is used in provisional memory DTOs
(`backend/src/living_island/agents/types.py:90`, `:97`). Those fields cannot silently
become a new interpretation of the frozen legacy schema.

## Decision

Adopt the [shared interfaces and implementation plan](../plans/p3-implementation-plan-v0.1.md)
and four single-owner specifications linked by the [M8 decision sheet](../tasks/p3/M8-decisions.md).
Use a separate versioned P3 runtime, decision/context and save lane. Keep physical
contracts and legacy serialization unchanged. Experience is resident-local and pure;
identity/goal context is assembled before a bounded provider request. Only validated
plans and accepted cognitive deltas commit; world still settles all physical effects.
A frozen-rule adapter supplies fallback, without changing the accepted P2 algorithm.
Recorded re-execution uses retained decisions and cognitive deltas, never fresh calls.
Durable call evidence is separate from deterministic state so interruption cannot erase
potential spend or silently reissue a call.
One durable registration/case allocation outside run outputs owns live capacity;
exclusive continuation ownership and a current checkpoint head prevent duplicate
restores from spending it twice. Normal already-authorized continuation retains its
grant. Checkpoint/replay mirrors neither create nor refund capacity. The decision
spec owns this protocol and its crash vectors.

Context profiles bind an exact retrieval algorithm to the unchanged projection
algorithm. Manifests record the strategy actually used, and recorded execution reruns
the retained pinned strategy, including the test-only alternative in its fake lineage.
The experience spec owns these bindings and deterministic fixtures.

The plan's extension-port table names later consolidation, forgetting, reflection,
relationships, emotion and dreams. Their behavior is excluded from this decision.
The character panel and debug view remain a P3 deliverable via a separate read-only
inspection artifact; ReplayBundle remains unchanged.

## Alternatives and consequences

| Option | Benefit | Cost / decision |
| --- | --- | --- |
| Small explicit ports and a versioned P3 lane (recommended) | Auditable state, testable boundaries, intact P1/P2 bytes | More version dispatch and explicit recovery records |
| Extend legacy DTOs in place | Fewer model classes | Breaks old request hashes, validators and reference bytes; rejected |
| Adopt a general agent/memory framework now | Many prebuilt behaviors | No demonstrated fit with deterministic world commits and privacy; deferred |
| Ports only, no working experience | Smaller phase | Does not exercise the owner-approved CR-005 option A; rejected |

Bounded capacity eviction is a storage rule, not a psychological forgetting model.
Missing provider usage stays unknown; a registered ceiling controls further dispatch,
not an assertion of the provider's final invoice. Fresh live runs can differ even
with identical seed/configuration. M8 records the approved profile and CNY150 live-trial ceiling;
Gate 2 is outside this authoring team. No acceptance or owner signature is implied here.
