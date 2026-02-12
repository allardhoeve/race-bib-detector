# Code Review TODOs (Codex)

Structure and Organization
- TODO: Extract a dedicated `PhotoRepository` (or DB gateway) to centralize SQL and connection handling used in `db.py`, `web/app.py`, and `scan/service.py`. This avoids scattered SQL and makes it easier to mock DB access in tests.
- TODO: Introduce a small `CachePaths` or reuse `photo.ImagePaths` in `scan/pipeline.py` and `web/app.py` to eliminate repeated path math for cache/gray/candidates/snippets directories.
- TODO: Replace ad-hoc `print()` calls across `scan/` and `benchmarking/runner.py` with a shared logging setup so verbosity can be configured and tested.
- TODO: Split `benchmarking/web_app.py` into `templates.py` + `routes.py` (or blueprint modules) to reduce file size and isolate HTML/CSS from request handlers.
- TODO: Move inline HTML templates into separate `.tmpl` files (start with `benchmarking/web_app.py` and `web/templates.py`) to improve maintainability.
- TODO: Move inline CSS into dedicated `.css` files; evaluate whether to serve them as static assets or embed via template includes.
- TODO: If/when moving CSS/HTML to files, add a small static-file serving strategy in Flask.

Hardcoded Values and Configuration
- TODO: Centralize web server ports (`30001`, `30002`) and hosts in config to avoid scattered literals in `bnr.py`, `web/app.py`, and `benchmarking/web_app.py`.

Functions That Are Too Long / Branchy
- TODO: Break up `scan.scan_images()` into smaller functions (cache fetch, per-image processing, stats update, error handling) to reduce branching and make it easier to unit test each piece.
- TODO: Extract the full-image OCR fallback block in `detection/detector.detect_bib_numbers()` into a helper to reduce cyclomatic complexity and make experiments easier.
- TODO: Split `benchmarking/runner.run_benchmark()` into phases (`prepare_run_dirs`, `load_inputs`, `process_photo`, `finalize_metrics`) to improve readability and reuse in tests.
- TODO: Factor `web/app.py:get_photo_with_bibs()` into helpers (load photo row, resolve local/cache path, snippet lookup) to reduce branching and improve testability.

Potential Class-Based Refactors
- TODO: Introduce a `BibDetector` class that owns the EasyOCR reader, preprocess config, and detection steps; this will simplify `scan/pipeline.py` and benchmarking by reusing the same detector instance.
- TODO: Add a `BenchmarkRunner` class that bundles run metadata, pipeline config, artifact output, and metric aggregation; this removes many global functions in `benchmarking/runner.py` and improves test setup.

Missing Tests (Unit/Integration)
- TODO: Add unit tests for `detection/regions.py` to validate candidate filtering, aspect ratio bounds, brightness thresholds, and padding behavior.
- TODO: Add unit tests for `detection/filtering.py` to cover substring-vs-confidence logic, overlap thresholds, and deterministic selection across ties.
- TODO: Add unit tests for `detection/bbox.py` (area, IoU, overlap ratio) to lock down geometry math.
- TODO: Add tests for `db.py` covering `insert_photo` dedupe behavior, `delete_bib_detections`, and `migrate_add_photo_hash`.
- TODO: Add tests for `utils.py` snippet path hashing and image drawing/saving paths (with temp dirs + tiny arrays).
- TODO: Add tests for `scan.is_photo_identifier()` and `run_scan()` routing (path vs hash) using mocks for `scan.scan_local_directory` and `scan.rescan_single_photo`.
- TODO: Add tests for `sources/local.scan_local_images()` to cover single-file input, non-image file, and directory scans with mixed extensions.
- TODO: Add tests for `benchmarking/runner.compute_photo_result()` (edge case: no expected bibs + false positives) and `compare_to_baseline()` (no baseline, regressions, improvements).
- TODO: Add tests for `web/app.py:get_photo_with_bibs()` to verify local vs cached photo handling, snippet filename creation, and presence flags.
