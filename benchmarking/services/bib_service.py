"""Business logic for bib photo labeling."""

import io
import random
from pathlib import Path
from typing import TypedDict

from PIL import Image

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
)
from benchmarking.ghost import BibSuggestion, load_suggestion_store
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index, get_path_for_hash
from benchmarking.photo_metadata import (
    PhotoMetadata,
    load_photo_metadata,
    save_photo_metadata,
)
from config import ITERATION_SPLIT_PROBABILITY

PHOTOS_DIR = Path(__file__).parent.parent.parent / "photos"


class BibLabelData(TypedDict):
    full_hash: str
    boxes: list[BibBox]
    suggestions: list[BibSuggestion]
    tags: list[str]
    split: str
    labeled: bool


def get_bib_label(content_hash: str) -> BibLabelData | None:
    """Return typed bib label data for a photo hash prefix, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions: list[BibSuggestion] = photo_sugg.bibs if photo_sugg else []

    meta_store = load_photo_metadata()
    meta = meta_store.get(full_hash)

    if label:
        return BibLabelData(
            full_hash=full_hash,
            boxes=label.boxes,
            suggestions=suggestions,
            tags=meta.bib_tags if meta else [],
            split=meta.split if meta else "full",
            labeled=label.labeled,
        )
    return BibLabelData(
        full_hash=full_hash,
        boxes=[],
        suggestions=suggestions,
        tags=meta.bib_tags if meta else [],
        split=meta.split if meta else "full",
        labeled=False,
    )


def save_bib_label(content_hash: str, boxes: list[BibBox] | None,
                   bibs_legacy: list[int] | None, tags: list[str],
                   split: str) -> None:
    """Construct a BibPhotoLabel and persist it, plus save tags/split to PhotoMetadata."""
    bib_gt = load_bib_ground_truth()
    if boxes is not None:
        pass  # already validated BibBox objects
    elif bibs_legacy is not None:
        boxes = [BibBox(x=0, y=0, w=0, h=0, number=str(b), scope="bib")
                 for b in bibs_legacy]
    else:
        boxes = []
    label = BibPhotoLabel(
        content_hash=content_hash,
        boxes=boxes,
        labeled=True,
    )
    bib_gt.add_photo(label)
    save_bib_ground_truth(bib_gt)

    # Save tags and split to PhotoMetadata
    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash) or PhotoMetadata(paths=[])
    meta.bib_tags = tags
    meta.split = split
    meta_store.set(content_hash, meta)
    save_photo_metadata(meta_store)


def get_bib_crop_jpeg(content_hash: str, box_index: int) -> bytes | None:
    """Return JPEG bytes of a labeled bib crop, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)
    if not label or box_index < 0 or box_index >= len(label.boxes):
        return None

    box = label.boxes[box_index]
    if not box.has_coords:
        return None

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return None

    img = Image.open(photo_path)
    w, h = img.size
    left = int(box.x * w)
    upper = int(box.y * h)
    right = int((box.x + box.w) * w)
    lower = int((box.y + box.h) * h)
    crop = img.crop((left, upper, right, lower))

    buf = io.BytesIO()
    crop.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf.read()


def default_split_for_hash(content_hash: str) -> str:
    """Return the existing split for a hash, or randomly assign one."""
    meta_store = load_photo_metadata()
    meta = meta_store.get(content_hash)
    if meta and meta.split:
        return meta.split
    return 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'
