"""Ground truth management for benchmark evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# Schema version for forward compatibility
SCHEMA_VERSION = 1

# Allowed tag values
ALLOWED_TAGS = frozenset({
    "obscured_bib",
    "dark_bib",
    "no_bib",
    "blurry_bib",
    "partial_bib",
    "light_bib",
    "light_faces",
    "other_banners",
})

# Allowed split values
ALLOWED_SPLITS = frozenset({"iteration", "full"})

# Type alias for split
Split = Literal["iteration", "full"]


@dataclass
class PhotoLabel:
    """Ground truth label for a single photo.

    Attributes:
        content_hash: SHA256 hash of file contents (canonical identity)
        bibs: List of bib numbers visible in the photo (no duplicates)
        tags: List of tags describing photo conditions
        split: Which split this photo belongs to
        photo_hash: Optional 8-char hash for integration with existing code
    """

    content_hash: str
    bibs: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    split: Split = "full"
    photo_hash: str | None = None

    def __post_init__(self):
        """Validate and normalize fields."""
        # Remove duplicate bibs and sort
        self.bibs = sorted(set(self.bibs))

        # Validate tags
        invalid_tags = set(self.tags) - ALLOWED_TAGS
        if invalid_tags:
            raise ValueError(f"Invalid tags: {invalid_tags}")

        # Validate split
        if self.split not in ALLOWED_SPLITS:
            raise ValueError(f"Invalid split: {self.split}")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "content_hash": self.content_hash,
            "bibs": self.bibs,
            "tags": self.tags,
            "split": self.split,
        }
        if self.photo_hash:
            result["photo_hash"] = self.photo_hash
        return result

    @classmethod
    def from_dict(cls, data: dict) -> PhotoLabel:
        """Create from dictionary."""
        return cls(
            content_hash=data["content_hash"],
            bibs=data.get("bibs", []),
            tags=data.get("tags", []),
            split=data.get("split", "full"),
            photo_hash=data.get("photo_hash"),
        )


@dataclass
class GroundTruth:
    """Container for all ground truth labels.

    Attributes:
        version: Schema version
        photos: Dict mapping content_hash to PhotoLabel
    """

    version: int = SCHEMA_VERSION
    photos: dict[str, PhotoLabel] = field(default_factory=dict)

    def add_photo(self, label: PhotoLabel) -> None:
        """Add or update a photo label."""
        self.photos[label.content_hash] = label

    def get_photo(self, content_hash: str) -> PhotoLabel | None:
        """Get a photo label by content hash."""
        return self.photos.get(content_hash)

    def has_photo(self, content_hash: str) -> bool:
        """Check if a photo exists in ground truth."""
        return content_hash in self.photos

    def remove_photo(self, content_hash: str) -> bool:
        """Remove a photo label. Returns True if it existed."""
        if content_hash in self.photos:
            del self.photos[content_hash]
            return True
        return False

    def get_by_split(self, split: Split) -> list[PhotoLabel]:
        """Get all photos in a specific split.

        The "full" split returns ALL photos (for comprehensive testing).
        The "iteration" split returns only photos marked as "iteration" (for quick feedback).
        """
        if split == "full":
            return list(self.photos.values())
        return [p for p in self.photos.values() if p.split == split]

    def get_by_tag(self, tag: str) -> list[PhotoLabel]:
        """Get all photos with a specific tag."""
        return [p for p in self.photos.values() if tag in p.tags]

    def get_unlabeled_hashes(self, all_hashes: set[str]) -> set[str]:
        """Get content hashes that don't have labels yet."""
        return all_hashes - set(self.photos.keys())

    def stats(self) -> dict:
        """Get summary statistics."""
        total = len(self.photos)
        by_split = {}
        for split in ALLOWED_SPLITS:
            by_split[split] = len(self.get_by_split(split))

        by_tag = {}
        for tag in ALLOWED_TAGS:
            by_tag[tag] = len(self.get_by_tag(tag))

        total_bibs = sum(len(p.bibs) for p in self.photos.values())
        photos_with_bibs = sum(1 for p in self.photos.values() if p.bibs)

        return {
            "total_photos": total,
            "by_split": by_split,
            "by_tag": by_tag,
            "total_bibs": total_bibs,
            "photos_with_bibs": photos_with_bibs,
            "photos_without_bibs": total - photos_with_bibs,
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "tags": sorted(ALLOWED_TAGS),
            "photos": {
                content_hash: label.to_dict()
                for content_hash, label in self.photos.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> GroundTruth:
        """Create from dictionary."""
        gt = cls(version=data.get("version", SCHEMA_VERSION))
        for content_hash, photo_data in data.get("photos", {}).items():
            # Ensure content_hash is in the photo data
            photo_data["content_hash"] = content_hash
            gt.photos[content_hash] = PhotoLabel.from_dict(photo_data)
        return gt


def get_ground_truth_path() -> Path:
    """Get the default ground truth file path."""
    return Path(__file__).parent / "ground_truth.json"


def load_ground_truth(path: Path | None = None) -> GroundTruth:
    """Load ground truth from JSON file.

    Args:
        path: Path to JSON file (defaults to benchmarking/ground_truth.json)

    Returns:
        GroundTruth instance (empty if file doesn't exist)
    """
    if path is None:
        path = get_ground_truth_path()

    if not path.exists():
        return GroundTruth()

    with open(path, "r") as f:
        data = json.load(f)

    return GroundTruth.from_dict(data)


def save_ground_truth(gt: GroundTruth, path: Path | None = None) -> None:
    """Save ground truth to JSON file.

    Args:
        gt: GroundTruth instance to save
        path: Path to JSON file (defaults to benchmarking/ground_truth.json)
    """
    if path is None:
        path = get_ground_truth_path()

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(gt.to_dict(), f, indent=2)
