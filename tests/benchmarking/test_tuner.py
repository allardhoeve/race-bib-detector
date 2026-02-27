"""Tests for benchmarking.tuner (task-029)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from benchmarking.tuner import load_tune_config, print_sweep_results, run_face_sweep


# =============================================================================
# load_tune_config
# =============================================================================


def test_load_tune_config_valid(tmp_path):
    """Valid YAML produces a dict with param_grid, split, and metric."""
    cfg_file = tmp_path / "test.yaml"
    cfg_file.write_text(
        "params:\n"
        "  FACE_DNN_CONFIDENCE_MIN: [0.2, 0.3]\n"
        "split: iteration\n"
        "metric: face_f1\n"
    )
    cfg = load_tune_config(cfg_file)
    assert "param_grid" in cfg
    assert cfg["param_grid"]["FACE_DNN_CONFIDENCE_MIN"] == [0.2, 0.3]
    assert cfg["split"] == "iteration"
    assert cfg["metric"] == "face_f1"


def test_load_tune_config_missing_params(tmp_path):
    """YAML without 'params' key raises ValueError."""
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text("split: iteration\nmetric: face_f1\n")
    with pytest.raises(ValueError, match="params"):
        load_tune_config(cfg_file)


# =============================================================================
# run_face_sweep
# =============================================================================


def _make_stub_backend(tp: int = 1, fp: int = 0, fn: int = 0):
    """Return a face backend that always reports fixed detection counts."""
    from faces.types import FaceCandidate, FaceModelInfo
    from geometry import rect_to_bbox

    model = FaceModelInfo(name="stub", version="0", embedding_dim=0)

    class _StubBackend:
        def detect_face_candidates(self, image):
            candidates = []
            for _ in range(tp + fp):
                candidates.append(
                    FaceCandidate(
                        bbox=rect_to_bbox(10, 10, 20, 20),
                        confidence=0.9,
                        passed=True,
                        rejection_reason=None,
                        model=model,
                    )
                )
            return candidates

        def detect_faces(self, image):
            return [c.bbox for c in self.detect_face_candidates(image) if c.passed]

    return _StubBackend()


def test_face_sweep_returns_ranked_results(tmp_path):
    """Results are sorted descending by the target metric."""
    import cv2
    import numpy as np
    from benchmarking.ground_truth import (
        BibGroundTruth,
        BibPhotoLabel,
        FaceBox,
        FaceGroundTruth,
        FacePhotoLabel,
    )

    content_hash = "a" * 64
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img_path = tmp_path / "photo.jpg"
    cv2.imwrite(str(img_path), img)

    bib_gt = BibGroundTruth()
    bib_gt.photos[content_hash] = BibPhotoLabel(
        content_hash=content_hash, split="iteration"
    )

    face_gt = FaceGroundTruth()
    face_gt.add_photo(
        FacePhotoLabel(
            content_hash=content_hash,
            boxes=[FaceBox(x=0.1, y=0.1, w=0.2, h=0.2, scope="keep")],
        )
    )

    index = {content_hash: [str(img_path)]}

    # Two combos with different confidence_min → stub always returns the same
    # number of detections, so scores will be equal (both rank as "best").
    # What matters is that results are sorted and have the correct keys.
    param_grid = {"FACE_DNN_CONFIDENCE_MIN": [0.2, 0.4]}

    with patch("benchmarking.tuner.load_bib_ground_truth", return_value=bib_gt), \
         patch("benchmarking.tuner.load_face_ground_truth", return_value=face_gt), \
         patch("benchmarking.tuner.load_photo_index", return_value=index), \
         patch("benchmarking.tuner.PHOTOS_DIR", tmp_path), \
         patch("benchmarking.tuner.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        results = run_face_sweep(
            param_grid=param_grid,
            split="iteration",
            metric="face_f1",
            verbose=False,
        )

    assert len(results) == 2
    # Sorted descending by face_f1
    f1_values = [r["face_f1"] for r in results]
    assert f1_values == sorted(f1_values, reverse=True)
    # Each row has the expected metric keys
    for row in results:
        assert "face_f1" in row
        assert "face_precision" in row
        assert "face_recall" in row
        assert "FACE_DNN_CONFIDENCE_MIN" in row
