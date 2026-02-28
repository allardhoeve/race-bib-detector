"""Photo-level metadata — paths, split, bib/face tags.

Consolidates photo-level data that was previously scattered across
``photo_index.json``, ``bib_ground_truth.json``, and
``face_ground_truth.json`` into a single ``photo_metadata.json`` file.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from .ground_truth import ALLOWED_SPLITS, BIB_PHOTO_TAGS, FACE_PHOTO_TAGS, _FACE_PHOTO_TAGS_COMPAT


class PhotoMetadata(BaseModel):
    """Photo-level metadata for a single photo.

    Attributes:
        paths: Relative file paths from the photos/ directory.
        split: Evaluation split ("iteration", "full", or "" for unassigned).
        bib_tags: Photo-level bib condition descriptors.
        face_tags: Photo-level face condition descriptors.
    """

    paths: list[str] = Field(default_factory=list)
    split: str = ""
    bib_tags: list[str] = Field(default_factory=list)
    face_tags: list[str] = Field(default_factory=list)
    frozen: str | None = None

    @field_validator("split")
    @classmethod
    def _validate_split(cls, v: str) -> str:
        if v and v not in ALLOWED_SPLITS:
            raise ValueError(f"Invalid split: {v!r}")
        return v

    @field_validator("bib_tags")
    @classmethod
    def _validate_bib_tags(cls, v: list[str]) -> list[str]:
        invalid = set(v) - BIB_PHOTO_TAGS
        if invalid:
            raise ValueError(f"Invalid bib photo tags: {invalid}")
        return v

    @field_validator("face_tags", mode="before")
    @classmethod
    def _validate_face_tags(cls, v: list[str]) -> list[str]:
        # Migrate legacy face tag name
        v = ["no_faces" if t == "face_no_faces" else t for t in v]
        invalid = set(v) - _FACE_PHOTO_TAGS_COMPAT
        if invalid:
            raise ValueError(f"Invalid face photo tags: {invalid}")
        return v


class PhotoMetadataStore(BaseModel):
    """Container for all photo metadata entries.

    Serialised as ``photo_metadata.json`` with structure::

        {"version": 1, "photos": {"<hash>": {paths, split, bib_tags, face_tags}}}
    """

    version: int = 1
    photos: dict[str, PhotoMetadata] = Field(default_factory=dict)

    def get(self, content_hash: str) -> PhotoMetadata | None:
        return self.photos.get(content_hash)

    def set(self, content_hash: str, meta: PhotoMetadata) -> None:
        self.photos[content_hash] = meta

    def is_frozen(self, content_hash: str) -> str | None:
        """Return frozen set name if frozen, else None."""
        meta = self.photos.get(content_hash)
        if meta:
            return meta.frozen
        return None

    def frozen_hashes(self) -> dict[str, str]:
        """Return {hash: set_name} for all frozen photos."""
        return {h: m.frozen for h, m in self.photos.items() if m.frozen}

    def get_hashes_by_split(self, split: str) -> list[str]:
        """Return hashes for an evaluation split.

        ``"full"`` returns ALL hashes; ``"iteration"`` returns only those
        with ``split == "iteration"`` — same semantics as the old
        ``BibGroundTruth.get_by_split()``.
        """
        if split == "full":
            return list(self.photos.keys())
        return [h for h, m in self.photos.items() if m.split == split]


# =============================================================================
# File paths & load/save
# =============================================================================


def get_photo_metadata_path() -> Path:
    return Path(__file__).parent / "photo_metadata.json"


def load_photo_metadata(path: Path | None = None) -> PhotoMetadataStore:
    if path is None:
        path = get_photo_metadata_path()
    if not path.exists():
        return PhotoMetadataStore()
    with open(path, "r") as f:
        data = json.load(f)
    store = PhotoMetadataStore(version=data.get("version", 1))
    for content_hash, meta_data in data.get("photos", {}).items():
        store.photos[content_hash] = PhotoMetadata.model_validate(meta_data)
    return store


def save_photo_metadata(store: PhotoMetadataStore, path: Path | None = None) -> None:
    if path is None:
        path = get_photo_metadata_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": store.version,
        "photos": {
            h: meta.model_dump() for h, meta in store.photos.items()
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
