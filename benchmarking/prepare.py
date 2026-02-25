"""Benchmark preparation — copy photos, update index, create GT entries.

The ``prepare`` command is the entry point for adding photos to the
benchmark set.  It copies image files from a source directory into the
benchmark ``photos/`` folder, deduplicating by content hash, then rebuilds
the photo index and ensures every photo has a ground truth entry in both
``bib_ground_truth.json`` and ``face_ground_truth.json``.

Ghost labeling (step 3) hooks in here once implemented.
"""

from __future__ import annotations

import logging
import shutil

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from pathlib import Path

from .ground_truth import (
    BibPhotoLabel,
    FacePhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
)
from .photo_index import save_photo_index
from .scanner import scan_photos, build_photo_index


@dataclass
class PrepareResult:
    """Summary of what prepare_benchmark did.

    Attributes:
        copied: Number of photos copied into photos_dir.
        skipped: Number of photos skipped (already present or duplicate).
        total_photos: Total unique photos in photos_dir after preparation.
        new_hashes: Set of content hashes for newly added photos.
    """

    copied: int = 0
    skipped: int = 0
    total_photos: int = 0
    new_hashes: set[str] = field(default_factory=set)


def prepare_benchmark(
    source_dir: Path,
    photos_dir: Path,
    *,
    bib_gt_path: Path | None = None,
    face_gt_path: Path | None = None,
    index_path: Path | None = None,
    suggestion_store_path: Path | None = None,
    reset_labels: bool = False,
    refresh: bool = False,
) -> PrepareResult:
    """Prepare benchmark photos from a source directory.

    1. Scan source_dir for image files.
    2. Copy new photos into photos_dir (dedup by content hash).
    3. Rebuild the photo index.
    4. Ensure every photo has a ground truth entry in both bib and face GT.
    5. Run ghost labeling on new photos (or all if ``refresh=True``).

    Args:
        source_dir: Directory containing source photos to import.
        photos_dir: Benchmark photos directory (destination).
        bib_gt_path: Path to bib_ground_truth.json (default: standard location).
        face_gt_path: Path to face_ground_truth.json (default: standard location).
        index_path: Path to photo_index.json (default: standard location).
        suggestion_store_path: Path to suggestions.json (default: standard location).
        reset_labels: If True, clear all labels (keep photos and GT entries).
        refresh: If True, re-run ghost labeling on all photos.

    Returns:
        PrepareResult with copy/skip counts and new hashes.
    """
    photos_dir.mkdir(parents=True, exist_ok=True)
    result = PrepareResult()

    # --- 1. Build set of hashes already in photos_dir ---
    existing_index = build_photo_index(photos_dir)
    existing_hashes: set[str] = set(existing_index.keys())

    # --- 2. Scan source and copy new photos ---
    seen_hashes: set[str] = set()

    if source_dir.exists() and source_dir.is_dir():
        for src_path, content_hash in scan_photos(source_dir):
            if content_hash in existing_hashes or content_hash in seen_hashes:
                result.skipped += 1
                seen_hashes.add(content_hash)
                continue

            # Copy to photos_dir preserving filename
            dest = photos_dir / src_path.name
            # Handle filename collision (different content, same name)
            if dest.exists():
                stem = src_path.stem
                suffix = src_path.suffix
                dest = photos_dir / f"{stem}_{content_hash[:8]}{suffix}"
            shutil.copy2(src_path, dest)

            seen_hashes.add(content_hash)
            result.new_hashes.add(content_hash)
            result.copied += 1

    # --- 3. Rebuild photo index ---
    new_index = build_photo_index(photos_dir)
    save_photo_index(new_index, index_path)
    result.total_photos = len(new_index)

    # --- 4. Ensure GT entries exist ---
    bib_gt = load_bib_ground_truth(bib_gt_path)
    face_gt = load_face_ground_truth(face_gt_path)

    if reset_labels:
        # Clear all labels but keep entries
        for content_hash in new_index:
            bib_gt.add_photo(BibPhotoLabel(
                content_hash=content_hash,
                boxes=[],
                tags=[],
                split="full",
                labeled=False,
            ))
            face_gt.add_photo(FacePhotoLabel(
                content_hash=content_hash,
                boxes=[],
                tags=[],
            ))
    else:
        # Only create entries for photos that don't have one yet
        for content_hash in new_index:
            if not bib_gt.has_photo(content_hash):
                bib_gt.add_photo(BibPhotoLabel(
                    content_hash=content_hash,
                    boxes=[],
                    tags=[],
                    split="full",
                    labeled=False,
                ))
            if not face_gt.has_photo(content_hash):
                face_gt.add_photo(FacePhotoLabel(
                    content_hash=content_hash,
                    boxes=[],
                    tags=[],
                ))

    save_bib_ground_truth(bib_gt, bib_gt_path)
    save_face_ground_truth(face_gt, face_gt_path)

    # --- 5. Ghost labeling ---
    ghost_hashes: list[str] = []
    if refresh:
        # Re-run on ALL photos
        ghost_hashes = list(new_index.keys())
    elif result.new_hashes:
        # Run on newly added photos only
        ghost_hashes = list(result.new_hashes)

    if ghost_hashes:
        try:
            from .ghost import run_ghost_labeling

            run_ghost_labeling(
                content_hashes=ghost_hashes,
                photos_dir=photos_dir,
                photo_index=new_index,
                store_path=suggestion_store_path,
            )
        except (ImportError, RuntimeError) as exc:
            # ML dependencies not installed or model files not configured
            logger.debug("Ghost labeling skipped: %s", exc)
            pass

    return result
