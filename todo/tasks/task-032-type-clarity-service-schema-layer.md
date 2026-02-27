# Task 032: Type clarity in service and schema layers

Independent of other open tasks. Can be done incrementally.

## Goal

Replace opaque `dict`, `list[dict]`, and `list[list[int]]` in service function
signatures and Pydantic response schemas with named types that already exist in
the codebase.

## Background

The service layer currently uses untyped dicts as the boundary between the HTTP
layer and business logic. This loses the value of having typed domain models
(`BibBox`, `FaceBox`, `BibSuggestion`, etc.) and makes it harder to understand
what data flows where.

## Context

`benchmarking/schemas.py` was introduced in task-026 to type the HTTP boundary.
The service layer (`bib_service.py`, `face_service.py`, `association_service.py`)
was explicitly left out of scope in task-026. This task extends the same
principle inward: services should speak domain types, not wire-format dicts.

## Changes in priority order

### 1. `boxes_data: list[dict]` → domain types in service params

**`benchmarking/services/bib_service.py:54`**

```python
# Before
def save_bib_label(content_hash: str, boxes_data: list[dict] | None,
                   bibs_legacy: list[int] | None, tags: list[str],
                   split: str) -> None:

# After
def save_bib_label(content_hash: str, boxes: list[BibBox],
                   bibs_legacy: list[int] | None, tags: list[str],
                   split: str) -> None:
```

The route already validates `BibBoxIn` objects — convert them to `BibBox` in the
route before calling the service, instead of passing dicts and re-validating.

**`benchmarking/services/face_service.py:91`**

```python
# Before
def save_face_label(content_hash: str, boxes_data: list[dict] | None,
                    tags: list[str]) -> None:

# After
def save_face_label(content_hash: str, boxes: list[FaceBox],
                    tags: list[str]) -> None:
```

Same pattern — route converts `FaceBoxIn` → `FaceBox`, service receives domain
objects directly.

Route call sites to update accordingly (pass `[BibBox(**b.model_dump()) for b in
body.boxes]` or add a `.to_domain()` helper on the `In` schemas).

### 2. `get_*_label() -> dict | None` → typed return

**`benchmarking/services/bib_service.py:17`** and
**`benchmarking/services/face_service.py:58`**

Both functions return a `dict` with shape documented only in the docstring. They
should either:

- Return the existing Pydantic model (`BibPhotoLabel` / `FacePhotoLabel`) plus a
  separate `suggestions` list, or
- Return a `TypedDict` that documents the shape statically.

The route layer is then responsible for constructing the response schema
(`GetBibBoxesResponse(**...)`) from the typed result.

### 3. `suggestions: list[dict]` in response schemas

**`benchmarking/schemas.py:45`** (`GetBibBoxesResponse`) and
**`benchmarking/schemas.py:84`** (`GetFaceBoxesResponse`)**

`BibSuggestion` and `FaceSuggestion` already exist in `ghost.py` as dataclasses
with known fields. Add equivalent Pydantic output schemas and use them:

```python
class BibSuggestionOut(BaseModel):
    x: float
    y: float
    w: float
    h: float
    number: str
    confidence: float

class FaceSuggestionOut(BaseModel):
    x: float
    y: float
    w: float
    h: float
    confidence: float
```

Then:

```python
class GetBibBoxesResponse(BaseModel):
    suggestions: list[BibSuggestionOut] = Field(default_factory=list)
    ...

class GetFaceBoxesResponse(BaseModel):
    suggestions: list[FaceSuggestionOut] = Field(default_factory=list)
    ...
```

### 4. `get_identity_suggestions() -> list[dict] | None`

**`benchmarking/services/face_service.py:139`**

Returns `[m.to_dict() for m in matches]` where `m` is `IdentityMatch` from
`face_embeddings.py`. Return `list[IdentityMatch] | None` directly; let the
route or a response schema serialise it.

Add an `IdentityMatchOut` schema in `schemas.py` (fields: `identity`, `similarity`,
`content_hash`, `box_index`) and use it as the response type for the identity
suggestions endpoint.

### 5. `Bbox = list[list[int]]` (cosmetic, lowest priority)

**`geometry.py:6`**

```python
# Before
Bbox = list[list[int]]

# After
Bbox = list[tuple[int, int]]  # 4 corner points, each (x, y)
```

Update `scale_bbox` to return tuples: `(int(p[0] * factor), int(p[1] * factor))`.

## Scope boundaries

- **In scope**: `benchmarking/services/bib_service.py`,
  `benchmarking/services/face_service.py`,
  `benchmarking/services/association_service.py`,
  `benchmarking/schemas.py`, `geometry.py`,
  and the route handlers that call the changed services.
- **Out of scope**: domain models in `ground_truth.py`, `ghost.py`,
  `face_embeddings.py` (avoid touching their internals).
- **Do not** change the JSON wire format — only internal Python types change.
- **Do not** change URL paths or HTTP status codes.

## Tests

All 250 existing tests must continue to pass unchanged. No new tests are required
unless a non-trivial conversion path is introduced (e.g. a `.to_domain()` helper
that warrants a unit test).
