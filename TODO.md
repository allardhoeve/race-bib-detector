# TODO


## Medium Priority: Full-Image Scan Evaluation

### Evaluate full-image scan contribution
**Location:** `detection/detector.py`

The full-image OCR scan runs after white region detection as a fallback. Questions:
1. How many additional detections does it find that white regions missed?
2. What's the false positive rate compared to white region detections?
3. Is the extra processing time justified?

**Tasks:**
- [ ] Add logging/metrics to track detection sources in production
- [ ] Create test pipeline that runs detection with/without full-image scan
- [ ] Analyze results on a sample album to measure contribution

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
- URL manipulation (`clean_photo_url`, `get_full_res_url`)
- Image downloading (`download_image`, `download_image_to_file`)
- Image manipulation (`save_bib_snippet`, `draw_bounding_boxes_on_gray`)
- Bounding box utilities (`compute_bbox_hash`, `get_snippet_path`)

Split into:
- `url_utils.py` - URL manipulation
- `image_utils.py` - Image download/manipulation
- `bbox_utils.py` - Bounding box operations

### Remove duplication in scan_album.py image iteration
**Location:** `scan_album.py:206-217`, `239-251`

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
- No tests for sources module (Google Photos, local scanning)
- No tests for edge cases (corrupt images, invalid URLs)

---

## Backlog

### Explore facial recognition for photo grouping
See IDEAS.md for exploration notes.

---

## Completed

- [x] Add `ocr_image`, `ocr_grayscale`, `ocr_dimensions` properties to `PreprocessResult`
- [x] Create `DetectionResult` dataclass bundling detection outputs
- [x] Create `BibCandidate` dataclass with filtering metadata
- [x] Integrate `BibCandidate` throughout pipeline (deprecate `find_white_regions`)
- [x] Update documentation (DETECTION.md, STRUCTURE.md)
- [x] Phase 1: Create `Photo` dataclass as anchor for lineage tracking
- [x] Phase 2: Add lineage to `Detection` (source, source_candidate fields)
- [x] Phase 3: Expand `DetectionResult` to `PipelineResult` with all candidates
- [x] Phase 4: Update `detect_bib_numbers()` to populate lineage
- [x] Phase 5: Create `ImagePaths` dataclass for consolidated path management
- [x] Phase 6: Web interface enhancements (Candidates tab, keyboard shortcuts)
