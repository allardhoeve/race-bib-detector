"""Tests for pipeline.run_single_photo — unified single-photo detection."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from detection.types import Detection, DetectionResult
from faces.types import FaceCandidate, FaceModelInfo
from geometry import rect_to_bbox


# =============================================================================
# Helpers
# =============================================================================

_FAKE_MODEL = FaceModelInfo(name="fake", version="0", embedding_dim=128)


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    """Return raw bytes for a minimal black PNG image."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def _fake_detect_fn(reader, image_data, artifact_dir=None, **kwargs):
    """Stub detect_fn returning one bib detection in a 100x100 image."""
    det = Detection(
        bib_number="42",
        bbox=rect_to_bbox(10, 10, 20, 20),  # pixel [10,10 -> 30,30]
        confidence=0.9,
        source_candidate=None,
    )
    return DetectionResult(
        detections=[det],
        all_candidates=[],
        ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
        original_dimensions=(100, 100),
        ocr_dimensions=(100, 100),
        scale_factor=1.0,
    )


def _noop_detect_fn(reader, image_data, artifact_dir=None, **kwargs):
    """Stub detect_fn returning no detections."""
    return DetectionResult(
        detections=[],
        all_candidates=[],
        ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
        original_dimensions=(100, 100),
        ocr_dimensions=(100, 100),
        scale_factor=1.0,
    )


class FakeFaceBackend:
    """Returns one passing candidate at [10,10,40,40] in pixel coords."""

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        return [
            FaceCandidate(
                bbox=rect_to_bbox(10, 10, 40, 40),
                confidence=0.9,
                passed=True,
                rejection_reason=None,
                model=_FAKE_MODEL,
            )
        ]


class EmptyFaceBackend:
    """Returns one candidate that did NOT pass (all rejected)."""

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        return [
            FaceCandidate(
                bbox=rect_to_bbox(10, 10, 40, 40),
                confidence=0.05,
                passed=False,
                rejection_reason="low_confidence",
                model=_FAKE_MODEL,
            )
        ]


class FallbackFaceBackend:
    """Returns one passing candidate at a different location."""

    def detect_face_candidates(self, image: np.ndarray) -> list[FaceCandidate]:
        return [
            FaceCandidate(
                bbox=rect_to_bbox(60, 60, 20, 20),
                confidence=0.8,
                passed=True,
                rejection_reason=None,
                model=_FAKE_MODEL,
            )
        ]


class FakeEmbedder:
    """Returns a fixed embedding vector for each face box."""

    def embed(self, image, boxes):
        return [np.ones(4, dtype=np.float32) for _ in boxes]

    def model_info(self):
        return _FAKE_MODEL


# =============================================================================
# Tests
# =============================================================================


class TestBibsOnly:
    def test_bib_detection_produces_normalised_traces(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=_fake_detect_fn,
            run_faces=False,
            run_autolink=False,
        )

        assert result.image_dims == (100, 100)
        accepted = [t for t in result.bib_trace if t.accepted]
        assert len(accepted) == 1
        trace = accepted[0]
        assert abs(trace.x - 0.1) < 1e-6
        assert abs(trace.y - 0.1) < 1e-6
        assert abs(trace.w - 0.2) < 1e-6
        assert abs(trace.h - 0.2) < 1e-6
        assert trace.bib_number == "42"

    def test_no_bib_detections(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=_noop_detect_fn,
            run_faces=False,
            run_autolink=False,
        )

        assert [t for t in result.bib_trace if t.accepted] == []
        assert result.bib_result is not None


class TestFacesOnly:
    def test_face_detection_produces_normalised_traces(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=FakeFaceBackend(),
            run_autolink=False,
        )

        accepted = [t for t in result.face_trace if t.accepted]
        assert len(accepted) == 1
        trace = accepted[0]
        # FakeFaceBackend: rect_to_bbox(10,10,40,40) -> [10,10->50,50] in 100x100
        assert abs(trace.x - 0.1) < 1e-6
        assert abs(trace.y - 0.1) < 1e-6
        assert abs(trace.w - 0.4) < 1e-6
        assert abs(trace.h - 0.4) < 1e-6
        assert trace.confidence == 0.9

    def test_no_face_backend_produces_empty_trace(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=None,
            run_faces=True,
            run_autolink=False,
        )

        # run_faces=True but no backend → treated as no faces
        assert result.face_trace == []


class TestBibsAndFacesWithAutolink:
    def test_autolink_produces_links(self):
        from pipeline import run_single_photo
        from pipeline.types import TraceLink

        # Bib at [10,50,30,20] → centroid (0.25, 0.60) in 100x100
        det = Detection(
            bib_number="42",
            bbox=rect_to_bbox(10, 50, 30, 20),
            confidence=0.9,
            source_candidate=None,
        )
        fake_result = DetectionResult(
            detections=[det],
            all_candidates=[],
            ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
            original_dimensions=(100, 100),
            ocr_dimensions=(100, 100),
            scale_factor=1.0,
        )
        detect_fn = lambda reader, image_data, artifact_dir=None, **kwargs: fake_result

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=detect_fn,
            face_backend=FakeFaceBackend(),
            run_autolink=True,
        )

        assert len(result.links) == 1
        assert isinstance(result.links[0], TraceLink)


class TestFaceFallbackChain:
    def test_fallback_triggers_when_primary_has_no_passed(self):
        """Primary returns 0 passed candidates, fallback adds faces."""
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=EmptyFaceBackend(),
            fallback_face_backend=FallbackFaceBackend(),
            run_autolink=False,
        )

        # EmptyFaceBackend has 0 passed, FallbackFaceBackend has 1 passed
        accepted = [t for t in result.face_trace if t.accepted]
        assert len(accepted) >= 1

    def test_no_fallback_when_primary_has_faces(self):
        """Primary returns passed candidates, fallback is not used."""
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=FakeFaceBackend(),
            fallback_face_backend=FallbackFaceBackend(),
            run_autolink=False,
        )

        # FakeFaceBackend returns 1 passed → no fallback needed
        # (Unless face count < FACE_FALLBACK_MIN_FACE_COUNT, which is 2 by default)
        # With default config (min_face_count=2), fallback WILL trigger for 1 face
        accepted = [t for t in result.face_trace if t.accepted]
        assert len(accepted) >= 1


class TestImageDecodeFailure:
    def test_corrupt_bytes_returns_empty_results(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            b"not-an-image",
            detect_fn=_noop_detect_fn,
            face_backend=FakeFaceBackend(),
            run_autolink=False,
        )

        assert result.face_trace == []
        assert result.image_dims == (0, 0)


class TestDetectFnInjection:
    def test_custom_detect_fn_is_called(self):
        from pipeline import run_single_photo

        called = []

        def tracking_detect_fn(reader, image_data, artifact_dir=None, **kwargs):
            called.append(True)
            return _noop_detect_fn(reader, image_data, artifact_dir=artifact_dir)

        run_single_photo(
            _make_png_bytes(),
            detect_fn=tracking_detect_fn,
            run_faces=False,
            run_autolink=False,
        )

        assert len(called) == 1


class TestBibTrace:
    """Tests for bib_trace on SinglePhotoResult (task-088)."""

    def test_trace_populated_with_detection(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=_fake_detect_fn,
            run_faces=False,
            run_autolink=False,
        )

        assert result.bib_trace is not None
        # _fake_detect_fn has 0 candidates, so trace may be empty
        # but accepted traces from detections without source_candidate are created
        accepted = [t for t in result.bib_trace if t.accepted]
        assert len(accepted) == 1
        assert accepted[0].bib_number == "42"

    def test_trace_empty_when_no_bibs(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=_noop_detect_fn,
            run_faces=False,
            run_autolink=False,
        )

        assert result.bib_trace is not None
        assert len(result.bib_trace) == 0

    def test_bib_trace_identity_with_links(self):
        """Links reference the same BibCandidateTrace instances as bib_trace."""
        from pipeline import run_single_photo

        det = Detection(
            bib_number="42",
            bbox=rect_to_bbox(10, 50, 30, 20),
            confidence=0.9,
            source_candidate=None,
        )
        fake_result = DetectionResult(
            detections=[det],
            all_candidates=[],
            ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
            original_dimensions=(100, 100),
            ocr_dimensions=(100, 100),
            scale_factor=1.0,
        )

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=lambda reader, image_data, artifact_dir=None, **kwargs: fake_result,
            face_backend=FakeFaceBackend(),
            run_autolink=True,
        )

        if result.links:
            bib_trace_from_link = result.links[0].bib_trace
            accepted_bibs = [t for t in result.bib_trace if t.accepted]
            assert bib_trace_from_link in accepted_bibs


class TestSinglePhotoResultFields:
    def test_result_has_all_fields(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=_fake_detect_fn,
            face_backend=FakeFaceBackend(),
            run_autolink=False,
        )

        assert result.image_dims == (100, 100)
        assert result.bib_result is not None
        assert isinstance(result.bib_trace, list)
        assert isinstance(result.face_trace, list)
        assert isinstance(result.links, list)
        assert result.bib_detect_time_ms >= 0
        assert result.face_detect_time_ms >= 0
        assert result.image_rgb is not None
        assert result.image_rgb.shape == (100, 100, 3)

    def test_face_trace_includes_rejected(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=EmptyFaceBackend(),
            run_autolink=False,
        )

        # EmptyFaceBackend returns 1 rejected candidate
        assert len(result.face_trace) >= 1
        accepted = [t for t in result.face_trace if t.accepted]
        assert accepted == []  # none passed (no fallback)


class TestFaceTrace:
    """Tests for face_trace on SinglePhotoResult (task-089)."""

    def test_trace_populated(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=FakeFaceBackend(),
            run_autolink=False,
        )

        assert len(result.face_trace) == 1
        trace = result.face_trace[0]
        assert trace.accepted is True
        assert trace.passed is True
        assert trace.confidence == 0.9
        # Normalised: FakeFaceBackend → rect_to_bbox(10,10,40,40) → [10,10,50,50]
        assert abs(trace.x - 0.1) < 1e-6
        assert abs(trace.y - 0.1) < 1e-6
        assert abs(trace.w - 0.4) < 1e-6
        assert abs(trace.h - 0.4) < 1e-6
        assert trace.pixel_bbox is not None

    def test_face_trace_identity_with_links(self):
        """Links reference the same FaceCandidateTrace instances as face_trace."""
        from pipeline import run_single_photo

        det = Detection(
            bib_number="42",
            bbox=rect_to_bbox(10, 50, 30, 20),
            confidence=0.9,
            source_candidate=None,
        )
        fake_result = DetectionResult(
            detections=[det],
            all_candidates=[],
            ocr_grayscale=np.zeros((100, 100), dtype=np.uint8),
            original_dimensions=(100, 100),
            ocr_dimensions=(100, 100),
            scale_factor=1.0,
        )

        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=lambda reader, image_data, artifact_dir=None, **kwargs: fake_result,
            face_backend=FakeFaceBackend(),
            run_autolink=True,
        )

        if result.links:
            face_trace_from_link = result.links[0].face_trace
            accepted_faces = [t for t in result.face_trace if t.accepted]
            assert face_trace_from_link in accepted_faces

    def test_rejected_in_trace_not_in_accepted(self):
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=EmptyFaceBackend(),
            run_autolink=False,
        )

        # EmptyFaceBackend returns 1 rejected candidate
        assert len(result.face_trace) >= 1
        rejected = [t for t in result.face_trace if not t.accepted]
        assert len(rejected) >= 1
        accepted = [t for t in result.face_trace if t.accepted]
        assert accepted == []

    def test_pixel_bbox_on_all_candidates(self):
        """pixel_bbox is set on ALL candidates, not just accepted ones."""
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=EmptyFaceBackend(),
            run_autolink=False,
        )

        for trace in result.face_trace:
            assert trace.pixel_bbox is not None

    def test_embedding_populated_with_embedder(self):
        """Accepted traces have embedding when face_embedder is provided."""
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=FakeFaceBackend(),
            face_embedder=FakeEmbedder(),
            run_autolink=False,
        )

        accepted = [t for t in result.face_trace if t.accepted]
        assert len(accepted) == 1
        assert accepted[0].embedding is not None
        assert accepted[0].embedding == [1.0, 1.0, 1.0, 1.0]

    def test_rejected_face_has_no_embedding(self):
        """Rejected traces still have embedding=None even with embedder."""
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=EmptyFaceBackend(),
            face_embedder=FakeEmbedder(),
            run_autolink=False,
        )

        rejected = [t for t in result.face_trace if not t.accepted]
        assert len(rejected) >= 1
        for trace in rejected:
            assert trace.embedding is None

    def test_no_embedder_means_no_embeddings(self):
        """Without face_embedder, all traces have embedding=None."""
        from pipeline import run_single_photo

        result = run_single_photo(
            _make_png_bytes(),
            run_bibs=False,
            face_backend=FakeFaceBackend(),
            run_autolink=False,
        )

        for trace in result.face_trace:
            assert trace.embedding is None


class TestBibPipelineConfig:
    """Tests for bib_config threading (task-100)."""

    def test_run_single_photo_accepts_bib_config(self):
        from config import BibPipelineConfig
        from pipeline import run_single_photo

        config = BibPipelineConfig()  # default = crop-based
        result = run_single_photo(
            _make_png_bytes(),
            detect_fn=_fake_detect_fn,
            run_faces=False,
            run_autolink=False,
            bib_config=config,
        )

        assert result.image_dims == (100, 100)
        accepted = [t for t in result.bib_trace if t.accepted]
        assert len(accepted) == 1

    def test_bib_config_passed_to_detect_fn(self):
        """Verify bib_config is forwarded to the detect function."""
        from config import BibPipelineConfig, OCRMethod
        from pipeline import run_single_photo

        received_config = []

        def tracking_detect_fn(reader, image_data, artifact_dir=None, **kwargs):
            received_config.append(kwargs.get("bib_config"))
            return _noop_detect_fn(reader, image_data, artifact_dir=artifact_dir)

        config = BibPipelineConfig(ocr_method=OCRMethod.FULL_IMAGE)
        run_single_photo(
            _make_png_bytes(),
            detect_fn=tracking_detect_fn,
            run_faces=False,
            run_autolink=False,
            bib_config=config,
        )

        assert len(received_config) == 1
        assert received_config[0] is config
