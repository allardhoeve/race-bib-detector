"""
Core data types for the bib number recognizer.

This module defines the fundamental data structures used across the application,
serving as the "anchor" types that other modules reference.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Default directories (can be overridden)
DEFAULT_CACHE_DIR = Path(__file__).parent / "cache"
DEFAULT_GRAY_BBOX_DIR = DEFAULT_CACHE_DIR / "gray_bounding"
DEFAULT_SNIPPETS_DIR = DEFAULT_CACHE_DIR / "snippets"
DEFAULT_FACE_SNIPPETS_DIR = DEFAULT_CACHE_DIR / "faces" / "snippets"
DEFAULT_FACE_BOXED_DIR = DEFAULT_CACHE_DIR / "faces" / "boxed"
DEFAULT_FACE_EVIDENCE_DIR = DEFAULT_CACHE_DIR / "faces" / "evidence"
DEFAULT_FACE_CANDIDATES_DIR = DEFAULT_CACHE_DIR / "faces" / "candidates"


def compute_photo_hash(photo_url: str) -> str:
    """Compute an 8-character hash from a photo URL for stable identification.

    This hash is the canonical identifier for photos throughout the system.
    It remains stable regardless of when/how often the photo is scanned.

    Args:
        photo_url: The photo URL (or local file path)

    Returns:
        8-character hex string (SHA-256 prefix)
    """
    return hashlib.sha256(photo_url.encode()).hexdigest()[:8]


@dataclass
class Photo:
    """A photo to be processed for bib number detection.

    This is the anchor type for lineage tracking. All pipeline results
    can be traced back to a Photo instance.

    The photo_hash is the stable identifier used throughout the system:
    - Database lookups
    - URL routing (e.g., /photo/298706ee)
    - Cache file naming
    - Logging and debugging

    Attributes:
        photo_url: Full URL or local file path
        album_id: Opaque album identifier
        thumbnail_url: Optional URL for thumbnail display
        photo_hash: 8-char SHA-256 hash of photo_url (computed if not provided)
        cache_path: Path to cached image file on disk
        source_type: Whether this is from a local file
        id: Database ID (None until persisted)
    """

    photo_url: str
    album_id: str
    thumbnail_url: str | None = None
    photo_hash: str | None = None
    cache_path: Path | None = None
    source_type: Literal["local_file"] = "local_file"
    id: int | None = None

    def __post_init__(self):
        """Compute photo_hash if not provided."""
        if self.photo_hash is None:
            self.photo_hash = compute_photo_hash(self.photo_url)

    @property
    def is_local(self) -> bool:
        """Check if this is a local file."""
        return self.source_type == "local_file"

    @classmethod
    def from_local_path(
        cls,
        file_path: str | Path,
        album_id: str,
    ) -> Photo:
        """Create a Photo from a local file path.

        Args:
            file_path: Path to the image file
            album_id: Album identifier for grouping

        Returns:
            Photo instance with source_type="local_file"
        """
        return cls(
            photo_url=str(file_path),
            album_id=album_id,
            thumbnail_url=None,
            source_type="local_file",
        )

    @classmethod
    def from_db_row(cls, row: dict) -> Photo:
        """Create a Photo from a database row.

        Args:
            row: Dict with keys from photos table (photo_url, album_id,
                 thumbnail_url, photo_hash, cache_path, id)

        Returns:
            Photo instance populated from database
        """
        cache_path = row.get("cache_path")
        return cls(
            photo_url=row["photo_url"],
            album_id=row.get("album_id") or row.get("album_url"),
            thumbnail_url=row.get("thumbnail_url"),
            photo_hash=row.get("photo_hash"),
            cache_path=Path(cache_path) if cache_path else None,
            source_type="local_file",
            id=row.get("id"),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dict suitable for JSON serialization or database operations
        """
        return {
            "photo_url": self.photo_url,
            "album_id": self.album_id,
            "thumbnail_url": self.thumbnail_url,
            "photo_hash": self.photo_hash,
            "cache_path": str(self.cache_path) if self.cache_path else None,
            "source_type": self.source_type,
            "id": self.id,
            "is_local": self.is_local,
        }

    def get_paths(
        self,
        gray_bbox_dir: Path | None = None,
        snippets_dir: Path | None = None,
        face_snippets_dir: Path | None = None,
        face_boxed_dir: Path | None = None,
        face_candidates_dir: Path | None = None,
        face_evidence_dir: Path | None = None,
    ) -> ImagePaths:
        """Get all derived paths for this photo.

        Args:
            gray_bbox_dir: Override default gray bounding box directory
            snippets_dir: Override default snippets directory
            face_snippets_dir: Override default face snippets directory
            face_boxed_dir: Override default face boxed preview directory
            face_evidence_dir: Override default face evidence directory

        Returns:
            ImagePaths with all computed paths

        Raises:
            ValueError: If cache_path is not set
        """
        if self.cache_path is None:
            raise ValueError("Cannot compute paths: cache_path is not set")

        return ImagePaths.for_cache_path(
            self.cache_path,
            gray_bbox_dir=gray_bbox_dir,
            snippets_dir=snippets_dir,
            face_snippets_dir=face_snippets_dir,
            face_boxed_dir=face_boxed_dir,
            face_candidates_dir=face_candidates_dir,
            face_evidence_dir=face_evidence_dir,
        )


@dataclass
class ImagePaths:
    """Consolidates all derived file paths for a photo.

    Given a photo's cache path, computes the paths for:
    - Grayscale image with bounding boxes drawn
    - Snippets directory for bib crops
    - Face snippets directory
    - Face boxed preview directory
    - Face candidates preview directory
    - Face evidence JSON directory
    - Individual snippet files

    This eliminates scattered path computation throughout the codebase.

    Attributes:
        cache_path: Path to the cached original image
        gray_bbox_path: Path to grayscale image with detection boxes drawn
        snippets_dir: Directory containing cropped bib snippets
        face_snippets_dir: Directory containing cropped face snippets
        face_boxed_dir: Directory containing boxed face previews
        face_candidates_dir: Directory containing face candidate previews
        face_evidence_dir: Directory containing face evidence JSON
    """

    cache_path: Path
    gray_bbox_path: Path
    snippets_dir: Path
    face_snippets_dir: Path
    face_boxed_dir: Path
    face_candidates_dir: Path
    face_evidence_dir: Path

    @classmethod
    def for_cache_path(
        cls,
        cache_path: Path,
        gray_bbox_dir: Path | None = None,
        snippets_dir: Path | None = None,
        face_snippets_dir: Path | None = None,
        face_boxed_dir: Path | None = None,
        face_candidates_dir: Path | None = None,
        face_evidence_dir: Path | None = None,
    ) -> ImagePaths:
        """Create ImagePaths from a cache path.

        Args:
            cache_path: Path to the cached image file
            gray_bbox_dir: Override default gray bounding box directory
            snippets_dir: Override default snippets directory
            face_snippets_dir: Override default face snippets directory
            face_boxed_dir: Override default face boxed preview directory

        Returns:
            ImagePaths with all computed paths
        """
        if gray_bbox_dir is None:
            gray_bbox_dir = DEFAULT_GRAY_BBOX_DIR
        if snippets_dir is None:
            snippets_dir = DEFAULT_SNIPPETS_DIR
        if face_snippets_dir is None:
            face_snippets_dir = DEFAULT_FACE_SNIPPETS_DIR
        if face_boxed_dir is None:
            face_boxed_dir = DEFAULT_FACE_BOXED_DIR
        if face_candidates_dir is None:
            face_candidates_dir = DEFAULT_FACE_CANDIDATES_DIR
        if face_evidence_dir is None:
            face_evidence_dir = DEFAULT_FACE_EVIDENCE_DIR

        return cls(
            cache_path=cache_path,
            gray_bbox_path=gray_bbox_dir / cache_path.name,
            snippets_dir=snippets_dir,
            face_snippets_dir=face_snippets_dir,
            face_boxed_dir=face_boxed_dir,
            face_candidates_dir=face_candidates_dir,
            face_evidence_dir=face_evidence_dir,
        )

    def snippet_path(self, bib_number: str, bbox_hash: str) -> Path:
        """Get the path for a specific bib snippet.

        Args:
            bib_number: The detected bib number
            bbox_hash: Hash of the bounding box (for uniqueness)

        Returns:
            Path to the snippet image file
        """
        stem = self.cache_path.stem
        return self.snippets_dir / f"{stem}_bib{bib_number}_{bbox_hash}.jpg"

    def face_snippet_path(self, face_index: int) -> Path:
        """Get the path for a specific face snippet."""
        stem = self.cache_path.stem
        return self.face_snippets_dir / f"{stem}_face{face_index}.jpg"

    def face_boxed_path(self, face_index: int) -> Path:
        """Get the path for a specific boxed face preview."""
        stem = self.cache_path.stem
        return self.face_boxed_dir / f"{stem}_face{face_index}_boxed.jpg"

    def face_evidence_path(self, photo_hash: str) -> Path:
        """Get the path for face evidence JSON for a given photo hash."""
        return self.face_evidence_dir / f"{photo_hash}_faces.json"

    def face_candidates_path(self) -> Path:
        """Get the path for face candidates preview image."""
        return self.face_candidates_dir / self.cache_path.name

    def ensure_dirs_exist(self) -> None:
        """Create all necessary directories if they don't exist."""
        self.gray_bbox_path.parent.mkdir(parents=True, exist_ok=True)
        self.snippets_dir.mkdir(parents=True, exist_ok=True)
        self.face_snippets_dir.mkdir(parents=True, exist_ok=True)
        self.face_boxed_dir.mkdir(parents=True, exist_ok=True)
        self.face_candidates_dir.mkdir(parents=True, exist_ok=True)
        self.face_evidence_dir.mkdir(parents=True, exist_ok=True)
