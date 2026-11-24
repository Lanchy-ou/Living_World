"""Project the actual WAP physical frames into the existing analysis-mode replay input."""

from living_island.contract.replay import DisplayFrame, ReplayBundle
from living_island.sim.equivalence.v2_extract import snapshot
from living_island.world.protocol import TERRAIN_BY_SYMBOL


class Display:
    def __init__(self, island):
        self.island = island
        world = island.world
        self.initial = world.initial_events[0].payload["initial_snapshot_hash"]
        self.trees = {
            t.id: dict(zip("xy", t.position, strict=True)) for t in island.config.world.fruit_trees
        }
        self.frames = []
        self.append()

    def append(self):
        world = self.island.world
        frame = snapshot(world, self.island.config.canteen.unique_item_id)
        residents = []
        for r in frame.residents:
            active = world.state.active_actions.get(r.id)
            residents.append(
                {
                    **r.model_dump(exclude={"canteen_id"}),
                    "active_action": {
                        "intent_id": active.intent.intent_id,
                        "action_type": active.intent.verb or active.intent.action,
                        "tick_started": active.tick_started,
                        "remaining_ticks": active.due_tick - frame.tick
                        if active.due_tick is not None
                        else None,
                    }
                    if active
                    else None,
                }
            )
        self.frames.append(
            DisplayFrame.model_validate(
                {
                    "tick": frame.tick,
                    "residents": residents,
                    "fruit_trees": [
                        {**t.model_dump(), "position": self.trees[t.id]} for t in frame.trees
                    ],
                    "ground_fruit": [g.model_dump() for g in frame.ground_fruit],
                    "ground_canteen": {
                        "position": frame.canteen.ground_position.model_dump(),
                        "servings": frame.canteen.servings,
                    }
                    if frame.canteen.ground_position
                    else None,
                    "corpses": [c.model_dump(exclude={"death_tick"}) for c in frame.corpses],
                    "event_range": {
                        "first_index": int(frame.tick > 0),
                        "count": int(frame.tick == 0),
                    },
                }
            )
        )

    def save(self, path):
        island = self.island
        setup, cfg = island.setup, island.config
        # The display schema requires a v1 initialization envelope. All physical
        # WAP events retain their original bytes in the inspection attempts shard.
        replay = ReplayBundle.model_validate(
            {
                "replay_schema_version": "0.1",
                "run_id": setup.run_id,
                "world_id": setup.world_id,
                "config_hash": setup.config_hash,
                "map_hash": setup.map_hash,
                "clock": cfg.time.model_dump(),
                "condition_bounds": {
                    "min_value": cfg.needs.min_value,
                    "max_value": cfg.needs.max_value,
                },
                "map": {
                    "width": cfg.map.width,
                    "height": cfg.map.height,
                    "rows": list(island.compat.map_rows),
                    "terrain_legend": [
                        {"symbol": k, "terrain": v} for k, v in TERRAIN_BY_SYMBOL.items()
                    ],
                },
                "residents": [
                    {"id": k, "display_name": k.title()} for k in sorted(island.profiles)
                ],
                "frames": self.frames,
                "events": [
                    {
                        "schema_version": "0.1",
                        "run_id": setup.run_id,
                        "event_id": f"{setup.run_id}:0000000000:000000",
                        "tick": 0,
                        "seq_in_tick": 0,
                        "type": "world_initialized",
                        "actor_id": None,
                        "target_id": None,
                        "intent_id": None,
                        "llm_call_id": None,
                        "caused_by_event_ids": [],
                        "payload": {
                            "config_hash": setup.config_hash,
                            "map_hash": setup.map_hash,
                            "initial_snapshot_hash": self.initial,
                        },
                    }
                ],
            }
        )
        path.write_bytes(replay.model_dump_json().encode())
