"""Tests for BibFaceLink / LinkGroundTruth schema."""

from __future__ import annotations

from benchmarking.ground_truth import (
    BibFaceLink,
    LinkGroundTruth,
    load_link_ground_truth,
    save_link_ground_truth,
)


def test_roundtrip_empty():
    gt = LinkGroundTruth()
    assert LinkGroundTruth.from_dict(gt.to_dict()).to_dict() == gt.to_dict()


def test_roundtrip_with_links():
    gt = LinkGroundTruth()
    gt.set_links("abc123", [BibFaceLink(0, 1), BibFaceLink(2, 0)])
    restored = LinkGroundTruth.from_dict(gt.to_dict())
    links = restored.get_links("abc123")
    assert len(links) == 2
    assert links[0].bib_index == 0 and links[0].face_index == 1
    assert links[1].bib_index == 2 and links[1].face_index == 0


def test_get_links_missing_hash():
    gt = LinkGroundTruth()
    assert gt.get_links("nonexistent") == []


def test_set_and_get_links():
    gt = LinkGroundTruth()
    links = [BibFaceLink(1, 3), BibFaceLink(0, 0)]
    gt.set_links("hash1", links)
    assert gt.get_links("hash1") == links


def test_load_missing_file(tmp_path):
    gt = load_link_ground_truth(tmp_path / "x.json")
    assert isinstance(gt, LinkGroundTruth)
    assert gt.photos == {}


def test_save_load_roundtrip(tmp_path):
    gt = LinkGroundTruth()
    gt.set_links("deadbeef", [BibFaceLink(0, 2)])
    path = tmp_path / "links.json"
    save_link_ground_truth(gt, path)
    loaded = load_link_ground_truth(path)
    assert loaded.to_dict() == gt.to_dict()
