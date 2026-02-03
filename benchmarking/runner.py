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
class RunMetadata:
    """Metadata about a benchmark run."""
    timestamp: str
    split: str
    git_commit: str
    git_dirty: bool
    python_version: str
    package_versions: dict[str, str]
    hostname: str
    gpu_info: str | None
    total_runtime_seconds: float

    def to_dict(self) -> dict:
        return {
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

    @classmethod
    def from_dict(cls, data: dict) -> RunMetadata:
        return cls(
            timestamp=data["timestamp"],
            split=data["split"],
            git_commit=data["git_commit"],
            git_dirty=data["git_dirty"],
            python_version=data["python_version"],
            package_versions=data["package_versions"],
            hostname=data["hostname"],
            gpu_info=data.get("gpu_info"),
            total_runtime_seconds=data.get("total_runtime_seconds", 0),
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
) -> BenchmarkRun:
    """Run benchmark on the specified split.

    Args:
        split: Which split to run ("iteration" or "full")
        verbose: Whether to print progress

    Returns:
        BenchmarkRun with all results and metadata
    """
    start_time = time.time()

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

        # Run detection with timing
        detect_start = time.time()
        result = detect_bib_numbers(reader, image_data)
        detect_time_ms = (time.time() - detect_start) * 1000

        # Extract detected bib numbers as integers
        detected_bibs = []
        for det in result.detections:
            try:
                detected_bibs.append(int(det.bib_number))
            except ValueError:
                pass

        # Compute result
        photo_result = compute_photo_result(label, detected_bibs, detect_time_ms)
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

    metadata = RunMetadata(
        timestamp=datetime.now().isoformat(),
        split=split,
        git_commit=git_commit,
        git_dirty=git_dirty,
        python_version=platform.python_version(),
        package_versions=get_package_versions(),
        hostname=socket.gethostname(),
        gpu_info=get_gpu_info(),
        total_runtime_seconds=total_runtime,
    )

    return BenchmarkRun(
        metadata=metadata,
        metrics=metrics,
        photo_results=photo_results,
    )


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
