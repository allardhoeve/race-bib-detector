"""Benchmark runner - evaluates detection accuracy against ground truth."""

from __future__ import annotations

import json
import logging
import platform
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import easyocr
import cv2
import numpy as np
import torch

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
from detection import detect_bib_numbers
from geometry import bbox_to_rect
from preprocessing import PreprocessConfig
from warnings_utils import suppress_torch_mps_pin_memory_warning

from faces import FaceBackend, get_face_backend

from faces.autolink import predict_links

from .ground_truth import (
    load_bib_ground_truth,
    load_face_ground_truth,
    load_link_ground_truth,
    BibBox,
    BibPhotoLabel,
    FaceGroundTruth,
    FaceBox,
    LinkGroundTruth,
)
from .photo_index import load_photo_index, get_path_for_hash
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


@dataclass
class PhotoResult:
    """Result of running detection on a single photo."""
    content_hash: str
    expected_bibs: list[int]
    detected_bibs: list[int]
    tp: int  # True positives
    fp: int  # False positives
    fn: int  # False negatives
    status: Status
    detection_time_ms: float
    tags: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    preprocess_metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "expected_bibs": self.expected_bibs,
            "detected_bibs": self.detected_bibs,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "status": self.status,
            "detection_time_ms": self.detection_time_ms,
            "tags": self.tags,
            "artifact_paths": self.artifact_paths,
            "preprocess_metadata": self.preprocess_metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PhotoResult:
        return cls(
            content_hash=data["content_hash"],
            expected_bibs=data["expected_bibs"],
            detected_bibs=data["detected_bibs"],
            tp=data["tp"],
            fp=data["fp"],
            fn=data["fn"],
            status=data["status"],
            detection_time_ms=data.get("detection_time_ms", 0),
            tags=data.get("tags", []),
            artifact_paths=data.get("artifact_paths", {}),
            preprocess_metadata=data.get("preprocess_metadata", {}),
        )


@dataclass
class BenchmarkMetrics:
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

    def to_dict(self) -> dict:
        return {
            "total_photos": self.total_photos,
            "total_tp": self.total_tp,
            "total_fp": self.total_fp,
            "total_fn": self.total_fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "pass_count": self.pass_count,
            "partial_count": self.partial_count,
            "miss_count": self.miss_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BenchmarkMetrics:
        return cls(
            total_photos=data["total_photos"],
            total_tp=data["total_tp"],
            total_fp=data["total_fp"],
            total_fn=data["total_fn"],
            precision=data["precision"],
            recall=data["recall"],
            f1=data["f1"],
            pass_count=data["pass_count"],
            partial_count=data["partial_count"],
            miss_count=data["miss_count"],
        )


@dataclass
class PipelineConfig:
    """Configuration of the preprocessing pipeline used in a benchmark run."""
    target_width: int | None
    clahe_enabled: bool
    clahe_clip_limit: float | None
    clahe_tile_size: tuple[int, int] | None
    clahe_dynamic_range_threshold: float | None

    def to_dict(self) -> dict:
        return {
            "target_width": self.target_width,
            "clahe_enabled": self.clahe_enabled,
            "clahe_clip_limit": self.clahe_clip_limit,
            "clahe_tile_size": list(self.clahe_tile_size) if self.clahe_tile_size else None,
            "clahe_dynamic_range_threshold": self.clahe_dynamic_range_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineConfig:
        tile_size = data.get("clahe_tile_size")
        return cls(
            target_width=data.get("target_width"),
            clahe_enabled=data.get("clahe_enabled", False),
            clahe_clip_limit=data.get("clahe_clip_limit"),
            clahe_tile_size=tuple(tile_size) if tile_size else None,
            clahe_dynamic_range_threshold=data.get("clahe_dynamic_range_threshold"),
        )

    def summary(self) -> str:
        """Return a short human-readable summary of the pipeline config."""
        parts = []
        if self.target_width:
            parts.append(f"w={self.target_width}")
        if self.clahe_enabled:
            parts.append("CLAHE")
        return ", ".join(parts) if parts else "default"


@dataclass
class FacePipelineConfig:
    """Configuration of the face detection pipeline used in a run."""
    face_backend: str
    dnn_confidence_min: float
    dnn_fallback_confidence_min: float
    dnn_fallback_max: int
    fallback_backend: str | None
    fallback_min_face_count: int
    fallback_max: int
    fallback_iou_threshold: float

    def to_dict(self) -> dict:
        return {
            "face_backend": self.face_backend,
            "dnn_confidence_min": self.dnn_confidence_min,
            "dnn_fallback_confidence_min": self.dnn_fallback_confidence_min,
            "dnn_fallback_max": self.dnn_fallback_max,
            "fallback_backend": self.fallback_backend,
            "fallback_min_face_count": self.fallback_min_face_count,
            "fallback_max": self.fallback_max,
            "fallback_iou_threshold": self.fallback_iou_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FacePipelineConfig":
        return cls(
            face_backend=data.get("face_backend", "unknown"),
            dnn_confidence_min=data.get("dnn_confidence_min", 0.0),
            dnn_fallback_confidence_min=data.get("dnn_fallback_confidence_min", 0.0),
            dnn_fallback_max=data.get("dnn_fallback_max", 0),
            fallback_backend=data.get("fallback_backend"),
            fallback_min_face_count=data.get("fallback_min_face_count", 0),
            fallback_max=data.get("fallback_max", 0),
            fallback_iou_threshold=data.get("fallback_iou_threshold", 0.0),
        )

    def summary(self) -> str:
        """Return a short human-readable summary of face backend config."""
        if not self.face_backend:
            return "faces: disabled"
        fallback = ""
        if self.fallback_backend:
            fallback = f"+{self.fallback_backend}"
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


@dataclass
class RunMetadata:
    """Metadata about a benchmark run."""
    run_id: str
    timestamp: str
    split: str
    git_commit: str
    git_dirty: bool
    python_version: str
    package_versions: dict[str, str]
    hostname: str
    gpu_info: str | None
    total_runtime_seconds: float
    pipeline_config: PipelineConfig | None = None
    face_pipeline_config: FacePipelineConfig | None = None
    note: str | None = None

    def to_dict(self) -> dict:
        result = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "split": self.split,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "python_version": self.python_version,
            "package_versions": self.package_versions,
            "hostname": self.hostname,
            "gpu_info": self.gpu_info,
            "total_runtime_seconds": self.total_runtime_seconds,
        }
        if self.pipeline_config:
            result["pipeline_config"] = self.pipeline_config.to_dict()
        if self.face_pipeline_config:
            result["face_pipeline_config"] = self.face_pipeline_config.to_dict()
        if self.note:
            result["note"] = self.note
        return result

    @classmethod
    def from_dict(cls, data: dict) -> RunMetadata:
        pipeline_config = None
        if "pipeline_config" in data:
            pipeline_config = PipelineConfig.from_dict(data["pipeline_config"])
        face_pipeline_config = None
        if "face_pipeline_config" in data:
            face_pipeline_config = FacePipelineConfig.from_dict(data["face_pipeline_config"])
        return cls(
            run_id=data.get("run_id", "unknown"),
            timestamp=data["timestamp"],
            split=data["split"],
            git_commit=data["git_commit"],
            git_dirty=data["git_dirty"],
            python_version=data["python_version"],
            package_versions=data["package_versions"],
            hostname=data["hostname"],
            gpu_info=data.get("gpu_info"),
            total_runtime_seconds=data.get("total_runtime_seconds", 0),
            pipeline_config=pipeline_config,
            face_pipeline_config=face_pipeline_config,
            note=data.get("note"),
        )


@dataclass
class BenchmarkRun:
    """Complete benchmark run results."""
    metadata: RunMetadata
    metrics: BenchmarkMetrics
    photo_results: list[PhotoResult]
    bib_scorecard: BibScorecard | None = None
    face_scorecard: FaceScorecard | None = None
    link_scorecard: LinkScorecard | None = None

    def to_dict(self) -> dict:
        d = {
            "metadata": self.metadata.to_dict(),
            "metrics": self.metrics.to_dict(),
            "photo_results": [r.to_dict() for r in self.photo_results],
        }
        if self.bib_scorecard is not None:
            d["bib_scorecard"] = self.bib_scorecard.to_dict()
        if self.face_scorecard is not None:
            d["face_scorecard"] = self.face_scorecard.to_dict()
        if self.link_scorecard is not None:
            d["link_scorecard"] = self.link_scorecard.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> BenchmarkRun:
        bib_scorecard = None
        if "bib_scorecard" in data:
            sc = data["bib_scorecard"]
            bib_scorecard = BibScorecard(
                detection_tp=sc["detection_tp"],
                detection_fp=sc["detection_fp"],
                detection_fn=sc["detection_fn"],
                ocr_correct=sc["ocr_correct"],
                ocr_total=sc["ocr_total"],
            )

        face_scorecard = None
        if "face_scorecard" in data:
            sc = data["face_scorecard"]
            face_scorecard = FaceScorecard(
                detection_tp=sc["detection_tp"],
                detection_fp=sc["detection_fp"],
                detection_fn=sc["detection_fn"],
            )

        link_scorecard = None
        if "link_scorecard" in data:
            link_scorecard = LinkScorecard.from_dict(data["link_scorecard"])

        return cls(
            metadata=RunMetadata.from_dict(data["metadata"]),
            metrics=BenchmarkMetrics.from_dict(data["metrics"]),
            photo_results=[PhotoResult.from_dict(r) for r in data["photo_results"]],
            bib_scorecard=bib_scorecard,
            face_scorecard=face_scorecard,
            link_scorecard=link_scorecard,
        )

    def save(self, path: Path) -> None:
        """Save benchmark run to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> BenchmarkRun:
        """Load benchmark run from JSON file."""
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))


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
                versions[pkg] = torch.__version__
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
    if torch.cuda.is_available():
        return torch.cuda.get_device_name(0)
    return None


def compute_photo_result(
    label: BibPhotoLabel,
    detected_bibs: list[int],
    detection_time_ms: float,
) -> PhotoResult:
    """Compute metrics for a single photo."""
    expected_set = set(label.bibs)
    detected_set = set(detected_bibs)

    tp = len(expected_set & detected_set)
    fp = len(detected_set - expected_set)
    fn = len(expected_set - detected_set)

    # Determine status
    if tp == len(expected_set) and fp == 0:
        status: Status = "PASS"
    elif tp == 0 and len(expected_set) > 0:
        status = "MISS"
    else:
        status = "PARTIAL"

    # Special case: no expected bibs
    if len(expected_set) == 0:
        if fp == 0:
            status = "PASS"
        else:
            status = "PARTIAL"  # False positives on a no-bib photo

    return PhotoResult(
        content_hash=label.content_hash,
        expected_bibs=sorted(expected_set),
        detected_bibs=sorted(detected_set),
        tp=tp,
        fp=fp,
        fn=fn,
        status=status,
        detection_time_ms=detection_time_ms,
        tags=label.tags,
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


def _run_detection_loop(
    reader,
    photos: list,
    index: dict,
    images_dir: Path,
    verbose: bool,
    face_backend: FaceBackend | None = None,
    face_gt: FaceGroundTruth | None = None,
    link_gt: LinkGroundTruth | None = None,
) -> tuple[list[PhotoResult], BibScorecard, FaceScorecard | None, LinkScorecard | None]:
    """Run detection on all photos; return results and aggregate IoU scorecards."""
    photo_results: list[PhotoResult] = []
    iou_det_tp = iou_det_fp = iou_det_fn = iou_ocr_correct = iou_ocr_total = 0
    face_det_tp = face_det_fp = face_det_fn = 0
    link_tp = link_fp = link_fn = 0

    for i, label in enumerate(photos):
        path = get_path_for_hash(label.content_hash, PHOTOS_DIR, index)
        if not path or not path.exists():
            if verbose:
                logger.info(
                    "  [%s/%s] SKIP (file not found): %s...",
                    i + 1, len(photos), label.content_hash[:8],
                )
            continue

        image_data = path.read_bytes()
        photo_artifact_dir = str(images_dir / label.content_hash[:16])

        detect_start = time.time()
        result = detect_bib_numbers(reader, image_data, artifact_dir=photo_artifact_dir)
        detect_time_ms = (time.time() - detect_start) * 1000

        detected_bibs = []
        for det in result.detections:
            try:
                detected_bibs.append(int(det.bib_number))
            except ValueError:
                pass

        photo_result = compute_photo_result(label, detected_bibs, detect_time_ms)
        photo_result.artifact_paths = result.artifact_paths
        photo_result.preprocess_metadata = result.preprocess_metadata
        photo_results.append(photo_result)

        pred_bib_boxes: list[BibBox] = []
        img_w, img_h = result.original_dimensions
        if img_w > 0 and img_h > 0:
            for det in result.detections:
                x1, y1, x2, y2 = bbox_to_rect(det.bbox)
                pred_bib_boxes.append(BibBox(
                    x=x1 / img_w, y=y1 / img_h,
                    w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
                    number=det.bib_number,
                ))
            photo_sc = score_bibs(pred_bib_boxes, label.boxes)
            iou_det_tp += photo_sc.detection_tp
            iou_det_fp += photo_sc.detection_fp
            iou_det_fn += photo_sc.detection_fn
            iou_ocr_correct += photo_sc.ocr_correct
            iou_ocr_total += photo_sc.ocr_total

        pred_face_boxes: list[FaceBox] = []
        photo_face_label = None
        if face_backend is not None and face_gt is not None:
            photo_face_label = face_gt.get_photo(label.content_hash)
            gt_face_boxes = photo_face_label.boxes if photo_face_label else []
            img_array = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
            if img_array is not None:
                image_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
                face_h, face_w = image_rgb.shape[:2]
                face_candidates = face_backend.detect_face_candidates(image_rgb)
                for cand in face_candidates:
                    if not cand.passed:
                        continue
                    x1, y1, x2, y2 = bbox_to_rect(cand.bbox)
                    pred_face_boxes.append(FaceBox(
                        x=x1 / face_w, y=y1 / face_h,
                        w=(x2 - x1) / face_w, h=(y2 - y1) / face_h,
                    ))
                photo_face_sc = score_faces(pred_face_boxes, gt_face_boxes)
                face_det_tp += photo_face_sc.detection_tp
                face_det_fp += photo_face_sc.detection_fp
                face_det_fn += photo_face_sc.detection_fn

        if link_gt is not None and photo_face_label is not None:
            autolink = predict_links(pred_bib_boxes, pred_face_boxes)
            photo_link_sc = score_links(
                predicted_pairs=autolink.pairs,
                gt_bib_boxes=label.boxes,
                gt_face_boxes=photo_face_label.boxes,
                gt_links=link_gt.get_links(label.content_hash),
            )
            link_tp += photo_link_sc.link_tp
            link_fp += photo_link_sc.link_fp
            link_fn += photo_link_sc.link_fn

        if verbose:
            status_icon = {"PASS": "✓", "PARTIAL": "◐", "MISS": "✗"}[photo_result.status]
            logger.info(
                "  [%s/%s] %s %-7s exp=%s det=%s (%.0fms)",
                i + 1, len(photos), status_icon,
                photo_result.status, photo_result.expected_bibs,
                photo_result.detected_bibs, detect_time_ms,
            )

    bib_scorecard = BibScorecard(
        detection_tp=iou_det_tp,
        detection_fp=iou_det_fp,
        detection_fn=iou_det_fn,
        ocr_correct=iou_ocr_correct,
        ocr_total=iou_ocr_total,
    )
    face_scorecard = None
    if face_backend is not None:
        face_scorecard = FaceScorecard(
            detection_tp=face_det_tp,
            detection_fp=face_det_fp,
            detection_fn=face_det_fn,
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
) -> RunMetadata:
    """Capture environment and pipeline configuration into RunMetadata."""
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
    fallback_backend = FACE_FALLBACK_BACKEND.strip() if isinstance(FACE_FALLBACK_BACKEND, str) else FACE_FALLBACK_BACKEND
    if fallback_backend == "":
        fallback_backend = None
    face_pipeline_config = FacePipelineConfig(
        face_backend=FACE_BACKEND,
        dnn_confidence_min=FACE_DNN_CONFIDENCE_MIN,
        dnn_fallback_confidence_min=FACE_DNN_FALLBACK_CONFIDENCE_MIN,
        dnn_fallback_max=FACE_DNN_FALLBACK_MAX,
        fallback_backend=fallback_backend,
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
        note=note,
    )


def run_benchmark(
    split: str = "full",
    verbose: bool = True,
    note: str | None = None,
) -> BenchmarkRun:
    """Run benchmark on the specified split.

    Args:
        split: Which split to run ("iteration" or "full")
        verbose: Whether to print progress

    Returns:
        BenchmarkRun with all results and metadata
    """
    start_time = time.time()

    run_id = generate_run_id()
    run_dir, images_dir = _prepare_run_dirs(run_id)

    gt = load_bib_ground_truth()
    index = load_photo_index()
    photos = gt.get_by_split(split)
    _validate_inputs(gt, index, photos, split)

    if verbose:
        logger.info("Running benchmark on %s photos (split: %s)", len(photos), split)
        logger.info("Run ID: %s", run_id)

    if verbose:
        logger.info("Initializing EasyOCR...")
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
        reader, photos, index, images_dir, verbose, face_backend, face_gt, link_gt
    )
    metrics = compute_metrics(photo_results)
    metadata = _build_run_metadata(run_id, split, note, start_time)

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

    Args:
        current: Current benchmark run
        tolerance: Tolerance for regression detection

    Returns:
        Tuple of (judgement, details) where details contains delta information
    """
    if not BASELINE_PATH.exists():
        return "NO_CHANGE", {"reason": "No baseline exists"}

    baseline = BenchmarkRun.load(BASELINE_PATH)

    # Calculate deltas
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

    # Determine judgement
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
            # Add pipeline config summary if available
            if run.metadata.pipeline_config:
                run_info["pipeline"] = run.metadata.pipeline_config.summary()
            else:
                run_info["pipeline"] = "unknown"
            if run.metadata.face_pipeline_config:
                run_info["passes"] = run.metadata.face_pipeline_config.summary_passes()
            else:
                run_info["passes"] = "unknown"
            run_info["note"] = run.metadata.note
            runs.append(run_info)
        except Exception:
            # Skip malformed runs
            continue

    # Sort by timestamp, newest first
    runs.sort(key=lambda r: r["timestamp"], reverse=True)

    # Mark baseline
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
        run_id: The run ID (or prefix)

    Returns:
        BenchmarkRun or None if not found
    """
    if not RESULTS_DIR.exists():
        return None

    # Try exact match first
    run_dir = RESULTS_DIR / run_id
    if run_dir.exists():
        run_json = run_dir / "run.json"
        if run_json.exists():
            return BenchmarkRun.load(run_json)

    # Try prefix match
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
        keep_count: Number of recent runs to keep
        dry_run: If True, don't actually delete, just return what would be deleted

    Returns:
        List of dicts describing deleted (or would-be-deleted) runs
    """
    import shutil

    runs = list_runs()

    if len(runs) <= keep_count:
        return []

    # Runs are already sorted newest first
    to_delete = runs[keep_count:]
    deleted = []

    for run_info in to_delete:
        run_dir = Path(run_info["path"])

        # Calculate size
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
