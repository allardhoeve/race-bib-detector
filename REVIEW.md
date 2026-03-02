# Python Code Review: google-photos-startnumber-recognizer

**Scope**: entire package (excluding `venv/`, `__pycache__/`)
**Python version**: >=3.14
**Files reviewed**: 140

## Critical

No critical issues found. The SQL f-string patterns in `db.py` (lines 26, 127) use only hardcoded internal values, not user-controlled input, so they do not represent an exploitable injection vector.

## Important

| File:Line | Category | Issue | Suggested Fix |
|-----------|----------|-------|---------------|
| db.py:250 | Missing None guard | In `insert_photo()` IntegrityError handler, `cursor.fetchone()[0]` crashes with `TypeError` if the duplicate row was deleted between the failed INSERT and the SELECT (race condition under concurrent access). | `row = cursor.fetchone(); if row is None: raise RuntimeError(f"Photo {photo_url} vanished during insert"); return row[0]` |
| benchmarking/runner.py:554 | Long function / SRP | `_run_detection_loop()` is ~158 lines orchestrating bib detection, face detection, scoring, and linkage — multiple responsibilities in one function. Hard to test components in isolation. | Extract `_run_face_detection_phase()` and `_run_link_scoring_phase()` as separate helpers. Keep loop iteration in main function. |
| detection/detector.py:82 | Long function | `detect_bib_numbers()` is ~128 lines covering image loading, preprocessing, candidate extraction, per-region OCR, full-image fallback, filtering, and deduplication. | Extract `_ocr_on_candidates()`, `_ocr_full_image_fallback()`, `_finalize_detections()` as private helpers. |
| scan/pipeline.py:151 | Excessive parameters | `process_image()` has ~12 parameters (`reader`, `face_backend`, `fallback_face_backend`, `conn`, `skip_existing`, etc.). Hard to call, mock, and extend. | Bundle into a `ProcessConfig` dataclass. Signature becomes `(config: ProcessConfig, image_data, cache_path)`. |
| benchmarking/runner.py:565 | Excessive parameters | `_run_detection_loop()` has ~11 parameters including optional backends, ground truth stores, and config. | Create a `RunContext` dataclass. Signature becomes `(reader, photos, index, images_dir, verbose, ctx: RunContext)`. |
| cache_cleanup.py:101 | High cyclomatic complexity | `cleanup_unreferenced_cache()` has ~21 branches checking each cache directory sequentially with deep nesting. Hard to follow and test. | Extract `_cleanup_directory(dir, pattern_fn)` helper. Loop over a list of directory configs instead of sequential if-chains. |
| scan/pipeline.py:191-254 | Complex nested logic | Face detection section has nested fallback logic: primary backend → confidence fallback → secondary backend with IoU dedup. High branch count, tightly coupled. | Extract `_detect_faces_with_fallback(image_rgb, primary, fallback, config)` returning a flat `list[FaceDetection]`. |
| detection/regions.py:80-101, 162-191 | Code duplication | Validation filter logic (aspect ratio, relative area, brightness thresholds) is duplicated between `validate_detection_region()` and `find_bib_candidates()`. Same checks in identical order. | Extract `_validate_candidate_filters(aspect_ratio, relative_area, brightness)` → returns rejection reason or None. ~20 lines deduplicated. |
| cache_cleanup.py + photo.py + utils.py | Scattered concept | Cache directory paths (`DEFAULT_*_DIR` constants) are defined independently in three modules with no single source of truth. Easy to get out of sync. | Consolidate all cache path constants into `photo.py` (where `ImagePaths` already lives). Import from there in `cache_cleanup.py` and `utils.py`. |
| Multiple: ghost.py, scoring.py, sets.py, detection/types.py, faces/types.py | Inconsistent serialization | Six different `to_dict()`/`from_dict()` patterns: some use Pydantic `model_dump()`/`model_validate()`, some are custom, some wrap Pydantic in a `to_dict()` method. Naming is inconsistent. | Standardize: Pydantic models use only `model_dump()`/`model_validate()`. Dataclasses use `to_dict()`/`from_dict()`. Remove redundant wrappers. |
| detection/bbox.py:26-79 + geometry.py:32-55 | Convergent subsystems | `bbox_iou()` and `rect_iou()` compute identical IoU logic on different representations. `bbox_iou()` converts to rect format then reimplements the computation instead of calling `rect_iou()`. | Have `bbox_iou()` call `rect_iou()` after converting via `bbox_to_rect()`, or unify into a single function. |

## Nice-to-Have

| File:Line | Category | Issue | Suggested Fix |
|-----------|----------|-------|---------------|
| db.py:212-434 | `Optional[X]` → `X \| None` | 10 uses of `Optional[str]`, `Optional[int]`, `Optional[dict]` in function signatures. Python 3.14 supports `X \| None` natively. | Replace `Optional[X]` with `X \| None` throughout db.py; remove `from typing import Optional`. |
| preprocessing/config.py:48 | `Optional[int]` → `int \| None` | `target_width: Optional[int] = TARGET_WIDTH` uses legacy typing syntax. | `target_width: int \| None = TARGET_WIDTH`; remove unused `Optional` import. |
| benchmarking/runner.py:284 | Swallowed exception | `except Exception:` in `get_package_versions()` silently sets version to "unknown" with no logging. Correct behavior, but a debug log would aid troubleshooting. | `except Exception: logger.debug("Failed to get %s version", pkg, exc_info=True); versions[pkg] = "unknown"` |
| benchmarking/runner.py:248-264 | Narrow exception types | `get_git_info()` catches `(CalledProcessError, FileNotFoundError)` but not `PermissionError` or other `OSError` subclasses that could occur. | Broaden to `except (subprocess.CalledProcessError, OSError):` for robustness. |
| benchmarking/app.py:43 | Info leak in error response | `str(exc)` on `RequestValidationError` includes Pydantic internals (field names, types, validation details). Acceptable for internal tool, but leaks implementation details. | `errors = [{"field": e.get("loc", [])[-1:], "msg": e["msg"]} for e in exc.errors()]; return JSONResponse(status_code=400, content={"errors": errors})` |
| benchmarking/identities.py:18 | Missing error handling | `load_identities()` checks `path.exists()` then calls `json.load()` with no handling for corrupted JSON (`JSONDecodeError`). | Wrap in `try/except json.JSONDecodeError as e: logger.error(...); return []`. |
| db.py:426 | Excessive parameters | `insert_face_detection()` has 8 parameters. Below the critical threshold but could benefit from a data object. | Create `FaceDetectionInput` dataclass to bundle parameters. |
| photo.py:214 | Excessive parameters | `ImagePaths.for_cache_path()` has 8 directory-override parameters. | Create an `ImagePathsConfig` dataclass with all override fields (None defaults). |
| benchmarking/ground_truth.py | Convergent containers | `BibGroundTruth`, `FaceGroundTruth`, `LinkGroundTruth` share ~50% duplicated CRUD methods (`add_photo`, `get_photo`, `has_photo`, `remove_photo`, `to_dict`, `from_dict`). | Extract a generic `PhotoLabelContainer[T]` base class with common CRUD. Subclasses define schema-specific logic only. |
| benchmarking/schemas.py | Parallel types | `BibBoxIn`/`BibBoxOut` and `FaceBoxIn`/`FaceBoxOut` have identical fields. Two parallel type hierarchies for the same data shape. | Merge into single `BibBox` and `FaceBox` Pydantic models used for both request and response. |
| benchmarking/label_utils.py:17-22, 91-101 | Scattered concept | `_filtered_hashes()` and `filter_results()` apply the same filter-by-type pattern but on different data types. Two mental models for one concept. | Unify or inline — each is called from ~2 places. |

## Postponed

| File:Line | Category | Issue | Reason |
|-----------|----------|-------|--------|
| db.py:26, 127 | SQL f-string in DDL/PRAGMA | `f"PRAGMA table_info({table})"` and `f"ALTER TABLE face_clusters ADD COLUMN {col} REAL"` use f-strings in SQL statements. Values are all hardcoded internal strings (not user input), and SQLite PRAGMA/DDL don't support parameterized queries. | Defensive concern only — no exploitable path today. Add a whitelist assertion if the functions ever accept external input. |
| benchmarking/ground_truth.py | Missing schema version validation | Loaders don't verify the file's schema version matches `SCHEMA_VERSION = 3`. Could silently load incompatible data if schema evolves. | Pydantic `model_validate()` provides structural validation already. Worth adding an explicit check when the next schema migration occurs. |
| benchmarking/runner.py | Mixed exception handling styles | Some `except` blocks use `except ValueError: pass`, others use `except Exception as exc:` with logging. Inconsistent intent signaling. | Style issue; each individual handler is correct for its context. Standardize during next runner refactor (task-035/036). |
