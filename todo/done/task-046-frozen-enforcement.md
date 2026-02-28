# Task 046: Enforce frozen sets with read-only viewer

Depends on task-044 (Photo entity). Prerequisite for task-045 (gallery frozen indicators).

## Goal

Add `frozen` to the `PhotoMetadata` model, make the freeze operation stamp it, enforce immutability in APIs (409), redirect edit views to a read-only frozen set viewer.

## Background

Task-044 creates the `PhotoMetadata` entity. This task adds the `frozen: str | None` field and wires up enforcement everywhere: API save endpoints reject edits with a descriptive 409 (visible in browser dev tools), edit view navigation excludes frozen photos, and direct navigation to a frozen photo redirects to a per-set read-only viewer that reuses the association renderer.

**Key UX principle**: edit views show work to do, the frozen viewer shows work that's done. No "disabled edit" state.

## Context

- `benchmarking/photo_metadata.py` (from task-044) — `PhotoMetadata`, `PhotoMetadataStore`
- `benchmarking/sets.py` — `freeze()`, `BenchmarkSnapshot`, `list_snapshots()`
- Save endpoints: `PUT /api/bibs/{hash}`, `PUT /api/faces/{hash}`, `PUT /api/associations/{hash}`
- Labeling UI routes: `GET /bibs/{hash}`, `GET /faces/{hash}`, `GET /associations/{hash}`
- Association template renderer (reusable for frozen detail view)

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Field | `PhotoMetadata.frozen: str \| None = None` — frozen set name or None |
| Freeze stamps | `freeze()` sets `frozen` on each photo's `PhotoMetadata` entry and saves |
| Re-freeze overlap | Allow silently — overwrite field with new set name |
| API guard | 409 Conflict: `{"detail": "Photo is in frozen set 'gold-v1' and cannot be edited"}` |
| Identity rename | Exempted — `PATCH /api/identities/{name}` is a metadata correction, not a labeling edit |
| Edit views | Exclude frozen photos from photo lists and navigation |
| Direct nav to frozen photo | Redirect to `/frozen/<set-name>/<hash>` |
| Frozen viewer | Per named set: `/frozen/` → `/frozen/<set-name>/` → `/frozen/<set-name>/<hash>` |
| Frozen detail view | Reuses association renderer (faces + bibs + links), no editing controls |

## Changes

### Modified: `benchmarking/photo_metadata.py`

Add field to `PhotoMetadata`:
```python
class PhotoMetadata(BaseModel):
    paths: list[str]
    split: str = ""
    bib_tags: list[str] = []
    face_tags: list[str] = []
    frozen: str | None = None  # frozen set name, or None
```

Add helper methods to `PhotoMetadataStore`:
```python
def is_frozen(self, content_hash: str) -> str | None:
    """Return frozen set name if frozen, else None."""

def frozen_hashes(self) -> dict[str, str]:
    """Return {hash: set_name} for all frozen photos."""
```

### Modified: `benchmarking/sets.py`

`freeze()` now also stamps `PhotoMetadata`:
1. Load `PhotoMetadataStore`
2. For each hash in `hashes`, set `meta.frozen = name`
3. Save `PhotoMetadataStore`
4. Continue creating `metadata.json` / `index.json` as before

### New: `benchmarking/frozen_check.py`

Thin helpers for use in route handlers:
```python
def is_frozen(content_hash: str) -> str | None:
    """Return snapshot name if hash is frozen, else None."""

def require_not_frozen(content_hash: str) -> None:
    """Raise HTTPException(409) if hash is in a frozen set.

    Detail message includes the set name for clarity in browser dev tools.
    """
```

### Modified: save endpoints

Add `require_not_frozen(content_hash)` at the top of each save handler, before any GT mutation:

- `PUT /api/bibs/{hash}` in `routes/api/bibs.py` → `save_bib_label()`
- `PUT /api/faces/{hash}` in `routes/api/faces.py` → `save_face_label()`
- `PUT /api/associations/{hash}` in `routes/api/bibs.py` → `save_associations()`

**Exempted**: `PATCH /api/identities/{name}` — identity rename is a metadata correction (e.g. renaming "Lonneke" to "Lonneke 420" when there turn out to be two).

### Modified: labeling UI routes in `routes/ui/labeling.py`

Each labeling page route checks `is_frozen(content_hash)`:
- If frozen → `RedirectResponse` to `/frozen/<set-name>/<hash>`
- If not frozen → render as normal

Affected routes:
- `bib_photo()` — `GET /bibs/{hash}`
- `face_photo()` — `GET /faces/{hash}`
- `association_photo()` — `GET /associations/{hash}`

### Modified: navigation / filtering

Exclude frozen photos from edit view photo lists. In `label_utils.py`:
- `get_filtered_hashes()` and `get_filtered_face_hashes()` should exclude frozen hashes when providing the labeling queue
- Tab/next-unlabeled already skips labeled photos (frozen photos are labeled), but explicit exclusion is cleaner

### New: `benchmarking/routes/ui/frozen.py`

```python
@ui_frozen_router.get('/frozen/')
async def frozen_sets_list(request: Request):
    """List all frozen sets with metadata (name, date, photo count, description)."""

@ui_frozen_router.get('/frozen/{set_name}/')
async def frozen_set_photos(request: Request, set_name: str):
    """Thumbnail grid of photos in a frozen set."""

@ui_frozen_router.get('/frozen/{set_name}/{content_hash}')
async def frozen_photo_detail(request: Request, set_name: str, content_hash: str):
    """Read-only composite view: faces, bibs, links all rendered.
    Reuses association page renderer. No save button, no editing controls.
    """
```

### New templates

- `benchmarking/templates/frozen_set_list.html` — cards/list for each frozen set
- `benchmarking/templates/frozen_set_photos.html` — thumbnail grid for one set
- Frozen photo detail: read-only variant of association template (extracted partial or minimal copy without form controls)

### Modified: `benchmarking/templates/labels_home.html`

Add "Frozen Sets" link to `/frozen/` in the home page.

### Modified: `benchmarking/app.py`

Register `ui_frozen_router`.

## Tests

Add `tests/test_frozen_check.py`:

- `test_is_frozen_returns_none_when_not_frozen()`
- `test_is_frozen_returns_snapshot_name()`
- `test_require_not_frozen_raises_409_with_detail()`
- `test_save_bib_boxes_rejected_for_frozen()` — PUT returns 409 with JSON body
- `test_save_face_boxes_rejected_for_frozen()` — PUT returns 409 with JSON body
- `test_save_associations_rejected_for_frozen()` — PUT returns 409 with JSON body
- `test_identity_rename_allowed_on_frozen()` — PATCH returns 200
- `test_labeling_page_redirects_for_frozen()` — GET `/bibs/<hash>` redirects to frozen viewer
- `test_frozen_sets_list_page()` — GET `/frozen/` returns 200
- `test_frozen_set_photos_page()` — GET `/frozen/<name>/` returns 200
- `test_frozen_photo_detail_page()` — GET `/frozen/<name>/<hash>` returns 200

Add to `tests/test_sets.py`:

- `test_freeze_stamps_photo_metadata()` — `PhotoMetadata.frozen` set after freeze
- `test_refreeze_overwrites()` — re-freezing overwrites silently

## Scope boundaries

- **In scope**: `frozen` field, freeze stamping, API guards (409), edit view exclusion + redirect, read-only frozen set viewer
- **Out of scope**: identity gallery frozen indicators (task-045), runner `--frozen` flag, unfreeze/delete operations
- **Do not** change the freeze CLI flags or `FreezeRequest` API schema
