# TODO


## Usability

- [x] Have a look at the CLI commands in benchmarking. The various CLI tools are becoming much. We should unify them
      into one top-level "bnr" command (bib number recognizer). I like the git command structure with subcommands.
      So this would be "bnr benchmark ui" to launch the ui for benchmarking and such. And "bnr serve" to launch the
      user-facing photo website on 30001.
      **Done:** Created `bnr.py` with git-style subcommands:
      - `bnr serve` - Launch photo viewer (port 30001)
      - `bnr scan <path>` - Scan for bib numbers
      - `bnr benchmark run/ui/list/clean/baseline/scan/stats` - Benchmark commands


---

## Structural Quality Follow-ups

### Preprocessing pipeline purity and metadata
**Location:** `preprocessing/steps.py`, `preprocessing/config.py`

**Tasks:**
- [ ] Remove state from `ResizeStep` (avoid storing `_scale_factor` on the instance); return metadata from `apply()` or use immutable steps per run.
- [ ] Fix `PreprocessResult.resized` so it does not return `None` when preprocessing still occurred (e.g., grayscale-only or CLAHE).

### Candidate metadata consistency
**Location:** `detection/regions.py`

**Tasks:**
- [ ] Recompute `BibCandidate.area`/`relative_area` after padding, or store both pre/post values to avoid inconsistencies in filtering and debugging.

### Full-image OCR validation criteria
**Location:** `detection/detector.py`

**Tasks:**
- [ ] Separate validation rules for full-image OCR vs white-region candidates, or adjust thresholds to avoid rejecting valid full-image detections.

### Test pipeline for filter effectiveness
**Location:** New file, e.g., `tools/evaluate_filters.py`

Create a tool to evaluate detection filters:
- Run detection on a labeled test set
- Compare results with different filter configurations
- Measure precision/recall tradeoffs
- Output report showing which filters catch false positives

---

## Lower Priority: Code Review Suggestions

These are suggestions identified during a code review. The codebase has excellent separation of concerns and follows a pure-functions philosophy well. The main areas for improvement are reducing duplication, breaking down some overly-large functions, and consolidating mixed-purpose modules.

### Split `utils.py` into focused modules
**Location:** `utils.py`

This file mixes unrelated utilities:
- Image manipulation (`save_bib_snippet`, `draw_bounding_boxes_on_gray`)
- Bounding box utilities (`compute_bbox_hash`, `get_snippet_path`)

Split into:
- `url_utils.py` - URL manipulation
- `image_utils.py` - Image download/manipulation
- `bbox_utils.py` - Bounding box operations

### Remove duplication in scan service image iteration
**Location:** `scan/service.py`

Code duplication in `scan_album()` and `scan_local_directory()` - both define nearly identical `make_images()` and `fetch_factory()` generators. Extract a generic factory function or decorator.

### Simplify web UI data loading
**Location:** `web/app.py:120-190`

The `get_photo_with_bibs()` function is 70 lines with complex branching. Split into:
- `load_photo_metadata(photo_hash)`
- `determine_image_source(photo)`
- `load_bib_detections(photo_id)`
- `enrich_detections_with_snippets(bibs, cache_filename)`

### Add structured logging
**Location:** Multiple entry points

When operations fail, users get minimal context. Add:
- `--verbose` flag for full tracebacks
- Structured logging with context
- Save error logs to file for review

### Document hash inconsistency
**Location:** `db.py:15` vs `utils.py:23`

Two different hashing approaches exist:
- Photo identification: SHA256, 8 chars (`db.py`)
- Cache file naming: MD5, 12 chars (`utils.py`)

Add docstrings explaining when to use which.

---

## Lower Priority: Testing Gaps

- No integration tests for full pipeline
- No tests for web UI routes
- No tests for sources module (local scanning)
- No tests for edge cases (corrupt images, invalid URLs)

---

## Backlog

### Explore facial recognition for photo grouping
See IDEAS.md for exploration notes.
