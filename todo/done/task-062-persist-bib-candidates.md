# Task 062: Persist bib candidates in PhotoResult

Independent of other open tasks. Prerequisite for task-065 (auto-tuner).

## Goal

Stop discarding `BibCandidate` data after bib detection in the benchmark runner. Store a serialisable summary of all candidates (passed and rejected) in `PhotoResult` so downstream consumers (task-059 auto-tuner) can diagnose failures without re-running detection.

## Background

`detect_bib_numbers()` returns a `PipelineResult` containing `all_candidates` — every white-region candidate, with `passed`/`rejection_reason` metadata. The benchmark runner (`_run_bib_detection()`) reads only `result.detections` and discards the candidates. Since the detection pipeline is not entirely idempotent, re-running it later to recover this data is unreliable. Better to capture it once.

## Context

- `detection/types.py` — `BibCandidate` dataclass (bbox, area, aspect_ratio, median/mean brightness, relative_area, passed, rejection_reason); `PipelineResult.all_candidates`
- `benchmarking/runner.py` — `PhotoResult` (Pydantic BaseModel); `_run_bib_detection()` at ~line 375 where candidates are discarded
- `tests/test_runner_models.py` — existing TDD tests for PhotoResult serialisation patterns

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Store full BibCandidate or a summary? | Pydantic summary model — exclude `extract_region()`, numpy deps, and pixel-coordinate bbox (normalise to [0,1] like BibBox) |
| Where to define the model? | In `benchmarking/runner.py` alongside PhotoResult (it's a benchmark-only concern, not a detection type) |
| Normalise bbox coordinates? | Yes, to [0,1] using image dimensions — consistent with pred_bib_boxes |
| Include OCR-scale bbox? | No, normalised coords are sufficient for the auto-tuner |

## Changes

### Modified: `benchmarking/runner.py`

Add `BibCandidateSummary` model and a new field on `PhotoResult`:

```python
class BibCandidateSummary(BaseModel):
    """Serialisable summary of a BibCandidate from the detection pipeline."""
    x: float          # normalised [0,1]
    y: float          # normalised [0,1]
    w: float          # normalised [0,1]
    h: float          # normalised [0,1]
    area: int         # pixel area (at OCR resolution)
    aspect_ratio: float
    median_brightness: float
    mean_brightness: float
    relative_area: float
    passed: bool
    rejection_reason: str | None = None


class PhotoResult(BaseModel):
    ...
    # Bib candidate diagnostics (task-062)
    bib_candidates: list[BibCandidateSummary] | None = None
```

Populate in `_run_bib_detection()` after computing image dims:

```python
# Store all candidates (passed + rejected) for diagnostics
if img_w > 0 and img_h > 0:
    scale = result.scale_factor
    photo_result.bib_candidates = [
        BibCandidateSummary(
            x=(c.x * scale) / img_w,
            y=(c.y * scale) / img_h,
            w=(c.w * scale) / img_w,
            h=(c.h * scale) / img_h,
            area=c.area,
            aspect_ratio=c.aspect_ratio,
            median_brightness=c.median_brightness,
            mean_brightness=c.mean_brightness,
            relative_area=c.relative_area,
            passed=c.passed,
            rejection_reason=c.rejection_reason,
        )
        for c in result.all_candidates
    ]
```

## Tests

Extend `tests/test_runner_models.py`:

- `test_bib_candidate_summary_round_trip` — create a BibCandidateSummary, dump to dict, load back, assert equality
- `test_photo_result_with_candidates_round_trip` — PhotoResult with `bib_candidates` populated serialises and deserialises correctly
- `test_photo_result_without_candidates_backward_compat` — PhotoResult JSON without `bib_candidates` key loads with `None` (backward compat with existing benchmark results)
- `test_rejected_candidate_has_reason` — a rejected candidate preserves `rejection_reason` through serialisation

## Verification

```bash
venv/bin/python -m pytest tests/test_runner_models.py -v
```

## Pitfalls

- `BibCandidate.bbox` is in OCR coordinates. Must scale by `PipelineResult.scale_factor` to get original-image coordinates before normalising by image dimensions. The existing `pred_bib_boxes` conversion uses `bbox_to_rect(det.bbox)` which works on `Detection` (already in original coords). Candidates need the extra scale step.
- Existing benchmark result JSON files won't have `bib_candidates`. The `None` default ensures backward compatibility — no migration needed.

## Acceptance criteria

- [ ] `BibCandidateSummary` model exists with all fields from the design
- [ ] `PhotoResult.bib_candidates` field exists, defaults to `None`
- [ ] `_run_bib_detection()` populates `bib_candidates` from `result.all_candidates`
- [ ] Candidate bbox coordinates are normalised to [0,1]
- [ ] Existing benchmark JSON loads without error (backward compat)
- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] New tests pass

## Scope boundaries

- **In scope**: new model, new field, populate in runner, tests
- **Out of scope**: consuming the data (that's task-059), modifying `detection/types.py`, web UI changes
- **Do not** modify existing benchmark result JSON files or storage format
