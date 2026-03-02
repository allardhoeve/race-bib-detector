# Task 092: Auto-tuner — diagnose failures and suggest parameter changes

Part of the tuning series (085-094).

**Depends on:** task-088 (bib candidate trace)

## Goal

Build a tuning workflow that starts from benchmark failures, diagnoses why they failed using trace data, suggests parameter changes, and validates those changes against passing photos.

## Background

The existing `GridTuner` does brute-force sweeps. The auto-tuner takes the opposite approach: start from what's broken, understand why, propose a fix, verify no regressions.

```
1. Select failures  ──→  harness reads BenchmarkRun
2. Diagnose         ──→  pluggable strategy reads bib_trace
3. Suggest          ──→  strategy proposes param changes
4. Regression test  ──→  harness replays/re-runs with new params
5. Report           ──→  harness prints before/after comparison
```

Steps 1, 4, 5 are the **harness** (stable). Steps 2+3 are the **strategy** (swappable).

## Design decisions

| Question | Decision |
|----------|----------|
| First scope | Bib detection only (richer trace data, more tunable params) |
| Strategy interface | Single `analyze()` method returning diagnosis + suggestions |
| Cheap vs expensive | "Replay" = re-filter stored OCR data (seconds). "Re-run" = re-run pipeline (minutes). First impl: replay only. |
| Regression scope | All currently-passing photos in the same split |

## Context

- `pipeline/types.py` — `BibCandidateTrace` with `ocr_text`, `ocr_confidence`, `accepted`
- `benchmarking/models.py` — `BenchmarkRun`, `PhotoResult` with `bib_trace`
- `benchmarking/scoring.py` — `score_bibs()`, `BibScorecard`
- `benchmarking/tuners/protocol.py` — `Tuner` Protocol, `TunerResult`
- `benchmarking/tuners/grid.py` — existing GridTuner reference

## Architecture

### Harness: `benchmarking/tuners/auto.py`

```python
@dataclass
class PhotoFailure:
    photo_result: PhotoResult
    failure_type: str  # "miss" | "partial"

@dataclass
class ParamSuggestion:
    param_name: str
    current_value: Any
    suggested_value: Any
    evidence: list[str]     # photo hashes
    estimated_tp_gain: int | None
    cost: str               # "replay" | "re-run"

@dataclass
class AutoTuneResult:
    failures: list[PhotoFailure]
    diagnosis: DiagnosisReport
    suggestions: list[ParamSuggestion]
    regression: RegressionResult | None

def run_auto_tune(
    benchmark_run: BenchmarkRun,
    strategy: TuningStrategy,
    run_regression: bool = True,
) -> AutoTuneResult: ...
```

### Strategy: `benchmarking/tuners/strategies/`

```python
# base.py
class TuningStrategy(Protocol):
    def analyze(self, failures, benchmark_run) -> tuple[DiagnosisReport, list[ParamSuggestion]]: ...

# rule_based.py — failure bucket classifier
class RuleBasedStrategy:
    ...
```

**Failure buckets for bibs:**

| Bucket | Meaning | Lever | Cost |
|--------|---------|-------|------|
| `no_candidate` | White region detector found nothing | `WHITE_THRESHOLD`, `MIN_CONTOUR_AREA` | re-run |
| `candidate_rejected` | Failed validation | rejection_reason-specific threshold | re-run |
| `ocr_below_threshold` | OCR confidence too low | `WHITE_REGION_CONFIDENCE_THRESHOLD` | replay |
| `ocr_wrong_number` | Wrong digits | Not tunable | — |
| `ocr_no_result` | OCR returned nothing | Model/preprocessing | re-run |

The strategy reads `bib_trace` to classify — no re-running detection.

### CLI

Add `bnr benchmark auto-tune` subcommand.

## Tests

`tests/test_auto_tuner.py`:
- `test_select_failures` — identifies miss/partial photos
- `test_classify_no_candidate` — no trace entries → `no_candidate`
- `test_classify_ocr_below_threshold` — low confidence → correct bucket
- `test_suggestion_for_threshold` — enough failures → threshold suggestion
- `test_regression_detects_new_fp` — catches regressions
- `test_replay_vs_rerun_labeling` — cost correctly labeled

`tests/test_tuning_strategies.py`:
- `test_protocol_compliance` — RuleBasedStrategy satisfies TuningStrategy
- `test_no_suggestions_for_untuneable` — all `ocr_wrong_number` → empty

## Acceptance criteria

- [ ] `run_auto_tune()` produces `AutoTuneResult` from a `BenchmarkRun`
- [ ] `RuleBasedStrategy` classifies failures into defined buckets
- [ ] `ocr_below_threshold` bucket produces concrete `ParamSuggestion`
- [ ] Regression testing detects regressions on passing photos
- [ ] CLI command prints report
- [ ] Strategy is pluggable
- [ ] All tests pass

## Scope boundaries

- **In scope**: harness, rule-based bib strategy, CLI, regression testing
- **Out of scope**: face tuning (future strategy), web UI, auto-apply to config
