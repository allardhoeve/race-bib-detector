# Task 104: Test coverage for photo index management

Independent. No dependencies on other tasks.

**TDD approach: `tdd: test-wrap`**

## Goal

Cover `benchmarking/photo_index.py` — the photo index compatibility layer at 59% coverage. `save_photo_index` (stale-entry pruning) and `update_photo_index` (scan + diff + stats) are the untested functions.

## Background

Coverage analysis (2026-03-02) found the write path and update logic untested. These functions manage the mapping from content hashes to file paths — a regression could silently drop photos from the benchmark index.

## Context

- `benchmarking/photo_index.py` — `save_photo_index()`, `update_photo_index()`, `get_path_for_hash()`
- `benchmarking/photo_metadata.py` — `PhotoMetadata`, `load_photo_metadata()`, `save_photo_metadata()` (already 99% covered)
- `benchmarking/scanner.py` — `build_photo_index()` (already 94% covered)
- Tests should use `tmp_path` with a temporary metadata JSON file

## Tests

### Extend: `tests/benchmarking/test_photo_index.py` (or new file)

**`save_photo_index`**:
- `test_save_creates_entries()` — new hashes appear in metadata
- `test_save_prunes_stale_entries()` — hash removed from index also removed from metadata
- `test_save_preserves_existing_metadata()` — non-path fields (split, tags) survive

**`update_photo_index`**:
- `test_update_returns_correct_stats()` — total_files, unique_hashes, duplicates, new_photos
- `test_update_saves_index()` — index persisted to disk after update
- `test_update_detects_new_photos()` — second call with added photo shows new_photos=1

**`get_path_for_hash`**:
- `test_returns_path_when_found()` — hash in index returns correct path
- `test_returns_none_when_missing()` — hash not in index returns None
- `test_loads_from_disk_when_no_index_provided()` — fallback load works

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `benchmarking/photo_index.py` coverage >= 85%
- [ ] Stale-entry pruning path exercised
- [ ] Stats dict verified for accuracy

## Scope boundaries

- **In scope**: `save_photo_index`, `update_photo_index`, `get_path_for_hash` fallback path
- **Out of scope**: `load_photo_index` (already covered), `photo_metadata.py` (already 99%)
- **Do not** modify function signatures or behavior
