# Project Structure

This document describes the architecture and organization of the Bib Number Recognizer.

## Directory Layout

```
google-photos-startnumber-recognizer/
├── bnr.py                   # CLI entry point — routes all subcommands
├── config.py                # All tunable parameters (preprocessing, detection, faces, benchmark)
├── photo.py                 # Photo dataclass, compute_photo_hash(), ImagePaths
├── geometry.py              # Shared Bbox type and rect/bbox conversion utilities
├── db.py                    # SQLite helpers (bibs.db — scan results, face embeddings)
├── utils.py                 # Misc utilities (bounding box drawing, hash helpers)
├── logging_utils.py         # Shared logging configuration
├── warnings_utils.py        # Suppression helpers for noisy third-party warnings
│
├── preprocessing/           # Image preprocessing before OCR
│   ├── config.py            # PreprocessConfig, PreprocessResult
│   ├── normalization.py     # to_grayscale(), resize_to_width()
│   ├── steps.py             # Class-based preprocessing steps (CLAHE, etc.)
│   └── pipeline.py          # run_pipeline() function-based API; Pipeline class-based API
│
├── detection/               # Bib number detection pipeline (EasyOCR-based)
│   ├── types.py             # Detection, PipelineResult, BibCandidate, DetectionSource
│   ├── bbox.py              # IoU, area, overlap geometry helpers
│   ├── regions.py           # find_bib_candidates() — white region detection
│   ├── validation.py        # is_valid_bib_number(), is_substring_bib()
│   ├── filtering.py         # filter_small_detections(), filter_overlapping_detections()
│   └── detector.py          # detect_bib_numbers() — main entry point
│
├── faces/                   # Face detection and embedding pipeline
│   ├── types.py             # FaceBbox, FaceCandidate, FaceDetection, FaceModelInfo
│   ├── backend.py           # FaceBackend Protocol + DNN SSD implementation
│   ├── embedder.py          # FaceEmbedder Protocol + implementation
│   ├── artifacts.py         # Save face snippets, preview images, and evidence JSON
│   ├── clustering.py        # Cluster face embeddings by similarity (uses db)
│   ├── autolink.py          # Rule-based bib-face pair predictor (predict_links())
│   └── models/
│       └── opencv_dnn_ssd/  # Bundled DNN SSD model weights
│
├── sources/                 # Image source adapters
│   ├── local.py             # scan_local_images() — find images in a directory
│   └── cache.py             # get_cache_path(), cache_image(), load_from_cache()
│
├── scan/                    # Scan orchestration (used by CLI and web viewer)
│   ├── pipeline.py          # scan_images() — runs detection + face pipeline per photo
│   └── service.py           # run_scan() entry point; resolves face mode from CLI flags
│
├── cli/                     # CLI subcommand parsers (wired into bnr.py)
│   ├── scan.py              # bnr scan <path>
│   ├── album.py             # bnr album list / forget
│   ├── cache.py             # bnr cache commands
│   └── faces.py             # bnr faces cluster
│
├── web/                     # Legacy Flask viewer (bnr serve, port 30001)
│   ├── app.py               # Flask routes for browsing scan results
│   └── templates.py         # HTML templates as string constants
│
├── benchmarking/            # FastAPI benchmark web app + labeling + runner
│   ├── app.py               # create_app() — FastAPI application factory (canonical)
│   ├── web_app.py           # Uvicorn shim: main() launches app on port 30002
│   ├── ground_truth.py      # Schema v3: BibBox, FaceBox, BibGroundTruth, FaceGroundTruth
│   ├── scoring.py           # IoU utils, box matching, BibScorecard, FaceScorecard
│   ├── runner.py            # Benchmark runner (Pydantic models, detection loop, results)
│   ├── ghost.py             # Ghost labeling: run detection and store as suggestions.json
│   ├── prepare.py           # prepare_benchmark(): copy photos, dedup, update index + GT
│   ├── schemas.py           # Pydantic request/response wire models for all API endpoints
│   ├── label_utils.py       # Shared helpers (get_filtered_hashes, find_next_unlabeled_url)
│   ├── photo_index.py       # load_photo_index(), get_path_for_hash()
│   ├── scanner.py           # compute_content_hash(), build_photo_index() for benchmark photos
│   ├── completeness.py      # PhotoCompleteness — tracks per-photo labeling progress
│   ├── identities.py        # load_identities() — known face identity list for autocomplete
│   ├── face_embeddings.py   # Embedding cache + top-k identity search for labeling UI
│   ├── sets.py              # Frozen benchmark snapshot management (freeze / list)
│   ├── tuner.py             # Face parameter sweep (run_face_sweep())
│   ├── templates_env.py     # Shared Jinja2Templates singleton
│   │
│   ├── routes/              # FastAPI routers (split by concern)
│   │   ├── api/
│   │   │   ├── bibs.py      # GET/PUT /api/bibs/<hash>, PUT /api/associations/<hash>
│   │   │   ├── faces.py     # GET/PUT /api/faces/<hash>, identity suggestions, crop
│   │   │   ├── benchmark.py # POST /api/freeze
│   │   │   └── identities.py# GET /api/identities, POST, PATCH
│   │   ├── ui/
│   │   │   ├── labeling.py  # HTML views: bib, face, and link labeling pages
│   │   │   └── benchmark.py # HTML views: benchmark run list + inspection
│   │   └── shims.py         # 301/308 backward-compat redirects for old URLs
│   │
│   ├── services/            # Business logic (no HTTP concerns)
│   │   ├── bib_service.py   # Load/save bib labels; ghost suggestion lookup
│   │   ├── face_service.py  # Load/save face labels; identity suggestions
│   │   ├── association_service.py  # Bib-face link ground truth read/write
│   │   ├── identity_service.py     # Create / rename identities across GT files
│   │   └── completion_service.py   # Completion checks used by labeling navigation
│   │
│   ├── cli/                 # benchmarking CLI commands (bnr benchmark …)
│   │   └── commands/
│   │       ├── benchmark.py # run, list, clean, baseline
│   │       ├── photos.py    # prepare, scan, stats, freeze, frozen-list
│   │       └── tune.py      # bnr benchmark tune (face parameter sweep)
│   │
│   ├── templates/           # Jinja2 HTML templates
│   ├── static/              # JS (labeling.js, *_labeling_ui.js) + test page
│   ├── tune_configs/        # YAML configs for face parameter sweeps
│   ├── photos/              # Benchmark photo files (content-addressed)
│   ├── results/             # Saved benchmark run JSON files
│   └── frozen/              # Frozen benchmark snapshot JSON files
│
├── tests/                   # pytest test suite
│   ├── conftest.py          # --slow flag; skip @pytest.mark.slow by default
│   ├── benchmarking/        # Benchmarking-specific integration tests
│   ├── samples/             # Sample images for unit tests
│   └── test_*.py            # Unit and integration tests
│
├── docs/                    # Documentation
│   ├── STRUCTURE.md         # This file
│   ├── BENCHMARK_DESIGN.md  # Benchmark design rationale
│   ├── BENCHMARK_UI_DESIGN.md
│   ├── API_DESIGN.md
│   ├── DETECTION.md
│   ├── PREPROCESSING.md
│   ├── STANDARDS.md
│   ├── INSTALLATION.md
│   └── TUNING.md
│
├── cache/                   # Runtime cache (gitignored)
│   ├── gray_bounding/       # Grayscale images with detection boxes
│   ├── snippets/            # Cropped bib number snippets
│   └── faces/               # Face snippets, previews, evidence JSON
│
├── bibs.db                  # SQLite database (scan results + face embeddings)
├── pyproject.toml           # Project metadata and tool configuration
└── requirements.txt         # Python dependencies
```

## Module Responsibilities

### Top-level modules

| File | Responsibility |
|------|----------------|
| `bnr.py` | Unified CLI entry point; builds the argument parser and dispatches subcommands |
| `config.py` | Single source of truth for all tunable constants (preprocessing, OCR, faces, benchmark) |
| `photo.py` | `Photo` dataclass and `compute_photo_hash()` — 8-character SHA-256 prefix used as the canonical photo identifier throughout the system |
| `geometry.py` | `Bbox` type (list of 4 corner points) and `rect_to_bbox` / `bbox_to_rect` converters shared by detection and face modules |
| `db.py` | SQLite access layer for scan results and face embeddings (`bibs.db`) |

### preprocessing/

Prepares images for OCR by normalising size and contrast. `run_pipeline()` is the main entry point; a class-based `Pipeline` API is also available for custom step sequences.

### detection/

EasyOCR-based bib number detection. `detect_bib_numbers()` in `detector.py` orchestrates preprocessing, white-region candidate finding (`regions.py`), OCR, number validation (`validation.py`), and overlap filtering (`filtering.py`).

### faces/

Face detection, embedding, and artifact generation. `backend.py` defines the `FaceBackend` Protocol with an OpenCV DNN SSD implementation. `embedder.py` provides face embeddings. `artifacts.py` writes snippet images and evidence JSON. `autolink.py` provides `predict_links()` — a rule-based bib/face pairing function.

### sources/

Thin adapters for image acquisition: `local.py` finds image files in a directory; `cache.py` manages the local image cache.

### scan/

Ties detection and faces together into a reusable scan pipeline. `pipeline.py`'s `scan_images()` processes a list of images end-to-end and writes results to the database. `service.py` provides the `run_scan()` entry point used by the CLI.

### cli/

One module per top-level CLI subcommand (`scan`, `album`, `cache`, `faces`). Each module exports an `add_*_subparser()` function wired into `bnr.py`.

### web/

Legacy Flask viewer (`bnr serve`, port 30001) for browsing scan results stored in `bibs.db`. Not related to the benchmarking web app.

### benchmarking/

FastAPI application for benchmark labeling and inspection (`bnr benchmark ui`, port 30002). Key sub-areas:

- **app.py** — `create_app()` registers all routers and serves static files; `web_app.py` is the uvicorn entry point.
- **ground_truth.py** — schema v3 Pydantic models: `BibBox`, `FaceBox`, `BibGroundTruth`, `FaceGroundTruth`, persisted in `bib_ground_truth.json` and `face_ground_truth.json`.
- **runner.py** — `run_benchmark()` evaluates detection accuracy against ground truth; Pydantic models for `PhotoResult`, `BenchmarkRun`, `PipelineConfig`, etc.
- **scoring.py** — `compute_iou()`, `match_boxes()`, `BibScorecard`, `FaceScorecard` for precision/recall/F1 metrics.
- **ghost.py** — pre-computes detection suggestions from the actual pipeline and stores them in `suggestions.json` for display in the labeling UI.
- **routes/api/** — JSON API routers (bibs, faces, identities, benchmark).
- **routes/ui/** — HTML page routers (labeling views, benchmark inspection).
- **routes/shims.py** — 301 redirects for old URL paths.
- **services/** — Business logic separated from HTTP: bib, face, association, identity, and completion services.
- **schemas.py** — Pydantic wire models for all request bodies and response shapes.

## Data Flow

### Scan pipeline

```
sources/       preprocessing/     detection/        db
local.py  -->  run_pipeline() --> detect_bib_numbers() --> bibs.db
                                                     ^
                                  faces/             |
                                  backend.py --------+
                                  embedder.py
```

### Benchmark pipeline

```
benchmarking/photos/
      |
      v
runner.py (run_benchmark())
      |-- detection.detect_bib_numbers()
      |-- faces.backend  (face detection)
      |-- faces.autolink (bib-face pairs)
      |
      v
scoring.py (IoU matching, scorecards)
      |
      v
benchmarking/results/<run_id>/result.json
```

### Labeling web app

```
Browser  <-->  benchmarking/routes/api/   (JSON CRUD)
               benchmarking/routes/ui/    (HTML pages)
               benchmarking/services/     (business logic)
               benchmarking/ground_truth.py  (JSON files on disk)
```

## Photo Identification

Photos are identified by an **8-character content hash** (first 8 hex digits of SHA-256). In the scan pipeline the hash is derived from the photo URL or file path via `compute_photo_hash()` in `photo.py`. In the benchmark the hash is derived from file contents via `compute_content_hash()` in `benchmarking/scanner.py`. See `docs/STANDARDS.md` for the canonical rules.

## Key Data Files (benchmarking/)

| File | Contents |
|------|----------|
| `photo_index.json` | Maps content hash → list of relative file paths |
| `bib_ground_truth.json` | Per-photo bib box annotations (schema v3) |
| `face_ground_truth.json` | Per-photo face box annotations (schema v3) |
| `bib_face_links.json` | Per-photo bib-face association ground truth |
| `face_identities.json` | Known identity names for autocomplete |
| `suggestions.json` | Ghost-labeling suggestions (not ground truth) |
| `results/<id>/` | Saved benchmark run JSON and per-photo artifacts |
| `frozen/<name>.json` | Frozen photo-set snapshots for reproducible runs |
