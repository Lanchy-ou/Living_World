"""Run offline M12 compatibility trajectories against the v1 archive."""

import argparse
import json
import posixpath
import subprocess
import sys
import tomllib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import partial
from hashlib import sha256
from pathlib import Path, PurePosixPath
from time import perf_counter

from living_island.agents.types import OwnProfile, PolicyConfig, RuleParams
from living_island.persistence._codec import PersistenceError
from living_island.persistence.v2.journal import PacketJournal, store_once
from living_island.sim.equivalence.compare import first_difference, legacy_replies
from living_island.sim.equivalence.projection import Projection, canonical_bytes, read_projection
from living_island.sim.equivalence.v2_extract import (
    EXCEPTION_NAMES,
    ProjectionHost,
    V2Extractor,
    declared_exceptions,
    snapshot,
)
from living_island.world.content import EffectiveConfig
from living_island.world.protocol import TERRAIN_BY_SYMBOL
from living_island.world.v2.engine import World, initialize
from living_island.world.v2.engine.validate import (
    ClockConfig,
    CueSetup,
    DialogueConfig,
    MapConfig,
    ResidentSetup,
    SensesConfig,
    WorldSetup,
)
from living_island.world.v2.protocol import Coord, Terrain
from living_island.world.v2.rules import load_vocabulary

from .compat.bridge import LegacyBridge
from .compat.config import BoundCompatPack, load_compat_pack
from .compat.policy_host import PolicyHost, PolicySession
from .compat.registry import REGISTRY

ROOT = Path(__file__).resolve().parents[5]
FIXTURES = ROOT / "backend/tests/fixtures/v1_projection"
PACK = ROOT / "content/packs/compat-v1"
VOCABULARY = ROOT / "content/vocabulary/vocab-0.1.toml"
WALKABLE: tuple[Terrain, ...] = ("beach", "grass", "woods", "cave", "damp_moss", "fruit_tree")
HORIZON = 1008
DEVELOPMENT = {
    ("s1-orig", "base"),
    ("s2-orig", "base"),
    ("s2-orig", "canteen-restricted"),
    ("s2-orig", "cue-ignored"),
    ("s3-orig", "base"),
    ("s4-orig", "base"),
    ("s4-orig", "canteen-restricted"),
}
BASE_POLICY = RuleParams(
    rule_params_version="0.1",
    fruit_carry_target=2,
    failed_target_retry_ticks=36,
    cue_use="enabled",
    canteen_use="enabled",
)
POLICIES = {
    "base": BASE_POLICY,
    "canteen-restricted": BASE_POLICY.model_copy(update={"canteen_use": "restricted"}),
    "cue-ignored": BASE_POLICY.model_copy(update={"cue_use": "ignored"}),
}


def matrix_names() -> list[str]:
    """Enumerate the frozen P2 arms and the seed lists in §2."""
    names: list[str] = []
    seen: set[int] = set()
    for suite, arms in (
        ("development", DEVELOPMENT),
        ("acceptance", {("production", "base")}),
    ):
        target = len(seen) + 20
        index = 0
        while len(seen) < target:
            digest = sha256(f"living-island/p2/{suite}/{index}".encode()).digest()
            seed = 1 + int.from_bytes(digest[:4], "big") % (2**32 - 1)
            index += 1
            if seed not in seen:
                names.extend(f"{suite}-{config}-{policy}-{seed}" for config, policy in arms)
                seen.add(seed)
    return sorted(names)


def _blob(ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT)


def load_inputs(config: str, seed: int, directory: Path) -> tuple[BoundCompatPack, EffectiveConfig]:
    registration = REGISTRY[config]
    map_source = REGISTRY["production"] if registration.substitution else registration
    raw = _blob(map_source.ref, map_source.path)
    data = tomllib.loads(raw.decode("utf-8"))
    layout = PurePosixPath(map_source.path).parent / data["map"]["layout_file"]
    layout = PurePosixPath(posixpath.normpath(layout.as_posix()))
    config_path = directory / f"{config}.toml"
    map_path = directory / f"{registration.map_digest}.map"
    config_raw = (
        (FIXTURES / "configs" / f"{config}.toml").read_bytes() if registration.substitution else raw
    )
    store_once(config_path, config_raw)
    store_once(map_path, _blob(map_source.ref, layout.as_posix()))
    bound = load_compat_pack(
        config_path, PACK, load_vocabulary(VOCABULARY), map_path=map_path, seed=seed
    )
    return bound, EffectiveConfig.model_validate(bound.config)


class DigestJournal(PacketJournal):
    """Track acknowledgement bindings and packet digests with bounded disk usage."""

    def __init__(self, directory: Path, run_id: str) -> None:
        super().__init__(directory, run_id)
        self._digests: dict[int, str] = {}

    def ingest(self, world: World) -> dict[str, str]:
        data, acknowledgements = self._pending(world)
        digest = sha256(data).hexdigest()
        if self._digests.setdefault(world.tick, digest) != digest:
            raise ValueError(f"packet re-ingestion differs at boundary {world.tick}")
        return acknowledgements

    def receipt(self) -> str:
        return sha256(json.dumps(self._digests, sort_keys=True).encode("ascii")).hexdigest()


def setup_world(bound: BoundCompatPack, config: EffectiveConfig) -> World:
    """Translate pinned config data into a fresh world owned by the v2 engine."""
    perception = config.perception
    return initialize(
        bound.pack,
        WorldSetup(
            world_id=config.meta.world_id,
            run_id=config.meta.run_id,
            seed=config.meta.seed,
            config_hash=bound.manifest.effective_config_sha256,
            map_hash=bound.manifest.map_sha256,
            static_map_ref=config.map.layout_file,
            pack_ids=bound.pack.pack_ids,
            terrain=MapConfig(
                rows=tuple(
                    tuple(TERRAIN_BY_SYMBOL[symbol] for symbol in row) for row in bound.map_rows
                ),
                step_costs={key: getattr(config.map, f"step_cost_{key}") for key in WALKABLE},
                walk_budget=config.map.walk_cost_budget_per_tick,
                opaque_terrains=frozenset(("woods", "fruit_tree", "rock")),
            ),
            clock=ClockConfig(
                tick_minutes=config.time.tick_minutes,
                start_minute=config.time.start_hour * 60,
                day_start_minute=config.time.day_start_hour * 60,
                day_end_minute=config.time.day_end_hour * 60,
            ),
            senses=SensesConfig(
                day_radius=perception.day_radius_tiles,
                night_radius=perception.night_radius_tiles,
                hearing_radius=perception.hearing_radius_tiles,
                cue_detail_radius=perception.cue_detail_radius_tiles,
                visible_weakness_below=perception.visible_weakness_health_below,
                visible_dehydration_below=perception.visible_dehydration_hydration_below,
                visible_fatigue_below=perception.visible_fatigue_stamina_below,
            ),
            dialogue=DialogueConfig(
                max_turns=config.social.max_dialogue_turns,
                gap_ticks=config.social.dialogue_gap_ticks,
                cooldown_ticks=config.social.dialogue_cooldown_ticks,
            ),
            residents=tuple(
                ResidentSetup(id=row.id, position=Coord(x=row.position[0], y=row.position[1]))
                for row in config.residents
            ),
            cues=tuple(
                CueSetup(
                    id=cue.id,
                    kind=cue.kind,
                    position=Coord(x=cue.position[0], y=cue.position[1]),
                    visible_description=cue.visible_description,
                    near_description=cue.near_description,
                    direction=cue.direction,
                )
                for cue in config.world.cues
            ),
        ),
    )


def run_case(path: Path, evidence: Path, through: int) -> dict[str, object]:
    oracle = legacy_replies(read_projection(path))
    expected_name = f"{oracle.config}-{oracle.policy}-{oracle.source.seed}"
    if (
        path.name != f"{oracle.case}.json.gz"
        or not oracle.case.endswith(f"-{expected_name}")
        or (oracle.frames[0].tick, oracle.frames[-1].tick) != (0, HORIZON)
    ):
        raise ValueError(f"{path}: projection is not bound to its registered matrix case")
    bound, config = load_inputs(
        oracle.config, oracle.source.seed, evidence / "inputs" / oracle.case
    )
    witness = {
        "case": oracle.case,
        "projection_sha256": sha256(path.read_bytes()).hexdigest(),
        "source": oracle.source.model_dump(),
        "config": oracle.config,
        "policy": oracle.policy,
        "rule_library_hash": bound.pack.rule_library_hash,
    }
    for field in ("config_blob_sha256", "effective_config_sha256", "map_blob_sha256", "map_sha256"):
        if getattr(bound.manifest, field) != getattr(oracle.source, field):
            return {
                **witness,
                "difference": {
                    "field": field,
                    "tick": None,
                    "expected": getattr(oracle.source, field),
                    "actual": getattr(bound.manifest, field),
                },
            }
    world = setup_world(bound, config)
    bridge = LegacyBridge(bound)
    extractor = V2Extractor(bridge)
    policy_config = PolicyConfig(
        policy_id="rule-based-v0",
        seed=config.meta.seed,
        max_plan_actions=config.agents.max_plan_actions,
        map_width=config.map.width,
        map_height=config.map.height,
        script_sha256=None,
        source_trace_sha256=None,
        rule_params=POLICIES[oracle.policy],
    )
    hosts: dict[str, PolicyHost] = {
        row.id: ProjectionHost(
            policy_config,
            OwnProfile(profile_id=row.profile_id, initial_goal=row.initial_goal),
            config.actions.sleep_ticks,
            extractor=extractor,
        )
        for row in config.residents
    }
    journal = DigestJournal(evidence, world.run_id)
    session = PolicySession(world, hosts, journal)
    extractor.frames.append(snapshot(world, config.canteen.unique_item_id))
    compare_through = min(through + 1, HORIZON)
    for expected in oracle.frames[:compare_through]:
        opening = world.state
        result = session.advance()
        assert result is not None
        submissions = session.runner.manifest.boundaries[-1].submissions
        hits = declared_exceptions(opening, world.pack, submissions)
        if hits:
            return {
                **witness,
                "difference": {
                    "tick": expected.tick,
                    "field": "declared_exceptions",
                    "expected": [],
                    "actual": [asdict(hit) for hit in hits],
                },
                "packet_receipt_sha256": journal.receipt(),
            }
        extractor.append(snapshot(world, config.canteen.unique_item_id), result)
        difference = first_difference(expected, extractor.frames[-2], links=False)
        if difference is not None:
            return {**witness, "difference": difference, "packet_receipt_sha256": journal.receipt()}
    frames = extractor.finish()
    if through < HORIZON:
        return {
            **witness,
            "difference": None,
            "matched_boundaries": compare_through,
            "checked_through": through,
            "packet_receipt_sha256": journal.receipt(),
        }
    for expected, actual in zip(oracle.frames, frames, strict=True):
        difference = first_difference(expected, actual)
        if difference is not None:
            return {**witness, "difference": difference, "packet_receipt_sha256": journal.receipt()}
    projected = Projection(
        case=oracle.case,
        config=oracle.config,
        policy=oracle.policy,
        source=oracle.source,
        frames=frames,
    )
    return {
        **witness,
        "difference": None,
        "matched_boundaries": len(frames),
        "v2_projection_sha256": sha256(canonical_bytes(projected)).hexdigest(),
        "packet_receipt_sha256": journal.receipt(),
        "declared_exceptions": dict.fromkeys(EXCEPTION_NAMES, 0),
    }


def run_recorded(path: Path, evidence: Path, through: int) -> dict[str, object]:
    try:
        result = run_case(path, evidence, through)
    except PersistenceError as error:
        raise RuntimeError(f"{path.name}: {error}") from error
    if result["difference"] is not None:
        print(f"{result['case']}: {result['difference']}", file=sys.stderr, flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True).add_parser("equivalence")
    selection = command.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--case", action="append")
    command.add_argument("--evidence", type=Path, default=ROOT / "runs/m12-equivalence")
    command.add_argument("--output", type=Path)
    command.add_argument("--jobs", type=int, default=1, choices=range(1, 33), metavar="1..32")
    command.add_argument(
        "--through",
        type=int,
        default=HORIZON,
        metavar="TICK",
        help="compare a diagnostic prefix (default: full 1008 ticks)",
    )
    args = parser.parse_args()
    matrix = FIXTURES / "matrix"
    registered = matrix_names()
    if not 0 <= args.through <= HORIZON:
        parser.error(f"--through must be between 0 and {HORIZON}")
    names = registered if args.all else sorted(set(args.case))
    if unknown := sorted(set(names).difference(registered)):
        parser.error(f"unregistered matrix case(s): {', '.join(unknown)}")
    cases = [matrix / f"{name}.json.gz" for name in names]
    start = perf_counter()
    work = partial(run_recorded, evidence=args.evidence, through=args.through)
    if args.jobs == 1:
        results = list(map(work, cases))
    else:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(work, cases))
    report = json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(report, end="")
    else:
        store_once(args.output, report.encode("utf-8"))
    print(
        f"Compared {len(results)} case(s) in {perf_counter() - start:.3f} seconds.", file=sys.stderr
    )
    return int(any(case["difference"] is not None for case in results))


if __name__ == "__main__":
    raise SystemExit(main())
