# Project Structure

This document describes the architecture and organization of the Google Photos Bib Number Recognizer.

## Directory Layout

```
google-photos-startnumber-recognizer/
├── scan_album.py           # Main CLI entry point for scanning
├── web_viewer.py           # Thin wrapper to run web interface
├── db.py                   # Database operations
├── utils.py                # Shared utilities (bounding box drawing)
├── schema.sql              # Database schema
│
├── preprocessing/          # Image preprocessing module
│   ├── __init__.py         # Module exports
│   ├── config.py           # PreprocessConfig, PreprocessResult
│   ├── normalization.py    # to_grayscale, resize_to_width
│   └── pipeline.py         # run_pipeline()
│
├── detection/              # Bib number detection module
│   ├── __init__.py         # Module exports
│   ├── bbox.py             # Bounding box geometry utilities
│   ├── validation.py       # Bib number validation
│   ├── regions.py          # White region detection
│   ├── filtering.py        # Detection filtering
│   └── detector.py         # Main detect_bib_numbers()
│
├── sources/                # Image source adapters
│   ├── __init__.py         # Module exports
│   ├── google_photos.py    # Google Photos album scraping
│   ├── local.py            # Local directory scanning
│   └── cache.py            # Image caching utilities
│
├── web/                    # Web interface module
│   ├── __init__.py         # Module exports
│   ├── app.py              # Flask application
│   └── templates.py        # HTML templates
│
├── tests/
│   ├── test_bib_detection.py
│   ├── test_preprocessing.py
│   └── samples/            # Sample images for testing
│
├── cache/                  # Downloaded/processed image cache
│   └── gray_bounding/      # Grayscale images with bounding boxes
│
└── bibs.db                 # SQLite database
```

## Module Design Philosophy

All modules follow these principles:

### 1. Pure Functions

Operations are pure functions `(input) -> output` with no mutation of original data:

```python
# Good: Pure function returns new data
gray = to_grayscale(rgb_image)
bibs = filter_overlapping_detections(detections)

# Original data is never modified
```

### 2. Early Validation

Parameters are validated early with helpful error messages:

```python
config = PreprocessConfig(target_width=50)
config.validate()  # Raises: "target_width=50 is too small..."
```

### 3. Clear Separation of Concerns

Each module has a single responsibility:

| Module | Responsibility |
|--------|---------------|
| `preprocessing/` | Image normalization (grayscale, resize) |
| `detection/` | Bib number detection and filtering |
| `sources/` | Image acquisition from various sources |
| `web/` | User interface |
| `scan_album.py` | Orchestration and CLI |

## Module Details

### preprocessing/

Prepares images for OCR by normalizing size and format.

- **config.py**: `PreprocessConfig` (immutable settings), `PreprocessResult` (pipeline output)
- **normalization.py**: `to_grayscale()`, `resize_to_width()`
- **pipeline.py**: `run_pipeline()` - applies all preprocessing steps

See [PREPROCESSING.md](PREPROCESSING.md) for detailed documentation.

### detection/

Detects and validates bib numbers in images.

- **types.py**: Data structures (`Detection`, `DetectionResult`, `BibCandidate`, `Bbox`)
- **bbox.py**: Geometry utilities (`bbox_area`, `bbox_iou`, `bbox_overlap_ratio`)
- **validation.py**: `is_valid_bib_number()`, `is_substring_bib()`
- **regions.py**: `find_bib_candidates()` - finds candidate bib areas as `BibCandidate` objects
- **filtering.py**: `filter_small_detections()`, `filter_overlapping_detections()`
- **detector.py**: `detect_bib_numbers()` - main entry point, returns `DetectionResult`

### sources/

Adapters for different image sources.

- **google_photos.py**: `extract_images_from_album()` - scrapes shared albums
- **local.py**: `scan_local_images()` - finds images in a directory
- **cache.py**: `get_cache_path()`, `cache_image()`, `load_from_cache()`

### web/

Flask-based web interface for browsing results.

- **app.py**: `create_app()`, `main()` - Flask routes and server
- **templates.py**: HTML templates as string constants

## Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   sources/  │────▶│ preprocessing│────▶│  detection/ │
│             │     │              │     │             │
│ Google      │     │ grayscale    │     │ OCR         │
│ Photos      │     │ resize       │     │ filtering   │
│ Local dir   │     │              │     │ validation  │
└─────────────┘     └──────────────┘     └─────────────┘
                                               │
                                               ▼
                                         ┌─────────────┐
                                         │     db      │
                                         │   bibs.db   │
                                         └─────────────┘
                                               │
                                               ▼
                                         ┌─────────────┐
                                         │    web/     │
                                         │   viewer    │
                                         └─────────────┘
```

## Photo Identification

Photos are identified by an 8-character **photo hash** derived from the photo URL using SHA-256. This hash is stable across re-scans and database changes. See [CLAUDE.md](CLAUDE.md) for details.

## Database Schema

The SQLite database (`bibs.db`) contains:

- `photos`: Photo metadata (URL, thumbnail, cache path, photo_hash)
- `bib_detections`: Detected bib numbers with confidence and bounding boxes

See `schema.sql` for the full schema definition.
