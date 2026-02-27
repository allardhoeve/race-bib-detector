"""Tests for link scorecard in benchmarking.runner._run_detection_loop (task-031)."""

from __future__ import annotations

from unittest.mock import patch

import cv2
import numpy as np
import pytest

from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    FaceBox,
    FaceGroundTruth,
    FacePhotoLabel,
    LinkGroundTruth,
    BibFaceLink,
)
from benchmarking.runner import _run_detection_loop
from faces.types import FaceCandidate, FaceModelInfo
from geometry import rect_to_bbox


_FAKE_MODEL = FaceModelInfo(name="fake", version="0", embedding_dim=128)


def _make_png_image(tmp_path, name: str = "photo.png"):
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    path = tmp_path / name
    cv2.imwrite(str(path), img)
    return path


def _fake_bib_result(width: int = 100, height: int = 100):
    from detection.types import DetectionResult
    return DetectionResult(
        detections=[],
        all_candidates=[],
        ocr_grayscale=np.zeros((height, width), dtype=np.uint8),
        original_dimensions=(width, height),
        ocr_dimensions=(width, height),
        scale_factor=1.0,
    )


class FakeFaceBackend:
    """Detects one face covering pixel rect [10, 10, 50, 50] in a 100×100 image."""

    def detect_face_candidates(self, image):
        return [
            FaceCandidate(
                bbox=rect_to_bbox(10, 10, 40, 40),
                confidence=0.9,
                passed=True,
                rejection_reason=None,
                model=_FAKE_MODEL,
            )
        ]

    def detect_faces(self, image):
        return [c.bbox for c in self.detect_face_candidates(image) if c.passed]


class TestLinkScorecard:
    def test_link_scorecard_not_stub(self, tmp_path):
        """With 1 GT link present, link_scorecard.gt_link_count > 0."""
        content_hash = "a" * 64
        _make_png_image(tmp_path)
        index = {content_hash: ["photo.png"]}

        # One GT bib box and one GT face box
        bib_label = BibPhotoLabel(
            content_hash=content_hash,
            boxes=[BibBox(x=0.1, y=0.5, w=0.1, h=0.1, number="1")],
        )
        face_gt = FaceGroundTruth()
        face_gt.add_photo(FacePhotoLabel(
            content_hash=content_hash,
            boxes=[FaceBox(x=0.1, y=0.1, w=0.4, h=0.4, scope="keep")],
        ))
        link_gt = LinkGroundTruth()
        link_gt.set_links(content_hash, [BibFaceLink(bib_index=0, face_index=0)])

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, _, _, link_sc = _run_detection_loop(
                reader=None,
                photos=[bib_label],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=FakeFaceBackend(),
                face_gt=face_gt,
                link_gt=link_gt,
            )

        assert link_sc is not None
        assert link_sc.gt_link_count > 0
        assert link_sc.link_tp >= 0

    def test_link_scorecard_zero_when_no_gt_links(self, tmp_path):
        """Photo with no GT links → gt_link_count == 0."""
        content_hash = "b" * 64
        _make_png_image(tmp_path)
        index = {content_hash: ["photo.png"]}

        face_gt = FaceGroundTruth()
        face_gt.add_photo(FacePhotoLabel(
            content_hash=content_hash,
            boxes=[FaceBox(x=0.1, y=0.1, w=0.4, h=0.4, scope="keep")],
        ))
        link_gt = LinkGroundTruth()  # no links for this hash

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, _, _, link_sc = _run_detection_loop(
                reader=None,
                photos=[BibPhotoLabel(content_hash=content_hash)],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=FakeFaceBackend(),
                face_gt=face_gt,
                link_gt=link_gt,
            )

        assert link_sc is not None
        assert link_sc.gt_link_count == 0

    def test_link_scorecard_none_without_link_gt(self, tmp_path):
        """link_gt=None → link_scorecard is None (backward compat)."""
        content_hash = "c" * 64
        _make_png_image(tmp_path)
        index = {content_hash: ["photo.png"]}

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, _, _, link_sc = _run_detection_loop(
                reader=None,
                photos=[BibPhotoLabel(content_hash=content_hash)],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=None,
                face_gt=FaceGroundTruth(),
                link_gt=None,
            )

        assert link_sc is None
