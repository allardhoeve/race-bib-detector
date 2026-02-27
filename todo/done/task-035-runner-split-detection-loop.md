# Task 035: Split `_run_detection_loop` into focused helpers

Extracted from task-033 sub-task B. Standalone.

## Goal

Break the 105-line `_run_detection_loop` function into focused, independently testable
helpers. The function currently mixes: file lookup, bib OCR, bib IoU scoring, image
decoding, face detection, and face scoring in a single deeply-nested loop body.

## Background

The function is hard to read and impossible to unit-test in isolation. The bib and face
paths share a loop but have no logical dependency on each other. Splitting them also
makes the face path optional at the call site without obscuring the bib path.

## Extract these functions

### `_run_bib_detection(reader, image_data, label, artifact_dir)`

```
Args:
    reader: EasyOCR Reader instance
    image_data: raw bytes of the image
    label: BibPhotoLabel (carries content_hash and GT box list)
    artifact_dir: str path for debug artifacts

Returns:
    PhotoResult: status, tp/fp/fn, detection time
    pred_bib_boxes: list[BibBox] — normalised [0,1] coordinates
    image_dims: tuple[int, int] — (width, height) of original image
```

Responsibilities: call `detect_bib_numbers()`, parse int bib numbers, call
`compute_photo_result()`, convert `det.bbox` → normalised `BibBox` list, return dims.

### `_run_face_detection(face_backend, image_data)`

```
Args:
    face_backend: FaceBackend instance
    image_data: raw bytes of the image

Returns:
    list[FaceBox] — normalised [0,1] coordinates, passed candidates only
    Returns [] if image decode fails (cv2.imdecode → None).
```

Responsibilities: decode image bytes with cv2, call
`face_backend.detect_face_candidates()`, filter to `cand.passed`, convert bbox →
normalised `FaceBox`.

### Revised `_run_detection_loop`

After extraction the per-photo body becomes:

```
1. Locate file; skip if missing.
2. Read image bytes.
3. Call _run_bib_detection → (photo_result, pred_boxes, dims).
4. Score bib IoU; accumulate bib_tp/fp/fn/ocr counters.
5. If face_backend and face_gt: call _run_face_detection → pred_face_boxes.
   Look up GT face boxes. Score faces; accumulate face_tp/fp/fn counters.
6. Log progress if verbose.
```

## Naming cleanup

Rename loop-internal accumulator variables (do here, not in task-036):

| Old name | New name |
|---|---|
| `iou_det_tp` | `bib_tp` |
| `iou_det_fp` | `bib_fp` |
| `iou_det_fn` | `bib_fn` |
| `iou_ocr_correct` | `bib_ocr_correct` |
| `iou_ocr_total` | `bib_ocr_total` |
| `face_det_tp` | `face_tp` |
| `face_det_fp` | `face_fp` |
| `face_det_fn` | `face_fn` |

## TDD constraint

- **Existing tests in `tests/test_runner.py` must pass without modification.**
- Write red tests for `_run_bib_detection` and `_run_face_detection` in
  `tests/test_runner.py` (extend the file) before implementing them.
- Minimum required test cases:

**`_run_bib_detection`**
- Mocked `detect_bib_numbers` with two known detections: assert `PhotoResult.detected_bibs`
  matches, `pred_bib_boxes` has correct normalised coordinates, `image_dims` is correct.
- Mocked with zero detections on a label with expected bibs: assert `status == "MISS"`.

**`_run_face_detection`**
- `FakeFaceBackend` (reuse from existing test helpers): assert returned `FaceBox` list
  has expected normalised coordinates for a 100×100 image.
- `FakeFaceBackend` with a deliberately corrupt image (empty bytes): assert returns `[]`.
- `face_backend` that returns a candidate with `passed=False`: assert it is excluded from
  the returned list.

## Coverage audit (from original task-033)

The original requirement said "check if all tests are accounted for." These existing
functions have no tests and contain real logic worth covering:

**`compute_photo_result`** (already exists, just untested)
- All-correct detection: expect `PASS`.
- Partial match (some TP, some FN): expect `PARTIAL`.
- Zero TP with expected bibs: expect `MISS`.
- Zero expected bibs, zero FP: expect `PASS`.
- Zero expected bibs, at least one FP: expect `PARTIAL`.

**`compute_metrics`**
- All-PASS results: precision == recall == f1 == 1.0.
- Mix of TP/FP/FN: verify precision = TP/(TP+FP), recall = TP/(TP+FN).
- All-zero (no detections, no ground truth): no division by zero; f1 == 0.0.

**`compare_to_baseline`** (pure logic, no I/O)
- F1 drops beyond tolerance → `"REGRESSED"`.
- F1 rises beyond tolerance → `"IMPROVED"`.
- F1 within tolerance band → `"NO_CHANGE"`.
- Precision regresses but recall improves → `"REGRESSED"` wins.

These tests go in `tests/test_runner.py`. No new implementation is needed — only tests
for code that already exists.

## Files

- `benchmarking/runner.py` — extract helpers, clean up loop, rename counters
- `tests/test_runner.py` — extend with TDD tests for new helpers + coverage audit
