# TODO - Benchmark Runner

Goal: Implement a runner that evaluates detection accuracy against ground truth.

## Decisions

- **Batch operation**: Run detection on all photos in the selected split or full set as a batch job.
- **Depends on**: todo_labeling.md (ground truth must exist).
- **Output**: Combined approach - detailed metrics (for interpretation) plus summary judgement (IMPROVED/REGRESSED/NO CHANGE) with exit code.
- **Split usage**:
  - `iteration`: Used during development for fast feedback
  - `full`: Used at the end to validate changes generalize (avoids overfitting)
- **Judgement criteria**:
  - REGRESSED: If precision OR recall drops (beyond tolerance threshold)
  - IMPROVED: If either precision or recall improves (and neither drops)
  - NO CHANGE: Otherwise
- **Tolerance**: Configurable threshold in config.py to handle noise (e.g., 0.5%)
- **Baseline**: Store a committed `baseline.json` that represents "current known good"
- **Baseline scope**: One baseline for `full` split only. The `iteration` split reports metrics without baseline comparison (used for fast feedback during development).

## Tasks

- [x] Load `benchmarking/ground_truth.json` and validate schema.
- [x] Run detection for each photo in the selected split (iteration or full).
- [x] Compare detected vs expected bibs per photo.
- [x] Compute per-photo TP/FP/FN and aggregate metrics (precision, recall, F1).
- [x] Store results with metadata (see below).
- [x] Compare against baseline and produce judgement (IMPROVED/REGRESSED/NO CHANGE).
- [x] Return appropriate exit code (0 = ok, 1 = regressed).
- [x] Implement `update-baseline` command that offers to update if metrics improve on `full` split.

## Run Metadata Stored

Essential:
- Git commit hash (and dirty flag if uncommitted changes)
- Timestamp
- Split used (iteration/full)
- Metrics (precision, recall, F1, TP/FP/FN totals)
- Per-photo results (for detailed comparison)

Environment:
- Python version
- Key package versions: easyocr, opencv-python, torch, numpy
- Hostname
- GPU info if CUDA available
- Total runtime

## Implementation

- `benchmarking/runner.py` - Core benchmark runner
- `benchmarking/cli.py` - CLI commands: `benchmark`, `update-baseline`

Usage:
```bash
# Run benchmark on iteration split (fast, for development)
python -m benchmarking.cli benchmark

# Run benchmark on full split (for validation)
python -m benchmarking.cli benchmark -s full

# Run quietly (no per-photo output)
python -m benchmarking.cli benchmark -q

# Update baseline if improved
python -m benchmarking.cli update-baseline
```

## Initial Baseline (2024-02-03)

Full split (113 photos):
- Precision: 90.7%
- Recall: 87.5%
- F1: 89.1%
