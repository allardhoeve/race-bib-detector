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
            _, bib_sc, face_sc = _run_detection_loop(
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
            _, bib_sc, face_sc = _run_detection_loop(
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
            _, bib_sc, face_sc = _run_detection_loop(
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


# =============================================================================
# _run_bib_detection (task-035 TDD — red until helper is extracted)
# =============================================================================


class TestRunBibDetection:
    """Unit tests for the _run_bib_detection helper extracted from _run_detection_loop."""

    def test_detection_returns_normalised_boxes_and_dims(self, tmp_path):
        """Known detection -> correct PhotoResult, normalised BibBox, and dims."""
        from benchmarking.runner import _run_bib_detection
        from benchmarking.ground_truth import BibPhotoLabel, BibBox
        from detection.types import DetectionResult, Detection
        from geometry import rect_to_bbox as _rtb

        label = BibPhotoLabel(
            content_hash="e" * 64,
            boxes=[BibBox(x=0.0, y=0.0, w=0.1, h=0.1, number="42")],
        )
        fake_det = Detection(
            bib_number="42",
            bbox=_rtb(10, 10, 20, 20),  # pixel rect [10,10->30,30]
            confidence=0.9,
            source_candidate=None,
        )
        fake_result = DetectionResult(
            detections=[fake_det],
            all_candidates=[],
            ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
            original_dimensions=(100, 100),
            ocr_dimensions=(100, 100),
            scale_factor=1.0,
        )

        with patch("benchmarking.runner.detect_bib_numbers", return_value=fake_result):
            photo_result, pred_boxes, dims = _run_bib_detection(
                reader=None, image_data=b"fake", label=label, artifact_dir="/tmp/art"
            )

        assert 42 in photo_result.detected_bibs
        assert dims == (100, 100)
        assert len(pred_boxes) == 1
        # [10,10->30,30] in 100x100 -> x=0.1, y=0.1, w=0.2, h=0.2
        assert abs(pred_boxes[0].x - 0.1) < 1e-6
        assert abs(pred_boxes[0].w - 0.2) < 1e-6

    def test_no_detections_on_labeled_photo_is_miss(self):
        """No detections on a photo with expected bibs -> status MISS."""
        from benchmarking.runner import _run_bib_detection
        from benchmarking.ground_truth import BibPhotoLabel, BibBox

        label = BibPhotoLabel(
            content_hash="f" * 64,
            boxes=[BibBox(x=0.1, y=0.1, w=0.2, h=0.2, number="7")],
        )

        with patch("benchmarking.runner.detect_bib_numbers", return_value=_fake_bib_result()):
            photo_result, pred_boxes, _ = _run_bib_detection(
                reader=None, image_data=b"fake", label=label, artifact_dir="/tmp/art"
            )

        assert photo_result.status == "MISS"
        assert pred_boxes == []


# =============================================================================
# _run_face_detection (task-035 TDD — red until helper is extracted)
# =============================================================================


class TestRunFaceDetection:
    """Unit tests for the _run_face_detection helper extracted from _run_detection_loop."""

    def test_passed_candidates_normalised_correctly(self, tmp_path):
        """Passed face candidate -> FaceBox with correct normalised coords."""
        from benchmarking.runner import _run_face_detection

        image_data = _make_png_image(tmp_path).read_bytes()
        pred_boxes = _run_face_detection(FakeFaceBackend(), image_data)

        assert len(pred_boxes) == 1
        # FakeFaceBackend: rect_to_bbox(10,10,40,40) -> [10,10->50,50] in 100x100
        assert abs(pred_boxes[0].x - 0.1) < 1e-6
        assert abs(pred_boxes[0].y - 0.1) < 1e-6
        assert abs(pred_boxes[0].w - 0.4) < 1e-6
        assert abs(pred_boxes[0].h - 0.4) < 1e-6

    def test_corrupt_image_returns_empty_list(self):
        """Undecodable bytes -> returns [] without raising."""
        from benchmarking.runner import _run_face_detection
        assert _run_face_detection(FakeFaceBackend(), b"") == []

    def test_failed_candidates_excluded(self, tmp_path):
        """Candidates with passed=False are not included."""
        from benchmarking.runner import _run_face_detection

        class FailingBackend:
            def detect_face_candidates(self, image):
                return [FaceCandidate(
                    bbox=rect_to_bbox(10, 10, 40, 40),
                    confidence=0.3,
                    passed=False,
                    rejection_reason="low_confidence",
                    model=_FAKE_MODEL,
                )]

        image_data = _make_png_image(tmp_path).read_bytes()
        assert _run_face_detection(FailingBackend(), image_data) == []


# =============================================================================
# compute_photo_result — coverage audit (task-035)
# =============================================================================


class TestComputePhotoResult:
    def _label(self, bibs):
        from types import SimpleNamespace
        return SimpleNamespace(bibs=bibs, content_hash="a" * 64, tags=[])

    def test_all_correct_no_fp_is_pass(self):
        from benchmarking.runner import compute_photo_result
        r = compute_photo_result(self._label([42, 7]), [42, 7], 10.0)
        assert r.status == "PASS"

    def test_partial_match_is_partial(self):
        from benchmarking.runner import compute_photo_result
        r = compute_photo_result(self._label([42, 7]), [42], 10.0)
        assert r.status == "PARTIAL"
        assert r.tp == 1 and r.fn == 1 and r.fp == 0

    def test_zero_tp_with_expected_bibs_is_miss(self):
        from benchmarking.runner import compute_photo_result
        r = compute_photo_result(self._label([42]), [], 10.0)
        assert r.status == "MISS"

    def test_no_expected_no_detections_is_pass(self):
        from benchmarking.runner import compute_photo_result
        r = compute_photo_result(self._label([]), [], 10.0)
        assert r.status == "PASS"

    def test_no_expected_with_fp_is_partial(self):
        """False positives on a clean photo -> PARTIAL, not PASS."""
        from benchmarking.runner import compute_photo_result
        r = compute_photo_result(self._label([]), [99], 10.0)
        assert r.status == "PARTIAL"
        assert r.fp == 1


# =============================================================================
# compute_metrics — coverage audit (task-035)
# =============================================================================


class TestComputeMetrics:
    def _result(self, tp, fp, fn, status="PASS"):
        from benchmarking.runner import PhotoResult
        return PhotoResult(
            content_hash="a" * 64, expected_bibs=[], detected_bibs=[],
            tp=tp, fp=fp, fn=fn, status=status, detection_time_ms=1.0,
        )

    def test_all_pass_gives_perfect_metrics(self):
        from benchmarking.runner import compute_metrics
        m = compute_metrics([self._result(1, 0, 0), self._result(2, 0, 0)])
        assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0

    def test_mixed_aggregates_correctly(self):
        from benchmarking.runner import compute_metrics
        m = compute_metrics([self._result(3, 1, 2, "PARTIAL")])
        assert abs(m.precision - 0.75) < 1e-9
        assert abs(m.recall - 0.6) < 1e-9

    def test_all_zeros_no_division_error(self):
        from benchmarking.runner import compute_metrics
        m = compute_metrics([self._result(0, 0, 0)])
        assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0


# =============================================================================
# compare_to_baseline — coverage audit (task-035)
# =============================================================================


def _make_run_for_cmp(precision: float, recall: float):
    from benchmarking.runner import BenchmarkRun, BenchmarkMetrics, RunMetadata
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return BenchmarkRun(
        metadata=RunMetadata(
            run_id="t", timestamp="2025-01-01T00:00:00", split="full",
            git_commit="abc", git_dirty=False, python_version="3.14",
            package_versions={}, hostname="h", gpu_info=None,
            total_runtime_seconds=1.0,
        ),
        metrics=BenchmarkMetrics(
            total_photos=10, total_tp=5, total_fp=2, total_fn=3,
            precision=precision, recall=recall, f1=f1,
            pass_count=5, partial_count=3, miss_count=2,
        ),
        photo_results=[],
    )


class TestCompareToBaseline:
    def test_regressed_when_precision_drops(self, tmp_path, monkeypatch):
        import benchmarking.runner as r
        from benchmarking.runner import compare_to_baseline
        _make_run_for_cmp(0.9, 0.9).save(tmp_path / "b.json")
        monkeypatch.setattr(r, "BASELINE_PATH", tmp_path / "b.json")
        assert compare_to_baseline(_make_run_for_cmp(0.7, 0.9), 0.01)[0] == "REGRESSED"

    def test_improved_when_precision_rises(self, tmp_path, monkeypatch):
        import benchmarking.runner as r
        from benchmarking.runner import compare_to_baseline
        _make_run_for_cmp(0.7, 0.7).save(tmp_path / "b.json")
        monkeypatch.setattr(r, "BASELINE_PATH", tmp_path / "b.json")
        assert compare_to_baseline(_make_run_for_cmp(0.9, 0.7), 0.01)[0] == "IMPROVED"

    def test_no_change_within_tolerance(self, tmp_path, monkeypatch):
        import benchmarking.runner as r
        from benchmarking.runner import compare_to_baseline
        _make_run_for_cmp(0.8, 0.8).save(tmp_path / "b.json")
        monkeypatch.setattr(r, "BASELINE_PATH", tmp_path / "b.json")
        assert compare_to_baseline(_make_run_for_cmp(0.8005, 0.8005), 0.01)[0] == "NO_CHANGE"

    def test_regression_beats_improvement(self, tmp_path, monkeypatch):
        """Precision up, recall down beyond tolerance -> REGRESSED wins."""
        import benchmarking.runner as r
        from benchmarking.runner import compare_to_baseline
        _make_run_for_cmp(0.8, 0.8).save(tmp_path / "b.json")
        monkeypatch.setattr(r, "BASELINE_PATH", tmp_path / "b.json")
        assert compare_to_baseline(_make_run_for_cmp(0.95, 0.65), 0.01)[0] == "REGRESSED"

    def test_no_baseline_file_returns_no_change(self, tmp_path, monkeypatch):
        import benchmarking.runner as r
        from benchmarking.runner import compare_to_baseline
        monkeypatch.setattr(r, "BASELINE_PATH", tmp_path / "none.json")
        j, d = compare_to_baseline(_make_run_for_cmp(0.8, 0.8))
        assert j == "NO_CHANGE" and "reason" in d
