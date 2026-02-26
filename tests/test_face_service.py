"""Unit tests for benchmarking.services.face_service."""

import pytest

from benchmarking.ground_truth import FacePhotoLabel, FaceBox, save_face_ground_truth, load_face_ground_truth
from benchmarking.photo_index import save_photo_index
from benchmarking.services import face_service

HASH_A = "a" * 64
HASH_UNKNOWN = "f" * 64


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    face_gt_path = tmp_path / "face_ground_truth.json"
    suggestions_path = tmp_path / "suggestions.json"
    index_path = tmp_path / "photo_index.json"
    save_photo_index({HASH_A: ["photo_a.jpg"]}, index_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path)
    monkeypatch.setattr("benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path)
    monkeypatch.setattr("benchmarking.photo_index.get_photo_index_path", lambda: index_path)


def test_get_face_label_not_found():
    result = face_service.get_face_label(HASH_UNKNOWN[:8])
    assert result is None


def test_save_face_label_empty_boxes():
    face_service.save_face_label(content_hash=HASH_A, boxes_data=None, tags=["no_faces"])
    result = face_service.get_face_label(HASH_A[:8])
    assert result is not None
    assert result["boxes"] == []
    assert result["tags"] == ["no_faces"]


def test_save_face_label_invalid_scope():
    with pytest.raises((ValueError, TypeError)):
        face_service.save_face_label(
            content_hash=HASH_A,
            boxes_data=[{"x": 0.1, "y": 0.2, "w": 0.1, "h": 0.1, "scope": "bad_scope"}],
            tags=[],
        )


def test_get_face_crop_jpeg_no_coords(tmp_path):
    """Box with has_coords=False (legacy) returns None."""
    face_gt = load_face_ground_truth()
    box = FaceBox(x=0, y=0, w=0, h=0, scope="keep")
    label = FacePhotoLabel(content_hash=HASH_A, boxes=[box], tags=[])
    face_gt.add_photo(label)
    save_face_ground_truth(face_gt)

    result = face_service.get_face_crop_jpeg(HASH_A[:8], 0)
    assert result is None
