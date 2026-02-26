# task-027: Wire face detection into benchmark runner

**Status:** pending

## Goal

Make `run_benchmark()` actually run face detection on each photo and populate
`BenchmarkRun.face_scorecard` with real TP/FP/FN metrics, so face P/R/F1 are no longer null.

## Changes

### `benchmarking/runner.py`

- Add imports: `load_face_ground_truth`, `FaceBox` (from `.ground_truth`); `score_faces` (check
  whether already imported — add if missing); `get_face_backend` (from `faces`).
- Extend `_run_detection_loop()` signature: add `face_backend: FaceBackend | None` and
  `face_gt: FaceGroundTruth` params.
- Add inner-loop face detection block following ghost.py pattern (lines 320–376):
  - Decode bytes → RGB.
  - Call `detect_face_candidates()`.
  - Filter passed → normalize → `score_faces()`.
  - Accumulate `face_det_tp`, `face_det_fp`, `face_det_fn`.
- Return `FaceScorecard` alongside `BibScorecard`.
- In `run_benchmark()`:
  - Load `face_gt = load_face_ground_truth()`.
  - Instantiate backend with try/except (warn and set `None` on failure).
  - Pass both to `_run_detection_loop()`.
  - Assign returned `FaceScorecard` to `benchmark_run.face_scorecard`.

### `benchmarking/cli/commands/benchmark.py`

After the existing bib scorecard print block, add a face scorecard print block (precision,
recall, F1). Guard with `if run.face_scorecard is not None`.

## Tests

File: `tests/benchmarking/test_runner.py`

- `test_face_scorecard_populated()` — run benchmark on a small synthetic GT; assert
  `face_scorecard is not None` and all fields are non-negative integers.
- `test_face_backend_failure_graceful()` — patch `get_face_backend` to raise; assert run
  completes with `face_scorecard is None` and bib scoring is unaffected.

## Scope boundary

- Do **not** change `score_faces()`, `FaceScorecard`, or `FaceGroundTruth`.
- No parameter tuning (see task-028/029).
- No link scoring changes (see task-031).
