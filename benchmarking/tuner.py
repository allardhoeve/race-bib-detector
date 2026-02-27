"""Face detection parameter sweep (task-029).

Usage::

    from benchmarking.tuner import run_face_sweep, load_tune_config, print_sweep_results

    cfg = load_tune_config(Path("benchmarking/tune_configs/face_default.yaml"))
    results = run_face_sweep(**cfg)
    print_sweep_results(results, metric=cfg["metric"])
"""

from __future__ import annotations

import itertools
import logging
from pathlib import Path

import cv2
import numpy as np

from benchmarking.ground_truth import FaceBox, load_bib_ground_truth, load_face_ground_truth
from benchmarking.photo_index import get_path_for_hash, load_photo_index
from benchmarking.scoring import FaceScorecard, score_faces
from faces.backend import get_face_backend_with_overrides
from geometry import bbox_to_rect

logger = logging.getLogger(__name__)

# Map from config-level YAML parameter names to OpenCVDnnSsdFaceBackend field names.
_PARAM_TO_BACKEND_KWARG: dict[str, str] = {
    "FACE_DNN_CONFIDENCE_MIN": "confidence_min",
    "FACE_DNN_NMS_IOU": "nms_iou",
    "FACE_DNN_FALLBACK_CONFIDENCE_MIN": "fallback_confidence_min",
    "FACE_DETECTION_MIN_NEIGHBORS": "min_neighbors",
    "FACE_DETECTION_SCALE_FACTOR": "scale_factor",
    "FACE_DETECTION_MIN_SIZE": "min_size",
}

PHOTOS_DIR = Path(__file__).parent.parent / "photos"


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


def run_face_sweep(
    param_grid: dict[str, list],
    split: str = "iteration",
    metric: str = "face_f1",
    verbose: bool = True,
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

    Returns:
        List of result dicts sorted descending by ``metric``.  Each dict
        contains the parameter combination plus ``face_f1``,
        ``face_precision``, and ``face_recall``.
    """
    bib_gt = load_bib_ground_truth()
    face_gt = load_face_ground_truth()
    index = load_photo_index()
    photos = bib_gt.get_by_split(split)

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
            path = get_path_for_hash(label.content_hash, PHOTOS_DIR, index)
            if not path or not path.exists():
                continue
            image_data = path.read_bytes()
            img_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            if img_array is None:
                continue
            image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            face_h, face_w = image_rgb.shape[:2]

            face_label = face_gt.get_photo(label.content_hash)
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
