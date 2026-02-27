# Task 033: Rename `body` → `request` in API route handlers

Depends on task-026 (typed request/response schemas). Small, mechanical rename.

## Goal

Replace the Flask-style `body` parameter name with the more idiomatic FastAPI
name `request` in all API route handler signatures. This makes it clear that
the variable holds a validated Pydantic request object, not a raw `dict`.

## Background

After task-026, every mutating route accepts a typed Pydantic schema instead of
`body: dict = Body(...)`. The parameter name `body` is a leftover from the Flask
style where `body = request.get_json()` was the idiom. In FastAPI the parameter
name is part of the function signature and can be anything; `request` better
communicates that this is the deserialized request payload.

Note: FastAPI reserves the name `request` for `fastapi.Request` (the raw HTTP
request object). However, none of the routes that take a Pydantic body also
inject a `fastapi.Request` — the two don't coexist — so there is no naming
conflict in practice.

## Affected functions (6 occurrences)

| File | Function | Change |
|------|----------|--------|
| `routes/api/bibs.py` | `save_bib_label` | `body: SaveBibBoxesRequest` → `request: SaveBibBoxesRequest` |
| `routes/api/bibs.py` | `save_associations` | `body: SaveAssociationsRequest` → `request: SaveAssociationsRequest` |
| `routes/api/benchmark.py` | `api_freeze` | `body: FreezeRequest` → `request: FreezeRequest` |
| `routes/api/faces.py` | `save_face_label` | `body: SaveFaceBoxesRequest` → `request: SaveFaceBoxesRequest` |
| `routes/api/identities.py` | `post_identity` | `body: CreateIdentityRequest` → `request: CreateIdentityRequest` |
| `routes/api/identities.py` | `patch_identity` | `body: PatchIdentityRequest` → `request: PatchIdentityRequest` |

In each function, also rename every `body.xxx` reference to `request.xxx`.

## Tests

No test changes needed — tests call the HTTP endpoints, not the function
parameters directly. Run `pytest` to confirm all 332 tests still pass.

## Scope boundaries

- **In scope**: parameter name in function signature + all `body.` references
  within the same function body.
- **Out of scope**: `schemas.py`, service layer, tests, UI routes, shims.
- **Do not** rename the `Request` import from `fastapi` (used in shims) or
  `starlette.responses` — only the local parameter variable name changes.
