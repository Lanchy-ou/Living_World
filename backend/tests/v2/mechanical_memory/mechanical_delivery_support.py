"""World setup and boundary helpers for mechanical gift and fallback scenarios."""

A, B, C = "res_a", "res_b", "res_c"

SLEEP_RULE = """
[[rule]]
id = "packet_sleep"
trigger = "verb:sleep"
work_ticks = { param = "duration_ticks" }
"""
BODY = """
enabled_verbs = ["sleep"]
enabled_needs = ["health", "satiety", "hydration", "mental_fatigue"]

[physiology]
replace = true
stamina_awake_decay_per_tick = 0
stamina_move_extra_cost_per_tick = 0
satiety_awake_decay_per_tick = 1
satiety_asleep_decay_per_tick = 1
health_recovery_min_satiety = 10
hydration_awake_decay_per_tick = 1
hydration_asleep_decay_per_tick = 1
health_recovery_min_hydration = 10
health_loss_per_tick_if_deprived = 1
health_recovery_sleep_per_tick = 0
awake_per_tick = 1
per_utterance_heard = 0
per_first_sighting = 0
recovery_per_tick_asleep = 1
faint_ticks = 3

[timing]
replace = true
invalid_attempt_ticks = 1
give_ticks = 3
pick_up_ticks = 1
drop_ticks = 1
wait_ticks = 1
inspect_ticks = 1

[timing.attempt_ticks]
build = 1
combine = 1
fill = 1
gather = 1
rest = 1
strike = 1
sleep = 1

[needs.health]
min = 0
max = 10
initial = 10
band_cutoffs = [2, 4, 6, 8]
max_gain_per_tick = 0
max_loss_per_tick = 1

[needs.satiety]
min = 0
max = 10
initial = 10
band_cutoffs = [2, 4, 6, 8]
max_gain_per_tick = 0
max_loss_per_tick = 1
thresholds = [{ id = "urgent", at = 3, wakes = true }]

[needs.hydration]
min = 0
max = 10
initial = 10
band_cutoffs = [2, 4, 6, 8]
max_gain_per_tick = 0
max_loss_per_tick = 1

[needs.mental_fatigue]
min = 0
max = 100
initial = 0
band_cutoffs = [20, 40, 60, 80]
max_gain_per_tick = 0
max_loss_per_tick = 1
"""
GIFT_STACKS = """
[[instance]]
id = "gift_source"
archetype = "arch_a"
at = { holder = "res_a" }
quantity = 2

[[instance]]
id = "gift_survivor"
archetype = "arch_a"
at = { holder = "res_b" }
"""


def pending(world, actor):
    return world.state.pending_deliveries[actor]


def step(world, *turns):
    return world.step(
        turns, acknowledged={p.actor_id: p.delivery_id for p in world.pending_packets()}
    )


def turn(world, actor, action, **fields):
    from living_island.sim.v2.turns import TurnRequest
    from living_island.world.v2.protocol import ModelTurn

    request = TurnRequest(pending(world, actor), world.state.turn_ordinals[actor], ())
    intent = {
        "action": action,
        "verb": None,
        "target": None,
        "params": {},
        "instruments": [],
        "inputs": [],
        "reason": None,
        **fields,
    }
    choice = ModelTurn.model_validate(
        {"action": {"kind": "intent", "intent": intent}, "utterance": None}
    )
    return request.bind(choice)


def entity(key, kind="entity"):
    return {"kind": kind, "id": key}
