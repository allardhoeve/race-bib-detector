# Task 050: Store predictions and GT boxes in detection loop

Depends on task-049.

## Goal

Populate the four new `PhotoResult` fields (`pred_bib_boxes`, `pred_face_boxes`, `gt_bib_boxes`, `gt_face_boxes`) inside `_run_detection_loop`, so that every benchmark run persists the box data needed for the inspect overlay.

## Background

After task-049 adds the fields, this task wires them up. The predicted boxes are already computed as local variables in the detection loop — they just need to be stored on the `PhotoResult` before they go out of scope. GT boxes are available from the `BibPhotoLabel` and `FacePhotoLabel` that the loop already loads.

## Context

- `benchmarking/runner.py:444` — `_run_detection_loop()`: iterates photos, calls `_run_bib_detection` and `_run_face_detection`
- `benchmarking/runner.py:361` — `_run_bib_detection()` returns `(photo_result, pred_bib_boxes, (img_w, img_h))`
- `benchmarking/runner.py:412` — `_run_face_detection()` returns `list[FaceBox]`
- `benchmarking/runner.py:494-496` — `pred_bib_boxes` is a local variable, used for scoring, then discarded
- `benchmarking/runner.py:509-514` — `pred_face_boxes` is a local variable, used for scoring, then discarded
- `benchmarking/ground_truth.py:113` — `BibPhotoLabel.boxes` carries GT bib boxes
- `benchmarking/ground_truth.py:246` — `FacePhotoLabel.boxes` carries GT face boxes

## Changes

### Modified: `benchmarking/runner.py` — `_run_detection_loop`

After scoring, store the boxes on `photo_result`:

```python
# After phase 2 (bib IoU scoring):
photo_result.pred_bib_boxes = pred_bib_boxes
photo_result.gt_bib_boxes = label.boxes

# After phase 3 (face detection + scoring):
photo_result.pred_face_boxes = pred_face_boxes
if photo_face_label is not None:
    photo_result.gt_face_boxes = photo_face_label.boxes
```

This is 4 assignment lines added to the existing loop body. No structural changes.

## Tests

Extend `tests/test_runner.py`:

- `test_detection_loop_stores_pred_bib_boxes()` — run loop on a small fixture, verify `photo_result.pred_bib_boxes` is a list of `BibBox` (not `None`)
- `test_detection_loop_stores_gt_bib_boxes()` — verify `photo_result.gt_bib_boxes` matches GT input
- `test_detection_loop_stores_face_boxes_when_backend_provided()` — with face backend, verify both `pred_face_boxes` and `gt_face_boxes` are populated
- `test_detection_loop_face_boxes_none_without_backend()` — without face backend, `pred_face_boxes` is `[]` and `gt_face_boxes` is `None`

## Verification

```bash
# Fast tests (no GPU)
venv/bin/python -m pytest tests/test_runner.py tests/test_runner_models.py -v

# Full run to verify JSON output includes boxes
venv/bin/python bnr.py benchmark run -s iteration
# Then check the run JSON:
# python -c "import json; r=json.load(open('benchmarking/results/<run_id>/run.json')); print(r['photo_results'][0].keys())"
```

## Pitfalls

- `pred_face_boxes` is initialised as `[]` before the `if face_backend` block, so it will be `[]` (not `None`) when face detection is disabled. This is intentional — `[]` means "no faces detected", while `None` on `gt_face_boxes` means "no GT available for this photo".
- Storing GT boxes means the run JSON grows, but `BibBox`/`FaceBox` are small (~6 fields each). For 250 photos with ~5 boxes each, this adds ~50KB — negligible vs the existing artifact images.

## Acceptance criteria

- [x] All existing tests still pass (`venv/bin/python -m pytest`)
- [x] New tests pass
- [x] After a benchmark run, the run JSON contains `pred_bib_boxes` and `gt_bib_boxes` in each `photo_results` entry
- [x] When face detection is enabled, `pred_face_boxes` and `gt_face_boxes` are also populated

## Scope boundaries

- **In scope**: wiring existing local variables into `PhotoResult` fields
- **Out of scope**: face clustering (task-051), inspect route (task-052), UI rendering (task-053)
- **Do not** change the detection logic, scoring, or `PhotoResult` field definitions (task-049 owns those)
