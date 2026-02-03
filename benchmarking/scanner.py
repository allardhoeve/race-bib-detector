"""Photo scanning and hashing for benchmark ground truth."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def compute_content_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file contents.

    Args:
        file_path: Path to the image file

    Returns:
        Full SHA256 hex string (64 characters)
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_image_file(path: Path) -> bool:
    """Check if a path is a supported image file."""
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def scan_photos(
    directory: Path,
    recursive: bool = True,
) -> Iterator[tuple[Path, str]]:
    """Scan a directory for photos and compute their content hashes.

    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories (default True)

    Yields:
        Tuples of (file_path, content_hash) for each image found
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    pattern = "**/*" if recursive else "*"

    for path in sorted(directory.glob(pattern)):
        if is_image_file(path):
            content_hash = compute_content_hash(path)
            yield path, content_hash


def build_photo_index(
    directory: Path,
    recursive: bool = True,
) -> dict[str, list[str]]:
    """Build an index mapping content hashes to file paths.

    This detects duplicates by grouping files with the same content hash.

    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories

    Returns:
        Dict mapping content_hash -> list of relative file paths
    """
    index: dict[str, list[str]] = {}

    for path, content_hash in scan_photos(directory, recursive):
        relative_path = str(path.relative_to(directory))
        if content_hash not in index:
            index[content_hash] = []
        index[content_hash].append(relative_path)

    return index
