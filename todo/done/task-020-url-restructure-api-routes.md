# Task 020: URL restructure — API routes

Depends on task-019 (UI routes, same theme). Independent of tasks 006–011.

## Goal

Restructure all `/api/…` endpoints to use consistent, resource-centric, nested URLs;
change bib/face save endpoints from POST-with-hash-in-body to PUT-with-hash-in-URL;
fix the verb-in-URL anti-pattern on identity rename.

## Background

Reviewed in `API_REVIEW.md`. Key problems:

- `POST /api/labels` has no subject prefix; `POST /api/face_labels` does — asymmetric.
- Both save endpoints use POST but are idempotent full-replacements — should be PUT.
- `GET /api/bib_boxes/<hash>` and `GET /api/face_boxes/<hash>` use flat URLs; nesting
  under `/api/bibs/` and `/api/faces/` makes sub-resources natural.
- `/api/bib_face_links/<hash>` encodes both subjects in the name; `/api/associations/<hash>`
  reflects the equal-standing relationship (same reasoning as UI task-019).
- `POST /api/rename_identity` has a verb in the URL (RPC style) — should be
  `PATCH /api/identities/<name>`.
- `/api/face_identity_suggestions/<hash>` and `/api/face_crop/<hash>/<idx>` are flat
  where they are sub-resources of a face photo.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| URL for association API | `/api/associations/<hash>` — matches UI namespace |
| Save bib/face: POST vs PUT | PUT with hash in URL — makes intent explicit and is idempotent |
| Rename identity | `PATCH /api/identities/<name>` — standard REST partial update |
| Sub-resources of a photo | Nested: `/api/faces/<hash>/crop/<idx>`, `/api/faces/<hash>/suggestions` |

## Full URL mapping

| Old | New | Method change |
|-----|-----|---------------|
| `POST /api/labels` | `PUT /api/bibs/<hash>` | POST → PUT; hash moves from body to URL |
| `GET /api/bib_boxes/<hash>` | `GET /api/bibs/<hash>` | none |
| `POST /api/face_labels` | `PUT /api/faces/<hash>` | POST → PUT; hash moves from body to URL |
| `GET /api/face_boxes/<hash>` | `GET /api/faces/<hash>` | none |
| `GET /api/bib_face_links/<hash>` | `GET /api/associations/<hash>` | none |
| `PUT /api/bib_face_links/<hash>` | `PUT /api/associations/<hash>` | none |
| `GET /api/face_identity_suggestions/<hash>` | `GET /api/faces/<hash>/suggestions` | none |
| `GET /api/face_crop/<hash>/<idx>` | `GET /api/faces/<hash>/crop/<idx>` | none |
| `GET /api/identities` | `GET /api/identities` | unchanged |
| `POST /api/identities` | `POST /api/identities` | unchanged |
| `POST /api/rename_identity` | `PATCH /api/identities/<name>` | POST → PATCH |
| `POST /api/freeze` | `POST /api/freeze` | unchanged |

Keep old routes as backward-compat shims (return 308 Permanent Redirect) during
transition; remove shims in a follow-up cleanup once all callers are updated.

## Changes: `benchmarking/routes_bib.py`

### Modified: `get_bib_boxes` → route rename only

```python
# OLD
@bib_bp.route('/api/bib_boxes/<content_hash>')
def get_bib_boxes(content_hash): ...

# NEW — add shim, rename primary
@bib_bp.route('/api/bib_boxes/<content_hash>')
def get_bib_boxes_redirect(content_hash):
    return redirect(url_for('bib.get_bib_boxes', content_hash=content_hash), 308)

@bib_bp.route('/api/bibs/<content_hash>', methods=['GET'])
def get_bib_boxes(content_hash): ...    # body unchanged
```

### Modified: `save_label` — POST with hash in body → PUT with hash in URL

```python
# OLD
@bib_bp.route('/api/labels', methods=['POST'])
def save_label():
    data = request.get_json()
    content_hash = data.get('content_hash')
    ...

# NEW — shim for old POST, new PUT handler
@bib_bp.route('/api/labels', methods=['POST'])
def save_label_legacy():
    """Legacy shim: redirect to PUT /api/bibs/<hash>."""
    data = request.get_json(silent=True) or {}
    h = data.get('content_hash', '')
    if not h:
        return jsonify({'error': 'Missing content_hash'}), 400
    # Re-issue as PUT (client must follow redirect and re-send body)
    # Better: process here and warn, or just drop once JS is updated.
    return jsonify({'error': 'Use PUT /api/bibs/<hash>'}), 410

@bib_bp.route('/api/bibs/<content_hash>', methods=['PUT'])
def save_bib_label(content_hash):
    """Save bib boxes + tags + split for a photo. Replaces all existing data."""
    data = request.get_json()
    tags = data.get('tags', [])
    split = data.get('split', 'full')
    # content_hash now comes from URL; no longer read from body
    ...
```

### Modified: `get_bib_face_links` and `save_bib_face_links` — route rename only

```python
# OLD
@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['GET'])
@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['PUT'])

# NEW — shims + primary
@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['GET'])
def get_bib_face_links_redirect(content_hash):
    return redirect(url_for('bib.get_associations', content_hash=content_hash), 308)

@bib_bp.route('/api/associations/<content_hash>', methods=['GET'])
def get_associations(content_hash): ...    # body of get_bib_face_links

@bib_bp.route('/api/associations/<content_hash>', methods=['PUT'])
def save_associations(content_hash): ...   # body of save_bib_face_links
```

## Changes: `benchmarking/routes_face.py`

### Modified: `get_face_boxes` — route rename

```python
# OLD
@face_bp.route('/api/face_boxes/<content_hash>')
def get_face_boxes(content_hash): ...

# NEW
@face_bp.route('/api/face_boxes/<content_hash>')
def get_face_boxes_redirect(content_hash):
    return redirect(url_for('face.get_face_boxes', content_hash=content_hash), 308)

@face_bp.route('/api/faces/<content_hash>', methods=['GET'])
def get_face_boxes(content_hash): ...
```

### Modified: `save_face_label` — POST → PUT with hash in URL

```python
# OLD
@face_bp.route('/api/face_labels', methods=['POST'])
def save_face_label():
    data = request.get_json()
    content_hash = data.get('content_hash')
    ...

# NEW
@face_bp.route('/api/face_labels', methods=['POST'])
def save_face_label_legacy():
    return jsonify({'error': 'Use PUT /api/faces/<hash>'}), 410

@face_bp.route('/api/faces/<content_hash>', methods=['PUT'])
def save_face_label(content_hash):
    """Save face boxes + tags for a photo. Replaces all existing data."""
    data = request.get_json()
    # content_hash comes from URL
    ...
```

### Modified: `face_crop` — nest under `/api/faces/<hash>/crop/<idx>`

```python
# OLD
@face_bp.route('/api/face_crop/<content_hash>/<int:box_index>')
def face_crop(content_hash, box_index): ...

# NEW
@face_bp.route('/api/face_crop/<content_hash>/<int:box_index>')   # shim
def face_crop_redirect(content_hash, box_index):
    return redirect(url_for('face.face_crop', content_hash=content_hash, box_index=box_index), 308)

@face_bp.route('/api/faces/<content_hash>/crop/<int:box_index>')
def face_crop(content_hash, box_index): ...   # body unchanged
```

### Modified: `face_identity_suggestions` — nest under `/api/faces/<hash>/suggestions`

```python
# OLD
@face_bp.route('/api/face_identity_suggestions/<content_hash>')
def face_identity_suggestions(content_hash): ...

# NEW
@face_bp.route('/api/face_identity_suggestions/<content_hash>')   # shim
def face_identity_suggestions_redirect(content_hash):
    return redirect(
        url_for('face.face_identity_suggestions', content_hash=content_hash)
        + '?' + request.query_string.decode(), 308)

@face_bp.route('/api/faces/<content_hash>/suggestions')
def face_identity_suggestions(content_hash): ...   # body unchanged
```

### Modified: `rename_identity_api` — POST → PATCH with name in URL

```python
# OLD
@face_bp.route('/api/rename_identity', methods=['POST'])
def rename_identity_api():
    data = request.get_json() or {}
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    ...

# NEW
@face_bp.route('/api/rename_identity', methods=['POST'])   # shim
def rename_identity_legacy():
    return jsonify({'error': 'Use PATCH /api/identities/<name>'}), 410

@face_bp.route('/api/identities/<name>', methods=['PATCH'])
def patch_identity(name):
    """Rename an identity. Body: {"new_name": "..."}"""
    data = request.get_json() or {}
    new_name = data.get('new_name', '').strip()
    old_name = name.strip()
    ...   # rest of body unchanged, old_name now from URL
```

## Changes: `benchmarking/static/labeling.js`

The `fetchBoxes()` function builds the GET URL from `state.apiBase`:

```javascript
// OLD
const endpoint = state.mode === 'bibs'
    ? state.apiBase + '/api/bib_boxes/' + state.contentHash
    : state.apiBase + '/api/face_boxes/' + state.contentHash;

// NEW
const endpoint = state.mode === 'bibs'
    ? state.apiBase + '/api/bibs/' + state.contentHash
    : state.apiBase + '/api/faces/' + state.contentHash;
```

## Changes: `benchmarking/static/bib_labeling_ui.js`

`saveUrl` is passed via `PAGE_DATA` from the template. After task-020 this will be
a per-photo URL (PUT). The JS `fetch()` call already uses `PAGE_DATA.saveUrl` —
only the method needs to change:

```javascript
// OLD (in saveBibs / submit handler)
const response = await fetch(PAGE_DATA.saveUrl, {
    method: 'POST',
    ...

// NEW
const response = await fetch(PAGE_DATA.saveUrl, {
    method: 'PUT',
    ...
```

`content_hash` must be removed from the JSON body (the URL carries it now).

## Changes: `benchmarking/static/face_labeling_ui.js`

Same as bib:
- Change method to `PUT` in the save `fetch()` call.
- Remove `content_hash` from the JSON body.
- Update `/api/identities` calls — URL unchanged.
- Update `/api/face_identity_suggestions/…` → `/api/faces/…/suggestions`.
- Update `/api/face_crop/…` → `/api/faces/…/crop/…`.

Specifically:

```javascript
// OLD
fetch('/api/face_identity_suggestions/' + contentHash + '?' + params, ...)

// NEW
fetch('/api/faces/' + contentHash + '/suggestions?' + params, ...)
```

```javascript
// OLD
img.src = '/api/face_crop/' + s.content_hash + '/' + s.box_index;

// NEW
img.src = '/api/faces/' + s.content_hash + '/crop/' + s.box_index;
```

## Changes: `benchmarking/static/link_labeling_ui.js`

```javascript
// OLD
fetch('/api/bib_face_links/' + contentHash, ...)   // appears twice (GET + PUT)

// NEW
fetch('/api/associations/' + contentHash, ...)
```

## Changes: templates — saveUrl and labelsIndexUrl in PAGE_DATA

`labeling.html` and `face_labeling.html` pass `saveUrl` via `PAGE_DATA`. After this
task the save URL is per-photo (PUT), not a static endpoint:

```html
<!-- OLD in labeling.html -->
saveUrl: '{{ url_for("bib.save_label") }}',

<!-- NEW -->
saveUrl: '{{ url_for("bib.save_bib_label", content_hash=content_hash[:8]) }}',
```

```html
<!-- OLD in face_labeling.html -->
saveUrl: '{{ url_for("face.save_face_label") }}',

<!-- NEW -->
saveUrl: '{{ url_for("face.save_face_label", content_hash=content_hash[:8]) }}',
```

Note: handler names `save_bib_label` and `save_face_label` are the new names from the
route changes above.

## Tests

- `test_get_bibs_returns_boxes()` — GET `/api/bibs/<hash>` returns boxes JSON
- `test_put_bibs_saves_label()` — PUT `/api/bibs/<hash>` with boxes body → 200
- `test_get_faces_returns_boxes()` — GET `/api/faces/<hash>` returns boxes JSON
- `test_put_faces_saves_label()` — PUT `/api/faces/<hash>` with boxes body → 200
- `test_get_associations()` — GET `/api/associations/<hash>` returns links
- `test_put_associations()` — PUT `/api/associations/<hash>` replaces links
- `test_patch_identity()` — PATCH `/api/identities/<name>` renames across GT
- `test_old_bib_boxes_url_redirects()` — GET `/api/bib_boxes/<hash>` → 308
- `test_old_face_boxes_url_redirects()` — GET `/api/face_boxes/<hash>` → 308
- `test_old_bib_face_links_url_redirects()` — GET `/api/bib_face_links/<hash>` → 308
- `test_old_rename_identity_returns_410()` — POST `/api/rename_identity` → 410
- `test_old_save_label_returns_410()` — POST `/api/labels` → 410

## Scope boundaries

- **In scope**: `/api/…` route URLs, HTTP methods, handler names, JS `fetch()` URL strings, template `PAGE_DATA.saveUrl`
- **Out of scope**: UI routes — handled in task-019; blueprint names; ground_truth schema; scoring; runner
- **Do not** merge GET and PUT handlers into a single function — keep them separate for readability
