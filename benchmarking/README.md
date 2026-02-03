# Benchmarking System

Evaluate bib number detection accuracy against a manually labeled ground truth.

## Quick Start

```bash
# 1. Scan photos directory
python -m benchmarking.cli scan

# 2. Launch web UI for labeling and inspection
python -m benchmarking.cli ui
# Open http://localhost:30002

# 3. Run benchmark
python -m benchmarking.cli benchmark -s full

# 4. Update baseline if improved
python -m benchmarking.cli update-baseline
```

## Web UI Routes

The unified web app (http://localhost:30002):

| Route | Description |
|-------|-------------|
| `/labels/` | Photo labeling UI |
| `/labels/<hash>` | Label specific photo |
| `/benchmark/` | List of benchmark runs |
| `/benchmark/<run_id>/` | Inspect a specific run |

## CLI Commands

```bash
# Scanning and labeling
scan              # Scan photos/ and update index
stats             # Show labeling statistics
ui                # Launch web UI

# Benchmarking
benchmark         # Run on iteration split (fast feedback)
benchmark -s full # Run on all photos
benchmark -q      # Quiet mode (no per-photo output)
update-baseline   # Update baseline if metrics improved

# Run management
benchmark-list    # List all saved runs
benchmark-inspect # Show URL to inspect a run
benchmark-clean   # Clean old runs (--keep-latest N, --keep-baseline)
```

## Splits

- **iteration**: Subset of photos (~50%) for fast development feedback
- **full**: ALL labeled photos for comprehensive validation

The `full` split is used for baseline comparison and should be run before committing changes.

## Metrics

| Metric | Description |
|--------|-------------|
| Precision | TP / (TP + FP) - How many detections were correct |
| Recall | TP / (TP + FN) - How many bibs were found |
| F1 | Harmonic mean of precision and recall |

Per-photo status:
- **PASS**: All expected bibs found, no false positives
- **PARTIAL**: Some bibs found or has false positives
- **MISS**: None of the expected bibs found

## Data Files

| File | Description |
|------|-------------|
| `ground_truth.json` | Labels: bibs, tags, split per photo |
| `photo_index.json` | SHA256 hash → file path mapping |
| `baseline.json` | Current baseline metrics (full split) |
| `results/<run_id>/` | Saved runs with artifacts |

## Ground Truth Schema

```json
{
  "version": 1,
  "tags": ["dark_bib", "no_bib", "blurry_bib", ...],
  "photos": {
    "<sha256_hash>": {
      "content_hash": "<sha256_hash>",
      "bibs": [123, 456],
      "tags": ["dark_bib"],
      "split": "iteration"
    }
  }
}
```

### Tags

| Tag | Description |
|-----|-------------|
| `dark_bib` | Bib is in shadow or poorly lit |
| `light_bib` | Bib is overexposed or washed out |
| `blurry_bib` | Bib text is blurry |
| `obscured_bib` | Bib is partially hidden |
| `partial_bib` | Only part of bib visible in frame |
| `no_bib` | Photo intentionally has no bibs (false positive test) |
| `light_faces` | Faces that might be mistaken for bibs |
| `other_banners` | Non-bib text/banners in image |

## Regression Detection

When running `benchmark -s full`:

| Judgement | Condition | Exit Code |
|-----------|-----------|-----------|
| IMPROVED | Precision or recall increased (neither decreased) | 0 |
| REGRESSED | Precision or recall decreased beyond tolerance | 1 |
| NO_CHANGE | Within tolerance threshold | 0 |

Tolerance is configured in `config.py` (default: 0.5%).

## Architecture

```
benchmarking/
├── cli.py           # CLI entry point
├── ground_truth.py  # Ground truth data structures
├── photo_index.py   # File hash → path mapping
├── runner.py        # Benchmark execution
├── web_app.py       # Unified Flask web UI
├── ground_truth.json
├── photo_index.json
├── baseline.json
└── results/         # Saved benchmark runs
```
