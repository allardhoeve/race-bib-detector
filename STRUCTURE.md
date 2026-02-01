# Project Structure

This document describes the architecture and organization of the Google Photos Bib Number Recognizer.

## Directory Layout

```
google-photos-startnumber-recognizer/
├── scan_album.py          # Main entry point for album scanning
├── web_viewer.py          # Web UI for browsing detections
├── list_detections.py     # CLI to list detected bib numbers
├── download_by_bib.py     # Download photos by bib number
├── db.py                  # Database operations
├── utils.py               # Shared utilities
├── schema.sql             # Database schema
├── preprocessing/         # Image preprocessing module
│   ├── __init__.py        # Module exports
│   ├── config.py          # Configuration dataclass
│   ├── normalization.py   # Grayscale, resize operations
│   └── pipeline.py        # Main run_pipeline() function
├── tests/
│   ├── test_bib_detection.py
│   ├── test_preprocessing.py
│   └── samples/           # Sample images for testing
├── cache/                 # Downloaded image cache
└── bibs.db                # SQLite database
```

## Module Design Principles

### Preprocessing Module (`preprocessing/`)

The preprocessing module follows these design principles:

1. **Pure Functions**: All operations are pure functions `(input) -> output` with no mutation of original arrays. This makes testing straightforward and behavior predictable.

2. **Immutable Configuration**: `PreprocessConfig` is a frozen dataclass. All parameters are validated early, and helpful error messages guide users to fix issues.

3. **Type Normalization**: Consistent dtypes throughout. Grayscale images use `uint8` by default, matching OpenCV conventions.

4. **Coordinate Mapping**: `PreprocessResult` includes scale factors and helper methods to map detections from resized images back to original coordinates.

See [PREPROCESSING.md](PREPROCESSING.md) for detailed preprocessing documentation.

## Photo Identification

Photos are identified by an 8-character **photo hash** derived from the photo URL using SHA-256. This hash is stable across re-scans and database changes. See [CLAUDE.md](CLAUDE.md) for details.

## Database Schema

The SQLite database (`bibs.db`) contains:

- `photos`: Photo metadata (URL, thumbnail, cache path)
- `bib_detections`: Detected bib numbers with confidence and bounding boxes

See `schema.sql` for the full schema definition.
