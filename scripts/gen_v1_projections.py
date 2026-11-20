"""Build and check the M12 reference fixtures using the unchanged v1 runtime."""

from __future__ import annotations

import argparse
import os
import posixpath
import sys
import tomllib
from collections.abc import Generator
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from time import monotonic

from living_island.sim.equivalence.projection import (
    Projection,
    Source,
    Values,
    fixture_bytes,
)
from living_island.sim.equivalence.v1_extract import run_matrix_case
from living_island.world.content import WorldContent, build_world_content
from p2_experiments import (
    ACCEPTANCE_SEEDS,
    DEVELOPMENT_SEEDS,
    VARIANTS,
    blob_at,
    git,
    git_text,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "backend/tests/fixtures/v1_projection"
V1_SOURCE = "214228e7cdc0277a287f82ceae091158ac48daa6"
MATRIX_TICKS = 1008
BUDGET = 50 * 1024 * 1024
ISLAND_MAP = "007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c"
MECHANICS_MAP = "c7e92011064d90ead5645c6fa8f16d03f52941ba39a6dff0f04d4dde446f734c"


@dataclass(frozen=True)
class Registration:
    ref: str
    path: str
    digest: str
    map_digest: str = ISLAND_MAP


# Starter content §4.7, including the historical source of S2 orig.
REGISTRY = {
    "production": Registration(
        "7c13d78",
        "content/worlds/default.toml",
        "15c576c98be29ac1054e1154376508b6479e4fb57ebf1f07d241905f433dc128",
    ),
    "s2-orig": Registration(
        "04fde8b",
        "content/worlds/default.toml",
        "c5599943abbb18830e9fad19222fbf4e2b3658fd1ee22e7afc89da54470de7fd",
    ),
    "s1-orig": Registration(
        "e7ade04",
        "content/scenarios/s1-spring-visible/orig.toml",
        "843331a01ff8ff7e3bff9a40bf4dcf294df6c6a14aa5ee30d059393d6893c263",
    ),
    "s3-orig": Registration(
        "e7ade04",
        "content/scenarios/s3-regrow288/orig.toml",
        "111bb746979df3c96dbc3ec9b421d8b608db734f049cd0d5570c9844a123fc29",
    ),
    "s4-orig": Registration(
        "e7ade04",
        "content/scenarios/s4-decay120/orig.toml",
        "a858afdee231e1d88272ed21e47a6fd02b8251ce4e74aefee902e632fe64091d",
    ),
    "p1-default": Registration(
        "e7ade04",
        "backend/tests/fixtures/p1_default/default.toml",
        "c5599943abbb18830e9fad19222fbf4e2b3658fd1ee22e7afc89da54470de7fd",
    ),
    "mechanics": Registration(
        "e7ade04",
        "backend/tests/fixtures/replay/mechanics.toml",
        "b3107b77dbaa0d9ed45e2e13e87c2f7f2aab8e363b59f4ea85880d63989411b0",
        MECHANICS_MAP,
    ),
}
SUBSTITUTIONS = {
    "give-3": (
        b"give_ticks = 1",
        b"give_ticks = 3",
        "b980a2cb42b526991eab648f417dbcf097776d18ab1679d6c015b9c229246c74",
    ),
    "regrowth-2": (
        b"regrow_per_cycle = 1",
        b"regrow_per_cycle = 2",
        "32a8098c62cc7b17a42cbb8825e5860dd80c222ed006bba493c7aa7afedbb5e4",
    ),
    "regrowth-0": (
        b"regrow_per_cycle = 1",
        b"regrow_per_cycle = 0",
        "92c32604733be96c1894045ab24960eb550cc27df4388e389654e99967459ecf",
    ),
    "gather-1": (
        b"gather_ticks = 2",
        b"gather_ticks = 1",
        "569cf836eaee207dce3df9efc55479cb823edfe3919392621b7c7e845601be43",
    ),
}


def admit(name: str, raw: bytes, map_raw: bytes) -> None:
    if name in REGISTRY:
        entry = REGISTRY[name]
        digest, map_digest = entry.digest, entry.map_digest
    elif name in SUBSTITUTIONS:
        digest, map_digest = SUBSTITUTIONS[name][2], ISLAND_MAP
    else:
        raise ValueError(f"unlisted config: {name}")
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f"{name}: config blob SHA-256 differs from CR-011")
    if sha256(map_raw).hexdigest() != map_digest:
        raise ValueError(f"{name}: map blob SHA-256 differs from CR-011")


def load_registry(repo: Path) -> dict[str, tuple[bytes, bytes]]:
    bound = {}
    for name, entry in REGISTRY.items():
        raw = blob_at(repo, entry.ref, entry.path)
        if sha256(raw).hexdigest() != entry.digest:
            raise ValueError(f"{name}: config blob SHA-256 differs from CR-011")
        layout = tomllib.loads(raw.decode("utf-8"))["map"]["layout_file"]
        path = posixpath.normpath(posixpath.join(posixpath.dirname(entry.path), layout))
        map_raw = blob_at(repo, entry.ref, path)
        admit(name, raw, map_raw)
        bound[name] = raw, map_raw
    raw, map_raw = bound["production"]
    for name, (previous, replacement, _) in SUBSTITUTIONS.items():
        if raw.count(previous) != 1:
            raise ValueError(f"{name}: expected exactly one substitution site")
        changed = raw.replace(previous, replacement)
        admit(name, changed, map_raw)
        bound[name] = changed, map_raw
    return bound


def verify_v1_source(repo: Path) -> None:
    tag = git(repo, "rev-parse", "--verify", "--quiet", "refs/tags/v1-archive^{commit}")
    if tag.returncode == 0 and tag.stdout.decode().strip() != git_text(
        repo, "rev-parse", "HEAD"
    ):
        raise ValueError("regenerate fixtures from the v1-archive tag")
    if tag.returncode not in (0, 1):
        raise ValueError("could not resolve the v1-archive tag")
    changes = git(
        repo,
        "diff",
        "--name-only",
        "--no-renames",
        "--diff-filter=MDTUXB",
        V1_SOURCE,
        "--",
        "backend/src/living_island",
        "scripts/p2_experiments.py",
    )
    if changes.returncode != 0 or changes.stdout:
        raise ValueError("the working tree does not contain the pinned v1 source")


def refused_cases(bound: dict[str, tuple[bytes, bytes]]) -> list[Values]:
    raw, map_raw = bound["production"]
    evidence: list[Values] = []
    for key, before, after in (
        ("talk-ticks-2", b"talk_ticks = 1", b"talk_ticks = 2"),
        ("sleep-ticks-60", b"sleep_ticks = 48", b"sleep_ticks = 60"),
        ("fruit-few-max-3", b"fruit_few_max = 2", b"fruit_few_max = 3"),
        ("canteen-3-servings", b"capacity_servings = 2", b"capacity_servings = 3"),
        (
            "canteen-3999-servings",
            b"capacity_servings = 2",
            b"capacity_servings = 3999",
        ),
    ):
        if raw.count(before) != 1:
            raise ValueError(f"{key}: expected exactly one negative test site")
        invalid = raw.replace(before, after)
        try:
            admit("production", invalid, map_raw)
        except ValueError as error:
            evidence.append(
                {
                    "case": key,
                    "candidate_sha256": sha256(invalid).hexdigest(),
                    "error": str(error),
                }
            )
        else:
            raise ValueError(f"{key}: unregistered config was admitted")
    return evidence


def effective(
    name: str, raw: bytes, map_raw: bytes, seed: int
) -> tuple[WorldContent, Source]:
    admit(name, raw, map_raw)
    data = tomllib.loads(raw.decode("utf-8"))
    data["meta"]["seed"] = seed
    content = build_world_content(data, map_raw)
    source = Source(
        v1_source_commit=V1_SOURCE,
        config_blob_sha256=sha256(raw).hexdigest(),
        effective_config_sha256=content.config_hash,
        map_blob_sha256=sha256(map_raw).hexdigest(),
        map_sha256=content.map_hash,
        seed=seed,
    )
    return content, source


@dataclass(frozen=True)
class MatrixCase:
    suite: str
    config: str
    variant: str
    seed: int

    @property
    def name(self) -> str:
        return f"{self.suite}-{self.config}-{self.variant}-{self.seed}"


def matrix_cases() -> list[MatrixCase]:
    development = (
        ("s1-orig", "base"),
        ("s2-orig", "base"),
        ("s2-orig", "canteen-restricted"),
        ("s2-orig", "cue-ignored"),
        ("s3-orig", "base"),
        ("s4-orig", "base"),
        ("s4-orig", "canteen-restricted"),
    )
    return [
        MatrixCase("acceptance", "production", "base", seed)
        for seed in ACCEPTANCE_SEEDS
    ] + [
        MatrixCase("development", config, variant, seed)
        for config, variant in development
        for seed in DEVELOPMENT_SEEDS
    ]


def generate_matrix(job: tuple[MatrixCase, bytes, bytes]) -> tuple[str, bytes]:
    case, raw, map_raw = job
    content, source = effective(case.config, raw, map_raw, case.seed)
    params = VARIANTS[case.variant].rule_params
    assert params is not None
    projection = Projection(
        case=case.name,
        config=case.config,
        policy=case.variant,
        source=source,
        frames=run_matrix_case(content, MATRIX_TICKS, params),
    )
    return f"matrix/{case.name}.json.gz", fixture_bytes(projection)


def generate(
    bound: dict[str, tuple[bytes, bytes]], group: str, jobs: int
) -> Generator[tuple[str, bytes], None, None]:
    if group in ("all", "scripted"):
        from living_island.sim.equivalence.v1_extract import scripted_projections

        for name in SUBSTITUTIONS:
            yield f"configs/{name}.toml", bound[name][0]
        mechanics, _ = effective("mechanics", *bound["mechanics"], 20261108)
        for name, config, seed, run in scripted_projections(mechanics):
            content, source = effective(config, *bound[config], seed)
            frames, evidence = run(content)
            if name in ("wap23-ct15-refused-profiles", "ct17-canteen-2-servings"):
                prefix = (
                    ("talk-", "sleep-", "fruit-")
                    if name.startswith("wap23")
                    else ("canteen-",)
                )
                evidence[0]["registry_rejections"] = [
                    refusal
                    for refusal in refused_cases(bound)
                    if str(refusal["case"]).startswith(prefix)
                ]
            projection = Projection(
                case=name,
                config=config,
                policy="scripted-v1",
                source=source,
                frames=frames,
                scripted_evidence=evidence,
            )
            yield f"scripted/{name}.json.gz", fixture_bytes(projection)
    if group in ("all", "matrix"):
        work = [(case, *bound[case.config]) for case in matrix_cases()]
        if jobs == 1:
            yield from map(generate_matrix, work)
        else:
            with get_context("spawn").Pool(processes=jobs) as workers:
                yield from workers.imap_unordered(generate_matrix, work)


def owned_files(group: str) -> set[str]:
    directories = {
        "all": ("matrix", "scripted", "configs"),
        "matrix": ("matrix",),
        "scripted": ("scripted", "configs"),
    }
    return {
        path.relative_to(FIXTURES).as_posix()
        for directory in directories[group]
        for path in (FIXTURES / directory).glob("*")
        if path.is_file()
    }


def existing_size(excluded: set[str]) -> int:
    return sum(
        path.stat().st_size
        for path in FIXTURES.rglob("*")
        if path.is_file() and path.relative_to(FIXTURES).as_posix() not in excluded
    )


def over_budget(size: int) -> bool:
    if size <= BUDGET:
        return False
    print(
        f"Fixture budget exceeded: {size:,} bytes > {BUDGET:,}; owner decision required."
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="regenerate and compare fixture bytes"
    )
    parser.add_argument("--group", choices=("all", "matrix", "scripted"), default="all")
    parser.add_argument(
        "--jobs", type=int, default=min(16, os.process_cpu_count() or 1)
    )
    options = parser.parse_args()
    if not 1 <= options.jobs <= 61:
        parser.error("--jobs must be between 1 and 61")
    for directory in ("matrix", "scripted", "configs"):
        if not options.check:
            (FIXTURES / directory).mkdir(parents=True, exist_ok=True)
    output: dict[str, bytes] = {}
    started = monotonic()
    verify_v1_source(ROOT)
    old = owned_files(options.group)
    size = existing_size(old)
    with closing(
        generate(load_registry(ROOT), options.group, options.jobs)
    ) as generated:
        for path, payload in generated:
            if path in output:
                raise ValueError(f"duplicate fixture: {path}")
            size += len(payload)
            if over_budget(size):
                return 2
            output[path] = payload
            if len(output) % 10 == 0:
                elapsed = monotonic() - started
                print(f"{len(output)} fixtures generated in {elapsed:.1f}s", flush=True)
    old = owned_files(options.group)
    size = existing_size(old) + sum(map(len, output.values()))
    if over_budget(size):
        return 2
    stale = sorted(old - output.keys())
    if stale:
        print(f"Unexpected fixtures: {', '.join(stale)}", file=sys.stderr)
        return 1
    if options.check:
        mismatches = [
            name
            for name, payload in output.items()
            if name not in old or (FIXTURES / name).read_bytes() != payload
        ]
        if mismatches:
            print(
                f"Missing or changed fixtures: {', '.join(mismatches)}", file=sys.stderr
            )
            return 1
    else:
        for name, payload in sorted(output.items()):
            (FIXTURES / name).write_bytes(payload)
    print(f"{len(output)} fixtures, {size:,} total bytes, {monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
