"""Business logic for bib photo labeling."""

import random
from typing import TypedDict

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
)
from benchmarking.ghost import BibSuggestion, load_suggestion_store
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index
from config import ITERATION_SPLIT_PROBABILITY


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

    if label:
        return BibLabelData(
            full_hash=full_hash,
            boxes=label.boxes,
            suggestions=suggestions,
            tags=label.tags,
            split=label.split,
            labeled=label.labeled,
        )
    return BibLabelData(
        full_hash=full_hash,
        boxes=[],
        suggestions=suggestions,
        tags=[],
        split='full',
        labeled=False,
    )


def save_bib_label(content_hash: str, boxes: list[BibBox] | None,
                   bibs_legacy: list[int] | None, tags: list[str],
                   split: str) -> None:
    """Construct a BibPhotoLabel and persist it."""
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
        tags=tags,
        split=split,
        labeled=True,
    )
    bib_gt.add_photo(label)
    save_bib_ground_truth(bib_gt)


def default_split_for_hash(content_hash: str) -> str:
    """Return the existing split for a hash, or randomly assign one."""
    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(content_hash)
    if label:
        return label.split
    return 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'
