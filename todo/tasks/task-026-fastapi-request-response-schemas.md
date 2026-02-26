# Task 026: FastAPI typed request/response schemas

Depends on task-025 (FastAPI migration). Can be done incrementally endpoint by endpoint.

## Goal

Replace `body: dict = Body(...)` interim request bodies and untyped `dict` return
values with explicit Pydantic schema classes, one per endpoint. This produces:
- Automatic 422 validation with clear error messages (no more manual 400 checks).
- A fully populated `/docs/` OpenAPI UI with correct request/response shapes.
- Removal of the remaining manual `if not field: return 400` guards.

## Background

Task-025 migrates Flask to FastAPI using `dict` bodies and untyped returns as an
interim step. This task replaces those stubs with typed schemas.

The schemas here are **API contracts** — the wire format. They are distinct from
the **domain models** in `ground_truth.py` (migrated in task-024). Sometimes an
API schema is identical to a domain model and can simply re-use it; sometimes it
is a different shape (e.g., a save endpoint accepts a flat payload but the domain
model is richer).

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where to put schemas? | `benchmarking/schemas.py` — one file at this scale; split into `schemas/` if it grows past ~300 lines |
| Re-use domain models as response schemas? | Yes where the shape matches exactly (e.g. `FaceBox` can be the response item type) |
| Input schemas vs domain models | Separate: `SaveFaceBoxesRequest` wraps `list[FaceBox]` from ground_truth; domain model may have fields the API doesn't accept |
| 422 vs 400 | FastAPI returns 422 for schema validation failures automatically; keep explicit `HTTPException(400)` only for semantic errors (e.g. hash not found) |
| `content_hash` in request body vs URL | After task-020, hash is always in the URL; request bodies must NOT include `content_hash` |

## Schema definitions: `benchmarking/schemas.py`

```python
"""Pydantic schemas for API request bodies and response models.

Domain model classes (BibBox, FaceBox, etc.) live in ground_truth.py.
These schemas define the exact wire format accepted / returned by each endpoint.
"""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class HashKeyedRecord(BaseModel):
    """Base for per-photo entries in list-all responses."""
    labeled: bool = False


# ---------------------------------------------------------------------------
# Bib boxes
# ---------------------------------------------------------------------------

class BibBoxIn(BaseModel):
    """Input shape for a single bib box (from the labeling UI)."""
    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"


class SaveBibBoxesRequest(BaseModel):
    """Body for PUT /api/bibs/{hash}."""
    boxes: list[BibBoxIn] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    split: str = "full"


class BibBoxOut(BaseModel):
    """Output shape for a single bib box."""
    x: float
    y: float
    w: float
    h: float
    number: str = ""
    scope: str = "bib"


class GetBibBoxesResponse(BaseModel):
    """Response for GET /api/bibs/{hash}."""
    boxes: list[BibBoxOut]
    suggestions: list[dict] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    split: str
    labeled: bool


class BibBoxesListItem(BaseModel):
    """Per-photo entry in GET /api/bibs list-all response."""
    boxes: list[BibBoxOut]
    labeled: bool


# ---------------------------------------------------------------------------
# Face boxes
# ---------------------------------------------------------------------------

class FaceBoxIn(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str = "keep"
    identity: str | None = None
    tags: list[str] = Field(default_factory=list)


class SaveFaceBoxesRequest(BaseModel):
    """Body for PUT /api/faces/{hash} (replaces POST /api/face_labels)."""
    boxes: list[FaceBoxIn] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class FaceBoxOut(BaseModel):
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    scope: str
    identity: str | None = None
    tags: list[str]


class GetFaceBoxesResponse(BaseModel):
    """Response for GET /api/faces/{hash}."""
    boxes: list[FaceBoxOut]
    suggestions: list[dict] = Field(default_factory=list)
    tags: list[str]


class FaceBoxesListItem(BaseModel):
    boxes: list[FaceBoxOut]
    labeled: bool


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------

class IdentitiesResponse(BaseModel):
    identities: list[str]


class CreateIdentityRequest(BaseModel):
    name: str


class RenameIdentityRequest(BaseModel):
    old_name: str
    new_name: str


class RenameIdentityResponse(BaseModel):
    updated_count: int
    identities: list[str]


# ---------------------------------------------------------------------------
# Associations (bib-face links)
# ---------------------------------------------------------------------------

class SaveAssociationsRequest(BaseModel):
    """Body for PUT /api/associations/{hash}."""
    links: list[list[int]] = Field(default_factory=list)


class AssociationsResponse(BaseModel):
    links: list[list[int]]


# ---------------------------------------------------------------------------
# Freeze
# ---------------------------------------------------------------------------

class FreezeRequest(BaseModel):
    name: str
    hashes: list[str]


class FreezeResponse(BaseModel):
    status: str
    name: str
    count: int
```

## Changes: route handlers

Apply the schemas as type annotations on route function parameters and return
types. FastAPI reads these to:
1. Validate and coerce the incoming JSON body.
2. Add the schema to `/docs/`.
3. Validate the outgoing response if `response_model=` is set.

### Example: `GET /api/faces/{hash}` in `routes_face.py`

**Before (task-025 interim):**
```python
@face_router.get('/api/faces/{content_hash}')
async def get_face_boxes(content_hash: str):
    result = face_service.get_face_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    return result  # untyped dict
```

**After:**
```python
from benchmarking.schemas import GetFaceBoxesResponse

@face_router.get('/api/faces/{content_hash}', response_model=GetFaceBoxesResponse)
async def get_face_boxes(content_hash: str) -> GetFaceBoxesResponse:
    result = face_service.get_face_label(content_hash)
    if result is None:
        raise HTTPException(status_code=404, detail='Photo not found')
    return GetFaceBoxesResponse(**result)
```

### Example: `PUT /api/faces/{hash}` in `routes_face.py`

**Before:**
```python
@face_router.put('/api/faces/{content_hash}')
async def save_face_boxes(content_hash: str, body: dict = Body(...)):
    boxes_data = body.get('boxes', [])
    tags = body.get('tags', [])
    ...
```

**After:**
```python
from benchmarking.schemas import SaveFaceBoxesRequest

@face_router.put('/api/faces/{content_hash}')
async def save_face_boxes(content_hash: str, body: SaveFaceBoxesRequest):
    try:
        face_service.save_face_label(
            content_hash=content_hash,
            boxes_data=[b.model_dump() for b in body.boxes],
            tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {'status': 'ok'}
```

The manual `if not field: return 400` guards disappear because Pydantic raises
a 422 automatically if required fields are missing.

### Example: `POST /api/rename_identity`

**Before:**
```python
async def rename_identity_api(body: dict = Body(...)):
    old_name = (body.get('old_name') or '').strip()
    new_name = (body.get('new_name') or '').strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail='Missing old_name or new_name')
```

**After:**
```python
from benchmarking.schemas import RenameIdentityRequest, RenameIdentityResponse

async def rename_identity_api(body: RenameIdentityRequest) -> RenameIdentityResponse:
    # No manual validation — Pydantic ensures old_name and new_name are non-empty strings
    try:
        updated_count, ids = identity_service.rename_identity_across_gt(
            body.old_name.strip(), body.new_name.strip()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RenameIdentityResponse(updated_count=updated_count, identities=ids)
```

## Endpoint coverage checklist

| Endpoint | Request schema | Response schema |
|----------|---------------|-----------------|
| `GET /api/bibs` | — | `dict[str, BibBoxesListItem]` |
| `GET /api/bibs/{hash}` | — | `GetBibBoxesResponse` |
| `PUT /api/bibs/{hash}` | `SaveBibBoxesRequest` | `{'status': 'ok'}` |
| `GET /api/faces` | — | `dict[str, FaceBoxesListItem]` |
| `GET /api/faces/{hash}` | — | `GetFaceBoxesResponse` |
| `PUT /api/faces/{hash}` | `SaveFaceBoxesRequest` | `{'status': 'ok'}` |
| `GET /api/identities` | — | `IdentitiesResponse` |
| `POST /api/identities` | `CreateIdentityRequest` | `IdentitiesResponse` |
| `POST /api/rename_identity` | `RenameIdentityRequest` | `RenameIdentityResponse` |
| `GET /api/associations/{hash}` | — | `AssociationsResponse` |
| `PUT /api/associations/{hash}` | `SaveAssociationsRequest` | `AssociationsResponse` |
| `POST /api/freeze` | `FreezeRequest` | `FreezeResponse` |

## Tests

Existing tests that pass a raw dict to `client.post(..., json={...})` continue to
work unchanged — the JSON is deserialised into the Pydantic schema transparently.

Add negative-case tests to verify 422 responses:
- `test_save_face_boxes_missing_body()` — POST with no body → 422
- `test_rename_identity_empty_name()` — `{"old_name": "", "new_name": "x"}` → 422
  (Pydantic min-length or validator on the schema)
- `test_freeze_missing_hashes()` — body without `hashes` field → 422

## Scope boundaries

- **In scope**: `benchmarking/schemas.py` (new), `response_model=` annotations
  and typed body parameters on all API route handlers.
- **Out of scope**: UI (HTML/template) routes, service layer logic, domain models
  in `ground_truth.py`, URL paths.
- **Do not** change service function signatures — only the HTTP layer changes.
- **Do not** add `response_model=` to UI routes (they return `TemplateResponse`,
  which is not a Pydantic model).
