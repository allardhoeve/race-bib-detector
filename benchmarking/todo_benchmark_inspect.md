# TODO - Benchmark Inspection

Goal: Provide visual inspection of benchmark results to debug detection issues.

## Problem

When a photo fails detection (MISS or PARTIAL), we need to understand *why*:
- Was the bib too dark/bright?
- Did preprocessing help or hurt?
- Were candidates found but rejected?
- Was OCR confident but wrong?

Currently we only see numbers (expected vs detected). We need to see the actual images and pipeline stages.

## Approach

### 1. Always Save Pipeline Artifacts

The preprocessing pipeline already captures intermediate images in `PipelineStepResults`. We should:
- Save these images to disk during detection (not just in benchmark mode)
- Store paths as attributes on the result objects
- This keeps one code path for both normal operation and benchmarking

**Key principle:** The artifact-saving code lives in the main pipeline, not in benchmark-specific code. This prevents divergence.

### 2. Artifact Storage Structure

For each detection run, save to a consistent location:
```
cache/pipeline/<photo_hash>/
  original.jpg
  grayscale.jpg
  clahe.jpg          (if CLAHE step was used)
  candidates.jpg     (bounding boxes of candidate regions)
  detections.jpg     (final detection overlay)
```

The `photo_hash` provides stable identification across runs.

### 3. Benchmark Run Artifacts

When running a benchmark, additionally save per-run metadata:
```
benchmarking/results/<run_id>/
  run.json           (metrics, metadata, photo_results)
  images/            (symlinks or copies of pipeline artifacts for this run)
```

**Question to resolve:** Should benchmark runs copy artifacts or symlink to cache? Symlinks save space but break if cache is cleared. Copies are self-contained but larger.

### 4. List Available Runs

Add `benchmark-list` command:
```
ID        Date        Split      P      R      F1     Commit
---------------------------------------------------------------
a1b2c3d   2024-02-03  full      90.7%  87.5%  89.1%  abc1234 (baseline)
e4f5g6h   2024-02-03  iteration 84.3%  88.2%  86.2%  abc1234
```

### 5. Visual Inspection UI

Add `benchmark-inspect [run_id]` command that launches a web UI (port 30003):
- If no run_id specified, defaults to the latest run
- If no runs exist, shows error message

Features:
- Select which run to view (dropdown to switch)
- Filter by status: All / PASS / PARTIAL / MISS
- For each photo show:
  - Original image
  - Pipeline stages (grayscale, CLAHE, etc.) with tabs or side-by-side
  - Candidates overlay (showing accepted/rejected regions)
  - Detections overlay with bounding boxes
  - Ground truth bibs vs detected bibs
  - Status indicator (✓ PASS / ◐ PARTIAL / ✗ MISS)
  - Tags from ground truth
- Keyboard navigation (like labeling UI)

### 6. Cleanup Command

Add `benchmark-clean` command (similar to `docker system prune`):
- List runs and their disk usage
- Interactive confirmation before deletion
- Options:
  - `--keep-latest N` - keep the N most recent runs
  - `--keep-baseline` - never delete the baseline run
  - `--older-than DAYS` - only delete runs older than N days
  - `-f, --force` - skip confirmation

## Tasks

### Pipeline Changes
- [x] Add `artifact_dir` parameter to Pipeline and detection functions
- [x] Save intermediate images when `artifact_dir` is set
- [x] Store artifact paths as attributes on StepResult and PipelineStepResults
- [x] Add candidates visualization saving (accepted in green, rejected in red)
- [x] Add detections visualization saving (final bounding boxes)

### Benchmark Runner Changes
- [x] Always save artifacts during benchmark runs
- [x] Store artifact paths in PhotoResult
- [x] Change `--save` behavior: always save run, remove flag (or make it `--no-save`)

### CLI Commands
- [x] Add `benchmark-list` command to show saved runs
- [x] Add `benchmark-inspect [run_id]` command to launch inspection UI (defaults to latest)
- [x] Add `benchmark-clean` command to remove old runs (like `docker system prune`)

### Inspection UI
- [x] Create `benchmarking/viewer_app.py` Flask app
- [x] Photo list view with status filtering
- [x] Photo detail view with pipeline stages
- [x] Image comparison/tabs for different stages
- [x] Keyboard shortcuts for navigation
- [ ] Run selector dropdown (nice-to-have, not essential)

## Decisions

1. **Copies for benchmark artifacts** (not symlinks)
   - Benchmark runs are immutable snapshots
   - Should not break if cache is cleared
   - ~2MB × 225 photos = ~450MB per run is acceptable
   - Use `benchmark-clean` to manage disk space

2. **Cache cleanup via `benchmark-clean` command**
   - Similar to `docker system prune`
   - Interactive by default, `-f` to force
   - Options to keep latest N runs, keep baseline, delete older than N days

## Dependencies

- Requires: todo_benchmark_runner.md (complete)
- Requires: todo_labeling.md (complete)
