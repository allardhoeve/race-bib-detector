# TODO

## Suggestions (Code Review)

These are suggestions identified during a code review. The codebase has excellent separation of concerns and follows a pure-functions philosophy well. The main areas for improvement are reducing duplication, breaking down some overly-large functions, and consolidating mixed-purpose modules.

### High Priority

#### ~~Extract `scale_bounding_boxes()` utility~~ DONE
Added `scale_bbox()` and `scale_detections()` functions to `detection/bbox.py`. Updated `detector.py` and `scan_album.py` to use them. Added unit tests.

#### ~~Split `process_image()` into focused functions~~ DONE
Extracted `save_detection_artifacts()` and `save_detections_to_db()` from `process_image()`. The main function is now a simple orchestrator that calls detection, saves artifacts, and saves to DB.

#### ~~Extract overlapping detection decision logic~~ DONE
Extracted `choose_detection_to_remove()` and `detections_overlap()` helper functions from `filter_overlapping_detections()`. The main function is now a simple loop that uses these helpers. Added 6 unit tests for the new functions.

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

### Low Priority

#### ~~Create Detection dataclass~~ DONE
Created `Detection` dataclass in `detection/types.py` with:
- `bib_number: str`, `confidence: float`, `bbox: Bbox`
- `scale_bbox(factor)` method returning new Detection
- `to_dict()` and `from_dict()` for backwards compatibility
Updated `detector.py`, `filtering.py`, `scan_album.py`, `utils.py` and tests to use Detection.

#### Create PhotoInfo dataclass
**Location:** `sources/google_photos.py`, `scan_album.py`

Image metadata is passed around as dicts with `photo_url`, `thumbnail_url`, `base_url` keys.
Create a `PhotoInfo` dataclass similar to `ImageInfo` in `scan_album.py` but for source data.

#### Create ScanStats dataclass
**Location:** `scan_album.py:174`, `scan_album.py:234`, etc.

Stats returned from scan functions are plain dicts. Could be a dataclass:
```python
@dataclass
class ScanStats:
    photos_found: int
    photos_scanned: int
    photos_skipped: int
    bibs_detected: int
```

#### Add type alias for Bbox
The `Bbox` type alias exists in `detection/types.py` but isn't used consistently.
Update bbox utility functions in `detection/bbox.py` to use `Bbox` type alias.

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


### Data structure

I think we are far enough into the code base that we can see a structure arrive. Should be start to have a data structure?

1. Race photo's are on disk and have remote references (cloud bucket, directory)
2. Optimized images are made of these (grey scale, later on other optimizations). We should have a traceable path to the previous version upto the original of all optimizations.
3. We detect bibs on there, now we can trace back the locations of the bibs through all resizing and such due to our tracing. We should make sure that if we rescale that we have a way to recalculate where they were in order to show the bibs and other boxes properly.

Maybe there are other datapoints that we can make classes out of.

- Propose a structure for this data, how to store it and how to model it. 
- Check if the code would become simpler and better to understand. 
- Then create TODO's to do this.


## Completed

[x] Go through the code, identify places where the code, the structure of the code, or core ideas need changing. Add these suggestions (as suggestions) to TODO.md, with descriptions.

[x] ~~Create preprocessing module skeleton~~ DONE
   [x] Create a preprocessing/ module with pure, deterministic functions (no global state).
   [x] Document your philosophy and guidance (below) in STRUCTURE.md and PREPROCESSING.md.
   [x] Define a single PreprocessConfig object (or dict) that parameterizes all steps.
   [x] Define a run_pipeline(img, config) function that applies steps in order.

[x] ~~Implement image-level normalization~~ DONE
   [x] Implement to_grayscale(img).
   [x] Implement resize_to_width(img, width) (preserve aspect ratio).
   [x] Add unit tests for grayscale + resize (shape, dtype, aspect ratio).
   [x] PreprocessResult includes scale_factor for coordinate mapping back to original.
   [x] Documentation in STRUCTURE.md and PREPROCESSING.md.

[x] ~~Integrate preprocessing into scan_album.py~~ DONE
   [x] Call run_pipeline() before OCR detection
   [x] Save preprocessed images (grayscale, resized) with linked filenames
   [x] Use coordinate mapping to convert detections back to original coordinates
   [x] Display grayscale with bounding boxes in web interface (new "Grayscale" tab)

[x] Change the scan entrypoints to also allow the formats: 6dde41fd and 47. This should rescan only that photo. Document this. This helps with rescanning a single photo after changing the code.
    - Added `rescan_single_photo()` function to scan_album.py
    - Added `get_photo_by_index()` and `get_photo_count()` to db.py
    - CLI now accepts photo hash (8 hex chars) or 1-based index as source argument
    - Example: `./scan_album.py 6dde41fd` or `./scan_album.py 47`

[x] There are a lot of hard-coded values, like the minimum median brightness and such. Move all functional values into a central global variable file so they are easily tweaked. Use all caps for globals and use descriptive names.
    - Created `config.py` with all tunable parameters
    - Updated detection/, preprocessing/, utils.py, and scan_album.py to use config values




### Improve bib detection filtering
# - [ ] Take a new approach to the bib detection. 1. Take all the squares that look like bibs. These are white squares. 
#      There can be multiple. Make these into snippets. Disregard all boxes that contain text that do not look like 
#      bibs. This prevents things like numbers on helmets, like in photo 7286de68 (make this a test). Detect a single (!)
#      number in each bib snippet. This is the largest number we can find. 
# - [ ] Clean up any unused code that was used in the previous way of detecting bibs.
# - [ ] Try to make methods shorter. Some methods have a large number of branches. Things will get more maintainable and
#      more readable if the methods are shorter.
# - [ ] Use tricks like increasing the contrast on each bib snippet to get to better results. Ideas are in "IDEAS.md".

## Backlog

### Explore facial recognition for photo grouping
See IDEAS.md for exploration notes.
