# World Rules Spec v0.1

Skeleton only. Content is defined by later tasks; do not invent numbers here.

## Map & tiles

Map dimensions, tile types, terrain properties, locations (shelter, water, fruit trees).

## Time scale

Game time per tick, ticks per day, day/night boundaries.

## Character state & numbers

Attributes (health, hunger, thirst, stamina), ranges, starting values, inventory limits.

## Needs decay

Per-tick decay and recovery rules for hunger, thirst and stamina; effects on health.

## Action table (preconditions / duration / effects / failure codes)

Every action with its preconditions, duration in ticks, state effects and failure codes.

## Conflict resolution

Deterministic order and rules when several residents contend for the same resource.

## Decision triggers

Explicit list of events that cause a resident to make a new high-level decision.

## Perception rules

Perception radius, day/night modifier, what an Observation contains and excludes.

## Conversation rules

Hearing range, time cost, exchange cap, information transfer limits.

## Resources & regrowth

Stock, gathering yield, tool effect, regrowth timing for plants and water.

## Death

Death conditions and the consequences for the world and other residents.

## Invariants

Properties that must always hold (e.g. resource conservation, non-negative inventory).
