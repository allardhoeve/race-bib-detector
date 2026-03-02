"""Auto-tuner: diagnose benchmark failures and suggest parameter changes (task-092)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from benchmarking.runner import BenchmarkRun, PhotoResult


class FailureBucket(str, Enum):
    """Classification of why a photo failed bib detection."""

    NO_CANDIDATE = "no_candidate"
    CANDIDATE_REJECTED = "candidate_rejected"
    OCR_NO_RESULT = "ocr_no_result"
    OCR_BELOW_THRESHOLD = "ocr_below_threshold"
    OCR_WRONG_NUMBER = "ocr_wrong_number"


@dataclass
class PhotoFailure:
    """A single photo that failed detection, with details about what's missing."""

    photo_result: PhotoResult
    failure_type: str  # "miss" | "partial"
    missing_bibs: list[int] = field(default_factory=list)


@dataclass
class DiagnosisReport:
    """Summary of failure classification across all failing photos."""

    bucket_counts: dict[str, int] = field(default_factory=dict)
    bucket_photos: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ParamSuggestion:
    """A concrete suggestion to change a config parameter."""

    param_name: str
    current_value: Any
    suggested_value: Any
    evidence: list[str] = field(default_factory=list)  # photo hashes
    estimated_tp_gain: int = 0
    cost: str = "replay"  # "replay" | "re-run"


class TuningStrategy(Protocol):
    """Protocol for pluggable tuning strategies."""

    def analyze(
        self,
        failures: list[PhotoFailure],
        benchmark_run: BenchmarkRun,
    ) -> tuple[DiagnosisReport, list[ParamSuggestion]]: ...


@dataclass
class AutoTuneResult:
    """Complete result of an auto-tune run."""

    failures: list[PhotoFailure]
    diagnosis: DiagnosisReport
    suggestions: list[ParamSuggestion]


def select_failures(benchmark_run: BenchmarkRun) -> list[PhotoFailure]:
    """Pick MISS and PARTIAL photos with missing bibs."""
    failures: list[PhotoFailure] = []
    for result in benchmark_run.photo_results:
        if result.status == "PASS":
            continue
        missing = sorted(set(result.expected_bibs) - set(result.detected_bibs))
        failures.append(PhotoFailure(
            photo_result=result,
            failure_type=result.status.lower(),
            missing_bibs=missing,
        ))
    return failures


def run_auto_tune(
    benchmark_run: BenchmarkRun,
    strategy: TuningStrategy | None = None,
) -> AutoTuneResult:
    """Main entry: select failures, analyze, return result.

    If no strategy is provided, uses the default RuleBasedStrategy.
    """
    if strategy is None:
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy
        strategy = RuleBasedStrategy()

    failures = select_failures(benchmark_run)
    diagnosis, suggestions = strategy.analyze(failures, benchmark_run)
    return AutoTuneResult(
        failures=failures,
        diagnosis=diagnosis,
        suggestions=suggestions,
    )


def print_auto_tune_report(result: AutoTuneResult) -> None:
    """Print human-readable report to stdout."""
    total = len(result.failures)
    print(f"\n=== Auto-tune report ({total} failure{'s' if total != 1 else ''}) ===\n")

    # Diagnosis summary
    if result.diagnosis.bucket_counts:
        print("Failure buckets:")
        for bucket, count in sorted(result.diagnosis.bucket_counts.items()):
            hashes = result.diagnosis.bucket_photos.get(bucket, [])
            hash_preview = ", ".join(h[:8] for h in hashes[:5])
            if len(hashes) > 5:
                hash_preview += f", ... (+{len(hashes) - 5})"
            print(f"  {bucket:25s} {count:3d}  [{hash_preview}]")
    else:
        print("No failures to diagnose.")

    # Suggestions
    print()
    if result.suggestions:
        print("Suggestions:")
        for s in result.suggestions:
            print(f"  {s.param_name}: {s.current_value} -> {s.suggested_value}")
            print(f"    Estimated TP gain: +{s.estimated_tp_gain}  (cost: {s.cost})")
            print(f"    Evidence: {', '.join(h[:8] for h in s.evidence[:5])}")
    else:
        print("No parameter suggestions.")
    print()
