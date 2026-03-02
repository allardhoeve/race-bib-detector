"""Tests for benchmarking.tuners.grid (task-060, moved from test_tuner.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from benchmarking.tuners.grid import (
    GridTuner,
    TunerContext,
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
# Stub helpers
# =============================================================================

_PATCH_PREFIX = "benchmarking.tuners.grid"


def _make_stub_backend(tp: int = 1, fp: int = 0, fn: int = 0):
    """Return a face backend that produces predictable detection results."""
    from faces.types import FaceCandidate, FaceModelInfo
    from geometry import rect_to_bbox

    model = FaceModelInfo(name="stub", version="0", embedding_dim=0)

    class _StubBackend:
        def detect_face_candidates(self, image):
            candidates = []
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


def _make_tuner_context(tmp_path, *, split="full", content_hash=None):
    """Create a TunerContext with one photo for testing."""
    import cv2
    import numpy as np
    from benchmarking.ground_truth import (
        BibGroundTruth,
        BibPhotoLabel,
        FaceLabel,
        FaceGroundTruth,
        FacePhotoLabel,
    )
    from benchmarking.photo_metadata import PhotoMetadata, PhotoMetadataStore

    if content_hash is None:
        content_hash = "b" * 64
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img_path = tmp_path / "photo.jpg"
    cv2.imwrite(str(img_path), img)

    bib_gt = BibGroundTruth()
    bib_gt.photos[content_hash] = BibPhotoLabel(
        content_hash=content_hash, split=split
    )

    face_gt = FaceGroundTruth()
    face_gt.add_photo(
        FacePhotoLabel(
            content_hash=content_hash,
            boxes=[FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2, scope="keep")],
        )
    )

    index = {content_hash: [str(img_path)]}

    meta_store = PhotoMetadataStore()
    meta_store.set(content_hash, PhotoMetadata(split=split))

    return TunerContext(
        bib_gt=bib_gt,
        face_gt=face_gt,
        index=index,
        meta_store=meta_store,
        photos_dir=tmp_path,
    )


# =============================================================================
# GridTuner.tune — returns list[TunerResult]
# =============================================================================


def test_grid_tuner_tune_returns_tuner_results(tmp_path):
    """GridTuner.tune() returns a list of TunerResult objects."""
    from benchmarking.tuners.protocol import TunerResult

    ctx = _make_tuner_context(tmp_path, split="iteration")
    param_grid = {"FACE_DNN_CONFIDENCE_MIN": [0.2, 0.4]}

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1)):
        tuner = GridTuner(param_grid=param_grid)
        results = tuner.tune(split="iteration", metric="face_f1", verbose=False, ctx=ctx)

    assert len(results) == 2
    for r in results:
        assert isinstance(r, TunerResult)
        assert "FACE_DNN_CONFIDENCE_MIN" in r.params
        assert "face_f1" in r.metrics
    # sorted descending by metric
    assert results[0].metrics["face_f1"] >= results[1].metrics["face_f1"]


# =============================================================================
# run_face_sweep (legacy function, still available on GridTuner)
# =============================================================================


def test_face_sweep_returns_ranked_results(tmp_path):
    """Results are sorted descending by the target metric."""
    ctx = _make_tuner_context(tmp_path, split="iteration")
    param_grid = {"FACE_DNN_CONFIDENCE_MIN": [0.2, 0.4]}

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        results = run_face_sweep(
            param_grid=param_grid,
            split="iteration",
            metric="face_f1",
            verbose=False,
            ctx=ctx,
        )

    assert len(results) == 2
    f1_values = [r["face_f1"] for r in results]
    assert f1_values == sorted(f1_values, reverse=True)
    for row in results:
        assert "face_f1" in row
        assert "face_precision" in row
        assert "face_recall" in row
        assert "FACE_DNN_CONFIDENCE_MIN" in row


# =============================================================================
# _evaluate_single_combo
# =============================================================================


def test_evaluate_single_combo_returns_metrics(tmp_path):
    """_evaluate_single_combo returns a dict with face_f1, face_precision, face_recall."""
    ctx = _make_tuner_context(tmp_path)
    combo = {"FACE_DNN_CONFIDENCE_MIN": 0.3}

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        row = _evaluate_single_combo(combo, split="full", verbose=False, ctx=ctx)

    assert "face_f1" in row
    assert "face_precision" in row
    assert "face_recall" in row
    assert "FACE_DNN_CONFIDENCE_MIN" in row
    assert row["FACE_DNN_CONFIDENCE_MIN"] == 0.3


def test_evaluate_single_combo_preserves_param_values(tmp_path):
    """The returned row contains the exact param values from the combo."""
    ctx = _make_tuner_context(tmp_path)
    combo = {"FACE_DNN_INPUT_SIZE": [500, 500], "FACE_DNN_CONFIDENCE_MIN": 0.25}

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        row = _evaluate_single_combo(combo, split="full", verbose=False, ctx=ctx)

    assert row["FACE_DNN_INPUT_SIZE"] == [500, 500]
    assert row["FACE_DNN_CONFIDENCE_MIN"] == 0.25


# =============================================================================
# validate_on_full
# =============================================================================


def test_validate_on_full_prints_comparison(tmp_path, capsys):
    """validate_on_full prints a table comparing defaults vs best on full split."""
    ctx = _make_tuner_context(tmp_path)

    best_combo = {
        "FACE_DNN_CONFIDENCE_MIN": 0.25,
        "face_f1": 0.85,
        "face_precision": 0.80,
        "face_recall": 0.90,
    }

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1, fp=0, fn=0)):
        validate_on_full(best_combo, metric="face_f1", ctx=ctx)

    output = capsys.readouterr().out
    assert "VALIDATION ON FULL SPLIT" in output
    assert "Defaults" in output
    assert "Best" in output
    assert "Delta" in output


def test_validate_on_full_warns_on_overfitting(tmp_path, capsys):
    """When defaults beat the sweep winner on full, print an overfitting warning."""
    ctx = _make_tuner_context(tmp_path)

    best_combo = {
        "FACE_DNN_CONFIDENCE_MIN": 0.1,
        "face_f1": 0.90,
        "face_precision": 0.85,
        "face_recall": 0.95,
    }

    call_count = 0

    def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_stub_backend(tp=1, fp=0, fn=0)
        else:
            return _make_stub_backend(tp=0, fp=1, fn=1)

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               side_effect=_side_effect):
        validate_on_full(best_combo, metric="face_f1", ctx=ctx)

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
    args.frozen_set = None

    with patch(f"{_PATCH_PREFIX}.run_face_sweep", return_value=fake_results), \
         patch(f"{_PATCH_PREFIX}.print_sweep_results"), \
         patch(f"{_PATCH_PREFIX}.validate_on_full") as mock_validate:
        cmd_tune(args)

    mock_validate.assert_called_once_with(fake_results[0], metric="face_f1", frozen_set=None)


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
    args.frozen_set = None

    with patch(f"{_PATCH_PREFIX}.run_face_sweep", return_value=fake_results), \
         patch(f"{_PATCH_PREFIX}.print_sweep_results"), \
         patch(f"{_PATCH_PREFIX}.validate_on_full") as mock_validate:
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
    args.frozen_set = None

    with patch(f"{_PATCH_PREFIX}.run_face_sweep", return_value=fake_results), \
         patch(f"{_PATCH_PREFIX}.print_sweep_results"), \
         patch(f"{_PATCH_PREFIX}.validate_on_full") as mock_validate:
        cmd_tune(args)

    mock_validate.assert_not_called()


# =============================================================================
# frozen_set filtering
# =============================================================================


def test_run_face_sweep_filters_by_frozen_set(tmp_path):
    """run_face_sweep with frozen_set only evaluates photos in that set."""
    import cv2
    import numpy as np
    from benchmarking.ground_truth import (
        BibGroundTruth,
        BibPhotoLabel,
        FaceLabel,
        FaceGroundTruth,
        FacePhotoLabel,
    )
    from benchmarking.photo_metadata import PhotoMetadata, PhotoMetadataStore

    hash_in = "a" * 64
    hash_out = "c" * 64
    img = np.zeros((100, 100, 3), dtype=np.uint8)

    img_in = tmp_path / "in.jpg"
    img_out = tmp_path / "out.jpg"
    cv2.imwrite(str(img_in), img)
    cv2.imwrite(str(img_out), img)

    bib_gt = BibGroundTruth()
    bib_gt.photos[hash_in] = BibPhotoLabel(content_hash=hash_in, split="iteration")
    bib_gt.photos[hash_out] = BibPhotoLabel(content_hash=hash_out, split="iteration")

    face_gt = FaceGroundTruth()
    for h in (hash_in, hash_out):
        face_gt.add_photo(
            FacePhotoLabel(content_hash=h, boxes=[FaceLabel(x=0.1, y=0.1, w=0.2, h=0.2, scope="keep")])
        )

    index = {hash_in: [str(img_in)], hash_out: [str(img_out)]}

    meta_store = PhotoMetadataStore()
    meta_store.set(hash_in, PhotoMetadata(split="iteration"))
    meta_store.set(hash_out, PhotoMetadata(split="iteration"))

    ctx = TunerContext(
        bib_gt=bib_gt,
        face_gt=face_gt,
        index=index,
        meta_store=meta_store,
        photos_dir=tmp_path,
    )

    mock_snapshot = MagicMock()
    mock_snapshot.hashes = [hash_in]

    detected_hashes = []
    real_backend = _make_stub_backend(tp=1)

    class _TrackingBackend:
        def detect_face_candidates(self, image):
            detected_hashes.append("called")
            return real_backend.detect_face_candidates(image)

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_TrackingBackend()), \
         patch("benchmarking.sets.BenchmarkSnapshot") as mock_snap_cls:
        mock_snap_cls.load.return_value = mock_snapshot
        results = run_face_sweep(
            param_grid={"FACE_DNN_CONFIDENCE_MIN": [0.3]},
            split="iteration",
            frozen_set="test-set",
            metric="face_f1",
            verbose=False,
            ctx=ctx,
        )

    assert len(detected_hashes) == 1
    assert len(results) == 1


def test_evaluate_single_combo_filters_by_frozen_set(tmp_path):
    """_evaluate_single_combo with frozen_set only evaluates photos in that set."""
    ctx = _make_tuner_context(tmp_path)
    content_hash = list(ctx.index.keys())[0]

    mock_snapshot = MagicMock()
    mock_snapshot.hashes = [content_hash]

    with patch(f"{_PATCH_PREFIX}.get_face_backend_with_overrides",
               return_value=_make_stub_backend(tp=1)), \
         patch("benchmarking.sets.BenchmarkSnapshot") as mock_snap_cls:
        mock_snap_cls.load.return_value = mock_snapshot
        row = _evaluate_single_combo(
            {"FACE_DNN_CONFIDENCE_MIN": 0.3},
            split="full",
            frozen_set="test-set",
            verbose=False,
            ctx=ctx,
        )

    assert "face_f1" in row
    mock_snap_cls.load.assert_called_once_with("test-set")


def test_validate_on_full_passes_frozen_set(tmp_path, capsys):
    """validate_on_full forwards frozen_set to _evaluate_single_combo."""
    best_combo = {
        "FACE_DNN_CONFIDENCE_MIN": 0.25,
        "face_f1": 0.85,
        "face_precision": 0.80,
        "face_recall": 0.90,
    }

    with patch(f"{_PATCH_PREFIX}._evaluate_single_combo") as mock_eval:
        mock_eval.return_value = {"face_f1": 0.85, "face_precision": 0.80, "face_recall": 0.90}
        validate_on_full(best_combo, metric="face_f1", frozen_set="jeugd-1")

    for call in mock_eval.call_args_list:
        assert call.kwargs.get("frozen_set") == "jeugd-1"


def test_cmd_tune_passes_frozen_set_to_sweep_and_validate(tmp_path):
    """cmd_tune forwards --set to both run_face_sweep and validate_on_full."""
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
    args.no_validate = False
    args.frozen_set = "jeugd-1"

    with patch(f"{_PATCH_PREFIX}.run_face_sweep", return_value=fake_results) as mock_sweep, \
         patch(f"{_PATCH_PREFIX}.print_sweep_results"), \
         patch(f"{_PATCH_PREFIX}.validate_on_full") as mock_validate:
        cmd_tune(args)

    assert mock_sweep.call_args.kwargs.get("frozen_set") == "jeugd-1"
    assert mock_validate.call_args.kwargs.get("frozen_set") == "jeugd-1"
