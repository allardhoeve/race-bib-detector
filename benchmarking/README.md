# Benchmarking System

Evaluate bib number detection accuracy against a manually labeled ground truth.

For full design rationale see `docs/BENCHMARK_DESIGN.md`.

## Quick Start

```bash
# 1. Import photos into the benchmark set
bnr benchmark prepare /path/to/photos

# 2. Launch web UI for labeling and inspection
bnr benchmark ui
# Open http://localhost:30002

# 3. Run benchmark (iteration split for quick feedback)
bnr benchmark run

# 4. Run full benchmark and set baseline
bnr benchmark run --full
bnr benchmark baseline
```

## Web UI Routes

The unified web app (http://localhost:30002):

| Route | Description |
|-------|-------------|
| `/` | Landing page with per-step labeling progress |
| `/bibs/` | Bib labeling UI |
| `/bibs/<hash>` | Label bibs for a specific photo |
| `/faces/` | Face labeling UI |
| `/faces/<hash>` | Label faces for a specific photo |
| `/associations/` | Bib-face association UI |
| `/associations/<hash>` | Associate bibs and faces for a specific photo |
| `/benchmark/` | List of benchmark runs |
| `/benchmark/<run_id>/` | Inspect a specific run |

## CLI Commands

All commands are invoked as `bnr benchmark <command>`.

```bash
# Setup and labeling
prepare <dir>         # Import photos from source directory into benchmark set
scan                  # Scan photos/ directory and update the index
stats                 # Show labeling statistics (bib + face)
ui                    # Launch web UI (labels + benchmark inspection)

# Benchmarking
run                   # Run on iteration split (fast feedback)
run --full            # Run on all labeled photos
run -q                # Quiet mode (no per-photo output)
run --note "..."      # Attach a note to this run

# Baseline management
baseline              # Set latest run as baseline (prompts for confirmation)
baseline -f           # Skip confirmation

# Run management
list                  # List all saved runs
clean                 # Remove old runs (keeps 5 most recent by default)
clean --keep-latest N # Keep N most recent runs
clean --keep-baseline # Never delete the baseline run
clean --older-than N  # Only delete runs older than N days

# Frozen snapshots
freeze --name <name>  # Freeze fully-labeled photos as a named snapshot
frozen-list           # List all frozen snapshots
```

## Splits

- **iteration**: Subset of photos for fast development feedback
- **full**: ALL labeled photos for comprehensive validation

Baseline comparison is only available for the `full` split.

## Metrics

| Metric | Description |
|--------|-------------|
| Precision | TP / (TP + FP) — How many detections were correct |
| Recall | TP / (TP + FN) — How many bibs were found |
| F1 | Harmonic mean of precision and recall |

Per-photo status:
- **PASS**: All expected bibs found, no false positives
- **PARTIAL**: Some bibs found or has false positives
- **MISS**: None of the expected bibs found

## Data Files

| File | Description |
|------|-------------|
| `bib_ground_truth.json` | Bib boxes, numbers, scopes, and photo-level bib tags (schema v3) |
| `face_ground_truth.json` | Face boxes, scopes, identities, and photo-level face tags (schema v3) |
| `bib_face_links.json` | Ground truth bib-face associations |
| `suggestions.json` | Ghost labeling suggestions (auto-generated, not hand-labeled) |
| `photo_index.json` | SHA256 hash → file path mapping |
| `results/<run_id>/` | Saved runs with artifacts |

## Ground Truth Schema (v3)

The schema is split across two files. Each photo is keyed by SHA256 content hash.

**bib_ground_truth.json**
```json
{
  "version": 3,
  "photos": {
    "<sha256_hash>": {
      "boxes": [
        {"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.08, "number": "123", "scope": "bib"}
      ],
      "tags": ["dark_bib"],
      "split": "iteration",
      "labeled": true
    }
  }
}
```

**face_ground_truth.json**
```json
{
  "version": 3,
  "photos": {
    "<sha256_hash>": {
      "boxes": [
        {"x": 0.3, "y": 0.1, "w": 0.06, "h": 0.09, "scope": "keep", "identity": "runner_42", "tags": []}
      ],
      "tags": [],
      "labeled": true
    }
  }
}
```

Bounding box coordinates are normalised [0, 1] image space (x, y, w, h).

### Bib box scopes

| Scope | Scored |
|-------|--------|
| `bib` | Yes |
| `bib_clipped` | Yes |
| `not_bib` | No |
| `bib_obscured` | No |

### Face box scopes

| Scope | Description |
|-------|-------------|
| `keep` | Real participant face, included in scoring |
| `exclude` | Visible but irrelevant (spectators, crowd) |
| `uncertain` | Labeler unsure, excluded until resolved |

## Regression Detection

When running `bnr benchmark run --full`:

| Judgement | Condition | Exit Code |
|-----------|-----------|-----------|
| IMPROVED | Precision or recall increased (neither decreased) | 0 |
| REGRESSED | Precision or recall decreased beyond tolerance | 1 |
| NO_CHANGE | Within tolerance threshold | 0 |

Tolerance is configured in `config.py` (default: 0.5%).

## Architecture

```
benchmarking/
├── cli/               # CLI entry points (subcommands)
├── routes/
│   ├── api/           # FastAPI JSON API routers
│   └── ui/            # FastAPI HTML page routers
├── ground_truth.py    # Schema v3: BibBox, FaceBox, BibGroundTruth, FaceGroundTruth
├── runner.py          # Benchmark execution
├── scoring.py         # IoU utilities, BibScorecard, FaceScorecard
├── prepare.py         # Import photos, dedup, ghost labeling
├── ghost.py           # Ghost labeling: auto-suggestions for unlabeled photos
├── tuner.py           # Face parameter sweep
├── app.py             # FastAPI app factory
├── web_app.py         # Uvicorn shim
├── bib_ground_truth.json
├── face_ground_truth.json
├── bib_face_links.json
├── suggestions.json
├── photo_index.json
└── results/           # Saved benchmark runs
```
