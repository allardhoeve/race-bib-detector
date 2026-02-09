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

# Schema version (bumped from 2 to 3 for the bib/face split)
SCHEMA_VERSION = 3

# --- Tag sets ----------------------------------------------------------------

# Per-box bib label (what kind of bib detection is this?)
BIB_BOX_TAGS = frozenset({"bib", "not_bib", "bib_partial"})

# Per-box face scope (should this face be recognized?)
FACE_SCOPE_TAGS = frozenset({"keep", "ignore", "unknown"})

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

# Photo-level face condition descriptors
FACE_PHOTO_TAGS = frozenset({
    "face_no_faces",
    "face_tiny_faces",
    "face_occluded_faces",
    "face_blurry_faces",
    "face_profile",
    "light_faces",
})

# Allowed split values (shared between bib and face)
ALLOWED_SPLITS = frozenset({"iteration", "full"})
Split = Literal["iteration", "full"]

# Backward-compat aliases used by web_app.py templates
ALLOWED_TAGS = BIB_PHOTO_TAGS
ALLOWED_FACE_TAGS = FACE_PHOTO_TAGS


# =============================================================================
# Bib schema
# =============================================================================


@dataclass
class BibBox:
    """A single bib bounding box with number and label tag.

    Coordinates are in normalised [0, 1] image space.
    Legacy migrated boxes have x=y=w=h=0 (see ``has_coords``).
    """

    x: float
    y: float
    w: float
    h: float
    number: str
    tag: str = "bib"

    def __post_init__(self):
        if self.tag not in BIB_BOX_TAGS:
            raise ValueError(f"Invalid bib box tag: {self.tag!r}")

    @property
    def has_coords(self) -> bool:
        return self.w > 0 and self.h > 0

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "number": self.number,
            "tag": self.tag,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BibBox:
        return cls(
            x=data["x"],
            y=data["y"],
            w=data["w"],
            h=data["h"],
            number=data["number"],
            tag=data.get("tag", "bib"),
        )


@dataclass
class BibPhotoLabel:
    """Ground truth bib data for a single photo.

    Attributes:
        content_hash: SHA256 content hash (canonical photo identity).
        boxes: Bib bounding boxes with numbers and tags.
        tags: Photo-level condition descriptors (from ``BIB_PHOTO_TAGS``).
        split: Which evaluation split this photo belongs to.
        labeled: True once a human has reviewed this photo's bibs.
    """

    content_hash: str
    boxes: list[BibBox] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    split: Split = "full"
    labeled: bool = False

    def __post_init__(self):
        invalid = set(self.tags) - BIB_PHOTO_TAGS
        if invalid:
            raise ValueError(f"Invalid bib photo tags: {invalid}")
        if self.split not in ALLOWED_SPLITS:
            raise ValueError(f"Invalid split: {self.split!r}")

    @property
    def bib_numbers_int(self) -> list[int]:
        """Bib numbers as sorted, deduplicated ints.

        Skips ``not_bib`` boxes and non-numeric numbers (e.g. ``62?``).
        """
        result: set[int] = set()
        for box in self.boxes:
            if box.tag == "not_bib":
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

    def to_dict(self) -> dict:
        return {
            "boxes": [b.to_dict() for b in self.boxes],
            "tags": self.tags,
            "split": self.split,
            "labeled": self.labeled,
        }

    @classmethod
    def from_dict(cls, content_hash: str, data: dict) -> BibPhotoLabel:
        return cls(
            content_hash=content_hash,
            boxes=[BibBox.from_dict(b) for b in data.get("boxes", [])],
            tags=data.get("tags", []),
            split=data.get("split", "full"),
            labeled=data.get("labeled", False),
        )


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

    def get_by_split(self, split: Split) -> list[BibPhotoLabel]:
        """Get photos for an evaluation split.

        ``"full"`` returns ALL photos; ``"iteration"`` returns only those
        explicitly marked as iteration.
        """
        if split == "full":
            return list(self.photos.values())
        return [p for p in self.photos.values() if p.split == split]

    def get_unlabeled_hashes(self, all_hashes: set[str]) -> set[str]:
        return all_hashes - set(self.photos.keys())

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "photos": {
                h: label.to_dict() for h, label in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> BibGroundTruth:
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, photo_data in data.get("photos", {}).items():
            gt.photos[content_hash] = BibPhotoLabel.from_dict(
                content_hash, photo_data
            )
        return gt


# =============================================================================
# Face schema
# =============================================================================


@dataclass
class FaceBox:
    """A single face bounding box with scope and optional identity.

    Coordinates are in normalised [0, 1] image space.
    """

    x: float
    y: float
    w: float
    h: float
    scope: str = "keep"
    identity: str | None = None

    def __post_init__(self):
        if self.scope not in FACE_SCOPE_TAGS:
            raise ValueError(f"Invalid face scope: {self.scope!r}")

    @property
    def has_coords(self) -> bool:
        return self.w > 0 and self.h > 0

    def to_dict(self) -> dict:
        d: dict = {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "scope": self.scope,
        }
        if self.identity is not None:
            d["identity"] = self.identity
        return d

    @classmethod
    def from_dict(cls, data: dict) -> FaceBox:
        return cls(
            x=data["x"],
            y=data["y"],
            w=data["w"],
            h=data["h"],
            scope=data.get("scope", "keep"),
            identity=data.get("identity"),
        )


@dataclass
class FacePhotoLabel:
    """Ground truth face data for a single photo.

    ``face_count`` is derived from the number of ``keep``-scoped boxes.
    """

    content_hash: str
    boxes: list[FaceBox] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        invalid = set(self.tags) - FACE_PHOTO_TAGS
        if invalid:
            raise ValueError(f"Invalid face photo tags: {invalid}")

    @property
    def face_count(self) -> int:
        return sum(1 for b in self.boxes if b.scope == "keep")

    def to_dict(self) -> dict:
        return {
            "boxes": [b.to_dict() for b in self.boxes],
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, content_hash: str, data: dict) -> FacePhotoLabel:
        return cls(
            content_hash=content_hash,
            boxes=[FaceBox.from_dict(b) for b in data.get("boxes", [])],
            tags=data.get("tags", []),
        )


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
                h: label.to_dict() for h, label in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> FaceGroundTruth:
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, photo_data in data.get("photos", {}).items():
            gt.photos[content_hash] = FacePhotoLabel.from_dict(
                content_hash, photo_data
            )
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


def migrate_from_legacy(
    legacy_data: dict,
) -> tuple[BibGroundTruth, FaceGroundTruth]:
    """Convert a v2 ground_truth.json dict to the new split schema.

    Each legacy photo becomes one ``BibPhotoLabel`` and one
    ``FacePhotoLabel``.  Bib numbers become ``BibBox`` entries with
    zero-area coordinates (``has_coords == False``).  ``face_count`` is
    dropped (now derived from keep-scoped face boxes).

    Returns:
        (BibGroundTruth, FaceGroundTruth) pair.
    """
    bib_gt = BibGroundTruth()
    face_gt = FaceGroundTruth()

    for content_hash, photo in legacy_data.get("photos", {}).items():
        # --- bib side ---
        bib_boxes: list[BibBox] = []
        for bib_number in photo.get("bibs", []):
            bib_boxes.append(
                BibBox(x=0, y=0, w=0, h=0, number=str(bib_number), tag="bib")
            )

        # Filter tags: only keep those that belong to BIB_PHOTO_TAGS
        bib_tags = [t for t in photo.get("tags", []) if t in BIB_PHOTO_TAGS]

        bib_gt.add_photo(BibPhotoLabel(
            content_hash=content_hash,
            boxes=bib_boxes,
            tags=bib_tags,
            split=photo.get("split", "full"),
            labeled=photo.get("bib_labeled", False),
        ))

        # --- face side ---
        # Collect face tags from legacy face_tags field, plus any
        # face-related tags that were in the old bib tags list
        face_tags = list(photo.get("face_tags", []))
        for t in photo.get("tags", []):
            if t in FACE_PHOTO_TAGS and t not in face_tags:
                face_tags.append(t)

        face_gt.add_photo(FacePhotoLabel(
            content_hash=content_hash,
            boxes=[],  # No face boxes in legacy data
            tags=face_tags,
        ))

    return bib_gt, face_gt
