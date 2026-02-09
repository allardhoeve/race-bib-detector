"""Tests for the new bib/face ground truth schemas (Step 0)."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from benchmarking.ground_truth import (
    BibBox,
    FaceBox,
    BibPhotoLabel,
    FacePhotoLabel,
    BibGroundTruth,
    FaceGroundTruth,
    BIB_BOX_TAGS,
    FACE_SCOPE_TAGS,
    BIB_PHOTO_TAGS,
    FACE_PHOTO_TAGS,
    ALLOWED_SPLITS,
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
    def test_create_default(self):
        box = BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="231")
        assert box.tag == "bib"
        assert box.number == "231"

    def test_create_with_tag(self):
        box = BibBox(x=0, y=0, w=0, h=0, number="62?", tag="bib_partial")
        assert box.tag == "bib_partial"
        assert box.number == "62?"

    def test_invalid_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid bib box tag"):
            BibBox(x=0, y=0, w=0, h=0, number="1", tag="invalid")

    def test_all_valid_tags(self):
        for tag in BIB_BOX_TAGS:
            box = BibBox(x=0, y=0, w=0, h=0, number="1", tag=tag)
            assert box.tag == tag

    def test_empty_number(self):
        box = BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="")
        assert box.number == ""

    def test_has_coords_true(self):
        box = BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="1")
        assert box.has_coords

    def test_has_coords_false_zeroes(self):
        box = BibBox(x=0, y=0, w=0, h=0, number="1")
        assert not box.has_coords

    def test_to_dict_round_trip(self):
        box = BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="231", tag="bib")
        d = box.to_dict()
        restored = BibBox.from_dict(d)
        assert restored.x == box.x
        assert restored.y == box.y
        assert restored.w == box.w
        assert restored.h == box.h
        assert restored.number == box.number
        assert restored.tag == box.tag


# =============================================================================
# FaceBox
# =============================================================================


class TestFaceBox:
    def test_create_default(self):
        box = FaceBox(x=0.3, y=0.1, w=0.08, h=0.1)
        assert box.scope == "keep"
        assert box.identity is None

    def test_create_with_identity(self):
        box = FaceBox(x=0.3, y=0.1, w=0.08, h=0.1, scope="keep", identity="Alice")
        assert box.identity == "Alice"

    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError, match="Invalid face scope"):
            FaceBox(x=0, y=0, w=0, h=0, scope="maybe")

    def test_all_valid_scopes(self):
        for scope in FACE_SCOPE_TAGS:
            box = FaceBox(x=0, y=0, w=0, h=0, scope=scope)
            assert box.scope == scope

    def test_to_dict_round_trip(self):
        box = FaceBox(x=0.3, y=0.1, w=0.08, h=0.1, scope="ignore", identity="Bob")
        d = box.to_dict()
        restored = FaceBox.from_dict(d)
        assert restored.x == box.x
        assert restored.scope == box.scope
        assert restored.identity == box.identity

    def test_to_dict_no_identity(self):
        box = FaceBox(x=0.1, y=0.2, w=0.05, h=0.03)
        d = box.to_dict()
        assert "identity" not in d


# =============================================================================
# BibPhotoLabel
# =============================================================================


class TestBibPhotoLabel:
    def test_create_empty(self):
        label = BibPhotoLabel(content_hash="abc123")
        assert label.boxes == []
        assert label.tags == []
        assert label.split == "full"
        assert label.labeled is False

    def test_create_with_boxes(self):
        boxes = [
            BibBox(x=0, y=0, w=0, h=0, number="231"),
            BibBox(x=0, y=0, w=0, h=0, number="62?", tag="bib_partial"),
        ]
        label = BibPhotoLabel(content_hash="abc", boxes=boxes, labeled=True)
        assert len(label.boxes) == 2

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

    def test_to_dict_round_trip(self):
        boxes = [BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="231")]
        label = BibPhotoLabel(
            content_hash="abc123",
            boxes=boxes,
            tags=["no_bib"],
            split="iteration",
            labeled=True,
        )
        d = label.to_dict()
        restored = BibPhotoLabel.from_dict("abc123", d)
        assert restored.content_hash == label.content_hash
        assert len(restored.boxes) == 1
        assert restored.boxes[0].number == "231"
        assert restored.tags == ["no_bib"]
        assert restored.split == "iteration"
        assert restored.labeled is True


# =============================================================================
# FacePhotoLabel
# =============================================================================


class TestFacePhotoLabel:
    def test_create_empty(self):
        label = FacePhotoLabel(content_hash="abc123")
        assert label.boxes == []
        assert label.tags == []

    def test_face_count_from_keep_scoped_boxes(self):
        boxes = [
            FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, scope="keep"),
            FaceBox(x=0.2, y=0.2, w=0.1, h=0.1, scope="keep"),
            FaceBox(x=0.3, y=0.3, w=0.1, h=0.1, scope="ignore"),
            FaceBox(x=0.4, y=0.4, w=0.1, h=0.1, scope="unknown"),
        ]
        label = FacePhotoLabel(content_hash="abc", boxes=boxes)
        assert label.face_count == 2

    def test_face_count_empty(self):
        label = FacePhotoLabel(content_hash="abc")
        assert label.face_count == 0

    def test_invalid_tag_raises(self):
        with pytest.raises(ValueError, match="Invalid face photo tags"):
            FacePhotoLabel(content_hash="abc", tags=["not_a_tag"])

    def test_to_dict_round_trip(self):
        boxes = [
            FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, scope="keep", identity="Alice"),
        ]
        label = FacePhotoLabel(
            content_hash="abc123",
            boxes=boxes,
            tags=["face_tiny_faces"],
        )
        d = label.to_dict()
        restored = FacePhotoLabel.from_dict("abc123", d)
        assert restored.content_hash == label.content_hash
        assert len(restored.boxes) == 1
        assert restored.boxes[0].identity == "Alice"
        assert restored.tags == ["face_tiny_faces"]


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

    def test_to_dict_from_dict_round_trip(self):
        gt = BibGroundTruth()
        boxes = [BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="231")]
        gt.add_photo(BibPhotoLabel(
            content_hash="abc123",
            boxes=boxes,
            tags=["no_bib"],
            split="iteration",
            labeled=True,
        ))
        gt.add_photo(BibPhotoLabel(content_hash="def456"))

        d = gt.to_dict()
        restored = BibGroundTruth.from_dict(d)
        assert len(restored.photos) == 2
        label = restored.get_photo("abc123")
        assert label is not None
        assert label.boxes[0].number == "231"
        assert label.split == "iteration"


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

    def test_to_dict_from_dict_round_trip(self):
        gt = FaceGroundTruth()
        boxes = [
            FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, scope="keep", identity="Alice"),
            FaceBox(x=0.5, y=0.5, w=0.1, h=0.1, scope="ignore"),
        ]
        gt.add_photo(FacePhotoLabel(
            content_hash="abc123",
            boxes=boxes,
            tags=["face_blurry_faces"],
        ))

        d = gt.to_dict()
        restored = FaceGroundTruth.from_dict(d)
        assert len(restored.photos) == 1
        label = restored.get_photo("abc123")
        assert label is not None
        assert len(label.boxes) == 2
        assert label.boxes[0].identity == "Alice"
        assert label.face_count == 1  # only 1 "keep"


# =============================================================================
# Load / Save
# =============================================================================


class TestBibLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        gt = load_bib_ground_truth(tmp_path / "nonexistent.json")
        assert len(gt.photos) == 0

    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "bib_gt.json"
        gt = BibGroundTruth()
        gt.add_photo(BibPhotoLabel(
            content_hash="abc123",
            boxes=[BibBox(x=0.1, y=0.2, w=0.05, h=0.03, number="231")],
            tags=["no_bib"],
            split="iteration",
            labeled=True,
        ))
        save_bib_ground_truth(gt, path)
        loaded = load_bib_ground_truth(path)
        assert len(loaded.photos) == 1
        label = loaded.get_photo("abc123")
        assert label.boxes[0].number == "231"
        assert label.labeled is True

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

    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "face_gt.json"
        gt = FaceGroundTruth()
        gt.add_photo(FacePhotoLabel(
            content_hash="abc123",
            boxes=[FaceBox(x=0.1, y=0.1, w=0.1, h=0.1, scope="keep", identity="Alice")],
            tags=["face_profile"],
        ))
        save_face_ground_truth(gt, path)
        loaded = load_face_ground_truth(path)
        assert len(loaded.photos) == 1
        label = loaded.get_photo("abc123")
        assert label.boxes[0].identity == "Alice"