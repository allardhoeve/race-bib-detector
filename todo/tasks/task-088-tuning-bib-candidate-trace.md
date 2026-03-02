# Task 088: Bib candidate trace — traces as primary pipeline output

Part of the tuning series (085-094).

**Depends on:** task-085 (pipeline/ package), task-087 (remove full-image OCR)

## Goal

Create `BibCandidateTrace` in `pipeline/types.py` and make it the primary bib output of `SinglePhotoResult`. Each trace records a candidate's complete journey: validation → OCR → acceptance verdict. Replaces the separate `bib_boxes`, `bib_result`, and `BibCandidateSummary` fields.

## Background

Today `SinglePhotoResult` carries three bib representations:
- `bib_result: PipelineResult` — raw detection output with candidates + detections
- `bib_boxes: list[BibBox]` — normalised boxes for accepted detections

And `PhotoResult` in the benchmark carries:
- `bib_candidates: list[BibCandidateSummary]` — validation-only diagnostics (no OCR outcome)

Three views of the same data, with OCR sub-threshold results silently discarded. The trace unifies all of this into one list.

### Data flow after this task

```
detect_bib_numbers() → PipelineResult (internal)
    ↓
run_single_photo() wraps into → list[BibCandidateTrace]
    ↓
SinglePhotoResult.bib_trace  ← THE bib output
    ↓
Need accepted bibs?  → [t for t in bib_trace if t.accepted]
Need bib numbers?    → [t.bib_number for t in bib_trace if t.accepted]
```

## Design decisions

| Question | Decision |
|----------|----------|
| Where does BibCandidateTrace live? | `pipeline/types.py` — it's a pipeline output, used by both consumers |
| What replaces on SinglePhotoResult? | `bib_trace: list[BibCandidateTrace]` replaces `bib_boxes`, `bib_result` |
| Does the trace link to Detection? | No. The trace carries the outcome inline (bib_number, ocr_confidence, accepted). The trace IS the enriched record. |
| OCR data on BibCandidate | Add `ocr_text` and `ocr_confidence` to the dataclass in detection — the pipeline captures what OCR produced |
| Multiple OCR results per candidate | Store only the best (highest confidence valid bib). Sufficient for threshold replay. |

## Context

- `detection/bib/types.py` — `BibCandidate` dataclass (gains `ocr_text`, `ocr_confidence`)
- `detection/bib/detector.py` — per-candidate OCR loop where sub-threshold results are discarded
- `pipeline/single_photo.py` — `run_single_photo()`, `SinglePhotoResult`
- `pipeline/types.py` — where `BibCandidateTrace` will live
- `benchmarking/runner.py` — `BibCandidateSummary` (deleted), `PhotoResult.bib_candidates` (renamed to `bib_trace`)
- `benchmarking/runner.py:_run_detection_loop()` — reads `sp_result.bib_result` and `sp_result.bib_boxes`
- `scan/persist.py` — reads `sp.bib_result` and `sp.bib_boxes`
- `benchmarking/scoring.py:score_bibs()` — takes `list[BibBox]`

## Changes

### Modified: `detection/bib/types.py`

Add OCR outcome fields to `BibCandidate`:

```python
@dataclass
class BibCandidate:
    ...existing fields...
    ocr_text: str | None = None
    ocr_confidence: float | None = None
```

### Modified: `detection/bib/detector.py`

In the per-candidate OCR loop, capture the best valid-bib OCR result regardless of threshold:

```python
for candidate in passed_candidates:
    region = candidate.extract_region(ocr_image)
    results = reader.readtext(region)
    best_bib_conf = 0.0

    for bbox, text, confidence in results:
        cleaned = text.strip().replace(" ", "")
        if is_valid_bib_number(cleaned) and confidence > best_bib_conf:
            best_bib_conf = confidence
            candidate.ocr_text = cleaned
            candidate.ocr_confidence = float(confidence)

        # Existing Detection creation unchanged
        if is_valid_bib_number(cleaned) and confidence > WHITE_REGION_CONFIDENCE_THRESHOLD:
            ...
```

### New: `pipeline/types.py` — BibCandidateTrace

```python
class BibCandidateTrace(BaseModel):
    """Complete journey of one bib candidate through the pipeline."""
    # Geometry (normalised [0,1])
    x: float
    y: float
    w: float
    h: float
    # Candidate properties
    area: int
    aspect_ratio: float
    median_brightness: float
    mean_brightness: float
    relative_area: float
    # Validation verdict
    passed_validation: bool
    rejection_reason: str | None = None
    # OCR outcome (None if rejected before OCR or OCR found nothing valid)
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    # Pipeline verdict
    accepted: bool = False
    bib_number: str | None = None
```

### Modified: `pipeline/single_photo.py`

Build traces in `run_single_photo()` from `PipelineResult`:

```python
bib_trace: list[BibCandidateTrace] = []
if img_w > 0 and img_h > 0:
    sf = bib_result.scale_factor
    accepted_candidates = {
        det.source_candidate for det in bib_result.detections
        if det.source_candidate is not None
    }
    for c in bib_result.all_candidates:
        is_accepted = c in accepted_candidates
        det = next((d for d in bib_result.detections if d.source_candidate is c), None)
        bib_trace.append(BibCandidateTrace(
            x=(c.x * sf) / img_w, y=(c.y * sf) / img_h,
            w=(c.w * sf) / img_w, h=(c.h * sf) / img_h,
            area=c.area, aspect_ratio=c.aspect_ratio,
            median_brightness=c.median_brightness,
            mean_brightness=c.mean_brightness,
            relative_area=c.relative_area,
            passed_validation=c.passed,
            rejection_reason=c.rejection_reason,
            ocr_text=c.ocr_text, ocr_confidence=c.ocr_confidence,
            accepted=is_accepted,
            bib_number=det.bib_number if det else None,
        ))
```

Replace `bib_boxes` and `bib_result` on `SinglePhotoResult`:

```python
@dataclass
class SinglePhotoResult:
    image_dims: tuple[int, int]
    bib_trace: list[BibCandidateTrace]
    bib_detect_time_ms: float
    # ... face fields unchanged for now ...
    # Keep bib_result temporarily for artifact_paths/preprocess_metadata access
    _bib_result: PipelineResult  # internal, not part of public interface
```

Note: `_bib_result` may still be needed by `scan/persist.py` for artifact saving and `preprocess_metadata`. Evaluate whether these can be extracted into the trace or kept as a private field.

### Modified: consumers

**`benchmarking/runner.py`:**
- Delete `BibCandidateSummary` class
- `PhotoResult.bib_candidates` → `PhotoResult.bib_trace: list[BibCandidateTrace] | None`
- `_run_detection_loop()`: read `sp_result.bib_trace` directly instead of building summaries
- Extract bib numbers: `[t.bib_number for t in sp_result.bib_trace if t.accepted and t.bib_number]`
- For scoring: build `list[BibBox]` from accepted traces for `score_bibs()`
- Add backward compat validator on `PhotoResult` for old `bib_candidates` key

**`scan/persist.py`:**
- Read bib numbers from traces for DB storage
- Artifact saving may still need `_bib_result`

**`benchmarking/scoring.py`:**
- `score_bibs()` still takes `list[BibBox]` — callers project from traces

## Tests

Extend `tests/test_runner_models.py`:

- `test_bib_candidate_trace_round_trip` — all fields serialise correctly
- `test_trace_ocr_below_threshold` — `passed_validation=True, ocr_confidence=0.37, accepted=False`
- `test_trace_no_ocr_result` — `passed_validation=True, ocr_text=None, accepted=False`
- `test_trace_accepted_with_bib_number` — `accepted=True, bib_number="142"`
- `test_backward_compat_bib_candidates_key` — old JSON with `bib_candidates` loads into `bib_trace`
- `test_backward_compat_missing_ocr_fields` — old trace JSON loads with defaults

Add to `tests/test_bib_detection.py` (slow):

- `test_candidate_ocr_fields_populated` — detection on test image populates `ocr_text`/`ocr_confidence`

## Verification

```bash
venv/bin/python -m pytest tests/test_runner_models.py -v
venv/bin/python -m pytest
```

## Pitfalls

- **Determining `accepted`**: A candidate's OCR result may pass threshold but get filtered by `filter_small_detections()` or `filter_overlapping_detections()`. Build the accepted set from `Detection.source_candidate` on surviving detections.
- **`_bib_result` for artifacts**: `scan/persist.py` needs `bib_result.artifact_paths` and `bib_result.preprocess_metadata`. Either keep as private field on SinglePhotoResult or extract these onto top-level fields.
- **Scoring still needs BibBox**: `score_bibs()` compares prediction boxes against GT boxes. Project accepted traces into `BibBox` at the call site — a one-liner list comprehension.
- **BibCandidate field ordering**: New fields with defaults must come after existing defaulted fields. Safe since `passed=True` and `rejection_reason=None` are already last.

## Acceptance criteria

- [ ] `BibCandidateTrace` exists in `pipeline/types.py`
- [ ] `BibCandidate` has `ocr_text` and `ocr_confidence` fields
- [ ] `detect_bib_numbers()` captures best OCR result on each passed candidate
- [ ] `SinglePhotoResult.bib_trace` replaces `bib_boxes` (and reduces `bib_result` exposure)
- [ ] `PhotoResult.bib_trace` replaces `PhotoResult.bib_candidates`
- [ ] `BibCandidateSummary` deleted
- [ ] All consumers updated to use traces
- [ ] Backward compat for old JSON
- [ ] All tests pass

## Scope boundaries

- **In scope**: trace type, OCR capture, SinglePhotoResult change, consumer updates, backward compat
- **Out of scope**: face traces (task-089), consuming traces for tuning (task-092)
- **Do not** change detection behavior — only capture data that was previously discarded
