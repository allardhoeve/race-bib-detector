# Task 021: Introduce a service layer and split routes_face.py

Depends on task-019 and task-020 (URL restructure). Independent of task-011.

## Goal

Introduce a `benchmarking/services/` package that separates business logic from
HTTP routing. Route handlers become thin: validate input, call service, return
JSON or render template. Also split `routes_face.py` into two files because
identities are a separate resource that does not belong with face-photo labeling.

## Background

Route handlers currently mix three concerns:
- **HTTP layer**: parse request, build response.
- **Business logic**: construct domain objects, apply validation rules, decide
  what to save.
- **Data access**: call `load_*/save_*` functions from `ground_truth.py`.

The developer's mental model follows Django's separation: Model (data classes in
`ground_truth.py`) / View (HTTP handlers) / Service (business logic that connects
the two). As in DRF, each *resource* gets its own file; if a file grows large it
becomes a sub-package.

Section 5 of `API_REVIEW.md` describes this layering in more detail and should be
treated as the authoritative design reference for this task.

## Context

The `ground_truth.py` data classes (`BibBox`, `BibPhotoLabel`, `FaceBox`,
`FacePhotoLabel`, `BibFaceLink`) stay as the **model** layer — no changes needed
there.

`label_utils.py` already extracts some shared query helpers (`get_filtered_hashes`,
`find_hash_by_prefix`). The new service layer sits one level above it: services
call `label_utils` helpers and `ground_truth` load/save functions.

Tasks 019 and 020 restructure the URLs. This task must be done *after* those so
that services are built on top of the final URL shape and handler signatures, not
the old ones. If 019/020 are not yet done, do not start this task.

The migration must be incremental: introduce `services/`, migrate one resource at a
time, keep existing route function signatures and return values intact throughout.
No big-bang rewrite.

## Constraints

- Do **not** move templates or JavaScript files — this is Python backend structure
  only.
- Do **not** change any URL paths or HTTP methods in this task; URL shape is owned
  by task-019 and task-020.
- The public interface of each service function must be usable without a Flask
  request context (so services can be tested without a test client).
- Keep `ground_truth.py` and `label_utils.py` unchanged.

## Design decisions (resolved)

| Question | Decision |
|----------|----------|
| Where to put services? | New `benchmarking/services/` package, one module per resource subject |
| Split routes_face.py? | Yes — `routes_face.py` keeps face-photo labeling; `routes_identities.py` gets identity CRUD |
| Migrate all at once? | No — migrate one resource at a time, keep all route signatures intact |
| Service functions or classes? | Plain module-level functions (no classes); mirrors the existing `load_*/save_*` function style |
| Move embedding/crop logic? | `face_service.py` wraps `_get_embedding_index` and `_load_image_rgb`; removes them from routes_face.py |
| Test the services? | Unit tests directly on service functions, no Flask test client needed |

## Changes: `benchmarking/services/`

Create the package directory and `__init__.py`.

### New file: `benchmarking/services/__init__.py`

```python
"""Service layer — business logic between HTTP routes and ground_truth.py."""
```

### New file: `benchmarking/services/bib_service.py`

```python
"""Business logic for bib photo labeling."""

import random
from benchmarking.ground_truth import (
    BibBox,
    BibPhotoLabel,
    load_bib_ground_truth,
    save_bib_ground_truth,
)
from benchmarking.ghost import load_suggestion_store
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index
from config import ITERATION_SPLIT_PROBABILITY


def get_bib_label(content_hash: str) -> dict | None:
    """Return serialised bib label data for a photo hash prefix, or None if not found.

    Returns a dict ready to be passed to jsonify():
        {boxes, suggestions, tags, split, labeled}
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions = [s.to_dict() for s in photo_sugg.bibs] if photo_sugg else []

    if label:
        return {
            'full_hash': full_hash,
            'boxes': [b.to_dict() for b in label.boxes],
            'suggestions': suggestions,
            'tags': label.tags,
            'split': label.split,
            'labeled': label.labeled,
        }
    return {
        'full_hash': full_hash,
        'boxes': [],
        'suggestions': suggestions,
        'tags': [],
        'split': 'full',
        'labeled': False,
    }


def save_bib_label(content_hash: str, boxes_data: list[dict] | None,
                   bibs_legacy: list[int] | None, tags: list[str],
                   split: str) -> None:
    """Construct a BibPhotoLabel and persist it.

    Raises ValueError on invalid data (propagate to HTTP layer as 400).
    """
    bib_gt = load_bib_ground_truth()
    if boxes_data is not None:
        boxes = [BibBox.from_dict(b) for b in boxes_data]
    elif bibs_legacy is not None:
        boxes = [BibBox(x=0, y=0, w=0, h=0, number=str(b), scope="bib")
                 for b in bibs_legacy]
    else:
        boxes = []
    label = BibPhotoLabel(
        content_hash=content_hash,
        boxes=boxes,
        tags=tags,
        split=split,
        labeled=True,
    )
    bib_gt.add_photo(label)
    save_bib_ground_truth(bib_gt)


def default_split_for_hash(content_hash: str) -> str:
    """Return the existing split for a hash, or randomly assign one."""
    bib_gt = load_bib_ground_truth()
    label = bib_gt.get_photo(content_hash)
    if label:
        return label.split
    return 'iteration' if random.random() < ITERATION_SPLIT_PROBABILITY else 'full'
```

### New file: `benchmarking/services/face_service.py`

```python
"""Business logic for face photo labeling."""

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from benchmarking.face_embeddings import build_embedding_index, find_top_k, EmbeddingIndex
from benchmarking.ghost import load_suggestion_store
from benchmarking.ground_truth import (
    FaceBox,
    FacePhotoLabel,
    load_face_ground_truth,
    save_face_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index, get_path_for_hash

logger = logging.getLogger(__name__)

PHOTOS_DIR = Path(__file__).parent.parent.parent / "photos"

_embedding_index_cache: dict[str, EmbeddingIndex] = {}


def get_embedding_index() -> EmbeddingIndex | None:
    """Build or return cached embedding index."""
    if 'index' not in _embedding_index_cache:
        try:
            from faces.embedder import get_face_embedder
            embedder = get_face_embedder()
            face_gt = load_face_ground_truth()
            index = load_photo_index()
            _embedding_index_cache['index'] = build_embedding_index(
                face_gt, PHOTOS_DIR, index, embedder
            )
        except Exception as e:
            logger.exception("Failed to build embedding index: %s", e)
            return None
    return _embedding_index_cache['index']


def load_image_rgb(photo_path: Path):
    """Load a photo and return an RGB numpy array, or None on failure."""
    image_data = photo_path.read_bytes()
    arr = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        return None
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def get_face_label(content_hash: str) -> dict | None:
    """Return serialised face label data for a hash prefix, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)

    store = load_suggestion_store()
    photo_sugg = store.get(full_hash)
    suggestions = [s.to_dict() for s in photo_sugg.faces] if photo_sugg else []

    if label:
        return {
            'full_hash': full_hash,
            'boxes': [b.to_dict() for b in label.boxes],
            'suggestions': suggestions,
            'tags': label.tags,
        }
    return {
        'full_hash': full_hash,
        'boxes': [],
        'suggestions': suggestions,
        'tags': [],
    }


def save_face_label(content_hash: str, boxes_data: list[dict] | None,
                    tags: list[str]) -> None:
    """Construct a FacePhotoLabel and persist it.

    Raises ValueError or TypeError on invalid data.
    """
    face_gt = load_face_ground_truth()
    boxes = [FaceBox.from_dict(b) for b in boxes_data] if boxes_data else []
    label = FacePhotoLabel(content_hash=content_hash, boxes=boxes, tags=tags)
    face_gt.add_photo(label)
    save_face_ground_truth(face_gt)


def get_face_crop_jpeg(content_hash: str, box_index: int) -> bytes | None:
    """Return JPEG bytes of a labeled face crop, or None if not found."""
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    face_gt = load_face_ground_truth()
    label = face_gt.get_photo(full_hash)
    if not label or box_index < 0 or box_index >= len(label.boxes):
        return None

    box = label.boxes[box_index]
    if not box.has_coords:
        return None

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return None

    img = Image.open(photo_path)
    w, h = img.size
    left = int(box.x * w)
    upper = int(box.y * h)
    right = int((box.x + box.w) * w)
    lower = int((box.y + box.h) * h)
    crop = img.crop((left, upper, right, lower))

    buf = io.BytesIO()
    crop.save(buf, format='JPEG', quality=85)
    buf.seek(0)
    return buf.read()


def get_identity_suggestions(content_hash: str, box_x: float, box_y: float,
                              box_w: float, box_h: float, k: int = 5) -> list[dict] | None:
    """Return top-k identity suggestions for a face box region.

    Returns None if the photo is not found. Returns [] if no embedding index
    is available or the face crop yields no embeddings.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None

    emb_index = get_embedding_index()
    if emb_index is None or emb_index.size == 0:
        return []

    photo_path = get_path_for_hash(full_hash, PHOTOS_DIR, index)
    if not photo_path or not photo_path.exists():
        return None

    image_rgb = load_image_rgb(photo_path)
    if image_rgb is None:
        return None

    h_px, w_px = image_rgb.shape[:2]
    from geometry import rect_to_bbox
    bbox = rect_to_bbox(int(box_x * w_px), int(box_y * h_px),
                        int(box_w * w_px), int(box_h * h_px))

    from faces.embedder import get_face_embedder
    embeddings = get_face_embedder().embed(image_rgb, [bbox])
    if not embeddings:
        return []

    matches = find_top_k(embeddings[0], emb_index, k=k)
    return [m.to_dict() for m in matches]
```

### New file: `benchmarking/services/identity_service.py`

```python
"""Business logic for identity CRUD and bulk-rename across face GT."""

from benchmarking.ground_truth import load_face_ground_truth, save_face_ground_truth
from benchmarking.identities import load_identities, add_identity, rename_identity


def list_identities() -> list[str]:
    return load_identities()


def create_identity(name: str) -> list[str]:
    """Add a new identity. Returns updated identity list."""
    return add_identity(name)


def rename_identity_across_gt(old_name: str, new_name: str) -> tuple[int, list[str]]:
    """Rename an identity in face GT boxes and the identities list.

    Returns (updated_count, new_identity_list).
    Raises ValueError if old_name == new_name.
    """
    if old_name == new_name:
        raise ValueError("old_name and new_name are the same")

    face_gt = load_face_ground_truth()
    updated_count = 0
    for label in face_gt.photos.values():
        for box in label.boxes:
            if box.identity == old_name:
                box.identity = new_name
                updated_count += 1
    save_face_ground_truth(face_gt)

    ids = rename_identity(old_name, new_name)
    return updated_count, ids
```

### New file: `benchmarking/services/association_service.py`

```python
"""Business logic for bib-face link associations."""

from benchmarking.ground_truth import (
    BibFaceLink,
    load_link_ground_truth,
    save_link_ground_truth,
)
from benchmarking.label_utils import find_hash_by_prefix
from benchmarking.photo_index import load_photo_index


def get_associations(content_hash: str) -> list[list[int]] | None:
    """Return links for a hash prefix as [[bib_index, face_index], ...].

    Returns None if the hash prefix is not found.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None
    link_gt = load_link_ground_truth()
    return [lnk.to_pair() for lnk in link_gt.get_links(full_hash)]


def set_associations(content_hash: str,
                     raw_links: list[list[int]]) -> list[list[int]] | None:
    """Replace all links for a hash prefix. Returns the saved links.

    Returns None if the hash prefix is not found.
    Raises ValueError / TypeError / IndexError on malformed link pairs.
    """
    index = load_photo_index()
    full_hash = find_hash_by_prefix(content_hash, set(index.keys()))
    if not full_hash:
        return None
    links = [BibFaceLink.from_pair(pair) for pair in raw_links]
    link_gt = load_link_ground_truth()
    link_gt.set_links(full_hash, links)
    save_link_ground_truth(link_gt)
    return [lnk.to_pair() for lnk in links]
```

## Changes: `benchmarking/routes_face.py` → split into two files

`routes_face.py` currently contains two distinct resources: face-photo labeling
and identity management. Split them.

### New file: `benchmarking/routes_identities.py`

Extract the identity-related handlers from `routes_face.py` into a new Blueprint.
The blueprint prefix and URL paths are determined by task-019/020; use whatever
they decide. Shown here with the current paths for reference:

```python
"""Identity management routes."""

from flask import Blueprint, jsonify, request

from benchmarking.services.identity_service import (
    list_identities,
    create_identity,
    rename_identity_across_gt,
)

identities_bp = Blueprint('identities', __name__)


@identities_bp.route('/api/identities')
def get_identities():
    return jsonify({'identities': list_identities()})


@identities_bp.route('/api/identities', methods=['POST'])
def post_identity():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Missing name'}), 400
    ids = create_identity(name)
    return jsonify({'identities': ids})


@identities_bp.route('/api/rename_identity', methods=['POST'])
def rename_identity_api():
    """Rename an identity across all face GT entries and the identities list."""
    data = request.get_json() or {}
    old_name = (data.get('old_name') or '').strip()
    new_name = (data.get('new_name') or '').strip()

    if not old_name or not new_name:
        return jsonify({'error': 'Missing old_name or new_name'}), 400

    try:
        updated_count, ids = rename_identity_across_gt(old_name, new_name)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'updated_count': updated_count, 'identities': ids})
```

### Modified: `benchmarking/routes_face.py`

Remove identity handlers and the `rename_identity` import. Replace inline
construction of `FacePhotoLabel` and the embedding/crop logic with calls to the
service layer. The before/after below uses `save_face_label` as the representative
example.

**Before** (current `routes_face.py`, lines 153–185):

```python
@face_bp.route('/api/face_labels', methods=['POST'])
def save_face_label():
    data = request.get_json()

    content_hash = data.get('content_hash')
    face_tags = data.get('face_tags', [])

    if not content_hash:
        return jsonify({'error': 'Missing content_hash'}), 400

    try:
        face_gt = load_face_ground_truth()
        if 'boxes' in data:
            boxes = [FaceBox.from_dict(b) for b in data['boxes']]
        else:
            boxes = []
        label = FacePhotoLabel(
            content_hash=content_hash,
            boxes=boxes,
            tags=face_tags,
        )
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    face_gt.add_photo(label)
    save_face_ground_truth(face_gt)

    return jsonify({'status': 'ok'})
```

**After**:

```python
from benchmarking.services import face_service

@face_bp.route('/api/face_labels', methods=['POST'])
def save_face_label():
    data = request.get_json()

    content_hash = data.get('content_hash')
    face_tags = data.get('face_tags', [])

    if not content_hash:
        return jsonify({'error': 'Missing content_hash'}), 400

    try:
        face_service.save_face_label(
            content_hash=content_hash,
            boxes_data=data.get('boxes'),
            tags=face_tags,
        )
    except (ValueError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'status': 'ok'})
```

Apply the same pattern to `get_face_boxes`, `face_crop`, and
`face_identity_suggestions`: replace the inline implementation with a single
service call, keep the HTTP 404/400/500 logic in the route handler.

Also remove `_get_embedding_index`, `_load_image_rgb`, and `_embedding_index_cache`
from `routes_face.py` — they move into `face_service.py`.

Remove these imports from `routes_face.py` (now unused after the split):
- `from benchmarking.identities import load_identities, add_identity, rename_identity`

### Modified: `benchmarking/routes_bib.py`

Replace inline construction of `BibPhotoLabel` in `save_label` and the inline
fetch of bib boxes in `get_bib_boxes` with calls to `bib_service`.

**Before** (`save_label`, lines 100–136):

```python
@bib_bp.route('/api/labels', methods=['POST'])
def save_label():
    data = request.get_json()

    content_hash = data.get('content_hash')
    tags = data.get('tags', [])
    split = data.get('split', 'full')

    if not content_hash:
        return jsonify({'error': 'Missing content_hash'}), 400

    try:
        bib_gt = load_bib_ground_truth()
        if 'boxes' in data:
            boxes = [BibBox.from_dict(b) for b in data['boxes']]
        else:
            bibs = data.get('bibs', [])
            boxes = [BibBox(x=0, y=0, w=0, h=0, number=str(b), scope="bib") for b in bibs]
        label = BibPhotoLabel(
            content_hash=content_hash,
            boxes=boxes,
            tags=tags,
            split=split,
            labeled=True,
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    bib_gt.add_photo(label)
    save_bib_ground_truth(bib_gt)

    return jsonify({'status': 'ok'})
```

**After**:

```python
from benchmarking.services import bib_service

@bib_bp.route('/api/labels', methods=['POST'])
def save_label():
    data = request.get_json()

    content_hash = data.get('content_hash')
    tags = data.get('tags', [])
    split = data.get('split', 'full')

    if not content_hash:
        return jsonify({'error': 'Missing content_hash'}), 400

    try:
        bib_service.save_bib_label(
            content_hash=content_hash,
            boxes_data=data.get('boxes'),
            bibs_legacy=data.get('bibs'),
            tags=tags,
            split=split,
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    return jsonify({'status': 'ok'})
```

Apply the same pattern to `get_bib_boxes`: replace the inline gt + suggestion
fetch with `bib_service.get_bib_label(content_hash)`.

### Modified: `benchmarking/routes_bib.py` — bib-face link handlers

Replace inline `load_link_ground_truth` / `save_link_ground_truth` calls in
`get_bib_face_links` and `save_bib_face_links` with `association_service` calls.

**After** (`get_bib_face_links`):

```python
from benchmarking.services import association_service

@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['GET'])
def get_bib_face_links(content_hash):
    links = association_service.get_associations(content_hash)
    if links is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"links": links})
```

**After** (`save_bib_face_links`):

```python
@bib_bp.route('/api/bib_face_links/<content_hash>', methods=['PUT'])
def save_bib_face_links(content_hash):
    data = request.get_json()
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400

    try:
        saved = association_service.set_associations(content_hash, data.get("links", []))
    except (TypeError, IndexError, ValueError) as e:
        return jsonify({"error": f"Invalid link format: {e}"}), 400

    if saved is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"status": "ok", "links": saved})
```

## Changes: `benchmarking/web_app.py`

Register the new `identities_bp` blueprint alongside the existing ones:

```python
from benchmarking.routes_identities import identities_bp

def create_app() -> Flask:
    ...
    app.register_blueprint(bib_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(identities_bp)
    app.register_blueprint(benchmark_bp)
    ...
```

## Migration order

1. Create `benchmarking/services/__init__.py` (empty sentinel).
2. Create `bib_service.py` — no existing code changes yet.
3. Migrate `routes_bib.py` → use `bib_service` in `save_label` and `get_bib_boxes`.
4. Create `association_service.py` — no existing code changes yet.
5. Migrate `routes_bib.py` → use `association_service` in the link handlers.
6. Create `identity_service.py` — no existing code changes yet.
7. Create `routes_identities.py` with `identities_bp` using `identity_service`.
8. Register `identities_bp` in `web_app.py`.
9. Remove identity handlers and now-unused imports from `routes_face.py`.
10. Create `face_service.py` — moves `_get_embedding_index` / `_load_image_rgb`.
11. Migrate `routes_face.py` → use `face_service` in all four API handlers.
12. Run all tests after each step; fix any breakage before proceeding.

## Tests

Add `tests/test_bib_service.py`:

- `test_get_bib_label_not_found()` — prefix that matches no hash returns None.
- `test_get_bib_label_no_existing_label()` — known hash with no GT entry returns
  empty boxes/suggestions and labeled=False.
- `test_save_bib_label_boxes()` — saves boxes correctly and sets labeled=True.
- `test_save_bib_label_legacy_bibs()` — legacy bibs list is converted to BibBox
  entries with has_coords=False.
- `test_save_bib_label_invalid_scope()` — ValueError propagates on bad scope.

Add `tests/test_face_service.py`:

- `test_get_face_label_not_found()` — unknown prefix returns None.
- `test_save_face_label_empty_boxes()` — saves with empty box list.
- `test_save_face_label_invalid_scope()` — ValueError propagates.
- `test_get_face_crop_jpeg_no_coords()` — box with has_coords=False returns None.

Add `tests/test_identity_service.py`:

- `test_list_identities()` — returns list from identities file.
- `test_rename_identity_same_name()` — raises ValueError.
- `test_rename_identity_updates_gt_boxes()` — updated_count reflects actual
  mutations; face GT file is rewritten with new name.

Add `tests/test_association_service.py`:

- `test_get_associations_not_found()` — unknown prefix returns None.
- `test_set_then_get()` — round-trip: set links, get links, values match.
- `test_set_associations_invalid_pair()` — malformed pair raises.

## Scope boundaries

- **In scope**: new `services/` package, split of `routes_face.py` into
  `routes_face.py` + `routes_identities.py`, registration of `identities_bp`,
  service unit tests.
- **Out of scope**: URL changes (task-019, task-020), JS/template changes
  (task-011), scoring or runner logic.
- **Do not** modify `ground_truth.py`, `label_utils.py`, `ghost.py`, `scoring.py`,
  or `runner.py`.
- **Do not** change any URL paths or HTTP method choices in route handlers.
