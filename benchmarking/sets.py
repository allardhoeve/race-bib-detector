"""Staging and frozen benchmark set management."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


FROZEN_DIR = Path(__file__).parent / "frozen"


class BenchmarkSnapshotMetadata(BaseModel):
    name: str
    created_at: str          # ISO 8601
    photo_count: int
    description: str = ""

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> BenchmarkSnapshotMetadata:
        return cls.model_validate(data)


@dataclass
class BenchmarkSnapshot:
    metadata: BenchmarkSnapshotMetadata
    hashes: list[str]         # content hashes in this set
    index: dict[str, str]     # content_hash → relative photo path

    @property
    def path(self) -> Path:
        return FROZEN_DIR / self.metadata.name

    def save(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.path / "index.json", "w") as f:
            json.dump({"hashes": self.hashes, "index": self.index}, f, indent=2)
        with open(self.path / "metadata.json", "w") as f:
            json.dump(self.metadata.to_dict(), f, indent=2)

    @classmethod
    def load(cls, name: str) -> BenchmarkSnapshot:
        path = FROZEN_DIR / name
        with open(path / "metadata.json") as f:
            metadata = BenchmarkSnapshotMetadata.from_dict(json.load(f))
        with open(path / "index.json") as f:
            data = json.load(f)
        return cls(metadata=metadata, hashes=data["hashes"], index=data["index"])


def list_snapshots() -> list[BenchmarkSnapshotMetadata]:
    """Return metadata for all frozen sets, sorted by created_at descending."""
    if not FROZEN_DIR.exists():
        return []
    result = []
    for d in FROZEN_DIR.iterdir():
        meta_path = d / "metadata.json"
        if meta_path.exists():
            with open(meta_path) as f:
                result.append(BenchmarkSnapshotMetadata.from_dict(json.load(f)))
    result.sort(key=lambda m: m.created_at, reverse=True)
    return result


def freeze(
    name: str,
    hashes: list[str],
    index: dict[str, str],
    description: str = "",
) -> BenchmarkSnapshot:
    """Create a new frozen snapshot. Raises ValueError if name already exists."""
    target = FROZEN_DIR / name
    if target.exists():
        raise ValueError(f"Snapshot already exists: {name!r}")

    # Stamp each photo's metadata with the frozen set name
    from benchmarking.photo_metadata import load_photo_metadata, save_photo_metadata, PhotoMetadata
    meta_store = load_photo_metadata()
    for h in hashes:
        meta = meta_store.get(h)
        if meta is None:
            meta = PhotoMetadata()
            meta_store.set(h, meta)
        meta.frozen = name
    save_photo_metadata(meta_store)

    metadata = BenchmarkSnapshotMetadata(
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        photo_count=len(hashes),
        description=description,
    )
    snapshot = BenchmarkSnapshot(metadata=metadata, hashes=hashes, index=index)
    snapshot.save()
    return snapshot
