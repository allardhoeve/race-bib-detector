"""Tests for bib/face ground truth schemas — validation and business logic only."""

from __future__ import annotations

import pytest

from benchmarking.ground_truth import (
    BibBox,
    FaceBox,
    BibPhotoLabel,
    FacePhotoLabel,
    BibGroundTruth,
    load_bib_ground_truth,
    load_face_ground_truth,
)


# =============================================================================
# BibBox
# =============================================================================


class TestBibBox:
    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError, match="Invalid bib box scope"):
            BibBox(x=0, y=0, w=0, h=0, number="1", scope="invalid")

    def test_has_coords_true(self):
        box = BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="1")
        assert box.has_coords

    def test_has_coords_false_zeroes(self):
        box = BibBox(x=0, y=0, w=0, h=0, number="1")
        assert not box.has_coords


# =============================================================================
# FaceBox
# =============================================================================


class TestFaceBox:
    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError, match="Invalid face scope"):
            FaceBox(x=0, y=0, w=0, h=0, scope="maybe")

    def test_invalid_box_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid face box tags"):
            FaceBox(x=0, y=0, w=0.1, h=0.1, tags=["not_a_real_tag"])


# =============================================================================
# BibPhotoLabel
# =============================================================================


class TestBibPhotoLabel:
    def test_extra_fields_ignored(self):
        """BibPhotoLabel silently ignores old tags/split fields from JSON."""
        label = BibPhotoLabel(content_hash="abc", tags=["no_bib"], split="full")
        assert "tags" not in BibPhotoLabel.model_fields
        assert "split" not in BibPhotoLabel.model_fields

    def test_bib_numbers_int(self):
        boxes = [
            BibBox(x=0, y=0, w=0, h=0, number="231"),
            BibBox(x=0, y=0, w=0, h=0, number="62?", scope="bib_obscured"),
            BibBox(x=0, y=0, w=0, h=0, number="100", scope="not_bib"),
            BibBox(x=0, y=0, w=0, h=0, number="55", scope="bib_clipped"),
        ]
        label = BibPhotoLabel(content_hash="abc", boxes=boxes)
        # "bib" and "bib_clipped" with parseable numbers are included
        assert 231 in label.bib_numbers_int
        assert 55 in label.bib_numbers_int
        # "not_bib" and "bib_obscured" excluded
        assert 100 not in label.bib_numbers_int
        # "62?" is not a valid int
        assert len([n for n in label.bib_numbers_int if n == 62]) == 0

    def test_bib_numbers_int_deduplicates(self):
        boxes = [
            BibBox(x=0.1, y=0.1, w=0.1, h=0.1, number="231"),
            BibBox(x=0.5, y=0.5, w=0.1, h=0.1, number="231"),
        ]
        label = BibPhotoLabel(content_hash="abc", boxes=boxes)
        assert label.bib_numbers_int == [231]


# =============================================================================
# FacePhotoLabel
# =============================================================================


class TestFacePhotoLabel:
    def test_labeled_defaults_false(self):
        label = FacePhotoLabel(content_hash="abc")
        assert label.labeled is False

    def test_labeled_roundtrip(self):
        """to_dict / from_dict preserves labeled=True."""
        from benchmarking.ground_truth import FaceGroundTruth
        gt = FaceGroundTruth()
        gt.add_photo(FacePhotoLabel(content_hash="abc", labeled=True))
        restored = FaceGroundTruth.from_dict(gt.to_dict())
        assert restored.get_photo("abc").labeled is True

    def test_from_dict_missing_labeled_defaults_false(self):
        """Old JSON without 'labeled' key loads as labeled=False (no backfill)."""
        from benchmarking.ground_truth import FaceGroundTruth
        old_json = {"version": 3, "photos": {"abc": {"boxes": [], "tags": []}}}
        gt = FaceGroundTruth.from_dict(old_json)
        assert gt.get_photo("abc").labeled is False

    def test_from_dict_with_boxes_no_labeled_stays_false(self):
        """Old JSON with boxes but no 'labeled' key does NOT get backfilled."""
        from benchmarking.ground_truth import FaceGroundTruth, FaceBox
        old_json = {
            "version": 3,
            "photos": {
                "abc": {
                    "boxes": [{"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1, "scope": "keep", "tags": []}],
                    "tags": [],
                }
            },
        }
        gt = FaceGroundTruth.from_dict(old_json)
        assert gt.get_photo("abc").labeled is False

    def test_face_count_from_keep_scoped_boxes(self):
        boxes = [
            FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, scope="keep"),
            FaceBox(x=0.2, y=0.2, w=0.1, h=0.1, scope="keep"),
            FaceBox(x=0.3, y=0.3, w=0.1, h=0.1, scope="exclude"),
            FaceBox(x=0.4, y=0.4, w=0.1, h=0.1, scope="uncertain"),
        ]
        label = FacePhotoLabel(content_hash="abc", boxes=boxes)
        assert label.face_count == 2

    def test_extra_tags_field_ignored(self):
        """FacePhotoLabel silently ignores old tags field from JSON."""
        label = FacePhotoLabel(content_hash="abc", tags=["no_faces"])
        assert "tags" not in FacePhotoLabel.model_fields


# =============================================================================
# BibGroundTruth
# =============================================================================


class TestBibGroundTruth:
    def test_get_unlabeled_hashes(self):
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(content_hash="a"))
        gt.add_photo(BibPhotoLabel(content_hash="b"))
        unlabeled = gt.get_unlabeled_hashes({"a", "b", "c", "d"})
        assert unlabeled == {"c", "d"}


# =============================================================================
# Load / Save — graceful fallback
# =============================================================================


class TestBibLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        gt = load_bib_ground_truth(tmp_path / "nonexistent.json")
        assert len(gt.photos) == 0


class TestFaceLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        gt = load_face_ground_truth(tmp_path / "nonexistent.json")
        assert len(gt.photos) == 0
