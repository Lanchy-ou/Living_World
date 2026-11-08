"""LLM residents: planner, model adapters and prompt building.

Must NOT: modify world state, import ``living_island.world`` except via its protocol, or
let model output declare world facts. Every model call must be recordable for replay.
"""
