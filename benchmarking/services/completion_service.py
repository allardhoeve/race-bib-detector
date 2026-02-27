"""Workflow completion queries: which photos are ready for each labeling step."""
from __future__ import annotations

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
)
from benchmarking.photo_index import load_photo_index


def get_link_ready_hashes() -> list[str]:
    """Return sorted hashes where both bib and face labeling are explicitly done.

    These are the only photos that should appear in the linking queue.
    Photos where bib_count==0 OR face_count==0 are included — the link step
    is trivially done, but they should still be visible/skippable in the UI.
    """
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    index = load_photo_index()

    ready = []
    for h in sorted(index.keys()):
        bib_label = bib_gt.get_photo(h)
        face_label = face_gt.get_photo(h)
        bib_labeled = bool(bib_label and bib_label.labeled)
        face_labeled = bool(face_label and face_label.labeled)
        if bib_labeled and face_labeled:
            ready.append(h)
    return ready


def get_unlinked_hashes() -> list[str]:
    """Return link-ready hashes that have not yet had links saved."""
    link_gt = load_link_ground_truth()
    return [h for h in get_link_ready_hashes() if h not in link_gt.photos]
