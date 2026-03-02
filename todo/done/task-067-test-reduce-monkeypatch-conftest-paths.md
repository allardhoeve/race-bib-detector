# Task 067: Reduce monkeypatch — shared conftest fixture for path functions

## Problem

8 test files independently patch the same 5-6 path-returning functions to redirect
filesystem access to `tmp_path`. The same block appears near-identically in:

- `test_web_app.py` (20 patches total)
- `test_ui_routes.py` (17)
- `test_link_api.py` (6)
- `test_identity_gallery.py` (7)
- `test_frozen_check.py` (8)
- `test_completion_service.py` (4)
- `test_bib_service.py` (3)
- `test_face_service.py` (3)
- `test_association_service.py` (2)

Typical repeated block:

```python
monkeypatch.setattr("benchmarking.ground_truth.get_bib_ground_truth_path", lambda: bib_gt_path)
monkeypatch.setattr("benchmarking.ground_truth.get_face_ground_truth_path", lambda: face_gt_path)
monkeypatch.setattr("benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path)
monkeypatch.setattr("benchmarking.ghost.get_suggestion_store_path", lambda: suggestions_path)
monkeypatch.setattr("benchmarking.identities.get_identities_path", lambda: identities_path)
monkeypatch.setattr("benchmarking.photo_metadata.get_photo_metadata_path", lambda: meta_path)
```

## Solution

Create a shared pytest fixture in `tests/benchmarking/conftest.py` (or `tests/conftest.py`
if the paths are used outside `tests/benchmarking/`) that patches all path functions to
point at `tmp_path` subdirectories. Each file then uses the fixture instead of repeating
the `monkeypatch.setattr` calls.

## Scope

- **No production code changes** — only test files
- Eliminates ~60 lines of near-identical boilerplate across 8+ files
- All existing tests must continue to pass

## Acceptance criteria

- [ ] Shared fixture exists in conftest.py
- [ ] All 8+ files use the shared fixture instead of inline patches
- [ ] All tests pass (`venv/bin/python -m pytest`)
- [ ] No file has more than 1 inline path-function patch (for any file-specific overrides)
