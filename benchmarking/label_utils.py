"""Shared helper functions for bib and face labeling routes.

These functions have no Flask dependencies and operate on ground truth data only.
"""

from typing import Callable

from benchmarking.ground_truth import (
    FacePhotoLabel,
    load_bib_ground_truth,
    load_face_ground_truth,
)
from benchmarking.photo_index import load_photo_index


def _filtered_hashes(filter_type: str, all_hashes: set[str], labeled: set[str]) -> list[str]:
    if filter_type == 'unlabeled':
        return sorted(all_hashes - labeled)
    elif filter_type == 'labeled':
        return sorted(all_hashes & labeled)
    return sorted(all_hashes)


def get_filtered_hashes(filter_type: str) -> list[str]:
    """Get photo hashes based on bib label filter."""
    index = load_photo_index()
    all_hashes = set(index.keys())
    if filter_type == 'all':
        return sorted(all_hashes)
    gt = load_bib_ground_truth()
    labeled = {h for h, lbl in gt.photos.items() if lbl.labeled}
    return _filtered_hashes(filter_type, all_hashes, labeled)


def is_face_labeled(label: FacePhotoLabel) -> bool:
    """Check if a photo has face labeling data."""
    return bool(label.boxes) or bool(label.tags)


def get_filtered_face_hashes(filter_type: str) -> list[str]:
    """Get photo hashes based on face label filter."""
    index = load_photo_index()
    all_hashes = set(index.keys())
    if filter_type == 'all':
        return sorted(all_hashes)
    gt = load_face_ground_truth()
    labeled = {h for h, lbl in gt.photos.items() if is_face_labeled(lbl)}
    return _filtered_hashes(filter_type, all_hashes, labeled)


def find_next_unlabeled_url(
    full_hash: str,
    all_hashes_sorted: list[str],
    is_labeled_fn: Callable[[str], bool],
    endpoint: str,
    filter_type: str,
) -> str | None:
    """Return url_for the next unlabeled photo after full_hash, or None."""
    from flask import url_for
    try:
        all_idx = all_hashes_sorted.index(full_hash)
        for h in all_hashes_sorted[all_idx + 1:]:
            if not is_labeled_fn(h):
                return url_for(endpoint, content_hash=h[:8], filter=filter_type)
    except ValueError:
        pass
    return None


def find_hash_by_prefix(prefix: str, hashes) -> str | None:
    """Find full hash from prefix."""
    if isinstance(hashes, set):
        hashes = list(hashes)

    matches = [h for h in hashes if h.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        for h in matches:
            if h == prefix:
                return h
        return matches[0]
    return None


def filter_results(results, filter_type: str):
    """Filter photo results by status."""
    if filter_type == 'all':
        return results
    elif filter_type == 'pass':
        return [r for r in results if r.status == 'PASS']
    elif filter_type == 'partial':
        return [r for r in results if r.status == 'PARTIAL']
    elif filter_type == 'miss':
        return [r for r in results if r.status == 'MISS']
    return results
