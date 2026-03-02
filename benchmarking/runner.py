"""Benchmark runner - evaluates detection accuracy against ground truth."""

from __future__ import annotations

import json
import logging
import platform
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from pydantic import BaseModel, Field, field_serializer, field_validator

import config
from config import (
    BENCHMARK_REGRESSION_TOLERANCE,
    FACE_BACKEND,
    FACE_DNN_CONFIDENCE_MIN,
    FACE_DNN_FALLBACK_CONFIDENCE_MIN,
    FACE_DNN_FALLBACK_MAX,
    FACE_FALLBACK_BACKEND,
    FACE_FALLBACK_IOU_THRESHOLD,
    FACE_FALLBACK_MAX,
    FACE_FALLBACK_MIN_FACE_COUNT,
)
from geometry import bbox_to_rect
from preprocessing import PreprocessConfig
from warnings_utils import suppress_torch_mps_pin_memory_warning

from faces import FaceBackend, get_face_backend

from pipeline import run_single_photo
from pipeline.types import predict_links

from .ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
    BibBox,
    BibFaceLink,
    BibPhotoLabel,
    FaceGroundTruth,
    FaceBox,
    LinkGroundTruth,
)
from .photo_index import load_photo_index, get_path_for_hash
from .photo_metadata import PhotoMetadataStore, load_photo_metadata
from .scoring import score_bibs, score_faces, score_links, BibScorecard, FaceScorecard, LinkScorecard

logger = logging.getLogger(__name__)

# Photos directory
PHOTOS_DIR = Path(__file__).parent.parent / "photos"

# Results directory
RESULTS_DIR = Path(__file__).parent / "results"

# Baseline file (for full split only)
BASELINE_PATH = Path(__file__).parent / "baseline.json"


# Status constants
Status = Literal["PASS", "PARTIAL", "MISS"]
Judgement = Literal["IMPROVED", "REGRESSED", "NO_CHANGE"]


class BibCandidateSummary(BaseModel):
    """Serialisable summary of a BibCandidate from the detection pipeline."""
    x: float
    y: float
    w: float
    h: float
    area: int
    aspect_ratio: float
    median_brightness: float
    mean_brightness: float
    relative_area: float
    passed: bool
    rejection_reason: str | None = None


class PhotoResult(BaseModel):
    """Result of running detection on a single photo."""
    content_hash: str
    expected_bibs: list[int]
    detected_bibs: list[int]
    tp: int  # True positives
    fp: int  # False positives
    fn: int  # False negatives
    status: Status
    detection_time_ms: float
    tags: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    preprocess_metadata: dict[str, Any] = Field(default_factory=dict)
    # Prediction + GT boxes for inspect overlay (task-049)
    pred_bib_boxes: list[BibBox] | None = None
    pred_face_boxes: list[FaceBox] | None = None
    gt_bib_boxes: list[BibBox] | None = None
    gt_face_boxes: list[FaceBox] | None = None
    # Predicted bib↔face links from autolink (task-060)
    pred_links: list[BibFaceLink] | None = None
    # Per-photo IoU scorecards (task-061)
    bib_scorecard: BibScorecard | None = None
    face_scorecard: FaceScorecard | None = None
    link_scorecard: LinkScorecard | None = None
    face_detection_time_ms: float | None = None
    # Bib candidate diagnostics (task-062)
    bib_candidates: list[BibCandidateSummary] | None = None


class BenchmarkMetrics(BaseModel):
    """Aggregate metrics from a benchmark run."""
    total_photos: int
    total_tp: int
    total_fp: int
    total_fn: int
    precision: float
    recall: float
    f1: float
    pass_count: int
    partial_count: int
    miss_count: int


class PipelineConfig(BaseModel):
    """Configuration of the preprocessing pipeline used in a benchmark run."""
    target_width: int | None
    clahe_enabled: bool
    clahe_clip_limit: float | None
    clahe_tile_size: tuple[int, int] | None
    clahe_dynamic_range_threshold: float | None

    @field_validator("clahe_tile_size", mode="before")
    @classmethod
    def _coerce_tile_size(cls, v: Any) -> Any:
        """Accept list [w, h] from JSON; convert to tuple for in-memory use."""
        if isinstance(v, list):
            return tuple(v)
        return v

    @field_serializer("clahe_tile_size")
    def _serialize_tile_size(self, v: tuple[int, int] | None) -> list[int] | None:
        """Emit as list for JSON compatibility (JSON has no tuple type)."""
        return list(v) if v is not None else None

    def summary(self) -> str:
        """Return a short human-readable summary of the pipeline config."""
        parts = []
        if self.target_width:
            parts.append(f"w={self.target_width}")
        if self.clahe_enabled:
            parts.append("CLAHE")
        return ", ".join(parts) if parts else "default"


class FacePipelineConfig(BaseModel):
    """Configuration of the face detection pipeline used in a run."""
    face_backend: str
    dnn_confidence_min: float
    dnn_fallback_confidence_min: float
    dnn_fallback_max: int
    fallback_backend: str | None
    fallback_min_face_count: int
    fallback_max: int
    fallback_iou_threshold: float

    @field_validator("fallback_backend", mode="before")
    @classmethod
    def _normalize_fallback_backend(cls, v: Any) -> Any:
        """Normalise empty string to None; config layer emits '' when no fallback is set."""
        if v == "":
            return None
        return v

    def summary(self) -> str:
        """Return a short human-readable summary of face backend config."""
        if not self.face_backend:
            return "faces: disabled"
        fallback = f"+{self.fallback_backend}" if self.fallback_backend else ""
        return f"faces: {self.face_backend}{fallback}"

    def summary_passes(self) -> str:
        """Return a concise summary of passes for list views."""
        if not self.face_backend:
            return "faces: off"
        passes = [self.face_backend]
        if self.dnn_fallback_confidence_min > 0 and self.dnn_fallback_max > 0:
            passes.append("lowconf")
        if self.fallback_backend:
            passes.append(self.fallback_backend)
        return f"faces: {', '.join(passes)}"


class RunMetadata(BaseModel):
    """Metadata about a benchmark run."""
    run_id: str
    timestamp: str
    split: str
    git_commit: str
    git_dirty: bool
    python_version: str
    package_versions: dict[str, str]
    hostname: str
    gpu_info: str | None = None
    total_runtime_seconds: float
    pipeline_config: PipelineConfig | None = None
    face_pipeline_config: FacePipelineConfig | None = None
    frozen_set: str | None = None
    note: str | None = None


class BenchmarkRun(BaseModel):
    """Complete benchmark run results."""

    metadata: RunMetadata
    metrics: BenchmarkMetrics
    photo_results: list[PhotoResult]
    bib_scorecard: BibScorecard | None = None
    face_scorecard: FaceScorecard | None = None
    link_scorecard: LinkScorecard | None = None

    def save(self, path: Path) -> None:
        """Save benchmark run to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(exclude_none=True), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "BenchmarkRun":
        """Load benchmark run from JSON file."""
        with open(path, "r") as f:
            return cls.model_validate(json.load(f))


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp."""
    import hashlib
    timestamp = datetime.now().isoformat()
    return hashlib.sha256(timestamp.encode()).hexdigest()[:8]


def get_git_info() -> tuple[str, bool]:
    """Get git commit hash and dirty status."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        dirty_check = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, check=True
        )
        dirty = bool(dirty_check.stdout.strip())

        return commit, dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", False


def get_package_versions() -> dict[str, str]:
    """Get versions of key packages."""
    versions = {}
    packages = ["easyocr", "opencv-python", "torch", "numpy"]

    for pkg in packages:
        try:
            if pkg == "opencv-python":
                versions[pkg] = cv2.__version__
            elif pkg == "torch":
                import torch as _torch
                versions[pkg] = _torch.__version__
            elif pkg == "numpy":
                versions[pkg] = np.__version__
            elif pkg == "easyocr":
                import easyocr as eo
                versions[pkg] = getattr(eo, "__version__", "unknown")
        except Exception:
            versions[pkg] = "unknown"

    return versions


def get_gpu_info() -> str | None:
    """Get GPU info if CUDA available."""
    import torch
    if torch.cuda.is_available():
        return torch.cuda.get_device_name(0)
    return None


def compute_photo_result(
    label: BibPhotoLabel,
    detected_bibs: list[int],
    detection_time_ms: float,
    tags: list[str] | None = None,
) -> PhotoResult:
    """Compute per-photo detection status and TP/FP/FN counts.

    Status rules:
    - PASS:    all expected bibs found, no false positives.
    - MISS:    at least one expected bib, but none detected (tp == 0).
    - PARTIAL: anything in between, including false positives on a clean photo
               (zero expected bibs but non-zero detected bibs).
    """
    expected_set = set(label.bibs)
    detected_set = set(detected_bibs)

    tp = len(expected_set & detected_set)
    fp = len(detected_set - expected_set)
    fn = len(expected_set - detected_set)

    if tp == len(expected_set) and fp == 0:
        status: Status = "PASS"
    elif tp == 0 and len(expected_set) > 0:
        # Hard miss: detected nothing that was expected.
        status = "MISS"
    else:
        status = "PARTIAL"

    # Special case: photo with no expected bibs.
    # A clean photo is PASS only when there are also no false positives.
    if len(expected_set) == 0:
        status = "PASS" if fp == 0 else "PARTIAL"

    return PhotoResult(
        content_hash=label.content_hash,
        expected_bibs=sorted(expected_set),
        detected_bibs=sorted(detected_set),
        tp=tp,
        fp=fp,
        fn=fn,
        status=status,
        detection_time_ms=detection_time_ms,
        tags=tags or [],
    )


def compute_metrics(photo_results: list[PhotoResult]) -> BenchmarkMetrics:
    """Compute aggregate metrics from photo results."""
    total_tp = sum(r.tp for r in photo_results)
    total_fp = sum(r.fp for r in photo_results)
    total_fn = sum(r.fn for r in photo_results)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    pass_count = sum(1 for r in photo_results if r.status == "PASS")
    partial_count = sum(1 for r in photo_results if r.status == "PARTIAL")
    miss_count = sum(1 for r in photo_results if r.status == "MISS")

    return BenchmarkMetrics(
        total_photos=len(photo_results),
        total_tp=total_tp,
        total_fp=total_fp,
        total_fn=total_fn,
        precision=precision,
        recall=recall,
        f1=f1,
        pass_count=pass_count,
        partial_count=partial_count,
        miss_count=miss_count,
    )


def _prepare_run_dirs(run_id: str) -> tuple[Path, Path]:
    """Create and return (run_dir, images_dir) for a new benchmark run."""
    run_dir = RESULTS_DIR / run_id
    images_dir = run_dir / "images"
    run_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, images_dir


def _validate_inputs(gt, index: dict, photos: list, split: str) -> None:
    """Raise ValueError if GT, index, or photo list are empty."""
    if not gt.photos:
        raise ValueError("No ground truth data. Run labeling first.")
    if not index:
        raise ValueError("No photo index. Run 'python -m benchmarking.cli scan' first.")
    if not photos:
        raise ValueError(f"No photos in split '{split}'")


def _assign_face_clusters(
    photo_results: list[PhotoResult],
    image_cache: dict[str, bytes],
    distance_threshold: float | None = None,
) -> None:
    """Embed predicted faces and assign cluster IDs in-place."""
    from faces.embedder import get_face_embedder
    from faces.clustering import _cluster_embeddings

    embedder = get_face_embedder()
    all_embeddings: list[np.ndarray] = []
    face_refs: list[tuple[int, int]] = []  # (photo_idx, face_idx)

    for p_idx, result in enumerate(photo_results):
        if not result.pred_face_boxes:
            continue
        image_data = image_cache.get(result.content_hash)
        if not image_data:
            continue
        img_array = cv2.imdecode(
            np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR
        )
        if img_array is None:
            continue
        image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
        h, w = image_rgb.shape[:2]
        bboxes = []
        for f_idx, fbox in enumerate(result.pred_face_boxes):
            if fbox.x is None or fbox.w is None:
                continue
            x1 = int(fbox.x * w)
            y1 = int(fbox.y * h)
            x2 = int((fbox.x + fbox.w) * w)
            y2 = int((fbox.y + fbox.h) * h)
            bboxes.append(((x1, y1), (x2, y1), (x2, y2), (x1, y2)))
            face_refs.append((p_idx, f_idx))

        if bboxes:
            embeddings = embedder.embed(image_rgb, bboxes)
            all_embeddings.extend(embeddings)

    if not all_embeddings:
        return

    emb_matrix = np.stack(all_embeddings).astype(np.float32)
    threshold = distance_threshold if distance_threshold is not None else config.FACE_CLUSTER_DISTANCE_THRESHOLD
    clusters = _cluster_embeddings(emb_matrix, threshold)

    for cluster_id, indices in enumerate(clusters):
        for idx in indices:
            p_idx, f_idx = face_refs[idx]
            photo_results[p_idx].pred_face_boxes[f_idx].cluster_id = cluster_id


def _run_detection_loop(
    reader,
    photos: list,
    index: dict,
    images_dir: Path,
    verbose: bool,
    face_backend: FaceBackend | None = None,
    face_gt: FaceGroundTruth | None = None,
    link_gt: LinkGroundTruth | None = None,
    meta_store: PhotoMetadataStore | None = None,
    photos_dir: Path | None = None,
    detect_fn=None,
) -> tuple[list[PhotoResult], BibScorecard, FaceScorecard | None, LinkScorecard | None]:
    """Run detection on all photos; return results and aggregate IoU scorecards.

    Delegates per-photo detection to ``run_single_photo()`` (the unified
    pipeline), then scores results against ground truth.
    """
    if photos_dir is None:
        photos_dir = PHOTOS_DIR
    photo_results: list[PhotoResult] = []
    bib_tp = bib_fp = bib_fn = bib_ocr_correct = bib_ocr_total = 0
    face_tp = face_fp = face_fn = 0
    link_tp = link_fp = link_fn = 0
    image_cache: dict[str, bytes] = {}

    for i, label in enumerate(photos):
        path = get_path_for_hash(label.content_hash, photos_dir, index)
        if not path or not path.exists():
            if verbose:
                logger.info(
                    "  [%s/%s] SKIP (file not found): %s...",
                    i + 1, len(photos), label.content_hash[:8],
                )
            continue

        image_data = path.read_bytes()
        if face_backend is not None:
            image_cache[label.content_hash] = image_data
        photo_artifact_dir = str(images_dir / label.content_hash[:16])

        # --- Unified pipeline call ---
        sp_result = run_single_photo(
            image_data,
            reader=reader,
            detect_fn=detect_fn,
            run_bibs=True,
            face_backend=face_backend,
            fallback_face_backend=None,  # benchmarking: no fallback chain
            run_faces=face_backend is not None,
            run_autolink=link_gt is not None and face_backend is not None and face_gt is not None,
            artifact_dir=photo_artifact_dir,
        )

        pred_bib_boxes = sp_result.bib_boxes
        img_w, img_h = sp_result.image_dims

        # --- Build PhotoResult from pipeline output ---
        detected_bibs: list[int] = []
        for det in sp_result.bib_result.detections:
            try:
                detected_bibs.append(int(det.bib_number))
            except ValueError:
                pass

        photo_tags: list[str] = []
        if meta_store is not None:
            meta = meta_store.get(label.content_hash)
            if meta:
                photo_tags = meta.bib_tags

        photo_result = compute_photo_result(
            label, detected_bibs, sp_result.bib_detect_time_ms, tags=photo_tags,
        )
        photo_result.artifact_paths = sp_result.bib_result.artifact_paths
        photo_result.preprocess_metadata = sp_result.bib_result.preprocess_metadata
        photo_results.append(photo_result)

        # Bib candidate diagnostics
        if img_w > 0 and img_h > 0:
            sf = sp_result.bib_result.scale_factor
            photo_result.bib_candidates = [
                BibCandidateSummary(
                    x=(c.x * sf) / img_w,
                    y=(c.y * sf) / img_h,
                    w=(c.w * sf) / img_w,
                    h=(c.h * sf) / img_h,
                    area=c.area,
                    aspect_ratio=c.aspect_ratio,
                    median_brightness=c.median_brightness,
                    mean_brightness=c.mean_brightness,
                    relative_area=c.relative_area,
                    passed=c.passed,
                    rejection_reason=c.rejection_reason,
                )
                for c in sp_result.bib_result.all_candidates
            ]

        # --- Bib IoU scoring ---
        if img_w > 0 and img_h > 0:
            photo_sc = score_bibs(pred_bib_boxes, label.boxes)
            photo_result.bib_scorecard = photo_sc
            bib_tp += photo_sc.detection_tp
            bib_fp += photo_sc.detection_fp
            bib_fn += photo_sc.detection_fn
            bib_ocr_correct += photo_sc.ocr_correct
            bib_ocr_total += photo_sc.ocr_total

        photo_result.pred_bib_boxes = pred_bib_boxes
        photo_result.gt_bib_boxes = label.boxes

        # --- Face scoring ---
        pred_face_boxes = sp_result.face_boxes
        photo_face_label = None
        if face_backend is not None and face_gt is not None:
            photo_face_label = face_gt.get_photo(label.content_hash)
            gt_face_boxes = photo_face_label.boxes if photo_face_label else []
            photo_result.face_detection_time_ms = sp_result.face_detect_time_ms
            photo_face_sc = score_faces(pred_face_boxes, gt_face_boxes)
            photo_result.face_scorecard = photo_face_sc
            face_tp += photo_face_sc.detection_tp
            face_fp += photo_face_sc.detection_fp
            face_fn += photo_face_sc.detection_fn

        # --- Link scoring ---
        if link_gt is not None and photo_face_label is not None:
            autolink = sp_result.autolink
            predicted_pairs = autolink.pairs if autolink else []
            pred_link_list = []
            for bib_box, face_box in predicted_pairs:
                try:
                    bi = pred_bib_boxes.index(bib_box)
                    fi = pred_face_boxes.index(face_box)
                    pred_link_list.append(BibFaceLink(bib_index=bi, face_index=fi))
                except ValueError:
                    pass
            photo_result.pred_links = pred_link_list
            photo_link_sc = score_links(
                predicted_pairs=predicted_pairs,
                gt_bib_boxes=label.boxes,
                gt_face_boxes=photo_face_label.boxes,
                gt_links=link_gt.get_links(label.content_hash),
            )
            photo_result.link_scorecard = photo_link_sc
            link_tp += photo_link_sc.link_tp
            link_fp += photo_link_sc.link_fp
            link_fn += photo_link_sc.link_fn

        photo_result.pred_face_boxes = pred_face_boxes
        if photo_face_label is not None:
            photo_result.gt_face_boxes = photo_face_label.boxes

        if verbose:
            status_icon = {"PASS": "✓", "PARTIAL": "◐", "MISS": "✗"}[photo_result.status]
            face_info = f" faces={len(pred_face_boxes)}" if pred_face_boxes else ""
            logger.info(
                "  [%s/%s] %s %-7s exp=%s det=%s%s (%.0fms) %s",
                i + 1, len(photos), status_icon,
                photo_result.status, photo_result.expected_bibs,
                photo_result.detected_bibs, face_info, photo_result.detection_time_ms,
                label.content_hash[:8],
            )

    # Post-processing: embed + cluster predicted faces (task-051)
    if face_backend is not None:
        _assign_face_clusters(photo_results, image_cache)

    bib_scorecard = BibScorecard(
        detection_tp=bib_tp,
        detection_fp=bib_fp,
        detection_fn=bib_fn,
        ocr_correct=bib_ocr_correct,
        ocr_total=bib_ocr_total,
    )
    face_scorecard = None
    if face_backend is not None:
        face_scorecard = FaceScorecard(
            detection_tp=face_tp,
            detection_fp=face_fp,
            detection_fn=face_fn,
        )
    link_scorecard = None
    if link_gt is not None:
        total_gt_links = link_tp + link_fn
        link_scorecard = LinkScorecard(
            link_tp=link_tp,
            link_fp=link_fp,
            link_fn=link_fn,
            gt_link_count=total_gt_links,
        )
    return photo_results, bib_scorecard, face_scorecard, link_scorecard


def _build_run_metadata(
    run_id: str,
    split: str,
    note: str | None,
    start_time: float,
    frozen_set: str | None = None,
) -> RunMetadata:
    """Capture environment and pipeline configuration into RunMetadata.

    Records git state, Python/package versions, hostname, GPU info, and a
    snapshot of the active preprocessing and face pipeline configs.

    The fallback_backend value from config is normalised from '' to None here
    because the config layer emits an empty string when no fallback is set,
    but RunMetadata.FacePipelineConfig represents "no fallback" as None.
    """
    git_commit, git_dirty = get_git_info()
    total_runtime = time.time() - start_time

    preprocess_config = PreprocessConfig()
    pipeline_config = PipelineConfig(
        target_width=preprocess_config.target_width,
        clahe_enabled=preprocess_config.clahe_enabled,
        clahe_clip_limit=preprocess_config.clahe_clip_limit if preprocess_config.clahe_enabled else None,
        clahe_tile_size=preprocess_config.clahe_tile_size if preprocess_config.clahe_enabled else None,
        clahe_dynamic_range_threshold=preprocess_config.clahe_dynamic_range_threshold if preprocess_config.clahe_enabled else None,
    )

    # FacePipelineConfig validator handles '' → None for fallback_backend.
    face_pipeline_config = FacePipelineConfig(
        face_backend=FACE_BACKEND,
        dnn_confidence_min=FACE_DNN_CONFIDENCE_MIN,
        dnn_fallback_confidence_min=FACE_DNN_FALLBACK_CONFIDENCE_MIN,
        dnn_fallback_max=FACE_DNN_FALLBACK_MAX,
        fallback_backend=FACE_FALLBACK_BACKEND,
        fallback_min_face_count=FACE_FALLBACK_MIN_FACE_COUNT,
        fallback_max=FACE_FALLBACK_MAX,
        fallback_iou_threshold=FACE_FALLBACK_IOU_THRESHOLD,
    )

    return RunMetadata(
        run_id=run_id,
        timestamp=datetime.now().isoformat(),
        split=split,
        git_commit=git_commit,
        git_dirty=git_dirty,
        python_version=platform.python_version(),
        package_versions=get_package_versions(),
        hostname=socket.gethostname(),
        gpu_info=get_gpu_info(),
        total_runtime_seconds=total_runtime,
        pipeline_config=pipeline_config,
        face_pipeline_config=face_pipeline_config,
        frozen_set=frozen_set,
        note=note,
    )


def _select_photo_hashes(
    split: str,
    meta_store,
    frozen_set: str | None,
) -> list[str]:
    """Choose which photo hashes to run and in what order.

    Photo ordering contract: when running against a frozen set, the
    returned list follows snapshot.hashes order so that photo index
    [N/total] in runner output matches #N in the frozen-set gallery
    (/frozen/{set_name}/).  Both the runner and the gallery template
    must use snapshot.hashes as the single source of order.

    When --split is not "full", only the intersection of the frozen set
    and the split is returned, but still in snapshot order.
    """
    if frozen_set is not None:
        from .sets import BenchmarkSnapshot
        snapshot = BenchmarkSnapshot.load(frozen_set)
        if split == "full":
            return list(snapshot.hashes)
        allowed = set(meta_store.get_hashes_by_split(split))
        return [h for h in snapshot.hashes if h in allowed]
    return meta_store.get_hashes_by_split(split)


def run_benchmark(
    split: str = "full",
    verbose: bool = True,
    note: str | None = None,
    frozen_set: str | None = None,
) -> BenchmarkRun:
    """Run benchmark on the specified split.

    Loads ground truth and photo index, initialises EasyOCR, and runs the
    detection loop over every photo in the split.

    Face backend strategy: get_face_backend() is called once at startup inside
    a try/except. If it raises for any reason (model not installed, config
    error, etc.), face_backend is set to None and face scoring is silently
    skipped for the entire run. A warning is logged in that case.

    Args:
        split: Which split to run ("iteration" or "full").
        verbose: Whether to log per-photo progress.
        note: Optional free-text annotation stored in run metadata.
        frozen_set: Optional frozen set name to restrict photos to.

    Returns:
        BenchmarkRun with all results and metadata, also saved to disk.
    """
    start_time = time.time()

    run_id = generate_run_id()
    run_dir, images_dir = _prepare_run_dirs(run_id)

    gt = load_bib_ground_truth()
    index = load_photo_index()
    meta_store = load_photo_metadata()
    split_hashes = _select_photo_hashes(split, meta_store, frozen_set)

    photos = [gt.get_photo(h) or BibPhotoLabel(content_hash=h) for h in split_hashes if gt.has_photo(h) or h in index]
    _validate_inputs(gt, index, photos, split)

    if verbose:
        set_label = f", set: {frozen_set}" if frozen_set else ""
        logger.info("Running benchmark on %s photos (split: %s%s)", len(photos), split, set_label)
        logger.info("Run ID: %s", run_id)

    if verbose:
        logger.info("Initializing EasyOCR...")
    import easyocr
    import torch
    suppress_torch_mps_pin_memory_warning()
    reader = easyocr.Reader(["en"], gpu=torch.cuda.is_available())

    face_gt = load_face_ground_truth()
    link_gt = load_link_ground_truth()
    face_backend: FaceBackend | None = None
    try:
        face_backend = get_face_backend()
    except Exception as exc:
        logger.warning("Face backend unavailable — face scoring skipped: %s", exc)

    photo_results, bib_scorecard, face_scorecard, link_scorecard = _run_detection_loop(
        reader, photos, index, images_dir, verbose, face_backend, face_gt, link_gt, meta_store
    )
    metrics = compute_metrics(photo_results)
    metadata = _build_run_metadata(run_id, split, note, start_time, frozen_set=frozen_set)

    benchmark_run = BenchmarkRun(
        metadata=metadata,
        metrics=metrics,
        photo_results=photo_results,
        bib_scorecard=bib_scorecard,
        face_scorecard=face_scorecard,
        link_scorecard=link_scorecard,
    )

    run_json_path = run_dir / "run.json"
    benchmark_run.save(run_json_path)

    if verbose:
        logger.info("Results saved to: %s", run_dir)

    return benchmark_run


def compare_to_baseline(
    current: BenchmarkRun,
    tolerance: float = BENCHMARK_REGRESSION_TOLERANCE,
) -> tuple[Judgement, dict]:
    """Compare current run to baseline.

    A metric has regressed if it dropped more than ``tolerance`` below the
    baseline value; it has improved if it rose more than ``tolerance`` above.
    The band is symmetric.

    Judgement asymmetry: if *any* metric (precision OR recall) regresses,
    the overall judgement is REGRESSED, even if another metric improved.
    Regression wins over improvement when metrics move in opposite directions.

    Args:
        current: Current benchmark run.
        tolerance: Symmetric band around zero for NO_CHANGE detection.

    Returns:
        Tuple of (judgement, details) where details contains delta information.
    """
    if not BASELINE_PATH.exists():
        return "NO_CHANGE", {"reason": "No baseline exists"}

    baseline = BenchmarkRun.load(BASELINE_PATH)

    precision_delta = current.metrics.precision - baseline.metrics.precision
    recall_delta = current.metrics.recall - baseline.metrics.recall
    f1_delta = current.metrics.f1 - baseline.metrics.f1

    details = {
        "baseline_commit": baseline.metadata.git_commit[:8],
        "baseline_timestamp": baseline.metadata.timestamp,
        "precision_delta": precision_delta,
        "recall_delta": recall_delta,
        "f1_delta": f1_delta,
        "baseline_precision": baseline.metrics.precision,
        "baseline_recall": baseline.metrics.recall,
        "baseline_f1": baseline.metrics.f1,
    }

    precision_regressed = precision_delta < -tolerance
    recall_regressed = recall_delta < -tolerance
    precision_improved = precision_delta > tolerance
    recall_improved = recall_delta > tolerance

    if precision_regressed or recall_regressed:
        judgement: Judgement = "REGRESSED"
    elif precision_improved or recall_improved:
        judgement = "IMPROVED"
    else:
        judgement = "NO_CHANGE"

    details["precision_regressed"] = precision_regressed
    details["recall_regressed"] = recall_regressed
    details["precision_improved"] = precision_improved
    details["recall_improved"] = recall_improved

    return judgement, details


def load_baseline() -> BenchmarkRun | None:
    """Load baseline if it exists."""
    if BASELINE_PATH.exists():
        return BenchmarkRun.load(BASELINE_PATH)
    return None


def save_baseline(run: BenchmarkRun) -> None:
    """Save a run as the new baseline."""
    run.save(BASELINE_PATH)


def list_runs() -> list[dict]:
    """List all saved benchmark runs.

    Returns:
        List of dicts with run info, sorted by timestamp (newest first).
    """
    runs = []

    if not RESULTS_DIR.exists():
        return runs

    for run_dir in RESULTS_DIR.iterdir():
        if not run_dir.is_dir():
            continue

        run_json = run_dir / "run.json"
        if not run_json.exists():
            continue

        try:
            run = BenchmarkRun.load(run_json)
            run_info = {
                "run_id": run.metadata.run_id,
                "timestamp": run.metadata.timestamp,
                "split": run.metadata.split,
                "precision": run.metrics.precision,
                "recall": run.metrics.recall,
                "f1": run.metrics.f1,
                "git_commit": run.metadata.git_commit[:8],
                "total_photos": run.metrics.total_photos,
                "path": str(run_dir),
            }
            if run.metadata.pipeline_config:
                run_info["pipeline"] = run.metadata.pipeline_config.summary()
            else:
                run_info["pipeline"] = "unknown"
            if run.metadata.face_pipeline_config:
                run_info["passes"] = run.metadata.face_pipeline_config.summary_passes()
            else:
                run_info["passes"] = "unknown"
            run_info["frozen_set"] = run.metadata.frozen_set
            run_info["note"] = run.metadata.note
            runs.append(run_info)
        except Exception:
            continue

    runs.sort(key=lambda r: r["timestamp"], reverse=True)

    baseline = load_baseline()
    if baseline:
        for run in runs:
            if run["run_id"] == baseline.metadata.run_id:
                run["is_baseline"] = True
                break

    return runs


def get_run(run_id: str) -> BenchmarkRun | None:
    """Load a specific run by ID.

    Args:
        run_id: The run ID (or prefix).

    Returns:
        BenchmarkRun or None if not found.
    """
    if not RESULTS_DIR.exists():
        return None

    run_dir = RESULTS_DIR / run_id
    if run_dir.exists():
        run_json = run_dir / "run.json"
        if run_json.exists():
            return BenchmarkRun.load(run_json)

    for d in RESULTS_DIR.iterdir():
        if d.is_dir() and d.name.startswith(run_id):
            run_json = d / "run.json"
            if run_json.exists():
                return BenchmarkRun.load(run_json)

    return None


def get_latest_run() -> BenchmarkRun | None:
    """Get the most recent benchmark run."""
    runs = list_runs()
    if not runs:
        return None
    return get_run(runs[0]["run_id"])


def clean_runs(keep_count: int = 5, dry_run: bool = False) -> list[dict]:
    """Remove old benchmark runs, keeping the most recent ones.

    Args:
        keep_count: Number of recent runs to keep.
        dry_run: If True, don't actually delete, just return what would be deleted.

    Returns:
        List of dicts describing deleted (or would-be-deleted) runs.
    """
    import shutil

    runs = list_runs()

    if len(runs) <= keep_count:
        return []

    to_delete = runs[keep_count:]
    deleted = []

    for run_info in to_delete:
        run_dir = Path(run_info["path"])

        total_size = 0
        for f in run_dir.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size

        deleted.append({
            "run_id": run_info["run_id"],
            "timestamp": run_info["timestamp"],
            "split": run_info["split"],
            "size_mb": total_size / (1024 * 1024),
            "path": str(run_dir),
        })

        if not dry_run:
            shutil.rmtree(run_dir)

    return deleted
