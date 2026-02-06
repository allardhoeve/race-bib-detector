"""Benchmark runner - evaluates detection accuracy against ground truth."""

from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import easyocr
import cv2
import numpy as np
import torch

from config import BENCHMARK_REGRESSION_TOLERANCE
from detection import detect_bib_numbers
from preprocessing import PreprocessConfig

from .ground_truth import load_ground_truth, PhotoLabel, GroundTruth
from .photo_index import load_photo_index, get_path_for_hash

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
            parts.append(f"CLAHE")
        return ", ".join(parts) if parts else "default"


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
        if self.note:
            result["note"] = self.note
        return result

    @classmethod
    def from_dict(cls, data: dict) -> RunMetadata:
        pipeline_config = None
        if "pipeline_config" in data:
            pipeline_config = PipelineConfig.from_dict(data["pipeline_config"])
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
            note=data.get("note"),
        )


@dataclass
class BenchmarkRun:
    """Complete benchmark run results."""
    metadata: RunMetadata
    metrics: BenchmarkMetrics
    photo_results: list[PhotoResult]

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "metrics": self.metrics.to_dict(),
            "photo_results": [r.to_dict() for r in self.photo_results],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BenchmarkRun:
        return cls(
            metadata=RunMetadata.from_dict(data["metadata"]),
            metrics=BenchmarkMetrics.from_dict(data["metrics"]),
            photo_results=[PhotoResult.from_dict(r) for r in data["photo_results"]],
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
    label: PhotoLabel,
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

    # Generate run ID and create results directory
    run_id = generate_run_id()
    run_dir = RESULTS_DIR / run_id
    images_dir = run_dir / "images"
    run_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Load ground truth and photo index
    gt = load_ground_truth()
    index = load_photo_index()

    if not gt.photos:
        raise ValueError("No ground truth data. Run labeling first.")

    if not index:
        raise ValueError("No photo index. Run 'python -m benchmarking.cli scan' first.")

    # Get photos for this split
    photos = gt.get_by_split(split)
    if not photos:
        raise ValueError(f"No photos in split '{split}'")

    if verbose:
        print(f"Running benchmark on {len(photos)} photos (split: {split})")
        print(f"Run ID: {run_id}")

    # Initialize EasyOCR reader
    if verbose:
        print("Initializing EasyOCR...")
    reader = easyocr.Reader(["en"], gpu=torch.cuda.is_available())

    # Run detection on each photo
    photo_results: list[PhotoResult] = []

    for i, label in enumerate(photos):
        path = get_path_for_hash(label.content_hash, PHOTOS_DIR, index)
        if not path or not path.exists():
            if verbose:
                print(f"  [{i+1}/{len(photos)}] SKIP (file not found): {label.content_hash[:16]}...")
            continue

        # Read image
        image_data = path.read_bytes()

        # Create artifact directory for this photo
        photo_artifact_dir = str(images_dir / label.content_hash[:16])

        # Run detection with timing and artifact saving
        detect_start = time.time()
        result = detect_bib_numbers(reader, image_data, artifact_dir=photo_artifact_dir)
        detect_time_ms = (time.time() - detect_start) * 1000

        # Extract detected bib numbers as integers
        detected_bibs = []
        for det in result.detections:
            try:
                detected_bibs.append(int(det.bib_number))
            except ValueError:
                pass

        # Compute result with artifact paths
        photo_result = compute_photo_result(label, detected_bibs, detect_time_ms)
        photo_result.artifact_paths = result.artifact_paths
        photo_results.append(photo_result)

        if verbose:
            status_icon = {"PASS": "✓", "PARTIAL": "◐", "MISS": "✗"}[photo_result.status]
            print(f"  [{i+1}/{len(photos)}] {status_icon} {photo_result.status:7} "
                  f"exp={photo_result.expected_bibs} det={photo_result.detected_bibs} "
                  f"({detect_time_ms:.0f}ms)")

    # Compute aggregate metrics
    metrics = compute_metrics(photo_results)

    # Collect metadata
    git_commit, git_dirty = get_git_info()
    total_runtime = time.time() - start_time

    # Capture pipeline configuration
    preprocess_config = PreprocessConfig()
    pipeline_config = PipelineConfig(
        target_width=preprocess_config.target_width,
        clahe_enabled=preprocess_config.clahe_enabled,
        clahe_clip_limit=preprocess_config.clahe_clip_limit if preprocess_config.clahe_enabled else None,
        clahe_tile_size=preprocess_config.clahe_tile_size if preprocess_config.clahe_enabled else None,
        clahe_dynamic_range_threshold=preprocess_config.clahe_dynamic_range_threshold if preprocess_config.clahe_enabled else None,
    )

    metadata = RunMetadata(
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
        note=note,
    )

    benchmark_run = BenchmarkRun(
        metadata=metadata,
        metrics=metrics,
        photo_results=photo_results,
    )

    # Always save results
    run_json_path = run_dir / "run.json"
    benchmark_run.save(run_json_path)

    if verbose:
        print(f"\nResults saved to: {run_dir}")

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
