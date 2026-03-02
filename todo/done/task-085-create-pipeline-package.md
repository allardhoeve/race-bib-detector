# Task 085: Create `pipeline/` package

Structural prerequisite for the tuning series (085-094).

## Goal

Move the root-level `pipeline.py` and `pipeline_types.py` into a proper `pipeline/` package. Rename `scan/pipeline.py` to `scan/persist.py` to resolve the naming collision.

## Background

The pipeline layer currently lives as two root-level files:
- `pipeline.py` — `run_single_photo()`, `SinglePhotoResult`
- `pipeline_types.py` — `BibBox`, `FaceBox`, `BibFaceLink`, `AutolinkResult`, `predict_links`

Upcoming tasks add `pipeline/cluster.py` and `pipeline/refine.py`. A package is cleaner than accumulating `pipeline_*.py` files at the root.

`scan/pipeline.py` is confusing alongside `pipeline/`. After task-081, what remains in that file is persistence: take a `SinglePhotoResult`, save artifacts to disk, write records to DB. Rename to `scan/persist.py`.

## Changes

### New: `pipeline/__init__.py`

Re-exports for backward compat and convenience:

```python
from pipeline.single_photo import SinglePhotoResult, run_single_photo
from pipeline.types import (
    BibBox, FaceBox, BibFaceLink, AutolinkResult,
    BIB_BOX_SCOPES, _BIB_BOX_UNSCORED,
    FACE_SCOPE_TAGS, _FACE_SCOPE_COMPAT, FACE_BOX_TAGS,
    predict_links,
)
```

### Moved: `pipeline.py` → `pipeline/single_photo.py`

Content unchanged. Update internal imports.

### Moved: `pipeline_types.py` → `pipeline/types.py`

Content unchanged.

### Renamed: `scan/pipeline.py` → `scan/persist.py`

Content unchanged. Update imports in `scan/service.py`, `scan/__init__.py`, CLI entry points.

### Import updates

Every file that imports from `pipeline` or `pipeline_types` needs updating. Major consumers:

- `benchmarking/runner.py` — imports `run_single_photo`, `BibBox`, `FaceBox`, `BibFaceLink`, `predict_links`
- `benchmarking/ground_truth.py` — re-exports `BibBox`, `FaceBox`, etc. from `pipeline_types`
- `benchmarking/scoring.py` — imports `BibBox`, `FaceBox`
- `benchmarking/routes/api/*.py` — various type imports
- `benchmarking/ghost.py` — imports `BibBox`, `FaceBox`
- `scan/service.py` — imports from `scan.pipeline`
- `cli/scan.py` — imports from `scan.pipeline`
- Test files throughout

Strategy: update imports to use `from pipeline.types import ...` and `from pipeline.single_photo import ...` (or `from pipeline import ...` via re-exports).

### Delete: root-level `pipeline.py` and `pipeline_types.py`

After all imports are updated.

## Test-first approach

```python
def test_pipeline_package_importable():
    """pipeline/ package exports all expected symbols."""
    from pipeline import run_single_photo, SinglePhotoResult
    from pipeline.types import BibBox, FaceBox, BibFaceLink, AutolinkResult

def test_scan_persist_importable():
    """scan.persist module is importable and has process_image."""
    from scan.persist import process_image
```

## Verification

```bash
venv/bin/python -m pytest  # all tests pass with new paths
venv/bin/python -c "from pipeline import run_single_photo; print('ok')"
venv/bin/python -c "from scan.persist import process_image; print('ok')"
```

## Acceptance criteria

- [ ] `pipeline/` package exists with `__init__.py`, `types.py`, `single_photo.py`
- [ ] `scan/persist.py` exists (renamed from `scan/pipeline.py`)
- [ ] Root-level `pipeline.py` and `pipeline_types.py` deleted
- [ ] All imports updated — no remaining references to old paths
- [ ] All existing tests pass (`venv/bin/python -m pytest`)

## Scope boundaries

- **In scope**: file moves, import updates, re-exports for backward compat
- **Out of scope**: any behavioral changes, new types, new functions
- **Do not** change any logic — this is purely structural
