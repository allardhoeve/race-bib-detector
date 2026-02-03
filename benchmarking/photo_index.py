"""Photo index management - maps content hashes to file paths."""

from __future__ import annotations

import json
from pathlib import Path

from .scanner import build_photo_index


def get_photo_index_path() -> Path:
    """Get the default photo index file path."""
    return Path(__file__).parent / "photo_index.json"


def load_photo_index(path: Path | None = None) -> dict[str, list[str]]:
    """Load photo index from JSON file.

    Args:
        path: Path to JSON file (defaults to benchmarking/photo_index.json)

    Returns:
        Dict mapping content_hash -> list of relative file paths
    """
    if path is None:
        path = get_photo_index_path()

    if not path.exists():
        return {}

    with open(path, "r") as f:
        return json.load(f)


def save_photo_index(
    index: dict[str, list[str]],
    path: Path | None = None,
) -> None:
    """Save photo index to JSON file.

    Args:
        index: Dict mapping content_hash -> list of relative file paths
        path: Path to JSON file (defaults to benchmarking/photo_index.json)
    """
    if path is None:
        path = get_photo_index_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(index, f, indent=2)


def update_photo_index(
    photos_dir: Path,
    recursive: bool = True,
) -> tuple[dict[str, list[str]], dict]:
    """Scan photos directory and update the index.

    Args:
        photos_dir: Directory containing photos
        recursive: Whether to scan subdirectories

    Returns:
        Tuple of (new_index, stats) where stats contains:
        - total_files: Number of image files found
        - unique_hashes: Number of unique content hashes
        - duplicates: Number of duplicate files
        - new_photos: Number of photos not in previous index
    """
    # Load existing index for comparison
    existing_index = load_photo_index()
    existing_hashes = set(existing_index.keys())

    # Build new index from disk
    new_index = build_photo_index(photos_dir, recursive)
    new_hashes = set(new_index.keys())

    # Compute stats
    total_files = sum(len(paths) for paths in new_index.values())
    unique_hashes = len(new_index)
    duplicates = total_files - unique_hashes
    new_photos = len(new_hashes - existing_hashes)

    stats = {
        "total_files": total_files,
        "unique_hashes": unique_hashes,
        "duplicates": duplicates,
        "new_photos": new_photos,
    }

    # Save updated index
    save_photo_index(new_index)

    return new_index, stats


def get_path_for_hash(
    content_hash: str,
    photos_dir: Path,
    index: dict[str, list[str]] | None = None,
) -> Path | None:
    """Get the file path for a content hash.

    Args:
        content_hash: The content hash to look up
        photos_dir: Base directory for photos
        index: Optional pre-loaded index (loads from disk if not provided)

    Returns:
        Path to the first file with this hash, or None if not found
    """
    if index is None:
        index = load_photo_index()

    paths = index.get(content_hash, [])
    if not paths:
        return None

    return photos_dir / paths[0]
