# Task 080: Flatten benchmarking services layer

Independent of other tasks.

## Goal

Remove the `benchmarking/services/` package by inlining thin pass-through services into their callers and promoting the two valuable services to top-level benchmarking modules.

## Background

Code review found that `benchmarking/services/` contains 6 service files, but only 2 contain substantial logic worth keeping as separate modules. The rest are thin wrappers with a single caller each — adding indirection without benefit. This is an internal benchmarking/labeling tool, not a multi-entry-point system that benefits from a service layer.

## Context

- `benchmarking/services/association_service.py` (41 lines) — pure pass-through, single caller
- `benchmarking/services/identity_service.py` (36 lines) — 2 trivial forwards + 1 real function
- `benchmarking/services/bib_service.py` (144 lines) — metadata coordination, single caller
- `benchmarking/services/face_service.py` (193 lines) — embedding cache + image processing, single caller
- `benchmarking/services/completion_service.py` (122 lines) — multi-store aggregation, real logic, keep as module
- `benchmarking/services/identity_gallery_service.py` (109 lines) — multi-store aggregation, real logic, keep as module
- `benchmarking/routes/api/bibs.py` — calls `bib_service` and `association_service`
- `benchmarking/routes/api/faces.py` — calls `face_service`
- `benchmarking/routes/api/identities.py` — calls `identity_service`
- `benchmarking/routes/ui/labeling.py` — calls `completion_service` and `identity_gallery_service`
- `tests/test_bib_service.py`, `tests/test_face_service.py`, `tests/test_association_service.py`, `tests/test_identity_service.py`, `tests/test_identity_gallery.py`, `tests/test_completion_service.py` — existing tests

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| What happens to `completion_service.py`? | Move to `benchmarking/completion_service.py` (top-level module) |
| What happens to `identity_gallery_service.py`? | Move to `benchmarking/identity_gallery_service.py` (top-level module) |
| What happens to `association_service.py`? | Inline into `routes/api/bibs.py` (~10 lines) |
| What happens to `bib_service.py`? | Inline into `routes/api/bibs.py` |
| What happens to `face_service.py`? | Inline into `routes/api/faces.py` |
| What happens to `identity_service.py`? | Inline `list`/`create` into route; move `rename_identity_across_gt()` to `benchmarking/identities.py` |
| What happens to `services/__init__.py`? | Delete along with the package |

## Changes

### Deleted: `benchmarking/services/` package

Remove the entire `benchmarking/services/` directory after completing all moves below.

### Moved: `benchmarking/services/completion_service.py` → `benchmarking/completion_service.py`

Move file, update imports in callers (`routes/ui/labeling.py`, tests).

### Moved: `benchmarking/services/identity_gallery_service.py` → `benchmarking/identity_gallery_service.py`

Move file, update imports in callers (`routes/ui/labeling.py`, tests).

### Modified: `benchmarking/routes/api/bibs.py`

Inline logic from `bib_service.py` and `association_service.py`. The route handlers gain the ground truth loading, hash resolution, metadata coordination, and crop extraction that currently live in the service. Remove `from benchmarking.services import association_service, bib_service`.

### Modified: `benchmarking/routes/api/faces.py`

Inline logic from `face_service.py`. The embedding index cache, image loading, crop extraction, and identity suggestion logic move here. Remove `from benchmarking.services import face_service`.

### Modified: `benchmarking/routes/api/identities.py`

Inline `list_identities()` → direct `load_identities()` call. Inline `create_identity()` → direct `add_identity()` call. Replace `rename_identity_across_gt()` call with import from `benchmarking/identities.py`.

### Modified: `benchmarking/identities.py`

Add `rename_identity_across_gt(old_name, new_name)` function (moved from `identity_service.py`).

### Modified: test files

Update imports in all affected test files. Tests should exercise the same behavior through the new locations.

## Tests

Existing tests cover the behavior. After inlining:

- `tests/test_association_service.py` — migrate to test the route directly or merge into `tests/test_link_api.py`
- `tests/test_bib_service.py` — migrate to test the route directly or merge into `tests/test_web_app.py`
- `tests/test_face_service.py` — migrate to test the route directly or merge into `tests/test_web_app.py`
- `tests/test_identity_service.py` — split: rename test moves to `tests/test_identities.py`; route tests merge into identities API tests
- `tests/test_completion_service.py` — update import path only
- `tests/test_identity_gallery.py` — update import path only

## Verification

```bash
venv/bin/python -m pytest -v
```

All existing tests must pass after the refactor. No behavior changes.

## Pitfalls

- `face_service.py` has a module-level `_embedding_index_cache` dict. When inlining into the route module, ensure this cache remains module-level in `faces.py` (not inside a function).
- `bib_service.py` imports `ITERATION_SPLIT_PROBABILITY` from `config.py` — carry this import into the route.
- Several test files patch `benchmarking.services.X.load_Y`; after inlining, patch targets change to `benchmarking.routes.api.X.load_Y`.
- `completion_service.py` and `identity_gallery_service.py` have no `services.` prefix in their function names, so callers just need an import path update.

## Acceptance criteria

- [ ] `benchmarking/services/` directory no longer exists
- [ ] `completion_service.py` and `identity_gallery_service.py` live at `benchmarking/` top level
- [ ] `rename_identity_across_gt()` lives in `benchmarking/identities.py`
- [ ] All existing tests still pass (`venv/bin/python -m pytest`)
- [ ] No `from benchmarking.services` imports remain anywhere in the codebase
- [ ] No behavior changes — all API endpoints return the same responses

## Scope boundaries

- **In scope**: moving/inlining service code, updating imports, updating tests
- **Out of scope**: refactoring the route handlers themselves, changing API behavior, modifying production code
- **Do not** change any files outside `benchmarking/` and `tests/`
