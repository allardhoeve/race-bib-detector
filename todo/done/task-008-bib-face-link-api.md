# Task 008: Bib-face link API routes

Step 5 (part 2/4). Depends on task-007 (link schema). No UI changes.

## Goal

Add `GET` and `PUT` endpoints for bib-face links. Follows the same pattern as the
existing `GET /api/bib_boxes/<hash>` and `PUT /api/bib_boxes/<hash>` in `routes_bib.py`.

## Where to add the routes

Add to `benchmarking/routes_bib.py` — the bib Blueprint owns link management since
links are created during bib labeling. No new Blueprint needed.

## Current API pattern (reference)

```python
# Existing in bib.py — follow this pattern exactly:
@bib_bp.route('/api/bib_boxes/<content_hash>', methods=['GET'])
def get_bib_boxes(content_hash):
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({"error": "Not found"}), 404
    gt = load_bib_ground_truth()
    label = gt.get_photo(full_hash)
    boxes = [b.to_dict() for b in label.boxes] if label else []
    return jsonify({"boxes": boxes})

@bib_bp.route('/api/bib_boxes/<content_hash>', methods=['PUT'])
def save_bib_boxes(content_hash):
    ...
    save_bib_ground_truth(gt)
    return jsonify({"status": "ok", "boxes": [b.to_dict() for b in label.boxes]})
```

## New routes

### `GET /api/bib_face_links/<content_hash>`

```python
@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['GET'])
def get_bib_face_links(content_hash):
    """Return the bib-face links for a photo.

    Response: {"links": [[bib_index, face_index], ...]}
    """
    from benchmarking.ground_truth import load_link_ground_truth
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({"error": "Not found"}), 404
    link_gt = load_link_ground_truth()
    links = link_gt.get_links(full_hash)
    return jsonify({"links": [lnk.to_pair() for lnk in links]})
```

### `PUT /api/bib_face_links/<content_hash>`

```python
@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['PUT'])
def save_bib_face_links(content_hash):
    """Save the bib-face links for a photo. Replaces all existing links.

    Request body: {"links": [[bib_index, face_index], ...]}
    Response: {"status": "ok", "links": [[bib_index, face_index], ...]}
    """
    from benchmarking.ground_truth import (
        BibFaceLink, load_link_ground_truth, save_link_ground_truth
    )
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json()
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400

    raw_links = data.get("links", [])
    try:
        links = [BibFaceLink.from_pair(pair) for pair in raw_links]
    except (TypeError, IndexError, ValueError) as e:
        return jsonify({"error": f"Invalid link format: {e}"}), 400

    link_gt = load_link_ground_truth()
    link_gt.set_links(full_hash, links)
    save_link_ground_truth(link_gt)
    return jsonify({"status": "ok", "links": [lnk.to_pair() for lnk in links]})
```

## Import additions to `routes_bib.py`

The `load_link_ground_truth` and `save_link_ground_truth` imports are inside the route
functions (lazy import pattern already used in some routes) — no top-level changes needed.

If preferred, add to the existing top-level imports from `benchmarking.ground_truth`.

## Tests

Add to `tests/test_web_app.py` (or a new `tests/test_link_api.py`):

- `test_get_links_no_data()` — GET for a hash with no links returns `{"links": []}`.
- `test_put_and_get_links()` — PUT `[[0, 1], [2, 0]]`, then GET returns same list.
- `test_put_links_replaces_all()` — PUT twice; second PUT fully replaces first.
- `test_get_links_unknown_hash()` — GET for unknown hash returns 404.
- `test_put_links_invalid_json()` — PUT with non-JSON body returns 400.
- `test_put_links_empty()` — PUT `[]` clears all links.

### Monkeypatching pattern

Follow the existing path-function pattern (not direct load/save monkeypatching). The
existing `app_client` fixture in `test_web_app.py` patches bib/face/photo-index path
functions but does not patch the link GT path. Either:

**Option A** — extend `app_client` to include the link path (preferred if tests go in
`test_web_app.py`):

```python
link_gt_path = tmp_path / "bib_face_links.json"
monkeypatch.setattr(
    "benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path
)
```

**Option B** — create a separate fixture in a new `tests/test_link_api.py` that reuses
the same pattern:

```python
@pytest.fixture
def link_client(tmp_path, monkeypatch):
    """Flask test client with link GT path and photo index patched."""
    link_gt_path = tmp_path / "bib_face_links.json"
    index_path = tmp_path / "photo_index.json"
    save_photo_index({HASH_A: ["photo_a.jpg"]}, index_path)
    monkeypatch.setattr(
        "benchmarking.ground_truth.get_link_ground_truth_path", lambda: link_gt_path
    )
    monkeypatch.setattr(
        "benchmarking.photo_index.get_photo_index_path", lambda: index_path
    )
    from benchmarking.web_app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()
```

The key point: patch `get_link_ground_truth_path` (the path getter), not
`load_link_ground_truth` or `save_link_ground_truth` directly. This keeps the actual
load/save code exercised and matches how all other GT paths are handled.

## Scope boundaries

- **In scope**: two new routes in `routes_bib.py`, tests.
- **Out of scope**: UI changes (task-009), scoring (task-010).
- **Do not** modify the link schema (task-007) or any existing routes.
