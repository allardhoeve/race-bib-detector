# Task 022: URL restructure — CRUD gaps (deferred)

**DEFERRED — lower priority.**

Dependencies (task-019, task-020) are done.

## Goal

Fill the CRUD gaps: add JSON list endpoints for every resource, add DELETE endpoints
where missing, and add read endpoints for frozen sets and benchmark runs.

## Background

The API has consistent resource-centric URLs but is missing:

- Any GET-list endpoint that returns JSON.
- Any DELETE endpoint.
- GET endpoints for frozen sets — `POST /api/freeze` creates a set but there is no
  way to list or read sets via the API.
- JSON endpoints for benchmark runs — `/benchmark/` and `/benchmark/{run_id}/` return
  HTML only.

## Context

Missing operations by resource family:

- **Photos (bibs)** — no JSON list, no DELETE.
- **Photos (faces)** — no JSON list, no DELETE.
- **Associations (bib-face links)** — no JSON list, no DELETE (empty PUT is an
  acceptable workaround for delete today).
- **Identities** — list and create exist; no DELETE.
- **Frozen sets** — create exists; no list, no read.
- **Benchmark runs** — list and read exist as HTML; no JSON variant.

`GET /api/identities` already returns a JSON list. That endpoint is complete.

## Constraints

- Ground-truth files are managed via `ground_truth.py`. DELETE must call
  `remove_photo()` / `remove_links()` on the appropriate GT object and save.
- Benchmark run directories are written by the CLI runner and are read-only from the
  web app. There is no DELETE for runs — explicitly out of scope.
- The frozen-set store is managed by `benchmarking/sets.py`. Use `list_snapshots()`
  for the list endpoint. For single-set fetch, use `BenchmarkSnapshot.load(name)`.
- New list/delete service functions belong in the existing service modules under
  `benchmarking/services/`.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| JSON list response envelope | `{"items": [...], "count": N}` — consistent across all list endpoints |
| Hash representation in list responses | Full 64-char hash, not prefix |
| Labeled status field in list items | Include `"labeled": true/false` |
| DELETE bib/face label — remove record or mark unlabeled? | Remove the record entirely from the ground-truth store |
| DELETE associations — remove record or zero links? | Remove the record entirely (equivalent to the empty-PUT workaround) |
| DELETE identity — guard against use in GT? | Return 409 Conflict if the identity name appears in any face box; caller must reassign first |
| Sets list response | Full metadata per set but not the hash list — use GET /api/sets/{name} for hashes |
| Runs list response | Mirror the fields already in `list_runs()` in `runner.py` |

## Route file locations

All new API routes go in the existing files under `benchmarking/routes/api/`:

| New endpoints | File | Router |
|---------------|------|--------|
| GET/DELETE `/api/bibs/`, DELETE `/api/bibs/{hash}` | `routes/api/bibs.py` | `api_bibs_router` |
| GET `/api/associations/`, DELETE `/api/associations/{hash}` | `routes/api/bibs.py` | `api_bibs_router` |
| GET/DELETE `/api/faces/`, DELETE `/api/faces/{hash}` | `routes/api/faces.py` | `api_faces_router` |
| DELETE `/api/identities/{name}` | `routes/api/identities.py` | `api_identities_router` |
| GET `/api/sets/`, GET `/api/sets/{name}` | `routes/api/benchmark.py` | `api_benchmark_router` |
| GET `/api/runs/`, GET `/api/runs/{run_id}` | `routes/api/benchmark.py` | `api_benchmark_router` |

## Changes: `routes/api/bibs.py`

### New: `list_bibs()` — GET /api/bibs/

Response 200: `{"items": [{content_hash, labeled, split, tags, bib_count}, ...], "count": N}`

```python
@api_bibs_router.get('/api/bibs/')
async def list_bibs():
    items = bib_service.list_bibs()
    return {'items': items, 'count': len(items)}
```

Add `list_bibs() -> list[dict]` to `bib_service.py`. Iterate `load_photo_index()` and
`load_bib_ground_truth()`, return one dict per photo with `labeled` from
`label.labeled` (or `False` if no label).

Status codes: 200 always.

### New: `delete_bib_label()` — DELETE /api/bibs/{hash}

```python
@api_bibs_router.delete('/api/bibs/{content_hash}')
async def delete_bib_label(content_hash: str):
    result = bib_service.delete_bib_label(content_hash)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail='Not found')
    if result == 'not_labeled':
        raise HTTPException(status_code=409, detail='Not labeled')
    return {'status': 'deleted', 'content_hash': result}
```

Add `delete_bib_label(content_hash: str) -> str` to `bib_service.py`. Return the full
hash on success, `'not_found'` if hash unknown, `'not_labeled'` if no label exists.
`BibGroundTruth.remove_photo()` already exists — call it.

Status codes: 200 on success, 404 if hash unknown, 409 if no label exists.

### New: `list_associations()` — GET /api/associations/

Response 200: `{"items": [{content_hash, link_count}, ...], "count": N}`

```python
@api_bibs_router.get('/api/associations/')
async def list_associations():
    items = association_service.list_associations()
    return {'items': items, 'count': len(items)}
```

Add `list_associations() -> list[dict]` to `association_service.py`.

Status codes: 200 always.

### New: `delete_associations()` — DELETE /api/associations/{hash}

```python
@api_bibs_router.delete('/api/associations/{content_hash}')
async def delete_associations(content_hash: str):
    result = association_service.delete_associations(content_hash)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail='Not found')
    if result == 'no_links':
        raise HTTPException(status_code=409, detail='No links')
    return {'status': 'deleted', 'content_hash': result}
```

Add `delete_associations(content_hash: str) -> str` to `association_service.py`.
`LinkGroundTruth` has no `remove_links()` — add it (see below).

Status codes: 200 on success, 404 if hash unknown, 409 if no link record exists.

## Changes: `routes/api/faces.py`

### New: `list_faces()` — GET /api/faces/

Response 200: `{"items": [{content_hash, labeled, tags, face_count}, ...], "count": N}`

```python
@api_faces_router.get('/api/faces/')
async def list_faces():
    items = face_service.list_faces()
    return {'items': items, 'count': len(items)}
```

Add `list_faces() -> list[dict]` to `face_service.py`. Use `is_face_labeled()` from
`label_utils` for the `labeled` field (this is inferred; will become an explicit flag
when task-038 lands).

Status codes: 200 always.

### New: `delete_face_label()` — DELETE /api/faces/{hash}

```python
@api_faces_router.delete('/api/faces/{content_hash}')
async def delete_face_label(content_hash: str):
    result = face_service.delete_face_label(content_hash)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail='Not found')
    if result == 'not_labeled':
        raise HTTPException(status_code=409, detail='Not labeled')
    return {'status': 'deleted', 'content_hash': result}
```

Add `delete_face_label(content_hash: str) -> str` to `face_service.py`.
`FaceGroundTruth.remove_photo()` already exists — call it.

Status codes: 200 on success, 404 if hash unknown, 409 if no label exists.

## Changes: `routes/api/identities.py`

### New: `delete_identity()` — DELETE /api/identities/{name}

```python
@api_identities_router.delete('/api/identities/{name}')
async def delete_identity(name: str):
    result = identity_service.delete_identity(name)
    if result == 'not_found':
        raise HTTPException(status_code=404, detail='Identity not found')
    if isinstance(result, int):
        raise HTTPException(status_code=409, detail='Identity in use',
                            headers={'X-References': str(result)})
    return {'status': 'deleted', 'identities': result}
```

Add `delete_identity(name: str) -> list[str] | str | int` to `identity_service.py`.
Return updated identities list on success, `'not_found'` if name unknown, reference
count (int > 0) if name is in use in face GT.

Status codes: 200 on success, 404 if name unknown, 409 if referenced in GT.

## Changes: `routes/api/benchmark.py`

### New: `api_list_sets()` — GET /api/sets/

Response 200: `{"items": [{name, description, photo_count, created_at}, ...], "count": N}`

```python
@api_benchmark_router.get('/api/sets/')
async def api_list_sets():
    from benchmarking.sets import list_snapshots
    items = [s.to_dict() for s in list_snapshots()]
    return {'items': items, 'count': len(items)}
```

`list_snapshots()` exists in `sets.py` and returns `list[BenchmarkSnapshotMetadata]`.
`BenchmarkSnapshotMetadata.to_dict()` returns `{name, created_at, photo_count, description}`.
Note: the field is `photo_count`, not `hash_count`.

Status codes: 200 always.

### New: `api_get_set()` — GET /api/sets/{name}

Response 200: `{name, description, photo_count, created_at, hashes: [...]}`

```python
@api_benchmark_router.get('/api/sets/{name}')
async def api_get_set(name: str):
    from benchmarking.sets import BenchmarkSnapshot
    try:
        snapshot = BenchmarkSnapshot.load(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Set not found')
    return {**snapshot.metadata.to_dict(), 'hashes': sorted(snapshot.hashes)}
```

Status codes: 200 on success, 404 if name unknown.

### New: `api_list_runs()` — GET /api/runs/

Response 200: `{"items": [...], "count": N}`

```python
@api_benchmark_router.get('/api/runs/')
async def api_list_runs():
    from benchmarking.runner import list_runs
    items = list_runs()
    return {'items': items, 'count': len(items)}
```

`list_runs()` exists in `runner.py` (line 805). Each item includes: `run_id`,
`timestamp`, `split`, `precision`, `recall`, `f1`, `git_commit`, `total_photos`,
`pipeline`, `passes`, `note`, optionally `is_baseline`.

Status codes: 200 always.

### New: `api_get_run()` — GET /api/runs/{run_id}

```python
@api_benchmark_router.get('/api/runs/{run_id}')
async def api_get_run(run_id: str):
    from benchmarking.runner import get_run
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail='Run not found')
    return run.model_dump()
```

`get_run()` exists in `runner.py` (line 862) and returns `BenchmarkRun | None`.
`BenchmarkRun` is a Pydantic model with `model_dump()`.

Status codes: 200 on success, 404 if run_id unknown.

## Changes: `benchmarking/ground_truth.py`

`BibGroundTruth.remove_photo()` and `FaceGroundTruth.remove_photo()` **already exist**.

Add `remove_links()` to `LinkGroundTruth`:

```python
def remove_links(self, content_hash: str) -> bool:
    """Remove all links for content_hash. Returns True if a record was removed."""
    if content_hash in self.photos:
        del self.photos[content_hash]
        return True
    return False
```

## Changes: `benchmarking/services/identity_service.py`

Add `delete_identity()`:

```python
def delete_identity(name: str) -> list[str] | str | int:
    """Remove an identity. Returns updated list, 'not_found', or ref count if in use."""
    ids = load_identities()
    if name not in ids:
        return 'not_found'
    face_gt = load_face_ground_truth()
    ref_count = sum(
        1
        for label in face_gt.photos.values()
        for box in label.boxes
        if box.identity == name
    )
    if ref_count > 0:
        return ref_count
    updated = [i for i in ids if i != name]
    save_identities(updated)
    return updated
```

## Tests

Add to `tests/test_crud_gaps.py`:

- `test_list_bibs_returns_all_photos()` — GET `/api/bibs/` → 200 with `items` + `count`
- `test_list_bibs_includes_unlabeled()` — unlabeled photo has `labeled: false`
- `test_delete_bib_label_removes_record()` — DELETE `/api/bibs/{hash}` → 200; subsequent GET has `labeled: false`
- `test_delete_bib_label_not_found()` — unknown hash → 404
- `test_delete_bib_label_not_labeled()` — known but unlabeled photo → 409
- `test_list_faces_returns_all_photos()` — GET `/api/faces/` → 200 with `items`
- `test_delete_face_label_removes_record()` — DELETE `/api/faces/{hash}` → 200
- `test_delete_face_label_not_found()` → 404
- `test_list_associations_returns_items()` — GET `/api/associations/` → 200
- `test_delete_associations_removes_record()` — DELETE `/api/associations/{hash}` → 200
- `test_delete_associations_no_links()` → 409
- `test_delete_identity_ok()` — DELETE `/api/identities/{name}` → 200 when not in use
- `test_delete_identity_not_found()` → 404
- `test_delete_identity_in_use()` → 409
- `test_list_sets_empty()` — GET `/api/sets/` → 200 with empty items
- `test_get_set_not_found()` — GET `/api/sets/unknown` → 404
- `test_list_runs_returns_items()` — GET `/api/runs/` → 200 with `items`
- `test_get_run_not_found()` — GET `/api/runs/bad_id` → 404
- `test_get_run_returns_model_dump()` — GET `/api/runs/{id}` includes expected keys

## Scope boundaries

- **In scope**: new GET-list endpoints, new DELETE endpoints, GET /api/sets/ and
  GET /api/sets/{name}, GET /api/runs/ and GET /api/runs/{run_id}, `remove_links()`
  on `LinkGroundTruth`, `delete_identity()` in `identity_service.py`.
- **Out of scope**: routes already handled by task-019/020 — do not touch
  `/api/bibs/{hash}` GET/PUT, `/api/faces/{hash}` GET/PUT, `/api/associations/{hash}`
  GET/PUT, `PATCH /api/identities/{name}`, `POST /api/freeze`, any UI route.
- **Do not** add DELETE for benchmark runs.
- **Do not** add POST/PUT for sets — `POST /api/freeze` covers creation.
- **Do not** modify ground-truth JSON schema or Pydantic model fields.
- **Do not** change existing GET/POST handlers for identities.
