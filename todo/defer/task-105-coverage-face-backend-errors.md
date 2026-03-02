# Task 105: Test coverage for face backend factory error paths

Independent. No dependencies on other tasks.

**TDD approach: `tdd: test-wrap`**

## Goal

Cover error-handling paths in `faces/backend.py` factory functions — specifically `get_face_backend_with_overrides` kwarg validation. Currently at 50% coverage; the error paths (unknown backend name, invalid kwargs) are untested.

## Background

Coverage analysis (2026-03-02) found lines 253, 276, and 278-282 untested. These are validation paths that protect against typos in backend names and parameter names. Testable without loading actual OpenCV models.

## Context

- `faces/backend.py` — `get_face_backend_by_name()`, `get_face_backend_with_overrides()`
- The error paths raise `ValueError` — no side effects, no model loading needed
- Note: instantiating actual backends requires OpenCV model files — only test the factory validation, not the backends themselves

## Tests

### Extend: `tests/test_face_backend.py` (or new file)

- `test_unknown_backend_name_raises()` — `get_face_backend_by_name("nonexistent")` raises ValueError
- `test_overrides_unknown_kwarg_raises()` — `get_face_backend_with_overrides("opencv_dnn_ssd", bogus=True)` raises ValueError with helpful message
- `test_overrides_unknown_kwarg_lists_invalid_names()` — error message includes the invalid kwarg names
- `test_overrides_defaults_to_config_backend()` — `backend_name=None` uses `config.FACE_BACKEND`

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] Factory error paths covered (ValueError raised for unknown name and unknown kwargs)
- [ ] Tests do NOT require OpenCV model files to be present

## Scope boundaries

- **In scope**: `get_face_backend_by_name` error path, `get_face_backend_with_overrides` validation
- **Out of scope**: `OpenCVHaarFaceBackend`, `OpenCVDnnSsdFaceBackend` detection methods (require models, acceptable gap)
- **Do not** attempt to instantiate actual backends in these tests
