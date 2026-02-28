"""One-time migration: consolidate photo-level data into photo_metadata.json.

Reads paths from photo_index.json, split/tags from bib_ground_truth.json,
tags from face_ground_truth.json, merges into a PhotoMetadataStore, and
saves photo_metadata.json.  Then re-saves GT files (stripped of split/tags)
and deletes photo_index.json.

Usage::

    venv/bin/python -m benchmarking.migrate_photo_metadata
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .ground_truth import (
    BIB_PHOTO_TAGS,
    FACE_PHOTO_TAGS,
    _FACE_PHOTO_TAGS_COMPAT,
    get_bib_ground_truth_path,
    get_face_ground_truth_path,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
)
from .photo_metadata import (
    PhotoMetadata,
    PhotoMetadataStore,
    get_photo_metadata_path,
    save_photo_metadata,
)

logger = logging.getLogger(__name__)


def _load_old_photo_index(path: Path | None = None) -> dict[str, list[str]]:
    """Load the old photo_index.json (pre-migration format)."""
    if path is None:
        path = Path(__file__).parent / "photo_index.json"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _load_raw_json(path: Path) -> dict:
    """Load raw JSON from a file path."""
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return json.load(f)


def migrate(
    *,
    index_path: Path | None = None,
    bib_gt_path: Path | None = None,
    face_gt_path: Path | None = None,
    metadata_path: Path | None = None,
    delete_old_index: bool = True,
) -> PhotoMetadataStore:
    """Run the migration.

    1. Load photo_index.json → paths
    2. Load bib_ground_truth.json → extract split and tags per photo
    3. Load face_ground_truth.json → extract tags per photo
    4. Build PhotoMetadataStore merging all three sources
    5. Save photo_metadata.json
    6. Re-save bib GT and face GT (updated models drop split/tags)
    7. Delete photo_index.json

    Returns:
        The populated PhotoMetadataStore.
    """
    if index_path is None:
        index_path = Path(__file__).parent / "photo_index.json"
    if bib_gt_path is None:
        bib_gt_path = get_bib_ground_truth_path()
    if face_gt_path is None:
        face_gt_path = get_face_ground_truth_path()
    if metadata_path is None:
        metadata_path = get_photo_metadata_path()

    # Step 1: Load photo index
    old_index = _load_old_photo_index(index_path)
    logger.info("Loaded photo_index.json: %d photos", len(old_index))

    # Step 2: Load raw bib GT (to get split/tags before models strip them)
    raw_bib = _load_raw_json(bib_gt_path)
    raw_bib_photos = raw_bib.get("photos", {})
    logger.info("Loaded bib_ground_truth.json: %d photos", len(raw_bib_photos))

    # Step 3: Load raw face GT (to get tags before models strip them)
    raw_face = _load_raw_json(face_gt_path)
    raw_face_photos = raw_face.get("photos", {})
    logger.info("Loaded face_ground_truth.json: %d photos", len(raw_face_photos))

    # Step 4: Build PhotoMetadataStore
    store = PhotoMetadataStore()
    all_hashes = set(old_index.keys()) | set(raw_bib_photos.keys()) | set(raw_face_photos.keys())

    for content_hash in sorted(all_hashes):
        paths = old_index.get(content_hash, [])

        # Extract split from bib GT
        bib_data = raw_bib_photos.get(content_hash, {})
        split = bib_data.get("split", "")
        # Validate split
        if split not in ("iteration", "full", ""):
            logger.warning("Invalid split %r for %s, defaulting to ''", split, content_hash[:8])
            split = ""

        # Extract bib tags
        raw_bib_tags = bib_data.get("tags", [])
        bib_tags = [t for t in raw_bib_tags if t in BIB_PHOTO_TAGS]

        # Extract face tags
        face_data = raw_face_photos.get(content_hash, {})
        raw_face_tags = face_data.get("tags", [])
        # Migrate legacy face tag name
        face_tags = []
        for t in raw_face_tags:
            if t == "face_no_faces":
                t = "no_faces"
            if t in FACE_PHOTO_TAGS:
                face_tags.append(t)

        store.set(content_hash, PhotoMetadata(
            paths=paths,
            split=split,
            bib_tags=bib_tags,
            face_tags=face_tags,
        ))

    logger.info("Built PhotoMetadataStore: %d photos", len(store.photos))

    # Step 5: Save photo_metadata.json
    save_photo_metadata(store, metadata_path)
    logger.info("Saved %s", metadata_path)

    # Step 6: Re-save GT files (models now strip split/tags via extra="ignore")
    bib_gt = load_bib_ground_truth(bib_gt_path)
    save_bib_ground_truth(bib_gt, bib_gt_path)
    logger.info("Re-saved %s (split/tags removed)", bib_gt_path)

    face_gt = load_face_ground_truth(face_gt_path)
    save_face_ground_truth(face_gt, face_gt_path)
    logger.info("Re-saved %s (tags removed)", face_gt_path)

    # Step 7: Delete old photo_index.json
    if delete_old_index and index_path.exists():
        index_path.unlink()
        logger.info("Deleted %s", index_path)

    return store


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    store = migrate()
    print(f"Migration complete: {len(store.photos)} photos in photo_metadata.json")


if __name__ == "__main__":
    main()
