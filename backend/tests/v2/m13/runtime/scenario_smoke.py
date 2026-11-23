"""A five-tick downstream case on the registered mechanics config and map."""

import argparse
import subprocess
from functools import partial
from hashlib import sha256
from pathlib import Path

from living_island.agents.types import OwnProfile, PolicyConfig, RuleParams
from living_island.sim.v2.compat.config import load_compat_pack
from living_island.sim.v2.compat.policy_host import PolicyHost
from living_island.sim.v2.scenarios import runtime
from living_island.sim.v2.scenarios.receipts import CasePlan
from living_island.world.protocol import TERRAIN_BY_SYMBOL
from living_island.world.v2 import engine, protocol
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
        case_index=0,
        horizon=5,
        checkpoint_every=2,
    )


def setup(mode):
    bound = load_compat_pack(
        MECHANICS,
        ROOT / "content/packs/compat-v1",
        load_vocabulary(ROOT / "content/vocabulary/vocab-0.1.toml"),
    )
    cfg = bound.config
    meta, terrain, clock = cfg["meta"], cfg["map"], cfg["time"]
    senses, social = cfg["perception"], cfg["social"]

    def point(pair):
        return protocol.Coord(x=pair[0], y=pair[1])

    world = engine.initialize(
        bound.pack,
        engine.WorldSetup(
            world_id=meta["world_id"],
            run_id=meta["run_id"],
            seed=meta["seed"],
            config_hash=bound.manifest.effective_config_sha256,
            map_hash=bound.manifest.map_sha256,
            static_map_ref=terrain["layout_file"],
            pack_ids=bound.pack.pack_ids,
            terrain=engine.MapConfig(
                rows=tuple(tuple(TERRAIN_BY_SYMBOL[c] for c in row) for row in bound.map_rows),
                step_costs={
                    key.removeprefix("step_cost_"): value
                    for key, value in terrain.items()
                    if key.startswith("step_cost_")
                },
                walk_budget=terrain["walk_cost_budget_per_tick"],
                opaque_terrains=frozenset(("woods", "fruit_tree", "rock")),
            ),
            clock=engine.ClockConfig(
                tick_minutes=clock["tick_minutes"],
                start_minute=60 * clock["start_hour"],
                day_start_minute=60 * clock["day_start_hour"],
                day_end_minute=60 * clock["day_end_hour"],
            ),
            senses=engine.SensesConfig(
                day_radius=senses["day_radius_tiles"],
                night_radius=senses["night_radius_tiles"],
                hearing_radius=senses["hearing_radius_tiles"],
                cue_detail_radius=senses["cue_detail_radius_tiles"],
                visible_weakness_below=senses["visible_weakness_health_below"],
                visible_dehydration_below=senses["visible_dehydration_hydration_below"],
                visible_fatigue_below=senses["visible_fatigue_stamina_below"],
            ),
            dialogue=engine.DialogueConfig(
                max_turns=social["max_dialogue_turns"],
                gap_ticks=social["dialogue_gap_ticks"],
                cooldown_ticks=social["dialogue_cooldown_ticks"],
            ),
            residents=tuple(
                engine.ResidentSetup(id=r["id"], position=point(r["position"]))
                for r in cfg["residents"]
            ),
            cues=tuple(
                engine.CueSetup(**(cue | {"position": point(cue["position"])}))
                for cue in cfg["world"]["cues"]
            ),
        ),
    )

    def hosts(restored):
        config = PolicyConfig(
            policy_id="rule-based-v0",
            seed=meta["seed"],
            max_plan_actions=cfg["agents"]["max_plan_actions"],
            map_width=terrain["width"],
            map_height=terrain["height"],
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
        return {
            r["id"]: PolicyHost(
                config,
                OwnProfile(profile_id=r["profile_id"], initial_goal=r["initial_goal"]),
                cfg["actions"]["sleep_ticks"],
                restored=None if restored is None else restored[r["id"]],
            )
            for r in cfg["residents"]
        }

    return runtime.Scenario(
        world,
        bound.manifest.config_blob_sha256,
        bound.manifest.map_blob_sha256,
        runtime.scripted(RestProgram) if mode == "script" else runtime.rule_based(hosts),
        observe,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--mode", choices=("script", "policy"), default="script")
    parser.add_argument("--pause-at", type=int)
    args = parser.parse_args()
    progress = runtime.run_or_resume(
        args.directory,
        plan(args.mode),
        partial(setup, args.mode),
        pause_after=lambda tick: tick == args.pause_at,
    )
    print(f"tick={progress.tick} checkpoint={progress.checkpoint}")
    if progress.evidence is not None:
        print(progress.evidence.model_dump_json())
    print(progress.timing.model_dump_json())
