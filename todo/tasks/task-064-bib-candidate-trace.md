# Task 064: Bib candidate trace — capture complete pipeline journey

Prerequisite for task-065 (auto-tuner).

## Goal

Replace `BibCandidateSummary` with `BibCandidateTrace`: a model that records each white-region candidate's complete journey through validation → OCR → acceptance. This closes the diagnostic data gap that would otherwise force the auto-tuner to re-run detection.

## Background

Task-062 added `BibCandidateSummary` to store candidate validation data (geometry, brightness, passed/rejected). But the model stops before OCR — we know whether a candidate passed validation, but not what happened when OCR ran on it. Three outcomes are silently discarded in `detector.py:128-150`:

1. OCR returned a result below the confidence threshold (the "replay" opportunity)
2. OCR returned nothing
3. OCR returned invalid text (not a bib number)

The auto-tuner (task-065) needs all three to classify failures and replay threshold changes without re-running detection.

### Data flow today

```
PipelineResult
├── all_candidates: list[BibCandidate]     ──→  BibCandidateSummary (validation only)
├── detections: list[Detection]            ──→  pred_bib_boxes: list[BibBox] (coords + number)
└── (OCR results below threshold)          ──→  DISCARDED
```

After this task:

```
PipelineResult
├── all_candidates: list[BibCandidate]     ──→  BibCandidateTrace (validation + OCR + verdict)
├── detections: list[Detection]            ──→  pred_bib_boxes: list[BibBox] (unchanged)
└── (OCR results below threshold)          ──→  captured on BibCandidate.ocr_*
```

`pred_bib_boxes` is the **result view** (what to score/link/display). `bib_trace` is the **diagnostic view** (why things happened). Accepted traces correspond 1:1 to entries in `pred_bib_boxes`.

## Design decisions

| Question | Decision |
|----------|----------|
| Where to capture OCR outcomes? | On `BibCandidate` in `detection/types.py` — the pipeline already has the data at runtime |
| Model name | `BibCandidateTrace` — it records a journey, not a summary |
| PhotoResult field name | `bib_trace` — clearly diagnostic, distinct from `pred_bib_boxes` |
| Full-image OCR detections | Excluded from trace — they have no white-region candidate. Already in `pred_bib_boxes` for scoring. Removing full-image OCR entirely is a separate investigation. |
| Multiple OCR results per candidate | Store only the best (highest confidence). Sufficient for threshold replay. |
| What counts as "best" OCR result? | Highest-confidence result with a valid bib number format. Non-bib text is noise, not diagnostic. |

## Context

- `detection/types.py:92` — `BibCandidate` dataclass: bbox, area, aspect_ratio, brightness, passed, rejection_reason
- `detection/detector.py:128-150` — per-candidate OCR loop where sub-threshold results are discarded
- `detection/detector.py:35-61` — `extract_bib_detections()` (full-image OCR path — not modified)
- `benchmarking/runner.py:73` — `BibCandidateSummary` (to be replaced)
- `benchmarking/runner.py:114` — `PhotoResult.bib_candidates` (to be renamed)
- `benchmarking/runner.py:430-457` — `_run_bib_detection()` where candidates are mapped to summaries
- `tests/test_runner_models.py:281-333` — existing BibCandidateSummary tests

## Changes

### Modified: `detection/types.py`

Add OCR outcome fields to `BibCandidate`:

```python
@dataclass
class BibCandidate:
    ...existing fields...

    # OCR outcome (populated after OCR runs; None if rejected before OCR)
    ocr_text: str | None = None
    ocr_confidence: float | None = None
```

### Modified: `detection/detector.py`

In the per-candidate OCR loop (~line 128), capture the best valid-bib OCR result on the candidate regardless of whether it passes the confidence threshold:

```python
for candidate in passed_candidates:
    region = candidate.extract_region(ocr_image)
    results = reader.readtext(region)

    region_detections: list[Detection] = []
    best_bib_conf = 0.0

    for bbox, text, confidence in results:
        cleaned = text.strip().replace(" ", "")

        if is_valid_bib_number(cleaned) and confidence > best_bib_conf:
            best_bib_conf = confidence
            candidate.ocr_text = cleaned
            candidate.ocr_confidence = float(confidence)

        # Existing: create Detection only if above threshold
        if is_valid_bib_number(cleaned) and confidence > WHITE_REGION_CONFIDENCE_THRESHOLD:
            ...existing Detection creation (unchanged)...
```

### Modified: `benchmarking/runner.py`

Rename and extend the model:

```python
class BibCandidateTrace(BaseModel):
    """Record of one candidate's journey through the bib detection pipeline."""
    # Geometry (normalised [0,1])
    x: float
    y: float
    w: float
    h: float

    # Validation stage
    area: int
    aspect_ratio: float
    median_brightness: float
    mean_brightness: float
    relative_area: float
    passed_validation: bool
    rejection_reason: str | None = None

    # OCR stage (None if rejected before OCR or OCR returned nothing valid)
    ocr_text: str | None = None
    ocr_confidence: float | None = None

    # Final verdict
    accepted: bool = False
```

Rename field on `PhotoResult`:

```python
class PhotoResult(BaseModel):
    ...
    bib_trace: list[BibCandidateTrace] | None = None  # was bib_candidates
```

Update `_run_bib_detection()` to populate the new fields from `BibCandidate`:

```python
photo_result.bib_trace = [
    BibCandidateTrace(
        ...existing coordinate normalisation...
        passed_validation=c.passed,        # was: passed=c.passed
        rejection_reason=c.rejection_reason,
        ocr_text=c.ocr_text,              # NEW
        ocr_confidence=c.ocr_confidence,   # NEW
        accepted=c in accepted_candidates, # NEW — see Pitfalls
    )
    for c in result.all_candidates
]
```

### Modified: consumers

Update all references from `bib_candidates` → `bib_trace` and `BibCandidateSummary` → `BibCandidateTrace`:

- `tests/test_runner_models.py` — rename test class and fixtures

Backward compat: add a model validator on `PhotoResult` that accepts the old `bib_candidates` key:

```python
@model_validator(mode="before")
@classmethod
def _migrate_bib_candidates(cls, data):
    if isinstance(data, dict) and "bib_candidates" in data and "bib_trace" not in data:
        data["bib_trace"] = data.pop("bib_candidates")
    return data
```

## Tests

Extend `tests/test_runner_models.py`:

- `test_bib_candidate_trace_with_ocr_round_trip` — trace with OCR fields serialises correctly
- `test_trace_ocr_below_threshold` — `passed_validation=True`, `ocr_confidence=0.37`, `accepted=False` preserved
- `test_trace_no_ocr_result` — `passed_validation=True`, `ocr_text=None`, `accepted=False`
- `test_trace_accepted_true` — candidate that became a detection has `accepted=True`
- `test_backward_compat_bib_candidates_key` — JSON with old `bib_candidates` key loads into `bib_trace`
- `test_backward_compat_missing_ocr_fields` — old trace JSON without `ocr_text`/`ocr_confidence`/`accepted` loads with defaults

Add to `tests/test_bib_detection.py` (slow, uses real OCR):

- `test_candidate_ocr_fields_populated` — run detection on a test image, verify passed candidates have `ocr_text`/`ocr_confidence` set

## Verification

```bash
venv/bin/python -m pytest tests/test_runner_models.py -v
venv/bin/python -m pytest  # full suite
```

## Pitfalls

- **Determining `accepted`**: A candidate's OCR result may pass the threshold but then get filtered by `filter_small_detections()` or `filter_overlapping_detections()`. The `accepted` flag should reflect the final outcome. Simplest approach: after all filtering, build a set of accepted candidates from `Detection.source_candidate` on the surviving detections, then check membership.
- **`BibCandidate` field ordering**: It's a dataclass. New fields with defaults (`ocr_text=None`, `ocr_confidence=None`) must come after existing fields with defaults (`passed=True`, `rejection_reason=None`). This is already safe since those are at the end.
- **Rename `passed` → `passed_validation`**: The `BibCandidateSummary` field was `passed` (mirroring `BibCandidate.passed`). Renaming to `passed_validation` in `BibCandidateTrace` clarifies that it's about the validation stage, not the final verdict. The backward compat validator should handle the old key name.
- **Full-image detections**: These come from `extract_bib_detections()` on the whole image and produce their own `BibCandidate` objects that get appended to `all_candidates`. These full-image candidates don't have the same validation semantics (no white-region filtering). Either exclude them from the trace or mark them with a `source` field. Excluding is simpler — filter `all_candidates` to only white-region candidates when building the trace.

## Acceptance criteria

- [ ] `BibCandidate` has `ocr_text` and `ocr_confidence` fields
- [ ] `detect_bib_numbers()` captures best OCR result on each passed candidate
- [ ] `BibCandidateTrace` replaces `BibCandidateSummary` with `passed_validation`, `ocr_text`, `ocr_confidence`, `accepted`
- [ ] `PhotoResult.bib_trace` replaces `PhotoResult.bib_candidates`
- [ ] Old JSON with `bib_candidates` key and missing OCR fields loads without error
- [ ] All existing tests pass (`venv/bin/python -m pytest`)
- [ ] New tests pass

## Scope boundaries

- **In scope**: trace model, OCR capture in detector, rename, backward compat, tests
- **Out of scope**: consuming traces for tuning (task-065), removing full-image OCR, face pipeline traces
- **Do not** change detection behavior — only capture data that was previously discarded
