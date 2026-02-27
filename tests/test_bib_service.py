"""Unit tests for benchmarking.services.bib_service."""

import pytest

from benchmarking.ground_truth import BibBox
from benchmarking.photo_index import save_photo_index
from benchmarking.services import bib_service

HASH_A = "a" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    suggestions_path = tmp_path / "suggestions.json"
    index_path = tmp_path / "photo_index.json"
    save_photo_index({HASH_A: ["photo_a.jpg"]}, index_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path)
    monkeypatch.setattr("benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path)
    monkeypatch.setattr("benchmarking.photo_index.get_photo_index_path", lambda: index_path)


def test_get_bib_label_not_found():
    result = bib_service.get_bib_label(HASH_UNKNOWN[:8])
    assert result is None


def test_get_bib_label_no_existing_label():
    result = bib_service.get_bib_label(HASH_A[:8])
    assert result is not None
    assert result["boxes"] == []
    assert result["tags"] == []
    assert result["labeled"] is False
    assert result["full_hash"] == HASH_A


def test_save_bib_label_boxes():
    bib_service.save_bib_label(
        content_hash=HASH_A,
        boxes=[BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="42", scope="bib")],
        bibs_legacy=None,
        tags=["dark_bib"],
        split="full",
    )
    result = bib_service.get_bib_label(HASH_A[:8])
    assert result["labeled"] is True
    assert len(result["boxes"]) == 1
    assert result["boxes"][0].number == "42"
    assert result["tags"] == ["dark_bib"]


def test_save_bib_label_legacy_bibs():
    bib_service.save_bib_label(
        content_hash=HASH_A,
        boxes=None,
        bibs_legacy=[7, 42],
        tags=[],
        split="iteration",
    )
    result = bib_service.get_bib_label(HASH_A[:8])
    assert result["labeled"] is True
    assert len(result["boxes"]) == 2
    # Legacy boxes have has_coords=False (x=y=w=h=0)
    assert all(b.x == 0 and b.y == 0 for b in result["boxes"])
    assert {b.number for b in result["boxes"]} == {"7", "42"}


def test_save_bib_label_invalid_scope():
    """BibBox rejects invalid scope at construction time."""
    with pytest.raises(ValueError):
        BibBox(x=0.1, y=0.2, w=0.3, h=0.4, number="1", scope="invalid_scope")
