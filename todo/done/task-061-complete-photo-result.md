# Task 061: Complete PhotoResult with per-photo scorecards, confidence, and timing

Independent of task-060 (pred_links). Both should land before the next benchmark run.

## Goal

Enrich `PhotoResult` so a single `run.json` contains everything needed to analyse detection quality per photo — IoU-based scorecards, confidence scores, and separate face timing — without re-running the pipeline.

## Background

The runner computes per-photo IoU scorecards (`score_bibs`, `score_faces`, `score_links`) and confidence values, but only accumulates aggregates — the per-photo detail is discarded. The existing `tp/fp/fn` on PhotoResult is **number-matching** ("did bib 415 appear in the detected list?"), which conflates two distinct failure modes: the detector never finding the bib region vs. finding it but OCR misreading the number. There is also no confidence on predicted boxes and no face detection timing.

The key value of per-photo scorecards is the **GT-centric view** — for each labeled bib:
- **Detection miss**: the detector drew no box overlapping the GT bib (the region was missed entirely).
- **OCR miss**: the detector found the region (IoU match) but read the wrong number.
- **Success**: region found AND number correct.

`score_bibs()` already separates these (`detection_tp/fn` vs `ocr_correct/ocr_total`) but the per-photo result is discarded after aggregation. Similarly for faces: there is zero per-photo face detection quality info today — you cannot tell which photos have missed faces without re-running.

Without this data:
- Cannot distinguish "detector didn't see the bib" from "OCR failed on a found bib".
- Cannot filter photos by face detection quality (e.g. "show photos where a GT face was missed").
- Confidence-based analysis (e.g. "are low-confidence bibs more likely to be OCR errors?") requires re-running.

## Context

- `benchmarking/runner.py` — `PhotoResult` (line ~72), `_run_bib_detection` (line ~370), `_run_face_detection` (line ~418), `_run_detection_loop` (line ~504)
- `benchmarking/scoring.py` — `score_bibs()`, `score_faces()`, `score_links()` return per-photo scorecards; `match_boxes()` returns `MatchResult` with `tp: list[tuple[int,int]]`, `fp: list[int]`, `fn: list[int]`
- `detection/types.py` — `Detection.confidence: float` (bib OCR confidence)
- `faces/types.py` — `FaceCandidate.confidence: float | None` (face detection confidence)
- `benchmarking/ground_truth.py` — `BibBox`, `FaceBox` models (would gain optional `confidence` field)

## Changes

### Modified: `benchmarking/ground_truth.py`

Add optional `confidence` field to both box models (None for GT boxes, populated for predictions):

```python
class BibBox(BaseModel):
    # ... existing fields ...
    confidence: float | None = None  # OCR confidence (predictions only)

class FaceBox(BaseModel):
    # ... existing fields ...
    confidence: float | None = None  # detection confidence (predictions only)
```

### Modified: `benchmarking/runner.py`

1. **Add fields to `PhotoResult`:**

```python
class PhotoResult(BaseModel):
    # ... existing fields ...

    # Per-photo IoU scorecards (None for old runs without this data)
    bib_scorecard: BibScorecard | None = None
    face_scorecard: FaceScorecard | None = None
    link_scorecard: LinkScorecard | None = None

    # Separate face detection timing
    face_detection_time_ms: float | None = None
```

2. **In `_run_bib_detection`**: carry `det.confidence` onto `BibBox`:

```python
pred_bib_boxes.append(BibBox(
    x=x1 / img_w, y=y1 / img_h,
    w=(x2 - x1) / img_w, h=(y2 - y1) / img_h,
    number=det.bib_number,
    confidence=det.confidence,  # NEW
))
```

3. **In `_run_face_detection`**: carry `cand.confidence` onto `FaceBox`, and return timing:

```python
def _run_face_detection(face_backend, image_data) -> tuple[list[FaceBox], float]:
    """Return (face_boxes, detection_time_ms)."""
    start = time.time()
    # ... existing detection code ...
    pred_face_boxes.append(FaceBox(
        x=..., y=..., w=..., h=...,
        confidence=cand.confidence,  # NEW
    ))
    elapsed_ms = (time.time() - start) * 1000
    return pred_face_boxes, elapsed_ms
```

4. **In `_run_detection_loop`**: store per-photo scorecards and face timing:

```python
photo_sc = score_bibs(pred_bib_boxes, label.boxes)
photo_result.bib_scorecard = photo_sc  # NEW

pred_face_boxes, face_time_ms = _run_face_detection(...)
photo_result.face_detection_time_ms = face_time_ms  # NEW
photo_face_sc = score_faces(pred_face_boxes, gt_face_boxes)
photo_result.face_scorecard = photo_face_sc  # NEW

photo_link_sc = score_links(...)
photo_result.link_scorecard = photo_link_sc  # NEW
```

### Modified: `benchmarking/routes/ui/benchmark.py`

Add new fields to the `include` set in `model_dump()`:

```python
include={
    ...,
    'bib_scorecard', 'face_scorecard', 'link_scorecard',
    'face_detection_time_ms',
}
```

### Modified: `benchmarking/templates/benchmark_inspect.html`

Update details panel to show per-photo IoU metrics alongside existing number-match counts. Example: show `Bib IoU: 2/0/1` and `Face IoU: 3/1/0` next to existing `TP/FP/FN: 2/0/1`.

## Tests

Extend `tests/test_runner_models.py`:

- [ ] `test_photo_result_with_scorecards()` — verify round-trip serialization with embedded scorecards
- [ ] `test_photo_result_backward_compat()` — verify old run.json without new fields loads with None defaults

Extend `tests/test_runner.py`:

- [ ] `test_bib_box_has_confidence()` — verify pred_bib_boxes carry confidence values
- [ ] `test_face_box_has_confidence()` — verify pred_face_boxes carry confidence values
- [ ] `test_photo_result_has_scorecards()` — verify bib_scorecard/face_scorecard populated after detection

## Verification

```bash
venv/bin/python -m pytest tests/test_runner.py tests/test_runner_models.py tests/test_scoring.py -v
```

Manual: run a benchmark, inspect `run.json` — verify per-photo entries have `bib_scorecard`, `face_scorecard`, `confidence` on boxes, and `face_detection_time_ms`.

## Pitfalls

- `BibBox` and `FaceBox` are shared between GT and predictions. The `confidence` field must be optional (None for GT) and excluded from GT serialization via `exclude_none=True` (already used).
- Old `run.json` files lack the new fields — all new fields must default to None for backward compatibility.
- `_run_face_detection` signature changes (returns tuple) — update the one call site in `_run_detection_loop`.

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `BibBox` and `FaceBox` predictions carry `confidence` values
- [ ] `PhotoResult` has `bib_scorecard`, `face_scorecard`, `link_scorecard` per photo
- [ ] `PhotoResult` has `face_detection_time_ms` separate from bib `detection_time_ms`
- [ ] Old run.json files load without errors (backward compat)
- [ ] Inspect page details panel shows per-photo IoU metrics

## Scope boundaries

- **In scope**: persisting per-photo scorecards, confidence, face timing, inspect page display
- **Out of scope**: per-box match assignments (which pred matched which GT), overlay color changes based on IoU (follow-up), changing scoring logic
- **Do not** change `score_bibs()`, `score_faces()`, `score_links()` signatures
