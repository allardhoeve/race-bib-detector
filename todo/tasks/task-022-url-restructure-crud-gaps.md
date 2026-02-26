# Task 022: URL restructure — CRUD gaps (deferred)

**DEFERRED — lower priority. Start only after task-019 and task-020 are merged.**

Depends on task-019 (UI routes) and task-020 (API routes). Independent of tasks 006–011.

## Goal

Fill the CRUD gaps identified in `API_REVIEW.md` sections 2 and 3: add JSON list endpoints
for every resource, add DELETE endpoints where missing, and add read endpoints for frozen
sets and benchmark runs. All new routes use the URL naming established by task-019/020.

## Background

After task-019 and task-020 land, the API has consistent resource-centric URLs
(`/api/bibs/<hash>`, `/api/faces/<hash>`, `/api/associations/<hash>`,
`/api/identities/<name>`) but is still missing:

- Any GET-list endpoint that returns JSON — callers have no machine-readable way to
  enumerate resources.
- Any DELETE endpoint — removing a label requires manually editing the ground-truth
  JSON files.
- GET endpoints for frozen sets — `POST /api/freeze` creates a set but there is no
  way to list or read sets via the API.
- JSON endpoints for benchmark runs — `/benchmark/` and `/benchmark/<run_id>/` return
  HTML only; a JSON equivalent is needed for scripting and future dashboard work.

See `API_REVIEW.md` sections 2 and 3 for the full gap analysis and naming-inconsistency
catalogue that motivated task-020. This task addresses only what task-020 left out.

## Context

`API_REVIEW.md` section 2 enumerates four resource families with missing operations:

- **Photos (bibs)** — no JSON list, no DELETE.
- **Photos (faces)** — no JSON list, no DELETE.
- **Associations (bib-face links)** — no JSON list, no DELETE (though an empty PUT is
  an acceptable workaround for delete today).
- **Identities** — list and create exist; no DELETE.
- **Freeze / sets** — create exists; no list, no read.
- **Benchmark runs** — list and read exist as HTML; no JSON variant.

`API_REVIEW.md` section 3 highlights that bibs and faces are parallel resources. New
list and delete endpoints must be symmetric: same field names, same status codes, same
error shapes, mirroring the GET/PUT symmetry already established by task-020.

`GET /api/identities` already returns a JSON list (see `routes_face.py` line 217–219).
That endpoint is complete and is noted below only to document the gap as closed.

## Constraints

- Do not touch any routes being renamed or added by task-019 or task-020. See "Scope
  boundaries" below.
- Ground-truth files are append-oriented JSON stores managed via `ground_truth.py`
  helpers. DELETE must call the appropriate `remove_photo` / `remove_links` method if
  one exists, or implement the removal directly via the `BibGroundTruth` /
  `FaceGroundTruth` / `LinkGroundTruth` objects and save.
- Benchmark run directories are written by the CLI runner and are read-only from the
  web app's perspective. There is no DELETE for runs — that is explicitly out of scope.
- The frozen-set store is managed by `benchmarking/sets.py`. Read endpoints must use
  the existing `list_sets()` / `get_set()` functions (or add them if absent).

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| JSON list response envelope | `{"items": [...], "count": N}` — consistent across all list endpoints |
| Hash representation in list responses | Full 64-char hash, not prefix — callers can truncate |
| Labeled status field in list items | Include `"labeled": true/false` so callers can replicate the filter logic |
| DELETE bib/face label — remove record or mark unlabeled? | Remove the record entirely from the ground-truth store |
| DELETE associations — remove record or zero links? | Remove the record entirely (equivalent to the empty-PUT workaround) |
| DELETE identity — guard against use in GT? | Return 409 Conflict if the identity name appears in any face box; caller must reassign first |
| Sets list response | Include full metadata per set (name, description, hash count, created_at) but not the hash list — use GET /api/sets/<name> for hashes |
| Runs list response | Mirror the fields already serialised for the HTML template in `routes_benchmark.py` |

## Changes: `benchmarking/routes_bib.py`

All new routes are added **after** the changes from task-020 are in place. The URLs
below use the task-020 names (`/api/bibs/<hash>`, `/api/associations/<hash>`).

### New: `list_bibs()` — GET /api/bibs/

```python
@bib_bp.route('/api/bibs/', methods=['GET'])
def list_bibs():
    """List all photos in the bib ground truth, with their labeled status.

    Response 200:
    {
        "items": [
            {
                "content_hash": "<64-char hex>",
                "labeled": true,
                "split": "full" | "iteration",
                "tags": ["<tag>", ...],
                "bib_count": <int>
            },
            ...
        ],
        "count": <int>
    }
    """
    index = load_photo_index()
    bib_gt = load_bib_ground_truth()
    items = []
    for h in sorted(index.keys()):
        label = bib_gt.get_photo(h)
        if label:
            items.append({
                'content_hash': h,
                'labeled': label.labeled,
                'split': label.split,
                'tags': label.tags,
                'bib_count': len(label.boxes),
            })
        else:
            items.append({
                'content_hash': h,
                'labeled': False,
                'split': None,
                'tags': [],
                'bib_count': 0,
            })
    return jsonify({'items': items, 'count': len(items)})
```

Status codes: 200 always (empty list when no photos).

### New: `delete_bib_label()` — DELETE /api/bibs/<hash>

```python
@bib_bp.route('/api/bibs/<content_hash>', methods=['DELETE'])
def delete_bib_label(content_hash):
    """Remove the bib label for a photo.

    Response 200:  {"status": "deleted", "content_hash": "<full hash>"}
    Response 404:  {"error": "Not found"}          — hash not in photo index
    Response 409:  {"error": "Not labeled"}        — photo exists but has no label
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Not found'}), 404

    bib_gt = load_bib_ground_truth()
    if not bib_gt.get_photo(full_hash):
        return jsonify({'error': 'Not labeled'}), 409

    bib_gt.remove_photo(full_hash)   # add this method to BibGroundTruth if absent
    save_bib_ground_truth(bib_gt)
    return jsonify({'status': 'deleted', 'content_hash': full_hash})
```

Status codes: 200 on success, 404 if hash unknown, 409 if no label exists.

### New: `list_associations()` — GET /api/associations/

```python
@bib_bp.route('/api/associations/', methods=['GET'])
def list_associations():
    """List all photos that have bib-face link records.

    Response 200:
    {
        "items": [
            {
                "content_hash": "<64-char hex>",
                "link_count": <int>
            },
            ...
        ],
        "count": <int>
    }
    """
    from benchmarking.ground_truth import load_link_ground_truth
    link_gt = load_link_ground_truth()
    items = [
        {'content_hash': h, 'link_count': len(links)}
        for h, links in sorted(link_gt.photos.items())
    ]
    return jsonify({'items': items, 'count': len(items)})
```

Status codes: 200 always.

### New: `delete_associations()` — DELETE /api/associations/<hash>

```python
@bib_bp.route('/api/associations/<content_hash>', methods=['DELETE'])
def delete_associations(content_hash):
    """Remove all bib-face links for a photo.

    Response 200:  {"status": "deleted", "content_hash": "<full hash>"}
    Response 404:  {"error": "Not found"}     — hash not in photo index
    Response 409:  {"error": "No links"}      — photo has no link record
    """
    from benchmarking.ground_truth import load_link_ground_truth, save_link_ground_truth
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Not found'}), 404

    link_gt = load_link_ground_truth()
    if full_hash not in link_gt.photos:
        return jsonify({'error': 'No links'}), 409

    link_gt.remove_links(full_hash)   # add this method to LinkGroundTruth if absent
    save_link_ground_truth(link_gt)
    return jsonify({'status': 'deleted', 'content_hash': full_hash})
```

Status codes: 200 on success, 404 if hash unknown, 409 if no link record exists.

## Changes: `benchmarking/routes_face.py`

All new routes are added after task-020 changes are in place.

### New: `list_faces()` — GET /api/faces/

```python
@face_bp.route('/api/faces/', methods=['GET'])
def list_faces():
    """List all photos in the face ground truth, with their labeled status.

    Response 200:
    {
        "items": [
            {
                "content_hash": "<64-char hex>",
                "labeled": true,
                "tags": ["<tag>", ...],
                "face_count": <int>
            },
            ...
        ],
        "count": <int>
    }
    """
    index = load_photo_index()
    face_gt = load_face_ground_truth()
    items = []
    for h in sorted(index.keys()):
        label = face_gt.get_photo(h)
        if label:
            items.append({
                'content_hash': h,
                'labeled': is_face_labeled(label),
                'tags': label.tags,
                'face_count': len(label.boxes),
            })
        else:
            items.append({
                'content_hash': h,
                'labeled': False,
                'tags': [],
                'face_count': 0,
            })
    return jsonify({'items': items, 'count': len(items)})
```

Status codes: 200 always.

### New: `delete_face_label()` — DELETE /api/faces/<hash>

```python
@face_bp.route('/api/faces/<content_hash>', methods=['DELETE'])
def delete_face_label(content_hash):
    """Remove the face label for a photo.

    Response 200:  {"status": "deleted", "content_hash": "<full hash>"}
    Response 404:  {"error": "Not found"}      — hash not in photo index
    Response 409:  {"error": "Not labeled"}    — photo exists but has no label
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Not found'}), 404

    face_gt = load_face_ground_truth()
    if not face_gt.get_photo(full_hash):
        return jsonify({'error': 'Not labeled'}), 409

    face_gt.remove_photo(full_hash)   # add this method to FaceGroundTruth if absent
    save_face_ground_truth(face_gt)
    return jsonify({'status': 'deleted', 'content_hash': full_hash})
```

Status codes: 200 on success, 404 if hash unknown, 409 if no label exists.

### New: `delete_identity()` — DELETE /api/identities/<name>

```python
@face_bp.route('/api/identities/<name>', methods=['DELETE'])
def delete_identity(name):
    """Remove an identity from the identities list.

    Refuses if the identity is referenced by any face box in the ground truth.

    Response 200:  {"status": "deleted", "identities": [...remaining list...]}
    Response 404:  {"error": "Identity not found"}
    Response 409:  {"error": "Identity in use", "references": <int>}
                   — caller must reassign or clear affected boxes first
    """
    from benchmarking.identities import load_identities, remove_identity

    ids = load_identities()
    if name not in ids:
        return jsonify({'error': 'Identity not found'}), 404

    # Guard: count references in face GT
    face_gt = load_face_ground_truth()
    ref_count = sum(
        1
        for label in face_gt.photos.values()
        for box in label.boxes
        if box.identity == name
    )
    if ref_count > 0:
        return jsonify({'error': 'Identity in use', 'references': ref_count}), 409

    remaining = remove_identity(name)   # add to benchmarking/identities.py if absent
    return jsonify({'status': 'deleted', 'identities': remaining})
```

Status codes: 200 on success, 404 if name not found, 409 if name is referenced in GT.

Note: `GET /api/identities` (list) and `POST /api/identities` (create) already exist and
are unchanged. `PATCH /api/identities/<name>` (rename) is added by task-020.

## Changes: `benchmarking/routes_benchmark.py`

### New: `api_list_sets()` — GET /api/sets/

```python
@benchmark_bp.route('/api/sets/', methods=['GET'])
def api_list_sets():
    """List all frozen sets.

    Response 200:
    {
        "items": [
            {
                "name": "<set name>",
                "description": "<description>",
                "hash_count": <int>,
                "created_at": "<ISO-8601 string>"
            },
            ...
        ],
        "count": <int>
    }

    The hash list is omitted; use GET /api/sets/<name> to retrieve it.
    """
    from benchmarking.sets import list_sets
    sets = list_sets()   # returns list of snapshot metadata dicts or objects
    items = [
        {
            'name': s['name'],
            'description': s.get('description', ''),
            'hash_count': s['hash_count'],
            'created_at': s['created_at'],
        }
        for s in sets
    ]
    return jsonify({'items': items, 'count': len(items)})
```

Status codes: 200 always (empty list when no sets exist).

### New: `api_get_set()` — GET /api/sets/<name>

```python
@benchmark_bp.route('/api/sets/<name>', methods=['GET'])
def api_get_set(name):
    """Return metadata and hash list for a named frozen set.

    Response 200:
    {
        "name": "<set name>",
        "description": "<description>",
        "hash_count": <int>,
        "created_at": "<ISO-8601 string>",
        "hashes": ["<64-char hex>", ...]
    }
    Response 404:  {"error": "Set not found"}
    """
    from benchmarking.sets import get_set
    snapshot = get_set(name)
    if snapshot is None:
        return jsonify({'error': 'Set not found'}), 404
    meta = snapshot.metadata.to_dict()
    return jsonify({**meta, 'hashes': sorted(snapshot.hashes)})
```

Status codes: 200 on success, 404 if name unknown.

### New: `api_list_runs()` — GET /api/runs/

```python
@benchmark_bp.route('/api/runs/', methods=['GET'])
def api_list_runs():
    """List all benchmark runs (JSON equivalent of GET /benchmark/).

    Response 200:
    {
        "items": [
            {
                "run_id": "<run id>",
                "created_at": "<ISO-8601 string>",
                "split": "<split name>",
                "photo_count": <int>,
                "precision": <float | null>,
                "recall": <float | null>,
                "f1": <float | null>
            },
            ...
        ],
        "count": <int>
    }

    Runs are ordered newest-first (same order as list_runs()).
    """
    runs = list_runs()
    items = [
        {
            'run_id': r['run_id'],
            'created_at': r.get('created_at'),
            'split': r.get('split'),
            'photo_count': r.get('photo_count'),
            'precision': r.get('precision'),
            'recall': r.get('recall'),
            'f1': r.get('f1'),
        }
        for r in runs
    ]
    return jsonify({'items': items, 'count': len(items)})
```

Status codes: 200 always (inspect `list_runs()` return shape to confirm field names
before implementing; adjust field names to match what `list_runs()` actually returns).

### New: `api_get_run()` — GET /api/runs/<run_id>

```python
@benchmark_bp.route('/api/runs/<run_id>', methods=['GET'])
def api_get_run(run_id):
    """Return full JSON for a benchmark run.

    Response 200:
    {
        "run_id": "<run id>",
        "created_at": "<ISO-8601 string>",
        "split": "<split name>",
        "photo_count": <int>,
        "precision": <float | null>,
        "recall": <float | null>,
        "f1": <float | null>,
        "metadata": { <pipeline config fields> },
        "photo_results": [
            {
                "content_hash": "<hash>",
                "expected_bibs": [...],
                "detected_bibs": [...],
                "tp": <int>,
                "fp": <int>,
                "fn": <int>,
                "status": "<ok|fp|fn|mixed>",
                "detection_time_ms": <float>,
                "tags": [...],
                "artifact_paths": {...},
                "preprocess_metadata": {...}
            },
            ...
        ]
    }
    Response 404:  {"error": "Run not found"}

    The photo_results field uses the same field set already serialised in
    benchmark_inspect() — keep the two in sync.
    """
    run = get_run(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404

    photo_results = [
        {
            'content_hash': r.content_hash,
            'expected_bibs': r.expected_bibs,
            'detected_bibs': r.detected_bibs,
            'tp': r.tp,
            'fp': r.fp,
            'fn': r.fn,
            'status': r.status,
            'detection_time_ms': r.detection_time_ms,
            'tags': r.tags,
            'artifact_paths': r.artifact_paths,
            'preprocess_metadata': r.preprocess_metadata,
        }
        for r in run.photo_results
    ]

    meta = {}
    if run.metadata.pipeline_config:
        meta['pipeline_summary'] = run.metadata.pipeline_config.summary()
    if run.metadata.face_pipeline_config:
        meta['passes_summary'] = run.metadata.face_pipeline_config.summary_passes()

    return jsonify({
        'run_id': run_id,
        'metadata': meta,
        'photo_results': photo_results,
        'photo_count': len(photo_results),
    })
```

Status codes: 200 on success, 404 if run_id unknown.

## Changes: `benchmarking/ground_truth.py`

If `BibGroundTruth`, `FaceGroundTruth`, or `LinkGroundTruth` do not already have
`remove_photo()` / `remove_links()` methods, add them:

```python
# In BibGroundTruth
def remove_photo(self, content_hash: str) -> None:
    """Remove the label for content_hash. No-op if not present."""
    self.photos.pop(content_hash, None)

# In FaceGroundTruth
def remove_photo(self, content_hash: str) -> None:
    """Remove the label for content_hash. No-op if not present."""
    self.photos.pop(content_hash, None)

# In LinkGroundTruth
def remove_links(self, content_hash: str) -> None:
    """Remove all links for content_hash. No-op if not present."""
    self.photos.pop(content_hash, None)
```

## Changes: `benchmarking/identities.py`

If `remove_identity()` does not already exist, add it:

```python
def remove_identity(name: str) -> list[str]:
    """Remove name from the identities list. Returns the updated list.

    Caller is responsible for ensuring the name is not in use in face GT
    before calling this function.
    """
    ids = load_identities()
    ids = [i for i in ids if i != name]
    _save_identities(ids)   # use whatever internal save function exists
    return ids
```

## Changes: `benchmarking/sets.py`

If `list_sets()` and `get_set()` do not already exist (task-006 may add them), add stubs:

```python
def list_sets() -> list[dict]:
    """Return metadata dicts for all frozen sets, newest first."""
    ...

def get_set(name: str):
    """Return the snapshot for name, or None if not found."""
    ...
```

Coordinate with task-006 (Staging/frozen sets) — if task-006 adds these, do not
duplicate them here; just import and call them.

## Tests

Add to `tests/test_routes_bib.py` (or a new `tests/test_crud_gaps.py`):

- `test_list_bibs_returns_all_photos()` — GET `/api/bibs/` returns 200 with `items` list
  and `count` equal to the number of photos in the index.
- `test_list_bibs_includes_unlabeled()` — an unlabeled photo appears with `labeled: false`.
- `test_delete_bib_label_removes_record()` — DELETE `/api/bibs/<hash>` returns 200;
  subsequent GET `/api/bibs/<hash>` returns `labeled: false`.
- `test_delete_bib_label_not_found()` — DELETE on unknown hash returns 404.
- `test_delete_bib_label_not_labeled()` — DELETE on known-but-unlabeled photo returns 409.
- `test_list_faces_returns_all_photos()` — GET `/api/faces/` returns 200 with `items`.
- `test_delete_face_label_removes_record()` — DELETE `/api/faces/<hash>` returns 200.
- `test_delete_face_label_not_found()` — returns 404.
- `test_list_associations_returns_items()` — GET `/api/associations/` returns 200.
- `test_delete_associations_removes_record()` — DELETE `/api/associations/<hash>` returns 200.
- `test_delete_associations_no_links()` — returns 409 when no link record exists.
- `test_delete_identity_ok()` — DELETE `/api/identities/<name>` returns 200 when not in use.
- `test_delete_identity_not_found()` — returns 404 for unknown name.
- `test_delete_identity_in_use()` — returns 409 when name appears in a face box.
- `test_list_sets_empty()` — GET `/api/sets/` returns 200 with empty items when no sets exist.
- `test_get_set_not_found()` — GET `/api/sets/unknown` returns 404.
- `test_list_runs_returns_items()` — GET `/api/runs/` returns 200 with `items` list.
- `test_get_run_not_found()` — GET `/api/runs/bad_id` returns 404.
- `test_get_run_returns_photo_results()` — GET `/api/runs/<id>` includes `photo_results`.

## Scope boundaries

- **In scope**: new GET-list endpoints, new DELETE endpoints, new GET /api/sets/ and
  GET /api/sets/<name>, new GET /api/runs/ and GET /api/runs/<run_id>, helper methods
  on ground-truth classes, `remove_identity()` in identities.py.
- **Out of scope**: any route renamed or added by task-019 or task-020 — do not touch
  `/api/bibs/<hash>` GET/PUT, `/api/faces/<hash>` GET/PUT, `/api/associations/<hash>`
  GET/PUT, `PATCH /api/identities/<name>`, `POST /api/freeze`, or any UI route.
- **Do not** add DELETE for benchmark runs — runs are created by the CLI and are
  considered immutable from the web app's perspective.
- **Do not** add POST/PUT for sets via this task — `POST /api/freeze` already covers
  creation and is handled by task-020.
- **Do not** modify the ground-truth JSON schema or data-class fields — only add
  `remove_photo()` / `remove_links()` methods that operate on the existing `photos` dict.
- **Do not** change the `GET /api/identities` or `POST /api/identities` handlers —
  they are already correct and not part of this task.
