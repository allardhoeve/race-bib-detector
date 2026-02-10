"""Tests for the new bib/face ground truth schemas (Step 0)."""

from __future__ import annotations

import json
import pytest

from benchmarking.ground_truth import (
    BibBox,
    FaceBox,
    BibPhotoLabel,
    FacePhotoLabel,
    BibGroundTruth,
    FaceGroundTruth,
    BIB_BOX_TAGS,
    FACE_BOX_TAGS,
    FACE_SCOPE_TAGS,
    FACE_PHOTO_TAGS,
    _FACE_PHOTO_TAGS_COMPAT,
    load_bib_ground_truth,
    save_bib_ground_truth,
    load_face_ground_truth,
    save_face_ground_truth,
    migrate_from_legacy,
)


# =============================================================================
# BibBox
# =============================================================================


class TestBibBox:
    def test_invalid_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid bib box tag"):
            BibBox(x=0, y=0, w=0, h=0, number="1", tag="invalid")

    def test_all_valid_tags(self):
        for tag in BIB_BOX_TAGS:
            box = BibBox(x=0, y=0, w=0, h=0, number="1", tag=tag)
            assert box.tag == tag

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

    def test_all_valid_scopes(self):
        for scope in FACE_SCOPE_TAGS:
            box = FaceBox(x=0, y=0, w=0, h=0, scope=scope)
            assert box.scope == scope

    def test_valid_box_tags(self):
        box = FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, tags=["tiny", "blurry"])
        assert box.tags == ["tiny", "blurry"]

    def test_all_valid_box_tags(self):
        for tag in FACE_BOX_TAGS:
            box = FaceBox(x=0, y=0, w=0.1, h=0.1, tags=[tag])
            assert tag in box.tags

    def test_invalid_box_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid face box tags"):
            FaceBox(x=0, y=0, w=0.1, h=0.1, tags=["not_a_real_tag"])

    def test_empty_tags_default(self):
        box = FaceBox(x=0, y=0, w=0.1, h=0.1)
        assert box.tags == []

    def test_tags_round_trip(self):
        box = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4, scope="keep", tags=["profile", "looking_down"])
        d = box.to_dict()
        assert d["tags"] == ["profile", "looking_down"]
        restored = FaceBox.from_dict(d)
        assert restored.tags == ["profile", "looking_down"]

    def test_empty_tags_not_serialised(self):
        box = FaceBox(x=0.1, y=0.2, w=0.3, h=0.4)
        d = box.to_dict()
        assert "tags" not in d

    def test_from_dict_missing_tags(self):
        d = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4, "scope": "keep"}
        box = FaceBox.from_dict(d)
        assert box.tags == []


# =============================================================================
# BibPhotoLabel
# =============================================================================


class TestBibPhotoLabel:
    def test_invalid_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid bib photo tags"):
            BibPhotoLabel(content_hash="abc", tags=["not_a_real_tag"])

    def test_invalid_split_raises(self):
        with pytest.raises(ValueError, match="Invalid split"):
            BibPhotoLabel(content_hash="abc", split="bogus")

    def test_bib_numbers_int(self):
        boxes = [
            BibBox(x=0, y=0, w=0, h=0, number="231"),
            BibBox(x=0, y=0, w=0, h=0, number="62?", tag="bib_partial"),
            BibBox(x=0, y=0, w=0, h=0, number="100", tag="not_bib"),
        ]
        label = BibPhotoLabel(content_hash="abc", boxes=boxes)
        # Only "bib" and "bib_partial" tags with parseable numbers
        assert 231 in label.bib_numbers_int
        # "not_bib" box excluded
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
    def test_face_count_from_keep_scoped_boxes(self):
        boxes = [
            FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, scope="keep"),
            FaceBox(x=0.2, y=0.2, w=0.1, h=0.1, scope="keep"),
            FaceBox(x=0.3, y=0.3, w=0.1, h=0.1, scope="ignore"),
            FaceBox(x=0.4, y=0.4, w=0.1, h=0.1, scope="unknown"),
        ]
        label = FacePhotoLabel(content_hash="abc", boxes=boxes)
        assert label.face_count == 2

    def test_invalid_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid face photo tags"):
            FacePhotoLabel(content_hash="abc", tags=["not_a_tag"])

    def test_new_photo_level_tags_valid(self):
        for tag in FACE_PHOTO_TAGS:
            label = FacePhotoLabel(content_hash="abc", tags=[tag])
            assert tag in label.tags

    def test_compat_old_photo_tags_still_load(self):
        """Old per-photo face tags (now per-box) are still accepted during transition."""
        old_tags = ["face_tiny_faces", "face_blurry_faces", "face_occluded_faces", "face_profile"]
        for tag in old_tags:
            label = FacePhotoLabel(content_hash="abc", tags=[tag])
            assert tag in label.tags

    def test_compat_set_includes_all(self):
        assert FACE_PHOTO_TAGS < _FACE_PHOTO_TAGS_COMPAT
        assert "face_tiny_faces" in _FACE_PHOTO_TAGS_COMPAT
        assert "face_no_faces" in _FACE_PHOTO_TAGS_COMPAT


# =============================================================================
# BibGroundTruth
# =============================================================================


class TestBibGroundTruth:
    def test_create_empty(self):
        gt = BibGroundTruth()
        assert len(gt.photos) == 0

    def test_add_and_get_photo(self):
        gt = BibGroundTruth()
        label = BibPhotoLabel(content_hash="abc123", labeled=True)
        gt.add_photo(label)
        assert gt.get_photo("abc123") is label
        assert gt.has_photo("abc123")

    def test_get_nonexistent(self):
        gt = BibGroundTruth()
        assert gt.get_photo("nope") is None
        assert not gt.has_photo("nope")

    def test_remove_photo(self):
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(content_hash="abc123"))
        assert gt.remove_photo("abc123") is True
        assert gt.remove_photo("abc123") is False
        assert not gt.has_photo("abc123")

    def test_get_by_split_full(self):
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(content_hash="a", split="full"))
        gt.add_photo(BibPhotoLabel(content_hash="b", split="iteration"))
        gt.add_photo(BibPhotoLabel(content_hash="c", split="full"))
        # "full" split returns ALL photos
        full = gt.get_by_split("full")
        assert len(full) == 3

    def test_get_by_split_iteration(self):
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(content_hash="a", split="full"))
        gt.add_photo(BibPhotoLabel(content_hash="b", split="iteration"))
        gt.add_photo(BibPhotoLabel(content_hash="c", split="full"))
        iteration = gt.get_by_split("iteration")
        assert len(iteration) == 1
        assert iteration[0].content_hash == "b"

    def test_get_unlabeled_hashes(self):
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(content_hash="a"))
        gt.add_photo(BibPhotoLabel(content_hash="b"))
        unlabeled = gt.get_unlabeled_hashes({"a", "b", "c", "d"})
        assert unlabeled == {"c", "d"}


# =============================================================================
# FaceGroundTruth
# =============================================================================


class TestFaceGroundTruth:
    def test_create_empty(self):
        gt = FaceGroundTruth()
        assert len(gt.photos) == 0

    def test_add_and_get_photo(self):
        gt = FaceGroundTruth()
        label = FacePhotoLabel(content_hash="abc123")
        gt.add_photo(label)
        assert gt.get_photo("abc123") is label

    def test_remove_photo(self):
        gt = FaceGroundTruth()
        gt.add_photo(FacePhotoLabel(content_hash="abc123"))
        assert gt.remove_photo("abc123") is True
        assert gt.remove_photo("abc123") is False


# =============================================================================
# Load / Save
# =============================================================================


class TestBibLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        gt = load_bib_ground_truth(tmp_path / "nonexistent.json")
        assert len(gt.photos) == 0

    def test_saved_json_is_valid(self, tmp_path):
        path = tmp_path / "bib_gt.json"
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(content_hash="h1", labeled=True))
        save_bib_ground_truth(gt, path)
        # Should be valid JSON
        data = json.loads(path.read_text())
        assert "version" in data
        assert "photos" in data


class TestFaceLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        gt = load_face_ground_truth(tmp_path / "nonexistent.json")
        assert len(gt.photos) == 0
