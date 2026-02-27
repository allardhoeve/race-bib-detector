# task-031: Wire autolink into benchmark runner

**Status:** pending
**Depends on:** task-027 (face detection in runner), task-030 (autolink predictor)

## Goal

Replace the stub `LinkScorecard(link_tp=0, ...)` in `run_benchmark()` with real link
predictions from `predict_links()`, so `link_scorecard` reports meaningful
precision/recall/F1.

## Changes

### `benchmarking/runner.py`

- Import `predict_links` from `faces.autolink`.
- Import `score_links` from `.scoring` (add if not already imported).
- Confirm `load_link_ground_truth` is already imported (it should be).
- After the per-photo face detection block (added in task-027), call:

  ```python
  autolink = predict_links(pred_bib_boxes, pred_face_boxes)
  photo_link_sc = score_links(
      predicted_pairs=autolink.pairs,
      gt_bib_boxes=label.boxes,
      gt_face_boxes=face_label.boxes,
      gt_links=link_gt.get_links(label.content_hash),
  )
  # accumulate link_tp/fp/fn across photos
  ```

- Replace stub `LinkScorecard(link_tp=0, ...)` with values accumulated above.

### `benchmarking/cli/commands/benchmark.py`

Print link scorecard (precision, recall, F1, gt_link_count) alongside bib and face
scorecards. Guard with `if run.link_scorecard is not None`.

## Tests

File: `tests/benchmarking/test_runner_links.py`

- `test_link_scorecard_not_stub()` — run on a photo with 1 face + 1 bib in GT + 1 GT link;
  assert `link_scorecard.link_tp >= 0` and `gt_link_count > 0`.
- `test_link_scorecard_zero_when_no_gt_links()` — photo with no GT links in the ground
  truth → `gt_link_count == 0`.

## Scope boundary

- Uses only the task-030 predictor (single-face rule).
- Cluster-based inheritance is deferred.
- Do **not** change `score_links()` or `LinkScorecard`.
