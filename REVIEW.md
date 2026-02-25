# Python Code Review: google-photos-startnumber-recognizer

**Scope**: entire package
**Python version**: >=3.14
**Files reviewed**: 73

---

## Critical

_No critical issues found._

---

## Important

| File:Line | Category | Issue | Suggested Fix |
|-----------|----------|-------|---------------|
| `benchmarking/routes_face.py:32` | Module-level mutable state | `_embedding_index_cache: dict[str, EmbeddingIndex] = {}` is module-level shared state. Leaks between tests; problematic in multi-worker deployments. | Move to Flask app context (`g` or `current_app.extensions`) or wrap in a class with explicit lifecycle. → **[task-013](todo/tasks/task-013-refactor-face-identity-suggestions.md)** |
| `benchmarking/routes_face.py:56–123` `benchmarking/routes_bib.py:36–101` | Code duplication | `label_photo()` and `face_label_photo()` are 65–67 lines each with near-identical structure: filter validation → hash lookup → split selection → next-unlabeled navigation → template render. The "find next unlabeled" loop is copy-pasted verbatim. | Extract shared navigation into `label_utils.find_next_unlabeled_url(...)`. → **[task-012](todo/tasks/task-012-refactor-label-photo-navigation.md)** |
| `benchmarking/routes_face.py:233–302` | Long function / mixed concerns | `face_identity_suggestions()` (68 lines) combines: parameter validation, embedding index building + module-level caching, image loading/decoding, embedding computation, and similarity search. | Extract `_get_embedding_index()`, `_load_image_rgb()` helpers; keep route handler to <30 lines. → **[task-013](todo/tasks/task-013-refactor-face-identity-suggestions.md)** |
| `benchmarking/routes_face.py:277–281` | Resource leak | `Image.open(photo_path)` is never closed; if a crop operation raises, the file handle leaks. | Use `with Image.open(photo_path) as img: img.crop(...)` → **[task-018](todo/tasks/task-018-refactor-misc-cleanups.md)** |
| `benchmarking/runner.py:483–677` | Long function / mixed concerns | `run_benchmark()` is 195 lines orchestrating photo loading, detection execution, metric computation, metadata capture, and file I/O without separation. | Extract `_run_detection_loop()`, `_build_run_metadata()` sub-functions. → **[task-014](todo/tasks/task-014-refactor-run-benchmark.md)** |
| `db.py:51–192` | Long function | `ensure_face_tables()` is 142 lines mixing DDL schema creation and multiple migration steps, making it hard to test migrations independently. | Split into `_create_face_tables()`, `_ensure_album_columns()`, `_create_albums_table()`, `_migrate_album_urls()`. → **[task-015](todo/tasks/task-015-refactor-ensure-face-tables.md)** |
| `geometry.py:32–54` + `benchmarking/scoring.py:27–60` | Duplicated concept | Two IoU implementations exist: `compute_intersection_over_union()` in `geometry.py` (x1,y1,x2,y2 tuples) and `compute_iou()` in `scoring.py` (x,y,w,h boxes). Callers must know which to use. | Keep both (different coordinate domains); remove `rect_iou()` alias; add cross-reference docstrings. → **[task-016](todo/tasks/task-016-refactor-consolidate-iou.md)** |
| `web/app.py:20–27`, `utils.py:19–22`, `cache_cleanup.py:13–19`, `sources/cache.py:10`, `photo.py:16–22` | Scattered constants | Cache directory paths (`CACHE_DIR`, `SNIPPETS_DIR`, `GRAY_BBOX_DIR`, etc.) are defined independently in 5 modules. Changes to cache structure require updates in multiple places. | Consolidate all path definitions in `photo.py` (which already defines `DEFAULT_*` versions). Other modules import from `photo`. → **[task-018](todo/tasks/task-018-refactor-misc-cleanups.md)** |
| `benchmarking/cli.py:1–779` | God module | 779-line file containing 12 command functions with duplicated stat-gathering, validation, and formatting logic. | Split into `benchmarking/cli/commands/photos.py` and `benchmark.py`. → **[task-017](todo/tasks/task-017-refactor-split-cli.md)** |

---

## Nice-to-Have

| File:Line | Category | Issue | Suggested Fix |
|-----------|----------|-------|---------------|
| `benchmarking/routes_face.py:254, 295` | Duplicate import in function | `get_face_embedder()` is imported twice inside `face_identity_suggestions()`. | Import once at the top of the function. → **[task-013](todo/tasks/task-013-refactor-face-identity-suggestions.md)** |
| `benchmarking/routes_face.py:277` | Import inside function | `import cv2 as _cv2` at line 277 shadows the module-level `import cv2` at line 8 — confusing. | Remove the inner import; use the module-level `cv2` directly. → **[task-018](todo/tasks/task-018-refactor-misc-cleanups.md)** |
| `geometry.py:57–59` | Redundant alias | `rect_iou()` is a one-liner that calls `compute_intersection_over_union()` with no added value. | Remove the alias. → **[task-016](todo/tasks/task-016-refactor-consolidate-iou.md)** |
| `web/app.py:90–145` | Route boilerplate | Seven nearly-identical routes each do `send_from_directory(CONSTANT_DIR, filename)` with no logic (~55 lines total). | Use a dict + factory function. See Simplification Tradeoffs below. |
| `benchmarking/label_utils.py:14–34` | Duplicated filter logic | `get_filtered_hashes()` and `get_filtered_face_hashes()` are ~75 % identical: same `filter_type` switch, different GT sources. | Extract a shared `_filtered_hashes()` inner helper. → **[task-018](todo/tasks/task-018-refactor-misc-cleanups.md)** |
| `db.py:19–21` + `photo.py:8–10` | Duplicate hash function | Both `compute_photo_hash()` (photo.py) and `compute_album_id()` (db.py) do `sha256().hexdigest()[:8]` on a string. | Have `db.py` import and reuse `compute_photo_hash()` from `photo.py`. → **[task-018](todo/tasks/task-018-refactor-misc-cleanups.md)** |
| `web/app.py:160–243` | Long function | `get_photo_with_bibs()` (84 lines) makes multiple DB calls and dict-transforms inline. | Extract bib/face lookup into separate helper functions; consider a SQL JOIN for the bib/face fetch. |

---

## Simplification Tradeoffs

These proposals require restructuring module boundaries. Each states what changes so you can make an informed decision.

| Location | Complexity Problem | Proposed Simplification | What Changes | Estimated Gain |
|----------|--------------------|------------------------|--------------|----------------|
| `utils.py`, `cache_cleanup.py`, `photo.py`, `web/app.py`, `sources/cache.py` | 5 modules each define their own cache path constants/helpers; "how do I get a snippet path?" requires reading multiple files | Consolidate all path logic into `photo.ImagePaths` (already well-designed). Move `get_gray_bbox_path()`, `get_candidates_path()`, etc. into `ImagePaths` methods. | Callers in `cache_cleanup.py`, `web/app.py` update to use `ImagePaths` API. No behavioral change — same files on disk. | Eliminates ~60 lines of scattered definitions; CACHE_DIR reduced to 1 source of truth; reduces files-to-read for path questions from 5 to 1. |
| `benchmarking/label_utils.py:14–62` | Two near-identical filter functions duplicating `filter_type` logic | Single `get_filtered_hashes(gt_loader, filter_type)` parameterized function; two thin named wrappers for bib/face | Callers unchanged; internal implementation simplified | ~25 lines removed (40 % reduction in label_utils filter section) |
| `web/app.py:90–145` | 7 mechanical cache-serving routes with no logic | Replace with a dispatch dict + `_make_cache_route()` factory, or a single `/<cache_type>/<filename>` route | Route URLs are unchanged; route definitions become data-driven (less explicit but fully mechanical) | ~55 → ~15 lines (70 % reduction); tradeoff: route list is no longer visible at a glance |

---

## Postponed

| File:Line | Category | Issue | Reason |
|-----------|----------|-------|--------|
| `benchmarking/routes_face.py:1–340` | Module cohesion | Routes module mixes persistence, embedding business logic, identity management, and HTTP | Valid concern but extracting a service layer is a larger refactor; defer until the embedding/identity features stabilise. |
| `benchmarking/routes_bib.py`, `benchmarking/routes_face.py` | GT caching per request | Ground truth is loaded fresh on every request; no caching | GT files are small and fast to load; adding `lru_cache` or Flask `g` caching adds complexity with negligible runtime gain at current scale. |
