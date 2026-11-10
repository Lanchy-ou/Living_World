"""Experiment-case identity and the ``P2CaseManifest`` record (P2 experiments §6). No file IO."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_island.agents.types import RuleParams

BATCH_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
HASH64 = r"^[0-9a-f]{64}$"


def is_valid_batch_id(batch_id: str) -> bool:
    return BATCH_ID_PATTERN.fullmatch(batch_id) is not None


def case_id_of(scenario_id: str, revision_label: str, variant_id: str, seed: int) -> str:
    """``<scenario_id>.<revision_label>.<variant_id>.s<seed>``."""
    return f"{scenario_id}.{revision_label}.{variant_id}.s{seed}"


class P2CaseManifest(BaseModel):
    """One manifest per case (§6). ``cli_args`` follows ``-m living_island`` exactly."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal["0.1"]
    case_id: str
    batch_id: str
    scenario_id: str
    revision_label: str
    scenario_file: str  # repo-relative path of the world TOML
    pin_commit: str  # the label's pin commit
    content_revision_sha256: str  # config hash of scenario_file as committed
    script_file: str | None
    seed: int
    cli_args: list[str]
    policy_id: str  # tick-0 policy_config.policy_id
    policy_variant_id: str
    rule_params: RuleParams | None  # tick-0 policy_config.rule_params; null for P1 policies
    script_sha256: str | None
    policy_config_sha256: str
    config_sha256: str  # effective identity, from world_initialized
    map_sha256: str
    run_id: str
    run_dir: str  # relative to the batch directory
    events_sha256: str
    decisions_sha256: str
    final_world_sha256: str
    code_commit: str
