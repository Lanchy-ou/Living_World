"""Load registered v1 TOML and bind it to the v2 compatibility pack."""

import tomllib
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TypedDict, cast

from living_island.world.v2.rules import ContentError, Pack, Vocabulary, load_pack
from living_island.world.v2.rules.loader import bind, read_toml
from living_island.world.v2.rules.schema import Table, array, content_hash, fields, table

from .registry import check_digest, map_pin

NEEDS = ("satiety", "hydration", "stamina", "health")
LEGACY_CODES = frozenset(
    {
        "ALREADY_FULL",
        "EXHAUSTED",
        "INVENTORY_FULL",
        "NO_ITEM",
        "NO_NEED",
        "NO_WATER",
        "OUT_OF_REACH",
        "RESOURCE_TAKEN",
    }
)


class ConfigMeta(TypedDict):
    seed: int
    world_id: str
    run_id: str
    schema_version: str


class CanteenConfig(TypedDict):
    unique_item_id: str
    capacity_servings: int
    initial_servings: int
    initial_owner_id: str


class TreeConfig(TypedDict):
    id: str
    position: list[int]
    regrow_phase_offset_ticks: int


class ConfigWorld(TypedDict):
    fruit_trees: list[TreeConfig]
    initial_cave: list[int]
    spring: list[int]
    cues: list[Table]


class CompatConfig(TypedDict):
    """The sections consumed during binding, with the remaining TOML preserved."""

    meta: ConfigMeta
    map: Table
    time: dict[str, int]
    needs: dict[str, int]
    fruit: dict[str, int]
    inventory: dict[str, int]
    canteen: CanteenConfig
    actions: dict[str, int]
    perception: Table
    social: dict[str, int]
    agents: dict[str, int]
    world: ConfigWorld
    residents: list[Table]


@dataclass(frozen=True)
class CompatManifest:
    config_blob_sha256: str
    effective_config_sha256: str
    map_blob_sha256: str
    map_sha256: str
    seed: int


@dataclass(frozen=True)
class BoundCompatPack:
    pack: Pack
    config: CompatConfig
    map_rows: tuple[str, ...]
    codes: dict[str, dict[str, str]]
    manifest: CompatManifest


def _p2_seeds() -> frozenset[int]:
    # P2 experiments §2 generates development first and skips collisions.
    seen: set[int] = set()
    for name in ("development", "acceptance"):
        target = len(seen) + 20
        index = 0
        while len(seen) < target:
            digest = sha256(f"living-island/p2/{name}/{index}".encode()).digest()
            seen.add(1 + int.from_bytes(digest[:4], "big") % (2**32 - 1))
            index += 1
    return frozenset(seen)


P2_SEEDS = _p2_seeds()


def _placements(config: CompatConfig, regrowth: bool) -> list[Table]:
    fruit = config["fruit"]
    trees: list[Table] = [
        {
            "id": tree["id"],
            "archetype": "fruit_tree",
            "at": {"tile": tree["position"]},
            "state": {"store": {"count": fruit["initial_stock_per_tree"]}},
            "phase_offset": {"compat_regrow_fruit": tree["regrow_phase_offset_ticks"]}
            if regrowth
            else {},
        }
        for tree in config["world"]["fruit_trees"]
    ]
    canteen = config["canteen"]
    canteen_id = canteen["unique_item_id"]
    water_id = f"{canteen_id}_water"
    return [
        *trees,
        {
            "id": canteen_id,
            "archetype": "canteen",
            "at": {"holder": canteen["initial_owner_id"]},
            "owner_id": canteen["initial_owner_id"],
            "contents": [water_id],
        },
        {
            "id": water_id,
            "archetype": "water",
            "at": {"holder": canteen_id},
            "quantity": canteen["initial_servings"],
        },
    ]


def _completion_rate(magnitude: int, work_ticks: int) -> int:
    return (magnitude + work_ticks - 1) // work_ticks


def _bindings(config: CompatConfig, directory: Path) -> Table:
    needs, actions, fruit = config["needs"], config["actions"], config["fruit"]
    canteen = config["canteen"]["capacity_servings"]
    slots = config["inventory"]["slot_capacity"]
    regrowth = fruit["regrow_per_cycle"]
    sleep_gain = needs["stamina_sleep_gain_per_tick"] + needs["stamina_sleep_cave_bonus_per_tick"]
    max_live_units = len(config["world"]["fruit_trees"]) + 1 + canteen
    max_live_units += len(config["residents"]) * (slots + 1)
    gain_bounds = {
        "satiety": _completion_rate(needs["satiety_gain_per_fruit"], actions["eat_ticks"]),
        "hydration": _completion_rate(needs["hydration_gain_per_serving"], actions["drink_ticks"]),
        "stamina": max(needs["stamina_rest_gain_per_tick"], sleep_gain),
        "health": 0,
    }
    loss_bounds = {
        "stamina": _completion_rate(
            needs["stamina_gather_cost_per_completion"], actions["gather_ticks"]
        )
    }
    sources = {"spring_water": {"archetype": "water", "max_per_application": canteen}}
    if regrowth:
        sources["fruit_regrowth"] = {"archetype": "fruit", "max_per_application": regrowth}
    values: Table = {
        **needs,
        **actions,
        **fruit,
        **config["agents"],
        **{f"{need}_gain_bound": gain_bounds[need] for need in NEEDS},
        **{f"{need}_loss_bound": loss_bounds.get(need, 0) for need in NEEDS},
        "slot_capacity": slots,
        "capacity_servings": canteen,
        "need_band_cutoffs": config["perception"]["need_band_cutoffs"],
        "cave_stamina_gain": sleep_gain,
        "gather_stamina_delta": -needs["stamina_gather_cost_per_completion"],
        "max_entity_units_world": max(4000, max_live_units),
        "regrowth_trigger": f"every:{fruit['regrow_ticks']}",
        "sources": sources,
        "instances": _placements(config, bool(regrowth)),
    }
    rule_files = ["rule-templates.toml"]
    if regrowth:
        rule_files.append("rule-regrowth.toml")
    active: list[Table] = []
    for filename in rule_files:
        template = fields(read_toml(directory / filename), filename, "rule")
        rules = array(template["rule"], f"{filename}:rule")
        active.extend(bind(rules, values, filename))
    values["rules"] = active
    return values


def _load_codes(pack: Pack) -> dict[str, dict[str, str]]:
    path = "compat-codes.toml"
    if "compat_codes" not in pack.data:
        raise ContentError("BAD_SHAPE", path, "missing compatibility code table")
    raw: Table = pack.data["compat_codes"]
    proven = set(pack.report.unreachable_checks)
    codes: dict[str, dict[str, str]] = {}
    for rule_id, rule in pack.rules.items():
        row = rule.data
        if not row["trigger"].startswith("verb:"):
            continue
        checks = set(pack.report.slot_coverage[rule_id])
        checks.update(condition["id"] for condition in row["conditions"])
        # RR §3.3 reserves this check for branches with physical debits or placements.
        if (
            row["inputs"]
            or row["outputs"]
            or any(e["op"] in ("move", "consume") for e in row["effects"])
        ):
            checks.add("world_limit")
        if not checks:
            continue
        entries = table(raw.get(rule_id, {}), f"{path}:{rule_id}")
        if entries.keys() != checks:
            missing, extra = sorted(checks - entries.keys()), sorted(entries.keys() - checks)
            raise ContentError(
                "BAD_SHAPE", f"{path}:{rule_id}", f"missing {missing}; extra {extra}"
            )
        for check, code in entries.items():
            if code == "unreachable" and (rule_id, check) in proven:
                continue
            if code == "defect" and check == "world_limit":
                continue
            if isinstance(code, str) and code in LEGACY_CODES:
                continue
            raise ContentError("BAD_SHAPE", f"{path}:{rule_id}.{check}", "invalid disposition")
        codes[rule_id] = entries
    if raw.keys() != codes.keys():
        extra = sorted(raw.keys() - codes.keys())
        raise ContentError("BAD_SHAPE", path, f"unexpected rules {extra}")
    return codes


def load_compat_pack(
    config_path: Path,
    directory: Path,
    vocabulary: Vocabulary,
    *,
    map_path: Path | None = None,
    seed: int | None = None,
) -> BoundCompatPack:
    """Read an exact CR-011 config/map pair and load its run-specific pack.

    Supply the pinned map explicitly when loading a relocated fixture TOML.
    A P2 override changes the effective identity without changing the source pin.
    """
    raw = config_path.read_bytes()
    config_digest = sha256(raw).hexdigest()
    expected_map = map_pin(config_digest)
    # Admission pins the complete TOML and map. The admitted schemas are known.
    config = cast(CompatConfig, tomllib.loads(raw.decode("utf-8")))
    layout = map_path if map_path is not None else config_path.parent / config["map"]["layout_file"]
    map_raw = layout.read_bytes()
    check_digest(map_raw, expected_map, "map blob")
    if seed is not None:
        if seed != config["meta"]["seed"] and seed not in P2_SEEDS:
            raise ValueError(f"unregistered P2 seed override: {seed}")
        config["meta"]["seed"] = seed
    pack = load_pack(directory, vocabulary, bindings=_bindings(config, directory))
    codes = _load_codes(pack)
    manifest = CompatManifest(
        config_blob_sha256=config_digest,
        effective_config_sha256=content_hash(config),
        map_blob_sha256=expected_map,
        map_sha256=expected_map,  # the pinned maps are already canonical LF-terminated rows
        seed=config["meta"]["seed"],
    )
    return BoundCompatPack(
        pack, config, tuple(map_raw.decode("utf-8").splitlines()), codes, manifest
    )
