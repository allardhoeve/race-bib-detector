# Task 057: Add integration tests for untested UI route handlers

Depends on task-054 (nav helper must exist for clean test setup). Can start after 054 even if 055/056 are not yet done.

## Goal

Add integration test coverage for the five UI route handlers that currently have zero tests: `bib_photo`, `face_photo`, `association_photo`, `benchmark_inspect`, and `frozen_photo_detail`.

## Problem

These handlers serve the core labeling and inspection pages, yet none have test coverage:

| Handler | File:Line | Tests |
|---------|-----------|-------|
| `bib_photo` | `ui/labeling.py:53` | 0 |
| `face_photo` | `ui/labeling.py:153` | 0 |
| `association_photo` | `ui/labeling.py:282` | 0 |
| `benchmark_inspect` | `ui/benchmark.py:35` | 0 |
| `frozen_photo_detail` | `ui/frozen.py:42` | 0 (only `frozen_sets_list` has a test) |

Meanwhile, the index/redirect endpoints (`bibs_index`, `faces_index`, `associations_index`) ARE tested in `tests/test_web_app.py:736` (`TestTask019Redirects`).

## Context — existing test infrastructure

### `tests/test_web_app.py` — `app_client` fixture (:26–57)

```python
@pytest.fixture
def app_client(tmp_path, monkeypatch):
    bib_gt_path = tmp_path / "bib_ground_truth.json"
    face_gt_path = tmp_path / "face_ground_truth.json"
    suggestions_path = tmp_path / "suggestions.json"
    identities_path = tmp_path / "face_identities.json"
    index_path = tmp_path / "photo_index.json"

    save_photo_index({HASH_A: ["photo_a.jpg"], HASH_B: ["photo_b.jpg"]}, index_path)

    monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path)
    monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path)
    monkeypatch.setattr("benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path)
    monkeypatch.setattr("benchmarking.identities.get_identities_path", lambda: identities_path)
    monkeypatch.setattr("benchmarking.photo_metadata.get_photo_metadata_path", lambda: index_path)

    from benchmarking.app import create_app
    app = create_app()
    return TestClient(app, follow_redirects=False)
```

This fixture does NOT patch:
- `benchmarking.photo_index.get_photo_index_path` (uses a different path pattern)
- `benchmarking.frozen_check` (frozen set lookup)
- `benchmarking.runner.RESULTS_DIR` / `list_runs` / `get_run` (benchmark results)
- `benchmarking.ground_truth.get_link_ground_truth_path` (link GT)

### What the handlers need

| Handler | Needs beyond `app_client` |
|---------|---------------------------|
| `bib_photo` | Photo index with hashes, bib GT with labeled data, photo metadata, `list_runs()` |
| `face_photo` | Photo index, face GT with labeled data, photo metadata, `list_runs()` |
| `association_photo` | Photo index, bib GT, face GT, link GT, completion service hashes |
| `benchmark_inspect` | `get_run()` returning a `BenchmarkRun`, `list_runs()`, link GT |
| `frozen_photo_detail` | `BenchmarkSnapshot.load()` returning a snapshot with known hashes, bib/face/link GT |

### Existing test patterns to follow

- `tests/test_link_api.py` — `link_client` fixture builds bib + face GT, patches link GT path
- `tests/test_web_app.py:668` — `freeze_client` fixture creates frozen snapshots
- `tests/test_web_app.py:582` — `TestHomeRoute` tests a UI route returning 200

### Key route URLs (from FastAPI router)

```
GET /bibs/{content_hash}?filter=all          → bib_photo
GET /faces/{content_hash}?filter=all         → face_photo
GET /associations/{content_hash}?filter=all  → association_photo
GET /benchmark/{run_id}/                     → benchmark_inspect
GET /frozen/{set_name}/{content_hash}        → frozen_photo_detail
```

### `BenchmarkRun` structure (for benchmark_inspect tests)

```python
from benchmarking.runner import BenchmarkRun, BenchmarkMetrics, PhotoResult, RunMetadata
# Minimal construction:
run = BenchmarkRun(
    metadata=RunMetadata(run_id="test-run", ...),
    metrics=BenchmarkMetrics(total=1, ...),
    photo_results=[PhotoResult(content_hash=HASH_A, ...)],
)
```

## Changes

### New: `tests/test_ui_routes.py`

```python
"""Integration tests for UI route handlers (labeling, inspect, frozen)."""

HASH_A = "a" * 64
HASH_B = "b" * 64
```

#### Fixtures

- `labeling_client` — extends `app_client` pattern with:
  - Photo index containing `HASH_A`, `HASH_B`
  - Bib GT with one labeled photo (`HASH_A`)
  - Face GT with one labeled photo (`HASH_A`)
  - Photo metadata patched
  - `is_frozen` patched to return `None` (no frozen sets)
  - `list_runs` patched to return `[]`

- `frozen_client` — extends `labeling_client` with:
  - A frozen snapshot containing `HASH_A`
  - `is_frozen` patched to return the set name for `HASH_A`

- `benchmark_client` — extends base with:
  - `get_run` patched to return a minimal `BenchmarkRun`
  - `list_runs` patched to return `[{"run_id": "test-run", ...}]`
  - Link GT patched

#### Test classes

```
TestBibPhoto
    test_renders_200                     # GET /bibs/{HASH_A[:8]}?filter=all → 200
    test_404_unknown_hash                # GET /bibs/deadbeef?filter=all → 404
    test_frozen_redirect                 # frozen hash → 302 to /frozen/...
    test_empty_filter_shows_empty_page   # no hashes match → empty.html

TestFacePhoto
    test_renders_200                     # GET /faces/{HASH_A[:8]}?filter=all → 200
    test_404_unknown_hash                # → 404
    test_frozen_redirect                 # → 302

TestAssociationPhoto
    test_renders_200                     # GET /associations/{HASH_A[:8]} → 200
    test_404_unknown_hash                # → 404
    test_frozen_redirect                 # → 302

TestBenchmarkInspect
    test_renders_200                     # GET /benchmark/test-run/ → 200
    test_404_missing_run                 # GET /benchmark/nonexistent/ → 404

TestFrozenPhotoDetail
    test_renders_200                     # GET /frozen/setname/{HASH_A[:8]} → 200
    test_404_unknown_hash                # → 404
    test_404_unknown_set                 # → 404
```

## Scope boundaries

- **In scope**: new test file with fixtures and ~15 test cases
- **Out of scope**: refactoring handlers (tasks 055/056), modifying route code, template changes
- **Do not** change any production code — this is a test-only task
