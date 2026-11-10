"""Read-only analysis of finished experiment runs (P2 experiments v0.1 §3-§7).

Responsibility:
    Compute the §3 metrics, the §4 technical-validity checks and pass lines, and the §5 paired
    comparisons as pure functions over parsed objects (events, decision records, replay,
    checkpoints, trace manifest) plus a few config values.

Must NOT:
    Do file IO, write into a run directory, or import ``living_island.world``,
    ``sim``, ``persistence``, ``memory`` or the agent runtime and policies. It may import
    ``living_island.events``, ``living_island.contract`` and ``living_island.agents.types``.
    ``scripts/p2_experiments.py`` loads the artifacts and calls into this package.
"""
