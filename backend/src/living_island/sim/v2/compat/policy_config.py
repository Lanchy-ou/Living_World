"""The compatibility rule policy's configuration, free of the retired v1 engine."""

from living_island.agents.types import PolicyConfig, RuleParams
from living_island.world.content import EffectiveConfig


def script_policy_config(cfg: EffectiveConfig) -> PolicyConfig:
    return PolicyConfig(
        policy_id="rule-based-v0",
        seed=cfg.meta.seed,
        max_plan_actions=cfg.agents.max_plan_actions,
        map_width=cfg.map.width,
        map_height=cfg.map.height,
        script_sha256=None,
        source_trace_sha256=None,
        rule_params=RuleParams(
            rule_params_version="0.1",
            canteen_use="enabled",
            cue_use="enabled",
            fruit_carry_target=2,
            failed_target_retry_ticks=36,
        ),
    )
