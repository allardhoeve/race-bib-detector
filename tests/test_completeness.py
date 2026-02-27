"""Tests for benchmarking/completeness.py."""

import pytest

from benchmarking.completeness import PhotoCompleteness, photo_completeness, get_all_completeness
from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    BibGroundTruth,
    FaceBox,
    FacePhotoLabel,
    FaceGroundTruth,
    save_bib_ground_truth,
    save_face_ground_truth,
    load_link_ground_truth,
    save_link_ground_truth,
    LinkGroundTruth,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


@pytest.fixture(autouse=True)
def patch_gt_paths(tmp_path, monkeypatch):
    bib_path = tmp_path / "bib_ground_truth.json"
    face_path = tmp_path / "face_ground_truth.json"
    link_path = tmp_path / "bib_face_links.json"
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_path
    )
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_path
    )


def _bib_gt_with(hashes_boxes: dict) -> BibGroundTruth:
    """Build a BibGroundTruth with each hash mapped to a list of BibBox objects."""
    gt = BibGroundTruth()
    for h, boxes in hashes_boxes.items():
        gt.add_photo(BibPhotoLabel(content_hash=h, boxes=boxes, labeled=True))
    return gt


def _face_gt_with(hashes_boxes: dict) -> FaceGroundTruth:
    """Build a FaceGroundTruth with each hash mapped to a list of FaceBox objects."""
    gt = FaceGroundTruth()
    for h, boxes in hashes_boxes.items():
        gt.add_photo(FacePhotoLabel(content_hash=h, boxes=boxes, labeled=True))
    return gt


def _bib_box(number: str = "42") -> BibBox:
    return BibBox(x=0.1, y=0.1, w=0.2, h=0.2, number=number, scope="bib")


def _face_box() -> FaceBox:
    return FaceBox(x=0.1, y=0.1, w=0.2, h=0.2, scope="keep")


class TestPhotoCompleteness:
    def test_all_done(self):
        """Bib + face GT populated with boxes, link GT entry exists → is_complete=True."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: [_bib_box()]}))
        save_face_ground_truth(_face_gt_with({HASH_A: [_face_box()]}))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])
        save_link_ground_truth(link_gt)

        result = photo_completeness(HASH_A)

        assert result.bib_labeled is True
        assert result.face_labeled is True
        assert result.links_labeled is True
        assert result.is_complete is True
        assert result.bib_box_count == 1
        assert result.face_box_count == 1

    def test_bib_only(self):
        """Only bib labeled → is_complete=False, face_labeled=False."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: [_bib_box()]}))
        save_face_ground_truth(FaceGroundTruth())

        result = photo_completeness(HASH_A)

        assert result.bib_labeled is True
        assert result.face_labeled is False
        assert result.is_complete is False

    def test_face_only(self):
        """Only face labeled → is_complete=False, bib_labeled=False."""
        save_bib_ground_truth(BibGroundTruth())
        save_face_ground_truth(_face_gt_with({HASH_A: [_face_box()]}))

        result = photo_completeness(HASH_A)

        assert result.bib_labeled is False
        assert result.face_labeled is True
        assert result.is_complete is False

    def test_known_negative(self):
        """Both labeled, 0 boxes each → is_known_negative=True, is_complete=True."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: []}))
        gt = FaceGroundTruth()
        gt.add_photo(FacePhotoLabel(content_hash=HASH_A, boxes=[], tags=["no_faces"], labeled=True))
        save_face_ground_truth(gt)
        # (No link GT needed)

        result = photo_completeness(HASH_A)

        assert result.bib_labeled is True
        assert result.face_labeled is True
        assert result.links_labeled is True  # trivially True
        assert result.bib_box_count == 0
        assert result.face_box_count == 0
        assert result.is_known_negative is True
        assert result.is_complete is True

    def test_links_trivial_when_both_labeled_and_face_empty(self):
        """Bib has boxes, face explicitly labeled with 0 boxes → links trivially done."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: [_bib_box()]}))
        save_face_ground_truth(_face_gt_with({HASH_A: []}))  # labeled=True via helper

        result = photo_completeness(HASH_A)

        assert result.bib_box_count == 1
        assert result.face_box_count == 0
        assert result.links_labeled is True

    def test_links_not_trivial_when_face_not_labeled(self):
        """Face not explicitly labeled → links not trivially done even with 0 face boxes."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: [_bib_box()]}))
        gt = FaceGroundTruth()
        gt.add_photo(FacePhotoLabel(content_hash=HASH_A, boxes=[]))  # labeled=False (default)
        save_face_ground_truth(gt)

        result = photo_completeness(HASH_A)

        assert result.face_labeled is False
        assert result.links_labeled is False

    def test_links_missing_when_both_have_boxes(self):
        """Both have boxes but no link GT entry → links_labeled=False."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: [_bib_box()]}))
        save_face_ground_truth(_face_gt_with({HASH_A: [_face_box()]}))
        # No link GT saved

        result = photo_completeness(HASH_A)

        assert result.bib_box_count == 1
        assert result.face_box_count == 1
        assert result.links_labeled is False
        assert result.is_complete is False


class TestGetAllCompleteness:
    def test_only_touched_photos_returned(self):
        """A photo in neither GT is not returned."""
        save_bib_ground_truth(_bib_gt_with({HASH_A: [_bib_box()]}))
        save_face_ground_truth(_face_gt_with({HASH_B: [_face_box()]}))
        # HASH_C is in neither GT

        results = get_all_completeness()
        hashes = {r.content_hash for r in results}

        assert HASH_A in hashes
        assert HASH_B in hashes
        assert HASH_C not in hashes

    def test_returns_sorted(self):
        """Results are sorted by content_hash."""
        save_bib_ground_truth(_bib_gt_with({HASH_B: [], HASH_A: []}))
        save_face_ground_truth(FaceGroundTruth())

        results = get_all_completeness()
        hashes = [r.content_hash for r in results]

        assert hashes == sorted(hashes)
