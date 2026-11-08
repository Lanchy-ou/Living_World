# Interface Contract

Skeleton only. The contract is defined as pydantic models in
`backend/src/living_island/contract/` and exported to TypeScript by `scripts/gen_types.py`.

## Snapshot format

World snapshot written at tick boundaries as JSON; what it contains and how it is restored.

## Event format (tick, seq, failure code, llm_call_id)

Event log record layout (JSONL): tick, sequence within tick, type, failure code, link to the
LLM call that caused it. This is also the frontend replay file format.

## LLM call log format

Per-call record: input observation, prompt version, model, raw output, parsed result,
latency, token counts.

## Character panel view

Read-only view model the frontend shows for a selected character.

## Player commands

Commands the frontend may send (pause, step, speed, paused-only parameter edits, dreams).

## Versioning

Schema version field, compatibility rules and snapshot migration policy.
