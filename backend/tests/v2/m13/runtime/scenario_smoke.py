"""A five-tick downstream case on the registered mechanics config and map."""

import argparse
import subprocess
from functools import partial
from hashlib import sha256
from pathlib import Path

from living_island.agents.types import OwnProfile, PolicyConfig
from living_island.sim.v2 import cli
from living_island.sim.v2.compat.config import load_compat_pack
from living_island.sim.v2.compat.policy_host import PolicyHost
from living_island.sim.v2.scenarios import runtime
from living_island.sim.v2.scenarios.receipts import CasePlan
from living_island.world.content import EffectiveConfig
from living_island.world.v2 import protocol
from living_island.world.v2.rules import load_vocabulary

ROOT = Path(__file__).resolve().parents[5]
MECHANICS = ROOT / "backend/tests/fixtures/replay/mechanics.toml"


class RestProgram:
    def __init__(self, state):
        self.position = {} if state is None else state["position"]

    def deliver(self, packet):
        return packet.perception.running_action is not None

    def choose(self, request):
        actor = request.delivery.actor_id
        index = self.position.get(actor, 0)
        self.position[actor] = index + 1
        if index == 1:
            choice = protocol.ContinueAction(kind="continue")
        else:
            shape = protocol.IntentShape(
                action="act" if index == 0 else "wait",
                verb="rest" if index == 0 else None,
                target=None,
                instruments=[],
                inputs=[],
                params={},
                reason=None,
            )
            choice = protocol.ModelIntentAction(kind="intent", intent=shape)
        return protocol.ModelTurn(action=choice, utterance=None)

    def checkpoint(self):
        return {"position": dict(self.position)}


def observe(state, boundary):
    return {
        "ticks": state.get("ticks", 0) + 1,
        "events": state.get("events", 0) + len(boundary.result.events),
        "packets": state.get("packets", 0) + len(boundary.opening_packets()),
        "turns": state.get("turns", 0) + len(boundary.turns.submissions),
    }


def plan(mode):
    revision = subprocess.check_output(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    fixture_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    return CasePlan(
        revision=revision,
        runner=sha256(Path(runtime.__file__).read_bytes()).hexdigest(),
        controller=f"{mode}/{fixture_hash}",
        setup=f"mechanics/{fixture_hash}",
        observer=f"boundary-counts/{fixture_hash}",
        arm=mode,
        case_index={"script": 0, "policy": 1}[mode],
        horizon=5,
        checkpoint_every=2,
    )


def setup(mode):
    bound = load_compat_pack(
        MECHANICS,
        cli.PACK,
        load_vocabulary(cli.VOCABULARY),
    )
    cfg = EffectiveConfig.model_validate(bound.config)
    world = cli.setup_world(bound, cfg)

    def hosts(restored):
        config = PolicyConfig(
            policy_id="rule-based-v0",
            seed=cfg.meta.seed,
            max_plan_actions=cfg.agents.max_plan_actions,
            map_width=cfg.map.width,
            map_height=cfg.map.height,
            script_sha256=None,
            source_trace_sha256=None,
            rule_params=cli.BASE_POLICY,
        )
        return {
            resident.id: PolicyHost(
                config,
                OwnProfile(profile_id=resident.profile_id, initial_goal=resident.initial_goal),
                cfg.actions.sleep_ticks,
                restored=None if restored is None else restored[resident.id],
            )
            for resident in cfg.residents
        }

    return runtime.Scenario(
        world,
        bound.manifest.config_blob_sha256,
        bound.manifest.map_blob_sha256,
        runtime.scripted(RestProgram) if mode == "script" else runtime.rule_based(hosts),
        observe,
    )


def cases(mode):
    modes = ("script", "policy") if mode == "campaign" else (mode,)
    return tuple(runtime.CampaignCase(plan(arm), partial(setup, arm)) for arm in modes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--mode", choices=("script", "policy", "campaign"), default="script")
    parser.add_argument("--pause-at", type=int, help="pause the last selected case at this tick")
    args = parser.parse_args()
    selected = cases(args.mode)
    pause = (selected[-1].plan.case_index, args.pause_at)
    for progress in runtime.run_campaign(
        args.directory, selected, pause_after=lambda index, tick: (index, tick) == pause
    ):
        print(f"tick={progress.tick} checkpoint={progress.checkpoint}")
        if progress.evidence is not None:
            print(progress.evidence.model_dump_json())
        print(progress.timing.model_dump_json())
