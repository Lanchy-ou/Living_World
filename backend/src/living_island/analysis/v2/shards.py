"""Content-address verification and bounded, numbered inspection files."""

from base64 import b64decode, b64encode
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from living_island.analysis.canon import canonical_bytes_of_data, sha256_hex
from living_island.contract.inspection_v2 import (
    FilePart,
    InspectionIndex,
    Record,
    RevisionRef,
    Revisions,
    Shard,
    ShardRef,
)

SHARD_LIMIT = 8 << 20
INDEX_LIMIT = 32 << 20
_SHARD = TypeAdapter(Shard)


def encoded(value: object) -> bytes:
    return canonical_bytes_of_data(value)


def basename(family: str, identity: str) -> str:
    return sha256_hex(encoded([family, identity]))


def write_shard(directory: Path, identity: str, value: Shard) -> ShardRef:
    raw = encoded(value.model_dump(mode="json", by_alias=True))
    family = value.family
    name = basename(family, identity)
    # A split part is a canonical JSON string containing one base64 byte slice.
    # Split bytes, so a single string or record larger than the limit also fits.
    chunk = (SHARD_LIMIT - 2) // 4 * 3
    blocks = (
        (raw,)
        if len(raw) <= SHARD_LIMIT
        else (b'"' + b64encode(raw[i : i + chunk]) + b'"' for i in range(0, len(raw), chunk))
    )
    parts = []
    for n, block in enumerate(blocks, 1):
        path = directory / f"{name}.{n}.json"
        with path.open("xb") as stream:
            stream.write(block)
        parts.append(FilePart(name=path.name, sha256=sha256_hex(block), size=len(block)))
    return ShardRef(id=identity, family=family, parts=parts, sha256=sha256_hex(raw))


def read_index(directory: Path) -> InspectionIndex:
    path = directory / "index.json"
    if path.stat().st_size > INDEX_LIMIT:
        raise ValueError("inspection index exceeds 32 MiB")
    raw = path.read_bytes()
    index = InspectionIndex.model_validate_json(raw)
    if encoded(index.model_dump(mode="json")) != raw:
        raise ValueError("expected canonical inspection index")
    return index


def read_shard(directory: Path, ref: ShardRef) -> Shard:
    prefix = basename(ref.family, ref.id)
    raw = bytearray()
    for n, part in enumerate(ref.parts, 1):
        if part.name != f"{prefix}.{n}.json":
            raise ValueError("incorrect numbered part filename")
        path = directory / part.name
        if path.stat().st_size != part.size:
            raise ValueError(f"{part.name}: size mismatch")
        block = path.read_bytes()
        if sha256_hex(block) != part.sha256:
            raise ValueError(f"{part.name}: hash mismatch")
        if len(ref.parts) > 1:
            block = b64decode(TypeAdapter(str).validate_json(block), validate=True)
        raw.extend(block)
    if sha256_hex(bytes(raw)) != ref.sha256:
        raise ValueError(f"{ref.id}: assembled hash mismatch")
    value = _SHARD.validate_json(raw, extra="forbid")
    if value.family != ref.family:
        raise ValueError(f"{ref.id}: wrong shard family")
    return value


@dataclass(frozen=True)
class InspectionArchive:
    """The wave-8 consumer entry point. Open the index once and resolve exact refs on demand."""

    directory: Path
    index: InspectionIndex

    @classmethod
    def open(cls, directory: Path) -> "InspectionArchive":
        return cls(directory, read_index(directory))

    def read(self, ref: ShardRef) -> Shard:
        return read_shard(self.directory, ref)

    def revision(self, resident_id: str, ref: RevisionRef) -> Record | None:
        identity = f"{resident_id}:{ref.store_version}"
        source = next((s for s in self.index.revisions if s.id == identity), None)
        if source is None:
            return None
        revisions = self.read(source)
        if not isinstance(revisions, Revisions):
            raise ValueError("index points to the wrong revision family")
        return next((r.record for r in revisions.records if r.ref == ref), None)
