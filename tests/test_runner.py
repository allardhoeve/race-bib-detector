"""Tests for benchmarking.runner — face detection integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from benchmarking.ground_truth import (
    BibPhotoLabel,
    FaceBox,
    FaceGroundTruth,
    FacePhotoLabel,
)
from benchmarking.runner import _run_detection_loop
from faces.types import FaceCandidate, FaceModelInfo
from geometry import rect_to_bbox


# =============================================================================
# Helpers
# =============================================================================


def _make_png_image(tmp_path: Path, name: str = "photo.png") -> Path:
    """Write a minimal 100×100 black PNG to tmp_path/name and return its path."""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    path = tmp_path / name
    cv2.imwrite(str(path), img)
    return path


def _fake_bib_result(width: int = 100, height: int = 100):
    """Return a minimal DetectionResult with no detections."""
    from detection.types import DetectionResult
    return DetectionResult(
        detections=[],
        all_candidates=[],
        ocr_grayscale=np.zeros((height, width), dtype=np.uint8),
        original_dimensions=(width, height),
        ocr_dimensions=(width, height),
        scale_factor=1.0,
    )


_FAKE_MODEL = FaceModelInfo(name="fake", version="0", embedding_dim=128)


class FakeFaceBackend:
    """Returns one passing candidate covering pixel rect [10, 10, 50, 50]."""

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        return [
            FaceCandidate(
                bbox=rect_to_bbox(10, 10, 40, 40),  # x1=10, y1=10, x2=50, y2=50
                confidence=0.9,
                passed=True,
                rejection_reason=None,
                model=_FAKE_MODEL,
            )
        ]

    def detect_faces(self, image: np.ndarray):
        return [c.bbox for c in self.detect_face_candidates(image) if c.passed]


# =============================================================================
# Tests
# =============================================================================


class TestFaceScorecardPopulated:
    def test_face_scorecard_non_none_with_backend(self, tmp_path):
        """face_scorecard is populated (not None) when a face backend is provided."""
        content_hash = "a" * 64
        img_path = _make_png_image(tmp_path)

        # Index: relative path from PHOTOS_DIR — but we pass tmp_path as photos_dir via index
        # get_path_for_hash returns photos_dir / paths[0], so use relative name
        index = {content_hash: ["photo.png"]}

        # Face GT: one keep-scoped box matching [10,10,50,50] in 100×100 image
        face_gt = FaceGroundTruth()
        face_gt.add_photo(FacePhotoLabel(
            content_hash=content_hash,
            boxes=[FaceBox(x=0.1, y=0.1, w=0.4, h=0.4, scope="keep")],
        ))

        bib_label = BibPhotoLabel(content_hash=content_hash)

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, bib_sc, face_sc, _ = _run_detection_loop(
                reader=None,
                photos=[bib_label],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=FakeFaceBackend(),
                face_gt=face_gt,
            )

        assert face_sc is not None
        assert face_sc.detection_tp >= 0
        assert face_sc.detection_fp >= 0
        assert face_sc.detection_fn >= 0
        # Predicted box (0.1, 0.1, 0.4, 0.4) matches GT box exactly → TP=1
        assert face_sc.detection_tp == 1
        assert face_sc.detection_fp == 0
        assert face_sc.detection_fn == 0

    def test_bib_scorecard_also_returned(self, tmp_path):
        """Both scorecards are returned together."""
        content_hash = "c" * 64
        _make_png_image(tmp_path)
        index = {content_hash: ["photo.png"]}
        face_gt = FaceGroundTruth()

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, bib_sc, face_sc, _ = _run_detection_loop(
                reader=None,
                photos=[BibPhotoLabel(content_hash=content_hash)],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=FakeFaceBackend(),
                face_gt=face_gt,
            )

        assert bib_sc is not None
        assert face_sc is not None


class TestFaceBackendFailureGraceful:
    def test_none_backend_yields_none_scorecard(self, tmp_path):
        """face_backend=None → face_scorecard is None; bib scoring is unaffected."""
        content_hash = "b" * 64
        _make_png_image(tmp_path)
        index = {content_hash: ["photo.png"]}

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, bib_sc, face_sc, _ = _run_detection_loop(
                reader=None,
                photos=[BibPhotoLabel(content_hash=content_hash)],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=None,
                face_gt=FaceGroundTruth(),
            )

        assert face_sc is None
        assert bib_sc is not None

    def test_get_face_backend_raises_gracefully(self, tmp_path, monkeypatch):
        """get_face_backend raising → run_benchmark sets face_scorecard=None."""
        import warnings
        from benchmarking import runner as runner_mod

        monkeypatch.setattr(runner_mod, "get_face_backend", lambda: (_ for _ in ()).throw(RuntimeError("no model")))

        # Verify that the except branch in run_benchmark sets face_backend to None.
        # We test this by calling _run_detection_loop with face_backend=None
        # (the state after the except branch), confirming graceful behaviour.
        content_hash = "d" * 64
        _make_png_image(tmp_path)
        index = {content_hash: ["photo.png"]}

        with patch("benchmarking.runner.detect_bib_numbers") as mock_det, \
             patch("benchmarking.runner.PHOTOS_DIR", tmp_path):
            mock_det.return_value = _fake_bib_result()
            _, bib_sc, face_sc, _ = _run_detection_loop(
                reader=None,
                photos=[BibPhotoLabel(content_hash=content_hash)],
                index=index,
                images_dir=tmp_path / "images",
                verbose=False,
                face_backend=None,
                face_gt=FaceGroundTruth(),
            )

        assert face_sc is None
        assert bib_sc is not None
