"""Business logic for bib-face link associations."""

from benchmarking.ground_truth import (
    BibFaceLink,
    load_link_ground_truth,
    save_link_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index


def get_associations(content_hash: str) -> list[list[int]] | None:
    """Return links for a hash prefix as [[bib_index, face_index], ...].

    Returns None if the hash prefix is not found.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None
    link_gt = load_link_ground_truth()
    return [lnk.to_pair() for lnk in link_gt.get_links(full_hash)]


def set_associations(content_hash: str,
                     raw_links: list[list[int]]) -> list[list[int]] | None:
    """Replace all links for a hash prefix. Returns the saved links.

    Returns None if the hash prefix is not found.
    Raises ValueError / TypeError / IndexError on malformed link pairs.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None
    links = [BibFaceLink.from_pair(pair) for pair in raw_links]
    link_gt = load_link_ground_truth()
    link_gt.set_links(full_hash, links)
    save_link_ground_truth(link_gt)
    return [lnk.to_pair() for lnk in links]
