"""Rule-based tuning strategy: classify failures into buckets (task-092)."""

from __future__ import annotations

from collections import defaultdict

from config import WHITE_REGION_CONFIDENCE_THRESHOLD

from benchmarking.runner import BenchmarkRun
from benchmarking.tuners.auto import DiagnosisReport, FailureBucket, ParamSuggestion, PhotoFailure


def _threshold_candidates(current: float, step: float = 0.05, floor: float = 0.05) -> list[float]:
    """Generate candidate thresholds stepping down from current."""
    candidates = []
    t = round(current - step, 10)
    while t >= floor:
        candidates.append(round(t, 10))
        t = round(t - step, 10)
    return candidates


class RuleBasedStrategy:
    """Classify bib detection failures by examining stored trace data."""

    def analyze(
        self,
        failures: list[PhotoFailure],
        benchmark_run: BenchmarkRun,
    ) -> tuple[DiagnosisReport, list[ParamSuggestion]]:
        """Classify failures into buckets and suggest parameter changes."""
        diagnosis = self._classify(failures)
        suggestions = self._suggest(diagnosis, benchmark_run)
        return diagnosis, suggestions

    def _classify(self, failures: list[PhotoFailure]) -> DiagnosisReport:
        """Classify all failures and build a DiagnosisReport."""
        bucket_counts: dict[str, int] = defaultdict(int)
        bucket_photos: dict[str, list[str]] = defaultdict(list)

        for failure in failures:
            bucket = self._classify_photo(failure)
            bucket_counts[bucket.value] += 1
            bucket_photos[bucket.value].append(failure.photo_result.content_hash)

        return DiagnosisReport(
            bucket_counts=dict(bucket_counts),
            bucket_photos=dict(bucket_photos),
        )

    def _suggest(
        self,
        diagnosis: DiagnosisReport,
        benchmark_run: BenchmarkRun,
    ) -> list[ParamSuggestion]:
        """For OCR_BELOW_THRESHOLD bucket: find optimal threshold via replay."""
        suggestions: list[ParamSuggestion] = []

        below_hashes = set(diagnosis.bucket_photos.get(FailureBucket.OCR_BELOW_THRESHOLD.value, []))
        if not below_hashes:
            return suggestions

        suggestion = self._suggest_confidence_threshold(below_hashes, benchmark_run)
        if suggestion is not None:
            suggestions.append(suggestion)

        return suggestions

    def _suggest_confidence_threshold(
        self,
        below_hashes: set[str],
        benchmark_run: BenchmarkRun,
    ) -> ParamSuggestion | None:
        """Find an optimal confidence threshold by replaying stored trace data.

        1. Collect all sub-threshold (confidence, ocr_text, hash) from failure photos.
        2. Step down from current threshold in 0.05 increments.
        3. At each candidate threshold, count recovered TPs and new FPs from passing photos.
        4. Pick the threshold with best net gain (recovered TPs - new FPs).
        """
        current = WHITE_REGION_CONFIDENCE_THRESHOLD

        # Collect sub-threshold candidates from failure photos
        sub_threshold_entries: list[tuple[float, str, str]] = []  # (confidence, ocr_text, hash)
        for result in benchmark_run.photo_results:
            if result.content_hash not in below_hashes:
                continue
            for trace in result.bib_trace or []:
                if (
                    trace.passed_validation
                    and trace.ocr_text
                    and trace.ocr_confidence is not None
                    and trace.ocr_confidence < current
                    and not trace.accepted
                ):
                    sub_threshold_entries.append(
                        (trace.ocr_confidence, trace.ocr_text, result.content_hash)
                    )

        if not sub_threshold_entries:
            return None

        # Collect existing sub-threshold traces from passing photos (potential FPs)
        pass_sub_threshold: list[tuple[float, str, str]] = []
        for result in benchmark_run.photo_results:
            if result.status != "PASS":
                continue
            expected_set = set(str(b) for b in result.expected_bibs)
            for trace in result.bib_trace or []:
                if (
                    trace.passed_validation
                    and trace.ocr_text
                    and trace.ocr_confidence is not None
                    and trace.ocr_confidence < current
                    and not trace.accepted
                    and trace.ocr_text not in expected_set
                ):
                    pass_sub_threshold.append(
                        (trace.ocr_confidence, trace.ocr_text, result.content_hash)
                    )

        # Try candidate thresholds from current-0.05 down to 0.05
        best_threshold = None
        best_net_gain = 0
        best_tp_gain = 0
        best_evidence: list[str] = []

        candidates = _threshold_candidates(current, step=0.05, floor=0.05)
        for candidate_threshold in candidates:
            recovered = [
                (conf, text, h) for conf, text, h in sub_threshold_entries
                if conf >= candidate_threshold
            ]
            new_fps = [
                (conf, text, h) for conf, text, h in pass_sub_threshold
                if conf >= candidate_threshold
            ]
            tp_gain = len(recovered)
            fp_cost = len(new_fps)
            net_gain = tp_gain - fp_cost

            if net_gain > best_net_gain:
                best_net_gain = net_gain
                best_threshold = candidate_threshold
                best_tp_gain = tp_gain
                best_evidence = list({h for _, _, h in recovered})

        if best_threshold is None:
            return None

        return ParamSuggestion(
            param_name="WHITE_REGION_CONFIDENCE_THRESHOLD",
            current_value=current,
            suggested_value=best_threshold,
            evidence=sorted(best_evidence),
            estimated_tp_gain=best_tp_gain,
            cost="replay",
        )

    def _classify_photo(self, failure: PhotoFailure) -> FailureBucket:
        """Classify a single failure by examining its bib_trace."""
        traces = failure.photo_result.bib_trace or []

        if not traces:
            return FailureBucket.NO_CANDIDATE

        if all(not t.passed_validation for t in traces):
            return FailureBucket.CANDIDATE_REJECTED

        passed = [t for t in traces if t.passed_validation]

        if not any(t.ocr_text for t in passed):
            return FailureBucket.OCR_NO_RESULT

        sub_threshold = [
            t for t in passed
            if t.ocr_text and t.ocr_confidence is not None
            and t.ocr_confidence < WHITE_REGION_CONFIDENCE_THRESHOLD
            and not t.accepted
        ]
        if sub_threshold:
            return FailureBucket.OCR_BELOW_THRESHOLD

        return FailureBucket.OCR_WRONG_NUMBER
