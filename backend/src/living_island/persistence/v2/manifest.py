"""Identity of the protocol and content at the start of a run."""

from pathlib import Path
from typing import Annotated

from pydantic import Field

from living_island.world.v2.protocol import ProtocolModel, VersionedMessage
from living_island.world.v2.rules import Pack
from living_island.world.v2.rules.schema import canonical_json_bytes

from .._files import atomic_create

type Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PackPin(ProtocolModel):
    pack_id: str
    pack_hash: Digest


class RunManifest(VersionedMessage):
    run_id: str
    vocabulary_hash: Digest
    rule_library_hash: Digest
    packs: Annotated[tuple[PackPin, ...], Field(min_length=1)]

    @classmethod
    def capture(cls, run_id: str, pack: Pack) -> "RunManifest":
        """Pin the exact base-first composition of the loaded pack."""
        return cls(
            schema_version="wap/0.1",
            run_id=run_id,
            vocabulary_hash=pack.vocabulary_hash,
            rule_library_hash=pack.rule_library_hash,
            packs=(
                *(
                    PackPin(pack_id=layer.pack_id, pack_hash=layer.pack_hash)
                    for layer in pack.ancestors
                ),
                PackPin(pack_id=pack.pack_id, pack_hash=pack.pack_hash),
            ),
        )

    @property
    def pack_ids(self) -> tuple[str, ...]:
        return tuple(pin.pack_id for pin in self.packs)

    def check_content(self, pack: Pack) -> None:
        if self != self.capture(self.run_id, pack):
            raise ValueError("loaded content differs from the run manifest")


def write_manifest(path: Path, manifest: RunManifest) -> None:
    atomic_create(path, canonical_json_bytes(manifest.model_dump(mode="json")))


def read_manifest(path: Path) -> RunManifest:
    data = path.read_bytes()
    manifest = RunManifest.model_validate_json(data)
    if canonical_json_bytes(manifest.model_dump(mode="json")) != data:
        raise ValueError("expected canonical manifest bytes")
    return manifest
