"""Ground truth management for benchmark evaluation.

Two independent ground truth files:
- bib_ground_truth.json: bib bounding boxes, numbers, and photo-level bib tags.
- face_ground_truth.json: face bounding boxes, scope tags, identity labels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Re-export shared types from pipeline.types (canonical location).
# All existing importers continue to work via these re-exports.
from pipeline.types import (  # noqa: F401
    BibLabel,
    FaceLabel,
    BibFaceLink,
    BIB_BOX_SCOPES,
    _BIB_BOX_UNSCORED,
    FACE_SCOPE_TAGS,
    _FACE_SCOPE_COMPAT,
    FACE_BOX_TAGS,
)

# Schema version (bumped from 2 to 3 for the bib/face split)
SCHEMA_VERSION = 3

# Photo-level bib condition descriptors
BIB_PHOTO_TAGS = frozenset({
    "obscured_bib",
    "dark_bib",
    "no_bib",
    "blurry_bib",
    "partial_bib",
    "light_bib",
    "other_banners",
})

# Photo-level face condition descriptors (scene-level only)
FACE_PHOTO_TAGS = frozenset({
    "no_faces",
    "light_faces",
})

# Compat set: old per-photo tags that now live on boxes, kept for loading legacy data
_FACE_PHOTO_TAGS_COMPAT = FACE_PHOTO_TAGS | frozenset({
    "face_no_faces",  # old name for no_faces
    "face_tiny_faces",
    "face_blurry_faces",
    "face_occluded_faces",
    "face_profile",
})

# Allowed split values (shared between bib and face)
ALLOWED_SPLITS = frozenset({"iteration", "full"})
Split = Literal["iteration", "full"]

# Backward-compat aliases used by web_app.py templates
ALLOWED_TAGS = BIB_PHOTO_TAGS
ALLOWED_FACE_TAGS = FACE_PHOTO_TAGS  # web_app.py uses this for photo-level checkboxes


class BibPhotoLabel(BaseModel):
    """Ground truth bib data for a single photo.

    Attributes:
        content_hash: SHA256 content hash (canonical photo identity).
        boxes: Bib bounding boxes with numbers and scopes.
        labeled: True once a human has reviewed this photo's bibs.
    """

    content_hash: str
    boxes: list[BibLabel] = Field(default_factory=list)
    labeled: bool = False

    model_config = ConfigDict(extra="ignore")

    @property
    def bib_numbers_int(self) -> list[int]:
        """Bib numbers as sorted, deduplicated ints.

        Skips unscored boxes (``not_bib``, ``bib_obscured``) and non-numeric
        numbers (e.g. ``62?``).
        """
        result: set[int] = set()
        for box in self.boxes:
            if box.scope in _BIB_BOX_UNSCORED:
                continue
            try:
                result.add(int(box.number))
            except ValueError:
                pass
        return sorted(result)

    # Backward-compat alias used by runner.compute_photo_result
    @property
    def bibs(self) -> list[int]:
        return self.bib_numbers_int


@dataclass
class BibGroundTruth:
    """Container for all bib ground truth labels."""

    version: int = SCHEMA_VERSION
    photos: dict[str, BibPhotoLabel] = field(default_factory=dict)

    def add_photo(self, label: BibPhotoLabel) -> None:
        self.photos[label.content_hash] = label

    def get_photo(self, content_hash: str) -> BibPhotoLabel | None:
        return self.photos.get(content_hash)

    def has_photo(self, content_hash: str) -> bool:
        return content_hash in self.photos

    def remove_photo(self, content_hash: str) -> bool:
        if content_hash in self.photos:
            del self.photos[content_hash]
            return True
        return False

    def get_unlabeled_hashes(self, all_hashes: set[str]) -> set[str]:
        return all_hashes - set(self.photos.keys())

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "photos": {
                h: label.model_dump(exclude={"content_hash"})
                for h, label in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> BibGroundTruth:
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, photo_data in data.get("photos", {}).items():
            gt.photos[content_hash] = BibPhotoLabel.model_validate(
                {"content_hash": content_hash, **photo_data}
            )
        return gt


class FacePhotoLabel(BaseModel):
    """Ground truth face data for a single photo.

    ``face_count`` is derived from the number of ``keep``-scoped boxes.
    """

    content_hash: str
    boxes: list[FaceLabel] = Field(default_factory=list)
    labeled: bool = False  # True once a human has explicitly saved face labels for this photo

    model_config = ConfigDict(extra="ignore")

    @property
    def face_count(self) -> int:
        return sum(1 for b in self.boxes if b.scope == "keep")


@dataclass
class FaceGroundTruth:
    """Container for all face ground truth labels."""

    version: int = SCHEMA_VERSION
    photos: dict[str, FacePhotoLabel] = field(default_factory=dict)

    def add_photo(self, label: FacePhotoLabel) -> None:
        self.photos[label.content_hash] = label

    def get_photo(self, content_hash: str) -> FacePhotoLabel | None:
        return self.photos.get(content_hash)

    def has_photo(self, content_hash: str) -> bool:
        return content_hash in self.photos

    def remove_photo(self, content_hash: str) -> bool:
        if content_hash in self.photos:
            del self.photos[content_hash]
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "photos": {
                h: label.model_dump(exclude={"content_hash"})
                for h, label in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> FaceGroundTruth:
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, photo_data in data.get("photos", {}).items():
            gt.photos[content_hash] = FacePhotoLabel.model_validate(
                {"content_hash": content_hash, **photo_data}
            )
        return gt


@dataclass
class LinkGroundTruth:
    """Container for all bib-face link ground truth associations."""

    version: int = SCHEMA_VERSION
    photos: dict[str, list[BibFaceLink]] = field(default_factory=dict)

    def get_links(self, content_hash: str) -> list[BibFaceLink]:
        return self.photos.get(content_hash, [])

    def set_links(self, content_hash: str, links: list[BibFaceLink]) -> None:
        self.photos[content_hash] = links

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "photos": {
                h: [lnk.to_pair() for lnk in links]
                for h, links in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> LinkGroundTruth:
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, pairs in data.get("photos", {}).items():
            gt.photos[content_hash] = [BibFaceLink.from_pair(p) for p in pairs]
        return gt


# =============================================================================
# File paths & load/save
# =============================================================================


def get_bib_ground_truth_path() -> Path:
    return Path(__file__).parent / "bib_ground_truth.json"


def get_face_ground_truth_path() -> Path:
    return Path(__file__).parent / "face_ground_truth.json"


def load_bib_ground_truth(path: Path | None = None) -> BibGroundTruth:
    if path is None:
        path = get_bib_ground_truth_path()
    if not path.exists():
        return BibGroundTruth()
    with open(path, "r") as f:
        return BibGroundTruth.from_dict(json.load(f))


def save_bib_ground_truth(gt: BibGroundTruth, path: Path | None = None) -> None:
    if path is None:
        path = get_bib_ground_truth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(gt.to_dict(), f, indent=2)


def load_face_ground_truth(path: Path | None = None) -> FaceGroundTruth:
    if path is None:
        path = get_face_ground_truth_path()
    if not path.exists():
        return FaceGroundTruth()
    with open(path, "r") as f:
        return FaceGroundTruth.from_dict(json.load(f))


def save_face_ground_truth(
    gt: FaceGroundTruth, path: Path | None = None
) -> None:
    if path is None:
        path = get_face_ground_truth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(gt.to_dict(), f, indent=2)


def get_link_ground_truth_path() -> Path:
    return Path(__file__).parent / "bib_face_links.json"


def load_link_ground_truth(path: Path | None = None) -> LinkGroundTruth:
    if path is None:
        path = get_link_ground_truth_path()
    if not path.exists():
        return LinkGroundTruth()
    with open(path, "r") as f:
        return LinkGroundTruth.from_dict(json.load(f))


def save_link_ground_truth(gt: LinkGroundTruth, path: Path | None = None) -> None:
    if path is None:
        path = get_link_ground_truth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(gt.to_dict(), f, indent=2)


def migrate_from_legacy(
    legacy_data: dict,
) -> tuple[BibGroundTruth, FaceGroundTruth]:
    """Convert a v2 ground_truth.json dict to the new split schema.

    Each legacy photo becomes one ``BibPhotoLabel`` and one
    ``FacePhotoLabel``.  Bib numbers become ``BibLabel`` entries with
    zero-area coordinates (``has_coords == False``).  ``face_count`` is
    dropped (now derived from keep-scoped face boxes).

    Returns:
        (BibGroundTruth, FaceGroundTruth) pair.
    """
    bib_gt = BibGroundTruth()
    face_gt = FaceGroundTruth()

    for content_hash, photo in legacy_data.get("photos", {}).items():
        # --- bib side ---
        bib_boxes: list[BibLabel] = []
        for bib_number in photo.get("bibs", []):
            bib_boxes.append(
                BibLabel(x=0, y=0, w=0, h=0, number=str(bib_number), scope="bib")
            )

        # Filter tags: only keep those that belong to BIB_PHOTO_TAGS
        bib_tags = [t for t in photo.get("tags", []) if t in BIB_PHOTO_TAGS]

        bib_gt.add_photo(BibPhotoLabel(
            content_hash=content_hash,
            boxes=bib_boxes,
            labeled=photo.get("bib_labeled", False),
        ))

        # --- face side ---
        face_gt.add_photo(FacePhotoLabel(
            content_hash=content_hash,
            boxes=[],  # No face boxes in legacy data
        ))

    return bib_gt, face_gt
