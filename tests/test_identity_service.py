"""Unit tests for identity management in benchmarking.identities."""

import pytest

from benchmarking.ground_truth import FacePhotoLabel, FaceBox, save_face_ground_truth
from benchmarking.identities import (
    add_identity,
    load_identities,
    rename_identity_across_gt,
)

HASH_A = "a" * 64


@pytest.fixture(autouse=True)
def patch_paths(benchmark_paths):
    pass


def test_list_identities_empty():
    ids = load_identities()
    assert isinstance(ids, list)
    assert ids == []


def test_list_identities_after_create():
    add_identity("Alice")
    ids = load_identities()
    assert "Alice" in ids


def test_rename_identity_same_name():
    add_identity("Bob")
    with pytest.raises(ValueError, match="same"):
        rename_identity_across_gt("Bob", "Bob")


def test_rename_identity_updates_gt_boxes():
    add_identity("Alice")

    box = FaceBox(x=0.1, y=0.1, w=0.2, h=0.2, scope="keep", identity="Alice")
    label = FacePhotoLabel(content_hash=HASH_A, boxes=[box])
    face_gt_empty = __import__("benchmarking.ground_truth", fromlist=["load_face_ground_truth"]).load_face_ground_truth()
    face_gt_empty.add_photo(label)
    save_face_ground_truth(face_gt_empty)

    updated_count, ids = rename_identity_across_gt("Alice", "Alicia")
    assert updated_count == 1
    assert "Alicia" in ids
    assert "Alice" not in ids

    from benchmarking.ground_truth import load_face_ground_truth
    face_gt = load_face_ground_truth()
    saved_box = face_gt.get_photo(HASH_A).boxes[0]
    assert saved_box.identity == "Alicia"
