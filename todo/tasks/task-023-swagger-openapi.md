# Task 023: Swagger / OpenAPI browsable UI

Depends on task-019 (UI URL restructure) and task-020 (API URL restructure). Independent of tasks 006–011.

## Goal

Add Flasgger to the Flask app so that every `/api/…` endpoint is documented with
an OpenAPI 2.0 (Swagger) YAML docstring, and developers can browse and try out the
API at `http://localhost:30002/apidocs/`.

## Background

Reviewed in `API_REVIEW.md`, section 4. The app has ~12 JSON API endpoints spread
across three blueprints. There is no machine-readable contract today; the only
documentation is the existing route docstrings, which are informal.

Flasgger reads YAML from route function docstrings and mounts the Swagger UI at
`/apidocs/` with no additional template or JavaScript to maintain. It is the lowest-
friction option for a small internal tool.

## Context

This task must follow task-019 and task-020. Documenting the old URLs (e.g.
`/api/bib_boxes/<hash>`) would be wasteful because those routes become 308 redirect
shims after the restructure. The docstrings in this task target only the new,
canonical URL. Redirect shims must NOT receive Flasgger docstrings (Flasgger would
parse any `---` block in the docstring, producing spurious endpoints in the UI).

`flask-smorest` is an alternative that enforces marshmallow schemas and generates
OpenAPI 3.0 automatically, but it would require adding serializer classes for every
request/response type and rewriting the route functions as class-based views. That
upfront cost is not justified for this codebase today. Flasgger keeps the diff
minimal: one `pip install`, one call in `create_app()`, and docstring additions.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Library | Flasgger — reads YAML from docstrings, zero schema boilerplate |
| OpenAPI version | 2.0 (Swagger) — Flasgger default; sufficient for try-it-out |
| Scope | Only `/api/…` routes. HTML routes and `/media/…` routes are excluded |
| Registration point | `create_app()` in `benchmarking/web_app.py` |
| Redirect shims | No Flasgger docstrings on shim handlers; shims return 308/410 only |

## Constraints

- Do not add Flasgger docstrings to the 308/410 redirect shim handlers introduced
  by task-019 and task-020. Flasgger will parse any function docstring that contains
  `---`, producing junk entries in the UI.
- `GET /api/faces/<hash>/crop/<box_index>` returns `image/jpeg`, not JSON. Document
  it with `produces: [image/jpeg]` and a `200` response with `schema: {type: string,
  format: binary}`. Do not claim it returns JSON.
- Keep the YAML blocks concise — avoid spelling out every enum value in the schema
  unless it adds clarity.

## Changes: `requirements.txt`

Add one line:

```
flasgger>=0.9.7
```

`pyproject.toml` contains only tool configuration (ruff, pytest), not dependencies,
so only `requirements.txt` needs updating.

## Changes: `benchmarking/web_app.py`

### Modified: `create_app()`

```python
# Add import at the top of the file:
from flasgger import Swagger

# In create_app(), after `app = Flask(...)` and before blueprint registration:
Swagger(app, template={
    "info": {
        "title": "Benchmark Labeling API",
        "description": (
            "Internal API for the bib and face labeling tool. "
            "All endpoints are under /api/. "
            "UI routes (/bibs/, /faces/, /associations/, /benchmark/) "
            "and media routes (/media/) are not documented here."
        ),
        "version": "1.0",
    },
    "host": "localhost:30002",
    "basePath": "/",
    "consumes": ["application/json"],
    "produces": ["application/json"],
})
```

## Changes: `benchmarking/routes_bib.py`

Document the four API handlers introduced by task-020. The old `save_label`,
`get_bib_boxes`, `get_bib_face_links`, and `save_bib_face_links` handlers become
redirect shims — they must NOT receive Flasgger docstrings.

### New docstring: `get_bib_boxes` (renamed to primary handler at `GET /api/bibs/<hash>`)

```python
@bib_bp.route('/api/bibs/<content_hash>', methods=['GET'])
def get_bib_boxes(content_hash):
    """Get bib boxes, suggestions, tags, split, and labeled status for a photo.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: >
          SHA-256 content hash of the photo, or an unambiguous prefix (minimum 8
          characters). Full hash is always accepted.
    responses:
      200:
        description: Bib label data for the photo.
        schema:
          type: object
          properties:
            boxes:
              type: array
              description: >
                Labeled bib boxes. Each box has normalised [0,1] coordinates.
                Boxes with w=0, h=0 are legacy entries without spatial data.
              items:
                type: object
                properties:
                  x: {type: number, format: float}
                  y: {type: number, format: float}
                  w: {type: number, format: float}
                  h: {type: number, format: float}
                  number:
                    type: string
                    description: Bib number as a string (may include '?' for uncertain digits).
                  scope:
                    type: string
                    description: >
                      'bib' (scored), 'bib_clipped' (scored, partially out of frame),
                      'not_bib' (unscored), 'bib_obscured' (unscored).
            suggestions:
              type: array
              description: Ghost-labeled box suggestions not yet reviewed by the labeler.
              items:
                type: object
                properties:
                  x: {type: number, format: float}
                  y: {type: number, format: float}
                  w: {type: number, format: float}
                  h: {type: number, format: float}
                  number: {type: string}
            tags:
              type: array
              description: Photo-level bib condition tags.
              items:
                type: string
            split:
              type: string
              description: Evaluation split ('full' or 'iteration').
            labeled:
              type: boolean
              description: True once a human has reviewed this photo.
      404:
        description: Photo not found in the index.
    """
```

### New docstring: `save_bib_label` (new PUT handler at `PUT /api/bibs/<hash>`)

```python
@bib_bp.route('/api/bibs/<content_hash>', methods=['PUT'])
def save_bib_label(content_hash):
    """Save bib boxes, tags, and split for a photo. Replaces all existing data.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [boxes]
          properties:
            boxes:
              type: array
              description: Full list of bib boxes to store (replaces existing list).
              items:
                type: object
                required: [x, y, w, h, number, scope]
                properties:
                  x: {type: number, format: float}
                  y: {type: number, format: float}
                  w: {type: number, format: float}
                  h: {type: number, format: float}
                  number: {type: string}
                  scope:
                    type: string
                    enum: [bib, bib_clipped, not_bib, bib_obscured]
            tags:
              type: array
              description: Photo-level bib condition tags. Defaults to [].
              items: {type: string}
            split:
              type: string
              description: Evaluation split. Defaults to 'full'.
              enum: [full, iteration]
    responses:
      200:
        description: Save confirmed.
        schema:
          type: object
          properties:
            status: {type: string, example: ok}
      400:
        description: Invalid request body (bad scope value, missing field, etc.).
      404:
        description: Photo not found in the index.
    """
```

### New docstring: `get_associations` (new GET handler at `GET /api/associations/<hash>`)

```python
@bib_bp.route('/api/associations/<content_hash>', methods=['GET'])
def get_associations(content_hash):
    """Get bib-face associations (links) for a photo.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
    responses:
      200:
        description: List of bib-face index pairs for this photo.
        schema:
          type: object
          properties:
            links:
              type: array
              description: >
                Each element is [bib_index, face_index] where bib_index is
                the 0-based index into the photo's bib boxes list and
                face_index is the 0-based index into the face boxes list.
              items:
                type: array
                items: {type: integer}
                minItems: 2
                maxItems: 2
      404:
        description: Photo not found in the index.
    """
```

### New docstring: `save_associations` (new PUT handler at `PUT /api/associations/<hash>`)

```python
@bib_bp.route('/api/associations/<content_hash>', methods=['PUT'])
def save_associations(content_hash):
    """Save bib-face associations for a photo. Replaces all existing links.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [links]
          properties:
            links:
              type: array
              description: >
                Full replacement list of [bib_index, face_index] pairs.
                Send an empty array to clear all associations.
              items:
                type: array
                items: {type: integer}
                minItems: 2
                maxItems: 2
    responses:
      200:
        description: Save confirmed; echoes the stored links.
        schema:
          type: object
          properties:
            status: {type: string, example: ok}
            links:
              type: array
              items:
                type: array
                items: {type: integer}
      400:
        description: Invalid JSON or malformed link pairs.
      404:
        description: Photo not found in the index.
    """
```

## Changes: `benchmarking/routes_face.py`

Document the six API handlers introduced by task-020. Shim handlers (`get_face_boxes_redirect`,
`save_face_label_legacy`, `face_crop_redirect`, `face_identity_suggestions_redirect`,
`rename_identity_legacy`) must NOT receive Flasgger docstrings.

### New docstring: `get_face_boxes` (new GET handler at `GET /api/faces/<hash>`)

```python
@face_bp.route('/api/faces/<content_hash>', methods=['GET'])
def get_face_boxes(content_hash):
    """Get face boxes, ghost suggestions, and photo tags for a photo.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
    responses:
      200:
        description: Face label data for the photo.
        schema:
          type: object
          properties:
            boxes:
              type: array
              description: Labeled face boxes with normalised [0,1] coordinates.
              items:
                type: object
                properties:
                  x: {type: number, format: float}
                  y: {type: number, format: float}
                  w: {type: number, format: float}
                  h: {type: number, format: float}
                  scope:
                    type: string
                    description: "'keep' (scored), 'exclude', or 'uncertain'."
                  identity:
                    type: string
                    description: Named identity, or null if unknown.
                    nullable: true
                  tags:
                    type: array
                    description: Per-box condition tags (tiny, blurry, occluded, profile, looking_down).
                    items: {type: string}
            suggestions:
              type: array
              description: Ghost-labeled face box suggestions not yet reviewed.
              items:
                type: object
                properties:
                  x: {type: number, format: float}
                  y: {type: number, format: float}
                  w: {type: number, format: float}
                  h: {type: number, format: float}
            tags:
              type: array
              description: Photo-level face condition tags (no_faces, light_faces).
              items: {type: string}
      404:
        description: Photo not found in the index.
    """
```

### New docstring: `save_face_label` (new PUT handler at `PUT /api/faces/<hash>`)

```python
@face_bp.route('/api/faces/<content_hash>', methods=['PUT'])
def save_face_label(content_hash):
    """Save face boxes and photo tags for a photo. Replaces all existing data.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [boxes]
          properties:
            boxes:
              type: array
              description: Full list of face boxes to store (replaces existing list).
              items:
                type: object
                required: [x, y, w, h, scope]
                properties:
                  x: {type: number, format: float}
                  y: {type: number, format: float}
                  w: {type: number, format: float}
                  h: {type: number, format: float}
                  scope:
                    type: string
                    enum: [keep, exclude, uncertain]
                  identity:
                    type: string
                    nullable: true
                    description: Named identity, or omit/null if unknown.
                  tags:
                    type: array
                    description: Per-box condition tags.
                    items: {type: string}
            face_tags:
              type: array
              description: Photo-level face condition tags. Defaults to [].
              items: {type: string}
    responses:
      200:
        description: Save confirmed.
        schema:
          type: object
          properties:
            status: {type: string, example: ok}
      400:
        description: Invalid request body.
      404:
        description: Photo not found in the index.
    """
```

### New docstring: `get_identities` (GET handler at `GET /api/identities`)

```python
@face_bp.route('/api/identities')
def get_identities():
    """List all known face identities.
    ---
    responses:
      200:
        description: Sorted list of identity name strings.
        schema:
          type: object
          properties:
            identities:
              type: array
              items: {type: string}
    """
```

### New docstring: `post_identity` (POST handler at `POST /api/identities`)

```python
@face_bp.route('/api/identities', methods=['POST'])
def post_identity():
    """Add a new face identity.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [name]
          properties:
            name:
              type: string
              description: Display name for the new identity.
    responses:
      200:
        description: Updated identity list after adding the new entry.
        schema:
          type: object
          properties:
            identities:
              type: array
              items: {type: string}
      400:
        description: Missing or empty name.
    """
```

### New docstring: `patch_identity` (new PATCH handler at `PATCH /api/identities/<name>`)

```python
@face_bp.route('/api/identities/<name>', methods=['PATCH'])
def patch_identity(name):
    """Rename a face identity across all ground truth boxes and the identity list.
    ---
    parameters:
      - name: name
        in: path
        type: string
        required: true
        description: Current identity name (URL-encoded if it contains spaces).
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [new_name]
          properties:
            new_name:
              type: string
              description: Replacement name.
    responses:
      200:
        description: Rename confirmed. Returns updated identity list and box count changed.
        schema:
          type: object
          properties:
            updated_count:
              type: integer
              description: Number of face boxes that had their identity updated.
            identities:
              type: array
              items: {type: string}
      400:
        description: Missing new_name, or old_name equals new_name.
    """
```

### New docstring: `face_identity_suggestions` (new handler at `GET /api/faces/<hash>/suggestions`)

```python
@face_bp.route('/api/faces/<content_hash>/suggestions')
def face_identity_suggestions(content_hash):
    """Suggest named identities for a face box using embedding similarity.
    ---
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
      - name: box_x
        in: query
        type: number
        format: float
        required: true
        description: Normalised [0,1] left edge of the face box.
      - name: box_y
        in: query
        type: number
        format: float
        required: true
        description: Normalised [0,1] top edge of the face box.
      - name: box_w
        in: query
        type: number
        format: float
        required: true
        description: Normalised [0,1] width of the face box.
      - name: box_h
        in: query
        type: number
        format: float
        required: true
        description: Normalised [0,1] height of the face box.
      - name: k
        in: query
        type: integer
        required: false
        default: 5
        description: Maximum number of suggestions to return.
    responses:
      200:
        description: >
          Top-k identity matches ordered by embedding similarity (highest first).
          Returns an empty list when the embedding index is unavailable.
        schema:
          type: object
          properties:
            suggestions:
              type: array
              items:
                type: object
                properties:
                  identity:
                    type: string
                    description: Matched identity name.
                  content_hash:
                    type: string
                    description: Hash of the photo the matched face came from.
                  box_index:
                    type: integer
                    description: Box index within that photo's face box list.
                  score:
                    type: number
                    format: float
                    description: Cosine similarity score (0–1; higher is better).
      400:
        description: Missing or non-numeric box_x/box_y/box_w/box_h.
      404:
        description: Photo not found in the index, or photo file missing on disk.
      500:
        description: Failed to decode the image file.
    """
```

### New docstring: `face_crop` (new handler at `GET /api/faces/<hash>/crop/<box_index>`)

```python
@face_bp.route('/api/faces/<content_hash>/crop/<int:box_index>')
def face_crop(content_hash, box_index):
    """Return a JPEG crop of a labeled face box.
    ---
    produces:
      - image/jpeg
    parameters:
      - name: content_hash
        in: path
        type: string
        required: true
        description: SHA-256 content hash or unambiguous prefix.
      - name: box_index
        in: path
        type: integer
        required: true
        description: 0-based index of the face box in the photo's face box list.
    responses:
      200:
        description: JPEG image of the cropped face region.
        schema:
          type: string
          format: binary
      404:
        description: >
          Photo not found, box index out of range, box has no coordinates
          (legacy entry), or photo file missing on disk.
    """
```

## Changes: `benchmarking/routes_benchmark.py`

### New docstring: `api_freeze` (POST handler at `POST /api/freeze`)

```python
@benchmark_bp.route('/api/freeze', methods=['POST'])
def api_freeze():
    """Freeze a named snapshot of a set of photo hashes.
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required: [name, hashes]
          properties:
            name:
              type: string
              description: Unique name for the snapshot (slug-style, no spaces).
            description:
              type: string
              description: Human-readable description. Defaults to empty string.
            hashes:
              type: array
              description: Full SHA-256 content hashes of the photos to include.
              items: {type: string}
    responses:
      200:
        description: Snapshot metadata for the newly created freeze.
        schema:
          type: object
          description: >
            Fields from SnapshotMetadata.to_dict(). Includes at minimum 'name',
            'description', 'created_at', and 'count'.
      400:
        description: Missing name or empty hashes list.
      409:
        description: A snapshot with this name already exists.
    """
```

## Changes: `docs/API_DESIGN.md` (new file)

Create this file to record the URL conventions decided across tasks 019, 020, and 023
so future contributors do not have to reconstruct them from task history.

Contents:

```markdown
# API Design Conventions

## Namespace split

| Namespace | Purpose | Response type |
|-----------|---------|---------------|
| `/api/…` | JSON API — all programmatic endpoints | `application/json` |
| `/bibs/…` | Bib labeling UI | HTML |
| `/faces/…` | Face labeling UI | HTML |
| `/associations/…` | Bib-face link labeling UI | HTML |
| `/benchmark/…` | Benchmark run inspection UI | HTML |
| `/media/…` | Binary file serving (photos, artifacts) | `image/jpeg` etc. |

UI routes and media routes are **not** documented in Swagger (`/apidocs/`).

## HTTP method conventions

| Method | Meaning | Idempotent |
|--------|---------|------------|
| GET | Fetch a resource or list | Yes |
| PUT | Replace a resource in full | Yes |
| POST | Create a new resource | No |
| PATCH | Partial update (e.g. rename) | Yes |
| DELETE | Remove a resource | Yes |

Save operations (bib boxes, face boxes, associations) use **PUT** because they replace
the entire resource for a given photo. The content hash goes in the URL, not the body.

## Resource URL shape

```
GET  /api/<resource>/           list (returns {"items": [...], "count": N})
POST /api/<resource>/           create
GET  /api/<resource>/<id>       detail
PUT  /api/<resource>/<id>       full replace
PATCH /api/<resource>/<id>      partial update
DELETE /api/<resource>/<id>     remove
```

Sub-resources are nested:

```
GET /api/faces/<hash>/crop/<box_index>
GET /api/faces/<hash>/suggestions
```

## No verbs in URLs

URLs name resources, not actions. Use HTTP methods for the action.

| Wrong (RPC style) | Right (REST) |
|-------------------|--------------|
| `POST /api/rename_identity` | `PATCH /api/identities/<name>` |
| `POST /api/save_label` | `PUT /api/bibs/<hash>` |

## Naming relationships

When a resource links two equal-standing entities, name it after the **relationship**,
not either participant. Example: bib-face associations are at `/api/associations/<hash>`
and `/associations/<hash>`, not `/bibs/<hash>/links` or `/faces/<hash>/links`.

## Photo hash addressing

Every per-photo endpoint accepts either a full SHA-256 hash or an unambiguous prefix
(minimum 8 characters). The server resolves the prefix to a full hash and returns 404
if no match or if the prefix is ambiguous.

## Backward-compatibility shims

When a URL is renamed, the old URL stays as a redirect shim:

- **UI routes**: 301 Moved Permanently (browser caches the redirect)
- **API routes**: 308 Permanent Redirect (preserves the HTTP method)
- **Retired POST endpoints** replaced by PUT: return 410 Gone with a JSON error body
  pointing to the new URL, so callers get a clear signal rather than a silent redirect.

Shim handlers must **not** contain Flasgger YAML docstrings. Flasgger parses any
docstring containing `---` and would publish the shim as a real endpoint in `/apidocs/`.

## Swagger UI

Available at `http://localhost:30002/apidocs/`. Only `/api/…` endpoints are documented.
Powered by Flasgger; docstrings use OpenAPI 2.0 YAML format.
```

## Tests

Add to `tests/test_web_app.py` (or a new `tests/test_swagger.py`):

- `test_apidocs_returns_200()` — GET `/apidocs/` returns 200 and HTML content
- `test_swagger_json_contains_api_bibs()` — GET `/apispec_1.json` (Flasgger's spec
  endpoint) returns JSON with `/api/bibs/{content_hash}` in `paths`
- `test_swagger_json_contains_api_faces()` — same check for `/api/faces/{content_hash}`
- `test_swagger_json_contains_api_identities()` — same check for `/api/identities`
- `test_swagger_json_excludes_ui_routes()` — confirm `/bibs/` and `/faces/` are
  absent from `paths` in the spec JSON
- `test_swagger_json_excludes_media_routes()` — confirm `/media/photos/` is absent

## Scope boundaries

- **In scope**: Flasgger installation and wiring in `create_app()`; YAML docstrings
  on the 12 canonical `/api/…` handlers listed in this task
- **Out of scope**: UI routes (`/bibs/`, `/faces/`, `/associations/`, `/benchmark/`);
  media routes (`/media/photos/`, `/media/artifacts/`); 308/410 redirect shim handlers;
  any marshmallow schema or OpenAPI 3.0 migration
- **Do not** add a Flasgger `---` block to shim handlers — Flasgger will parse any
  docstring containing `---` and produce ghost entries in `/apidocs/`
- **Do not** document `POST /api/labels`, `POST /api/face_labels`,
  `GET /api/bib_boxes/<hash>`, `GET /api/face_boxes/<hash>`,
  `GET /api/bib_face_links/<hash>`, `PUT /api/bib_face_links/<hash>`,
  `GET /api/face_identity_suggestions/<hash>`, `GET /api/face_crop/<hash>/<idx>`,
  or `POST /api/rename_identity` — those are the shim routes superseded by task-020
