# TODO


## High Priority: Improve White Region Detection for Gray/Off-White Bibs

### Problem
White region detection misses bibs that aren't bright white. Example: photo b54bd347 has bibs 405 and 411 that are detected by full-image OCR but missed by white region detection.

**Root cause analysis (photo b54bd347):**
- Bib 21 (detected): median brightness 178, 43% pixels pass threshold 200
- Bib 405 (missed): median brightness 159, only 15% pixels pass threshold 200
- Bib 411 (missed): median brightness 158, only 7% pixels pass threshold 200

**Additional examples (photos c23577b0, a407a4b9):**
- Faces detected as candidates: median brightness 177-193, 33-39% white pixels
- Actual bibs missed: median brightness 81-119, only 2-3% white pixels
- Result: heads detected instead of bibs (full-image OCR still finds numbers)

The fixed `WHITE_THRESHOLD=200` is too aggressive for gray/off-white bibs common in outdoor race photos with varying lighting. In overcast conditions, faces often appear brighter than bibs.

### Proposed Solutions

#### 1. CLAHE preprocessing before thresholding
**Location:** `detection/regions.py` or `preprocessing/`

Apply Contrast Limited Adaptive Histogram Equalization (CLAHE) to normalize brightness before white region detection. Testing shows CLAHE improves brightness:
- 405: median 159 → 210 (66% white at threshold 200)
- 411: median 158 → 194 (45% white at threshold 200)

```python
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)
```

**Pros:** Normalizes varying lighting conditions, preserves local contrast
**Cons:** May increase false positives in already-bright areas

#### 2. Multi-threshold approach
**Location:** `detection/regions.py`

Run white region detection at multiple thresholds (e.g., 180, 200, 220) and merge candidates.

**Pros:** Catches bibs across brightness range
**Cons:** More computation, need deduplication logic

#### 3. Adaptive thresholding
**Location:** `detection/regions.py`

Replace fixed threshold with adaptive (local) thresholding:
```python
adaptive = cv2.adaptiveThreshold(
    gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, -10
)
```

**Pros:** Handles varying lighting within single image
**Cons:** Many more contours (5000+ vs 3), need better filtering

#### 4. Lower WHITE_THRESHOLD to 180
**Location:** `config.py`

Simple fix: lower threshold from 200 to 180.

**Pros:** Simplest change
**Cons:** May increase false positives, doesn't address root cause

### Recommended approach
Start with **Option 1 (CLAHE)** as it addresses the root cause (varying lighting) without significantly increasing false positives. Combine with slightly lower threshold (190) for best results.

### Architecture Decision: Class-Based Preprocessing Steps

Before implementing CLAHE, we need to decide on the preprocessing pipeline architecture. Currently, `preprocessing/normalization.py` uses pure functions. With 4+ preprocessing steps planned (CLAHE, multi-threshold, adaptive threshold, etc.), a more structured approach is needed.

#### Class-Based Steps with Common Interface
```python
# preprocessing/steps.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

class PreprocessStep(ABC):
    """Base class for preprocessing steps."""

    @abstractmethod
    def apply(self, img: np.ndarray) -> np.ndarray:
        """Apply this step. Must be pure (no mutation)."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging/debugging."""
        pass

@dataclass(frozen=True)
class GrayscaleStep(PreprocessStep):
    dtype: np.dtype = np.uint8

    def apply(self, img: np.ndarray) -> np.ndarray:
        return to_grayscale(img, self.dtype)

    @property
    def name(self) -> str:
        return "grayscale"

@dataclass(frozen=True)
class CLAHEStep(PreprocessStep):
    clip_limit: float = 2.0
    tile_size: tuple[int, int] = (8, 8)

    def apply(self, img: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=self.clip_limit, tileGridSize=self.tile_size)
        return clahe.apply(img)

    @property
    def name(self) -> str:
        return f"clahe(clip={self.clip_limit})"

# Pipeline becomes a list of steps
@dataclass
class Pipeline:
    steps: list[PreprocessStep]

    def run(self, img: np.ndarray) -> PreprocessResult:
        current = img.copy()
        intermediates = {"original": img}
        for step in self.steps:
            current = step.apply(current)
            intermediates[step.name] = current
        return PreprocessResult(intermediates=intermediates, ...)

# Usage
pipeline = Pipeline(steps=[
    GrayscaleStep(),
    CLAHEStep(clip_limit=2.0),
    ResizeStep(target_width=1280),
])
result = pipeline.run(image)
```

**Pros:**
- Clear interface for adding new steps (`PreprocessStep.apply`)
- Each step is self-contained with its own config (frozen dataclass)
- Easy to compose different pipelines (e.g., with/without CLAHE)
- Steps can be reordered, added, removed dynamically
- Better for experimentation and A/B testing
- Intermediates tracked automatically per-step

**Cons:**
- More abstraction overhead
- Slight learning curve
- Need to handle steps that return multiple outputs (resize returns scale_factor)
- 

#### Recommendation: Option B (Class-Based Steps)

For this project, **Option B** is recommended because:

1. **Multiple planned enhancements**: CLAHE, adaptive threshold, multi-threshold, and potentially more. A proper interface prevents the pipeline from becoming a mess of conditionals.

2. **Experimentation support**: Easy to swap steps, try different orderings, A/B test configurations.

3. **Self-documenting**: Each step class documents its parameters and purpose. `CLAHEStep(clip_limit=2.0)` is clearer than `config.clahe_clip_limit=2.0`.

4. **Composable**: Can create preset pipelines (e.g., `OUTDOOR_PIPELINE`, `INDOOR_PIPELINE`) with different step combinations.

5. **Debugging**: Each step produces named intermediate output, making it easy to visualize what each step does.

**Migration path:**
1. Create `PreprocessStep` base class and `Pipeline` class
2. Wrap existing `to_grayscale` and `resize_to_width` as `GrayscaleStep` and `ResizeStep`
3. Update `run_pipeline()` to use the new `Pipeline` internally (backwards compatible)
4. Add `CLAHEStep` as the first new step
5. Gradually add more steps as needed

**Tasks:**
- [x] Create `PreprocessStep` ABC in `preprocessing/steps.py`
- [x] Implement `GrayscaleStep`, `ResizeStep` wrapping existing functions
- [x] Create `Pipeline` class to orchestrate steps
- [x] Update `run_pipeline()` to use `Pipeline` internally (grayscale-first)
- [x] Simplify `PreprocessResult` to only store `original` and `processed` (no redundant color paths)
- [x] Add `CLAHEStep` implementation (ready for use)
- [ ] Enable CLAHE in `build_pipeline()` and test on sample album
- [ ] Monitor false positive rate

---

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
