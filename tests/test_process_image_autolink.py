"""Tests for autolink persistence in scan/pipeline.py:process_image()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

import db
from detection.types import Detection, DetectionResult
from faces.types import FaceCandidate, FaceModelInfo
from geometry import rect_to_bbox
from scan.persist import process_image


_FAKE_MODEL = FaceModelInfo(name="fake", version="0", embedding_dim=128)


def _make_png_bytes(width: int = 100, height: int = 100) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


class FakeFaceBackend:
    """Returns one passing candidate at [10,10,40,40]."""

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


class FakeEmbedder:
    def model_info(self):
        return _FAKE_MODEL

    def embed(self, image, bboxes):
        return [np.zeros(128, dtype=np.float32) for _ in bboxes]


def _bib_detect_fn(reader, image_data, artifact_dir=None):
    """Detect one bib at [10,50,30,20]."""
    det = Detection(
        bib_number="42",
        bbox=rect_to_bbox(10, 50, 30, 20),
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


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    connection = db.get_connection()
    yield connection
    connection.close()


class TestProcessImageAutolink:
    def test_autolink_persists_links_to_db(self, conn, tmp_path, monkeypatch):
        """process_image with both bibs and faces → links persisted in bib_face_links table."""
        cache_path = tmp_path / "photo.png"
        image_data = _make_png_bytes()
        with open(cache_path, "wb") as f:
            f.write(image_data)

        # Patch pipeline.run_single_photo's detect_fn
        from pipeline import run_single_photo as _orig
        from pipeline import SinglePhotoResult

        def patched_run_single_photo(image_data, **kwargs):
            kwargs["detect_fn"] = _bib_detect_fn
            return _orig(image_data, **kwargs)

        monkeypatch.setattr("scan.persist.run_single_photo", patched_run_single_photo)

        bibs_count, faces_count = process_image(
            reader="fake_reader",  # detect_fn injected via patched run_single_photo
            face_backend=FakeFaceBackend(),
            fallback_face_backend=None,
            face_embedder=FakeEmbedder(),
            conn=conn,
            photo_url="http://example.com/photo.jpg",
            thumbnail_url=None,
            album_id="test",
            image_data=image_data,
            cache_path=cache_path,
            skip_existing=False,
            run_bib_detection=True,
            run_face_detection=True,
        )

        assert bibs_count == 1
        assert faces_count == 1

        # Check links were persisted
        photo_id = db.get_photo_id_by_url(conn, "http://example.com/photo.jpg")
        assert photo_id is not None
        links = db.get_bib_face_links(conn, photo_id)
        assert len(links) == 1
        assert links[0]["provenance"] is not None
