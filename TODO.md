# TODO

## Suggestions (Code Review)

These are suggestions identified during a code review. The codebase has excellent separation of concerns and follows a pure-functions philosophy well. The main areas for improvement are reducing duplication, breaking down some overly-large functions, and consolidating mixed-purpose modules.

### High Priority

#### Split `utils.py` into focused modules
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

### Medium Priority

#### Remove duplication in scan_album.py image iteration
**Location:** `scan_album.py:206-217`, `239-251`

Code duplication in `scan_album()` and `scan_local_directory()` - both define nearly identical `make_images()` and `fetch_factory()` generators. Extract a generic factory function or decorator.

#### Consolidate grayscale image reference logic
**Location:** `detection/detector.py:60-62`, `100-101`

The logic for choosing which grayscale image to use for brightness checking is duplicated. Define once at the top of the function.

#### Extract brightness check utility
**Location:** `detection/regions.py:69-72`, `detector.py` (similar)

Brightness threshold logic is checked in similar ways in multiple places:
```python
median_brightness = np.median(region)
mean_brightness = np.mean(region)
if median_brightness < MEDIAN_BRIGHTNESS_THRESHOLD or mean_brightness < MEAN_BRIGHTNESS_THRESHOLD:
    continue
```

Extract into `is_bright_enough(region)` in `detection/validation.py`.

#### Simplify web UI data loading
**Location:** `web/app.py:120-190`

The `get_photo_with_bibs()` function is 70 lines with complex branching. Split into:
- `load_photo_metadata(photo_hash)`
- `determine_image_source(photo)`
- `load_bib_detections(photo_id)`
- `enrich_detections_with_snippets(bibs, cache_filename)`

#### Add structured logging
**Location:** Multiple entry points

When operations fail, users get minimal context. Add:
- `--verbose` flag for full tracebacks
- Structured logging with context
- Save error logs to file for review

#### Document hash inconsistency
**Location:** `db.py:15` vs `utils.py:23`

Two different hashing approaches exist:
- Photo identification: SHA256, 8 chars (`db.py`)
- Cache file naming: MD5, 12 chars (`utils.py`)

Add docstrings explaining when to use which.

### Testing Gaps

- No integration tests for full pipeline
- No tests for web UI routes
- No tests for sources module (Google Photos, local scanning)
- No tests for edge cases (corrupt images, invalid URLs)




### Data Structure Formalization

**Analysis complete.** The codebase has clear data flow patterns but several areas where formalization would improve maintainability and debuggability.

#### Correct Pipeline (4 stages)

```
1. IMAGE RETRIEVAL & CACHING
   Source (URL/File) → Cache (MD5 hash) → cached image on disk
   - Link to original source preserved

2. PREPROCESSING
   Cached image → resize → grayscale → preprocessed images
   - Each step saved to disk with link to previous
   - Enables web interface debugging/transparency

3. BIB CANDIDATE DETECTION
   Preprocessed image → find white regions → filter candidates
   - Candidates filtered by: size, contrast, aspect ratio, noise
   - Candidate regions saved/visualized for debugging
   - THIS STAGE WAS MISSING FROM PREVIOUS ANALYSIS

4. NUMBER DETECTION (OCR)
   Bib candidates → OCR → validate numbers → filter overlaps
   - Bounding boxes drawn on preprocessing output
   - Numbers and confidence scores saved
```

#### Key Issues Identified
1. **Photo metadata scattered** - `ImageInfo`, database rows, and web app dicts all represent photos differently
2. **Coordinate system ambiguity** - bboxes exist in original or OCR coords with no explicit tracking
3. **Scale factor recomputation** - `detect_bib_numbers` computes scale_factor but `scan_album.py` recomputes it from image dimensions
4. **Path conventions scattered** - cache, gray_bbox, snippet paths computed in different places
5. **Bib candidates not exposed** - white region detection happens but regions aren't saved/visualized separately
6. **No lineage tracking** - can't trace a detection back through preprocessing steps


#### High Priority: Create `DetectionPipeline` result structure
**Location:** `detection/types.py`

Bundle all pipeline outputs for transparency/debugging:

```python
@dataclass
class PipelineResult:
    """Complete result from the detection pipeline."""
    # Stage 2: Preprocessing
    preprocess_result: PreprocessResult

    # Stage 3: Bib candidates
    all_candidates: list[BibCandidate]  # ALL found, including rejected
    passed_candidates: list[BibCandidate]  # Only those that passed filters

    # Stage 4: Number detection
    detections: list[Detection]  # Final validated detections

    # Metadata for coordinate mapping
    scale_factor: float  # original_width / ocr_width

    @property
    def ocr_grayscale(self) -> np.ndarray:
        return self.preprocess_result.ocr_grayscale
```

---

#### Medium Priority: Save preprocessing stages to disk
**Location:** `preprocessing/pipeline.py`, new save functions

Each preprocessing step should be saveable with lineage:

```python
@dataclass
class PreprocessArtifact:
    """A saved preprocessing artifact with lineage."""
    path: Path
    stage: str  # "original", "resized", "grayscale", "resized_grayscale"
    parent_path: Path | None  # Link to previous stage
    dimensions: tuple[int, int]

def save_preprocessing_artifacts(
    result: PreprocessResult,
    base_path: Path,
) -> list[PreprocessArtifact]:
    """Save all preprocessing stages to disk with lineage."""
    ...
```

---

#### Medium Priority: Save bib candidates visualization
**Location:** New function in `utils.py` or `detection/`

```python
def save_candidates_visualization(
    image: np.ndarray,
    candidates: list[BibCandidate],
    output_path: Path,
) -> None:
    """Draw all candidates on image (green=passed, red=rejected)."""
    ...
```

---

#### Medium Priority: Create `ImagePaths` dataclass
**Location:** New `paths.py` or in `utils.py`

Path conventions are scattered across `utils.py` and `sources/cache.py`:

```python
@dataclass
class ImagePaths:
    cache_path: Path
    gray_bbox_path: Path
    candidates_path: Path  # NEW: visualization of bib candidates
    snippets_dir: Path

    @staticmethod
    def for_photo_url(photo_url: str) -> "ImagePaths": ...

    def snippet_path(self, bib_number: str, bbox: list) -> Path: ...
    def preprocessing_path(self, stage: str) -> Path: ...  # NEW
```

---

#### Medium Priority: Create unified `Photo` dataclass
**Location:** New `types.py` at root

Unify `ImageInfo` (scan_album.py), database rows, and web app dicts:

```python
@dataclass
class Photo:
    photo_url: str
    photo_hash: str  # 8-char SHA256
    album_url: str
    thumbnail_url: str | None = None
    cache_path: Path | None = None
    source_type: Literal["google_photos", "local_file"] = "google_photos"
    id: int | None = None  # None until persisted

    @property
    def is_local(self) -> bool:
        return self.source_type == "local_file"
```

---

#### Lower Priority
- **FilteringConfig dataclass** - Bundle filtering parameters for testability
- **ScanStats dataclass** - Replace stats dict with typed structure
- **WhiteRegionConfig** - Bundle region detection parameters (already in config.py, just formalize)
- **Coordinate system tags** - Track which coord system a bbox is in

---

#### Web Interface Enhancements (to support debugging)

Once the data structures above are in place, the web interface can show:

1. **Preprocessing tab** - Show each preprocessing stage (original → resized → grayscale)
2. **Candidates tab** - Show all bib candidates with green (passed) / red (rejected) boxes
3. **Detections tab** - Current grayscale+bbox view (already exists)
4. **Lineage view** - Click a detection to see: which candidate → which preprocessing stage → original image

This requires the pipeline to save intermediate artifacts, which the data structures above enable.


## Completed
## Backlog

### Explore facial recognition for photo grouping
See IDEAS.md for exploration notes.
