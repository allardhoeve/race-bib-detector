# Task 095: Defensive data boundaries — None guards and JSON decode handling

From code review (REVIEW.md, 2026-03-02). Independent of other tasks.

## Goal

Add missing None guards and JSON decode error handling at data boundaries (database results, file I/O) to prevent crashes on corrupted or unexpected data.

## Background

Several functions index `cursor.fetchone()` without checking for None, or call `json.load()`/`json.loads()` without catching `JSONDecodeError`. While unlikely in normal operation (SQLite IntegrityError implies the row exists; JSON files are machine-written), these are system boundaries where defensive checks are warranted.

## Context

- `db.py:270-273` — `insert_photo()` IntegrityError handler indexes fetchone without None check
- `db.py:231-273` — same function mixes schema discovery, SQL generation, and exception handling (45 lines)
- `web/app.py:212` — `json.loads(bib['bbox_json'])` without JSONDecodeError handling
- `benchmarking/identities.py:19` — `json.load(f)` without JSONDecodeError handling
- `benchmarking/ground_truth.py:256-257, 273-274, 296-297` — three `load_*_ground_truth()` functions without JSONDecodeError handling

## Changes

### Modified: `db.py`

**insert_photo() None guard** (line 273):

```python
# Before
except sqlite3.IntegrityError:
    cursor.execute("SELECT id FROM photos WHERE photo_url = ?", (photo_url,))
    return cursor.fetchone()[0]

# After
except sqlite3.IntegrityError:
    cursor.execute("SELECT id FROM photos WHERE photo_url = ?", (photo_url,))
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Photo URL '{photo_url}' triggered IntegrityError but was not found in database")
    return row[0]
```

**insert_photo() extraction** (lines 231-273): optionally extract `_ensure_photo_columns(conn)` for the schema-discovery logic (column existence checks + ALTER TABLE). This makes the core insert logic ~20 lines shorter.

### Modified: `web/app.py`

Wrap `json.loads(bib['bbox_json'])` (line 212):

```python
try:
    bbox = json.loads(bib['bbox_json'])
except json.JSONDecodeError:
    bbox = None
```

### Modified: `benchmarking/identities.py`

Wrap `json.load(f)` (line 19):

```python
try:
    return sorted(json.load(f))
except json.JSONDecodeError:
    logger.error("Corrupted identities file: %s", path)
    return []
```

### Modified: `benchmarking/ground_truth.py`

Same pattern for `load_bib_ground_truth()`, `load_face_ground_truth()`, `load_link_ground_truth()`:

```python
try:
    return BibGroundTruth.from_dict(json.load(f))
except json.JSONDecodeError:
    logger.error("Corrupted ground truth file: %s", path)
    return BibGroundTruth()
```

## Tests

Extend `tests/test_ground_truth.py`:

- `test_load_bib_gt_corrupted_json()` — write invalid JSON, verify returns empty BibGroundTruth
- `test_load_face_gt_corrupted_json()` — same for face
- `test_load_link_gt_corrupted_json()` — same for links

Add to existing db tests:

- `test_insert_photo_integrity_error_missing_row()` — mock fetchone to return None after IntegrityError, verify RuntimeError raised

## Verification

```bash
venv/bin/python -m pytest tests/test_ground_truth.py -v
```

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `db.py:insert_photo()` checks fetchone result before indexing
- [ ] `web/app.py` handles JSONDecodeError on bbox_json
- [ ] `benchmarking/identities.py` handles JSONDecodeError
- [ ] Three `load_*_ground_truth()` functions handle JSONDecodeError
- [ ] New tests for corrupted JSON cases pass

## Scope boundaries

- **In scope**: None guards on fetchone, JSONDecodeError handling at file/db boundaries
- **Out of scope**: Refactoring insert_photo into smaller functions (optional, not required)
- **Do not** change the happy-path behavior of any function
