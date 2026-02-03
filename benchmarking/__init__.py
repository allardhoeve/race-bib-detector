"""Benchmarking module for bib detection evaluation."""

from .scanner import scan_photos, compute_content_hash, build_photo_index
from .ground_truth import (
    GroundTruth,
    PhotoLabel,
    load_ground_truth,
    save_ground_truth,
    ALLOWED_TAGS,
    ALLOWED_SPLITS,
)
from .photo_index import (
    load_photo_index,
    save_photo_index,
    update_photo_index,
    get_path_for_hash,
)

__all__ = [
    # Scanner
    "scan_photos",
    "compute_content_hash",
    "build_photo_index",
    # Ground truth
    "GroundTruth",
    "PhotoLabel",
    "load_ground_truth",
    "save_ground_truth",
    "ALLOWED_TAGS",
    "ALLOWED_SPLITS",
    # Photo index
    "load_photo_index",
    "save_photo_index",
    "update_photo_index",
    "get_path_for_hash",
]
