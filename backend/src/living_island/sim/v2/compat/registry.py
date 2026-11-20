"""The CR-011 A source, map and fixture pins for compatibility loading."""

from dataclasses import dataclass
from hashlib import sha256

ISLAND_MAP = "007a113879e45ceea908306b00606d3c6bc9dc516632939fd13023563bff1a9c"
MECHANICS_MAP = "c7e92011064d90ead5645c6fa8f16d03f52941ba39a6dff0f04d4dde446f734c"


@dataclass(frozen=True)
class Registration:
    ref: str
    path: str
    digest: str
    map_digest: str = ISLAND_MAP
    substitution: tuple[bytes, bytes] | None = None


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
    "give-3": Registration(
        "7c13d78",
        "content/worlds/default.toml",
        "b980a2cb42b526991eab648f417dbcf097776d18ab1679d6c015b9c229246c74",
        substitution=(b"give_ticks = 1", b"give_ticks = 3"),
    ),
    "regrowth-2": Registration(
        "7c13d78",
        "content/worlds/default.toml",
        "32a8098c62cc7b17a42cbb8825e5860dd80c222ed006bba493c7aa7afedbb5e4",
        substitution=(b"regrow_per_cycle = 1", b"regrow_per_cycle = 2"),
    ),
    "regrowth-0": Registration(
        "7c13d78",
        "content/worlds/default.toml",
        "92c32604733be96c1894045ab24960eb550cc27df4388e389654e99967459ecf",
        substitution=(b"regrow_per_cycle = 1", b"regrow_per_cycle = 0"),
    ),
    "gather-1": Registration(
        "7c13d78",
        "content/worlds/default.toml",
        "569cf836eaee207dce3df9efc55479cb823edfe3919392621b7c7e845601be43",
        substitution=(b"gather_ticks = 2", b"gather_ticks = 1"),
    ),
}


def check_digest(raw: bytes, expected: str, label: str) -> None:
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"{label} SHA-256 differs from CR-011")


def map_pin(config_digest: str) -> str:
    for entry in REGISTRY.values():
        if entry.digest == config_digest:
            return entry.map_digest
    raise ValueError(f"unregistered v1 config blob SHA-256: {config_digest}")


def materialize_fixture(production: bytes, name: str) -> bytes:
    """Apply a single registered byte substitution and verify the resulting pin."""
    entry = REGISTRY.get(name)
    if entry is None or entry.substitution is None:
        raise ValueError(f"unregistered v1 fixture: {name}")
    before, after = entry.substitution
    check_digest(production, REGISTRY["production"].digest, "production config blob")
    result = production.replace(before, after)
    check_digest(result, entry.digest, f"{name} config blob")
    return result
