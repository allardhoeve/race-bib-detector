# Task 014: Refactor run_benchmark() — extract sub-functions

Medium refactor. Independent of all other pending tasks.

## Goal

`run_benchmark()` in `benchmarking/runner.py:483–678` is 195 lines mixing photo
loading, per-photo detection, IoU accumulation, metadata capture, and file I/O.
Extract the per-photo detection loop and the metadata-building block into named helpers
so the orchestration logic is visible at a glance.

## Current structure

```
run_benchmark()
  ├── setup (run_id, dirs, GT load, split filter)      lines 497–519
  ├── EasyOCR init                                      lines 525–529
  ├── per-photo detection loop (41 lines)               lines 541–607
  │     for label in photos:
  │         detect_bib_numbers(...)
  │         compute_photo_result(...)
  │         iou accumulation
  │         logging
  ├── aggregate metrics                                  lines 609–619
  ├── metadata building (42 lines)                       lines 621–662
  │     git info, PipelineConfig, FacePipelineConfig,
  │     RunMetadata construction
  └── assemble BenchmarkRun + save + return             lines 664–678
```

## Changes

### 1. Extract `_run_detection_loop()`

```python
def _run_detection_loop(
    reader,
    photos: list[BibPhotoLabel],
    index: dict,
    images_dir: Path,
    verbose: bool,
) -> tuple[list[PhotoResult], BibScorecard]:
    """Run detection on all photos; return results and aggregate IoU scorecard."""
    photo_results: list[PhotoResult] = []
    iou_det_tp = iou_det_fp = iou_det_fn = iou_ocr_correct = iou_ocr_total = 0

    for i, label in enumerate(photos):
        # ... (current loop body, lines 542–607)

    bib_scorecard = BibScorecard(
        detection_tp=iou_det_tp,
        detection_fp=iou_det_fp,
        detection_fn=iou_det_fn,
        ocr_correct=iou_ocr_correct,
        ocr_total=iou_ocr_total,
    )
    return photo_results, bib_scorecard
```

### 2. Extract `_build_run_metadata()`

```python
def _build_run_metadata(
    run_id: str,
    split: str,
    note: str | None,
    start_time: float,
) -> RunMetadata:
    """Capture environment and pipeline configuration into RunMetadata."""
    git_commit, git_dirty = get_git_info()
    # ... (current lines 626–662)
    return RunMetadata(...)
```

### 3. Slim down `run_benchmark()`

After extraction:
```python
def run_benchmark(split="full", verbose=True, note=None) -> BenchmarkRun:
    start_time = time.time()
    run_id = generate_run_id()
    run_dir, images_dir = _prepare_run_dirs(run_id)

    gt = load_bib_ground_truth()
    index = load_photo_index()
    photos = gt.get_by_split(split)
    _validate_inputs(gt, index, photos, split)

    if verbose:
        logger.info("Running benchmark on %s photos (split: %s) — run %s", len(photos), split, run_id)

    suppress_torch_mps_pin_memory_warning()
    reader = easyocr.Reader(["en"], gpu=torch.cuda.is_available())

    photo_results, bib_scorecard = _run_detection_loop(reader, photos, index, images_dir, verbose)
    metrics = compute_metrics(photo_results)
    metadata = _build_run_metadata(run_id, split, note, start_time)

    benchmark_run = BenchmarkRun(metadata=metadata, metrics=metrics,
                                  photo_results=photo_results, bib_scorecard=bib_scorecard)
    run_json_path = run_dir / "run.json"
    benchmark_run.save(run_json_path)
    if verbose:
        logger.info("Results saved to: %s", run_dir)
    return benchmark_run
```

Also extract `_prepare_run_dirs(run_id)` for the directory setup (lines 501–504)
and `_validate_inputs(gt, index, photos, split)` for the three ValueError guards
(lines 510–519) if desired — these are optional but clean.

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md).

- Run `pytest tests/` — benchmark runner tests should pass unchanged.
- Run a quick benchmark manually (`python -m benchmarking.cli benchmark --split iteration`)
  and verify output is identical.

## Scope boundaries

- **In scope**: extracting helpers as described. No changes to `BenchmarkRun`, detection
  algorithms, or I/O formats.
- **Out of scope**: changing the detection pipeline, metric formulas, or run file format.
