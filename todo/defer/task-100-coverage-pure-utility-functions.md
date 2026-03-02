# Task 100: Test coverage for pure utility functions

Independent. No dependencies on other tasks.

**TDD approach: `tdd: strangler rewrite`**

## Goal

Cover four small pure-function clusters that have zero or near-zero test coverage. Each is a self-contained unit with clear inputs and outputs — ideal for strangler rewrite.

## Background

Coverage analysis (2026-03-02) found these functions completely untested. All are pure (no I/O, no DB) and small enough to reimplement in one sitting each.

## Context

- `sources/local.py` — `scan_local_images()`: finds image files in a directory or validates a single file path
- `sources/cache.py` — `get_cache_path()`, `cache_image()`, `load_from_cache()`: URL-to-path hashing and file read/write
- `benchmarking/link_analysis.py` — `_box_center()`, `_inside_torso()`, `_percentile()`: geometric/statistical helpers
- `benchmarking/cli/commands/tune.py` — `_parse_value()`: string-to-int/float/str coercion

## Changes

No structural changes. Each function is reimplemented in place via the strangler cycle.

## Tests

### New: `tests/test_sources_local.py`

- `test_scan_single_image_file()` — returns `[path]` for a valid image
- `test_scan_rejects_non_image_file()` — raises ValueError for `.txt`
- `test_scan_directory_finds_images()` — finds `.jpg`, `.png`, etc.
- `test_scan_directory_deduplicates()` — mixed-case extensions don't duplicate
- `test_scan_empty_directory()` — returns `[]`
- `test_scan_nonexistent_path()` — raises ValueError

### New: `tests/test_sources_cache.py`

- `test_get_cache_path_deterministic()` — same URL always same path
- `test_get_cache_path_different_urls()` — different URLs different paths
- `test_cache_image_creates_dir()` — writes file, creates cache dir
- `test_load_from_cache_exists()` — returns bytes when file present
- `test_load_from_cache_missing()` — returns None when absent

### New: `tests/test_link_analysis_helpers.py`

- `test_box_center()` — correct (cx, cy) for a box
- `test_inside_torso_true()` — bib centroid within torso region
- `test_inside_torso_false()` — bib centroid outside torso region
- `test_percentile_empty()` — returns 0.0
- `test_percentile_single_value()` — returns that value
- `test_percentile_interpolation()` — correct linear interpolation

### Extend: `tests/benchmarking/test_tuners_grid.py` (or new file)

- `test_parse_value_int()` — `"42"` → `42`
- `test_parse_value_float()` — `"3.14"` → `3.14`
- `test_parse_value_string()` — `"abc"` → `"abc"`
- `test_parse_value_strips_whitespace()` — `" 42 "` → `42`

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] Each function group has its own test class or file
- [ ] `sources/local.py` coverage >= 90%
- [ ] `sources/cache.py` coverage >= 90%
- [ ] `_box_center`, `_inside_torso`, `_percentile` all covered
- [ ] `_parse_value` covered for int, float, string inputs
- [ ] No `_old_*` remnants left in codebase

## Scope boundaries

- **In scope**: the four function clusters listed above
- **Out of scope**: `link_analysis.main()` (CLI script, acceptable gap), other functions in these files
- **Do not** modify function signatures or behavior
