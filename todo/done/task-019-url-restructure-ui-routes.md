# Task 019: URL restructure — UI and media routes

Independent of other tasks. See also task-020 (API routes, same theme).

## Goal

Rename and reorganise all user-facing HTML routes and binary-serving media routes
so that every subject has a consistent top-level namespace and no orphan paths exist.

## Background

Reviewed in `API_REVIEW.md`. Key problems:

- Bibs have no `/bibs/` prefix (`/labels/`, `/links/`) while faces already have `/faces/`.
- `/staging/` sits at the root but belongs logically under `/benchmark/`.
- `/photo/<hash>` and `/artifact/…` are binary-serving endpoints that are not namespaced.
- `/faces/labels/` has a redundant `/labels/` sub-level.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Name for the bib-face link labeling UI | `/associations/` — reflects equal-standing relationship |
| Where to put photo + artifact serving | `/media/` namespace — signals binary responses, not JSON |
| Face labeling URL depth | Flatten: `/faces/<hash>` (drop the intermediate `/labels/`) |
| Staging URL | Move to `/benchmark/staging/` |

## Full URL mapping

| Old URL | New URL | Handler (old → new) |
|---------|---------|---------------------|
| `/labels/` | `/bibs/` | `bib.labels_index` → `bib.bibs_index` |
| `/labels/<hash>` | `/bibs/<hash>` | `bib.label_photo` → `bib.bib_photo` |
| `/links/` | `/associations/` | `bib.links_index` → `bib.associations_index` |
| `/links/<hash>` | `/associations/<hash>` | `bib.link_photo` → `bib.association_photo` |
| `/faces/` | `/faces/` | `face.faces_root` — keep, still redirects |
| `/faces/labels/` | `/faces/` | `face.face_labels_index` → `face.faces_index` |
| `/faces/labels/<hash>` | `/faces/<hash>` | `face.face_label_photo` → `face.face_photo` |
| `/staging/` | `/benchmark/staging/` | `benchmark.staging` — name unchanged |
| `/photo/<hash>` | `/media/photos/<hash>` | `serve_photo` — name unchanged |
| `/artifact/<run_id>/<hash_prefix>/<type>` | `/media/artifacts/<run_id>/<hash_prefix>/<type>` | `benchmark.serve_artifact` — name unchanged |

All old URLs should redirect (HTTP 301) to new URLs to avoid dead links in bookmarks
or existing browser history. Add a redirect for each in the same handler file, or in
`web_app.py` for root-level ones.

## Changes: `benchmarking/routes_bib.py`

### Modified: route decorators and handler names

```python
# OLD
@bib_bp.route('/labels/')
def labels_index(): ...

@bib_bp.route('/labels/<content_hash>')
def label_photo(content_hash): ...

@bib_bp.route('/links/')
def links_index(): ...

@bib_bp.route('/links/<content_hash>')
def link_photo(content_hash): ...

# NEW
@bib_bp.route('/labels/')           # 301 redirect shim — keep for backward compat
def labels_index_redirect():
    return redirect(url_for('bib.bibs_index'), 301)

@bib_bp.route('/bibs/')
def bibs_index(): ...               # was labels_index

@bib_bp.route('/bibs/<content_hash>')
def bib_photo(content_hash): ...    # was label_photo

@bib_bp.route('/links/')            # 301 redirect shim
def links_index_redirect():
    return redirect(url_for('bib.associations_index'), 301)

@bib_bp.route('/associations/')
def associations_index(): ...       # was links_index

@bib_bp.route('/associations/<content_hash>')
def association_photo(content_hash): ...   # was link_photo
```

Update all internal `url_for('bib.label_photo', …)` → `url_for('bib.bib_photo', …)` etc.

## Changes: `benchmarking/routes_face.py`

### Modified: route decorators and handler names

```python
# OLD
@face_bp.route('/faces/')
def faces_root(): ...               # redirected to face_labels_index

@face_bp.route('/faces/labels/')
def face_labels_index(): ...

@face_bp.route('/faces/labels/<content_hash>')
def face_label_photo(content_hash): ...

# NEW
@face_bp.route('/faces/labels/')    # 301 redirect shim
def face_labels_redirect():
    return redirect(url_for('face.faces_index', **request.args), 301)

@face_bp.route('/faces/labels/<content_hash>')   # 301 redirect shim
def face_label_redirect(content_hash):
    return redirect(url_for('face.face_photo', content_hash=content_hash, **request.args), 301)

@face_bp.route('/faces/')
def faces_index(): ...              # was face_labels_index (also replaces faces_root)

@face_bp.route('/faces/<content_hash>')
def face_photo(content_hash): ...   # was face_label_photo
```

Update all internal `url_for('face.face_label_photo', …)` → `url_for('face.face_photo', …)` etc.

## Changes: `benchmarking/routes_benchmark.py`

### Modified: staging route

```python
# OLD
@benchmark_bp.route('/staging/')
def staging(): ...

# NEW
@benchmark_bp.route('/staging/')    # 301 redirect shim
def staging_redirect():
    return redirect(url_for('benchmark.staging'), 301)

@benchmark_bp.route('/benchmark/staging/')
def staging(): ...                  # name unchanged
```

### Modified: serve_artifact route

```python
# OLD
@benchmark_bp.route('/artifact/<run_id>/<hash_prefix>/<image_type>')
def serve_artifact(...): ...

# NEW
@benchmark_bp.route('/artifact/<run_id>/<hash_prefix>/<image_type>')  # 301 shim
def serve_artifact_redirect(run_id, hash_prefix, image_type):
    return redirect(url_for('benchmark.serve_artifact', run_id=run_id,
                            hash_prefix=hash_prefix, image_type=image_type), 301)

@benchmark_bp.route('/media/artifacts/<run_id>/<hash_prefix>/<image_type>')
def serve_artifact(...): ...        # name unchanged
```

## Changes: `benchmarking/web_app.py`

### Modified: serve_photo route

```python
# OLD
@app.route('/photo/<content_hash>')
def serve_photo(content_hash): ...

# NEW
@app.route('/photo/<content_hash>')   # 301 shim
def serve_photo_redirect(content_hash):
    return redirect(url_for('serve_photo', content_hash=content_hash), 301)

@app.route('/media/photos/<content_hash>')
def serve_photo(content_hash): ...    # name unchanged
```

## Changes: templates

Every `url_for()` call that references a renamed endpoint must be updated.
Hardcoded URL strings must be updated to use `url_for()` instead.

### `templates/labeling.html`

| Old | New |
|-----|-----|
| `url_for('face.face_labels_index')` | `url_for('face.faces_index')` |
| `url_for('bib.link_photo', content_hash=…)` | `url_for('bib.association_photo', content_hash=…)` |
| `url_for('bib.save_label')` (PAGE_DATA.saveUrl) | unchanged (API task-020) |
| `url_for('bib.labels_index')` (PAGE_DATA.labelsIndexUrl) | `url_for('bib.bibs_index')` |

### `templates/face_labeling.html`

| Old | New |
|-----|-----|
| `url_for('bib.labels_index')` | `url_for('bib.bibs_index')` |
| `url_for('bib.link_photo', content_hash=…)` | `url_for('bib.association_photo', content_hash=…)` |
| `url_for('face.save_face_label')` (PAGE_DATA.saveUrl) | unchanged (API task-020) |
| `url_for('face.face_labels_index')` (PAGE_DATA.labelsIndexUrl) | `url_for('face.faces_index')` |

### `templates/link_labeling.html`

| Old | New |
|-----|-----|
| `url_for('bib.label_photo', content_hash=…)` | `url_for('bib.bib_photo', content_hash=…)` |
| `url_for('face.face_label_photo', content_hash=…)` | `url_for('face.face_photo', content_hash=…)` |

### `templates/benchmark_inspect.html`

| Old | New |
|-----|-----|
| `url_for('bib.labels_index')` (editLinkBase) | `url_for('bib.bibs_index')` |
| `url_for('serve_photo', …)` | unchanged (name stays `serve_photo`) |
| `url_for('benchmark.serve_artifact', …)` | unchanged (name stays) |

### `templates/benchmark_list.html`

| Old | New |
|-----|-----|
| `url_for('bib.labels_index')` | `url_for('bib.bibs_index')` |

### `templates/labels_home.html`

| Old | New |
|-----|-----|
| `url_for('bib.labels_index')` | `url_for('bib.bibs_index')` |
| `url_for('face.face_labels_index')` | `url_for('face.faces_index')` |
| `/links/` (hardcoded href) | `url_for('bib.associations_index')` |

### `templates/staging.html`

| Old | New |
|-----|-----|
| `/labels/{{ r.content_hash }}/` (×2, hardcoded) | `url_for('bib.bib_photo', content_hash=r.content_hash[:8])` |
| `/faces/labels/{{ r.content_hash }}/` (×2, hardcoded) | `url_for('face.face_photo', content_hash=r.content_hash[:8])` |
| Links column `/labels/…` (×2, hardcoded, wrong anyway) | `url_for('bib.association_photo', content_hash=r.content_hash[:8])` |

## Changes: `benchmarking/routes_bib.py` — url_for calls inside handlers

The handlers that compute `prev_url`, `next_url`, `next_unlabeled_url` reference
old endpoint names. Update every `url_for('bib.label_photo', …)` → `url_for('bib.bib_photo', …)`
and `url_for('bib.link_photo', …)` → `url_for('bib.association_photo', …)`.

Same for `routes_face.py`: `url_for('face.face_label_photo', …)` → `url_for('face.face_photo', …)`.

## Tests

Existing route tests will break on old URLs — update expected URL strings.
Add smoke tests:

- `test_old_labels_url_redirects_301()` — GET `/labels/` returns 301 to `/bibs/`
- `test_old_faces_labels_url_redirects_301()` — GET `/faces/labels/` returns 301 to `/faces/`
- `test_old_staging_url_redirects_301()` — GET `/staging/` returns 301 to `/benchmark/staging/`
- `test_bibs_index_ok()` — GET `/bibs/` returns 302 (to first photo) or 200
- `test_faces_index_ok()` — GET `/faces/` returns 302 or 200
- `test_associations_index_ok()` — GET `/associations/` returns 302 or 200

## Scope boundaries

- **In scope**: route URL strings, handler names, `url_for()` calls in Python and templates, 301 redirect shims for old URLs
- **Out of scope**: API routes (`/api/…`) — handled in task-020; JS files — no JS touches UI route URLs, those come via `url_for()` in templates passed through `PAGE_DATA`
- **Do not** rename blueprint identifiers (`bib_bp`, `face_bp`, `benchmark_bp`) — that would widen the diff unnecessarily
