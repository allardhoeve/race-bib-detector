"""Tests for benchmarking.tuner (task-029)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from benchmarking.tuner import (
    _evaluate_single_combo,
    load_tune_config,
    print_sweep_results,
    run_face_sweep,
    validate_on_full,
)


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
    """Return a face backend that produces predictable detection results.

    For a 100x100 image with GT box at (0.1, 0.1, 0.2, 0.2) = pixels (10, 10, 20, 20):
    - tp boxes overlap the GT box (at pixel 10,10)
    - fp boxes are far from any GT box (at pixel 80,80)
    - fn is implicit (GT boxes not matched by any prediction)
    """
    from faces.types import FaceCandidate, FaceModelInfo
    from geometry import rect_to_bbox

    model = FaceModelInfo(name="stub", version="0", embedding_dim=0)

    class _StubBackend:
        def detect_face_candidates(self, image):
            candidates = []
            # TP: boxes that overlap the GT box
            for _ in range(tp):
                candidates.append(
                    FaceCandidate(
                        bbox=rect_to_bbox(10, 10, 20, 20),
                        confidence=0.9,
                        passed=True,
                        rejection_reason=None,
                        model=model,
                    )
                )
            # FP: boxes far from any GT box
            for _ in range(fp):
                candidates.append(
                    FaceCandidate(
                        bbox=rect_to_bbox(80, 80, 15, 15),
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


# =============================================================================
# _evaluate_single_combo
# =============================================================================


def _make_gt_fixtures(tmp_path):
    """Shared helper: create GT, index, and a dummy photo for one hash."""
    import cv2
    import numpy as np
    from benchmarking.ground_truth import (
        BibGroundTruth,
        BibPhotoLabel,
        FaceBox,
        FaceGroundTruth,
        FacePhotoLabel,
    )

    content_hash = "b" * 64
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img_path = tmp_path / "photo.jpg"
    cv2.imwrite(str(img_path), img)

    bib_gt = BibGroundTruth()
    bib_gt.photos[content_hash] = BibPhotoLabel(
        content_hash=content_hash, split="full"
    )

    face_gt = FaceGroundTruth()
    face_gt.add_photo(
        FacePhotoLabel(
            content_hash=content_hash,
            boxes=[FaceBox(x=0.1, y=0.1, w=0.2, h=0.2, scope="keep")],
        )
    )

    index = {content_hash: [str(img_path)]}
    return bib_gt, face_gt, index



def test_evaluate_single_combo_returns_metrics(tmp_path):
    """_evaluate_single_combo returns a dict with face_f1, face_precision, face_recall."""
    bib_gt, face_gt, index = _make_gt_fixtures(tmp_path)
    combo = {"FACE_DNN_CONFIDENCE_MIN": 0.3}

    with patch("benchmarking.tuner.load_bib_ground_truth", return_value=bib_gt), \
         patch("benchmarking.tuner.load_face_ground_truth", return_value=face_gt), \
         patch("benchmarking.tuner.load_photo_index", return_value=index), \
         patch("benchmarking.tuner.load_photo_metadata") as mock_meta, \
         patch("benchmarking.tuner.PHOTOS_DIR", tmp_path), \
         patch("benchmarking.tuner.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        mock_meta.return_value.get_hashes_by_split.return_value = list(index.keys())
        row = _evaluate_single_combo(combo, split="full", verbose=False)

    assert "face_f1" in row
    assert "face_precision" in row
    assert "face_recall" in row
    assert "FACE_DNN_CONFIDENCE_MIN" in row
    assert row["FACE_DNN_CONFIDENCE_MIN"] == 0.3



def test_evaluate_single_combo_preserves_param_values(tmp_path):
    """The returned row contains the exact param values from the combo."""
    bib_gt, face_gt, index = _make_gt_fixtures(tmp_path)
    combo = {"FACE_DNN_INPUT_SIZE": [500, 500], "FACE_DNN_CONFIDENCE_MIN": 0.25}

    with patch("benchmarking.tuner.load_bib_ground_truth", return_value=bib_gt), \
         patch("benchmarking.tuner.load_face_ground_truth", return_value=face_gt), \
         patch("benchmarking.tuner.load_photo_index", return_value=index), \
         patch("benchmarking.tuner.load_photo_metadata") as mock_meta, \
         patch("benchmarking.tuner.PHOTOS_DIR", tmp_path), \
         patch("benchmarking.tuner.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        mock_meta.return_value.get_hashes_by_split.return_value = list(index.keys())
        row = _evaluate_single_combo(combo, split="full", verbose=False)

    assert row["FACE_DNN_INPUT_SIZE"] == [500, 500]
    assert row["FACE_DNN_CONFIDENCE_MIN"] == 0.25


# =============================================================================
# validate_on_full
# =============================================================================



def test_validate_on_full_prints_comparison(tmp_path, capsys):
    """validate_on_full prints a table comparing defaults vs best on full split."""
    bib_gt, face_gt, index = _make_gt_fixtures(tmp_path)

    best_combo = {
        "FACE_DNN_CONFIDENCE_MIN": 0.25,
        "face_f1": 0.85,
        "face_precision": 0.80,
        "face_recall": 0.90,
    }

    with patch("benchmarking.tuner.load_bib_ground_truth", return_value=bib_gt), \
         patch("benchmarking.tuner.load_face_ground_truth", return_value=face_gt), \
         patch("benchmarking.tuner.load_photo_index", return_value=index), \
         patch("benchmarking.tuner.load_photo_metadata") as mock_meta, \
         patch("benchmarking.tuner.PHOTOS_DIR", tmp_path), \
         patch("benchmarking.tuner.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        mock_meta.return_value.get_hashes_by_split.return_value = list(index.keys())
        validate_on_full(best_combo, metric="face_f1")

    output = capsys.readouterr().out
    assert "VALIDATION ON FULL SPLIT" in output
    assert "Defaults" in output
    assert "Best" in output
    assert "Delta" in output



def test_validate_on_full_warns_on_overfitting(tmp_path, capsys):
    """When defaults beat the sweep winner on full, print an overfitting warning."""
    bib_gt, face_gt, index = _make_gt_fixtures(tmp_path)

    # The "best" combo that actually performs worse than defaults on full
    best_combo = {
        "FACE_DNN_CONFIDENCE_MIN": 0.1,
        "face_f1": 0.90,
        "face_precision": 0.85,
        "face_recall": 0.95,
    }

    call_count = 0

    def _side_effect(**kwargs):
        """First call (defaults) returns better backend, second (best) returns worse."""
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # defaults: good
            return _make_stub_backend(tp=1, fp=0, fn=0)
        else:
            # "best" from sweep: worse on full
            return _make_stub_backend(tp=0, fp=1, fn=1)

    with patch("benchmarking.tuner.load_bib_ground_truth", return_value=bib_gt), \
         patch("benchmarking.tuner.load_face_ground_truth", return_value=face_gt), \
         patch("benchmarking.tuner.load_photo_index", return_value=index), \
         patch("benchmarking.tuner.load_photo_metadata") as mock_meta, \
         patch("benchmarking.tuner.PHOTOS_DIR", tmp_path), \
         patch("benchmarking.tuner.get_face_backend_with_overrides",
               side_effect=_side_effect):
        mock_meta.return_value.get_hashes_by_split.return_value = list(index.keys())
        validate_on_full(best_combo, metric="face_f1")

    output = capsys.readouterr().out
    assert "overfitting" in output.lower()


# =============================================================================
# cmd_tune integration: auto-validation
# =============================================================================


def test_cmd_tune_calls_validate_when_not_full(tmp_path):
    """cmd_tune calls validate_on_full after sweep when split != 'full'."""
    from benchmarking.cli.commands.tune import cmd_tune

    cfg_file = tmp_path / "test.yaml"
    cfg_file.write_text(
        "params:\n"
        "  FACE_DNN_CONFIDENCE_MIN: [0.2, 0.3]\n"
        "split: iteration\n"
        "metric: face_f1\n"
    )

    fake_results = [
        {"FACE_DNN_CONFIDENCE_MIN": 0.2, "face_f1": 0.85, "face_precision": 0.80, "face_recall": 0.90},
        {"FACE_DNN_CONFIDENCE_MIN": 0.3, "face_f1": 0.83, "face_precision": 0.82, "face_recall": 0.84},
    ]

    args = MagicMock()
    args.config = str(cfg_file)
    args.params = None
    args.split = None
    args.metric = None
    args.quiet = False
    args.no_validate = False

    with patch("benchmarking.tuner.run_face_sweep", return_value=fake_results), \
         patch("benchmarking.tuner.print_sweep_results"), \
         patch("benchmarking.tuner.validate_on_full") as mock_validate:
        cmd_tune(args)

    mock_validate.assert_called_once_with(fake_results[0], metric="face_f1")


def test_cmd_tune_skips_validate_with_no_validate_flag(tmp_path):
    """cmd_tune does not validate when --no-validate is passed."""
    from benchmarking.cli.commands.tune import cmd_tune

    cfg_file = tmp_path / "test.yaml"
    cfg_file.write_text(
        "params:\n"
        "  FACE_DNN_CONFIDENCE_MIN: [0.2]\n"
        "split: iteration\n"
        "metric: face_f1\n"
    )

    fake_results = [
        {"FACE_DNN_CONFIDENCE_MIN": 0.2, "face_f1": 0.85, "face_precision": 0.80, "face_recall": 0.90},
    ]

    args = MagicMock()
    args.config = str(cfg_file)
    args.params = None
    args.split = None
    args.metric = None
    args.quiet = False
    args.no_validate = True

    with patch("benchmarking.tuner.run_face_sweep", return_value=fake_results), \
         patch("benchmarking.tuner.print_sweep_results"), \
         patch("benchmarking.tuner.validate_on_full") as mock_validate:
        cmd_tune(args)

    mock_validate.assert_not_called()


def test_cmd_tune_skips_validate_when_split_is_full(tmp_path):
    """cmd_tune does not validate when sweep already runs on full."""
    from benchmarking.cli.commands.tune import cmd_tune

    cfg_file = tmp_path / "test.yaml"
    cfg_file.write_text(
        "params:\n"
        "  FACE_DNN_CONFIDENCE_MIN: [0.2]\n"
        "split: full\n"
        "metric: face_f1\n"
    )

    fake_results = [
        {"FACE_DNN_CONFIDENCE_MIN": 0.2, "face_f1": 0.85, "face_precision": 0.80, "face_recall": 0.90},
    ]

    args = MagicMock()
    args.config = str(cfg_file)
    args.params = None
    args.split = None
    args.metric = None
    args.quiet = False
    args.no_validate = False

    with patch("benchmarking.tuner.run_face_sweep", return_value=fake_results), \
         patch("benchmarking.tuner.print_sweep_results"), \
         patch("benchmarking.tuner.validate_on_full") as mock_validate:
        cmd_tune(args)

    mock_validate.assert_not_called()
