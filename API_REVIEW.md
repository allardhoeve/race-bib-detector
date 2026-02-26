# API Review

## 1. Full Route Inventory

All routes registered by the Flask app, grouped by blueprint.

### Root (`web_app.py`)

| Method | URL | Handler | Notes |
|--------|-----|---------|-------|
| GET | `/` | `index` | Landing page with progress stats |
| GET | `/photo/<content_hash>` | `serve_photo` | Serve photo binary by hash prefix |
| GET | `/test/labeling` | `test_labeling` | Redirect to static test HTML |

### Bib blueprint (`routes_bib.py`)

| Method | URL | Handler | Notes |
|--------|-----|---------|-------|
| GET | `/labels/` | `labels_index` | Redirect to first photo in filter |
| GET | `/labels/<content_hash>` | `label_photo` | Bib labeling UI |
| POST | `/api/labels` | `save_label` | Save bib boxes + tags + split |
| GET | `/api/bib_boxes/<content_hash>` | `get_bib_boxes` | Bib boxes, suggestions, tags, split |
| GET | `/links/` | `links_index` | Redirect to first photo for link labeling |
| GET | `/links/<content_hash>` | `link_photo` | Bib-face link labeling UI |
| GET | `/api/bib_face_links/<content_hash>` | `get_bib_face_links` | Get links for a photo |
| PUT | `/api/bib_face_links/<content_hash>` | `save_bib_face_links` | Replace all links for a photo |

### Face blueprint (`routes_face.py`)

| Method | URL | Handler | Notes |
|--------|-----|---------|-------|
| GET | `/faces/` | `faces_root` | Redirect to `/faces/labels/` |
| GET | `/faces/labels/` | `face_labels_index` | Redirect to first photo in filter |
| GET | `/faces/labels/<content_hash>` | `face_label_photo` | Face labeling UI |
| POST | `/api/face_labels` | `save_face_label` | Save face boxes + tags |
| GET | `/api/face_boxes/<content_hash>` | `get_face_boxes` | Face boxes, suggestions, tags |
| GET | `/api/identities` | `get_identities` | List all identities |
| POST | `/api/identities` | `post_identity` | Add new identity |
| POST | `/api/rename_identity` | `rename_identity_api` | Rename identity (updates all GT boxes) |
| GET | `/api/face_identity_suggestions/<content_hash>` | `face_identity_suggestions` | Embedding-based identity suggestions (query params: box_x/y/w/h, k) |
| GET | `/api/face_crop/<content_hash>/<box_index>` | `face_crop` | Serve JPEG crop of a labeled face box |

### Benchmark blueprint (`routes_benchmark.py`)

| Method | URL | Handler | Notes |
|--------|-----|---------|-------|
| GET | `/benchmark/` | `benchmark_list` | List all benchmark runs |
| GET | `/benchmark/<run_id>/` | `benchmark_inspect` | Inspect a run; filter/idx/hash query params |
| GET | `/staging/` | `staging` | Completeness overview across labeling steps |
| POST | `/api/freeze` | `api_freeze` | Freeze a set of hashes into a named snapshot |
| GET | `/artifact/<run_id>/<hash_prefix>/<image_type>` | `serve_artifact` | Serve a pipeline artifact image |

---

## 2. CRUD Gap Analysis

### Photos (bib labeling)

| Operation | Method | URL | Status |
|-----------|--------|-----|--------|
| List | GET | `/labels/` | UI redirect only, no JSON list |
| Read | GET | `/api/bib_boxes/<hash>` | ✓ |
| Create/Replace | POST | `/api/labels` | ✓ (acts as full replace) |
| Update | PUT | — | **Missing** — POST acts as PUT conceptually |
| Delete | DELETE | — | **Missing** |

### Photos (face labeling)

| Operation | Method | URL | Status |
|-----------|--------|-----|--------|
| List | GET | `/faces/labels/` | UI redirect only, no JSON list |
| Read | GET | `/api/face_boxes/<hash>` | ✓ |
| Create/Replace | POST | `/api/face_labels` | ✓ (acts as full replace) |
| Update | PUT | — | **Missing** — POST acts as PUT conceptually |
| Delete | DELETE | — | **Missing** |

### Bib-Face Links

| Operation | Method | URL | Status |
|-----------|--------|-----|--------|
| Read | GET | `/api/bib_face_links/<hash>` | ✓ |
| Replace | PUT | `/api/bib_face_links/<hash>` | ✓ |
| Delete | DELETE | — | **Missing** (can PUT empty list as workaround) |

### Identities

| Operation | Method | URL | Status |
|-----------|--------|-----|--------|
| List | GET | `/api/identities` | ✓ |
| Create | POST | `/api/identities` | ✓ |
| Rename | POST | `/api/rename_identity` | ✓ (but verb-in-URL is RPC-style) |
| Delete | DELETE | — | **Missing** |

### Benchmark Runs

| Operation | Method | URL | Status |
|-----------|--------|-----|--------|
| List | GET | `/benchmark/` | UI only, no JSON list |
| Read | GET | `/benchmark/<run_id>/` | UI only, no JSON |
| Create | — | — | Runs are created via CLI, not API |
| Delete | DELETE | — | **Missing** (not a priority) |

### Freeze / Sets

| Operation | Method | URL | Status |
|-----------|--------|-----|--------|
| Create | POST | `/api/freeze` | ✓ |
| List | GET | — | **Missing** |
| Read | GET | — | **Missing** |

---

## 3. Interface Inconsistencies Between Subjects

The bib and face domains parallel each other but have diverged in naming and method:

| Concern | Bibs | Faces | Problem |
|---------|------|-------|---------|
| UI root prefix | `/labels/` | `/faces/labels/` | Bibs have no `bibs/` prefix |
| Save label endpoint | `POST /api/labels` | `POST /api/face_labels` | No `bib_` prefix on bib endpoint |
| Fetch boxes endpoint | `GET /api/bib_boxes/<hash>` | `GET /api/face_boxes/<hash>` | Consistent naming here |
| HTTP method for save | POST (replaces all) | POST (replaces all) | Should be PUT since it is idempotent |
| Rename operation | — | `POST /api/rename_identity` | Verb in URL; should be `PATCH /api/identities/<name>` |
| Suggestions | ghost system (in `get_bib_boxes`) | ghost + embedding (in `get_face_boxes` + separate endpoint) | Face has an extra endpoint for embedding suggestions |

---

## 4. Swagger / OpenAPI View

The simplest path is **Flasgger**, which reads OpenAPI/Swagger YAML from docstrings and adds a `/apidocs/` UI with zero model changes:

```
pip install flasgger
```

```python
# in create_app()
from flasgger import Swagger
Swagger(app)
```

Then annotate each route with an OpenAPI docstring block:

```python
@face_bp.route('/api/face_boxes/<content_hash>')
def get_face_boxes(content_hash):
    """
    Get face boxes, suggestions, and tags for a photo.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
    responses:
      200:
        description: Face boxes with suggestions
        schema:
          type: object
          properties:
            boxes:
              type: array
            suggestions:
              type: array
            tags:
              type: array
      404:
        description: Photo not found
    """
```

This gives a browsable API at `http://localhost:30002/apidocs/` with try-it-out support.

An alternative is **flask-smorest** which enforces schemas via marshmallow and generates OpenAPI 3.0 automatically — more work upfront but makes validation explicit.

---

## 5. Code Structure Analysis

### Current structure

```
benchmarking/
  routes_bib.py       — UI + API for bibs + bib-face links
  routes_face.py      — UI + API for faces + identities + suggestions
  routes_benchmark.py — UI + API for runs + staging + freeze + artifacts
  web_app.py          — app factory, root routes
```

This is the "one file per subject" organisation. It works well at this scale, but the files are blurring three concerns: HTTP routing, business logic, and data access.

### Django analogy

Django separates:
- **Model**: field definitions + persistence (`models.py`)
- **View**: HTTP logic only — deserialise request, call service, serialise response (`views.py`)
- **URL conf**: mapping from URLs to views (`urls.py`)

DRF adds:
- **Serializer**: validates + transforms data between Python objects and JSON
- **ViewSet**: groups CRUD operations for one resource into a single class

### Where our code diverges

The route handlers currently do all of: hash lookup, data loading, business logic, and response serialisation inline. For example `save_face_label` in `routes_face.py` constructs the `FacePhotoLabel`, saves it, and returns the response — that middle step (construct + save) belongs in a service layer.

### Recommended layering (without a full rewrite)

```
benchmarking/
  routes/
    __init__.py         — register blueprints
    bib.py              — GET/POST UI + API for bibs
    face.py             — GET/POST UI + API for faces
    identities.py       — CRUD for identities (split from face.py)
    links.py            — GET/PUT for bib-face links
    benchmark.py        — runs + staging + freeze + artifacts
  services/
    bib_service.py      — load_bib_label(), save_bib_label(), etc.
    face_service.py     — load_face_label(), save_face_label(), etc.
    identity_service.py — list/add/rename/delete identity
    link_service.py     — get_links(), set_links()
```

The `ground_truth.py` data classes stay as the **model** layer. The new `services/` files wrap them with domain logic. Routes become thin: validate input → call service → return JSON.

This also makes unit-testing easier: services can be tested without a Flask test client.

### Whether a full MVC split is needed now

At ~400 lines of route code total, moving to a separate service layer is a worthwhile refactor but not urgent. The most impactful immediate improvements are:

1. Fix naming inconsistencies (rename `/api/labels` → `/api/bib_labels`, add `bibs/` prefix to UI, change save operations from POST to PUT).
2. Split `routes_face.py` — identities are a separate resource and should have their own file/blueprint.
3. Add Flasgger for the Swagger UI.
4. Then introduce a `services/` layer progressively as each area is touched.
