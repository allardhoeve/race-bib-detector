"""Tests for benchmarking/services/completion_service.py."""
from __future__ import annotations

import pytest

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    BibGroundTruth,
    FaceBox,
    FacePhotoLabel,
    FaceGroundTruth,
    LinkGroundTruth,
    save_bib_ground_truth,
    save_face_ground_truth,
    save_link_ground_truth,
)
from benchmarking.services.completion_service import get_link_ready_hashes, get_unlinked_hashes

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


@pytest.fixture(autouse=True)
def patch_paths(tmp_path, monkeypatch):
    bib_path = tmp_path / "bib_ground_truth.json"
    face_path = tmp_path / "face_ground_truth.json"
    link_path = tmp_path / "bib_face_links.json"
    index_path = tmp_path / "photo_index.json"
    monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_path)
    monkeypatch.setattr("benchmarking.photo_index.get_photo_index_path", lambda: index_path)


def _save_index(tmp_path, hashes: list[str]) -> None:
    import json
    index_path = tmp_path / "photo_index.json"
    index_path.write_text(json.dumps({h: [f"/photos/{h[:8]}.jpg"] for h in hashes}))


def _bib_label(h: str, labeled: bool = True) -> BibPhotoLabel:
    return BibPhotoLabel(content_hash=h, labeled=labeled)


def _face_label(h: str, labeled: bool = True) -> FacePhotoLabel:
    return FacePhotoLabel(content_hash=h, labeled=labeled)


class TestGetLinkReadyHashes:
    def test_requires_both_labeled(self, tmp_path):
        """Photo with only bib labeled is excluded."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=False))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == []

    def test_requires_face_labeled(self, tmp_path):
        """Photo with only face labeled is excluded."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=False))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == []

    def test_includes_when_both_done(self, tmp_path):
        """Photo with both bib and face labeled is included."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == [HASH_A]

    def test_mixed_set(self, tmp_path):
        """Only photos where both dimensions are labeled appear."""
        _save_index(tmp_path, [HASH_A, HASH_B, HASH_C])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_B, labeled=True))
        bib_gt.add_photo(_bib_label(HASH_C, labeled=False))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A, labeled=True))
        face_gt.add_photo(_face_label(HASH_B, labeled=False))
        face_gt.add_photo(_face_label(HASH_C, labeled=True))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)

        assert get_link_ready_hashes() == [HASH_A]


class TestGetUnlinkedHashes:
    def test_excludes_already_linked(self, tmp_path):
        """Photo already in link GT does not appear in unlinked list."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        link_gt = LinkGroundTruth()
        link_gt.set_links(HASH_A, [])
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(link_gt)

        assert get_unlinked_hashes() == []

    def test_includes_link_ready_without_links(self, tmp_path):
        """Link-ready photo with no link GT entry appears in unlinked list."""
        _save_index(tmp_path, [HASH_A])
        bib_gt = BibGroundTruth()
        bib_gt.add_photo(_bib_label(HASH_A))
        face_gt = FaceGroundTruth()
        face_gt.add_photo(_face_label(HASH_A))
        save_bib_ground_truth(bib_gt)
        save_face_ground_truth(face_gt)
        save_link_ground_truth(LinkGroundTruth())

        assert get_unlinked_hashes() == [HASH_A]
