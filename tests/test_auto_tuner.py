"""Tests for the auto-tuner (task-092)."""

from __future__ import annotations

import pytest

from benchmarking.runner import BenchmarkRun, PhotoResult, BenchmarkMetrics, RunMetadata
from pipeline.types import BibCandidateTrace


def _make_photo_result(
    content_hash: str = "aabb0000",
    expected_bibs: list[int] | None = None,
    detected_bibs: list[int] | None = None,
    status: str = "PASS",
    **kwargs,
) -> PhotoResult:
    """Helper to build a PhotoResult with sane defaults."""
    exp = expected_bibs or []
    det = detected_bibs or []
    exp_set = set(exp)
    det_set = set(det)
    tp = len(exp_set & det_set)
    fp = len(det_set - exp_set)
    fn = len(exp_set - det_set)
    return PhotoResult(
        content_hash=content_hash,
        expected_bibs=exp,
        detected_bibs=det,
        tp=tp,
        fp=fp,
        fn=fn,
        status=status,
        detection_time_ms=100.0,
        **kwargs,
    )


def _make_benchmark_run(photo_results: list[PhotoResult]) -> BenchmarkRun:
    """Helper to build a minimal BenchmarkRun."""
    return BenchmarkRun(
        metadata=RunMetadata(
            run_id="test0001",
            timestamp="2026-01-01T00:00:00",
            split="iteration",
            git_commit="abc12345",
            git_dirty=False,
            python_version="3.12.0",
            package_versions={},
            hostname="test",
            total_runtime_seconds=1.0,
        ),
        metrics=BenchmarkMetrics(
            total_photos=len(photo_results),
            total_tp=0, total_fp=0, total_fn=0,
            precision=0.0, recall=0.0, f1=0.0,
            pass_count=0, partial_count=0, miss_count=0,
        ),
        photo_results=photo_results,
    )


class TestSelectFailures:
    def test_picks_miss_and_partial(self):
        """PASS photos are excluded; MISS and PARTIAL are selected."""
        from benchmarking.tuners.auto import select_failures

        results = [
            _make_photo_result("aa000000", [100], [100], "PASS"),
            _make_photo_result("bb000000", [200], [], "MISS"),
            _make_photo_result("cc000000", [300, 400], [300], "PARTIAL"),
        ]
        run = _make_benchmark_run(results)
        failures = select_failures(run)

        assert len(failures) == 2
        hashes = {f.photo_result.content_hash for f in failures}
        assert hashes == {"bb000000", "cc000000"}

    def test_computes_missing_bibs(self):
        """missing_bibs = expected - detected."""
        from benchmarking.tuners.auto import select_failures

        results = [
            _make_photo_result("bb000000", [200, 201], [201], "PARTIAL"),
        ]
        run = _make_benchmark_run(results)
        failures = select_failures(run)

        assert len(failures) == 1
        assert failures[0].missing_bibs == [200]
        assert failures[0].failure_type == "partial"

    def test_empty_run(self):
        """All-PASS run produces no failures."""
        from benchmarking.tuners.auto import select_failures

        results = [
            _make_photo_result("aa000000", [100], [100], "PASS"),
            _make_photo_result("bb000000", [200], [200], "PASS"),
        ]
        run = _make_benchmark_run(results)
        failures = select_failures(run)

        assert failures == []


def _make_trace(
    passed_validation: bool = True,
    ocr_text: str | None = None,
    ocr_confidence: float | None = None,
    accepted: bool = False,
    bib_number: str | None = None,
    rejection_reason: str | None = None,
) -> BibCandidateTrace:
    """Helper to build a BibCandidateTrace with sane defaults."""
    return BibCandidateTrace(
        x=0.1, y=0.1, w=0.1, h=0.1,
        area=5000, aspect_ratio=1.5, median_brightness=150.0,
        mean_brightness=140.0, relative_area=0.01,
        passed_validation=passed_validation,
        rejection_reason=rejection_reason,
        ocr_text=ocr_text,
        ocr_confidence=ocr_confidence,
        accepted=accepted,
        bib_number=bib_number,
    )


class TestClassifyPhoto:
    def test_no_candidate_empty_trace(self):
        """Photo with empty bib_trace → NO_CANDIDATE."""
        from benchmarking.tuners.auto import PhotoFailure, FailureBucket
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        result = _make_photo_result("aa000000", [100], [], "MISS", bib_trace=[])
        failure = PhotoFailure(photo_result=result, failure_type="miss", missing_bibs=[100])

        strategy = RuleBasedStrategy()
        bucket = strategy._classify_photo(failure)
        assert bucket == FailureBucket.NO_CANDIDATE

    def test_candidate_rejected(self):
        """All traces failed validation → CANDIDATE_REJECTED."""
        from benchmarking.tuners.auto import PhotoFailure, FailureBucket
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        traces = [
            _make_trace(passed_validation=False, rejection_reason="too_small"),
            _make_trace(passed_validation=False, rejection_reason="too_dark"),
        ]
        result = _make_photo_result("aa000000", [100], [], "MISS", bib_trace=traces)
        failure = PhotoFailure(photo_result=result, failure_type="miss", missing_bibs=[100])

        strategy = RuleBasedStrategy()
        bucket = strategy._classify_photo(failure)
        assert bucket == FailureBucket.CANDIDATE_REJECTED

    def test_ocr_no_result(self):
        """Passed validation, but no ocr_text → OCR_NO_RESULT."""
        from benchmarking.tuners.auto import PhotoFailure, FailureBucket
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        traces = [_make_trace(passed_validation=True, ocr_text=None)]
        result = _make_photo_result("aa000000", [100], [], "MISS", bib_trace=traces)
        failure = PhotoFailure(photo_result=result, failure_type="miss", missing_bibs=[100])

        strategy = RuleBasedStrategy()
        bucket = strategy._classify_photo(failure)
        assert bucket == FailureBucket.OCR_NO_RESULT

    def test_ocr_below_threshold(self):
        """Has ocr_text below confidence threshold → OCR_BELOW_THRESHOLD."""
        from benchmarking.tuners.auto import PhotoFailure, FailureBucket
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        # ocr_confidence=0.3 is below WHITE_REGION_CONFIDENCE_THRESHOLD=0.4
        traces = [_make_trace(
            passed_validation=True,
            ocr_text="100",
            ocr_confidence=0.3,
            accepted=False,
        )]
        result = _make_photo_result("aa000000", [100], [], "MISS", bib_trace=traces)
        failure = PhotoFailure(photo_result=result, failure_type="miss", missing_bibs=[100])

        strategy = RuleBasedStrategy()
        bucket = strategy._classify_photo(failure)
        assert bucket == FailureBucket.OCR_BELOW_THRESHOLD

    def test_ocr_wrong_number(self):
        """Accepted with wrong number → OCR_WRONG_NUMBER."""
        from benchmarking.tuners.auto import PhotoFailure, FailureBucket
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        # Trace was accepted with bib "999" but expected 100
        traces = [_make_trace(
            passed_validation=True,
            ocr_text="999",
            ocr_confidence=0.9,
            accepted=True,
            bib_number="999",
        )]
        result = _make_photo_result("aa000000", [100], [999], "MISS", bib_trace=traces)
        failure = PhotoFailure(photo_result=result, failure_type="miss", missing_bibs=[100])

        strategy = RuleBasedStrategy()
        bucket = strategy._classify_photo(failure)
        assert bucket == FailureBucket.OCR_WRONG_NUMBER


class TestDiagnosisAndSuggestions:
    def test_diagnosis_counts_buckets(self):
        """diagnosis.bucket_counts is correct across multiple failures."""
        from benchmarking.tuners.auto import PhotoFailure, FailureBucket, DiagnosisReport
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        failures = [
            # 2 × NO_CANDIDATE
            PhotoFailure(
                photo_result=_make_photo_result("aa000000", [100], [], "MISS", bib_trace=[]),
                failure_type="miss", missing_bibs=[100],
            ),
            PhotoFailure(
                photo_result=_make_photo_result("bb000000", [200], [], "MISS", bib_trace=[]),
                failure_type="miss", missing_bibs=[200],
            ),
            # 1 × OCR_BELOW_THRESHOLD
            PhotoFailure(
                photo_result=_make_photo_result(
                    "cc000000", [300], [], "MISS",
                    bib_trace=[_make_trace(passed_validation=True, ocr_text="300", ocr_confidence=0.3, accepted=False)],
                ),
                failure_type="miss", missing_bibs=[300],
            ),
        ]
        run = _make_benchmark_run([f.photo_result for f in failures])
        strategy = RuleBasedStrategy()
        diagnosis, _suggestions = strategy.analyze(failures, run)

        assert isinstance(diagnosis, DiagnosisReport)
        assert diagnosis.bucket_counts["no_candidate"] == 2
        assert diagnosis.bucket_counts["ocr_below_threshold"] == 1
        assert diagnosis.bucket_photos["no_candidate"] == ["aa000000", "bb000000"]
        assert diagnosis.bucket_photos["ocr_below_threshold"] == ["cc000000"]

    def test_suggest_threshold_for_below_threshold(self):
        """OCR_BELOW_THRESHOLD failures produce a ParamSuggestion for confidence threshold."""
        from benchmarking.tuners.auto import PhotoFailure, ParamSuggestion
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        # Two photos with sub-threshold OCR results
        failures = [
            PhotoFailure(
                photo_result=_make_photo_result(
                    "aa000000", [100], [], "MISS",
                    bib_trace=[_make_trace(passed_validation=True, ocr_text="100", ocr_confidence=0.35, accepted=False)],
                ),
                failure_type="miss", missing_bibs=[100],
            ),
            PhotoFailure(
                photo_result=_make_photo_result(
                    "bb000000", [200], [], "MISS",
                    bib_trace=[_make_trace(passed_validation=True, ocr_text="200", ocr_confidence=0.30, accepted=False)],
                ),
                failure_type="miss", missing_bibs=[200],
            ),
        ]
        # Include a PASS photo to check regression
        pass_result = _make_photo_result("cc000000", [300], [300], "PASS")
        run = _make_benchmark_run([f.photo_result for f in failures] + [pass_result])
        strategy = RuleBasedStrategy()
        _diagnosis, suggestions = strategy.analyze(failures, run)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.param_name == "WHITE_REGION_CONFIDENCE_THRESHOLD"
        assert s.current_value == 0.4
        assert s.suggested_value < 0.4
        assert s.estimated_tp_gain >= 1
        assert s.cost == "replay"
        assert "aa000000" in s.evidence or "bb000000" in s.evidence

    def test_no_suggestion_for_untuneable(self):
        """All OCR_WRONG_NUMBER failures → empty suggestions."""
        from benchmarking.tuners.auto import PhotoFailure
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        failures = [
            PhotoFailure(
                photo_result=_make_photo_result(
                    "aa000000", [100], [999], "MISS",
                    bib_trace=[_make_trace(
                        passed_validation=True, ocr_text="999",
                        ocr_confidence=0.9, accepted=True, bib_number="999",
                    )],
                ),
                failure_type="miss", missing_bibs=[100],
            ),
        ]
        run = _make_benchmark_run([f.photo_result for f in failures])
        strategy = RuleBasedStrategy()
        _diagnosis, suggestions = strategy.analyze(failures, run)

        assert suggestions == []

    def test_replay_counts_recovered_tps(self):
        """estimated_tp_gain reflects how many bibs would be recovered at suggested threshold."""
        from benchmarking.tuners.auto import PhotoFailure
        from benchmarking.tuners.strategies.rule_based import RuleBasedStrategy

        # 2 failure photos with sub-threshold traces
        failures = [
            PhotoFailure(
                photo_result=_make_photo_result(
                    "aa000000", [100], [], "MISS",
                    bib_trace=[_make_trace(passed_validation=True, ocr_text="100", ocr_confidence=0.35, accepted=False)],
                ),
                failure_type="miss", missing_bibs=[100],
            ),
            PhotoFailure(
                photo_result=_make_photo_result(
                    "bb000000", [200], [], "MISS",
                    bib_trace=[_make_trace(passed_validation=True, ocr_text="200", ocr_confidence=0.25, accepted=False)],
                ),
                failure_type="miss", missing_bibs=[200],
            ),
        ]
        # A passing photo with a sub-threshold trace that's a false positive at conf 0.22
        # If threshold drops to 0.20, this becomes an FP, reducing net gain
        pass_result = _make_photo_result(
            "pp000000", [500], [500], "PASS",
            bib_trace=[
                _make_trace(passed_validation=True, ocr_text="500", ocr_confidence=0.9, accepted=True, bib_number="500"),
                _make_trace(passed_validation=True, ocr_text="777", ocr_confidence=0.22, accepted=False),
            ],
        )
        run = _make_benchmark_run([f.photo_result for f in failures] + [pass_result])
        strategy = RuleBasedStrategy()
        _diagnosis, suggestions = strategy.analyze(failures, run)

        assert len(suggestions) == 1
        s = suggestions[0]
        # At 0.35: recover aa (conf 0.35) → net gain 1, no FPs
        # At 0.25: recover aa + bb → net gain 2, no FPs (0.22 < 0.25)
        # At 0.20: recover aa + bb → 2 TPs but 1 FP → net gain 1
        assert s.suggested_value == 0.25
        assert s.estimated_tp_gain == 2
        assert set(s.evidence) == {"aa000000", "bb000000"}


class TestEndToEnd:
    def test_run_auto_tune_end_to_end(self):
        """Full pipeline from BenchmarkRun to AutoTuneResult."""
        from benchmarking.tuners.auto import run_auto_tune, AutoTuneResult

        results = [
            _make_photo_result("aa000000", [100], [100], "PASS"),
            _make_photo_result(
                "bb000000", [200], [], "MISS",
                bib_trace=[_make_trace(passed_validation=True, ocr_text="200", ocr_confidence=0.35, accepted=False)],
            ),
            _make_photo_result(
                "cc000000", [300], [999], "MISS",
                bib_trace=[_make_trace(
                    passed_validation=True, ocr_text="999",
                    ocr_confidence=0.9, accepted=True, bib_number="999",
                )],
            ),
        ]
        run = _make_benchmark_run(results)
        result = run_auto_tune(run)

        assert isinstance(result, AutoTuneResult)
        assert len(result.failures) == 2
        assert result.diagnosis.bucket_counts.get("ocr_below_threshold") == 1
        assert result.diagnosis.bucket_counts.get("ocr_wrong_number") == 1
        # Should have a suggestion for the sub-threshold photo
        assert len(result.suggestions) == 1
        assert result.suggestions[0].param_name == "WHITE_REGION_CONFIDENCE_THRESHOLD"

    def test_print_report_no_crash(self, capsys):
        """print_auto_tune_report doesn't raise."""
        from benchmarking.tuners.auto import run_auto_tune, print_auto_tune_report

        results = [
            _make_photo_result("aa000000", [100], [100], "PASS"),
            _make_photo_result(
                "bb000000", [200], [], "MISS",
                bib_trace=[_make_trace(passed_validation=True, ocr_text="200", ocr_confidence=0.35, accepted=False)],
            ),
            _make_photo_result("cc000000", [300], [], "MISS", bib_trace=[]),
        ]
        run = _make_benchmark_run(results)
        result = run_auto_tune(run)

        print_auto_tune_report(result)

        captured = capsys.readouterr()
        assert "no_candidate" in captured.out
        assert "WHITE_REGION_CONFIDENCE_THRESHOLD" in captured.out
