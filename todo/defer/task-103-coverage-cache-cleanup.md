# Task 103: Test coverage for cache cleanup

Independent. No dependencies on other tasks.

**TDD approach: `tdd: test-wrap`**

## Goal

Cover `cache_cleanup.py` — filesystem cleanup logic at 17% coverage. These functions delete cached artifacts for albums or remove orphaned files. Incorrect cleanup silently deletes valid cache or leaves orphaned files filling disk.

## Background

Coverage analysis (2026-03-02) found almost the entire module untested. The functions have filesystem side effects (file deletion, directory globbing) and some require DB access. Use `tmp_path` for filesystem and mock/stub for DB.

## Context

- `cache_cleanup.py` — `_is_under_cache()`, `_delete_paths()`, `_paths_for_cache_file()`, `delete_album_cache()`, `delete_album_cache_by_id()`, `cleanup_unreferenced_cache()`
- `db.py` — `get_connection()`, `list_album_cache_entries()`, `list_cache_entries()` (need mocking)
- The module uses module-level `CACHE_DIR` — tests should monkeypatch this to a tmp directory

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| How to isolate filesystem? | Monkeypatch `cache_cleanup.CACHE_DIR` (and sub-dirs) to point at `tmp_path` |
| How to handle DB calls? | Monkeypatch `db.get_connection` / `db.list_album_cache_entries` / `db.list_cache_entries` to return test data |

## Tests

### New: `tests/test_cache_cleanup.py`

**`_is_under_cache`**:
- `test_path_under_cache_returns_true()` — path inside CACHE_DIR
- `test_path_outside_cache_returns_false()` — path outside CACHE_DIR

**`_delete_paths`**:
- `test_deletes_existing_file()` — file removed, count incremented
- `test_dry_run_does_not_delete()` — file still exists after dry run
- `test_skips_non_cache_paths()` — path outside cache dir skipped
- `test_counts_missing_files()` — nonexistent path counted as missing
- `test_skips_directories()` — directory path skipped
- `test_deduplicates_paths()` — same path twice only processed once

**`_paths_for_cache_file`**:
- `test_includes_base_paths()` — cache, gray_bbox, candidates dirs listed
- `test_includes_snippet_globs()` — matching snippet files found

**`delete_album_cache`**:
- `test_deletes_cache_for_entries()` — given cache entries, deletes matching files
- `test_skips_entries_without_cache_path()` — entries with no cache_path ignored

**`cleanup_unreferenced_cache`**:
- `test_deletes_unreferenced_files()` — files not in DB listing get deleted
- `test_keeps_referenced_files()` — files in DB listing survive

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `cache_cleanup.py` coverage >= 80%
- [ ] Both dry-run and real-delete paths tested
- [ ] Safety guard (_is_under_cache) tested in both directions

## Scope boundaries

- **In scope**: all functions in `cache_cleanup.py`
- **Out of scope**: actual DB integration — use mocks/monkeypatches
- **Do not** modify function signatures or behavior
