"""Unit tests for benchmarking.services.association_service."""

import pytest

from benchmarking.photo_index import save_photo_index
from benchmarking.services import association_service

HASH_A = "a" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    link_gt_path = tmp_path / "bib_face_links.json"
    index_path = tmp_path / "photo_index.json"
    save_photo_index({HASH_A: ["photo_a.jpg"]}, index_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path)
    monkeypatch.setattr("benchmarking.photo_index.get_photo_index_path", lambda: index_path)


def test_get_associations_not_found():
    result = association_service.get_associations(HASH_UNKNOWN[:8])
    assert result is None


def test_set_then_get():
    saved = association_service.set_associations(HASH_A[:8], [[0, 1], [2, 3]])
    assert saved == [[0, 1], [2, 3]]

    retrieved = association_service.get_associations(HASH_A[:8])
    assert retrieved == [[0, 1], [2, 3]]


def test_set_associations_invalid_pair():
    """A pair with too few elements raises IndexError."""
    with pytest.raises((TypeError, IndexError, ValueError)):
        association_service.set_associations(HASH_A[:8], [[0]])
