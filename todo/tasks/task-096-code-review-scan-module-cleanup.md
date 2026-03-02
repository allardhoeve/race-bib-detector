# Task 096: Scan module cleanup — reduce duplication and simplify process_image

From code review (REVIEW.md, 2026-03-02). Independent of other tasks.

## Goal

Clean up `scan/service.py` and `scan/pipeline.py`: extract duplicated constants, simplify long functions, remove thin wrappers, and fix fragile index mapping in autolink persistence.

## Background

The scan module accumulated organic complexity across several iterations. `process_image()` is 119 lines orchestrating 8 operations. The same empty-result dict is copy-pasted 4 times. Two detection-ID fetchers are structurally identical. Autolink persistence relies on fragile `list.index()` lookups.

A larger tradeoff (consolidating scan/pipeline.py into scan/service.py) is noted but **not in scope** for this task — it requires broader restructuring.

## Context

- `scan/service.py:52-58, 63-69, 124-130, 137-143` — 4x identical empty result dict
- `scan/service.py:79-92` — nested `make_images()` closure with inner `fetch_factory()` lambda
- `scan/pipeline.py:110-121` — `ensure_photo_record()` thin wrapper around `db.insert_photo()`
- `scan/pipeline.py:147-164` — `_get_bib_detection_ids()` and `_get_face_detection_ids()` near-duplicates
- `scan/pipeline.py:167-285` — `process_image()` 119-line function with 8 interleaved concerns
- `scan/pipeline.py:264-283` — autolink persistence uses `sp.bib_boxes.index(bib_box)` for ID mapping

## Changes

### Modified: `scan/service.py`

**Extract empty result constant:**

```python
_EMPTY_RESULT: dict = {
    "photos_found": 0,
    "photos_scanned": 0,
    "photos_skipped": 0,
    "bibs_detected": 0,
    "faces_detected": 0,
}
```

Replace all 4 inline dicts with `return {**_EMPTY_RESULT}` (shallow copy to prevent mutation).

**Simplify nested closures** (lines 79-97): flatten `make_images()` + `fetch_factory()` into a single generator that yields `ImageInfo` objects with explicit data flow instead of captured lambda closures.

### Modified: `scan/pipeline.py`

**Inline ensure_photo_record** (lines 110-121): replace the single call site at line 206 with direct `db.insert_photo(...)`.

**Unify detection ID fetchers** (lines 147-164):

```python
def _get_detection_ids(conn: sqlite3.Connection, photo_id: int, table: str, order_col: str) -> list[int]:
    cursor = conn.cursor()
    cursor.execute(f"SELECT id FROM {table} WHERE photo_id = ? ORDER BY {order_col}", (photo_id,))
    return [row[0] for row in cursor.fetchall()]
```

Note: `table` and `order_col` are internal constants, not user input — no SQL injection risk.

**Split process_image** (lines 167-285) into focused helpers:

- `_save_bib_artifacts_and_db(conn, photo_id, sp, ...)` — bib snippet saving + DB insertion
- `_save_face_embeddings_and_artifacts(conn, photo_id, sp, ...)` — embedding + face artifact saving + DB insertion
- `_persist_autolinks(conn, photo_id, sp, bib_ids, face_ids)` — autolink DB persistence

**Fix fragile index mapping** (lines 264-283): instead of reconstructing indices via `sp.bib_boxes.index(bib_box)`, use the positional indices directly from the bib_ids/face_ids lists returned by the DB insertion helpers. The insertion order matches the box list order, so `zip(sp.autolink.pairs, ...)` can use the index directly.

## Tests

Extend `tests/test_album_ingest.py` or `tests/test_pipeline.py`:

- `test_empty_result_constant_not_mutated()` — verify `_EMPTY_RESULT` stays zero after function returns
- `test_process_image_split_equivalence()` — verify refactored process_image produces identical DB state

## Verification

```bash
venv/bin/python -m pytest tests/test_album_ingest.py tests/test_pipeline.py tests/test_process_image_autolink.py -v
```

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] Empty result dict appears exactly once as a module constant
- [ ] `ensure_photo_record()` removed, call inlined
- [ ] Single `_get_detection_ids()` replaces two near-duplicate functions
- [ ] `process_image()` delegates to focused helpers, each ≤30 lines
- [ ] Autolink persistence uses explicit index mapping, not `list.index()`

## Scope boundaries

- **In scope**: duplication removal, function splitting, index mapping fix within scan/
- **Out of scope**: consolidating scan/pipeline.py into scan/service.py (tradeoff proposal, separate decision)
- **Do not** change the public API of `process_image()` or `scan_images()`
