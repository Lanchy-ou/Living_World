"""Authoritative world: state, tiles, time, rules, actions, resolution and perception.

Responsibility:
    Own all world state and the only code that changes it. Validate and resolve action
    intents deterministically (seeded RNG, fixed resolution order). Build the limited
    ``Perception`` each resident receives (perception lives here).

Must NOT:
    Import any other ``living_island`` subpackage, or any LLM / network library
    (``anthropic``, ``openai``, ``httpx``, ``requests``, ``fastapi``). Accept direct world
    modifications from agents or LLM output. Know about rendering or persistence formats.
"""
