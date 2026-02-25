# Task 013: Refactor face_identity_suggestions() — split mixed concerns

Medium refactor. Independent of other pending tasks.

## Goal

`face_identity_suggestions()` in `routes_face.py:233–302` (68 lines) mixes five distinct
concerns in a single route handler. Split them into named helpers so the route handler
becomes a thin coordinator (~25 lines).

## Current structure (lines 233–302)

1. Hash lookup (lines 236–239)
2. Box parameter parsing (lines 241–247)
3. Embedding index build or cache lookup (lines 251–267) — with module-level state
4. Photo load + image decode (lines 272–284)
5. Bbox conversion + query embedding + similarity search (lines 287–302)

Two issues beyond length:
- `get_face_embedder()` is imported twice inside the function (lines 254 and 295).
- `import cv2 as _cv2` at line 277 is redundant — `cv2` is already imported at module
  level (line 8). The local alias shadows it unnecessarily.

## Changes

### 1. Fix imports at module top

Remove `import cv2 as _cv2` at line 277 (local alias inside function body).
Use the module-level `cv2` directly in the function.

Move both `from faces.embedder import get_face_embedder` (lines 254 and 295) to a
single import at the top of the function (or at module level as a lazy import guarded
by try/except).

### 2. Extract `_get_embedding_index()` helper

```python
def _get_embedding_index() -> EmbeddingIndex | None:
    """Build or return cached embedding index. Returns None on failure."""
    if 'index' not in _embedding_index_cache:
        try:
            from faces.embedder import get_face_embedder
            embedder = get_face_embedder()
            face_gt = load_face_ground_truth()
            index = load_photo_index()
            _embedding_index_cache['index'] = build_embedding_index(
                face_gt, PHOTOS_DIR, index, embedder
            )
            logger.info("Built embedding index: %d faces", _embedding_index_cache['index'].size)
        except Exception as e:
            logger.exception("Failed to build embedding index: %s", e)
            return None
    return _embedding_index_cache['index']
```

### 3. Extract `_load_image_rgb(photo_path: Path) -> np.ndarray | None`

```python
def _load_image_rgb(photo_path: Path):
    """Load a photo file and return an RGB numpy array, or None on failure."""
    image_data = photo_path.read_bytes()
    arr = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return None
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
```

### 4. Slim down the route handler

After the above extractions, `face_identity_suggestions()` becomes:
```python
@face_bp.route('/api/face_identity_suggestions/<content_hash>')
def face_identity_suggestions(content_hash):
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return jsonify({'error': 'Photo not found'}), 404

    try:
        box_x = float(request.args['box_x'])
        box_y = float(request.args['box_y'])
        box_w = float(request.args['box_w'])
        box_h = float(request.args['box_h'])
    except (KeyError, ValueError):
        return jsonify({'error': 'Missing or invalid box_x/box_y/box_w/box_h'}), 400

    k = request.args.get('k', 5, type=int)

    emb_index = _get_embedding_index()
    if emb_index is None or emb_index.size == 0:
        return jsonify({'suggestions': []})

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return jsonify({'error': 'Photo file not found'}), 404

    image_rgb = _load_image_rgb(photo_path)
    if image_rgb is None:
        return jsonify({'error': 'Failed to decode image'}), 500

    h, w = image_rgb.shape[:2]
    from geometry import rect_to_bbox
    bbox = rect_to_bbox(int(box_x * w), int(box_y * h), int(box_w * w), int(box_h * h))

    from faces.embedder import get_face_embedder
    embeddings = get_face_embedder().embed(image_rgb, [bbox])
    if not embeddings:
        return jsonify({'suggestions': []})

    matches = find_top_k(embeddings[0], emb_index, k=k)
    return jsonify({'suggestions': [m.to_dict() for m in matches]})
```

## Note on `_embedding_index_cache`

The module-level `_embedding_index_cache` dict is kept as-is for now (acceptable for a
single-developer tool). Document with a comment that it is intentionally reset only on
process restart, and that tests should call `_embedding_index_cache.clear()` in teardown
if they rely on a fresh index.

## Test strategy

Follow [docs/REFACTORING.md](../../docs/REFACTORING.md). Note: if any test patches
`_embedding_index_cache` directly, its patch path may need updating — see the
[Patch paths](../../docs/REFACTORING.md#patch-paths) section.

- Run `pytest tests/test_web_app.py` — identity suggestion endpoint tests should pass.
- Manual: open a face photo, hover over a face box, verify suggestions appear.

## Scope boundaries

- **In scope**: extracting the two helpers; cleaning up duplicate import + cv2 alias.
- **Out of scope**: changing the cache strategy, the embedding algorithm, or any API
  response format.
