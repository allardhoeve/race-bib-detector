"""Tests for face artifact helpers."""

from pathlib import Path

import cv2
import numpy as np

from faces.artifacts import save_face_snippet, save_face_boxed_preview, save_face_evidence_json
from faces.types import FaceCandidate, FaceDetection, FaceModelInfo


def _make_image() -> np.ndarray:
    """Create a simple RGB test image."""
    image = np.zeros((20, 20, 3), dtype=np.uint8)
    image[:, :] = [255, 0, 0]  # Red
    return image


def test_save_face_snippet(tmp_path: Path) -> None:
    image = _make_image()
    bbox = [[5, 5], [10, 5], [10, 10], [5, 10]]
    output_path = tmp_path / "snippet.jpg"

    saved = save_face_snippet(image, bbox, output_path, padding_ratio=0.0)

    assert saved is True
    assert output_path.exists()

    loaded = cv2.imread(str(output_path))
    assert loaded is not None
    assert loaded.shape[0] > 0
    assert loaded.shape[1] > 0


def test_save_face_boxed_preview(tmp_path: Path) -> None:
    image = _make_image()
    bbox = [[2, 2], [8, 2], [8, 8], [2, 8]]
    output_path = tmp_path / "preview.jpg"

    saved = save_face_boxed_preview(image, bbox, output_path)

    assert saved is True
    assert output_path.exists()


def test_save_face_evidence_json(tmp_path: Path) -> None:
    output_path = tmp_path / "evidence.json"
    model = FaceModelInfo(name="test", version="1", embedding_dim=4)
    faces = [
        FaceDetection(
            face_index=0,
            bbox=[[1, 1], [2, 1], [2, 2], [1, 2]],
            embedding=None,
            model=model,
            snippet_path="snippet.jpg",
            preview_path="preview.jpg",
        )
    ]
    candidates = [
        FaceCandidate(
            bbox=[[1, 1], [2, 1], [2, 2], [1, 2]],
            confidence=0.42,
            passed=False,
            rejection_reason="confidence",
            model=model,
        )
    ]
    bibs = [{"bib_number": "123", "confidence": 0.9, "bbox": [[0, 0], [1, 0], [1, 1], [0, 1]]}]

    saved = save_face_evidence_json(output_path, "deadbeef", faces, bibs, candidates)

    assert saved is True
    assert output_path.exists()
