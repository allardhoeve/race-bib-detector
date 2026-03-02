"""Grid-sweep tuner for face detection parameters (task-029, task-060).

Usage::

    from benchmarking.tuners.grid import GridTuner, load_tune_config, print_sweep_results

    cfg = load_tune_config(Path("benchmarking/tune_configs/face_default.yaml"))
    results = GridTuner(cfg["param_grid"]).tune(split=cfg["split"], metric=cfg["metric"])
    print_sweep_results(results, metric=cfg["metric"])
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from benchmarking.ground_truth import (
    BibGroundTruth,
    BibPhotoLabel,
    FaceBox,
    FaceGroundTruth,
    load_bib_ground_truth,
    load_face_ground_truth,
)
from benchmarking.photo_index import get_path_for_hash, load_photo_index
from benchmarking.photo_metadata import PhotoMetadataStore, load_photo_metadata
from benchmarking.scoring import FaceScorecard, score_faces
from benchmarking.tuners.protocol import TunerResult
from faces.backend import get_face_backend_with_overrides
from geometry import bbox_to_rect

logger = logging.getLogger(__name__)

# Map from config-level YAML parameter names to OpenCVDnnSsdFaceBackend field names.
_PARAM_TO_BACKEND_KWARG: dict[str, str] = {
    "FACE_DNN_INPUT_SIZE": "input_size",
    "FACE_DNN_CONFIDENCE_MIN": "confidence_min",
    "FACE_DNN_NMS_IOU": "nms_iou",
    "FACE_DNN_FALLBACK_CONFIDENCE_MIN": "fallback_confidence_min",
    "FACE_DETECTION_MIN_NEIGHBORS": "min_neighbors",
    "FACE_DETECTION_SCALE_FACTOR": "scale_factor",
    "FACE_DETECTION_MIN_SIZE": "min_size",
}

PHOTOS_DIR = Path(__file__).parent.parent.parent / "photos"


@dataclass
class TunerContext:
    """Pre-loaded data for tuner functions, eliminating repeated I/O."""

    bib_gt: BibGroundTruth
    face_gt: FaceGroundTruth
    index: dict
    meta_store: PhotoMetadataStore
    photos_dir: Path


def _load_context() -> TunerContext:
    """Load all data needed by tuner functions from disk."""
    return TunerContext(
        bib_gt=load_bib_ground_truth(),
        face_gt=load_face_ground_truth(),
        index=load_photo_index(),
        meta_store=load_photo_metadata(),
        photos_dir=PHOTOS_DIR,
    )


def _select_hashes(
    split: str,
    meta_store,
    frozen_set: str | None,
) -> list[str]:
    """Choose which photo hashes to evaluate, respecting frozen set and split."""
    if frozen_set is not None:
        from benchmarking.sets import BenchmarkSnapshot
        snapshot = BenchmarkSnapshot.load(frozen_set)
        if split == "full":
            return list(snapshot.hashes)
        allowed = set(meta_store.get_hashes_by_split(split))
        return [h for h in snapshot.hashes if h in allowed]
    return meta_store.get_hashes_by_split(split)


def load_tune_config(path: Path) -> dict:
    """Parse a YAML tune config file.

    Expected format::

        params:
          FACE_DNN_CONFIDENCE_MIN: [0.2, 0.3]
          FACE_DNN_NMS_IOU: [0.3, 0.4]
        split: iteration
        metric: face_f1

    Args:
        path: Path to the YAML config file.

    Returns:
        Dict with keys ``params``, ``split``, and ``metric``.

    Raises:
        ValueError: If the ``params`` key is missing.
    """
    import yaml  # type: ignore[import-untyped]

    with open(path) as f:
        data = yaml.safe_load(f)

    if "params" not in data:
        raise ValueError(f"Tune config {path} is missing required 'params' key")

    return {
        "param_grid": data["params"],
        "split": data.get("split", "iteration"),
        "metric": data.get("metric", "face_f1"),
    }


class GridTuner:
    """Exhaustive grid sweep over face detection parameters."""

    def __init__(self, param_grid: dict[str, list]) -> None:
        self.param_grid = param_grid

    def tune(
        self,
        *,
        split: str = "iteration",
        metric: str = "face_f1",
        verbose: bool = True,
        ctx: TunerContext | None = None,
    ) -> list[TunerResult]:
        """Run the grid sweep and return ranked TunerResult objects."""
        raw = run_face_sweep(
            param_grid=self.param_grid,
            split=split,
            metric=metric,
            verbose=verbose,
            ctx=ctx,
        )
        metric_keys = {"face_f1", "face_precision", "face_recall"}
        results = []
        for row in raw:
            params = {k: v for k, v in row.items() if k not in metric_keys}
            metrics = {k: v for k, v in row.items() if k in metric_keys}
            results.append(TunerResult(params=params, metrics=metrics))
        return results


def run_face_sweep(
    param_grid: dict[str, list],
    split: str = "iteration",
    metric: str = "face_f1",
    verbose: bool = True,
    frozen_set: str | None = None,
    ctx: TunerContext | None = None,
) -> list[dict]:
    """Sweep face detection parameters and return ranked results.

    Iterates over the cartesian product of ``param_grid`` values.  For each
    combination a fresh face backend is instantiated (via
    :func:`~faces.backend.get_face_backend_with_overrides`), face detection is
    run on all photos in ``split``, and the resulting
    :class:`~benchmarking.scoring.FaceScorecard` is recorded.

    Args:
        param_grid: Mapping of config-level parameter names to lists of values,
            e.g. ``{"FACE_DNN_CONFIDENCE_MIN": [0.2, 0.3]}``.
        split: Photo split to evaluate on (``"iteration"`` or ``"full"``).
        metric: Metric to sort by (``"face_f1"``, ``"face_recall"``,
            ``"face_precision"``).
        verbose: Log progress to the logger.
        frozen_set: Optional frozen set name to restrict photos to.
        ctx: Pre-loaded data context. Loaded from disk when ``None``.

    Returns:
        List of result dicts sorted descending by ``metric``.  Each dict
        contains the parameter combination plus ``face_f1``,
        ``face_precision``, and ``face_recall``.
    """
    if ctx is None:
        ctx = _load_context()
    split_hashes = _select_hashes(split, ctx.meta_store, frozen_set)
    photos = [ctx.bib_gt.get_photo(h) or BibPhotoLabel(content_hash=h) for h in split_hashes if ctx.bib_gt.has_photo(h) or h in ctx.index]

    param_names = list(param_grid.keys())
    value_lists = [param_grid[name] for name in param_names]

    results: list[dict] = []

    combos = list(itertools.product(*value_lists))
    if verbose:
        logger.info("Face sweep: %d combinations × %d photos", len(combos), len(photos))

    for combo_values in combos:
        combo = dict(zip(param_names, combo_values))
        backend_kwargs = {
            _PARAM_TO_BACKEND_KWARG.get(k, k): v for k, v in combo.items()
        }
        try:
            backend = get_face_backend_with_overrides(**backend_kwargs)
        except (ValueError, RuntimeError) as exc:
            logger.warning("Skipping combo %s: %s", combo, exc)
            continue

        det_tp = det_fp = det_fn = 0
        for label in photos:
            path = get_path_for_hash(label.content_hash, ctx.photos_dir, ctx.index)
            if not path or not path.exists():
                continue
            image_data = path.read_bytes()
            img_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            if img_array is None:
                continue
            image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            face_h, face_w = image_rgb.shape[:2]

            face_label = ctx.face_gt.get_photo(label.content_hash)
            gt_face_boxes = face_label.boxes if face_label else []

            candidates = backend.detect_face_candidates(image_rgb)
            pred_face_boxes: list[FaceBox] = []
            for cand in candidates:
                if not cand.passed:
                    continue
                x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
                pred_face_boxes.append(FaceBox(
                    x=x1 / face_w, y=y1 / face_h,
                    w=(x2 - x1) / face_w, h=(y2 - y1) / face_h,
                ))

            sc = score_faces(pred_face_boxes, gt_face_boxes)
            det_tp += sc.detection_tp
            det_fp += sc.detection_fp
            det_fn += sc.detection_fn

        scorecard = FaceScorecard(
            detection_tp=det_tp,
            detection_fp=det_fp,
            detection_fn=det_fn,
        )
        row = dict(combo)
        row["face_f1"] = scorecard.detection_f1
        row["face_precision"] = scorecard.detection_precision
        row["face_recall"] = scorecard.detection_recall
        results.append(row)

        if verbose:
            logger.info(
                "  %s → f1=%.1f%% P=%.1f%% R=%.1f%%",
                combo, scorecard.detection_f1 * 100,
                scorecard.detection_precision * 100,
                scorecard.detection_recall * 100,
            )

    metric_key = metric.replace("face_", "face_")  # keep as-is
    results.sort(key=lambda r: r.get(metric_key, 0.0), reverse=True)
    return results


def _evaluate_single_combo(
    combo: dict[str, object],
    split: str,
    verbose: bool = True,
    frozen_set: str | None = None,
    ctx: TunerContext | None = None,
) -> dict:
    """Evaluate a single parameter combination on a split and return a result row."""
    if ctx is None:
        ctx = _load_context()
    split_hashes = _select_hashes(split, ctx.meta_store, frozen_set)
    photos = [ctx.bib_gt.get_photo(h) or BibPhotoLabel(content_hash=h) for h in split_hashes if ctx.bib_gt.has_photo(h) or h in ctx.index]

    backend_kwargs = {
        _PARAM_TO_BACKEND_KWARG.get(k, k): v for k, v in combo.items()
    }
    backend = get_face_backend_with_overrides(**backend_kwargs)

    det_tp = det_fp = det_fn = 0
    for label in photos:
        path = get_path_for_hash(label.content_hash, ctx.photos_dir, ctx.index)
        if not path or not path.exists():
            continue
        image_data = path.read_bytes()
        img_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        if img_array is None:
            continue
        image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        face_h, face_w = image_rgb.shape[:2]

        face_label = ctx.face_gt.get_photo(label.content_hash)
        gt_face_boxes = face_label.boxes if face_label else []

        candidates = backend.detect_face_candidates(image_rgb)
        pred_face_boxes: list[FaceBox] = []
        for cand in candidates:
            if not cand.passed:
                continue
            x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
            pred_face_boxes.append(FaceBox(
                x=x1 / face_w, y=y1 / face_h,
                w=(x2 - x1) / face_w, h=(y2 - y1) / face_h,
            ))

        sc = score_faces(pred_face_boxes, gt_face_boxes)
        det_tp += sc.detection_tp
        det_fp += sc.detection_fp
        det_fn += sc.detection_fn

    scorecard = FaceScorecard(
        detection_tp=det_tp,
        detection_fp=det_fp,
        detection_fn=det_fn,
    )
    row = dict(combo)
    row["face_f1"] = scorecard.detection_f1
    row["face_precision"] = scorecard.detection_precision
    row["face_recall"] = scorecard.detection_recall

    if verbose:
        logger.info(
            "  %s → f1=%.1f%% P=%.1f%% R=%.1f%% (%d photos)",
            combo, scorecard.detection_f1 * 100,
            scorecard.detection_precision * 100,
            scorecard.detection_recall * 100,
            len(photos),
        )

    return row


def print_sweep_results(results: list[dict], metric: str = "face_f1") -> None:
    """Print a ranked sweep results table to stdout.

    Args:
        results: List of result dicts as returned by :func:`run_face_sweep`.
        metric: Metric column to highlight (must be present in each row).
    """
    if not results:
        print("No sweep results.")
        return

    param_names = [k for k in results[0] if k not in ("face_f1", "face_precision", "face_recall")]

    # Build header
    col_width = max(len(n) for n in param_names) if param_names else 10
    header_parts = ["Rank"]
    for name in param_names:
        header_parts.append(f"{name:<{col_width}}")
    header_parts += ["face_f1", "face_P ", "face_R "]
    print("  ".join(header_parts))
    print("-" * (sum(len(p) for p in header_parts) + 2 * len(header_parts)))

    for rank, row in enumerate(results, 1):
        parts = [f"{rank:>4}"]
        for name in param_names:
            parts.append(f"{row[name]!s:<{col_width}}")
        parts.append(f"{row['face_f1']:.1%}  ")
        parts.append(f"{row['face_precision']:.1%}  ")
        parts.append(f"{row['face_recall']:.1%}")
        print("  ".join(parts))

    if results:
        best = results[0]
        best_params = ", ".join(f"{k}={best[k]}" for k in param_names)
        print(f"\nBest: {best_params}  ({metric}={best.get(metric, 0):.1%})")


def validate_on_full(
    best_combo: dict[str, object],
    metric: str = "face_f1",
    frozen_set: str | None = None,
    ctx: TunerContext | None = None,
) -> None:
    """Run the best combo and current defaults on the full split, print comparison."""
    import config as _config

    param_names = [k for k in best_combo if k not in ("face_f1", "face_precision", "face_recall")]
    best_params = {k: best_combo[k] for k in param_names}

    # Build current defaults combo from config
    defaults: dict[str, object] = {}
    for name in param_names:
        defaults[name] = getattr(_config, name)

    print("\n" + "=" * 60)
    print("VALIDATION ON FULL SPLIT")
    print("=" * 60)

    logger.info("Validating on full split: best vs current defaults")
    logger.info("  Best params: %s", best_params)
    logger.info("  Current defaults: %s", defaults)

    print("\nCurrent defaults:")
    default_row = _evaluate_single_combo(defaults, split="full", frozen_set=frozen_set, ctx=ctx)

    print("\nBest from sweep:")
    best_row = _evaluate_single_combo(best_params, split="full", frozen_set=frozen_set, ctx=ctx)

    # Print comparison table
    print(f"\n{'':>30}  {'Defaults':>10}  {'Best':>10}  {'Delta':>10}")
    print("-" * 65)
    for m in ("face_f1", "face_precision", "face_recall"):
        label = m.replace("face_", "")
        d = default_row[m]
        b = best_row[m]
        delta = b - d
        sign = "+" if delta >= 0 else ""
        print(f"  {label:>28}  {d:>9.1%}  {b:>9.1%}  {sign}{delta:>8.1%}")

    best_metric = best_row.get(metric, 0)
    default_metric = default_row.get(metric, 0)
    if best_metric > default_metric:
        params_str = ", ".join(f"{k}={best_params[k]}" for k in param_names)
        print(f"\nWinner on full: {params_str}")
        print("Update config.py to apply these values.")
    elif best_metric < default_metric:
        print(f"\nCurrent defaults perform better on full — possible overfitting to iteration split.")
    else:
        print(f"\nNo difference on full split.")
