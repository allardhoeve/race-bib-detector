# Task 059: Auto-tuner — diagnose failures and suggest parameter changes

Independent of other open tasks. Benefits from task-035 (split detection loop) but does not require it.

## Goal

Build a tuning workflow that starts from benchmark failures, diagnoses why they failed, suggests parameter changes, and validates those changes against passing photos to check for regressions.

## Background

The existing `benchmarking/tuner.py` does brute-force grid sweeps: you define parameter ranges in YAML, it tries every combination. This is slow and uninformed — it doesn't know which parameters matter for the actual failures.

The auto-tuner takes the opposite approach: start from what's broken, understand why, propose a fix, and verify it doesn't break what's working. The workflow is:

```
1. Select failures  ──→  fixed harness, reads benchmark results
2. Diagnose         ──→  pluggable strategy module
3. Suggest          ──→  pluggable strategy module
4. Regression test  ──→  fixed harness, re-runs pipeline with new params
5. Report           ──→  fixed harness, compares before/after
```

Steps 1, 4, 5 are the **harness** — stable scaffolding. Steps 2 and 3 are the **strategy** — swappable modules where the real experimentation happens. The strategy can be replaced or iterated on without touching the harness.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Scope of first implementation | Bib detection only (richer intermediate data, more parameters) |
| Strategy interface | Steps 2+3 are a single pluggable module (diagnosis and suggestion are tightly coupled) |
| Regression test scope | Run proposed params against all currently-passing photos in the split |
| Cheap vs expensive suggestions | Distinguish between "replay" suggestions (re-filter existing data, seconds) and "re-run" suggestions (re-run detection pipeline, minutes). First implementation focuses on replay suggestions only. |

## Context

- `benchmarking/runner.py` — `BenchmarkRun`, `PhotoResult`, `BenchmarkMetrics`, `PipelineConfig`; detection loop stores pred/GT boxes per photo (task-049/050)
- `benchmarking/scoring.py` — `BibScorecard`, `score_bibs()`, IoU matching
- `benchmarking/tuner.py` — existing grid sweep (face params); reference for how sweeps work
- `detection/detector.py` — bib detection pipeline, `PipelineResult`, `BibCandidate`
- `detection/types.py` — `Detection` (has `confidence`, `source`), `BibCandidate` (has `passed`, `rejection_reason`, intermediate metrics)
- `config.py` — all default parameter values

## Architecture

### Harness: `benchmarking/auto_tuner.py`

The harness orchestrates the workflow. It is not pluggable — it's the stable frame.

```python
@dataclass
class AutoTuneResult:
    """Complete result of an auto-tune run."""
    failures: list[PhotoFailure]           # step 1 output
    diagnosis: DiagnosisReport             # step 2 output
    suggestions: list[ParamSuggestion]     # step 3 output
    regression: RegressionResult | None    # step 4 output (None if skipped)

@dataclass
class PhotoFailure:
    """A photo that partially or fully failed, with its result data."""
    photo_result: PhotoResult
    failure_type: str                      # "miss" | "partial"
    gt_bibs: list[BibBox]
    pred_bibs: list[BibBox]

@dataclass
class ParamSuggestion:
    """A concrete suggestion to change one parameter."""
    param_name: str                        # e.g. "WHITE_REGION_CONFIDENCE_THRESHOLD"
    current_value: Any
    suggested_value: Any
    direction: str                         # "increase" | "decrease"
    evidence: list[str]                    # photo hashes that motivated this
    estimated_tp_gain: int | None          # how many FN this might rescue
    estimated_fp_risk: int | None          # how many new FP this might introduce
    cost: str                              # "replay" | "re-run"

@dataclass
class RegressionResult:
    """Before/after comparison on passing photos."""
    photos_tested: int
    before_tp: int
    after_tp: int
    regressions: list[str]                 # photo hashes that went from TP to FP/FN
    new_fp: int


def run_auto_tune(
    benchmark_run: BenchmarkRun,
    strategy: TuningStrategy,
    run_regression: bool = True,
) -> AutoTuneResult:
    # Step 1: select failures
    failures = _select_failures(benchmark_run)

    # Step 2+3: diagnose and suggest (delegated to strategy)
    diagnosis, suggestions = strategy.analyze(failures, benchmark_run)

    # Step 4: regression test (harness-owned)
    regression = None
    if run_regression and suggestions:
        regression = _run_regression(benchmark_run, suggestions)

    return AutoTuneResult(failures, diagnosis, suggestions, regression)
```

### Strategy interface: `benchmarking/tuning_strategies/base.py`

```python
class TuningStrategy(Protocol):
    """Pluggable analysis strategy for steps 2+3."""

    def analyze(
        self,
        failures: list[PhotoFailure],
        benchmark_run: BenchmarkRun,
    ) -> tuple[DiagnosisReport, list[ParamSuggestion]]:
        """Diagnose failures and produce parameter suggestions."""
        ...
```

### First strategy: `benchmarking/tuning_strategies/rule_based.py`

Rule-based diagnosis that classifies each failure into a bucket and maps buckets to parameter suggestions.

**Failure buckets for bib detection:**

| Bucket | Meaning | Parameter lever | Cost |
|--------|---------|-----------------|------|
| `no_candidate` | White region detector found nothing | `WHITE_THRESHOLD`, `MIN_CONTOUR_AREA` | re-run |
| `candidate_rejected` | Candidate found but failed validation | The specific validation threshold from `rejection_reason` | re-run |
| `ocr_below_threshold` | OCR ran but confidence too low | `WHITE_REGION_CONFIDENCE_THRESHOLD` or `FULL_IMAGE_CONFIDENCE_THRESHOLD` | replay |
| `ocr_wrong_number` | OCR returned wrong digits | Not a parameter problem | — |
| `ocr_no_result` | OCR returned nothing | Model limitation or preprocessing | re-run |

The strategy re-runs the detection pipeline on failing photos in diagnostic mode to collect the intermediate `BibCandidate` and `Detection` data needed for classification.

For "replay" suggestions (confidence thresholds), the strategy can estimate impact by replaying the threshold change against existing detection data from all photos — no re-run needed.

```python
class RuleBasedStrategy:
    def analyze(self, failures, benchmark_run):
        # Re-run pipeline on failures in diagnostic mode
        diagnostics = self._collect_diagnostics(failures)

        # Classify each failure
        buckets = self._classify(diagnostics)

        # Aggregate buckets into suggestions
        suggestions = self._suggest(buckets, benchmark_run)

        return DiagnosisReport(buckets=buckets), suggestions
```

### Step 4: Regression testing

The harness takes the suggested parameter changes and re-runs detection on all currently-passing photos from the benchmark. For "replay" suggestions, this is just re-filtering — fast. For "re-run" suggestions, it requires running the actual pipeline — slower.

The regression result reports:
- How many previously-passing photos still pass
- Which specific photos regressed (hash + what changed)
- Net TP/FP/FN delta

### Step 5: Report

CLI output after auto-tune completes:

```
=== Auto-Tune Report ===

Analyzed 14 failures (8 miss, 6 partial) from run abc123

Failure diagnosis:
  no_candidate:         4 photos
  ocr_below_threshold:  6 photos
  candidate_rejected:   2 photos (aspect_ratio)
  ocr_wrong_number:     2 photos (not tunable)

Suggestions:
  1. WHITE_REGION_CONFIDENCE_THRESHOLD: 0.40 → 0.35
     Evidence: 6 photos with OCR confidence in [0.35, 0.40)
     Estimated: +5 TP, +1 FP (replay — validated)
     Cost: replay (instant)

  2. MIN_CONTOUR_AREA: 1000 → 800
     Evidence: 3 photos where GT region area was 800-1000px
     Estimated: +3 TP, unknown FP risk
     Cost: re-run (needs pipeline re-execution)

Regression test (suggestion 1 only — replay):
  Tested 86 passing photos
  Regressions: 1 (hash: a3f1bc02 — new FP from low-confidence OCR)
  Net: +5 TP, +2 FP → F1: 0.82 → 0.85

Run `bnr benchmark tune --apply suggestion-1` to adopt these settings.
```

## Constraints

- Strategy modules must not import from the harness (no circular deps)
- Diagnostic mode must not modify any stored benchmark data
- Regression testing must use the same split as the original benchmark run
- "Replay" suggestions must be clearly separated from "re-run" suggestions in the report

## Changes

### New: `benchmarking/auto_tuner.py`

Harness module: `run_auto_tune()`, failure selection, regression testing, result dataclasses.

### New: `benchmarking/tuning_strategies/base.py`

Protocol definition for `TuningStrategy`.

### New: `benchmarking/tuning_strategies/rule_based.py`

First strategy implementation: failure classification + rule-based suggestions.

### New: `benchmarking/tuning_strategies/__init__.py`

Re-exports.

### Modified: `benchmarking/cli/commands/tune.py`

Add `auto-tune` subcommand (or `bnr benchmark auto-tune`) that loads a benchmark run and runs the auto-tuner.

### Modified: `detection/detector.py`

Ensure `detect_bib_numbers()` can be called in a diagnostic mode that returns full `PipelineResult` including all candidates (passed and rejected) with their intermediate metrics. This may already be the case — verify before changing.

## Tests

Add `tests/test_auto_tuner.py`:

- `test_select_failures_from_benchmark_run` — correctly identifies miss/partial photos
- `test_rule_based_classifies_no_candidate` — failure with no candidate → `no_candidate` bucket
- `test_rule_based_classifies_ocr_below_threshold` — low OCR confidence → correct bucket
- `test_suggestion_for_confidence_threshold` — enough `ocr_below_threshold` failures → threshold suggestion
- `test_regression_detects_new_fp` — regression test catches a passing photo that becomes FP
- `test_replay_vs_rerun_cost_labeling` — suggestions correctly labeled as replay or re-run

Add `tests/test_tuning_strategies.py`:

- `test_strategy_protocol_compliance` — `RuleBasedStrategy` satisfies `TuningStrategy` protocol
- `test_strategy_returns_empty_when_no_tunable_failures` — all `ocr_wrong_number` → no suggestions

## Verification

```bash
venv/bin/python -m pytest tests/test_auto_tuner.py tests/test_tuning_strategies.py -v
```

Manual verification after implementation:

```bash
# Run a benchmark first
venv/bin/python bnr.py benchmark run

# Then run auto-tune on the latest result
venv/bin/python bnr.py benchmark auto-tune
```

## Pitfalls

- `PipelineResult` and `BibCandidate` data is produced during detection but not currently stored in `PhotoResult` or the benchmark run JSON. The strategy needs to either (a) re-run detection on failing photos to get this data, or (b) extend `PhotoResult` to store it. Option (a) is simpler for the first implementation — option (b) is an optimization for later.
- Confidence threshold replay assumes OCR results are deterministic for the same input — this is true for EasyOCR but verify.
- The regression test for "re-run" suggestions is expensive. Consider making it opt-in (`--regression` flag) or sampling a subset of passing photos.

## Acceptance criteria

- [ ] `run_auto_tune()` produces an `AutoTuneResult` from a `BenchmarkRun`
- [ ] `RuleBasedStrategy` classifies failures into the defined buckets
- [ ] At least `ocr_below_threshold` bucket produces a concrete `ParamSuggestion`
- [ ] Regression testing runs proposed params against passing photos and detects regressions
- [ ] CLI command `bnr benchmark auto-tune` prints the report
- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] New tests pass
- [ ] Strategy is pluggable — a new strategy can be added without modifying the harness

## Scope boundaries

- **In scope**: harness, rule-based strategy for bib detection, CLI command, report output
- **Out of scope**: face detection auto-tuning (future strategy), web UI for suggestions, automatic application of suggestions to `config.py`
- **Do not** modify existing benchmark run storage format
- **Do not** modify `benchmarking/tuner.py` (the grid sweep remains independent)
