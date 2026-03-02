# Task 098: Flatten abstractions — remove pass-through layers and schema duplication

From code review (REVIEW.md, 2026-03-02). Independent of other tasks.

## Goal

Remove unnecessary indirection layers: pass-through service wrappers, duplicate API schema types, redundant model_dump/validate round-trips, and a thin bbox re-export module.

## Background

Several benchmarking services are one-liner pass-throughs called from exactly one route each. The API schemas (BibBoxIn/Out, FaceBoxIn/Out) are structurally identical to domain types (BibBox, FaceBox) in `pipeline_types.py`, causing unnecessary conversions. `detection/bbox.py` re-exports from `geometry.py` without adding value.

## Context

- `benchmarking/services/association_service.py` — `get_associations()` / `set_associations()` delegate to ground_truth + label_utils
- `benchmarking/services/identity_service.py:7-8` — `list_identities()` is a one-liner wrapping `load_identities()`
- `benchmarking/schemas.py` — BibBoxIn/Out, FaceBoxIn/Out structurally identical to pipeline_types
- `benchmarking/routes/api/bibs.py:32-33` — `BibBoxOut.model_validate(b.model_dump())` round-trip
- `benchmarking/routes/api/faces.py:32-33` — `FaceBoxOut.model_validate(b.model_dump())` round-trip
- `detection/bbox.py` — re-exports `bbox_to_rect`, `scale_bbox` from geometry.py; adds thin `bbox_iou`, `bbox_area`, `bbox_overlap_ratio`

## Changes

### Modified: `benchmarking/routes/api/bibs.py`

Inline `association_service.get_associations()` and `set_associations()` — call `ground_truth` and `label_utils` directly in the route handlers.

### Modified: `benchmarking/routes/api/identities.py`

Replace `identity_service.list_identities()` with direct `load_identities()` call.

### Deleted: `benchmarking/services/association_service.py`

Remove after inlining into routes.

### Deleted: `benchmarking/services/identity_service.py`

Remove after inlining into routes.

### Modified: `benchmarking/schemas.py`

Remove `BibBoxIn`, `BibBoxOut`, `FaceBoxIn`, `FaceBoxOut`. Use `pipeline_types.BibBox` and `pipeline_types.FaceBox` directly in request/response schemas.

### Modified: `benchmarking/routes/api/bibs.py`, `benchmarking/routes/api/faces.py`

Remove `BibBoxOut.model_validate(b.model_dump())` round-trips. Return `BibBox` / `FaceBox` instances directly (Pydantic models serialize natively in FastAPI responses).

### Modified: `geometry.py`

Move `bbox_iou`, `bbox_area`, `bbox_overlap_ratio` from `detection/bbox.py` into `geometry.py` (natural home for geometric operations).

### Deleted: `detection/bbox.py`

Remove after moving utilities to `geometry.py`. Update `detection/__init__.py` imports.

### Modified: all import sites

Update imports that referenced `detection.bbox` or the deleted schemas/services. Grep for:
- `from detection.bbox import`
- `from detection import bbox`
- `from benchmarking.services.association_service import`
- `from benchmarking.services.identity_service import`
- `from benchmarking.schemas import BibBoxIn, BibBoxOut, FaceBoxIn, FaceBoxOut`

## Tests

No new tests needed — these are refactoring moves. Existing tests cover the behavior through the route/API layer.

Update import paths in any tests that directly import deleted modules.

## Verification

```bash
venv/bin/python -m pytest -v
```

Grep to confirm deleted modules are not imported anywhere:

```bash
grep -r "association_service\|identity_service\|detection.bbox\|BibBoxOut\|FaceBoxOut" --include="*.py" --exclude-dir=venv --exclude-dir=.venv .
```

## Pitfalls

- `benchmarking/schemas.py` may have other schema types beyond BibBoxIn/Out and FaceBoxIn/Out — only remove the duplicated ones, keep the rest.
- `detection/__init__.py` likely re-exports from `bbox.py` — update the `__init__` to re-export from `geometry` instead, or remove if unused.
- Some tests may import `BibBoxOut` directly for assertion — update to use `BibBox`.

## Acceptance criteria

- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] `benchmarking/services/association_service.py` deleted
- [ ] `benchmarking/services/identity_service.py` deleted
- [ ] `detection/bbox.py` deleted, utilities moved to `geometry.py`
- [ ] No `BibBoxIn/Out` or `FaceBoxIn/Out` in schemas.py
- [ ] No `model_validate(b.model_dump())` round-trips in route handlers
- [ ] No broken imports (grep confirms clean)

## Scope boundaries

- **In scope**: removing pass-through wrappers, schema deduplication, bbox module consolidation
- **Out of scope**: flattening remaining benchmarking/services/ (bib_service, face_service, completion_service have real logic)
- **Do not** change any API response format or break existing tests
