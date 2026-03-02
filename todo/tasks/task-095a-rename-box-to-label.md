# Task 095a: Rename BibBox → BibLabel, FaceBox → FaceLabel

Clarify that box types are ground truth / labeling types, not pipeline types.

**Depends on:** nothing (mechanical rename, can be done anytime)

## Problem

`BibBox` and `FaceBox` are used for ground truth labeling and serialization, but their names suggest they're general-purpose pipeline objects. This causes confusion when traces (the actual pipeline data) exist alongside them. The names should reflect their role: these are **labels** — what a human draws, not what the pipeline produces.

## Goal

Rename `BibBox` → `BibLabel` and `FaceBox` → `FaceLabel` throughout the codebase. Purely mechanical — no structural or behavioral changes.

## Changes

### Canonical definitions

`pipeline/types.py`:
- `class BibBox` → `class BibLabel`
- `class FaceBox` → `class FaceLabel`
- Update type annotations in `predict_links`, `_torso_region`, `AutolinkResult`, `BibFaceLink`
- Constants: `_BIB_BOX_UNSCORED` → consider renaming to `_BIB_UNSCORED_SCOPES` (optional)

### Re-exports and imports (~34 files)

Every file that imports `BibBox` or `FaceBox` needs updating:

**Pipeline** (4 files):
- `pipeline/__init__.py`
- `pipeline/single_photo.py`
- `pipeline/cluster.py` (if it references FaceBox)
- `pipeline/types.py`

**Benchmarking** (12 files):
- `benchmarking/ground_truth.py` — `BibPhotoLabel.boxes: list[BibLabel]`, `FacePhotoLabel.boxes: list[FaceLabel]`
- `benchmarking/runner.py` — `PhotoResult` fields
- `benchmarking/scoring.py`
- `benchmarking/link_analysis.py`
- `benchmarking/face_embeddings.py`
- `benchmarking/ghost.py`
- `benchmarking/schemas.py` — `BibBoxIn/Out`, `FaceBoxIn/Out` (rename to `BibLabelIn/Out`?)
- `benchmarking/routes/api/bibs.py`
- `benchmarking/routes/api/faces.py`
- `benchmarking/cli/commands/photos.py`
- `benchmarking/tuners/grid.py`
- `benchmarking/completeness.py`

**Scan** (1 file):
- `scan/persist.py`

**Tests** (15+ files):
- `test_autolink.py`, `test_pipeline.py`, `test_pipeline_types.py`, `test_scoring.py`, `test_ground_truth.py`, `test_runner.py`, `test_runner_models.py`, `test_link_scoring.py`, `test_bib_service.py`, `test_face_service.py`, `test_completion_service.py`, `test_completeness.py`, `test_prepare.py`, `test_identity_gallery.py`, `test_process_image_autolink.py`, plus `tests/benchmarking/` files

## Migration notes

- Keep backward compat aliases if needed: `BibBox = BibLabel` (can be removed later)
- JSON serialization is unaffected — field names don't change, only the class name
- `BibPhotoLabel.boxes` field name stays (it's the JSON key)
- `has_coords` property stays on both labels

## Acceptance criteria

- [ ] `BibBox` renamed to `BibLabel` everywhere
- [ ] `FaceBox` renamed to `FaceLabel` everywhere
- [ ] All existing tests pass
- [ ] No behavioral changes

## Scope boundaries

- **In scope**: class rename, import updates, type annotation updates
- **Out of scope**: structural changes, trace-based autolink (095b), inheritance
- Labels and traces remain separate types with no inheritance relationship
