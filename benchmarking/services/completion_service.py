"""Workflow completion queries: which photos are ready for each labeling step."""
from __future__ import annotations

from benchmarking.ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
)
from benchmarking.photo_index import load_photo_index


def get_bib_progress() -> tuple[int, int]:
    """Return (labeled_count, total_count) for bib labeling."""
    index = load_photo_index()
    total = len(index)
    bib_gt = load_bib_ground_truth()
    done = sum(1 for h in index if (lbl := bib_gt.get_photo(h)) and lbl.labeled)
    return done, total


def get_face_progress() -> tuple[int, int]:
    """Return (labeled_count, total_count) for face labeling."""
    index = load_photo_index()
    total = len(index)
    face_gt = load_face_ground_truth()
    done = sum(1 for h in index if (lbl := face_gt.get_photo(h)) and lbl.labeled)
    return done, total


def get_link_progress() -> tuple[int, int]:
    """Return (linked_count, link_ready_total) for link labeling."""
    link_gt = load_link_ground_truth()
    link_ready = get_link_ready_hashes()
    total = len(link_ready)
    done = sum(1 for h in link_ready if h in link_gt.photos)
    return done, total


def workflow_context_for(content_hash: str, active_step: str) -> dict:
    """Build the ``workflow`` dict passed to all labeling templates.

    active_step: one of 'bibs', 'faces', 'links'
    Returns dict with keys: active_step, bib_progress, face_progress,
    link_progress, bib_labeled, face_labeled, links_saved, link_ready.
    Progress values are dicts with 'done' and 'total' keys.
    """
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()

    bib_label = bib_gt.get_photo(content_hash)
    face_label = face_gt.get_photo(content_hash)

    bib_labeled = bool(bib_label and bib_label.labeled)
    face_labeled = bool(face_label and face_label.labeled)
    link_ready = bib_labeled and face_labeled
    links_saved = link_ready and content_hash in link_gt.photos

    bib_done, bib_total = get_bib_progress()
    face_done, face_total = get_face_progress()
    link_done, link_total = get_link_progress()

    return {
        'active_step': active_step,
        'bib_progress': {'done': bib_done, 'total': bib_total},
        'face_progress': {'done': face_done, 'total': face_total},
        'link_progress': {'done': link_done, 'total': link_total},
        'bib_labeled': bib_labeled,
        'face_labeled': face_labeled,
        'links_saved': links_saved,
        'link_ready': link_ready,
    }


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


def get_underlinked_hashes() -> list[str]:
    """Return processed link-ready hashes where link count < numbered bib count.

    A photo is underlinked when it has been reviewed (saved in link GT) but
    the number of links is fewer than the number of distinct numbered bibs.
    This is a quality-check filter — most underlinked photos are genuine
    mistakes; a few are legitimate exceptions (back-of-head, face out of frame).
    """
    bib_gt = load_bib_ground_truth()
    link_gt = load_link_ground_truth()
    result = []
    for h in get_link_ready_hashes():
        if h not in link_gt.photos:
            continue
        bib_label = bib_gt.get_photo(h)
        numbered_bibs = len(bib_label.bib_numbers_int) if bib_label else 0
        if len(link_gt.photos[h]) < numbered_bibs:
            result.append(h)
    return result
